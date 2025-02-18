import copy
from functools import reduce

import numpy as np
from scipy.linalg import eigvalsh_tridiagonal

import torch
import torch.nn.functional as F
from torch.autograd import Variable
from torch.optim.optimizer import Optimizer, required
from torch.nn.utils import vector_to_parameters, parameters_to_vector

from adacurv.torch.optim.hvp_closures import make_fvp_fun, make_gnvp_fun, make_fvp_obj_fun, make_gnvp_obj_fun
from adacurv.torch.optim.hvp_utils import Fvp, Hvp, GNvp
from adacurv.torch.utils.convert_gradients import gradients_to_vector, vector_to_gradients
from adacurv.torch.utils.cg import cg_solve
from adacurv.torch.utils.lanczos import lanczos_iteration, estimate_shrinkage
from adacurv.torch.utils.linesearch import randomized_linesearch

from adacurv.utils.logger import DictLogger

class NaturalAdam(Optimizer):

    def __init__(self,
                 params,
                 lr=required,
                 curv_type=required,
                 betas=(0.9, 0.99),
                 cg_iters=10,
                 cg_residual_tol=1e-10,
                 cg_prev_init_coef=0.5,
                 cg_precondition_empirical=True,
                 cg_precondition_regu_coef=0.001,
                 cg_precondition_exp=0.75,
                 shrinkage_method=None,
                 lanczos_amortization=10,
                 lanczos_iters=20,
                 batch_size=200,
                 assume_locally_linear=False):

        if lr is not required and lr < 0.0:
            raise ValueError("Invalid learning rate: {}".format(lr))

        self.valid_curv_types = ['fisher', 'gauss_newton']
        if curv_type is not required and curv_type not in self.valid_curv_types:
            raise ValueError("Invalid curv_type: " + str(curv_type) + ". Must be one of " + str(valid_curv_types))

        defaults = dict(lr=lr,
                        curv_type=curv_type,
                        betas=betas,
                        cg_iters=cg_iters,
                        cg_residual_tol=cg_residual_tol,
                        cg_prev_init_coef=cg_prev_init_coef,
                        cg_precondition_empirical=cg_precondition_empirical,
                        cg_precondition_regu_coef=cg_precondition_regu_coef,
                        cg_precondition_exp=cg_precondition_exp,
                        shrinkage_method=shrinkage_method,
                        lanczos_amortization=lanczos_amortization,
                        lanczos_iters=lanczos_iters,
                        batch_size=batch_size,
                        assume_locally_linear=assume_locally_linear)
        if cg_iters <= 0:
            raise ValueError("CG iters must be > 0")
        if cg_residual_tol < 0:
            raise ValueError("CG residual tolerance must be >= 0")
        if shrinkage_method == 'lanczos' and lanczos_iters <= 0:
            raise ValueError("Lanczos iters must be > 0")
        if batch_size <= 0:
            raise ValueError("Batch size must be > 0")

        super(NaturalAdam, self).__init__(params, defaults)

        if len(self.param_groups) != 1:
            raise ValueError("Adaptive NGD-CG doesn't support per-parameter options (parameter groups)")

        self.state = {}

        self._numel_cache = None
        self._param_group = self.param_groups[0]
        self._params = self._param_group['params']
        self._params_old = []

        np.random.seed(0)
        for i in range(len(self._params)):
            self._params_old.append(self._params[i] + np.random.normal() * torch.ones(self._params[i].shape) * 0.0001)
        # for i in range(len(self._params)):
        #     self._params_old.append(self._params[i] + torch.randn(self._params[i].shape) * 0.0001)

        self.log = DictLogger(log_dir='/tmp/adacurv/torch/adam_adaptive_ngd_cg/')
        # Add hyperparameters to log
        self.log.log_hyperparam_dict(defaults)

    def _numel(self):
        if self._numel_cache is None:
            self._numel_cache = reduce(lambda total, p: total + p.numel(), self._params, 0)
        return self._numel_cache

    def _make_combined_gnvp_fun(self, closure, theta, theta_old, bias_correction2=1.0):
        beta1, beta2 = self._param_group['betas']
        step = self.state['step']
        c1, z1, tmp_params1 = closure(theta_old)
        c2, z2, tmp_params2 = closure(theta)
        def f(v):
            hessp_beta1 = GNvp(c1, z1, tmp_params1, v)
            hessp_beta2 = GNvp(c2, z2, tmp_params2, v)
            if step >= 1:
                weighted_hessp = beta2 * hessp_beta1 + (1 - beta2) * hessp_beta2
            else:
                weighted_hessp = (1 - beta2) * hessp_beta2
            return weighted_hessp.data / bias_correction2
        return f

    def _make_combined_fvp_fun(self, closure, theta, theta_old, bias_correction2=1.0):
        beta1, beta2 = self._param_group['betas']
        step = self.state['step']
        c1, tmp_params1 = closure(theta_old)
        c2, tmp_params2 = closure(theta)
        def f(v):
            hessp_beta1 = Fvp(c1, tmp_params1, v)
            hessp_beta2 = Fvp(c2, tmp_params2, v)
            if step >= 1:
                weighted_hessp = beta2 * hessp_beta1 + (1 - beta2) * hessp_beta2
            else:
                weighted_hessp = (1 - beta2) * hessp_beta2
            return weighted_hessp.data / bias_correction2
        return f

    def step(self, closure, execute_update=True):
        """Performs a single optimization step.

        Arguments:
            Fvp_fn (callable): A closure that accepts a vector of length equal to the number of
                model paramsters and returns the Fisher-vector product.
        """

        # 0: {
        #     params: ...,
        #     gradient: ...,
        #     cg: {
        #         0: [res, direction, cg_delta],
        #         1: [res, direction, cg_delta],
        #         ...
        #     },
        #     loss: ...
        # },
        #

        state = self.state
        param_vec = parameters_to_vector(self._params)
        self.log.log_kv('params_pre', [p.data.numpy() for p in self._params])
        self.log.log_kv('params_old_pre', [p.data.numpy() for p in self._params_old])

        # State initialization
        if len(state) == 0:
            state['step'] = 0
            # Exponential moving average of gradient values
            state['m'] = torch.zeros_like(param_vec.data)
            # Maintain adaptive preconditioner if needed
            if self._param_group['cg_precondition_empirical']:
                state['M'] = torch.zeros_like(param_vec.data)
            # Set shrinkage to defaults, i.e. no shrinkage
            state['rho'] = 0.0
            state['diag_shrunk'] = 1.0

        m = state['m']
        beta1, beta2 = self._param_group['betas']
        state['step'] += 1

        bias_correction1 = 1 - beta1 ** state['step']
        bias_correction2 = 1 - beta2 ** state['step']

        # Get flat grad
        g = gradients_to_vector(self._params)
        self.log.log_kv('gradient', [p.grad.data.numpy() for p in self._params])

        # Update moving average mean
        m.mul_(beta1).add_(1 - beta1, g)
        g_hat = m / bias_correction1

        self.log.log_kv('m', m.numpy())
        self.log.log_kv('g_hat', g_hat.numpy())

        theta = parameters_to_vector(self._params)
        theta_old = parameters_to_vector(self._params_old)

        if 'ng_prior' not in state:
            state['ng_prior'] = torch.zeros_like(g_hat)

        curv_type = self._param_group['curv_type']
        if curv_type not in self.valid_curv_types:
            raise ValueError("Invalid curv_type.")

        if self._param_group['assume_locally_linear']:
            # Update theta_old beta2 portion towards theta
            theta_old = beta2 * theta_old + (1-beta2) * theta
        else:
            # Do linesearch first to update theta_old. Then can do CG with only one HVP at each itr.
            ng = self.state['ng_prior'].clone() if state['step'] > 1 else g_hat.data.clone()
            if curv_type == 'fisher':
                weighted_fvp_fn = self._make_combined_fvp_fun(closure, self._params, self._params_old) #theta, theta_old)
                f = make_fvp_obj_fun(closure, weighted_fvp_fn, ng)
            elif curv_type == 'gauss_newton':
                weighted_fvp_fn = self._make_combined_gnvp_fun(closure, self._params, self._params_old)
                f = make_gnvp_obj_fun(closure, weighted_fvp_fn, ng)
            xmin, fmin, alpha = randomized_linesearch(f, theta_old.data, theta.data)
            theta_old = Variable(xmin.float())
        vector_to_parameters(theta_old, self._params_old)

        # Now that theta_old has been updated, do CG with only theta old
        if curv_type == 'fisher':
            fvp_fn_div_beta2 = make_fvp_fun(closure,
                                            self._params_old,
                                            bias_correction2=bias_correction2)
        elif curv_type == 'gauss_newton':
            fvp_fn_div_beta2 = make_gnvp_fun(closure,
                                            self._params_old,
                                            bias_correction2=bias_correction2)

        shrinkage_method = self._param_group['shrinkage_method']
        lanczos_amortization = self._param_group['lanczos_amortization']
        if shrinkage_method == 'lanczos' and (state['step']-1) % lanczos_amortization == 0:
            # print ("Computing Lanczos shrinkage at step ", state['step'])
            w = lanczos_iteration(fvp_fn_div_beta2, self._numel(), k=self._param_group['lanczos_iters'])
            rho, diag_shrunk = estimate_shrinkage(w, self._numel(), self._param_group['batch_size'])
            print ("Lanc eigs: ", w)
            print ("Lanc shrink (rho, diag): ", rho, diag_shrunk)

            state['rho'] = rho
            state['diag_shrunk'] = diag_shrunk

        M = None
        if self._param_group['cg_precondition_empirical']:
            # Empirical Fisher is g * g
            V = state['M']
            Mt = (g * g + self._param_group['cg_precondition_regu_coef'] * torch.ones_like(g)) ** self._param_group['cg_precondition_exp']
            V.mul_(beta2).add_(1 - beta2, Mt)
            M = V / bias_correction2

            self.log.log_kv('M', M.numpy())

        extract_tridiag = self._param_group['shrinkage_method'] == 'cg'
        cg_result = cg_solve(fvp_fn_div_beta2,
                      g_hat.data.clone(),
                      x_0=self._param_group['cg_prev_init_coef'] * state['ng_prior'],
                      M=M,
                      cg_iters=self._param_group['cg_iters'],
                      cg_residual_tol=self._param_group['cg_residual_tol'],
                      shrunk=self._param_group['shrinkage_method'] is not None,
                      rho=state['rho'],
                      Dshrunk=state['diag_shrunk'],
                      extract_tridiag=extract_tridiag)

        cg_log = cg_result['cg_log']
        self.log.log_kv('cg', cg_log)

        if extract_tridiag:
            # print ("Computing CG shrinkage at step ", state['step'])
            ng = cg_result['x']
            (diag_elems, off_diag_elems) = cg_result['diag']
            w = eigvalsh_tridiagonal(diag_elems, off_diag_elems)
            rho, diag_shrunk = estimate_shrinkage(w, self._numel(), self._param_group['batch_size'])
            state['rho'] = rho
            state['diag_shrunk'] = diag_shrunk
        else:
            ng = cg_result['x']

        self.log.log_kv('natural_gradient', ng.numpy())
        self.log.log_kv('natural_gradient_prior', self.state['ng_prior'].numpy())

        self.state['ng_prior'] = ng.data.clone()


        # Normalize NG
        lr = self._param_group['lr']
        alpha = torch.sqrt(torch.abs(lr / (torch.dot(g_hat, ng) + 1e-20)))

        self.log.log_kv('lr', lr)
        self.log.log_kv('alpha', alpha)

        # Unflatten grad
        vector_to_gradients(ng, self._params)

        if execute_update:
            # Apply step
            for p in self._params:
                if p.grad is None:
                    continue
                d_p = p.grad.data
                p.data.add_(-alpha, d_p)

        self.log.log_kv('params_post', [p.data.numpy() for p in self._params])
        self.log.log_kv('params_old_post', [p.data.numpy() for p in self._params_old])

        self.log.save_log()
        self.log.next_iteration()
        return dict(alpha=alpha, delta=lr, natural_grad=ng)

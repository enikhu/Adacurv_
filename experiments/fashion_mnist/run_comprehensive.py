import copy
import arguments
from itertools import product, chain
import ray
import fashion_mnist

ray.init(num_cpus=20)

baselines = True
basic_fisher = True
fisher_all_no_shrunk = True

###
# Common params
###

global_tag = 'fashion_mnist_cnn_large'
seeds = list(range(1))
global_lrs = [0.001, 0.0005]
batch_sizes = [250] #, 500, 1000]
decay = True
epochs = 10
verbose = False
# Some by-hand testing seemed to do OK with larger betas
global_betas = [(0.1, 0.1), (0.9, 0.9)]

###
# Ray remote function simply to launch the run
###

@ray.remote
def run(args, i, n):
    print ("Starting job (" + str(i) + "/" + str(n) +") with args: ", args)
    fashion_mnist.launch_job(args)
    print ("Finished job (" + str(i) + "/" + str(n) + ") with args: ", args)

###
# Start a set of variants
###

def run_variants(variants):
    gets = []

    i = 1
    n = len(variants)
    for variant in variants:
        tag, seed, optim, curv_type, lr, bs, cg_iters, cg_prev_init_coef, cg_precondition_empirical, cg_precondition_regu_coef, cg_precondition_exp, shrinkage_method, lanczos_amortization, lanczos_iters, bts, approx_adaptive = variant

        # if optim in ['natural_adam', 'natural_amsgrad']:
            # if bs == 125:
            #     lr = 0.0001
            # elif bs == 250:
            #     lr = 0.0005

        args = arguments.get_args()
        args.optim = optim
        args.curv_type = curv_type
        args.lr = lr
        args.decay_lr = decay
        args.epochs = epochs
        args.batch_size = bs

        args.cg_iters = cg_iters
        args.cg_prev_init_coef = cg_prev_init_coef
        args.cg_precondition_empirical = cg_precondition_empirical
        args.cg_precondition_regu_coef = cg_precondition_regu_coef
        args.cg_precondition_exp = cg_precondition_exp

        args.shrinkage_method = shrinkage_method
        args.lanczos_amortization = lanczos_amortization
        args.lanczos_iters = lanczos_iters

        args.beta1 = bts[0]
        args.beta2 = bts[1]
        args.approx_adaptive = approx_adaptive

        args.seed = seed
        args.log_dir = 'results/'+str(tag)
        args.verbose = verbose

        pid = run.remote(args, i, n)
        i += 1
        gets.append(pid)

    ray.get([pid for pid in gets])


all_variants = []

###
# Run baselines only once
###

if baselines:
    tag = global_tag if global_tag is not None else 'baselines'
    lrs = [0.01, 0.005, 0.001]
    variants1 = product([tag],
                        seeds,
                        ['adam'],      # optim
                        [''],                                       # curv_type
                        lrs,                                        # lr
                        batch_sizes,                                # batch size
                        [10],                                       # cg_iters
                        [0.0],                                      # cg_prev_init_coef
                        [False],                                    # cg_precondition_empirical
                        [0.0],                                      # cg_precondition_regu_coef
                        [0.0],                                      # cg_precondition_exp
                        [None],                                     # shrinkage_method
                        [0],                                        # lanzcos_amortization
                        [0],                                        # lanzcos_iters
                        [(0.0, 0.0)],                               # betas (ignored for these optimizers)
                        [False])                                    # approx adaptive

    variants1 = copy.deepcopy(list(variants1))
    print (len(variants1))
    # print (variants1)
    # input("Continue?")
    # run_variants(variants1)
    all_variants = copy.deepcopy(list(chain(all_variants, variants1)))


###
# Run all basic with no preconditioner, no momentum, no amortization, to ensure code not broken
###

if basic_fisher:
    tag = global_tag if global_tag is not None else 'basic_fisher'
    variants1 = product([tag],
                        seeds,
                        ['ngd', 'natural_adam'],          # optim
                        ['fisher'],                                                             # curv_type
                        global_lrs,                                                             # lr
                        batch_sizes,                                                            # batch size
                        [10],                                                                   # cg_iters
                        [0.0],                                                                  # cg_prev_init_coef
                        [False],                                                                # cg_precondition_empirical
                        [0.0],                                                                  # cg_precondition_regu_coef
                        [0.0],                                                                  # cg_precondition_exp
                        [None],                                                                 # shrinkage_method
                        [0],                                                                    # lanzcos_amortization
                        [0],                                                                    # lanzcos_iters
                        global_betas,                                                           # betas
                        [False])                                                                # approx adaptive

    variants1 = list(variants1)
    print (len(variants1))
    all_variants = copy.deepcopy(list(chain(all_variants, variants1)))

###
# Fisher all
###

if fisher_all_no_shrunk:
    tag = global_tag if global_tag is not None else 'fisher_all_no_shrunk'
    variants1 = product([tag],
                        seeds,
                        ['ngd', 'natural_adam'],          # optim
                        ['fisher'],                                                             # curv_type
                        global_lrs,                                                             # lr
                        batch_sizes,                                                            # batch size
                        [10],                                                                   # cg_iters
                        [0.1],                                                                  # cg_prev_init_coef
                        [True],                                                                 # cg_precondition_empirical
                        [0.001],                                                                # cg_precondition_regu_coef
                        [0.75],                                                                 # cg_precondition_exp
                        [None],                                                      # shrinkage_method
                        [0],                                                                   # lanzcos_amortization
                        [0],                                                                   # lanzcos_iters
                        global_betas,                                                           # betas
                        [False])                                                                # approx adaptive

    variants1 = list(variants1)
    print (len(variants1))
    all_variants = copy.deepcopy(list(chain(all_variants, variants1)))

print ("Total:", len(all_variants))
input("Continue?")
run_variants(all_variants)

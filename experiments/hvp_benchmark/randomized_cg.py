
import types
import numpy as np
np.set_printoptions(precision=2)


def cg_solve(F,
             b,
             x_0=None,
             cg_iters=10,
             cg_residual_tol=1e-10,
             damping=1e-4):

    x = np.zeros_like(b) if x_0 is None else x_0
    if x_0 is not None:
        hvp_x0 = F(x) + damping * x
        # isinstance(F, types.FunctionType)
        # hvp_x0 = F @ x + damping * x

    r = b.copy() if x_0 is None else b-hvp_x0
    p = r.copy()
    rdotr = np.dot(r.T, r)
    directions = []
    for i in range(cg_iters):
        # obj = x.T @ (F @ x) - 2 * b.T @ x
        obj = x.T @ F(x) - 2 * b.T @ x
        print ("J: ", obj)
        # hvp_p = F @ p + damping * p
        hvp_p = F(p) + damping * p
        directions.append(r.copy())
        z = hvp_p
        v = rdotr / np.dot(p.T, z) #p.dot(z)
        x += v * p
        r -= v * z
        newrdotr = np.dot(r.T, r) #r.dot(r)
        mu = newrdotr / rdotr
        p = r + mu * p
        rdotr = newrdotr

        if rdotr < cg_residual_tol:
            break

    obj = x.T @ F(x) - 2 * b.T @ x
    print ("J: ", obj)

    nd = len(directions)
    for k in range(nd):
        print ("Norm of direction", k,":", np.linalg.norm(directions[k]))
    M = np.zeros((nd, nd))
    for i in range(nd):
        for j in range(i):
            orth = np.dot(directions[i].T, directions[j])
            M[i,j] = orth
    print (M)

    return x, rdotr

# update residuals but use random directions
def cg_solve_random_new_res_rand_dir(F,
                    b,
                    x_0=None,
                    cg_iters=10,
                    cg_residual_tol=1e-10,
                    damping=1e-4):

    x = np.zeros_like(b) if x_0 is None else x_0
    if x_0 is not None:
        hvp_x0 = F(x) + damping * x

    r = b.copy() if x_0 is None else b-hvp_x0
    p = r.copy()
    rdotr = np.dot(r.T, r)
    rorig = r.copy()
    rnorm = np.linalg.norm(r)
    # print ("Rorig: ", np.linalg.norm(rorig))
    # input("")

    directions = []
    for i in range(cg_iters):
        obj = x.T @ F(x) - 2 * b.T @ x
        print ("J: ", obj)

        # Random update
        d = np.random.randn(A.shape[0], 1)
        d = d / np.linalg.norm(d)
        print ("Norm of d: ", np.linalg.norm(d))
        print ("norm of r: ", rnorm)
        # input("")
        directions.append(d)
        z = F(d) + damping * d
        v = np.dot(d.T, r) / np.dot(d.T, z)
        x += v * d
        r = b - F(x)
        rdotr = np.dot(r.T, r)
        rnorm = np.linalg.norm(r)

        if rdotr < cg_residual_tol:
            print ("Breaking: ", rdotr)
            break

    obj = x.T @ F(x) - 2 * b.T @ x
    print ("J: ", obj)

    nd = len(directions)
    M = np.zeros((nd, nd))
    for i in range(nd):
        for j in range(i):
            orth = np.dot(directions[i].T, directions[j])
            M[i,j] = orth
    print (M)

    return x, rdotr

# or use proper dirctions but use original resid
def cg_solve_random_old_res_new_dir(F,
                    b,
                    x_0=None,
                    cg_iters=10,
                    cg_residual_tol=1e-10,
                    damping=1e-4):

    x = np.zeros_like(b) if x_0 is None else x_0
    if x_0 is not None:
        hvp_x0 = F(x) + damping * x

    r = b.copy() if x_0 is None else b-hvp_x0
    p = r.copy()
    rorig = r.copy()
    rdotr = np.dot(r.T, r)
    rdotr_orig = rdotr.copy()
    directions = []
    for i in range(cg_iters):
        obj = x.T @ F(x) - 2 * b.T @ x
        print ("J: ", obj)

        hvp_p = F(p) + damping * p

        z = hvp_p
        v = np.dot(p.T, rorig) / np.dot(p.T, z) #p.dot(z)
        x += v * p
        r -= v * z
        newrdotr = np.dot(r.T, r) #r.dot(r)
        mu = newrdotr / rdotr
        p = r + mu * p
        rdotr = newrdotr

        if rdotr < cg_residual_tol:
            break

    obj = x.T @ F(x) - 2 * b.T @ x
    print ("J: ", obj)

    nd = len(directions)
    M = np.zeros((nd, nd))
    for i in range(nd):
        for j in range(i):
            orth = np.dot(directions[i].T, directions[j])
            M[i,j] = orth
    print (M)

    return x, rdotr


# old res coord dir
def cg_solve_random_old_res_coord_dir(F,
                    b,
                    x_0=None,
                    cg_iters=10,
                    cg_residual_tol=1e-10,
                    damping=1e-4):

    x = np.zeros_like(b) if x_0 is None else x_0
    if x_0 is not None:
        hvp_x0 = F(x) + damping * x

    r = b.copy() if x_0 is None else b-hvp_x0
    p = r.copy()

    # print ("P orgin: ", p)
    rorig = r.copy()
    rdotr = np.dot(r.T, r)
    rdotr_orig = rdotr.copy()

    dirs = np.eye(cg_iters)
    directions = []
    for i in range(cg_iters):
        obj = x.T @ F(x) - 2 * b.T @ x
        print ("J: ", obj)

        p = dirs[i][:,np.newaxis]
        # print (p)
        hvp_p = F(p) + damping * p

        z = hvp_p
        v = np.dot(p.T, rorig) / np.dot(p.T, z) #p.dot(z)
        x += v * p
        r -= v * z
        newrdotr = np.dot(r.T, r) #r.dot(r)
        mu = newrdotr / rdotr
        p = r + mu * p
        rdotr = newrdotr

        if rdotr < cg_residual_tol:
            break
    obj = x.T @ F(x) - 2 * b.T @ x
    print ("J: ", obj)

    nd = len(directions)
    M = np.zeros((nd, nd))
    for i in range(nd):
        for j in range(i):
            orth = np.dot(directions[i].T, directions[j])
            M[i,j] = orth
    print (M)

    return x, rdotr

# def cg_solve_random(F,
#                     b,
#                     x_0=None,
#                     cg_iters=10,
#                     cg_residual_tol=1e-10,
#                     damping=1e-4):
#     # x_0 = np.random.randn(F.shape[0],1)
#     x = np.zeros_like(b) if x_0 is None else x_0
#     if x_0 is not None:
#         hvp_x0 = F @ x + damping * x
#
#     r = b.copy() if x_0 is None else b-hvp_x0
#     # rdotr = np.dot(r.T, r)
#
#     obj = x.T @ (F @ x) - 2 * b.T @ x
#     print ("RandJ: ", obj)
#     # 1) generate unit vector of random direction
#     d = r
#     q = F @ d + damping * d
#     alpha = np.dot(d.T, r) / np.dot(d.T, q)
#     x += alpha * d
#
#     r = b - F @ x + damping * x
#
#     for i in range(cg_iters):
#         obj = x.T @ (F @ x) - 2 * b.T @ x
#         print ("RandJ: ", obj)
#         # 1) generate unit vector of random direction
#         d = np.random.randn(A.shape[0], 1)
#         # d = np.random.uniform(low=-1.0, high=1.0, size=(A.shape[0], 1))
#         d /= np.linalg.norm(d)
#
#         q = F @ d + damping * d
#         alpha = np.dot(d.T, r) / np.dot(d.T, q)
#         x += alpha * d
#
#     r_tmp = b - F @ x
#     rdotr_tmp = np.dot(r_tmp.T, r_tmp)
#     return x, rdotr_tmp

if __name__ == '__main__':
    d = 10
    A = np.eye(d)
    # A = np.random.randn(d, 10)
    # A = A @ A.T
    # print (A.shape)
    b = np.random.randn(d, 1)

    def mv(v):
        return A @ (A.T @ v)

    print ("True")
    # x_min, x_resid = cg_solve(A, b)
    x_min, x_resid = cg_solve(mv, b)
    print (x_min.shape, x_resid)

    print ("Random A")
    # x_min_rand, x_resid_rand = cg_solve_random_new_res_rand_dir(A, b)
    x_min_rand, x_resid_rand = cg_solve_random_new_res_rand_dir(mv, b)
    print (x_min_rand.shape, x_resid_rand)

    print ("Random B")
    # # x_min_rand, x_resid_rand = cg_solve_random_old_res_new_dir(A, b)
    x_min_rand, x_resid_rand = cg_solve_random_old_res_new_dir(mv, b)
    # print (x_min_rand.shape, x_resid_rand)

    print ("Random C")
    x_min_rand, x_resid_rand = cg_solve_random_old_res_coord_dir(mv, b)

import numpy as np
from log import logger
import transformations
import scipy.linalg


def C_from_T(T):
    return T[0:3, 0:3]


def r_from_T(T):
    return T[0:3, 3]


def T_from_Ct(C, r):
    T = np.eye(4, 4)
    T[0:3, 0:3] = C
    T[0:3, 3] = r

    return T


def skew3(v):
    assert (type(v) == np.ndarray and v.size == 3) or (type(v) == type([]) and len(v) == 3)

    m = np.zeros([3, 3])
    m[0, 1] = -v[2]
    m[0, 2] = v[1]
    m[1, 0] = v[2]

    m[1, 2] = -v[0]
    m[2, 0] = -v[1]
    m[2, 1] = v[0]

    return m


def unskew3(m):
    assert (m.shape[0] == 3 and m.shape[1] == 3)
    return np.array([m[2, 1], m[0, 2], m[1, 0]])


def log_SO3(C):
    return log_SO3_old(C)


def log_SO3_eigen(C):
    assert (len(C.shape) == 2 and C.shape[0] == 3 and C.shape[1] == 3)

    phi_norm = np.arccos(np.clip((np.trace(C) - 1) / 2, -1.0, 1.0))
    w, v = np.linalg.eig(C)
    a = None
    for i in range(len(v)):
        if np.abs(w[i] - 1.0) < 1e-12:
            a = v[:, i]
            assert (np.linalg.norm(np.imag(a)) < 1e-12)
            a = np.real(a)

    assert (a is not None)
    if np.allclose(exp_SO3(phi_norm * a), C, atol=1e-12):
        return phi_norm * a
    elif np.allclose(exp_SO3(-phi_norm * a), C, atol=1e-12):
        return -phi_norm * a
    else:
        print(exp_SO3(phi_norm * a) - C)
        print(exp_SO3(-phi_norm * a) - C)
        raise ValueError("Invalid logarithmic mapping")


def log_SO3_old(C):
    assert (len(C.shape) == 2 and C.shape[0] == 3 and C.shape[1] == 3)

    arccos = (np.trace(C) - 1) / 2

    if arccos > 1:
        phi = 0.0
        # logger.print("WARNING: invalid arccos: %f\n" % arccos)
        # logger.print("%s\n" % str(C))
    elif arccos < -1:
        phi = np.pi
        # logger.print("WARNING: invalid arccos: %f\n" % arccos)
        # logger.print("%s\n" % str(C))
    else:
        phi = np.arccos((np.trace(C) - 1) / 2)

    assert (phi >= 0 and np.sin(phi) >= 0)

    if phi < np.pi / 2 and np.sin(phi) > 1e-6:
        u = unskew3(C - np.transpose(C)) / (2 * np.sin(phi))
        theta = phi * u
    elif phi < np.pi / 2:
        theta = 0.5 * unskew3(C - C.transpose())
    else:
        theta = unskew3(scipy.linalg.logm(C))

    return theta


def left_jacobi_SO3(phi):
    phi = np.reshape(phi, [3, 1])
    phi_norm = np.linalg.norm(phi)
    if np.abs(phi_norm) > 1e-8:
        a = phi / phi_norm
        J = (np.sin(phi_norm) / phi_norm) * np.eye(3, 3) + (1 - (np.sin(phi_norm) / phi_norm)) * a.dot(
                a.transpose()) + ((1 - np.cos(phi_norm)) / phi_norm) * skew3(a)
    else:
        J = np.eye(3, 3)
    return J


def left_jacobi_SO3_inv(phi):
    phi = np.reshape(phi, [3, 1])
    phi_norm = np.linalg.norm(phi)
    if np.abs(phi_norm) > 1e-8:
        a = phi / phi_norm
        cot_half_phi_norm = 1 / np.tan(phi_norm / 2)
        J_inv = (phi_norm / 2) * cot_half_phi_norm * np.eye(3, 3) + \
                (1 - (phi_norm / 2) * cot_half_phi_norm) * (a.dot(a.transpose())) - (phi_norm / 2) * skew3(a)
    else:
        J_inv = np.eye(3, 3)
    return J_inv


def log_SE3(T):
    C = C_from_T(T)
    r = r_from_T(T)
    phi = log_SO3(C)
    rou = left_jacobi_SO3_inv(phi).dot(r)
    return np.concatenate([rou, phi])


def exp_SO3(phi):
    phi_norm = np.linalg.norm(phi)
    if np.abs(phi_norm) > 1e-8:
        unit_phi = phi / phi_norm
        unit_phi_skewed = skew3(unit_phi)
        m = np.eye(3, 3) + np.sin(phi_norm) * unit_phi_skewed + \
            (1 - np.cos(phi_norm)) * unit_phi_skewed.dot(unit_phi_skewed)
    else:
        phi_skewed = skew3(phi)
        m = np.eye(3, 3) + phi_skewed + 0.5 * phi_skewed.dot(phi_skewed)

    return m


def interpolate_SO3(C1, C2, alpha):
    C_interp = scipy.linalg.fractional_matrix_power(C2.dot(C1.transpose()), alpha).dot(C1)
    if np.linalg.norm(np.imag(C_interp)) > 1e-10:
        logger.print("Bad SO(3) interp:")
        logger.print(C_interp)
    return np.real(C_interp)


def interpolate_SE3(T1, T2, alpha):
    T_interp = scipy.linalg.fractional_matrix_power(T2.dot(np.linalg.inv(T1)), alpha).dot(T1)
    if np.linalg.norm(np.imag(T_interp)) > 1e-10:
        logger.print("Bad SE(3) interp:")
        logger.print(T_interp)
    return np.real(T_interp)


# reorthogonalize the SO(3) part of SE(3) by normalizing a quaternion
def reorthogonalize_SE3(T):
    # ensure the rotational matrix is orthogonal
    q = transformations.quaternion_from_matrix(T)
    n = np.sqrt(q[0] ** 2 + q[1] ** 2 + q[2] ** 2 + q[3] ** 2)
    q = q / n
    T_new = transformations.quaternion_matrix(q)
    T_new[0:3, 3] = T[0:3, 3]
    return T_new

import numpy as np

from fit_tools import gaussianElimination


def polynomialFit(x, y, degree):
    n = degree + 1
    A = [[0 for _ in range(n)] for _ in range(n)]
    for i in range(len(A)):
        max_times = degree + i
        for j in range(len(A[i])):
            cur_times = max_times - j
            A[i][j] = sum([xk ** cur_times for xk in x])
    b = [0 for _ in range(n)]
    for i in range(len(b)):
        b[i] = sum([y[idx] * (xk ** i) for idx, xk in enumerate(x)])
    coeffs = gaussianElimination(A, b)
    return coeffs


def exponential(x, a, b):
    return a * np.exp(b * x)


def logarithmic(x, a, b):
    return a * np.log(b * x)


def sine(x, a, b, c):
    return a * np.sin(b * x + c)

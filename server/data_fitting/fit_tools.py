import copy


def gaussianElimination(A, b):
    n = len(b)
    M = copy.deepcopy(A)

    for i in range(n):
        maxEl = abs(M[i][i])
        maxRow = i
        for k in range(i + 1, n):
            if abs(M[k][i]) > maxEl:
                maxEl = abs(M[k][i])
                maxRow = k
        for k in range(i, n):
            M[maxRow][k], M[i][k] = M[i][k], M[maxRow][k]
        b[maxRow], b[i] = b[i], b[maxRow]

        for k in range(i + 1, n):
            c = -M[k][i] / M[i][i]
            for j in range(i, n):
                if i == j:
                    M[k][j] = 0
                else:
                    M[k][j] += c * M[i][j]
            b[k] += c * b[i]
    x = [0 for _ in range(n)]
    for i in range(n - 1, -1, -1):
        x[i] = b[i] / M[i][i]
        for k in range(i - 1, -1, -1):
            b[k] -= M[k][i] * x[i]

    return x


def get_poly_fun(coeffs):
    degree = len(coeffs) - 1
    fun_str = 'Y = '
    first = True
    for c in coeffs:
        cr = round(c, 4)
        neg = False
        if c < 0:
            neg = True
        if not first and not neg:
            cs = f' + {cr}'
        elif not first and neg:
            cs = f' - {abs(cr)}'
        elif first and neg:
            cs = f'- {abs(cr)}'
        else:
            cs = f'{cr}'
        fun_str = fun_str + cs + f'X^{degree}'
        degree -= 1
        first = False
    return fun_str


def get_fit_funcs(coeffs, fit_type):
    if fit_type == "Polynomial":
        return get_poly_fun(coeffs)
    elif fit_type == "Exponential":
        return f'y = {round(coeffs[0], 4)}e^({round(coeffs[1], 4)}x)'
    elif fit_type == "Logarithmic":
        return f'y = {round(coeffs[0], 4)}log({round(coeffs[1], 4)}x)'
    elif fit_type == "Sine":
        if coeffs[2] < 0:
            return f'y = {round(coeffs[0], 4)}sin({round(coeffs[1], 4)}x - {abs(round(coeffs[2], 4))})'
        else:
            return f'y = {round(coeffs[0], 4)}sin({round(coeffs[1], 4)}x + {round(coeffs[2], 4)})'
    return ''

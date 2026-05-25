"""Born 与 Mouhat–Coudert 弹性稳定性判据（金属常见晶系）。"""

from __future__ import annotations

from typing import Any


def _f(name: str, cij: dict[str, float | None]) -> float | None:
    v = cij.get(name)
    if v is None:
        return None
    return float(v)


def check_stability(crystal_system: str, cij: dict[str, float | None]) -> dict[str, Any]:
    """
    crystal_system: cubic | hexagonal | auto
    cij keys: C11, C12, C13, C33, C44 (GPa)
    """
    system = (crystal_system or 'auto').strip().lower()
    if system in ('fcc', 'bcc', 'cubic'):
        system = 'cubic'
    elif system in ('hcp', 'hexagonal', 'hex'):
        system = 'hexagonal'
    elif system == 'auto':
        if _f('C33', cij) is not None or _f('C13', cij) is not None:
            system = 'hexagonal'
        else:
            system = 'cubic'

    checks: list[dict[str, Any]] = []
    messages: list[str] = []

    if system == 'cubic':
        c11, c12, c44 = _f('C11', cij), _f('C12', cij), _f('C44', cij)
        if c11 is None or c12 is None or c44 is None:
            return {
                'passed': False,
                'crystal_system': system,
                'born_passed': False,
                'mouhat_passed': False,
                'checks': checks,
                'messages': ['立方晶系需要 C11、C12、C44'],
            }
        t1 = c11 - c12
        t2 = c11 + 2 * c12
        t3 = c44
        checks.extend(
            [
                {'id': 'C11-C12', 'expr': 'C11 − C12 > 0', 'value': round(t1, 4), 'passed': t1 > 0},
                {'id': 'C11+2C12', 'expr': 'C11 + 2C12 > 0', 'value': round(t2, 4), 'passed': t2 > 0},
                {'id': 'C44', 'expr': 'C44 > 0', 'value': round(t3, 4), 'passed': t3 > 0},
            ]
        )
        for c in checks:
            if not c['passed']:
                messages.append(f"Born/Mouhat 不满足：{c['expr']}（当前 {c['value']} GPa）")
    else:
        c11, c12, c13, c33, c44 = _f('C11', cij), _f('C12', cij), _f('C13', cij), _f('C33', cij), _f('C44', cij)
        if any(v is None for v in (c11, c12, c13, c33, c44)):
            return {
                'passed': False,
                'crystal_system': system,
                'born_passed': False,
                'mouhat_passed': False,
                'checks': checks,
                'messages': ['六方晶系需要 C11、C12、C13、C33、C44'],
            }
        assert c11 is not None and c12 is not None and c13 is not None and c33 is not None and c44 is not None
        t1 = c44
        t2 = c11 - abs(c12)
        t3 = (c11 + c12) * c33 - 2 * c13 * c13
        t4 = c33
        checks.extend(
            [
                {'id': 'C44', 'expr': 'C44 > 0', 'value': round(t1, 4), 'passed': t1 > 0},
                {'id': 'C11-|C12|', 'expr': 'C11 > |C12|', 'value': round(t2, 4), 'passed': t2 > 0},
                {
                    'id': 'hex-stability',
                    'expr': '(C11+C12)C33 > 2C13²',
                    'value': round(t3, 4),
                    'passed': t3 > 0,
                },
                {'id': 'C33', 'expr': 'C33 > 0', 'value': round(t4, 4), 'passed': t4 > 0},
            ]
        )
        for c in checks:
            if not c['passed']:
                messages.append(f"Born/Mouhat 不满足：{c['expr']}（当前 {c['value']} GPa 或 GPa³）")

    passed = all(c['passed'] for c in checks)
    return {
        'passed': passed,
        'crystal_system': system,
        'born_passed': passed,
        'mouhat_passed': passed,
        'checks': checks,
        'messages': messages if not passed else ['通过 Born/Mouhat 稳定性检验'],
    }

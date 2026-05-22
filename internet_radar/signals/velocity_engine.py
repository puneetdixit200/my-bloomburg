from __future__ import annotations


def velocity_score(current: float, previous: float = 0.0) -> int:
    if current <= 0:
        return 0
    if previous <= 0:
        return min(int(current), 100)
    return min(int(((current - previous) / previous) * 100), 100)

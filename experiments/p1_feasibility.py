"""Pure, external read-only first-feasible certificate; never feeds allocator control."""
from __future__ import annotations

from dataclasses import dataclass, field
import math

from democracy_mrta.diagnostics import Diagnostic, ProtocolError

OWNER = "experiments.p1_feasibility"


def valid_unique_assignment(pairs: tuple[tuple[int, int], ...], robots: int) -> bool:
    """Check exact full capacity-one assignment, not agents' consensus proof."""
    return (len(pairs) == robots
            and len({r for r, _ in pairs}) == robots
            and len({t for _, t in pairs}) == robots
            and all(type(r) is int and type(t) is int
                    and 0 <= r < robots and 0 <= t < robots
                    for r, t in pairs))


@dataclass
class FirstFeasibleObserver:
    """Evidence-only timestamps from immutable completed native phase snapshots."""
    robots: int
    first_feasible_ms: float | None = None
    first_pairs: tuple[tuple[int, int], ...] = ()
    last_pairs: tuple[tuple[int, int], ...] = ()
    last_ms: float = -1.0
    observed_phases: int = 0

    def observe(self, elapsed_ms: float, pairs: tuple[tuple[int, int], ...]) -> None:
        if (type(elapsed_ms) not in (int, float)
                or not math.isfinite(elapsed_ms) or elapsed_ms < 0
                or elapsed_ms + 1e-9 < self.last_ms):
            raise ProtocolError(Diagnostic(
                OWNER, "FirstFeasibleObserver.observe", "time", "P1_NONCAUSAL_OBSERVER_TIMESTAMP",
                expected=f"finite monotone >= {self.last_ms}", actual=elapsed_ms))
        if (not isinstance(pairs, tuple)
                or any(not isinstance(p, tuple) or len(p) != 2 for p in pairs)):
            raise ProtocolError(Diagnostic(
                OWNER, "FirstFeasibleObserver.observe", "data", "P1_INVALID_NATIVE_SNAPSHOT",
                expected="immutable tuple of robot/task integer pairs", actual=repr(pairs)[:150]))
        self.last_ms = float(elapsed_ms)
        self.last_pairs = tuple(pairs)
        self.observed_phases += 1
        if self.first_feasible_ms is None and valid_unique_assignment(pairs, self.robots):
            self.first_feasible_ms = float(elapsed_ms)
            self.first_pairs = tuple(pairs)


def assess_euclidean_assignment(cost_matrix: tuple[tuple[float, ...], ...],
                                pairs: tuple[tuple[int, int], ...],
                                oracle_cost: float) -> dict:
    """Common global *assessment* of already-emitted pairs, never a proposal."""
    n = len(cost_matrix)
    feasible = valid_unique_assignment(pairs, n)
    if not feasible:
        return {"feasible": 0, "sum_distance_m": "", "makespan_s": "",
                "hungarian_gap": "", "hungarian_ratio": ""}
    total = sum(cost_matrix[r][t] for r, t in pairs)
    makespan = max(cost_matrix[r][t] for r, t in pairs)
    if not math.isfinite(oracle_cost) or oracle_cost <= 0:
        raise ProtocolError(Diagnostic(
            OWNER, "assess_euclidean_assignment", "dependency", "P1_ORACLE_COST_INVALID",
            expected="finite >0 Hungarian total for seeded N>=25 scene", actual=oracle_cost))
    if total < oracle_cost - 1e-7:
        raise ProtocolError(Diagnostic(
            OWNER, "assess_euclidean_assignment", "contract", "P1_BELOW_HUNGARIAN_OPTIMUM",
            expected=f"cost >= {oracle_cost}", actual=total))
    return {"feasible": 1, "sum_distance_m": total, "makespan_s": makespan,
            "hungarian_gap": total - oracle_cost, "hungarian_ratio": total / oracle_cost}

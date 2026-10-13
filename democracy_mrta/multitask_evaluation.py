"""Read-only external observer of actual local routes; never repairs assignments."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from .multitask_scenario import MultiTaskScene, route_metrics
from .diagnostics import Diagnostic, ProtocolError


@dataclass(frozen=True)
class RouteAudit:
    covered_tasks: int
    duplicate_tasks: int
    missing_tasks: int
    capacity_violations: int
    total_distance_m: float
    makespan_s: float
    discounted_reward: float
    feasible: bool


def audit_routes(scene: MultiTaskScene,
                 routes: tuple[tuple[int, ...], ...]) -> RouteAudit:
    if len(routes) != scene.robots:
        raise ProtocolError(Diagnostic("multitask_evaluation", "audit_routes",
                                       "data", "E9M_OBSERVER_ROBOT_COUNT_MISMATCH",
                                       expected=scene.robots, actual=len(routes)))
    counts = Counter(task for route in routes for task in route)
    bad_ids = sum(n for task, n in counts.items() if task < 0 or task >= scene.tasks)
    duplicates = sum(n - 1 for n in counts.values() if n > 1) + bad_ids
    covered = sum(task in counts for task in range(scene.tasks))
    violations = sum(max(0, len(route) - scene.capacity) for route in routes)
    distances, scores = zip(*(route_metrics(scene, i, route)
                              for i, route in enumerate(routes)))
    return RouteAudit(
        covered_tasks=covered, duplicate_tasks=duplicates,
        missing_tasks=scene.tasks - covered, capacity_violations=violations,
        total_distance_m=sum(distances), makespan_s=max(distances),
        discounted_reward=sum(scores),
        feasible=(covered == scene.tasks and duplicates == 0 and violations == 0),
    )


@dataclass(frozen=True)
class MethodRun:
    method: str
    routes: tuple[tuple[int, ...], ...]
    rounds: int
    observer_agreement: bool
    local_certificates: int
    guard_censored: bool
    failure_code: str
    elapsed_ms: float
    ledger: dict[str, dict[str, int]]

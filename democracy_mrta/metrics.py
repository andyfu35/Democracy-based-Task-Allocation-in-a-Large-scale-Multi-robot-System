from __future__ import annotations

from dataclasses import dataclass

from scipy.optimize import linear_sum_assignment

from .protocol import AllocationResult


@dataclass(frozen=True)
class E0Metrics:
    protocol_cost: float
    oracle_cost: float
    optimality_gap_percent: float
    assignment_success_rate: float


def hungarian_oracle_cost(cost_matrix: tuple[tuple[float, ...], ...]) -> float:
    row_indices, column_indices = linear_sum_assignment(cost_matrix)
    return float(
        sum(cost_matrix[int(row_id)][int(task_id)] for row_id, task_id in zip(row_indices, column_indices))
    )


def optimality_gap_percent(protocol_cost: float, oracle_cost: float) -> float:
    if oracle_cost < 0:
        raise ValueError("oracle_cost must be non-negative")
    if oracle_cost == 0:
        return 0.0 if protocol_cost == 0 else float("inf")
    return (protocol_cost - oracle_cost) / oracle_cost * 100.0


def evaluate_e0(
    *,
    cost_matrix: tuple[tuple[float, ...], ...],
    allocation: AllocationResult,
) -> E0Metrics:
    oracle_cost = hungarian_oracle_cost(cost_matrix)
    num_tasks = len(cost_matrix[0])
    success_rate = allocation.assigned_tasks / num_tasks
    return E0Metrics(
        protocol_cost=allocation.total_cost,
        oracle_cost=oracle_cost,
        optimality_gap_percent=optimality_gap_percent(allocation.total_cost, oracle_cost),
        assignment_success_rate=success_rate,
    )

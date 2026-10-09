from __future__ import annotations

from dataclasses import dataclass

from .diagnostics import Diagnostic, ProtocolError
from .optimizer import AssignmentSolution, solve_hungarian_assignment
from .protocol import AllocationResult


@dataclass(frozen=True)
class E0Metrics:
    protocol_cost: float
    oracle_cost: float
    optimality_gap_percent: float
    assignment_success_rate: float


def optimality_gap_percent(protocol_cost: float, oracle_cost: float) -> float:
    if oracle_cost < 0:
        raise ValueError("oracle_cost must be non-negative")
    if oracle_cost == 0:
        return 0.0 if protocol_cost == 0 else float("inf")
    return (protocol_cost - oracle_cost) / oracle_cost * 100.0


def require_zero_loss_optimality(
    *,
    protocol_cost: float,
    oracle_cost: float,
    tolerance: float = 1e-12,
) -> None:
    difference = abs(protocol_cost - oracle_cost)
    if difference > tolerance:
        raise ProtocolError(
            Diagnostic(
                owner="metrics",
                function="require_zero_loss_optimality",
                category="contract",
                code="ZERO_LOSS_OPTIMALITY_MISMATCH",
                expected=oracle_cost,
                actual=protocol_cost,
                details=f"absolute_difference={difference}, tolerance={tolerance}",
            )
        )


def evaluate_e0(
    *,
    cost_matrix: tuple[tuple[float, ...], ...],
    allocation: AllocationResult,
) -> E0Metrics:
    oracle = solve_hungarian_assignment(cost_matrix)
    require_zero_loss_optimality(
        protocol_cost=allocation.total_cost,
        oracle_cost=oracle.total_cost,
    )

    num_tasks = len(cost_matrix[0])
    success_rate = allocation.assigned_tasks / num_tasks
    return E0Metrics(
        protocol_cost=allocation.total_cost,
        oracle_cost=oracle.total_cost,
        optimality_gap_percent=optimality_gap_percent(
            allocation.total_cost,
            oracle.total_cost,
        ),
        assignment_success_rate=success_rate,
    )



@dataclass(frozen=True)
class AssignmentCorrectnessMetrics:
    total_tasks: int
    committed_tasks: int
    correct_committed_tasks: int
    incorrect_committed_tasks: int
    correct_executor_rate: float
    correctness_among_committed: float


def evaluate_assignment_correctness(
    *,
    assigned_pairs: tuple[tuple[int, int], ...],
    oracle_assignment: AssignmentSolution,
    total_tasks: int,
) -> AssignmentCorrectnessMetrics:
    if total_tasks <= 0:
        raise ProtocolError(
            Diagnostic(
                owner="metrics",
                function="evaluate_assignment_correctness",
                category="data",
                code="INVALID_TOTAL_TASKS",
                expected="positive total_tasks",
                actual=total_tasks,
            )
        )

    oracle_by_task = {
        task_id: robot_id
        for robot_id, task_id in oracle_assignment.assigned_pairs
    }
    if len(oracle_by_task) != total_tasks:
        raise ProtocolError(
            Diagnostic(
                owner="metrics",
                function="evaluate_assignment_correctness",
                category="contract",
                code="ORACLE_ASSIGNMENT_INCOMPLETE",
                expected=total_tasks,
                actual=len(oracle_by_task),
            )
        )

    assigned_task_ids = [task_id for _robot_id, task_id in assigned_pairs]
    if len(assigned_task_ids) != len(set(assigned_task_ids)):
        raise ProtocolError(
            Diagnostic(
                owner="metrics",
                function="evaluate_assignment_correctness",
                category="contract",
                code="DUPLICATE_TASK_IN_EVALUATED_ASSIGNMENT",
                expected="unique committed task ids",
                actual=tuple(assigned_pairs),
            )
        )

    unknown_tasks = tuple(
        task_id
        for task_id in assigned_task_ids
        if task_id not in oracle_by_task
    )
    if unknown_tasks:
        raise ProtocolError(
            Diagnostic(
                owner="metrics",
                function="evaluate_assignment_correctness",
                category="data",
                code="COMMITTED_TASK_OUT_OF_ORACLE_RANGE",
                expected=tuple(sorted(oracle_by_task)),
                actual=unknown_tasks,
            )
        )

    correct = sum(
        int(oracle_by_task[task_id] == robot_id)
        for robot_id, task_id in assigned_pairs
    )
    committed = len(assigned_pairs)
    incorrect = committed - correct
    conditional = (
        correct / committed
        if committed > 0
        else float("nan")
    )

    return AssignmentCorrectnessMetrics(
        total_tasks=total_tasks,
        committed_tasks=committed,
        correct_committed_tasks=correct,
        incorrect_committed_tasks=incorrect,
        correct_executor_rate=correct / total_tasks,
        correctness_among_committed=conditional,
    )

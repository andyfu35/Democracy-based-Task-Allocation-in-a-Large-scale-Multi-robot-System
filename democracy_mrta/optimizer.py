from __future__ import annotations

from dataclasses import dataclass
import math

from scipy.optimize import linear_sum_assignment

from .diagnostics import Diagnostic, ProtocolError


@dataclass(frozen=True)
class AssignmentSolution:
    assigned_pairs: tuple[tuple[int, int], ...]
    total_cost: float

    @property
    def assigned_tasks(self) -> int:
        return len(self.assigned_pairs)


def validate_cost_matrix(
    cost_matrix: tuple[tuple[float, ...], ...],
) -> tuple[int, int]:
    if not cost_matrix:
        raise ProtocolError(
            Diagnostic(
                owner="optimizer",
                function="validate_cost_matrix",
                category="data",
                code="EMPTY_COST_MATRIX",
                expected="at least one robot row",
                actual=0,
            )
        )

    num_robots = len(cost_matrix)
    num_tasks = len(cost_matrix[0])
    if num_tasks <= 0:
        raise ProtocolError(
            Diagnostic(
                owner="optimizer",
                function="validate_cost_matrix",
                category="data",
                code="EMPTY_TASK_SET",
                expected="at least one task column",
                actual=0,
            )
        )

    if any(len(row) != num_tasks for row in cost_matrix):
        raise ProtocolError(
            Diagnostic(
                owner="optimizer",
                function="validate_cost_matrix",
                category="data",
                code="NON_RECTANGULAR_COST_MATRIX",
                expected=num_tasks,
                actual=tuple(len(row) for row in cost_matrix),
            )
        )

    if num_tasks > num_robots:
        raise ProtocolError(
            Diagnostic(
                owner="optimizer",
                function="validate_cost_matrix",
                category="contract",
                code="TASKS_EXCEED_ROBOTS",
                expected="num_tasks <= num_robots",
                actual=f"{num_tasks}>{num_robots}",
            )
        )

    for robot_id, row in enumerate(cost_matrix):
        for task_id, value in enumerate(row):
            if not math.isfinite(value):
                raise ProtocolError(
                    Diagnostic(
                        owner="optimizer",
                        function="validate_cost_matrix",
                        category="data",
                        code="NONFINITE_COST",
                        expected="finite cost",
                        actual=value,
                        details=f"robot_id={robot_id}, task_id={task_id}",
                    )
                )

    return num_robots, num_tasks


def solve_hungarian_assignment(
    cost_matrix: tuple[tuple[float, ...], ...],
) -> AssignmentSolution:
    _, num_tasks = validate_cost_matrix(cost_matrix)

    row_indices, column_indices = linear_sum_assignment(cost_matrix)
    assigned_pairs = tuple(
        sorted(
            (
                (int(robot_id), int(task_id))
                for robot_id, task_id in zip(row_indices, column_indices)
            ),
            key=lambda pair: (pair[1], pair[0]),
        )
    )

    if len(assigned_pairs) != num_tasks:
        raise ProtocolError(
            Diagnostic(
                owner="optimizer",
                function="solve_hungarian_assignment",
                category="contract",
                code="INCOMPLETE_HUNGARIAN_ASSIGNMENT",
                expected=num_tasks,
                actual=len(assigned_pairs),
            )
        )

    total_cost = float(
        sum(cost_matrix[robot_id][task_id] for robot_id, task_id in assigned_pairs)
    )
    return AssignmentSolution(
        assigned_pairs=assigned_pairs,
        total_cost=total_cost,
    )


def solve_visible_hungarian_assignment(
    cost_matrix: tuple[tuple[float, ...], ...],
    visible_robot_ids: frozenset[int] | set[int] | tuple[int, ...],
) -> AssignmentSolution:
    num_robots, num_tasks = validate_cost_matrix(cost_matrix)
    visible = tuple(sorted(set(int(robot_id) for robot_id in visible_robot_ids)))

    if not visible:
        raise ProtocolError(
            Diagnostic(
                owner="optimizer",
                function="solve_visible_hungarian_assignment",
                category="state",
                code="NO_VISIBLE_ROBOTS",
                expected="at least one visible robot row",
                actual=0,
            )
        )

    invalid = tuple(robot_id for robot_id in visible if robot_id < 0 or robot_id >= num_robots)
    if invalid:
        raise ProtocolError(
            Diagnostic(
                owner="optimizer",
                function="solve_visible_hungarian_assignment",
                category="data",
                code="VISIBLE_ROBOT_ID_OUT_OF_RANGE",
                expected=f"0 <= robot_id < {num_robots}",
                actual=invalid,
            )
        )

    local_matrix = tuple(cost_matrix[robot_id] for robot_id in visible)
    row_indices, column_indices = linear_sum_assignment(local_matrix)

    assigned_pairs = tuple(
        sorted(
            (
                (visible[int(local_row_id)], int(task_id))
                for local_row_id, task_id in zip(row_indices, column_indices)
            ),
            key=lambda pair: (pair[1], pair[0]),
        )
    )

    expected_assignments = min(len(visible), num_tasks)
    if len(assigned_pairs) != expected_assignments:
        raise ProtocolError(
            Diagnostic(
                owner="optimizer",
                function="solve_visible_hungarian_assignment",
                category="contract",
                code="PARTIAL_HUNGARIAN_CARDINALITY_MISMATCH",
                expected=expected_assignments,
                actual=len(assigned_pairs),
                details=f"visible_robot_count={len(visible)}, num_tasks={num_tasks}",
            )
        )

    total_cost = float(
        sum(cost_matrix[robot_id][task_id] for robot_id, task_id in assigned_pairs)
    )
    return AssignmentSolution(
        assigned_pairs=assigned_pairs,
        total_cost=total_cost,
    )

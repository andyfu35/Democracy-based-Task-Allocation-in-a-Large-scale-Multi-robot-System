from __future__ import annotations

import unittest

from democracy_mrta.optimizer import (
    solve_hungarian_assignment,
    solve_visible_hungarian_assignment,
)


class OptimizerTests(unittest.TestCase):
    def test_hungarian_finds_global_assignment_not_sequential_greedy(self) -> None:
        cost_matrix = (
            (1.0, 1.0),
            (2.0, 100.0),
        )

        solution = solve_hungarian_assignment(cost_matrix)

        self.assertEqual(solution.assigned_pairs, ((1, 0), (0, 1)))
        self.assertEqual(solution.total_cost, 3.0)

    def test_rectangular_more_robots_than_tasks_is_supported(self) -> None:
        cost_matrix = (
            (5.0, 1.0),
            (2.0, 8.0),
            (3.0, 4.0),
        )

        solution = solve_hungarian_assignment(cost_matrix)

        self.assertEqual(solution.assigned_tasks, 2)
        self.assertEqual(len({robot_id for robot_id, _ in solution.assigned_pairs}), 2)
        self.assertEqual(len({task_id for _, task_id in solution.assigned_pairs}), 2)

    def test_visible_hungarian_never_uses_hidden_robot_rows(self) -> None:
        cost_matrix = (
            (1.0, 100.0, 100.0),
            (100.0, 1.0, 100.0),
            (100.0, 100.0, 1.0),
        )

        solution = solve_visible_hungarian_assignment(
            cost_matrix,
            frozenset({0, 2}),
        )

        self.assertEqual(solution.assigned_tasks, 2)
        self.assertEqual({robot_id for robot_id, _ in solution.assigned_pairs}, {0, 2})
        self.assertNotIn(1, {robot_id for robot_id, _ in solution.assigned_pairs})

    def test_visible_hungarian_can_return_partial_assignment(self) -> None:
        cost_matrix = (
            (1.0, 4.0, 7.0),
            (2.0, 5.0, 8.0),
            (3.0, 6.0, 9.0),
        )

        solution = solve_visible_hungarian_assignment(
            cost_matrix,
            frozenset({0}),
        )

        self.assertEqual(solution.assigned_tasks, 1)


if __name__ == "__main__":
    unittest.main()

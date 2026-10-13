"""P2-C deterministic 100-seed actual-owner Global Greedy planning oracle tests.

No radio or native E9 baseline is asserted by this offline owner-level test.
"""
from __future__ import annotations

import math
import unittest

from democracy_mrta.optimizer import (
    solve_visible_batched_greedy_assignment,
    solve_hungarian_assignment,
    solve_sequential_greedy_reference,
)
from democracy_mrta.scenario import generate_e0_scenario
from democracy_mrta.protocol import validate_one_to_one_commits


def independent_global_cost_reference(cost_matrix, visible_robots):
    """Independent exhaustive edge ranking, NOT the production owner implementation."""
    edges = sorted(
        (float(cost_matrix[r][t]), t, r)
        for r in visible_robots
        for t in range(len(cost_matrix[0]))
    )
    picked = []
    used_robots = set()
    used_tasks = set()
    for _cost, task_id, robot_id in edges:
        if robot_id in used_robots or task_id in used_tasks:
            continue
        picked.append((robot_id, task_id))
        used_robots.add(robot_id)
        used_tasks.add(task_id)
        if len(picked) == min(len(visible_robots), len(cost_matrix[0])):
            break
    return tuple(sorted(picked, key=lambda p: (p[1], p[0])))


class P2CGlobalGreedyTests(unittest.TestCase):
    def test_zero_loss_100_seeds_exact_global_greedy_cost(self):
        ratios = []
        for seed in range(100):
            scene = generate_e0_scenario(seed, 100, 100)
            visible = frozenset(range(100))
            result = solve_visible_batched_greedy_assignment(
                scene.cost_matrix, visible,
            )
            independent = independent_global_cost_reference(
                scene.cost_matrix, visible,
            )
            self.assertEqual(result.assigned_pairs, independent, f"seed={seed}")
            self.assertEqual(result.assigned_tasks, 100)
            validate_one_to_one_commits(result.assigned_pairs)
            independent_cost = sum(scene.cost_matrix[r][t] for r, t in independent)
            self.assertAlmostEqual(result.total_cost, independent_cost, places=9)
            hungarian = solve_hungarian_assignment(scene.cost_matrix)
            ratios.append(result.total_cost / hungarian.total_cost)
        self.assertAlmostEqual(
            sum(ratios) / len(ratios), 1.2352608182858986, places=9,
        )

    def test_global_cost_does_not_prefer_earlier_task_id(self):
        cost = ((2., 1.), (3., 100.))
        greedy = solve_visible_batched_greedy_assignment(cost, {0, 1})
        self.assertEqual(greedy.assigned_pairs, ((1, 0), (0, 1)))
        self.assertEqual(greedy.total_cost, 4.)
        self.assertNotEqual(greedy.assigned_pairs,
                            solve_sequential_greedy_reference(cost).assigned_pairs)

    def test_partial_cost_view_can_vote_for_late_tasks(self):
        matrix = (
            (100., 100., 100., 1.),
            (100., 100., 1., 100.),
            (1., 100., 100., 100.),
            (100., 1., 100., 100.),
        )
        observed = solve_visible_batched_greedy_assignment(matrix, {0, 1})
        self.assertEqual(observed.assigned_pairs, ((1, 2), (0, 3)))
        self.assertEqual(observed.assigned_tasks, 2)
        validate_one_to_one_commits(observed.assigned_pairs)


if __name__ == "__main__":
    unittest.main()

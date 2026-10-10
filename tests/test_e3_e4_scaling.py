from __future__ import annotations

import csv
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from democracy_mrta.diagnostics import ProtocolError
from experiments.run_e3_e4_scaling import (
    DEFAULT_RATIOS,
    DEFAULT_ROBOTS,
    MAX_ROBOTS,
    build_scaling_cells,
    read_completed_scaling_cell,
    run_scaling_benchmark,
    validate_scaling_axes,
)


class FixedLatency:
    def sample_ms(self, key: str) -> float:
        return 10.0


def make_scenario(seed: int, robots: int, tasks: int) -> SimpleNamespace:
    # A small deterministic matrix with a unique cheapest local candidate.
    # Physical robot IDs remain stable as assigned executors retire.
    return SimpleNamespace(cost_matrix=tuple(
        tuple(float(abs(robot - task) + 1) for task in range(tasks))
        for robot in range(robots)
    ))


class ScalingCellDesignTests(unittest.TestCase):
    def test_default_grid_has_30_distinct_cells_with_100_robot_cap(self) -> None:
        validate_scaling_axes(
            robot_levels=DEFAULT_ROBOTS,
            load_ratios=DEFAULT_RATIOS,
            losses=(0.0, 0.30),
            seeds=100, attempts_per_task=2,
        )
        cells = build_scaling_cells(
            robot_levels=DEFAULT_ROBOTS, load_ratios=DEFAULT_RATIOS,
        )
        self.assertEqual(len(cells), 30)
        self.assertEqual(
            [(c.robots, c.tasks) for c in cells if c.robots == 10],
            [(10, 1), (10, 3), (10, 5), (10, 8), (10, 10)],
        )
        self.assertEqual(
            [(c.robots, c.tasks) for c in cells if c.robots == 100],
            [(100, 10), (100, 25), (100, 50), (100, 75), (100, 100)],
        )
        self.assertEqual(len({c.identifier for c in cells}), 30)
        self.assertTrue(all(1 <= c.tasks <= c.robots <= MAX_ROBOTS for c in cells))
        self.assertEqual(cells[-1].actual_load_ratio, 1.0)

    def test_robot_over_100_fails_before_simulation(self) -> None:
        with self.assertRaises(ProtocolError) as context:
            validate_scaling_axes(
                robot_levels=(10, 101), load_ratios=(0.5,),
                losses=(0.30,), seeds=100, attempts_per_task=2,
            )
        self.assertEqual(
            context.exception.diagnostic.code,
            "INVALID_SCALING_ROBOT_LEVELS",
        )

    def test_ratio_above_one_fails_before_simulation(self) -> None:
        with self.assertRaises(ProtocolError) as context:
            validate_scaling_axes(
                robot_levels=(100,), load_ratios=(0.50, 1.01),
                losses=(0.30,), seeds=100, attempts_per_task=2,
            )
        self.assertEqual(
            context.exception.diagnostic.code,
            "INVALID_SCALING_LOAD_RATIOS",
        )

    def test_rounded_duplicate_tasks_must_not_run_twice(self) -> None:
        with self.assertRaises(ProtocolError) as context:
            build_scaling_cells(
                robot_levels=(10,), load_ratios=(0.10, 0.11),
            )
        self.assertEqual(
            context.exception.diagnostic.code,
            "SCALING_DUPLICATE_TASK_CELL",
        )

    def test_unsorted_and_duplicate_axes_rejected(self) -> None:
        for robots, ratios, losses, expected in (
            ((20, 10), (0.50,), (0.30,), "INVALID_SCALING_ROBOT_LEVELS"),
            ((10, 10), (0.50,), (0.30,), "INVALID_SCALING_ROBOT_LEVELS"),
            ((10,), (1.0, 0.5), (0.30,), "INVALID_SCALING_LOAD_RATIOS"),
            ((10,), (0.50,), (0.30, 0.0), "INVALID_SCALING_LOSS_LEVELS"),
            ((10,), (0.50,), (0.30, 0.30), "INVALID_SCALING_LOSS_LEVELS"),
        ):
            with self.subTest(robots=robots, ratios=ratios, losses=losses):
                with self.assertRaises(ProtocolError) as context:
                    validate_scaling_axes(
                        robot_levels=robots, load_ratios=ratios,
                        losses=losses, seeds=2, attempts_per_task=2,
                    )
                self.assertEqual(context.exception.diagnostic.code, expected)

    def test_negative_seeds_and_zero_round_multiplier_fail(self) -> None:
        for seeds, attempts, expected in (
            (0, 2, "INVALID_SCALING_SEEDS"),
            (2, 0, "INVALID_SCALING_ATTEMPT_MULTIPLIER"),
        ):
            with self.subTest(seeds=seeds, attempts=attempts):
                with self.assertRaises(ProtocolError) as context:
                    validate_scaling_axes(
                        robot_levels=(10,), load_ratios=(1.0,),
                        losses=(0.30,), seeds=seeds,
                        attempts_per_task=attempts,
                    )
                self.assertEqual(context.exception.diagnostic.code, expected)


class ScalingRunnerEvidenceTests(unittest.TestCase):
    def run_fixture(
        self, root: Path, *, resume: bool = False,
        seeds: int = 2,
    ) -> list[dict[str, object]]:
        with (
            patch(
                "experiments.run_e3_e4_scaling.read_retirement_revision",
                return_value="test-scale-sha",
            ),
            patch(
                "experiments.run_e2_retirement.read_retirement_revision",
                return_value="test-scale-sha",
            ),
            patch(
                "experiments.run_e2_retirement.ensure_rady_dataset",
                return_value=Path(root) / "unused.json",
            ),
            patch(
                "experiments.run_e2_retirement.load_rady_latency_profile",
                return_value=object(),
            ),
            patch(
                "experiments.run_e2_retirement.summarize_latency_profile",
                return_value={"max_ms": 10.0},
            ),
            patch(
                "experiments.run_e2_retirement.EmpiricalLatencySampler",
                side_effect=lambda *args, **kwargs: FixedLatency(),
            ),
            patch(
                "experiments.run_e2_retirement.generate_e0_scenario",
                side_effect=make_scenario,
            ),
        ):
            return run_scaling_benchmark(
                robot_levels=(2, 4),
                load_ratios=(0.5, 1.0),
                losses=(0.0, 0.30),
                seeds=seeds, attempts_per_task=2,
                dataset=Path(root) / "unused.json",
                output_root=root / "scale",
                allow_download=False,
                resume=resume,
            )

    def test_runner_writes_all_cell_evidence_and_aggregate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            summaries = self.run_fixture(root)
            self.assertEqual(len(summaries), 8)  # 4 sizes x 2 loss levels
            self.assertTrue((root / "scale" / "benchmark_plan.json").is_file())
            self.assertTrue((root / "scale" / "summary.csv").is_file())
            self.assertEqual(
                {(int(r["robots"]), int(r["tasks"])) for r in summaries},
                {(2, 1), (2, 2), (4, 2), (4, 4)},
            )
            self.assertEqual(
                {(float(r["p_cost_loss"]), float(r["p_vote_loss"])) for r in summaries},
                {(0.0, 0.0), (0.30, 0.30)},
            )
            self.assertTrue(all(r["vote_decision_rule"] == "quarter_plurality" for r in summaries))
            self.assertTrue(all(r["git_sha"] == "test-scale-sha" for r in summaries))
            self.assertTrue(all(
                int(r["max_rounds"]) == 2 * int(r["tasks"]) for r in summaries
            ))
            self.assertTrue(all(
                float(r["mean_elapsed_ms_per_requested_task"]) >= 0
                for r in summaries
            ))
            self.assertTrue(all(
                float(r["mean_messages_per_requested_task"]) > 0
                for r in summaries
            ))
            baseline = [row for row in summaries if float(row["p_cost_loss"]) == 0.0]
            self.assertTrue(all(
                float(row["full_assignment_success_rate"]) == 1.0
                for row in baseline
            ))
            cell_root = root / "scale" / "cells" / "R004_T004"
            self.assertTrue((cell_root / "summary.csv").is_file())
            self.assertEqual(len(list((cell_root / "raw").glob("retirement_*.csv"))), 1)
            self.assertEqual(len(list((cell_root / "rounds").glob("retirement_rounds_*.csv"))), 1)
            self.assertEqual(len(list((cell_root / "events").glob("retirement_audit_*.csv.gz"))), 1)
            with (root / "scale" / "summary.csv").open(newline="", encoding="utf-8") as stream:
                self.assertEqual(len(list(csv.DictReader(stream))), 8)

    def test_fresh_result_root_may_contain_its_documentation_readme(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result_root = root / "scale"
            result_root.mkdir()
            (result_root / "README.md").write_text(
                "Scaling experiment evidence ledger", encoding="utf-8"
            )
            summaries = self.run_fixture(root)
            self.assertEqual(len(summaries), 8)
            self.assertTrue((result_root / "benchmark_plan.json").is_file())

    def test_resume_reuses_only_verified_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = self.run_fixture(root)
            with patch(
                "experiments.run_e3_e4_scaling.run_retirement_experiment",
                side_effect=AssertionError("completed cell must not be rerun"),
            ):
                reused = self.run_fixture(root, resume=True)
            self.assertEqual(first, reused)
            with self.assertRaises(ProtocolError) as context:
                self.run_fixture(root, resume=False)
            self.assertEqual(
                context.exception.diagnostic.code,
                "SCALING_OUTPUT_ALREADY_EXISTS",
            )

    def test_changed_seed_count_rejects_resume_even_when_summary_exists(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.run_fixture(root)
            with self.assertRaises(ProtocolError) as context:
                self.run_fixture(root, resume=True, seeds=3)
            self.assertEqual(
                context.exception.diagnostic.code,
                "SCALING_RESUME_PLAN_MISMATCH",
            )

    def test_corrupted_raw_sha_rejects_resume(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.run_fixture(root)
            cell = root / "scale" / "cells" / "R002_T001"
            raw = next((cell / "raw").glob("retirement_*.csv"))
            with raw.open(newline="", encoding="utf-8") as stream:
                rows = list(csv.DictReader(stream))
            rows[0]["git_sha"] = "different-code-revision"
            with raw.open("w", newline="", encoding="utf-8") as stream:
                writer = csv.DictWriter(stream, fieldnames=list(rows[0].keys()))
                writer.writeheader()
                writer.writerows(rows)
            with self.assertRaises(ProtocolError) as context:
                read_completed_scaling_cell(
                    cell_root=cell, cell=build_scaling_cells(
                        robot_levels=(2,), load_ratios=(0.5,)
                    )[0],
                    losses=(0.0, 0.30), seeds=2,
                    attempts_per_task=2, git_sha="test-scale-sha",
                )
            self.assertEqual(
                context.exception.diagnostic.code,
                "SCALING_CELL_PROVENANCE_MISMATCH",
            )


if __name__ == "__main__":
    unittest.main()

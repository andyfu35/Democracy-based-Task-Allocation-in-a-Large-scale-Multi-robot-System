from __future__ import annotations

import csv
import gzip
import json
import math
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from democracy_mrta.diagnostics import ProtocolError
from experiments.run_cbaa_baseline import (
    cbaa_full_batch_cost,
    prepare_cbaa_output,
    run_cbaa_baseline,
    validate_cbaa_benchmark_axes,
)


class ConstantLatency:
    def sample_ms(self, key: str) -> float:
        return 10.0


class CBAABenchmarkEvidenceTests(unittest.TestCase):
    def test_source_mutability_and_historical_directory_collision_rejected(self):
        with self.assertRaises(ProtocolError) as ctx:
            prepare_cbaa_output(Path("results/e2_repeat3_majority_100r50t"))
        self.assertEqual(ctx.exception.diagnostic.owner,
                         "experiments.run_cbaa_baseline")
        self.assertEqual(ctx.exception.diagnostic.function,
                         "prepare_cbaa_output")
        self.assertEqual(ctx.exception.diagnostic.code, "CBAA_OUTPUT_SOURCE_COLLISION")

    def test_invalid_robot_task_and_benchmark_axes_fail_before_execution(self):
        for robots, tasks, seeds, iterations, losses in (
            (2, 3, 2, 5, (0.0,)),
            (101, 50, 2, 5, (0.0,)),
            (2, 1, 0, 5, (0.0,)),
            (2, 1, 2, 0, (0.0,)),
        ):
            with self.subTest(shape=(robots, tasks, seeds, iterations)):
                with self.assertRaises(ProtocolError) as ctx:
                    validate_cbaa_benchmark_axes(
                        robots=robots, tasks=tasks, seeds=seeds,
                        max_iterations=iterations,
                        loss_probabilities=losses,
                    )
                self.assertEqual(ctx.exception.diagnostic.code, "INVALID_CBAA_BENCHMARK_AXES")
        with self.assertRaises(ProtocolError) as ctx:
            validate_cbaa_benchmark_axes(
                robots=2, tasks=1, seeds=2, max_iterations=5,
                loss_probabilities=(0.3, 0.0),
            )
        self.assertEqual(ctx.exception.diagnostic.code, "INVALID_CBAA_LOSS_AXIS")

    def test_full_reference_scenario_runner_persists_only_observer_agreement(self):
        costs = ((1.0, 20.0), (1.1, 100.0))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "cbaa_test"
            output.mkdir()
            (output / "README.md").write_text("This is an evidence directory.\n")
            with (
                patch("experiments.run_cbaa_baseline.ensure_rady_dataset",
                      return_value=root / "dataset.json"),
                patch("experiments.run_cbaa_baseline.load_rady_latency_profile",
                      return_value=object()),
                patch("experiments.run_cbaa_baseline.summarize_latency_profile",
                      return_value={"max_ms": 10.0}),
                patch("experiments.run_cbaa_baseline.EmpiricalLatencySampler",
                      side_effect=lambda *args, **kwargs: ConstantLatency()),
                patch("experiments.run_cbaa_baseline.generate_e0_scenario",
                      side_effect=lambda *args, **kwargs:
                      SimpleNamespace(cost_matrix=costs)),
                patch("experiments.run_cbaa_baseline.read_retirement_revision",
                      return_value="cbaa-contract-test-sha"),
            ):
                summaries = run_cbaa_baseline(
                    robots=2, tasks=2, seeds=2,
                    loss_probabilities=(0.0, 1.0),
                    max_iterations=2,
                    dataset_path=root / "dataset.json",
                    output_root=output,
                    allow_download=False,
                )
            self.assertEqual(len(summaries), 2)
            self.assertEqual([row["full_observer_agreement_rate"] for row in summaries],
                             [1.0, 0.0])
            self.assertEqual(summaries[0]["complete_case_cost_count"], 2)
            self.assertEqual(summaries[1]["complete_case_cost_count"], 0)
            self.assertTrue(math.isnan(summaries[1]["mean_full_batch_cost_complete_only"]))
            self.assertEqual(summaries[1]["mean_duplicate_claim_task_count"], 1)
            self.assertEqual(summaries[0]["observed_packet_loss"], 0.0)
            self.assertEqual(summaries[1]["observed_packet_loss"], 1.0)

            with next((output / "raw").glob("cbaa_*.csv")).open(
                encoding="utf-8", newline=""
            ) as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual(len(rows), 4)
            zero = [r for r in rows if float(r["p_consensus_loss"]) == 0]
            lost = [r for r in rows if float(r["p_consensus_loss"]) == 1]
            self.assertEqual(len(zero), 2)
            self.assertEqual({r["full_observer_agreement"] for r in zero}, {"1"})
            self.assertEqual({r["full_observer_agreement"] for r in lost}, {"0"})
            self.assertTrue(all(math.isnan(float(r["full_batch_cost_complete_only"]))
                                for r in lost))
            self.assertEqual({r["git_sha"] for r in rows}, {"cbaa-contract-test-sha"})
            self.assertEqual({r["method"] for r in rows},
                             {"cbaa_sync_single_assignment"})
            self.assertFalse(any(
                "hungarian" in key.lower()
                for key in rows[0]
            ))
            manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["source_git_sha"], "cbaa-contract-test-sha")
            self.assertEqual(manifest["max_iterations"], 2)
            self.assertIn("NOT a distributed Commit",
                          manifest["adaptations"][3])
            with gzip.open(
                next((output / "events").glob("cbaa_audit_*.csv.gz")),
                "rt", newline="", encoding="utf-8",
            ) as stream:
                events = list(csv.DictReader(stream))
            broadcasts = [r for r in events if r["kind"] == "broadcast"]
            self.assertEqual(len(broadcasts), 8)  # 2 robots * 2 rounds * 2 conditions
            self.assertTrue(all(r["phase"] == "cbaa_consensus" for r in broadcasts))
            physical = [r for r in events if r["kind"] == "delivery"]
            self.assertEqual(len(physical), 8)
            self.assertEqual({r["delivered"] for r in physical}, {"0", "1"})
            states = [r for r in events if r["kind"] == "final_local_state"]
            self.assertEqual(len(states), 4)
            self.assertFalse(any(r["phase"] == "commit" for r in events))
            self.assertTrue((output / "README.md").exists())

            with self.assertRaises(ProtocolError) as ctx:
                prepare_cbaa_output(output)
            self.assertEqual(ctx.exception.diagnostic.code, "CBAA_OUTPUT_ALREADY_EXISTS")

    def test_any_partial_completion_has_nan_full_batch_cost(self):
        costs = ((1.0, 20.0), (1.1, 100.0))
        from democracy_mrta.cbaa import simulate_cbaa
        from democracy_mrta.network import BernoulliLossSampler
        incomplete = simulate_cbaa(
            cost_matrix=costs,
            sampler=ConstantLatency(),
            loss_sampler=BernoulliLossSampler(seed=1),
            loss_probability=1.0,
            phase_timeout_ms=10.0,
            max_iterations=2,
        )
        self.assertTrue(math.isnan(cbaa_full_batch_cost(
            cost_matrix=costs, result=incomplete
        )))


if __name__ == "__main__":
    unittest.main()

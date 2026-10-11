"""E9A observational SEND-byte matching is deterministic, unbiased and immutable."""
from __future__ import annotations

import csv
import hashlib
import json
import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from democracy_mrta.diagnostics import ProtocolError
from experiments.compare_cbaa_budget import (
    compare_cbaa_communication_budget,
    validate_budget_calibration_config,
)


LOSSES = (0.0, 0.30, 0.50)


def save_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def quarter_row(seed: int, loss: float) -> dict[str, object]:
    completed = 2 if loss < 0.50 or seed == 0 else 1
    return {
        "seed": seed, "git_sha": "original-quarter-SHA",
        "robots": 2, "tasks": 2, "max_rounds": 4,
        "method": "democracy_greedy_quarter_plurality_retirement",
        "vote_decision_rule": "quarter_plurality", "vote_repetitions": 1,
        "p_cost_loss": loss, "p_vote_loss": loss,
        "full_assignment_success": int(completed == 2),
        "committed_tasks": completed, "task_commit_rate": completed / 2,
        "greedy_correct_executor_rate": 1.0 if completed == 2 else 0.5,
        "greedy_reference_cost": 100 + seed,
        "payload_bytes": (
            158 + 2 * seed if loss == 0.0
            else (170 + 50 * seed if loss == 0.30 else 300)
        ),
        "logical_message_count": 6 + seed,
        "total_elapsed_ms": 30.0 + loss,
        "safety_failures": 0,
    }


def cbaa_row(seed: int, loss: float, iterations: int) -> dict[str, object]:
    # Intentionally give the LOWER-byte option a better p=0 success rate:
    # any selector that uses CBAA success (cherry-picking) will fail tests.
    full = int(iterations == 1 and loss == 0.0)
    agreed, unconfirmed = (2, 0) if full else (1, 1)
    nmsg = 2 * iterations
    return {
        "seed": seed, "git_sha": f"cbaa-iter-{iterations}-SHA",
        "robots": 2, "tasks": 2,
        "method": "cbaa_sync_single_assignment",
        "score_rule": "1/(1+nonnegative_cost)",
        "communication": "synchronous_complete_graph_broadcast",
        "p_consensus_loss": loss, "max_iterations": iterations,
        "iterations": iterations,
        "full_observer_agreement": full,
        "task_agreement_rate": agreed / 2,
        "observer_agreed_task_count": agreed,
        "observer_unconfirmed_task_count": unconfirmed,
        "local_duplicate_claim_task_count": 0,
        "local_claim_count": 2 if full else 1,
        "greedy_reference_cost": 100 + seed,
        "payload_bytes": nmsg * (16 + 2 * 12),
        "logical_message_count": nmsg,
        "elapsed_ms": 10 * iterations,
        "delivery_attempts": nmsg,
        "delivery_drops": 0 if loss == 0 else 1,
        "late_deliveries": 0,
    }


class BudgetCalibrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.quarter = root / "historical_quarter"
        self.cbaa_one = root / "cbaa_budget1"
        self.cbaa_two = root / "cbaa_budget2"
        self.output = root / "budget_analysis"
        self.qfile = self.quarter / "raw" / "retirement_older.csv"
        self.one_file = self.cbaa_one / "raw" / "cbaa_a.csv"
        self.two_file = self.cbaa_two / "raw" / "cbaa_b.csv"
        save_csv(self.qfile, [quarter_row(seed, p)
                              for seed in range(4) for p in LOSSES])
        save_csv(self.one_file, [cbaa_row(seed, p, 1)
                                for seed in range(3) for p in LOSSES])
        save_csv(self.two_file, [cbaa_row(seed, p, 2)
                                for seed in range(3) for p in LOSSES])

    def run_report(self, *, output=None, roots=None, losses=LOSSES, seeds=3):
        with patch("experiments.compare_cbaa_budget.read_retirement_revision",
                   return_value="analysis-E9A-test-SHA"):
            return compare_cbaa_communication_budget(
                quarter_root=self.quarter,
                cbaa_roots=roots or (self.cbaa_one, self.cbaa_two),
                output_root=output or self.output,
                robots=2, tasks=2, seeds=seeds, max_rounds=4,
                losses=losses, tolerance=0.10,
            )

    def test_choose_config_using_only_p0_bytes_not_success(self):
        q_bytes_before = hashlib.sha256(self.qfile.read_bytes()).hexdigest()
        c_bytes_before = hashlib.sha256(self.one_file.read_bytes()).hexdigest()
        options, curves = self.run_report()
        self.assertEqual(len(options), 2)
        self.assertEqual(len(curves), 6)
        selected = [r for r in options if r["selected_by_zero_loss_bytes_only"] == 1]
        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0]["iterations"], 2)
        self.assertEqual(selected[0]["greedy_zero_loss_mean_sent_bytes"], 160.0)
        self.assertEqual(selected[0]["cbaa_zero_loss_mean_sent_bytes"], 160.0)
        self.assertEqual(selected[0]["within_zero_loss_calibration_tolerance"], 1)
        # On purpose the K=2 source fails all zero-loss task agreements.
        p0_one = next(x for x in curves if x["cbaa_iterations"] == 1 and x["p_loss"] == 0)
        p0_two = next(x for x in curves if x["cbaa_iterations"] == 2 and x["p_loss"] == 0)
        self.assertEqual(p0_one["cbaa_full_observer_agreement_rate"], 1.0)
        self.assertEqual(p0_two["cbaa_full_observer_agreement_rate"], 0.0)
        self.assertEqual(p0_two["selected_by_zero_loss_bytes_only"], 1)
        self.assertEqual(p0_two["mean_bytes_close_within_tolerance"], 1)
        p50 = next(x for x in curves if x["cbaa_iterations"] == 2 and x["p_loss"] == 0.5)
        self.assertEqual(p50["mean_bytes_close_within_tolerance"], 0)
        self.assertEqual(p50["paired_seeds_bytes_close_count"], 0)
        self.assertEqual(p50["greedy_full_assignment_success_rate"], 1 / 3)
        self.assertEqual(p50["cbaa_full_observer_agreement_rate"], 0.0)
        self.assertEqual(q_bytes_before, hashlib.sha256(self.qfile.read_bytes()).hexdigest())
        self.assertEqual(c_bytes_before, hashlib.sha256(self.one_file.read_bytes()).hexdigest())

    def test_writes_paired_rows_and_sha256_manifest_without_source_modification(self):
        self.run_report()
        with (self.output / "budget_per_seed.csv").open(
            encoding="utf-8", newline=""
        ) as f:
            rows = list(csv.DictReader(f))
        self.assertEqual(len(rows), 2 * 3 * 3)
        self.assertEqual(len({(r["cbaa_iterations"], r["seed"], r["p_loss"])
                              for r in rows}), len(rows))
        selected_p0 = [r for r in rows
                       if r["selected_by_zero_loss_bytes_only"] == "1"
                       and float(r["p_loss"]) == 0.0]
        self.assertEqual(len(selected_p0), 3)
        self.assertTrue(all(float(r["cbaa_to_greedy_sent_bytes_ratio"]) > 0
                            for r in selected_p0))
        self.assertTrue(all(r["observed_bytes_within_tolerance"] == "1"
                            for r in selected_p0))
        manifest = json.loads((self.output / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["selected_cbaa_iterations_by_zero_loss_bytes_only"], 2)
        self.assertEqual(manifest["analysis_git_sha"], "analysis-E9A-test-SHA")
        self.assertEqual(manifest["seeds"], 3)
        self.assertIn("NOT hard capped", manifest["study"])
        self.assertEqual(
            manifest["source_files"]["quarter"]["sha256"],
            hashlib.sha256(self.qfile.read_bytes()).hexdigest(),
        )
        self.assertFalse(any(
            "hungarian" in key.lower()
            for key in rows[0]
        ))

    def test_previous_report_cannot_be_overwritten(self):
        self.run_report()
        with self.assertRaises(ProtocolError) as ctx:
            self.run_report()
        self.assertEqual(ctx.exception.diagnostic.owner,
                         "experiments.compare_cbaa_budget")
        self.assertEqual(ctx.exception.diagnostic.function, "write_budget_calibration")
        self.assertEqual(ctx.exception.diagnostic.category, "state")
        self.assertEqual(ctx.exception.diagnostic.code, "BUDGET_REPORT_ALREADY_EXISTS")

    def test_source_tree_cannot_be_used_as_output(self):
        with self.assertRaises(ProtocolError) as ctx:
            self.run_report(output=self.quarter / "nested" / "report")
        self.assertEqual(ctx.exception.diagnostic.code, "BUDGET_REPORT_SOURCE_COLLISION")
        self.assertFalse((self.quarter / "nested").exists())

    def test_duplicate_iteration_configuration_rejected(self):
        alternate = Path(self.tmp.name) / "same_budget_different_root"
        save_csv(alternate / "raw" / "cbaa_again.csv",
                 [cbaa_row(seed, p, 2) for seed in range(3) for p in LOSSES])
        with self.assertRaises(ProtocolError) as ctx:
            self.run_report(roots=(self.cbaa_two, alternate))
        self.assertEqual(ctx.exception.diagnostic.category, "contract")
        self.assertEqual(ctx.exception.diagnostic.code,
                         "DUPLICATE_CBAA_BUDGET_CONFIGURATION")
        self.assertFalse(self.output.exists())

    def test_greedy_reference_must_match_for_every_paired_seed(self):
        rows = [cbaa_row(seed, p, 1) for seed in range(3) for p in LOSSES]
        rows[1]["greedy_reference_cost"] = 9999
        save_csv(self.one_file, rows)
        with self.assertRaises(ProtocolError) as ctx:
            self.run_report()
        self.assertEqual(ctx.exception.diagnostic.code, "BUDGET_PAIRED_SCENARIO_MISMATCH")
        self.assertFalse(self.output.exists())

    def test_missing_one_seed_condition_is_not_silently_imputed(self):
        save_csv(self.one_file, [cbaa_row(seed, p, 1)
                                 for seed in range(3) for p in LOSSES
                                 if not (seed == 2 and p == 0.30)])
        with self.assertRaises(ProtocolError) as ctx:
            self.run_report()
        self.assertEqual(ctx.exception.diagnostic.code,
                         "BUDGET_SOURCE_COVERAGE_MISMATCH")
        self.assertFalse(self.output.exists())

    def test_wrong_cbaa_bytes_or_packet_count_is_contract_failure(self):
        rows = [cbaa_row(seed, p, 1) for seed in range(3) for p in LOSSES]
        rows[0]["payload_bytes"] = 999
        save_csv(self.one_file, rows)
        with self.assertRaises(ProtocolError) as ctx:
            self.run_report()
        self.assertEqual(ctx.exception.diagnostic.code, "BUDGET_SOURCE_CONTRACT_MISMATCH")

    def test_missing_or_ambiguous_raw_is_first_dependency_failure(self):
        self.one_file.unlink()
        with self.assertRaises(ProtocolError) as ctx:
            self.run_report()
        self.assertEqual(ctx.exception.diagnostic.code, "MISSING_BUDGET_SOURCE_CSV")
        save_csv(self.one_file, [cbaa_row(seed, p, 1)
                                 for seed in range(3) for p in LOSSES])
        save_csv(self.cbaa_one / "raw" / "cbaa_duplicate.csv",
                 [cbaa_row(seed, p, 1) for seed in range(3) for p in LOSSES])
        with self.assertRaises(ProtocolError) as ctx:
            self.run_report()
        self.assertEqual(ctx.exception.diagnostic.code, "AMBIGUOUS_BUDGET_SOURCE_CSV")

    def test_invalid_shape_order_tolerance_and_duplicate_roots(self):
        with self.assertRaises(ProtocolError) as ctx:
            validate_budget_calibration_config(
                robots=2, tasks=3, seeds=3, max_rounds=4,
                losses=LOSSES, tolerance=0.10,
                cbaa_roots=(self.cbaa_one,),
            )
        self.assertEqual(ctx.exception.diagnostic.code, "INVALID_BUDGET_CALIBRATION_SHAPE")
        for losses, tolerance, roots in (
            ((0.30, 0.0), 0.1, (self.cbaa_one,)),
            (LOSSES, 1.0, (self.cbaa_one,)),
            (LOSSES, 0.1, (self.cbaa_one, self.cbaa_one)),
        ):
            with self.assertRaises(ProtocolError) as ctx:
                validate_budget_calibration_config(
                    robots=2, tasks=2, seeds=3, max_rounds=4,
                    losses=losses, tolerance=tolerance, cbaa_roots=roots,
                )
            self.assertEqual(ctx.exception.diagnostic.code, "INVALID_BUDGET_CALIBRATION_GRID")


if __name__ == "__main__":
    unittest.main()

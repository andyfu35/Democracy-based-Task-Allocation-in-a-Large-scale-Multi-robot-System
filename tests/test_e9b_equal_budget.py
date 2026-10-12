"""E9B-4 equal-hard-cap paired runner and evidence regression contract."""
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
from experiments.run_e9b_equal_budget import (
    parse_sender_budgets,
    prepare_equal_budget_output,
    run_budgeted_cbaa_trial,
    run_budgeted_greedy_trial,
    run_e9b_equal_budget_experiment,
    validate_equal_budget_config,
    validate_paired_sender_accounting,
)


class ConstantLatency:
    def sample_ms(self, key: str) -> float:
        return 5.0


def read_pair(root: Path) -> dict[str, str]:
    raw = next((root / "paired" / "raw").glob("e9b_pairs_*.csv"))
    with raw.open(encoding="utf-8", newline="") as handle:
        return next(csv.DictReader(handle))


class EqualBudgetEvidenceTests(unittest.TestCase):
    def run_small(
        self, root: Path, *, caps=(0, 32, 80, 1000),
        losses=(0.0, 0.30), seeds=2,
    ):
        with (
            patch("experiments.run_e9b_equal_budget.ensure_rady_dataset", return_value=root),
            patch("experiments.run_e9b_equal_budget.load_rady_latency_profile", return_value=object()),
            patch("experiments.run_e9b_equal_budget.summarize_latency_profile", return_value={"max_ms": 10.0}),
            patch("experiments.run_e9b_equal_budget.EmpiricalLatencySampler", return_value=ConstantLatency()),
            patch("experiments.run_e9b_equal_budget.read_retirement_revision", return_value="e9b-test-sha"),
        ):
            return run_e9b_equal_budget_experiment(
                robots=2, tasks=2, seeds=seeds, loss_probabilities=losses,
                budget_bytes=caps, max_rounds=4, max_iterations=10,
                dataset_path=root, output_root=root / "paired",
                allow_download=False,
            )

    def test_invalid_dimensions_first_diagnostic(self):
        for bad in ({"robots": 0}, {"tasks": 3}, {"seeds": 0},
                    {"max_rounds": 0}, {"max_iterations": 0}, {"robots": True}):
            args = dict(robots=2, tasks=2, seeds=1, loss_probabilities=(0.0,),
                        budget_bytes=(0,), max_rounds=2, max_iterations=2)
            args.update(bad)
            with self.subTest(bad=bad), self.assertRaises(ProtocolError) as cm:
                validate_equal_budget_config(**args)
            d = cm.exception.diagnostic
            self.assertEqual(
                (d.owner, d.function, d.category, d.code),
                ("experiments.run_e9b_equal_budget", "validate_equal_budget_config",
                 "data", "E9B_INVALID_DIMENSIONS"),
            )

    def test_invalid_loss_axis_and_budget_grid(self):
        args = dict(robots=2, tasks=2, seeds=1, loss_probabilities=(0.0,),
                    budget_bytes=(0,), max_rounds=2, max_iterations=2)
        for losses in ((), (0.30, 0.0), (0.0, 0.0), (0.0, True),
                       (float("nan"),), (-0.1,)):
            with self.subTest(losses=losses), self.assertRaises(ProtocolError):
                validate_equal_budget_config(**{**args, "loss_probabilities": losses})
        for caps in ((), (0, 0), (200, 100), (True, 200), (-1,), (0.5,)):
            with self.subTest(caps=caps), self.assertRaises(ProtocolError):
                validate_equal_budget_config(**{**args, "budget_bytes": caps})
        self.assertEqual(parse_sender_budgets("0,100,250000"), (0, 100, 250000))

    def test_protect_historical_sources_and_nonempty_output(self):
        with self.assertRaises(ProtocolError) as cm:
            prepare_equal_budget_output(Path("results/e8_cbaa_budget3_100r50t_smoke"))
        self.assertEqual(cm.exception.diagnostic.code, "E9B_OUTPUT_SOURCE_COLLISION")
        with self.assertRaises(ProtocolError):
            prepare_equal_budget_output(Path("results"))
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "experiment"
            path.mkdir()
            (path / "summary.csv").write_text("immutable")
            with self.assertRaises(ProtocolError) as cm:
                prepare_equal_budget_output(path)
            self.assertEqual(cm.exception.diagnostic.code, "E9B_OUTPUT_ALREADY_EXISTS")
            (path / "summary.csv").unlink()
            (path / "README.md").write_text("ledger")
            prepare_equal_budget_output(path)

    def test_paired_grid_and_source_sha256_manifest(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            summary = self.run_small(root)
            self.assertEqual(len(summary), 8)
            path = next((root / "paired" / "raw").glob("e9b_pairs_*.csv"))
            with path.open(encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(len(rows), 16)
            self.assertEqual({
                (int(r["seed"]), float(r["p_cost_loss"]),
                 int(r["hard_cap_sender_payload_bytes"])) for r in rows
            }, {(seed, p, cap) for seed in range(2) for p in (0.0, 0.30)
               for cap in (0, 32, 80, 1000)})
            manifest = json.loads((root / "paired" / "manifest.json").read_text())
            self.assertEqual(manifest["source_git_sha"], "e9b-test-sha")
            self.assertEqual(manifest["raw_rows"], 16)
            self.assertEqual(manifest["raw_sha256"], hashlib.sha256(path.read_bytes()).hexdigest())
            self.assertEqual(manifest["summary_sha256"], hashlib.sha256(
                (root / "paired" / "summary.csv").read_bytes()).hexdigest())
            self.assertTrue(manifest["observer_agreement_is_not_distributed_commit"])
            self.assertEqual(len({
                r["scenario_sha256"] for r in rows if r["seed"] == "0"
            }), 1)

    def test_zero_cap_has_zero_sends_and_zero_success(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            self.run_small(root, caps=(0,), losses=(0.0,), seeds=1)
            r = read_pair(root)
            self.assertEqual((r["greedy_sender_bytes"], r["cbaa_sender_bytes"]), ("0", "0"))
            self.assertEqual(
                (r["greedy_full_commit_success"], r["cbaa_full_observer_agreement"]),
                ("0", "0"),
            )
            self.assertEqual(
                (r["greedy_budget_exhausted"], r["cbaa_budget_exhausted"]), ("1", "1"),
            )
            self.assertEqual((r["greedy_stop_code"], r["cbaa_stop_code"]), (
                "SEND_PAYLOAD_BUDGET_EXHAUSTED", "SEND_PAYLOAD_BUDGET_EXHAUSTED",
            ))
            self.assertEqual((r["greedy_stop_owner"], r["cbaa_stop_owner"]), ("network", "network"))
            self.assertTrue(math.isnan(float(r["greedy_full_batch_cost_complete_only"])))
            self.assertTrue(math.isnan(float(r["cbaa_full_batch_cost_complete_only"])))

    def test_one_cost_packet_fits_but_no_cbaa_vector_fits(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            self.run_small(root, caps=(32,), losses=(0.0,), seeds=1)
            r = read_pair(root)
            self.assertEqual((r["greedy_sender_bytes"], r["cbaa_sender_bytes"]), ("32", "0"))
            self.assertEqual(r["greedy_budget_stop_phase"], "cost")
            self.assertEqual(r["cbaa_budget_stop_phase"], "cbaa_consensus")
            self.assertEqual(r["greedy_full_commit_success"], "0")
            self.assertEqual(r["cbaa_full_observer_agreement"], "0")

    def test_great_enough_cap_yields_both_distinct_full_success_types(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            self.run_small(root, caps=(1000,), losses=(0.0,), seeds=1)
            r = read_pair(root)
            self.assertEqual(r["greedy_full_commit_success"], "1")
            self.assertEqual(r["cbaa_full_observer_agreement"], "1")
            self.assertEqual(r["greedy_method"], "democracy_greedy_quarter_plurality_retirement")
            self.assertEqual(r["cbaa_method"], "cbaa_sync_single_assignment")
            self.assertTrue(math.isfinite(float(r["greedy_full_batch_cost_complete_only"])))
            self.assertTrue(math.isfinite(float(r["cbaa_full_batch_cost_complete_only"])))
            self.assertLessEqual(int(r["greedy_sender_bytes"]), 1000)
            self.assertLessEqual(int(r["cbaa_sender_bytes"]), 1000)

    def test_reuse_existing_evidence_fails_without_overwrite(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            self.run_small(root, caps=(0,), losses=(0.0,), seeds=1)
            raw = next((root / "paired" / "raw").glob("*.csv"))
            digest = hashlib.sha256(raw.read_bytes()).hexdigest()
            with self.assertRaises(ProtocolError) as cm:
                self.run_small(root, caps=(0,), losses=(0.0,), seeds=1)
            self.assertEqual(cm.exception.diagnostic.code, "E9B_OUTPUT_ALREADY_EXISTS")
            self.assertEqual(hashlib.sha256(raw.read_bytes()).hexdigest(), digest)

    def test_budget_is_fresh_and_same_seed_is_deterministic(self):
        costs = ((1.0, 10.0), (10.0, 1.0))
        with patch("experiments.run_e9b_equal_budget.EmpiricalLatencySampler",
                   return_value=ConstantLatency()):
            a, ab = run_budgeted_greedy_trial(
                cost_matrix=costs, seed=0, p=0.30, cap=1000,
                phase_timeout_ms=10.0, max_rounds=4, profile=object())
            b, bb = run_budgeted_greedy_trial(
                cost_matrix=costs, seed=0, p=0.30, cap=1000,
                phase_timeout_ms=10.0, max_rounds=4, profile=object())
            c, cb = run_budgeted_cbaa_trial(
                cost_matrix=costs, seed=0, p=0.30, cap=1000,
                phase_timeout_ms=10.0, max_iterations=10, profile=object())
        self.assertEqual(a, b)
        self.assertEqual((ab.sent_bytes, ab.sent_messages), (bb.sent_bytes, bb.sent_messages))
        self.assertIsNot(ab, bb)
        self.assertIsNot(ab, cb)
        self.assertEqual(c.payload_bytes, cb.sent_bytes)

    def test_mismatched_ledger_is_first_evidence_contract_failure(self):
        costs = ((1.0, 10.0), (10.0, 1.0))
        with patch("experiments.run_e9b_equal_budget.EmpiricalLatencySampler",
                   return_value=ConstantLatency()):
            greedy, gb = run_budgeted_greedy_trial(
                cost_matrix=costs, seed=0, p=0.0, cap=1000,
                phase_timeout_ms=10.0, max_rounds=4, profile=object())
            cbaa, cb = run_budgeted_cbaa_trial(
                cost_matrix=costs, seed=0, p=0.0, cap=1000,
                phase_timeout_ms=10.0, max_iterations=10, profile=object())
        cb.sent_bytes += 1
        with self.assertRaises(ProtocolError) as cm:
            validate_paired_sender_accounting(
                cap=1000, greedy=greedy, gb=gb, cbaa=cbaa, cb=cb,
            )
        d = cm.exception.diagnostic
        self.assertEqual(
            (d.owner, d.function, d.category, d.code),
            ("experiments.run_e9b_equal_budget", "validate_paired_sender_accounting",
             "contract", "E9B_PAIRED_SENDER_ACCOUNTING_MISMATCH"),
        )


if __name__ == "__main__":
    unittest.main()

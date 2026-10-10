from __future__ import annotations

import csv
import json
import math
from pathlib import Path
import tempfile
import unittest

from democracy_mrta.diagnostics import ProtocolError
from experiments.compare_greedy_communication import (
    DEFAULT_LOSSES,
    compare_existing_greedy_evidence,
    locate_single_raw_evidence,
    validate_comparison_configuration,
)


class GreedyOnlyCommunicationEvidenceTests(unittest.TestCase):
    LOSSES = (0.0, 0.30, 0.50)
    SEEDS = 3

    def make_row(self, *, rule: str, seed: int, loss: float) -> dict[str, str]:
        full = (
            loss == 0.0
            or rule == "quarter_plurality" and (loss == 0.30 or seed < 2)
            or rule == "strict_majority" and loss == 0.30 and seed != 1
        )
        base = 100.0 + 10.0 * seed
        cost = base * (1.0 if loss == 0 else 1.05 if full else 0.4)
        committed = 2 if full else 1
        row = {
            "timestamp_utc": "20261010T060000Z",
            "git_sha": "majority-historical-sha" if rule == "strict_majority" else "pure-quarter-sha",
            "seed": str(seed), "robots": "4", "tasks": "2",
            "max_rounds": "4",
            "method": "democracy_greedy_retirement" if rule == "strict_majority"
                      else "democracy_greedy_quarter_plurality_retirement",
            "p_cost_loss": str(loss),
            "p_vote_loss": str(loss),
            "committed_tasks": str(committed),
            "task_commit_rate": str(committed / 2),
            "greedy_correct_executor_rate": "1.0" if loss == 0 else "0.5",
            "greedy_correctness_among_committed": "1.0" if loss == 0 else "0.5",
            "full_assignment_success": str(int(full)),
            "total_cost": str(cost),
            "greedy_reference_cost": str(base),
            "rounds_executed": "2" if full else "4",
            "total_elapsed_ms": str(80 + 40 * loss + (30 if rule == "quarter_plurality" else 0)),
            "logical_message_count": str(30 + seed + (10 if rule == "quarter_plurality" else 0)),
            "payload_bytes": str(2000 + 10 * seed + (200 if rule == "quarter_plurality" else 0)),
            "quorum_failed_attempts": "0" if full else "3",
            "safety_failures": "0",
            "cost_packet_attempts": "20",
            "cost_packet_dropped": str(round(20 * loss)),
            "remote_vote_attempts": "10",
            "remote_vote_dropped": str(round(10 * loss)),
        }
        # Original 51% baseline was recorded BEFORE this optional column existed.
        if rule == "quarter_plurality":
            row["vote_decision_rule"] = "quarter_plurality"
        return row

    def make_files(self, root: Path) -> tuple[Path, Path, Path]:
        majority = root / "majority"
        quarter = root / "quarter"
        for rule, location in (
            ("strict_majority", majority),
            ("quarter_plurality", quarter),
        ):
            raw = location / "raw"
            raw.mkdir(parents=True)
            rows = [
                self.make_row(rule=rule, seed=seed, loss=loss)
                for seed in range(self.SEEDS) for loss in self.LOSSES
            ]
            with (raw / "retirement_formal.csv").open("w", newline="", encoding="utf-8") as stream:
                writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
                writer.writeheader()
                writer.writerows(rows)
        return majority, quarter, root / "greedy_report"

    @staticmethod
    def edit_raw(path: Path, change) -> None:
        with path.open(newline="", encoding="utf-8") as stream:
            rows = list(csv.DictReader(stream))
        change(rows)
        with path.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)

    def analyze(self, majority: Path, quarter: Path, report: Path):
        return compare_existing_greedy_evidence(
            majority_root=majority, quarter_root=quarter,
            output_root=report, robots=4, tasks=2,
            seeds=self.SEEDS, max_rounds=4, losses=self.LOSSES,
        )

    def test_pairing_baseline_gaps_and_all_incomplete_cost_excluded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            majority, quarter, report = self.make_files(Path(tmp))
            curves, paired = self.analyze(majority, quarter, report)
            self.assertEqual(len(curves), 6)
            self.assertEqual(len(paired), 3)
            mid = next(row for row in paired if row["p_cost_loss"] == 0.30)
            self.assertAlmostEqual(mid["majority_full_assignment_success_rate"], 2 / 3)
            self.assertEqual(mid["quarter_full_assignment_success_rate"], 1.0)
            self.assertAlmostEqual(
                mid["quarter_minus_majority_full_success_percentage_points"], 100 / 3
            )
            self.assertEqual(mid["both_completed_count"], 2)
            self.assertEqual(mid["only_quarter_completed_count"], 1)

            high = next(row for row in paired if row["p_cost_loss"] == 0.50)
            self.assertEqual(high["both_completed_count"], 0)
            self.assertEqual(high["only_quarter_completed_count"], 2)
            self.assertEqual(high["neither_completed_count"], 1)
            self.assertTrue(math.isnan(
                high["mean_quarter_minus_majority_cost_pct_of_no_loss_greedy_common_completed"]
            ))
            major_high = next(r for r in curves
                              if r["vote_decision_rule"] == "strict_majority"
                              and r["p_cost_loss"] == 0.50)
            self.assertEqual(major_high["complete_case_cost_count"], 0)
            self.assertTrue(math.isnan(
                major_high["mean_cost_degradation_vs_own_zero_loss_pct_complete_only"]
            ))
            quarter_high = next(r for r in curves
                                if r["vote_decision_rule"] == "quarter_plurality"
                                and r["p_cost_loss"] == 0.50)
            self.assertEqual(quarter_high["complete_case_cost_count"], 2)
            self.assertAlmostEqual(
                quarter_high["mean_cost_degradation_vs_own_zero_loss_pct_complete_only"], 5.0
            )
            zero = [r for r in curves if r["p_cost_loss"] == 0]
            self.assertEqual(len(zero), 2)
            self.assertTrue(all(
                abs(r["mean_cost_degradation_vs_own_zero_loss_pct_complete_only"]) < 1e-9
                for r in zero
            ))
            self.assertEqual(len(list(csv.DictReader(
                (report / "greedy_per_seed.csv").open(newline="", encoding="utf-8")
            ))), 18)
            for filename in ("greedy_per_seed.csv", "greedy_rule_curve.csv",
                             "greedy_protocol_delta.csv"):
                with (report / filename).open(newline="", encoding="utf-8") as stream:
                    cols = csv.DictReader(stream).fieldnames or []
                self.assertFalse(any("hungarian" in x or "oracle" in x for x in cols))
            manifest = json.loads((report / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["source_evidence"]["strict_majority"]["source_git_sha"],
                             "majority-historical-sha")
            self.assertEqual(manifest["source_evidence"]["quarter_plurality"]["source_git_sha"],
                             "pure-quarter-sha")
            self.assertEqual(manifest["seeds"], self.SEEDS)

    def test_changed_paired_greedy_scene_is_contract_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            majority, quarter, report = self.make_files(Path(tmp))
            raw = quarter / "raw" / "retirement_formal.csv"
            self.edit_raw(raw, lambda rows: rows[1].__setitem__("greedy_reference_cost", "999.0"))
            with self.assertRaises(ProtocolError) as context:
                self.analyze(majority, quarter, report)
            self.assertEqual(context.exception.diagnostic.code, "PAIRED_GREEDY_SCENE_MISMATCH")
            self.assertFalse(report.exists())

    def test_missing_zero_loss_seed_rejected_instead_of_imputed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            majority, quarter, report = self.make_files(Path(tmp))
            raw = majority / "raw" / "retirement_formal.csv"
            self.edit_raw(
                raw,
                lambda rows: rows.__setitem__(slice(None), [
                    r for r in rows if not (r["seed"] == "1" and r["p_cost_loss"] == "0.0")
                ]),
            )
            with self.assertRaises(ProtocolError) as context:
                self.analyze(majority, quarter, report)
            self.assertEqual(context.exception.diagnostic.code,
                             "GREEDY_SEED_LOSS_COVERAGE_MISMATCH")

    def test_reject_forced_fallback_as_wrong_protocol(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            majority, quarter, report = self.make_files(Path(tmp))
            raw = quarter / "raw" / "retirement_formal.csv"
            self.edit_raw(
                raw, lambda rows: rows[0].__setitem__(
                    "vote_decision_rule", "quarter_plurality_fallback"
                )
            )
            with self.assertRaises(ProtocolError) as context:
                self.analyze(majority, quarter, report)
            self.assertEqual(context.exception.diagnostic.code, "GREEDY_RAW_CONTRACT_MISMATCH")

    def test_duplicate_seed_loss_in_historical_raw_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            majority, quarter, report = self.make_files(Path(tmp))
            raw = majority / "raw" / "retirement_formal.csv"
            self.edit_raw(raw, lambda rows: rows.append(dict(rows[0])))
            with self.assertRaises(ProtocolError) as context:
                self.analyze(majority, quarter, report)
            self.assertEqual(
                context.exception.diagnostic.code, "DUPLICATE_GREEDY_SEED_CONDITION"
            )
            self.assertFalse(report.exists())

    def test_zero_loss_run_that_is_not_greedy_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            majority, quarter, report = self.make_files(Path(tmp))
            raw = majority / "raw" / "retirement_formal.csv"
            self.edit_raw(raw, lambda rows: rows[0].__setitem__("total_cost", "150.0"))
            with self.assertRaises(ProtocolError) as context:
                self.analyze(majority, quarter, report)
            self.assertEqual(
                context.exception.diagnostic.code, "ZERO_LOSS_GREEDY_BASELINE_MISMATCH"
            )

    def test_report_cannot_be_written_under_either_source_tree(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            majority, quarter, _ = self.make_files(Path(tmp))
            with self.assertRaises(ProtocolError) as context:
                self.analyze(majority, quarter, majority / "derived_results")
            self.assertEqual(
                context.exception.diagnostic.code,
                "GREEDY_ANALYSIS_SOURCE_OUTPUT_COLLISION",
            )
            self.assertFalse((majority / "derived_results").exists())

    def test_previously_written_report_is_never_overwritten(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            majority, quarter, report = self.make_files(Path(tmp))
            self.analyze(majority, quarter, report)
            original = (report / "greedy_protocol_delta.csv").read_bytes()
            with self.assertRaises(ProtocolError) as context:
                self.analyze(majority, quarter, report)
            self.assertEqual(context.exception.diagnostic.code, "GREEDY_ANALYSIS_OUTPUT_EXISTS")
            self.assertEqual(original, (report / "greedy_protocol_delta.csv").read_bytes())

    def test_missing_and_multiple_raw_archives_fail_at_dependency_owner(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaises(ProtocolError) as missing:
                locate_single_raw_evidence(root=root, rule="strict_majority")
            self.assertEqual(missing.exception.diagnostic.code, "MISSING_GREEDY_RAW_EVIDENCE")
            raw = root / "raw"
            raw.mkdir()
            (raw / "retirement_1.csv").write_text("seed\n0\n", encoding="utf-8")
            (raw / "retirement_2.csv").write_text("seed\n0\n", encoding="utf-8")
            with self.assertRaises(ProtocolError) as duplicate:
                locate_single_raw_evidence(root=root, rule="strict_majority")
            self.assertEqual(duplicate.exception.diagnostic.code, "AMBIGUOUS_GREEDY_RAW_EVIDENCE")

    def test_bad_coverage_duplicate_rows_and_safety_rejected(self) -> None:
        for field, value, code in (
            ("seed", "99", "GREEDY_RAW_CONTRACT_MISMATCH"),
            ("safety_failures", "1", "GREEDY_RAW_CONTRACT_MISMATCH"),
            ("full_assignment_success", "0", "GREEDY_RAW_CONTRACT_MISMATCH"),
        ):
            with self.subTest(field=field):
                with tempfile.TemporaryDirectory() as tmp:
                    majority, quarter, report = self.make_files(Path(tmp))
                    raw = quarter / "raw" / "retirement_formal.csv"
                    self.edit_raw(raw, lambda rows: rows[0].__setitem__(field, value))
                    with self.assertRaises(ProtocolError) as context:
                        self.analyze(majority, quarter, report)
                    self.assertEqual(context.exception.diagnostic.code, code)

    def test_comparison_config_requires_zero_loss(self) -> None:
        with self.assertRaises(ProtocolError) as context:
            validate_comparison_configuration(
                robots=100, tasks=50, seeds=100, max_rounds=100,
                losses=(0.10, 0.30),
            )
        self.assertEqual(context.exception.diagnostic.code,
                         "INVALID_GREEDY_COMPARISON_LOSS_AXIS")
        self.assertEqual(DEFAULT_LOSSES, (0.0, 0.10, 0.20, 0.30, 0.40, 0.50))


if __name__ == "__main__":
    unittest.main()

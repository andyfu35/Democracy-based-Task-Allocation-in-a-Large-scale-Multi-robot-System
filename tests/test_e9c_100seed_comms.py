"""E9C-2 regression tests: paired 100-seed evidence owner, original methods untouched."""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from democracy_mrta.diagnostics import ProtocolError
from experiments.run_e9c_100seed_comms import (
    calculate_offline_minimum_k,
    prepare_100seed_comms_output,
    run_e9c_100seed_comms,
    summarize_100seed_conditions,
    validate_100seed_comms_config,
)


class Real100SeedCommsTests(unittest.TestCase):

    def defaults(self, root, *, include_raw_robot_info=True, seeds=3, k=(1,2)):
        return dict(
            robots=2, tasks=2, seeds=seeds, first_seed=0,
            cbaa_iterations=k, max_rounds=5,
            latency_mode="constant", include_raw_robot_info=include_raw_robot_info,
            output_root=root, allow_download=False,
        )

    def run_small(self, **kwargs):
        with patch(
            "experiments.run_e9c_100seed_comms.read_retirement_revision",
            return_value="fixture-source-sha",
        ):
            return run_e9c_100seed_comms(**kwargs)

    def test_three_paired_seeds_have_real_task_and_own_cost_plus_cbaa_bid(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)/"e9c_data"
            rows = self.run_small(**self.defaults(root))
            self.assertEqual(len(rows), 15)
            by_seed = {}
            for row in rows:
                by_seed.setdefault(row["seed"], {})[row["method"]] = row
            self.assertEqual(set(by_seed), {0,1,2})
            for trial in by_seed.values():
                self.assertEqual(len(trial), 5)
                democracy = trial["democracy_task_cost_vote"]
                cbaa1 = trial["cbaa_original_local_bid_K1"]
                raw1 = trial["cbaa_raw_robot_information_K1"]
                cbaa2 = trial["cbaa_original_local_bid_K2"]
                self.assertEqual(democracy["task_announcement_sender_bytes"], 80)
                self.assertEqual(democracy["democracy_cost_rows_sender_bytes"], 64)
                self.assertEqual(democracy["peer_robot_position_sender_bytes"], 0)
                self.assertEqual(democracy["end_to_end_sender_application_bytes"], 296)
                self.assertEqual(cbaa1["cbaa_bid_vector_sender_bytes"], 80)
                self.assertEqual(cbaa1["end_to_end_sender_application_bytes"], 160)
                self.assertEqual(cbaa2["end_to_end_sender_application_bytes"], 240)
                self.assertEqual(raw1["end_to_end_sender_application_bytes"], 232)
                self.assertEqual(raw1["peer_robot_position_sender_bytes"], 72)
                self.assertEqual(raw1["completed_or_observer_agreed_tasks"], cbaa1["completed_or_observer_agreed_tasks"])
                self.assertEqual(raw1["full_result_of_own_semantics"], cbaa1["full_result_of_own_semantics"])
                self.assertEqual(democracy["success_semantics"], "actual_reliable_commit")
                self.assertEqual(cbaa1["success_semantics"], "posthoc_observer_unanimity_not_distributed_commit")

    def test_final_evidence_raw_summary_paired_and_manifest_sha(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)/"e9c_report"
            rows = self.run_small(**self.defaults(root))
            paths = [root/"per_seed_method_bytes.csv", root/"summary.csv",
                     root/"offline_min_cbaa_k_per_seed.csv", root/"manifest.json"]
            self.assertTrue(all(p.exists() for p in paths))
            self.assertFalse((root/"per_seed_method_bytes.partial.csv").exists())
            manifest = json.loads(paths[3].read_text(encoding="utf-8"))
            self.assertEqual(manifest["git_sha"], "fixture-source-sha")
            self.assertEqual(manifest["all_rows"], len(rows))
            self.assertEqual(manifest["expected_rows"], len(rows))
            self.assertEqual(manifest["seeds"], 3)
            self.assertTrue(manifest["cbaa_no_final_commit"])
            self.assertTrue(manifest["offline_minimum_K_is_not_runtime_stopping"])
            self.assertEqual(manifest["information"]["task_record_bytes"], 32)
            for path in paths[:3]:
                self.assertEqual(
                    manifest["sha256"][path.name],
                    hashlib.sha256(path.read_bytes()).hexdigest(),
                )
            with paths[0].open(newline="", encoding="utf-8") as handle:
                self.assertEqual(len(list(csv.DictReader(handle))), 15)
            with paths[1].open(newline="", encoding="utf-8") as handle:
                self.assertEqual(len(list(csv.DictReader(handle))), 5)
            with paths[2].open(newline="", encoding="utf-8") as handle:
                pairs = list(csv.DictReader(handle))
            self.assertEqual(len(pairs), 3)
            self.assertTrue(all(item["offline_oracle_cannot_stop_distributed_algorithm"] == "1" for item in pairs))

    def test_source_faithful_cbaa_alone_does_not_pay_poses(self):
        with tempfile.TemporaryDirectory() as folder:
            rows = self.run_small(
                **self.defaults(Path(folder)/"e9c_source_faithful",
                                include_raw_robot_info=False, seeds=2)
            )
            self.assertEqual(len(rows), 6)
            self.assertTrue(all("raw_robot_information" not in row["method"] for row in rows))
            self.assertTrue(all(row["peer_robot_position_sender_bytes"] == 0 for row in rows))
            self.assertEqual(set(x["method"] for x in rows),
                             {"democracy_task_cost_vote", "cbaa_original_local_bid_K1",
                              "cbaa_original_local_bid_K2"})

    def test_offline_min_k_is_report_only_without_distributed_stop(self):
        with tempfile.TemporaryDirectory() as folder:
            rows = self.run_small(**self.defaults(Path(folder)/"e9c_oracle"))
            pairs = calculate_offline_minimum_k(
                rows=rows, cbaa_iterations=(1, 2), include_raw_robot_info=True,
            )
            self.assertEqual(len(pairs), 3)
            self.assertTrue(all(int(item["democracy_actual_commit_full"]) == 1 for item in pairs))
            self.assertTrue(all(int(item["offline_oracle_cannot_stop_distributed_algorithm"]) == 1 for item in pairs))
            summary = summarize_100seed_conditions(rows)
            self.assertEqual(set(item["seeds"] for item in summary), {3})
            self.assertTrue(all(item["success_semantics"] for item in summary))

    def test_duplicate_root_never_overwrites_evidence(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)/"e9c_immutable"
            kwargs=self.defaults(root)
            self.run_small(**kwargs)
            before = (root/"per_seed_method_bytes.csv").read_bytes()
            with self.assertRaises(ProtocolError) as cm:
                self.run_small(**kwargs)
            self.assertEqual(cm.exception.diagnostic.code,"E9C2_OUTPUT_EXISTS")
            self.assertEqual(before, (root/"per_seed_method_bytes.csv").read_bytes())

    def test_old_result_roots_protected(self):
        for root in (Path("results"), Path("results/e9b_equal_sender_budget_pilot"),
                     Path("results/e8_cbaa_pilot")):
            with self.subTest(root=root), self.assertRaises(ProtocolError) as cm:
                prepare_100seed_comms_output(root)
            self.assertEqual(cm.exception.diagnostic.code, "E9C2_PROTECTED_OUTPUT_ROOT")

    def test_invalid_shapes_and_k_axes_use_original_diagnostics(self):
        baseline=self.defaults(Path("results/e9c_unused"))
        for altered in ({"robots":0}, {"tasks":3}, {"seeds":0},
                        {"seeds":True}, {"first_seed":-1},
                        {"max_rounds":1}):
            x=dict(baseline);x.update(altered);x.pop("output_root");x.pop("include_raw_robot_info");x.pop("allow_download")
            with self.subTest(altered=altered),self.assertRaises(ProtocolError) as cm:
                validate_100seed_comms_config(**x)
            self.assertEqual(cm.exception.diagnostic.code,"E9C2_INVALID_SCENARIO_GRID")
        for k in ((2,1), (1,1), (0,2), ()):
            with self.subTest(k=k),self.assertRaises(ProtocolError) as cm:
                validate_100seed_comms_config(
                    robots=2,tasks=2,seeds=3,first_seed=0,
                    cbaa_iterations=k,max_rounds=5,latency_mode="constant")
            self.assertEqual(cm.exception.diagnostic.code, "E9C2_INVALID_K_GRID")
        with self.assertRaises(ProtocolError) as cm:
            validate_100seed_comms_config(
                robots=2,tasks=2,seeds=3,first_seed=0,
                cbaa_iterations=(1,),max_rounds=5,latency_mode="unknown")
        self.assertEqual(cm.exception.diagnostic.code,"E9C2_UNKNOWN_LATENCY_MODE")


if __name__=="__main__":
    unittest.main()

"""E9D-2 losses on original Democracy and original CBAA without manually chosen K."""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from democracy_mrta.diagnostics import ProtocolError
from experiments.run_e9d_natural_loss import (
    DEFAULT_GRID,
    calculate_e9d_empirical_limits, prepare_e9d_output_root,
    run_e9d_natural_loss, summarize_e9d_loss_results,
    validate_e9d_natural_loss_axes, validate_e9d_physical_accounting,
)


class E9DNaturalLossTests(unittest.TestCase):
    def fixture(self, root, *, seeds=2, losses=(0.0, 1.0), guard=6):
        return dict(
            robots=5,tasks=3,seeds=seeds,first_seed=0,
            loss_probabilities=losses,
            cbaa_safety_round_limit=guard,
            democracy_safety_round_limit=20,
            latency_mode="constant",allow_download=False,
            output_root=root,
        )

    def execute(self, **kwargs):
        with patch(
            "experiments.run_e9d_natural_loss.read_retirement_revision",
            return_value="test-source-e9d",
        ):
            return run_e9d_natural_loss(**kwargs)

    def test_two_algorithms_are_paired_and_only_original_packets_are_sent(self):
        with tempfile.TemporaryDirectory() as tmp:
            rows=self.execute(**self.fixture(Path(tmp)/"e9d_paired"))
            self.assertEqual(len(rows),8)
            for seed in (0,1):
                for p in (0.0,1.0):
                    pair=tuple(r for r in rows
                               if r["seed"]==seed and r["loss_probability"]==p)
                    self.assertEqual(tuple(r["method"] for r in pair),
                                     ("democracy_cost_vote","cbaa_original_local_certified"))
                    validate_e9d_physical_accounting(pair)
                    for row in pair:
                        self.assertEqual(row["task_sender_bytes"],112)
                        self.assertEqual(row["task_packet_count"],1)
                        self.assertEqual(row["total_sender_bytes"],
                                         row["task_sender_bytes"]+row["coordination_sender_bytes"])
                    self.assertEqual(pair[0]["cbaa_bid_sender_bytes"],0)
                    self.assertEqual(pair[1]["cost_sender_bytes"],0)
                    self.assertEqual(pair[1]["vote_sender_bytes"],0)
                    self.assertEqual(pair[0]["cost_sender_bytes"],5*(16+3*8))

    def test_one_hundred_percent_loss_cannot_be_falsely_certified_by_silence(self):
        with tempfile.TemporaryDirectory() as tmp:
            rows=self.execute(**self.fixture(Path(tmp)/"e9d_fullloss",seeds=1))
            at_full_loss=[r for r in rows
                          if r["method"]=="cbaa_original_local_certified"
                          and r["loss_probability"]==1.0]
            self.assertEqual(len(at_full_loss),1)
            r=at_full_loss[0]
            self.assertEqual(r["stop_reason"],"iteration_safety_guard")
            self.assertEqual(r["safety_guard_hit"],1)
            self.assertEqual(r["all_locally_certified"],0)
            self.assertEqual(r["rounds_executed"],6)
            self.assertEqual(r["coordination_dropped"],r["coordination_delivery_attempts"])
            self.assertEqual(r["cbaa_bid_sender_bytes"],
                             r["coordination_send_count"]*(16+3*12))

    def test_no_loss_cbaa_stops_via_peer_evidence_and_original_greedy_commits(self):
        with tempfile.TemporaryDirectory() as tmp:
            rows=self.execute(**self.fixture(Path(tmp)/"e9d_noloss",
                                             seeds=2,losses=(0.0,),guard=25))
            for r in rows:
                if r["method"]=="cbaa_original_local_certified":
                    self.assertEqual(r["stop_reason"],"all_local_evidence_certified")
                    self.assertEqual(r["all_locally_certified"],1)
                    self.assertEqual(r["full_observer_agreement"],1)
                    self.assertLess(r["rounds_executed"],25)
                else:
                    self.assertEqual(r["full_commit"],1)
                    self.assertEqual(r["tasks_confirmed"],3)

    def test_report_summary_separates_guard_observer_and_real_commit(self):
        with tempfile.TemporaryDirectory() as tmp:
            rows=self.execute(**self.fixture(Path(tmp)/"e9d_summary"))
            summary=summarize_e9d_loss_results(rows)
            self.assertEqual(len(summary),4)
            limits=calculate_e9d_empirical_limits(summary)
            self.assertEqual(set(limits),{"democracy_cost_vote","cbaa_original_local_certified"})
            cbaa_full=next(x for x in summary
                           if x["method"]=="cbaa_original_local_certified"
                           and x["loss_probability"]==1.0)
            self.assertEqual(cbaa_full["guard_hit_count"],2)
            self.assertEqual(cbaa_full["full_protocol_result_count"],0)
            self.assertTrue(limits["cbaa_original_local_certified"]["has_censored_guard_cases"])

    def test_report_files_source_sha_and_sha256_are_reproducible(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/"e9d_report"
            rows=self.execute(**self.fixture(root))
            self.assertEqual(len(rows),8)
            raw,summary,manifest=(root/"per_seed_loss_method.csv",
                                   root/"summary_by_loss.csv",
                                   root/"manifest.json")
            self.assertTrue(all(p.exists() for p in (raw,summary,manifest)))
            self.assertFalse((root/"per_seed_loss_method.partial.csv").exists())
            with raw.open(newline="",encoding="utf-8") as handle:
                self.assertEqual(len(list(csv.DictReader(handle))),8)
            with summary.open(newline="",encoding="utf-8") as handle:
                self.assertEqual(len(list(csv.DictReader(handle))),4)
            meta=json.loads(manifest.read_text(encoding="utf-8"))
            self.assertEqual(meta["source_git_sha"],"test-source-e9d")
            self.assertEqual(meta["raw_rows"],8)
            self.assertEqual(meta["expected_rows"],8)
            self.assertTrue(meta["cbaa_no_distributed_stop_ack_or_actual_commit"])
            self.assertTrue(meta["common_task_announced_reliably_with_loss_zero"])
            self.assertTrue(meta["guard_reached_is_not_proof_of_theoretical_failure"])
            for path in (raw,summary):
                self.assertEqual(meta["sha256"][path.name],
                                 hashlib.sha256(path.read_bytes()).hexdigest())

    def test_immutable_protected_result_roots_cannot_be_overwritten(self):
        for path in (Path("results"),Path("results/e9c_original_cbaa_only_100seed")):
            with self.subTest(path=path),self.assertRaises(ProtocolError) as cm:
                prepare_e9d_output_root(path)
            self.assertEqual(cm.exception.diagnostic.code,"E9D_PROTECTED_OUTPUT_ROOT")
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/"e9d_immutable"
            self.execute(**self.fixture(root,seeds=1,losses=(0.0,)))
            with self.assertRaises(ProtocolError) as cm:
                self.execute(**self.fixture(root,seeds=1,losses=(0.0,)))
            self.assertEqual(cm.exception.diagnostic.code,"E9D_OUTPUT_ALREADY_EXISTS")

    def test_malformed_grid_and_guard_first_owner_failure(self):
        base=dict(robots=5,tasks=3,seeds=2,first_seed=0,
                  losses=(0.0,0.5),cbaa_safety_round_limit=5,
                  democracy_safety_round_limit=10,latency_mode="constant")
        for change in ({"robots":0},{"tasks":6},{"seeds":0},
                       {"first_seed":-1},{"cbaa_safety_round_limit":0},
                       {"democracy_safety_round_limit":0}):
            args=dict(base);args.update(change)
            with self.subTest(change=change),self.assertRaises(ProtocolError) as cm:
                validate_e9d_natural_loss_axes(**args)
            self.assertEqual(cm.exception.diagnostic.code,
                             "E9D_INVALID_SCENARIO_OR_GUARD")
        for grid in ((0.5,0.0),(0.5,0.5),(),(0.0,1.2)):
            args=dict(base,losses=grid)
            with self.subTest(grid=grid),self.assertRaises(ProtocolError):
                validate_e9d_natural_loss_axes(**args)

    def test_corrupted_pair_bytes_first_diagnostic_boundary(self):
        first={
            "method":"democracy_cost_vote","seed":0,"loss_probability":0.0,
            "task_sender_bytes":112,"cost_sender_bytes":100,"vote_sender_bytes":0,
            "score_sender_bytes":0,"commit_sender_bytes":0,
            "cbaa_bid_sender_bytes":0,"coordination_sender_bytes":1,
            "total_sender_bytes":113,"coordination_delivered":0,
            "coordination_dropped":0,"coordination_delivery_attempts":0,
        }
        second=dict(first,method="cbaa_original_local_certified",
                    cost_sender_bytes=0,cbaa_bid_sender_bytes=100)
        with self.assertRaises(ProtocolError) as cm:
            validate_e9d_physical_accounting((first,second))
        d=cm.exception.diagnostic
        self.assertEqual((d.owner,d.function,d.category,d.code),
                         ("experiments.run_e9d_natural_loss",
                          "validate_e9d_physical_accounting",
                          "contract","E9D_SENDER_BYTES_OR_DELIVERIES_MISMATCH"))


if __name__=="__main__":
    unittest.main()

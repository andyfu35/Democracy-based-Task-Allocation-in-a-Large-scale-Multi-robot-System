"""E9F original paid Cost-copy causal study: data, bytes, pairing, provenance."""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from democracy_mrta.diagnostics import ProtocolError
from democracy_mrta.network import BernoulliLossSampler
from experiments.run_e9c_100seed_comms import capture_seed_information, create_seed_sampler
from experiments.run_e9d_natural_loss import run_e9d_democracy_loss_case
from experiments.run_e9f_cost_redundancy import (
    CBAA_ID, DEFAULT_COST_COPIES, DEFAULT_LOSSES,
    parse_e9f_cost_copy_grid, prepare_e9f_output_root,
    require_e9f_paired_sender_contract,
    run_e9f_cost_redundancy, run_e9f_democracy_cost_case,
    summarize_e9f_cost_study, validate_e9f_cost_grid,
    validate_e9f_sweep_axes,
)


class E9FCostStudyTests(unittest.TestCase):
    def fixture(self, root, *, seeds=2, copies=(1,2,3), losses=(0.0,0.5,1.0)):
        return dict(
            robots=5,tasks=3,seeds=seeds,first_seed=0,
            loss_probabilities=losses,cost_copies=copies,
            cbaa_safety_round_limit=15,democracy_safety_round_limit=20,
            latency_mode="constant",allow_download=False,
            output_root=root,
        )

    def run_small(self, **kwargs):
        with patch(
            "experiments.run_e9f_cost_redundancy.read_retirement_revision",
            return_value="e9f-test-source",
        ):
            return run_e9f_cost_redundancy(**kwargs)

    def test_original_paired_methods_and_exact_sender_cost_packets(self):
        with tempfile.TemporaryDirectory() as tmp:
            rows=self.run_small(**self.fixture(Path(tmp)/"e9f_paired"))
            self.assertEqual(len(rows),2*3*4)
            for seed in (0,1):
                for p in (0.0,0.5,1.0):
                    cell=tuple(r for r in rows if r["seed"]==seed
                               and r["loss_probability"]==p)
                    self.assertEqual(tuple(r["method"] for r in cell),
                                     ("democracy_cost_copies_1",
                                      "democracy_cost_copies_2",
                                      "democracy_cost_copies_3",CBAA_ID))
                    require_e9f_paired_sender_contract(
                        rows=cell,cost_copies=(1,2,3),
                        robots=5,tasks=3,seed=seed,
                        loss_probability=p,task_bytes=112,
                    )
                    for copies,row in zip((1,2,3),cell[:3]):
                        self.assertEqual(row["cost_sender_bytes"],copies*5*(16+24))
                        self.assertEqual(row["cost_packet_count"],copies*5)
                        self.assertEqual(row["cost_peer_delivery_attempts"],copies*20)
                        self.assertEqual(row["task_sender_bytes"],112)
                        self.assertEqual(row["vote_sender_bytes"]%32,0)
                        self.assertEqual(row["total_sender_bytes"],
                                         row["task_sender_bytes"]+row["coordination_sender_bytes"])
                    self.assertEqual(cell[3]["cost_sender_bytes"],0)
                    self.assertEqual(cell[3]["cost_packet_count"],0)
                    self.assertEqual(cell[3]["full_commit"],"")

    def test_one_copy_baseline_exact_E9D_scenario_parity(self):
        class Constant:
            def sample_ms(self,key):
                return 1.0
        cost_matrix=((1.0,9.0),(9.0,1.0),(5.0,5.0))
        common=dict(
            cost_rows=cost_matrix,task_bytes=112,task_packets=1,
            robots=3,tasks=2,seed=4,p_loss=0.35,profile=None,
            timeout_ms=10.0,
        )
        with patch("experiments.run_e9f_cost_redundancy.create_seed_sampler",
                   return_value=Constant()),patch(
                       "experiments.run_e9d_natural_loss.create_seed_sampler",
                       return_value=Constant()):
            newer=run_e9f_democracy_cost_case(**common,copies=1,democracy_guard=40)
            legacy=run_e9d_democracy_loss_case(**common,round_guard=40)
        for key in ("task_sender_bytes","cost_sender_bytes","vote_sender_bytes",
                    "score_sender_bytes","commit_sender_bytes",
                    "coordination_sender_bytes","total_sender_bytes",
                    "rounds_executed","elapsed_ms","tasks_confirmed","full_commit",
                    "coordination_delivered","coordination_dropped"):
            with self.subTest(key=key):
                self.assertEqual(newer[key],legacy[key])

    def test_zero_loss_and_total_loss_physical_cost_reach(self):
        with tempfile.TemporaryDirectory() as tmp:
            rows=self.run_small(**self.fixture(
                Path(tmp)/"e9f_loss_limits",seeds=1,copies=(1,3),
                losses=(0.0,1.0)))
            for row in rows:
                if row["method"]==CBAA_ID:
                    continue
                expected=1.0 if row["loss_probability"]==0 else 0.0
                self.assertEqual(row["initial_cost_peer_reach_fraction"],expected)
                self.assertEqual(row["initial_mean_visible_cost_rows"],
                                 5 if expected else 1)
                self.assertEqual(row["cost_peer_delivered_packets"],
                                 row["cost_peer_delivery_attempts"] if expected else 0)
                self.assertEqual(row["cost_packet_count"],5*row["cost_copies"])
            high_cbaa=next(r for r in rows if r["method"]==CBAA_ID
                           and r["loss_probability"]==1.0)
            self.assertEqual(high_cbaa["all_locally_certified"],0)
            self.assertEqual(high_cbaa["stop_reason"],"iteration_safety_guard")

    def test_summary_labels_commit_and_cbaa_local_certificate_separately(self):
        with tempfile.TemporaryDirectory() as tmp:
            rows=self.run_small(**self.fixture(Path(tmp)/"e9f_semantics",
                             seeds=2,copies=(1,2),losses=(0,0.5,1.0)))
            summary=summarize_e9f_cost_study(rows)
            self.assertEqual(len(summary),3*3)
            for row in summary:
                if row["method"]==CBAA_ID:
                    self.assertIn("local_receipt_certificate",
                                  row["complete_outcome_semantics"])
                    self.assertEqual(row["mean_initial_cost_peer_reach_fraction"],"")
                else:
                    self.assertEqual(row["complete_outcome_semantics"],
                                     "Democracy_actual_reliable_Commit")
                    self.assertTrue(0 <= row["mean_initial_cost_peer_reach_fraction"] <= 1)
            self.assertTrue(all(row["seeds"]==2 for row in summary))

    def test_source_manifest_exact_coverage_sha256_and_guard_disclosure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/"e9f_report"
            self.run_small(**self.fixture(root,seeds=2,copies=(1,2),
                                          losses=(0,0.5)))
            csv_path=root/"per_seed_cost_copy_method.csv"
            summary_path=root/"summary_cost_copies_by_loss.csv"
            manifest_path=root/"manifest.json"
            with csv_path.open(encoding="utf-8",newline="") as fd:
                raw=list(csv.DictReader(fd))
            with summary_path.open(encoding="utf-8",newline="") as fd:
                summary=list(csv.DictReader(fd))
            self.assertEqual(len(raw),2*2*3)
            self.assertEqual(len(summary),2*3)
            meta=json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(meta["source_git_sha"],"e9f-test-source")
            self.assertEqual(meta["cost_copies"],[1,2])
            self.assertEqual(meta["actual_raw_rows"],12)
            self.assertEqual(meta["expected_raw_rows"],12)
            self.assertTrue(meta["each_copy_physically_charged_even_if_receiver_drops"])
            self.assertTrue(meta["cbaa_natural_stop_not_fixed_K"])
            for path in (csv_path,summary_path):
                self.assertEqual(meta["sha256"][path.name],
                                 hashlib.sha256(path.read_bytes()).hexdigest())
            self.assertFalse((root/"per_seed_cost_copy_method.partial.csv").exists())

    def test_copy_grid_and_scenario_validation_first_failure(self):
        self.assertEqual(parse_e9f_cost_copy_grid("1,2,3,5"),DEFAULT_COST_COPIES)
        self.assertGreater(len(DEFAULT_LOSSES),20)
        for value in ("", "3,2,1", "1,1,2", "2,3", "1,foo", "1,6"):
            with self.subTest(value=value),self.assertRaises(ProtocolError):
                parse_e9f_cost_copy_grid(value)
        with self.assertRaises(ProtocolError) as cm:
            validate_e9f_cost_grid((2,3))
        d=cm.exception.diagnostic
        self.assertEqual((d.owner,d.function,d.category,d.code),(
            "experiments.run_e9f_cost_redundancy",
            "validate_e9f_cost_grid","data","E9F_INVALID_COST_GRID"
        ))
        with self.assertRaises(ProtocolError) as cm:
            validate_e9f_sweep_axes(
                robots=1,tasks=1,seeds=2,first_seed=0,
                losses=(0.0,0.5),cost_copies=(1,2),
                cbaa_guard=20,democracy_guard=20,latency_mode="constant",
            )
        self.assertEqual(cm.exception.diagnostic.code,
                         "E9F_ROBOTS_REQUIRE_PEER_RECEIPTS")

    def test_protected_or_reused_result_roots_never_overwrite(self):
        for root in (Path("results"),Path("results/e9d_formal"),
                     Path("results/e9e_formal")):
            with self.subTest(root=root),self.assertRaises(ProtocolError) as cm:
                prepare_e9f_output_root(root)
            self.assertEqual(cm.exception.diagnostic.code,
                             "E9F_PROTECTED_OUTPUT_ROOT")
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/"e9f_once"
            self.run_small(**self.fixture(root,seeds=1,copies=(1,),
                                          losses=(0.0,)))
            with self.assertRaises(ProtocolError) as cm:
                self.run_small(**self.fixture(root,seeds=1,copies=(1,),
                                              losses=(0.0,)))
            self.assertEqual(cm.exception.diagnostic.code,"E9F_OUTPUT_EXISTS")

    def test_rogue_cbaa_method_and_bad_cost_bytes_are_contract_failures(self):
        with tempfile.TemporaryDirectory() as tmp:
            rows=self.run_small(**self.fixture(
                Path(tmp)/"e9f_tamper",seeds=1,copies=(1,),
                losses=(0.0,)))
            good=tuple(rows)
            wrong=tuple({**r,"method":"fake_pose_cbaa"} if r["method"]==CBAA_ID
                        else r for r in good)
            with self.assertRaises(ProtocolError) as cm:
                require_e9f_paired_sender_contract(
                    rows=wrong,cost_copies=(1,),robots=5,tasks=3,
                    seed=0,loss_probability=0.0,task_bytes=112)
            self.assertEqual(cm.exception.diagnostic.code,
                             "E9F_METHOD_PAIRING_MISMATCH")
            broken=tuple({**r,"cost_sender_bytes":123} if r["method"]!=CBAA_ID
                         else r for r in good)
            with self.assertRaises(ProtocolError) as cm:
                require_e9f_paired_sender_contract(
                    rows=broken,cost_copies=(1,),robots=5,tasks=3,
                    seed=0,loss_probability=0.0,task_bytes=112)
            self.assertEqual(cm.exception.diagnostic.code,
                             "E9F_PHYSICAL_SENDER_BYTES_MISMATCH")


if __name__=="__main__":
    unittest.main()

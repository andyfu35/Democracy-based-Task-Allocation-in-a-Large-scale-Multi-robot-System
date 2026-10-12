"""E9L baseline provenance/experiment gates and local modeled radio runner."""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from democracy_mrta.diagnostics import ProtocolError
from democracy_mrta.network import EmpiricalLatencyProfile,estimate_e9l_price_auction_stage_ms
from experiments.cbaa_baseline_registry import E9K_ZIP_SHA,load_pinned_e9k_paid_baseline
from experiments.run_e9l_price_auction import (
    validate_e9l_axes,validate_e9l_paired_scene,prepare_e9l_root,
    run_e9l,EPSILON_METERS,
)


def sample_profile():
    return EmpiricalLatencyProfile(
        source_repository="test/synthetic",source_commit="fixture",
        source_blob_sha="fixture",location="test",location_label="test",
        config="test",config_label="test",steady_start_s=0.0,steady_end_s=1.0,
        samples_ms=(5.0,7.0,9.0),
    )


class E9LRunnerTests(unittest.TestCase):
    def test_pinned_three_way_source_required_for_formal(self):
        with self.assertRaises(ProtocolError) as ctx:
            validate_e9l_axes(sizes=(5,10),seeds=100,first_seed=0,guard=160,
                              e9i_zip=None,e9j_zip=None,e9k_zip=None,
                              allow_unpaired_smoke=False)
        self.assertEqual(ctx.exception.diagnostic.code,"E9L_THREE_FROZEN_ARCHIVES_REQUIRED")
        with self.assertRaises(ProtocolError) as ctx:
            validate_e9l_axes(sizes=(100,),seeds=1,first_seed=0,guard=160,
                              e9i_zip=None,e9j_zip=None,e9k_zip=None,
                              allow_unpaired_smoke=True)
        self.assertEqual(ctx.exception.diagnostic.code,"E9L_SMOKE_REQUIRES_SMALL_UNPAIRED")
        self.assertEqual(EPSILON_METERS,10.0)

    def test_bad_e9k_archive_is_rejected_before_simulation(self):
        with tempfile.TemporaryDirectory() as d:
            bad=Path(d)/"bad.zip"
            bad.write_bytes(b"untrusted")
            with self.assertRaises(ProtocolError) as ctx:
                load_pinned_e9k_paid_baseline(archive=bad,sizes=(5,),
                                               seeds=1,first_seed=0)
        self.assertEqual(ctx.exception.diagnostic.code,"E9L_E9K_ZIP_SHA_MISMATCH")
        self.assertEqual(len(E9K_ZIP_SHA),64)

    def test_control_phase_window_native_28B_packet(self):
        p=sample_profile()
        small=estimate_e9l_price_auction_stage_ms(
            profile=p,robots=5,packet_bytes=28,reference_phy_mbps=144)
        large=estimate_e9l_price_auction_stage_ms(
            profile=p,robots=100,packet_bytes=28,reference_phy_mbps=144)
        self.assertGreater(small,9)
        self.assertGreater(large,small)
        with self.assertRaises(ProtocolError) as ctx:
            estimate_e9l_price_auction_stage_ms(
                profile=p,robots=5,packet_bytes=0,reference_phy_mbps=144)
        self.assertEqual(ctx.exception.diagnostic.code,"E9L_INVALID_PRICE_WAVE")

    def test_paired_scene_cannot_silently_invent_missing_archive(self):
        with self.assertRaises(ProtocolError) as ctx:
            validate_e9l_paired_scene(e9i=None,e9j={"seed":1},e9k=None,
                                       n=5,seed=1,task_bytes=176,
                                       task_ms=3.0,oracle=10.0)
        self.assertEqual(ctx.exception.diagnostic.code,"E9L_PARTIAL_PAIR_INVALID")

    def test_actual_unpaired_small_local_runner(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)/"new"
            with (
                patch("experiments.run_e9l_price_auction.ensure_rady_dataset",
                      return_value=Path(d)/"synthetic.json"),
                patch("experiments.run_e9l_price_auction.load_rady_latency_profile",
                      return_value=sample_profile()),
                patch("experiments.run_e9l_price_auction.subprocess.check_output",
                      return_value="f"*40),
            ):
                rows=run_e9l(sizes=(5,10),seeds=1,first_seed=0,guard=160,
                             dataset=Path(d)/"synthetic.json",root=root,
                             allow_unpaired_smoke=True,allow_download=False)
            self.assertEqual(len(rows),2)
            for row in rows:
                self.assertEqual(row["total_original_sender_bytes"],
                                 row["original_TASK_sender_bytes"]+
                                 row["auction_sender_application_bytes"])
                self.assertEqual(row["native_receiver_opportunities"],
                                 row["bid_sender_SENDs"]+
                                 (row["N"]-1)*row["award_sender_SENDs"])
            meta=json.loads((root/"manifest.json").read_text())
            self.assertEqual(meta["status"],"UNPAIRED_SMOKE_ONLY")
            for name,digest in meta["source_file_sha256"].items():
                self.assertEqual(hashlib.sha256((root/name).read_bytes()).hexdigest(),digest)
            with (root/"summary_e9l.csv").open(newline="") as handle:
                self.assertEqual(len(list(csv.DictReader(handle))),2)
            with self.assertRaises(ProtocolError) as ctx:
                prepare_e9l_root(root)
            self.assertEqual(ctx.exception.diagnostic.code,"E9L_OUTPUT_EXISTS")

if __name__=="__main__": unittest.main()

"""E9K runner tests: evidence gates, sender ledgers, and real local smoke."""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from democracy_mrta.diagnostics import ProtocolError
from democracy_mrta.network import EmpiricalLatencyProfile
from democracy_mrta.scenario import generate_e0_scenario
from experiments.cbaa_baseline_registry import (
    E9J_ZIP_SHA256, load_pinned_e9j_cbaa_baseline,
)
from experiments.run_e9k_paid_cbaa import (
    validate_e9k_axes, run_e9k_paid_case, run_e9k, prepare_e9k_output,
)


def sample_profile():
    return EmpiricalLatencyProfile(
        source_repository="test/synthetic",source_commit="fixture",
        source_blob_sha="fixture",location="test",location_label="test",
        config="test",config_label="test",
        steady_start_s=0.0,steady_end_s=1.0,
        samples_ms=(5.0,7.0,9.0),
    )


class E9KRunnerTests(unittest.TestCase):
    def test_formal_both_original_archives_required(self):
        with self.assertRaises(ProtocolError) as err:
            validate_e9k_axes(
                sizes=(5,10),seeds=100,first_seed=0,guard=160,
                e9i_zip=None,e9j_zip=None,allow_unpaired_smoke=False,
            )
        self.assertEqual(err.exception.diagnostic.code,
                         "E9K_BOTH_PINNED_BASELINES_REQUIRED")
        with self.assertRaises(ProtocolError) as err:
            validate_e9k_axes(
                sizes=(5,10),seeds=4,first_seed=0,guard=160,
                e9i_zip=None,e9j_zip=None,allow_unpaired_smoke=True,
            )
        self.assertEqual(err.exception.diagnostic.code,
                         "E9K_SMOKE_WITH_BASELINE_OR_FORMAL_SIZE")

    def test_invalid_e9j_source_refused_not_fake_replayed(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive=Path(tmp)/"bad.zip"
            archive.write_bytes(b"this is not original E9J")
            with self.assertRaises(ProtocolError) as err:
                load_pinned_e9j_cbaa_baseline(
                    archive=archive,sizes=(5,),seeds=1,first_seed=0,
                )
            self.assertEqual(err.exception.diagnostic.code,
                             "E9K_E9J_ZIP_SHA_MISMATCH")
            self.assertEqual(len(E9J_ZIP_SHA256),64)

    def test_real_native_cbaa_plus_paid_control_sender_ledger(self):
        n=5
        row=run_e9k_paid_case(
            scenario=generate_e0_scenario(1,n,n),
            profile=sample_profile(),seed=1,n=n,guard=50,
        )
        self.assertEqual(row["method"],
                         "cbaa_original_auction_plus_paid_ready_commit")
        self.assertEqual(
            row["native_bid_sender_SENDs"],
            n*row["iterations_including_paid_finalization"],
        )
        self.assertEqual(
            row["paid_control_sender_bytes"],
            48*(row["paid_ready_sender_SENDs"]+
                row["paid_commit_sender_SENDs"]),
        )
        self.assertEqual(
            row["full_physical_sender_bytes"],
            row["original_TASK_sender_bytes"]+
            row["native_bid_sender_bytes"]+
            row["paid_control_sender_bytes"],
        )
        self.assertEqual(row["paid_control_receiver_attempts"],
                         (n-1)*(row["paid_ready_sender_SENDs"]+
                                row["paid_commit_sender_SENDs"]))
        self.assertGreater(row["paid_control_sender_bytes"],0)

    def test_actual_unpaired_smoke_writes_nonformal_manifest(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)/"smoke"
            with (
                patch("experiments.run_e9k_paid_cbaa.ensure_rady_dataset",
                      return_value=Path(d)/"fixture.json"),
                patch("experiments.run_e9k_paid_cbaa.load_rady_latency_profile",
                      return_value=sample_profile()),
                patch("experiments.run_e9k_paid_cbaa.subprocess.check_output",
                      return_value="f"*40),
            ):
                rows=run_e9k(
                    sizes=(5,),seeds=1,first_seed=0,guard=50,
                    dataset=Path(d)/"fixture.json",root=root,
                    allow_unpaired_smoke=True,allow_download=False,
                )
            self.assertEqual(len(rows),1)
            manifest=json.loads((root/"manifest.json").read_text())
            self.assertEqual(manifest["status"],"UNPAIRED_SMOKE_ONLY")
            for file,digest in manifest["user_original_files_sha256"].items():
                self.assertEqual(
                    hashlib.sha256((root/file).read_bytes()).hexdigest(),
                    digest,
                )
            self.assertFalse((root/"per_seed_e9k.partial.csv").exists())
            summary=list(csv.DictReader(
                (root/"summary_e9k.csv").open(newline=""),
            ))
            self.assertEqual(len(summary),1)
            self.assertEqual(summary[0]["N"],"5")
            with self.assertRaises(ProtocolError) as err:
                prepare_e9k_output(root)
            self.assertEqual(err.exception.diagnostic.code,"E9K_OUTPUT_EXISTS")


if __name__=="__main__":
    unittest.main()

"""E9J: native CBAA sender/clock and immutable original E9I source gates."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from democracy_mrta.diagnostics import ProtocolError
from democracy_mrta.network import (
    EmpiricalLatencyProfile, estimate_e9j_cbaa_consensus_window_ms,
)
from democracy_mrta.scenario import generate_e0_scenario
from experiments.run_e9j_cbaa_vs_e9i import (
    BASE_ZIP_SHA, BASE_GIT_SHA, CBAA_BID_LOSS,
    validate_e9j_axes, load_e9j_pinned_e9i_baseline,
    run_e9j_original_cbaa_case, run_e9j_cbaa_vs_e9i,
    pair_e9j_against_e9i, summarize_e9j_comparison, prepare_e9j_root,
)


def example_profile() -> EmpiricalLatencyProfile:
    return EmpiricalLatencyProfile(
        source_repository="test/synthetic", source_commit="fixture",
        source_blob_sha="fixture", location="test", location_label="test",
        config="test", config_label="test",
        steady_start_s=0.0, steady_end_s=1.0,
        samples_ms=(5.0, 7.0, 9.0),
    )


class E9JNativeCBAATests(unittest.TestCase):
    def test_cbaa_vector_wave_matches_N_and_packet_size(self):
        p=example_profile()
        d5=estimate_e9j_cbaa_consensus_window_ms(
            profile=p,robots=5,tasks=5,reference_phy_mbps=144.0)
        d100=estimate_e9j_cbaa_consensus_window_ms(
            profile=p,robots=100,tasks=100,reference_phy_mbps=144.0)
        self.assertGreater(d5,9.0)
        self.assertGreater(d100,d5)
        with self.assertRaises(ProtocolError) as error:
            estimate_e9j_cbaa_consensus_window_ms(
                profile=p,robots=5,tasks=6,reference_phy_mbps=144.0)
        self.assertEqual(error.exception.diagnostic.code,"E9J_INVALID_CBAA_WAVE_INPUT")

    def test_hard_pinned_E9I_baseline_required_for_formal(self):
        with self.assertRaises(ProtocolError) as error:
            validate_e9j_axes(sizes=(5,10),seeds=10,first_seed=0,
                guard=160,baseline_zip=None,allow_unpaired_smoke=False)
        self.assertEqual(error.exception.diagnostic.code,
                         "E9J_BASELINE_REQUIRED_FOR_FORMAL_COMPARISON")
        validate_e9j_axes(sizes=(5,10),seeds=2,first_seed=0,
                          guard=40,baseline_zip=None,
                          allow_unpaired_smoke=True)
        self.assertEqual(len(BASE_ZIP_SHA),64)
        self.assertEqual(len(BASE_GIT_SHA),40)
        self.assertEqual(CBAA_BID_LOSS,.30)

    def test_wrong_zip_is_provenance_failure_not_fallback(self):
        with tempfile.TemporaryDirectory() as d:
            bad=Path(d)/"bad.zip"
            bad.write_bytes(b"incorrect-source")
            with self.assertRaises(ProtocolError) as error:
                load_e9j_pinned_e9i_baseline(
                    archive=bad,sizes=(5,),seeds=1,first_seed=0)
            self.assertEqual(error.exception.diagnostic.code,
                             "E9J_BASELINE_ARCHIVE_SHA_MISMATCH")

    def test_original_cbaa_real_sender_vector_and_network(self):
        scenario=generate_e0_scenario(1,5,5)
        p=example_profile()
        deadline=estimate_e9j_cbaa_consensus_window_ms(
            profile=p,robots=5,tasks=5,reference_phy_mbps=144.0)
        out=run_e9j_original_cbaa_case(
            scenario=scenario,profile=p,seed=1,n=5,guard=40,
            phase_deadline_ms=deadline,oracle_cost=1.0)
        self.assertGreater(out["cbaa_iterations"],0)
        self.assertEqual(out["total_original_SENDs"],
                         out["cbaa_iterations"]*5+1)
        self.assertEqual(out["cbaa_bid_sender_bytes"],
                         out["cbaa_iterations"]*5*(16+12*5))
        self.assertEqual(out["cbaa_receiver_delivery_attempts"],
                         5*4*out["cbaa_iterations"])
        self.assertGreater(out["modeled_airtime_ms"],0)
        self.assertGreater(out["total_original_sender_bytes"],
                           out["cbaa_bid_sender_bytes"])
        self.assertNotIn(out["cbaa_stop_reason"],("",None))

    def test_paired_original_e9i_rows_are_read_only(self):
        scenario=generate_e0_scenario(2,5,5)
        p=example_profile()
        out=run_e9j_original_cbaa_case(
            scenario=scenario,profile=p,seed=2,n=5,guard=20,
            phase_deadline_ms=estimate_e9j_cbaa_consensus_window_ms(
                profile=p,robots=5,tasks=5,reference_phy_mbps=144.0),
            oracle_cost=1.0)
        row={"full_commit":"1","successful_allocation_ms":"2000",
             "allocation_or_stop_ms":"2000","total_sender_application_bytes":"1200",
             "total_original_send_count":"26","total_airtime_ms":"2.5",
             "total_cost_over_hungarian_ratio":"1.34"}
        baseline={
            (5,2,vote,arm):dict(row)
            for vote in (0.0,.30)
            for arm in ("fixed_received","adaptive_guarded_k1_received")
        }
        paired=pair_e9j_against_e9i(rows=[out],baseline=baseline)
        self.assertEqual(len(paired),4)
        self.assertEqual(len(summarize_e9j_comparison(paired)),4)
        self.assertTrue(all(x["Voting_full_commit"]==1 for x in paired))
        self.assertTrue(all(x["CBAA_sender_SENDs"]==out["total_original_SENDs"]
                            for x in paired))
        self.assertTrue(all(x["not_equivalent_success_protocols"] for x in paired))

    def test_actual_unpaired_cbaa_smoke_has_verified_original_hashes(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)/"cbaa"
            with (
                patch("experiments.run_e9j_cbaa_vs_e9i.ensure_rady_dataset",
                      return_value=Path(d)/"pinned_fixture.json"),
                patch("experiments.run_e9j_cbaa_vs_e9i.load_rady_latency_profile",
                      return_value=example_profile()),
                patch("experiments.run_e9j_cbaa_vs_e9i.subprocess.check_output",
                      return_value="c"*40),
            ):
                rows=run_e9j_cbaa_vs_e9i(
                    sizes=(5,10),seeds=1,first_seed=0,guard=35,
                    dataset=Path(d)/"pinned_fixture.json",
                    output_root=root,baseline_zip=None,
                    allow_unpaired_smoke=True,allow_download=False)
            self.assertEqual(len(rows),2)
            manifest=json.loads((root/"manifest.json").read_text())
            self.assertEqual(manifest["result_status"],"UNPAIRED_SMOKE_ONLY")
            self.assertEqual(manifest["cbaa_original_cases"],2)
            for name,digest in manifest["sha256_source_files"].items():
                self.assertEqual(hashlib.sha256((root/name).read_bytes()).hexdigest(),digest)
            self.assertFalse((root/"per_seed_original_cbaa.partial.csv").exists())
            with self.assertRaises(ProtocolError) as error:
                prepare_e9j_root(root)
            self.assertEqual(error.exception.diagnostic.code,"E9J_OUTPUT_EXISTS")


if __name__=="__main__":
    unittest.main()

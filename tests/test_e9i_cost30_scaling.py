"""E9I fixed Cost 30% with independent Vote 0/30 original Voting tests."""
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
from experiments.run_e9i_cost30_scaling import (
    COST_LOSS,VOTE_GRID,MAIN_ARMS,
    validate_e9i_cost30_axes,prepare_e9i_output,
    selected_e9i_arms,run_e9i_cost30_scaling,
    summarize_e9i_scaling,
)


def profile_fixture()->EmpiricalLatencyProfile:
    return EmpiricalLatencyProfile(
        source_repository="test/synthetic",source_commit="synthetic",
        source_blob_sha="synthetic",location="test",location_label="synthetic",
        config="test",config_label="synthetic",
        steady_start_s=0.0,steady_end_s=1.0,
        samples_ms=(5.0,7.0,9.0),
    )


class E9ICost30OriginalVotingTests(unittest.TestCase):
    def test_cost30_and_vote_pair_are_fixed_and_not_duplicated(self):
        self.assertEqual(COST_LOSS,0.30)
        self.assertEqual(VOTE_GRID,(0.0,0.30))
        self.assertEqual(tuple(a[0] for a in selected_e9i_arms()),MAIN_ARMS)
        validate_e9i_cost30_axes(
            sizes=(5,10),seeds=5,first_seed=0,max_rounds=300,
            rate_mbps=144.,design_rate_mbps=144.,vote_losses=VOTE_GRID,
        )
        with self.assertRaises(ProtocolError) as err:
            validate_e9i_cost30_axes(
                sizes=(5,10),seeds=5,first_seed=0,max_rounds=300,
                rate_mbps=144.,design_rate_mbps=144.,vote_losses=(0.30,),
            )
        self.assertEqual(err.exception.diagnostic.owner,
                         "experiments.run_e9i_cost30_scaling")
        self.assertEqual(err.exception.diagnostic.category,"data")
        self.assertEqual(err.exception.diagnostic.code,
                         "E9I_VOTE_LOSS_PAIR_NOT_FROZEN")

    def test_original_runner_and_evidence_have_paired_cost_source(self):
        with tempfile.TemporaryDirectory() as temp:
            dest=Path(temp)/"new"
            with (
                patch("experiments.run_e9i_cost30_scaling.ensure_rady_dataset",
                      return_value=Path(temp)/"synthetic_rady.json"),
                patch("experiments.run_e9i_cost30_scaling.load_rady_latency_profile",
                      return_value=profile_fixture()),
                patch("experiments.run_e9i_cost30_scaling.subprocess.check_output",
                      return_value="c"*40),
            ):
                rows=run_e9i_cost30_scaling(
                    sizes=(3,5),seeds=2,first_seed=0,max_rounds=20,
                    dataset=Path(temp)/"synthetic_rady.json",
                    output_root=dest,rate_mbps=144.,design_rate_mbps=144.,
                    include_rady=True,allow_download=False,
                )
            self.assertEqual(len(rows),2*2*2*2*4)
            manifest=json.loads((dest/"manifest.json").read_text())
            self.assertEqual(manifest["raw_cases"],len(rows))
            self.assertEqual(manifest["source_git_sha"],"c"*40)
            self.assertEqual(manifest["cost_loss_probability_fixed"],0.30)
            self.assertEqual(manifest["vote_loss_probabilities_paired"],[0.0,0.3])
            self.assertFalse(manifest["full_phy_mac_80211ax_ofdma"])
            for filename,digest in manifest["source_files_sha256"].items():
                self.assertEqual(hashlib.sha256((dest/filename).read_bytes()).hexdigest(),digest)
            with (dest/"per_seed_e9i_cost30.csv").open() as f:
                self.assertEqual(len(list(csv.DictReader(f))),len(rows))
            self.assertFalse((dest/"per_seed_e9i_cost30.partial.csv").exists())
            for n in (3,5):
                for seed in (0,1):
                    for model in ("rady_bootstrap_no_shared_channel",
                                  "e9g_shared_medium_backoff_proxy"):
                        matched=[
                            x for x in rows if
                            x["robots"]==n and x["seed"]==seed
                            and x["model"]==model
                        ]
                        self.assertEqual(len(matched),8)
                        self.assertEqual({x["cost_loss_probability"] for x in matched},
                                         {0.3})
                        self.assertEqual({x["vote_loss_probability"] for x in matched},
                                         {0.,0.3})
                        self.assertEqual(
                            {x["cost_remote_packet_drop_count"] for x in matched},
                            {matched[0]["cost_remote_packet_drop_count"]}
                        )
                        self.assertTrue(all(
                            0.0<=x["cost_effective_peer_view_fraction"]<=1.0
                            and x["cost_remote_receiver_observation_count"]==n*(n-1)
                            for x in matched
                        ))
            overview=summarize_e9i_scaling(rows)
            self.assertEqual(len(overview),2*2*2*4)
            self.assertTrue(all(x["seeds"]==2 and 0<=x["full_commit_rate"]<=1
                                for x in overview))
            with self.assertRaises(ProtocolError) as err:
                prepare_e9i_output(dest)
            self.assertEqual(err.exception.diagnostic.code,"E9I_OUTPUT_EXISTS")


if __name__=="__main__":
    unittest.main()

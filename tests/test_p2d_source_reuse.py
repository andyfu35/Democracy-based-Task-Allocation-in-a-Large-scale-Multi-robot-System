"""P2D source identity and composition: never silently relabel old auction."""
import unittest
from pathlib import Path
from democracy_mrta.diagnostics import ProtocolError
from experiments.p2_baseline_reuse import (
    read_verified_p2c_voting, merge_p2d_paired_evidence,
)


class P2DSourceTests(unittest.TestCase):
    def test_requires_original_p2c_archive(self):
        with self.assertRaises(ProtocolError) as err:
            read_verified_p2c_voting(
                Path("/does-not-exist/p2c_global_greedy_100seed.zip"),
                (0,), 0, 1,
            )
        self.assertEqual(err.exception.diagnostic.owner, "experiments.p2_baseline_reuse")
        self.assertEqual(err.exception.diagnostic.category, "dependency")

    def test_merge_rejects_missing_native_comparator(self):
        with self.assertRaises(ProtocolError) as err:
            merge_p2d_paired_evidence(
                voting_rows=[], native_baselines=[], centralized_rows=[],
                percentages=(0,), first_seed=0, seeds=1,
                centralized_source_sha="f"*40,
            )
        self.assertEqual(err.exception.diagnostic.category, "contract")

    def test_merge_excludes_auction_and_retains_fields(self):
        common = {"loss_percent":0,"seed":0,"scene_sha256":"same",
                  "native_stop_ms":1.25,"native_sender_bytes":100,
                  "native_success":1,"final_feasible":1}
        voting=[{**common,"method":"voting"}]
        external=[{**common,"method":method} for method in ("cbaa","cbba")]
        central=[{**common,"method":"centralized"}]
        merged=merge_p2d_paired_evidence(
            voting_rows=voting, native_baselines=external,
            centralized_rows=central, percentages=(0,),
            first_seed=0, seeds=1, centralized_source_sha="f"*40,
        )
        self.assertEqual({x["method"] for x in merged},
                         {"voting","cbaa","cbba","centralized"})
        self.assertEqual(merged[0]["native_stop_ms"], 1.25)
        self.assertEqual(len(merged),4)


if __name__ == "__main__":
    unittest.main()

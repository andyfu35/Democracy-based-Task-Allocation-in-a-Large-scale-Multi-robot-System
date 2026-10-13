"""P2-B reuses the original SHA-verified 3,000 baseline rows; no new baseline execution."""
from __future__ import annotations

import tempfile
from pathlib import Path
import unittest

from democracy_mrta.diagnostics import ProtocolError
from experiments.p2_baseline_reuse import (
    BASELINE_METHODS, COMPARISON_METHODS, ORIGINAL_GIT_SHA,
    merge_paired_baseline_evidence, read_verified_original_baselines,
)
from experiments.run_p2_packet_loss import validate_complete_grid, summarize


def sample(p: int, seed: int, method: str):
    return {
        "loss_percent": p, "seed": seed, "method": method,
        "robots": 100, "tasks": 100, "capacity": 1,
        "p_loss": p / 100, "scene_sha256": f"scene-{seed}",
        "native_success": int(not (p == 90 and method == "price_auction")),
        "final_feasible": int(not (p == 90 and method == "price_auction")),
        "first_feasible_seen": 1, "native_guard_censored": int(p == 90 and method == "price_auction"),
        "native_diagnostic": "", "native_stop_ms": 2000 if method == "voting" else 8000,
        "native_sender_bytes": 512 if method == "voting" else 2048,
        "final_hungarian_ratio": 1.02, "method_contract": "original",
    }


class BaselineReuseTests(unittest.TestCase):
    def test_new_voting_and_old_baselines_are_paired_and_provenanced(self):
        losses = (0, 90)
        new_sha = "a" * 40
        fresh = [sample(p, seed, "voting") for p in losses for seed in range(100)]
        old = [sample(p, seed, method) for p in losses for seed in range(100)
               for method in BASELINE_METHODS]
        combined = merge_paired_baseline_evidence(fresh, old, losses, 0, 100, new_sha)
        validate_complete_grid(combined, losses, 0, 100, methods=COMPARISON_METHODS)
        self.assertEqual(len(combined), 800)
        self.assertEqual(sum(r["source_role"] == "new_batched_voting" for r in combined), 200)
        self.assertEqual(sum(r["source_role"] == "verified_reused_baseline" for r in combined), 600)
        self.assertEqual({r["source_git_sha"] for r in combined if r["method"] == "voting"}, {new_sha})
        self.assertEqual({r["source_git_sha"] for r in combined if r["method"] != "voting"}, {ORIGINAL_GIT_SHA})
        values = summarize(combined, losses)
        self.assertEqual(len(values), 8)
        self.assertEqual([r["same_four_success_seeds"] for r in values if r["loss_percent"] == 90],
                         [0, 0, 0, 0])

    def test_missing_and_unverified_archive_never_trigger_baseline_execution(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "original.zip"
            with self.assertRaises(ProtocolError) as cm:
                read_verified_original_baselines(p, (0,), 0, 1)
            self.assertEqual(cm.exception.diagnostic.code, "P2_BASELINE_ZIP_NOT_FOUND")
            p.write_bytes(b"not the SHA-verified original P2 archive")
            with self.assertRaises(ProtocolError) as cm:
                read_verified_original_baselines(p, (0,), 0, 1)
            self.assertEqual(cm.exception.diagnostic.code, "P2_BASELINE_ZIP_SHA_MISMATCH")

    def test_duplicate_method_or_different_geometry_fails_first_owner(self):
        fresh = [sample(0, 0, "voting")]
        baseline = [sample(0, 0, method) for method in BASELINE_METHODS]
        baseline[0]["scene_sha256"] = "different"
        with self.assertRaises(ProtocolError) as cm:
            merge_paired_baseline_evidence(fresh, baseline, (0,), 0, 1, "b" * 40)
        self.assertEqual(cm.exception.diagnostic.code, "P2_COMBINED_SEED_SCENE_MISMATCH")
        baseline[0]["scene_sha256"] = fresh[0]["scene_sha256"]
        with self.assertRaises(ProtocolError) as cm:
            merge_paired_baseline_evidence(fresh + fresh, baseline, (0,), 0, 1, "b" * 40)
        self.assertEqual(cm.exception.diagnostic.code, "P2_COMBINED_SOURCE_GRID_MISMATCH")


if __name__ == "__main__":
    unittest.main()

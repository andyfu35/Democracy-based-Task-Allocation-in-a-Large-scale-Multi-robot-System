"""E9E: dense controlled p grid, no original election/bidding changes."""
from __future__ import annotations

import unittest

from democracy_mrta.diagnostics import ProtocolError
from experiments.run_e9d_natural_loss import (
    DEFAULT_GRID,
    resolve_e9d_loss_grid_profile,
    validate_e9d_natural_loss_axes,
)


class E9EDenseGridTests(unittest.TestCase):
    def get(self, profile, explicit=None):
        return resolve_e9d_loss_grid_profile(
            profile=profile, explicit_losses=explicit,
        )

    def test_legacy_default_preserves_original_grid(self):
        self.assertEqual(self.get("legacy"), DEFAULT_GRID)
        chosen=(0.0,0.31,0.65)
        self.assertEqual(self.get("legacy",chosen),chosen)

    def test_dense_union_has_one_percent_near_both_transitions(self):
        grid=self.get("dense")
        self.assertEqual(len(grid),52)
        self.assertEqual(grid[0],0.0)
        self.assertEqual(grid[-1],0.99)
        self.assertEqual(grid,tuple(sorted(set(grid))))
        self.assertTrue(all(round(x*100,6)==round(x*100) for x in grid))
        for expected in (0.01,0.30,0.40,0.47,0.51,0.57,0.60,0.65,
                         0.70,0.85,0.91,0.94,0.95,0.98,0.99):
            with self.subTest(expected=expected):
                if expected == 0.01:
                    self.assertNotIn(expected,grid)
                else:
                    self.assertIn(expected,grid)

    def test_focused_transition_and_tail_profiles_are_exact(self):
        baseline=set(round(x/100,2) for x in range(0,100,5))
        transition=self.get("transition")
        tail=self.get("tail")
        self.assertEqual(len(transition),40)
        self.assertEqual(len(tail),32)
        self.assertEqual(set(transition),
                         baseline.union(x/100 for x in range(40,66)))
        self.assertEqual(set(tail),
                         baseline.union(x/100 for x in range(85,100)))

    def test_profile_explicit_conflict_fails_first_data_boundary(self):
        with self.assertRaises(ProtocolError) as cm:
            self.get("dense",(0.0,0.5))
        d=cm.exception.diagnostic
        self.assertEqual((d.owner,d.function,d.category,d.code),(
            "experiments.run_e9d_natural_loss",
            "resolve_e9d_loss_grid_profile",
            "data","E9D_CONFLICTING_LOSS_GRID_CHOICES",
        ))

    def test_unknown_profile_fails_first_data_boundary(self):
        with self.assertRaises(ProtocolError) as cm:
            self.get("magic")
        d=cm.exception.diagnostic
        self.assertEqual((d.owner,d.function,d.category,d.code),(
            "experiments.run_e9d_natural_loss",
            "resolve_e9d_loss_grid_profile",
            "data","E9D_UNKNOWN_LOSS_GRID_PROFILE",
        ))

    def test_selected_grids_match_existing_canonical_validation(self):
        for kind in ("legacy","transition","tail","dense"):
            with self.subTest(kind=kind):
                validate_e9d_natural_loss_axes(
                    robots=100,tasks=50,seeds=100,first_seed=0,
                    losses=self.get(kind),
                    cbaa_safety_round_limit=160,
                    democracy_safety_round_limit=300,
                    latency_mode="constant",
                )


if __name__=="__main__":
    unittest.main()

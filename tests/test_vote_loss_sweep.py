from __future__ import annotations

import csv
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from democracy_mrta.diagnostics import ProtocolError
from experiments.run_e2_retirement import (
    build_retirement_loss_conditions,
    resolve_retirement_vote_loss_axis,
    run_retirement_experiment,
)


class FixedLatency:
    def sample_ms(self, key: str) -> float:
        return 10.0


class VoteLossSweepTests(unittest.TestCase):
    def test_original_cost_only_axis_is_unchanged(self) -> None:
        votes = resolve_retirement_vote_loss_axis(
            cost_losses=(0.0, 0.3),
            fixed_vote_loss=0.0,
            vote_loss_sweep=None,
            loss_pairing="grid",
        )
        conditions = build_retirement_loss_conditions(
            cost_losses=(0.0, 0.3), vote_losses=votes, pairing="grid",
        )
        self.assertEqual(conditions, ((0.0, 0.0), (0.3, 0.0)))

    def test_vote_only_sweep_holds_cost_loss_constant(self) -> None:
        conditions = build_retirement_loss_conditions(
            cost_losses=(0.0,),
            vote_losses=(0.0, 0.02, 0.30, 0.70),
            pairing="grid",
        )
        self.assertEqual(
            conditions,
            ((0.0, 0.0), (0.0, 0.02), (0.0, 0.30), (0.0, 0.70)),
        )

    def test_fixed_30_percent_cost_loss_with_vote_axis(self) -> None:
        conditions = build_retirement_loss_conditions(
            cost_losses=(0.3,),
            vote_losses=(0.0, 0.3, 0.6),
            pairing="grid",
        )
        self.assertEqual(
            conditions, ((0.3, 0.0), (0.3, 0.3), (0.3, 0.6))
        )

    def test_diagonal_selects_only_equal_cost_and_vote_loss(self) -> None:
        costs = (0.0, 0.3, 0.7)
        votes = resolve_retirement_vote_loss_axis(
            cost_losses=costs,
            fixed_vote_loss=None,
            vote_loss_sweep=None,
            loss_pairing="diagonal",
        )
        self.assertEqual(votes, costs)
        self.assertEqual(
            build_retirement_loss_conditions(
                cost_losses=costs, vote_losses=votes, pairing="diagonal"
            ),
            ((0.0, 0.0), (0.3, 0.3), (0.7, 0.7)),
        )

    def test_full_grid_uses_every_unique_pair(self) -> None:
        conditions = build_retirement_loss_conditions(
            cost_losses=(0.0, 0.3),
            vote_losses=(0.0, 0.3, 0.7),
            pairing="grid",
        )
        self.assertEqual(len(conditions), 6)
        self.assertEqual(conditions[0], (0.0, 0.0))
        self.assertEqual(conditions[-1], (0.3, 0.7))
        self.assertEqual(len(set(conditions)), 6)

    def test_diagonal_rejects_non_equal_axes(self) -> None:
        with self.assertRaises(ProtocolError) as context:
            build_retirement_loss_conditions(
                cost_losses=(0.0, 0.3),
                vote_losses=(0.0, 0.5),
                pairing="diagonal",
            )
        self.assertEqual(
            context.exception.diagnostic.code,
            "DIAGONAL_LOSS_AXES_DIFFER",
        )

    def test_diagonal_cannot_override_fixed_vote_probability(self) -> None:
        with self.assertRaises(ProtocolError) as context:
            resolve_retirement_vote_loss_axis(
                cost_losses=(0.0, 0.3),
                fixed_vote_loss=0.0,
                vote_loss_sweep=None,
                loss_pairing="diagonal",
            )
        self.assertEqual(
            context.exception.diagnostic.code,
            "DIAGONAL_WITH_FIXED_VOTE_LOSS",
        )

    def test_duplicate_and_empty_axis_are_rejected(self) -> None:
        for cost, votes, expected in (
            ((), (0.0,), "EMPTY_PACKET_LOSS_SWEEP"),
            ((0.0,), (), "EMPTY_PACKET_LOSS_SWEEP"),
            ((0.0, 0.0), (0.3,), "DUPLICATE_PACKET_LOSS_CONDITION"),
            ((0.0,), (0.3, 0.3), "DUPLICATE_PACKET_LOSS_CONDITION"),
        ):
            with self.subTest(cost=cost, vote=votes):
                with self.assertRaises(ProtocolError) as context:
                    build_retirement_loss_conditions(
                        cost_losses=cost, vote_losses=votes, pairing="grid"
                    )
                self.assertEqual(context.exception.diagnostic.code, expected)

    def test_invalid_vote_probability_is_rejected(self) -> None:
        with self.assertRaises(ProtocolError) as context:
            build_retirement_loss_conditions(
                cost_losses=(0.0,), vote_losses=(1.1,), pairing="grid"
            )
        self.assertEqual(
            context.exception.diagnostic.code,
            "INVALID_PACKET_LOSS_PROBABILITY",
        )

    def test_runner_uses_both_axes_and_replays_paired_seeds(self) -> None:
        costs = ((1.0,), (2.0,), (3.0,))
        with tempfile.TemporaryDirectory() as root:
            output_root = Path(root) / "vote_grid"
            with (
                patch(
                    "experiments.run_e2_retirement.ensure_rady_dataset",
                    return_value=Path(root) / "unused.json",
                ),
                patch(
                    "experiments.run_e2_retirement.load_rady_latency_profile",
                    return_value=object(),
                ),
                patch(
                    "experiments.run_e2_retirement.summarize_latency_profile",
                    return_value={"max_ms": 10.0},
                ),
                patch(
                    "experiments.run_e2_retirement.EmpiricalLatencySampler",
                    side_effect=lambda *args, **kwargs: FixedLatency(),
                ),
                patch(
                    "experiments.run_e2_retirement.generate_e0_scenario",
                    side_effect=lambda *args, **kwargs: SimpleNamespace(cost_matrix=costs),
                ),
                patch(
                    "experiments.run_e2_retirement.read_retirement_revision",
                    return_value="vote-loss-sweep-test-sha",
                ),
            ):
                summary = run_retirement_experiment(
                    robots=3,
                    tasks=1,
                    seeds=2,
                    cost_losses=(0.0, 0.3),
                    p_vote_loss=0.0,
                    vote_losses=(0.0, 1.0),
                    loss_pairing="grid",
                    max_rounds=2,
                    dataset_path=Path(root) / "unused.json",
                    output_root=output_root,
                    allow_download=False,
                )

            self.assertEqual(len(summary), 4)
            self.assertEqual(
                {(r["p_cost_loss"], r["p_vote_loss"]) for r in summary},
                {(0.0, 0.0), (0.0, 1.0), (0.3, 0.0), (0.3, 1.0)},
            )
            self.assertTrue(all(r["seeds"] == 2 for r in summary))
            baseline = next(
                r for r in summary
                if r["p_cost_loss"] == 0.0 and r["p_vote_loss"] == 0.0
            )
            full_vote_blackout = next(
                r for r in summary
                if r["p_cost_loss"] == 0.0 and r["p_vote_loss"] == 1.0
            )
            self.assertEqual(baseline["full_assignment_success_rate"], 1.0)
            self.assertEqual(baseline["observed_vote_drop_rate"], 0.0)
            self.assertEqual(full_vote_blackout["full_assignment_success_rate"], 0.0)
            self.assertEqual(full_vote_blackout["observed_vote_drop_rate"], 1.0)
            self.assertEqual(full_vote_blackout["observed_cost_drop_rate"], 0.0)
            self.assertEqual(full_vote_blackout["mean_quorum_failed_attempts"], 2.0)
            self.assertEqual(full_vote_blackout["mean_self_votes"], 2.0)

            raw_files = list((output_root / "raw").glob("retirement_*.csv"))
            self.assertEqual(len(raw_files), 1)
            with raw_files[0].open(newline="", encoding="utf-8") as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual(len(rows), 8)
            self.assertTrue(all(
                row["git_sha"] == "vote-loss-sweep-test-sha" for row in rows
            ))
            self.assertEqual(len({
                (row["seed"], row["p_cost_loss"], row["p_vote_loss"])
                for row in rows
            }), 8)
            self.assertTrue((output_root / "summary.csv").is_file())


if __name__ == "__main__":
    unittest.main()

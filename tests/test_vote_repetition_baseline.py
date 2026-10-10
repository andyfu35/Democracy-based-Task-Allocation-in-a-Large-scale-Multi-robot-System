"""Opt-in unacknowledged vote repetition versus 1-copy Greedy baseline.

No duplicate counted ballot, no self-vote retransmission, no fallback winner.
"""
from __future__ import annotations

import csv
import gzip
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from democracy_mrta.coordination import (
    simulate_democracy_hungarian_lossy,
    simulate_democracy_hungarian_retirement,
)
from democracy_mrta.diagnostics import ProtocolError
from democracy_mrta.network import BernoulliLossSampler, validate_vote_repetitions
from experiments.run_e2_retirement import (
    retirement_transport_stage_metrics,
    run_retirement_experiment,
)


class ConstantLatency:
    def sample_ms(self, key: str) -> float:
        return 10.0


class FirstVoteCopyLost:
    """Every initial remote vote is lost; copy 1 delivered; all Cost rows visible."""
    def is_delivered(self, key: str, p_loss: float) -> bool:
        if key.startswith("broadcast|cost|"):
            return True
        if key.startswith("unicast|vote|"):
            return key.endswith("|copy=1")
        return True


class AllRemoteVotesLost:
    def is_delivered(self, key: str, p_loss: float) -> bool:
        return not key.startswith("unicast|vote|")


class VoteRepetitionNetworkTests(unittest.TestCase):
    def test_only_bounded_integer_packet_repetition_is_allowed(self) -> None:
        self.assertEqual(tuple(validate_vote_repetitions(k) for k in (1, 2, 3)), (1, 2, 3))
        for bad in (0, 4, -1, 1.0, True, False, "2"):
            with self.subTest(bad=bad):
                with self.assertRaises(ProtocolError) as context:
                    validate_vote_repetitions(bad)
                self.assertEqual(context.exception.diagnostic.owner, "network")
                self.assertEqual(context.exception.diagnostic.function, "validate_vote_repetitions")
                self.assertEqual(context.exception.diagnostic.category, "data")
                self.assertEqual(context.exception.diagnostic.code, "INVALID_VOTE_REPETITIONS")

    def test_copy_zero_preserves_original_physical_loss_samples(self) -> None:
        costs = ((1.0,), (2.0,), (3.0,), (4.0,))
        params = dict(
            cost_matrix=costs, sampler=ConstantLatency(),
            p_loss=0.30, p_vote_loss=0.30,
            phase_timeout_ms=10.0,
            voting_strategy="greedy_task",
            vote_decision_rule="strict_majority",
        )
        one = simulate_democracy_hungarian_lossy(
            **params, loss_sampler=BernoulliLossSampler(seed=7),
            vote_repetitions=1,
        )
        two = simulate_democracy_hungarian_lossy(
            **params, loss_sampler=BernoulliLossSampler(seed=7),
            vote_repetitions=2,
        )
        zero_one = [
            (o.sender_id, o.receiver_id, o.task_id, o.delivered)
            for o in one.deliveries if o.phase == "vote"
        ]
        zero_two = [
            (o.sender_id, o.receiver_id, o.task_id, o.delivered)
            for o in two.deliveries if o.phase == "vote" and o.transmission_index == 0
        ]
        self.assertEqual(zero_one, zero_two)
        self.assertEqual(len(two.deliveries), len(one.deliveries) + len(zero_one))

    def test_second_copy_can_reach_strict_majority_without_extra_votes(self) -> None:
        costs = ((1.0,), (2.0,), (3.0,), (4.0,))
        params = dict(
            cost_matrix=costs, sampler=ConstantLatency(),
            loss_sampler=FirstVoteCopyLost(),
            p_loss=0.30, p_vote_loss=0.30,
            phase_timeout_ms=10.0,
            voting_strategy="greedy_task",
            vote_decision_rule="strict_majority",
        )
        first = simulate_democracy_hungarian_lossy(
            **params, vote_repetitions=1,
        )
        repeat = simulate_democracy_hungarian_lossy(
            **params, vote_repetitions=2, capture_vote_audit=True,
        )
        self.assertEqual(first.assigned_pairs, ())
        self.assertEqual(repeat.assigned_pairs, ((0, 0),))
        copies = [e for e in repeat.events if e.phase == "vote"]
        self.assertEqual(len(copies), 6)
        self.assertEqual([e.transmission_index for e in copies].count(0), 3)
        self.assertEqual([e.transmission_index for e in copies].count(1), 3)
        deliveries = [o for o in repeat.deliveries if o.phase == "vote"]
        self.assertEqual(len(deliveries), 6)
        self.assertEqual(sum(o.delivered for o in deliveries), 3)
        self.assertEqual(
            set(o.transmission_index for o in deliveries if o.delivered), {1}
        )
        self.assertEqual(repeat.audit_counted_vote_ledgers, ((0, 0, (0, 1, 2, 3)),))
        commits = [e for e in repeat.events if e.phase == "commit"]
        self.assertEqual(len(commits), 1)
        self.assertGreater(repeat.global_agreement_ms, first.global_agreement_ms)

    def test_zero_loss_copy_repetition_keeps_winner_and_charges_extra_messages(self) -> None:
        costs = ((1.0,), (2.0,), (3.0,), (4.0,))
        params = dict(
            cost_matrix=costs, sampler=ConstantLatency(),
            loss_sampler=BernoulliLossSampler(seed=5), p_loss=0.0,
            p_vote_loss=0.0, phase_timeout_ms=10.0,
            voting_strategy="greedy_task",
            vote_decision_rule="strict_majority",
        )
        one = simulate_democracy_hungarian_lossy(**params)
        three = simulate_democracy_hungarian_lossy(**params, vote_repetitions=3,
            capture_vote_audit=True)
        self.assertEqual(one.assigned_pairs, three.assigned_pairs)
        self.assertEqual(three.assigned_pairs, ((0, 0),))
        self.assertEqual(three.audit_counted_vote_ledgers, ((0, 0, (0, 1, 2, 3)),))
        self.assertEqual(three.logical_message_count - one.logical_message_count, 6)
        self.assertEqual(three.payload_bytes - one.payload_bytes, 6 * 32)
        self.assertGreater(three.global_agreement_ms, one.global_agreement_ms)
        self.assertFalse(any(e.phase == "fallback_self_claim" for e in three.events))

    def test_loss_of_all_repeated_votes_does_not_trigger_fallback(self) -> None:
        costs = ((1.0,), (2.0,), (3.0,), (4.0,))
        result = simulate_democracy_hungarian_lossy(
            cost_matrix=costs, sampler=ConstantLatency(),
            loss_sampler=AllRemoteVotesLost(), p_loss=0.30,
            p_vote_loss=1.0, phase_timeout_ms=10.0,
            voting_strategy="greedy_task",
            vote_decision_rule="quarter_plurality",
            vote_repetitions=3,
        )
        self.assertEqual(result.assigned_pairs, ())
        self.assertEqual(result.qualified_announcement_count, 0)
        self.assertEqual(len([e for e in result.events if e.phase == "vote"]), 9)
        self.assertFalse(any(
            e.phase in ("commit", "vote_score_announcement", "fallback_self_claim")
            for e in result.events
        ))

    def test_repeated_votes_keep_one_retirement_per_robot_and_count_self_vote_once(self) -> None:
        costs = (
            (1.0, 4.0), (2.0, 1.0),
            (3.0, 3.0), (4.0, 2.0),
        )
        result = simulate_democracy_hungarian_retirement(
            cost_matrix=costs, sampler=ConstantLatency(),
            loss_sampler=BernoulliLossSampler(seed=2),
            p_loss=0.0, p_vote_loss=0.0,
            phase_timeout_ms=10.0, max_rounds=4,
            voting_strategy="greedy_task",
            vote_decision_rule="strict_majority",
            vote_repetitions=2,
        )
        self.assertTrue(result.full_assignment_success)
        self.assertEqual(result.vote_repetitions, 2)
        self.assertEqual(len(result.assigned_pairs), 2)
        self.assertEqual(len(set(r for r, t in result.assigned_pairs)), 2)
        stats = retirement_transport_stage_metrics(result)
        self.assertEqual(stats["remote_vote_attempts"] % 2, 0)
        self.assertGreater(stats["remote_vote_attempts"], 0)
        self.assertGreater(stats["self_votes"], 0)
        self.assertEqual(stats["remote_vote_dropped"], 0)
        self.assertEqual(stats["cost_packet_dropped"], 0)


class VoteRepetitionRunnerTests(unittest.TestCase):
    def test_runner_exports_physical_copy_index_and_preserves_original_cost_exchange(self) -> None:
        costs = ((1.0,), (2.0,), (3.0,), (4.0,))
        with tempfile.TemporaryDirectory() as root:
            out = Path(root) / "repeated_votes"
            with (
                patch("experiments.run_e2_retirement.ensure_rady_dataset", return_value=Path(root) / "unused"),
                patch("experiments.run_e2_retirement.load_rady_latency_profile", return_value=object()),
                patch("experiments.run_e2_retirement.summarize_latency_profile", return_value={"max_ms": 10.0}),
                patch("experiments.run_e2_retirement.EmpiricalLatencySampler",
                    side_effect=lambda *args, **kwargs: ConstantLatency()),
                patch("experiments.run_e2_retirement.generate_e0_scenario",
                    side_effect=lambda *args, **kwargs: SimpleNamespace(cost_matrix=costs)),
                patch("experiments.run_e2_retirement.read_retirement_revision",
                    return_value="repeat-vote-test-sha"),
            ):
                summaries = run_retirement_experiment(
                    robots=4, tasks=1, seeds=2,
                    cost_losses=(0.0, 0.30), p_vote_loss=0.0,
                    vote_losses=(0.0, 0.30), loss_pairing="diagonal",
                    max_rounds=2, vote_decision_rule="strict_majority",
                    vote_repetitions=2,
                    dataset_path=Path(root) / "unused",
                    output_root=out, allow_download=False,
                )
            self.assertEqual(len(summaries), 2)
            self.assertTrue(all(int(r["vote_repetitions"]) == 2 for r in summaries))
            with next((out / "raw").glob("retirement_*.csv")).open(
                newline="", encoding="utf-8"
            ) as f:
                raw = list(csv.DictReader(f))
            self.assertEqual(len(raw), 4)
            self.assertEqual({r["vote_repetitions"] for r in raw}, {"2"})
            self.assertEqual({r["git_sha"] for r in raw}, {"repeat-vote-test-sha"})
            self.assertTrue(all(
                int(r["remote_vote_attempts"]) % 2 == 0 for r in raw
            ))
            self.assertTrue(all(
                int(r["self_votes"]) >= 0 for r in raw
            ))
            with gzip.open(
                next((out / "events").glob("retirement_audit_*.csv.gz")),
                "rt", newline="", encoding="utf-8",
            ) as f:
                audit = list(csv.DictReader(f))
            phys = [r for r in audit if r["kind"] == "delivery" and r["phase"] == "vote"]
            self.assertEqual({r["transmission_index"] for r in phys}, {"0", "1"})
            logical = [r for r in audit if r["kind"] == "logical_message" and r["phase"] == "vote"]
            self.assertEqual({r["transmission_index"] for r in logical}, {"0", "1"})
            cost_msgs = [r for r in audit if r["kind"] == "logical_message" and r["phase"] == "cost"]
            self.assertEqual(len(cost_msgs), 8)  # 4 senders × 2 loss conditions
            self.assertFalse(any(
                r["phase"] == "fallback_self_claim" for r in audit
            ))


if __name__ == "__main__":
    unittest.main()

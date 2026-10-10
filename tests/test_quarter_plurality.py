from __future__ import annotations

import unittest
import csv
import gzip
from pathlib import Path
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

from democracy_mrta.coordination import (
    simulate_democracy_hungarian_lossy,
    simulate_democracy_hungarian_retirement,
)
from democracy_mrta.diagnostics import ProtocolError
from democracy_mrta.network import BernoulliLossSampler
from democracy_mrta.protocol import (
    CandidateVoteAnnouncement,
    quarter_vote_announcement_threshold,
    resolve_unique_plurality_claims,
)
from democracy_mrta.optimizer import solve_hungarian_assignment
from experiments.run_e2_retirement import (
    retirement_result_row,
    retirement_plurality_diagnostics,
    run_retirement_experiment,
)


class FixedLatency:
    def sample_ms(self, key: str) -> float:
        return 10.0


class SplitSixVoters:
    """Physical 3/3 split: receiver robots 3/4/5 cannot see robot 0's row."""
    def is_delivered(self, key: str, p_loss: float) -> bool:
        return not any(
            key.startswith(f"broadcast|cost|0|{receiver_id}|")
            for receiver_id in (3, 4, 5)
        )


class QuarterPluralityProtocolTests(unittest.TestCase):
    def test_strict_25_percent_requires_26_of_100(self) -> None:
        self.assertEqual(quarter_vote_announcement_threshold(100), 26)
        self.assertEqual(quarter_vote_announcement_threshold(99), 25)
        self.assertEqual(quarter_vote_announcement_threshold(8), 3)
        self.assertEqual(quarter_vote_announcement_threshold(4), 2)
        self.assertEqual(quarter_vote_announcement_threshold(1), 1)

    def test_multiple_qualified_announcements_choose_highest_vote(self) -> None:
        result = resolve_unique_plurality_claims(
            announcements=(
                CandidateVoteAnnouncement(candidate_id=3, received_votes=28),
                CandidateVoteAnnouncement(candidate_id=9, received_votes=37),
            ),
            eligible_robots=frozenset(range(100)),
            fallback_used=False, task_id=0, round_id=1,
        )
        self.assertEqual(result.winner_id, 9)
        self.assertEqual(result.announcement_threshold, 26)
        self.assertEqual(result.announced_candidate_count, 2)
        self.assertFalse(result.fallback_used)

    def test_qualified_tie_uses_stable_robot_id(self) -> None:
        result = resolve_unique_plurality_claims(
            announcements=(
                CandidateVoteAnnouncement(candidate_id=4, received_votes=3),
                CandidateVoteAnnouncement(candidate_id=1, received_votes=3),
            ),
            eligible_robots=frozenset(range(6)),
            fallback_used=False, task_id=0, round_id=0,
        )
        self.assertEqual(result.winner_id, 1)
        self.assertTrue(result.tied_highest)

    def test_exactly_one_quarter_does_not_qualify(self) -> None:
        with self.assertRaises(ProtocolError) as context:
            resolve_unique_plurality_claims(
                announcements=(CandidateVoteAnnouncement(0, 25),),
                eligible_robots=frozenset(range(100)),
                fallback_used=False, task_id=0, round_id=0,
            )
        self.assertEqual(
            context.exception.diagnostic.code,
            "INVALID_QUALIFIED_PLURALITY_ANNOUNCEMENTS",
        )

    def test_fallback_requires_every_eligible_candidate_claim(self) -> None:
        with self.assertRaises(ProtocolError) as context:
            resolve_unique_plurality_claims(
                announcements=(CandidateVoteAnnouncement(0, 0),),
                eligible_robots=frozenset((0, 1)),
                fallback_used=True, task_id=0, round_id=0,
            )
        self.assertEqual(
            context.exception.diagnostic.code,
            "INVALID_PLURALITY_FALLBACK_CLAIMS",
        )

    def test_duplicate_claim_fails_before_winner_execution(self) -> None:
        with self.assertRaises(ProtocolError) as context:
            resolve_unique_plurality_claims(
                announcements=(
                    CandidateVoteAnnouncement(0, 2),
                    CandidateVoteAnnouncement(0, 2),
                ),
                eligible_robots=frozenset(range(4)),
                fallback_used=False, task_id=0, round_id=0,
            )
        self.assertEqual(
            context.exception.diagnostic.code,
            "DUPLICATE_PLURALITY_ANNOUNCEMENT",
        )


class QuarterPluralityCoordinationTests(unittest.TestCase):
    def test_qualified_candidates_broadcast_scores_and_compare(self) -> None:
        costs = ((1.0,), (2.0,), (3.0,), (4.0,), (5.0,), (6.0,))
        result = simulate_democracy_hungarian_lossy(
            cost_matrix=costs,
            sampler=FixedLatency(),
            loss_sampler=SplitSixVoters(),
            p_loss=0.3,
            p_vote_loss=0.0,
            phase_timeout_ms=10.0,
            voting_strategy="greedy_task",
            vote_decision_rule="quarter_plurality_fallback",
        )
        self.assertEqual(result.assigned_pairs, ((0, 0),))
        self.assertEqual(result.announcement_threshold, 2)
        self.assertEqual(result.qualified_announcement_count, 2)
        self.assertEqual(result.fallback_self_claim_count, 0)
        self.assertEqual(result.fallback_used_task_count, 0)
        self.assertEqual(result.plurality_tie_break_count, 1)
        score_events = [
            event for event in result.events
            if event.phase == "vote_score_announcement"
        ]
        self.assertEqual(len(score_events), 2)
        self.assertEqual(
            {(event.sender_id, event.announced_vote_count) for event in score_events},
            {(0, 3), (1, 3)},
        )
        self.assertEqual(
            len([event for event in result.events if event.phase == "commit"]), 1
        )
        self.assertTrue(all(event.round_id == 0 for event in score_events))

    def test_no_candidate_qualifies_all_self_claim_then_one_commit(self) -> None:
        costs = ((9.0,), (1.0,), (2.0,), (3.0,))
        result = simulate_democracy_hungarian_lossy(
            cost_matrix=costs,
            sampler=FixedLatency(),
            loss_sampler=BernoulliLossSampler(seed=3),
            p_loss=1.0,
            p_vote_loss=1.0,
            phase_timeout_ms=10.0,
            voting_strategy="greedy_task",
            vote_decision_rule="quarter_plurality_fallback",
        )
        self.assertEqual(result.announcement_threshold, 2)
        self.assertEqual(result.qualified_announcement_count, 0)
        self.assertEqual(result.fallback_self_claim_count, 4)
        self.assertEqual(result.fallback_used_task_count, 1)
        self.assertEqual(result.plurality_winner_vote_count, 1)
        self.assertEqual(result.plurality_tie_break_count, 1)
        self.assertEqual(result.assigned_pairs, ((0, 0),))
        self.assertEqual(result.total_cost, 9.0)
        self.assertEqual(
            len([e for e in result.events if e.phase == "fallback_self_claim"]), 4
        )
        self.assertEqual(
            len([e for e in result.events if e.phase == "commit"]), 1
        )
        self.assertEqual(result.lossy_delivered, 0)
        self.assertGreater(result.logical_message_count, 4)

    def test_full_loss_can_complete_all_tasks_but_with_very_bad_cost(self) -> None:
        costs = ((100.0, 1.0), (1.0, 100.0))
        result = simulate_democracy_hungarian_retirement(
            cost_matrix=costs,
            sampler=FixedLatency(),
            loss_sampler=BernoulliLossSampler(seed=3),
            p_loss=1.0, p_vote_loss=1.0,
            phase_timeout_ms=10.0, max_rounds=2,
            voting_strategy="greedy_task",
            vote_decision_rule="quarter_plurality_fallback",
        )
        self.assertTrue(result.full_assignment_success)
        self.assertEqual(result.assigned_pairs, ((0, 0), (1, 1)))
        self.assertEqual(result.total_cost, 200.0)
        self.assertEqual(len(result.rounds), 2)
        self.assertEqual(
            [round_trace.announcement_threshold for round_trace in result.rounds],
            [1, 1],
        )
        self.assertTrue(all(
            round_trace.coordination.vote_decision_rule == "quarter_plurality_fallback"
            for round_trace in result.rounds
        ))
        self.assertEqual(result.rounds[0].coordination.fallback_self_claim_count, 0)
        self.assertEqual(result.rounds[1].coordination.fallback_self_claim_count, 0)
        # Under two voters, a single self-vote exceeds 25%; the candidate
        # comparison still produces one winner and loses global optimality.
        self.assertEqual(
            solve_hungarian_assignment(costs).total_cost, 2.0
        )
        diag = retirement_plurality_diagnostics(result)
        self.assertEqual(diag["fallback_commit_tasks"], 0)

    def test_runner_writes_distinct_plurality_evidence_and_fallback_audit(self) -> None:
        costs = ((9.0,), (1.0,), (2.0,), (3.0,))
        with tempfile.TemporaryDirectory() as root:
            out = Path(root) / "quarter_plurality"
            with (
                patch("experiments.run_e2_retirement.ensure_rady_dataset", return_value=Path(root) / "unused"),
                patch("experiments.run_e2_retirement.load_rady_latency_profile", return_value=object()),
                patch("experiments.run_e2_retirement.summarize_latency_profile", return_value={"max_ms": 10.0}),
                patch("experiments.run_e2_retirement.EmpiricalLatencySampler", side_effect=lambda *a, **kw: FixedLatency()),
                patch("experiments.run_e2_retirement.generate_e0_scenario", side_effect=lambda *a, **kw: SimpleNamespace(cost_matrix=costs)),
                patch("experiments.run_e2_retirement.read_retirement_revision", return_value="quarter-test-sha"),
            ):
                summaries = run_retirement_experiment(
                    robots=4, tasks=1, seeds=2,
                    cost_losses=(1.0,), p_vote_loss=1.0,
                    vote_losses=(1.0,), loss_pairing="diagonal",
                    max_rounds=1,
                    vote_decision_rule="quarter_plurality_fallback",
                    dataset_path=Path(root) / "unused",
                    output_root=out, allow_download=False,
                )
            self.assertEqual(len(summaries), 1)
            summary = summaries[0]
            self.assertEqual(summary["method"], "democracy_greedy_quarter_plurality_retirement")
            self.assertEqual(summary["full_assignment_success_rate"], 1.0)
            self.assertEqual(summary["mean_fallback_commit_rate"], 1.0)
            self.assertEqual(summary["mean_fallback_self_claims"], 4.0)
            self.assertEqual(summary["mean_qualified_announcements"], 0.0)
            self.assertEqual(summary["safety_failures"], 0)

            raw = next((out / "raw").glob("retirement_*.csv"))
            with raw.open(newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(len(rows), 2)
            self.assertEqual({r["git_sha"] for r in rows}, {"quarter-test-sha"})
            self.assertEqual({r["vote_decision_rule"] for r in rows}, {"quarter_plurality_fallback"})

            audit = next((out / "events").glob("*.csv.gz"))
            with gzip.open(audit, "rt", newline="", encoding="utf-8") as handle:
                events = list(csv.DictReader(handle))
            claimed = [e for e in events if e["phase"] == "fallback_self_claim"]
            self.assertEqual(len(claimed), 4)
            self.assertEqual({e["announced_vote_count"] for e in claimed}, {"1"})
            self.assertEqual(
                len([e for e in events if e["phase"] == "commit"]), 1
            )


    def test_original_majority_default_is_unchanged(self) -> None:
        costs = ((1.0,), (2.0,), (3.0,), (4.0,))
        params = dict(
            cost_matrix=costs, sampler=FixedLatency(),
            loss_sampler=BernoulliLossSampler(seed=3),
            p_loss=1.0, p_vote_loss=1.0,
            phase_timeout_ms=10.0,
            voting_strategy="greedy_task",
        )
        legacy = simulate_democracy_hungarian_lossy(**params)
        explicit = simulate_democracy_hungarian_lossy(
            **params, vote_decision_rule="strict_majority"
        )
        self.assertEqual(legacy.events, explicit.events)
        self.assertEqual(legacy.deliveries, explicit.deliveries)
        self.assertEqual(legacy.assigned_pairs, explicit.assigned_pairs)
        self.assertEqual(legacy.assigned_pairs, ())

    def test_pluraility_rule_rejects_hungarian_planning(self) -> None:
        with self.assertRaises(ProtocolError) as context:
            simulate_democracy_hungarian_lossy(
                cost_matrix=((1.0,), (2.0,)),
                sampler=FixedLatency(),
                loss_sampler=BernoulliLossSampler(seed=3),
                p_loss=0.0, p_vote_loss=0.0,
                phase_timeout_ms=10.0,
                voting_strategy="hungarian",
                vote_decision_rule="quarter_plurality_fallback",
            )
        self.assertEqual(
            context.exception.diagnostic.code,
            "PLURALITY_REQUIRES_ONE_TASK_GREEDY",
        )


if __name__ == "__main__":
    unittest.main()

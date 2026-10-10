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
from democracy_mrta.network import BernoulliLossSampler
from democracy_mrta.optimizer import solve_hungarian_assignment
from democracy_mrta.protocol import (
    CandidateVoteAnnouncement,
    quarter_vote_announcement_threshold,
    resolve_unique_plurality_claims,
)
from experiments.run_e2_retirement import (
    retirement_plurality_diagnostics,
    run_retirement_experiment,
)


class FixedLatency:
    def sample_ms(self, key: str) -> float:
        return 10.0


class SplitSixVoters:
    """Robots 3/4/5 cannot see robot 0's Cost row, so two candidates tie."""
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
            task_id=0, round_id=1,
        )
        self.assertIsNotNone(result)
        self.assertEqual(result.winner_id, 9)
        self.assertEqual(result.announcement_threshold, 26)
        self.assertEqual(result.announced_candidate_count, 2)
        self.assertFalse(result.tied_highest)

    def test_qualified_tie_uses_stable_robot_id(self) -> None:
        result = resolve_unique_plurality_claims(
            announcements=(
                CandidateVoteAnnouncement(candidate_id=4, received_votes=3),
                CandidateVoteAnnouncement(candidate_id=1, received_votes=3),
            ),
            eligible_robots=frozenset(range(6)),
            task_id=0, round_id=0,
        )
        self.assertIsNotNone(result)
        self.assertEqual(result.winner_id, 1)
        self.assertTrue(result.tied_highest)

    def test_absent_qualified_announcement_is_not_a_commit(self) -> None:
        result = resolve_unique_plurality_claims(
            announcements=(),
            eligible_robots=frozenset(range(100)),
            task_id=0, round_id=0,
        )
        self.assertIsNone(result)

    def test_exactly_one_quarter_does_not_qualify(self) -> None:
        with self.assertRaises(ProtocolError) as context:
            resolve_unique_plurality_claims(
                announcements=(CandidateVoteAnnouncement(0, 25),),
                eligible_robots=frozenset(range(100)),
                task_id=0, round_id=0,
            )
        self.assertEqual(
            context.exception.diagnostic.code,
            "INVALID_QUALIFIED_PLURALITY_ANNOUNCEMENTS",
        )

    def test_duplicate_qualified_announcement_is_rejected(self) -> None:
        with self.assertRaises(ProtocolError) as context:
            resolve_unique_plurality_claims(
                announcements=(
                    CandidateVoteAnnouncement(0, 3),
                    CandidateVoteAnnouncement(0, 3),
                ),
                eligible_robots=frozenset(range(4)),
                task_id=0, round_id=0,
            )
        self.assertEqual(
            context.exception.diagnostic.code,
            "DUPLICATE_PLURALITY_ANNOUNCEMENT",
        )

    def test_unqualified_announcement_cannot_select_a_winner(self) -> None:
        with self.assertRaises(ProtocolError) as context:
            resolve_unique_plurality_claims(
                announcements=(CandidateVoteAnnouncement(0, 1),),
                eligible_robots=frozenset(range(4)),
                task_id=0, round_id=0,
            )
        self.assertEqual(
            context.exception.diagnostic.code,
            "INVALID_QUALIFIED_PLURALITY_ANNOUNCEMENTS",
        )


class QuarterPluralityCoordinationTests(unittest.TestCase):
    def test_multiple_qualified_candidates_announce_scores_then_one_commits(self) -> None:
        costs = ((1.0,), (2.0,), (3.0,), (4.0,), (5.0,), (6.0,))
        result = simulate_democracy_hungarian_lossy(
            cost_matrix=costs,
            sampler=FixedLatency(),
            loss_sampler=SplitSixVoters(),
            p_loss=0.3,
            p_vote_loss=0.0,
            phase_timeout_ms=10.0,
            voting_strategy="greedy_task",
            vote_decision_rule="quarter_plurality",
        )
        self.assertEqual(result.assigned_pairs, ((0, 0),))
        self.assertEqual(result.announcement_threshold, 2)
        self.assertEqual(result.qualified_announcement_count, 2)
        self.assertEqual(result.plurality_tie_break_count, 1)
        announcements = [
            event for event in result.events
            if event.phase == "vote_score_announcement"
        ]
        self.assertEqual(
            {(e.sender_id, e.announced_vote_count) for e in announcements},
            {(0, 3), (1, 3)},
        )
        self.assertEqual(len([
            e for e in result.events if e.phase == "commit"
        ]), 1)
        self.assertFalse(any(
            e.phase == "fallback_self_claim" for e in result.events
        ))

    def test_no_candidate_above_25_percent_means_no_announcement_or_commit(self) -> None:
        costs = ((9.0,), (1.0,), (2.0,), (3.0,))
        result = simulate_democracy_hungarian_lossy(
            cost_matrix=costs,
            sampler=FixedLatency(),
            loss_sampler=BernoulliLossSampler(seed=3),
            p_loss=1.0,
            p_vote_loss=1.0,
            phase_timeout_ms=10.0,
            voting_strategy="greedy_task",
            vote_decision_rule="quarter_plurality",
        )
        self.assertEqual(result.announcement_threshold, 2)
        self.assertEqual(result.qualified_announcement_count, 0)
        self.assertEqual(result.plurality_winner_vote_count, 0)
        self.assertEqual(result.assigned_pairs, ())
        self.assertEqual(result.task_timeout_count, 1)
        self.assertEqual(result.total_cost, 0.0)
        self.assertEqual(result.lossy_delivered, 0)
        self.assertFalse(any(
            event.phase in ("vote_score_announcement", "fallback_self_claim", "commit")
            for event in result.events
        ))

    def test_no_qualified_candidate_rotates_task_and_retains_all_voters(self) -> None:
        costs = (
            (9.0, 8.0), (1.0, 6.0),
            (2.0, 5.0), (3.0, 4.0),
        )
        result = simulate_democracy_hungarian_retirement(
            cost_matrix=costs,
            sampler=FixedLatency(),
            loss_sampler=BernoulliLossSampler(seed=3),
            p_loss=1.0, p_vote_loss=1.0,
            phase_timeout_ms=10.0, max_rounds=3,
            voting_strategy="greedy_task",
            vote_decision_rule="quarter_plurality",
        )
        self.assertFalse(result.full_assignment_success)
        self.assertEqual(result.assigned_pairs, ())
        self.assertEqual(result.remaining_task_ids, (1, 0))
        self.assertEqual(len(result.rounds), 3)
        self.assertEqual([item.voted_task_id for item in result.rounds], [0, 1, 0])
        self.assertTrue(all(
            item.active_robot_ids == (0, 1, 2, 3)
            and item.announcement_threshold == 2
            and item.newly_committed_pairs == ()
            for item in result.rounds
        ))
        self.assertFalse(any(
            event.phase in ("vote_score_announcement", "fallback_self_claim", "commit")
            for item in result.rounds for event in item.coordination.events
        ))
        diag = retirement_plurality_diagnostics(result)
        self.assertEqual(diag["qualified_commit_tasks"], 0)
        self.assertEqual(diag["no_qualified_announcement_attempts"], 3)
        self.assertEqual(diag["no_qualified_announcement_rate"], 1.0)

    def test_zero_loss_commits_and_retires_one_executor_per_task(self) -> None:
        costs = (
            (1.0, 9.0), (2.0, 1.0),
            (3.0, 4.0), (4.0, 5.0),
        )
        result = simulate_democracy_hungarian_retirement(
            cost_matrix=costs,
            sampler=FixedLatency(),
            loss_sampler=BernoulliLossSampler(seed=3),
            p_loss=0.0, p_vote_loss=0.0,
            phase_timeout_ms=10.0, max_rounds=3,
            voting_strategy="greedy_task",
            vote_decision_rule="quarter_plurality",
        )
        self.assertTrue(result.full_assignment_success)
        self.assertEqual(result.assigned_pairs, ((0, 0), (1, 1)))
        self.assertEqual([item.announcement_threshold for item in result.rounds], [2, 1])
        self.assertEqual([len(item.active_robot_ids) for item in result.rounds], [4, 3])
        self.assertTrue(all(
            item.coordination.qualified_announcement_count == 1
            for item in result.rounds
        ))
        self.assertFalse(any(
            event.sender_id == 0 for event in result.rounds[1].coordination.events
        ))
        self.assertEqual(retirement_plurality_diagnostics(result)["no_qualified_announcement_attempts"], 0)

    def test_tiny_electorate_still_obeys_strict_25_percent(self) -> None:
        # With two voters a single self-vote qualifies; this is NOT fallback.
        costs = ((100.0, 1.0), (1.0, 100.0))
        result = simulate_democracy_hungarian_retirement(
            cost_matrix=costs,
            sampler=FixedLatency(),
            loss_sampler=BernoulliLossSampler(seed=3),
            p_loss=1.0, p_vote_loss=1.0,
            phase_timeout_ms=10.0, max_rounds=2,
            voting_strategy="greedy_task",
            vote_decision_rule="quarter_plurality",
        )
        self.assertTrue(result.full_assignment_success)
        self.assertEqual(result.assigned_pairs, ((0, 0), (1, 1)))
        self.assertEqual(result.total_cost, 200.0)
        self.assertEqual(
            [item.announcement_threshold for item in result.rounds],
            [1, 1],
        )
        self.assertEqual(
            solve_hungarian_assignment(costs).total_cost, 2.0
        )
        self.assertEqual(
            retirement_plurality_diagnostics(result)["no_qualified_announcement_attempts"],
            0,
        )

    def test_existing_majority_remains_default(self) -> None:
        params = dict(
            cost_matrix=((1.0,), (2.0,), (3.0,), (4.0,)),
            sampler=FixedLatency(),
            loss_sampler=BernoulliLossSampler(seed=3),
            p_loss=1.0, p_vote_loss=1.0,
            phase_timeout_ms=10.0,
            voting_strategy="greedy_task",
        )
        reference = simulate_democracy_hungarian_lossy(**params)
        explicit = simulate_democracy_hungarian_lossy(
            **params, vote_decision_rule="strict_majority"
        )
        self.assertEqual(reference.events, explicit.events)
        self.assertEqual(reference.deliveries, explicit.deliveries)
        self.assertEqual(reference.assigned_pairs, explicit.assigned_pairs)
        self.assertEqual(reference.assigned_pairs, ())

    def test_removed_fallback_rule_fails_with_diagnostic(self) -> None:
        with self.assertRaises(ProtocolError) as context:
            simulate_democracy_hungarian_lossy(
                cost_matrix=((1.0,), (2.0,)),
                sampler=FixedLatency(),
                loss_sampler=BernoulliLossSampler(seed=3),
                p_loss=0.0, p_vote_loss=0.0,
                phase_timeout_ms=10.0,
                voting_strategy="greedy_task",
                vote_decision_rule="quarter_plurality_fallback",
            )
        self.assertEqual(
            context.exception.diagnostic.code,
            "REMOVED_PLURALITY_FALLBACK_RULE",
        )
        self.assertEqual(context.exception.diagnostic.category, "contract")

    def test_plurality_requires_one_task_greedy(self) -> None:
        with self.assertRaises(ProtocolError) as context:
            simulate_democracy_hungarian_lossy(
                cost_matrix=((1.0,), (2.0,)),
                sampler=FixedLatency(),
                loss_sampler=BernoulliLossSampler(seed=3),
                p_loss=0.0, p_vote_loss=0.0,
                phase_timeout_ms=10.0,
                voting_strategy="hungarian",
                vote_decision_rule="quarter_plurality",
            )
        self.assertEqual(
            context.exception.diagnostic.code,
            "PLURALITY_REQUIRES_ONE_TASK_GREEDY",
        )

    def test_experiment_exports_timeouts_without_any_self_claims(self) -> None:
        costs = ((9.0,), (1.0,), (2.0,), (3.0,))
        with tempfile.TemporaryDirectory() as root:
            out = Path(root) / "quarter_plurality_pure"
            with (
                patch("experiments.run_e2_retirement.ensure_rady_dataset", return_value=Path(root) / "unused"),
                patch("experiments.run_e2_retirement.load_rady_latency_profile", return_value=object()),
                patch("experiments.run_e2_retirement.summarize_latency_profile", return_value={"max_ms": 10.0}),
                patch("experiments.run_e2_retirement.EmpiricalLatencySampler", side_effect=lambda *a, **kw: FixedLatency()),
                patch("experiments.run_e2_retirement.generate_e0_scenario", side_effect=lambda *a, **kw: SimpleNamespace(cost_matrix=costs)),
                patch("experiments.run_e2_retirement.read_retirement_revision", return_value="no-fallback-test-sha"),
            ):
                summaries = run_retirement_experiment(
                    robots=4, tasks=1, seeds=2,
                    cost_losses=(0.0, 1.0), p_vote_loss=0.0,
                    vote_losses=(0.0, 1.0), loss_pairing="diagonal",
                    max_rounds=2,
                    vote_decision_rule="quarter_plurality",
                    dataset_path=Path(root) / "unused",
                    output_root=out, allow_download=False,
                )
            self.assertEqual(len(summaries), 2)
            baseline = next(row for row in summaries if row["p_cost_loss"] == 0.0)
            blackout = next(row for row in summaries if row["p_cost_loss"] == 1.0)
            self.assertEqual(baseline["method"], "democracy_greedy_quarter_plurality_retirement")
            self.assertEqual(baseline["full_assignment_success_rate"], 1.0)
            self.assertEqual(baseline["mean_qualified_commit_tasks"], 1.0)
            self.assertEqual(baseline["mean_no_qualified_announcement_attempts"], 0.0)
            self.assertEqual(blackout["full_assignment_success_rate"], 0.0)
            self.assertEqual(blackout["mean_qualified_announcements"], 0.0)
            self.assertEqual(blackout["mean_no_qualified_announcement_attempts"], 2.0)
            self.assertEqual(blackout["mean_quorum_failed_attempts"], 2.0)
            self.assertEqual(blackout["safety_failures"], 0)

            with next((out / "raw").glob("retirement_*.csv")).open(newline="", encoding="utf-8") as stream:
                raw = list(csv.DictReader(stream))
            self.assertEqual(len(raw), 4)
            self.assertEqual({row["git_sha"] for row in raw}, {"no-fallback-test-sha"})
            self.assertEqual({row["vote_decision_rule"] for row in raw}, {"quarter_plurality"})
            self.assertTrue(all("fallback_commit_rate" not in row for row in raw))

            with next((out / "rounds").glob("retirement_rounds_*.csv")).open(newline="", encoding="utf-8") as stream:
                rounds = list(csv.DictReader(stream))
            failed = [row for row in rounds if row["p_cost_loss"] == "1.0"]
            self.assertEqual(len(failed), 4)
            self.assertTrue(all(row["no_qualified_announcement"] == "1" for row in failed))
            self.assertTrue(all(row["new_committed_tasks"] == "0" for row in failed))

            with gzip.open(next((out / "events").glob("*.csv.gz")), "rt", newline="", encoding="utf-8") as stream:
                events = list(csv.DictReader(stream))
            self.assertFalse(any(event["phase"] == "fallback_self_claim" for event in events))
            self.assertFalse(any(
                event["phase"] == "commit" and event["p_cost_loss"] == "1.0"
                for event in events
            ))
            qualified = [
                e for e in events if e["phase"] == "vote_score_announcement"
                and e["p_cost_loss"] == "0.0"
            ]
            self.assertEqual(len(qualified), 1)
            self.assertEqual(qualified[0]["announced_vote_count"], "4")


if __name__ == "__main__":
    unittest.main()

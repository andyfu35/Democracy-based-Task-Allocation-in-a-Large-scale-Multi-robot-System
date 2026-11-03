"""P2Q only: optimization-rank^2 vote separation without CLAIM repairs."""
from __future__ import annotations

from collections import Counter
import json
import unittest

from democracy_mrta.coordination import simulate_p2k_local_vote_epoch
from democracy_mrta.diagnostics import ProtocolError
from democracy_mrta.network import (
    BernoulliLossSampler,EmpiricalLatencyProfile,EmpiricalLatencySampler,
)
from democracy_mrta.optimizer import (
    apportion_p2q_task_tickets,
    compute_p2q_rank_squared_proposal_weights,
    sample_p2k_task_balanced_votes,
)
from experiments.run_p2q_rank_square_voting import (
    FIELDS,POLICY,analyze_p2q_vote_consensus,parse_args,
    summarize_p2q_rows,validate_p2q_axes,
)


def profile():
    return EmpiricalLatencyProfile(
        source_repository="test",source_commit="test",
        source_blob_sha="0"*40,location="2",location_label="p2q",
        config="ax_160mhz_6ghz",config_label="synthetic",
        steady_start_s=0.0,steady_end_s=4.0,
        samples_ms=(3.0,4.0,5.0,6.0),
    )


class P2QRankSquareVotingTests(unittest.TestCase):
    def setUp(self):
        self.costs=((1.,8.,9.),(8.,1.,9.),(9.,8.,1.))

    def test_inverse_square_rank_weights_are_stronger_than_second_place(self):
        proposals=tuple((float(rank),((rank,0),))
                        for rank in range(1,6))
        weights=compute_p2q_rank_squared_proposal_weights(proposals)
        self.assertEqual(weights[0],1.0)
        self.assertEqual(weights[1],0.25)
        self.assertAlmostEqual(weights[2],1/9)
        self.assertAlmostEqual(weights[0]/weights[1],4)
        self.assertAlmostEqual(weights[0]/weights[2],9)
        with self.assertRaises(ProtocolError):
            compute_p2q_rank_squared_proposal_weights(proposals[::-1])

    def test_exact_ten_tickets_using_deterministic_largest_remainder(self):
        weights=(1.0,0.25,1/9,1/16,1/25)
        ballot=apportion_p2q_task_tickets(
            visible_robots=(0,1,2,3,4),
            weights=weights,tickets_per_task=10,
        )
        self.assertEqual(len(ballot),10)
        self.assertEqual(Counter(ballot),Counter({0:7,1:2,2:1}))
        self.assertEqual(ballot,apportion_p2q_task_tickets(
            visible_robots=(0,1,2,3,4),
            weights=weights,tickets_per_task=10,
        ))
        with self.assertRaises(ProtocolError):
            apportion_p2q_task_tickets(
                visible_robots=(0,0),weights=(1.,1.),
                tickets_per_task=10,
            )

    def test_optimized_rank_square_ballots_only_use_visible_cost_rows(self):
        kwargs={
            "cost_matrix":self.costs,
            "visible_robot_ids":frozenset((0,2)),
            "voter_id":0,"seed":42,
            "votes_per_voter":600,"k":5,"epsilon":0.0,
            "temperature":5.0,"policy":POLICY,
        }
        ballot=sample_p2k_task_balanced_votes(**kwargs)
        self.assertEqual(len(ballot),600)
        self.assertEqual(ballot,sample_p2k_task_balanced_votes(**kwargs))
        self.assertTrue(all(robot in (0,2) for robot in ballot))
        for task in range(3):
            self.assertEqual(len(ballot[task*200:(task+1)*200]),200)

    def test_unobserved_cost_rows_cannot_receive_any_vote(self):
        ballot=sample_p2k_task_balanced_votes(
            cost_matrix=self.costs,visible_robot_ids=frozenset({1}),
            voter_id=1,seed=1,votes_per_voter=600,
            policy=POLICY,k=5,epsilon=0.0,
        )
        self.assertEqual(set(ballot),{1})
        self.assertEqual(len(ballot),600)

    def test_full_reception_runs_same_native_original_vote_only_epoch(self):
        result=simulate_p2k_local_vote_epoch(
            cost_matrix=self.costs,
            sampler=EmpiricalLatencySampler(profile(),0),
            loss_sampler=BernoulliLossSampler(0),
            p_loss=0.0,phase_timeout_ms=100000,
            seed=0,votes_per_voter=600,policy=POLICY,
            k=5,epsilon=0.0,
        )
        self.assertEqual(len(result.events),6)
        self.assertEqual(
            {event.phase for event in result.events},{"cost","vote"},
        )
        self.assertEqual(
            {event.payload_bytes for event in result.events
             if event.phase=="vote"},{616},
        )
        self.assertEqual(len(result.robot_claims),3)
        self.assertEqual(len({task for _,task in result.robot_claims}),3)
        self.assertEqual(result.local_vote_views[0],
                         result.local_vote_views[1])
        self.assertEqual(result.local_vote_views[1],
                         result.local_vote_views[2])

    def test_no_top_vote_tie_does_not_imply_no_execution_collision(self):
        # Two receivers have different but UNAMBIGUOUS local votes.
        # R0 sees R0>T0 and claims T0. R1 sees R1>T0 and claims T0.
        # Zero top-vote ties is NOT a global single-task proof.
        views=(
            ((5,0),(0,5)),
            ((0,5),(5,0)),
        )
        row={
            "robots":2,"tasks":2,
            "full_valid_allocation":0,
            "duplicate_task_count":1,
            "unassigned_task_count":1,
            "unique_task_completion_percent":0.0,
        }
        metrics=analyze_p2q_vote_consensus(
            source_row=row,received_vote_matrices=views,
        )
        self.assertEqual(metrics["receiver_task_top_vote_ties"],0)
        self.assertEqual(metrics["receiver_task_top_tie_percent"],0)
        self.assertGreater(metrics["mean_positive_top_two_vote_margin"],0)
        diagnostic=json.loads(metrics["first_diagnostic_json"])
        self.assertEqual(diagnostic["category"],"safety")
        self.assertEqual(
            diagnostic["code"],"P2Q_LOCAL_EXECUTIONS_NOT_ONE_TO_ONE",
        )
        self.assertEqual(diagnostic["owner"],
                         "experiments.run_p2q_rank_square_voting")

    def test_received_votes_can_still_tie_despite_rank_squaring(self):
        row={
            "robots":3,"tasks":1,
            "full_valid_allocation":0,
            "duplicate_task_count":1,
            "unassigned_task_count":0,
            "unique_task_completion_percent":0.0,
        }
        views=(
            ((10,),(10,),(0,)),
            ((8,),(7,),(5,)),
            ((0,),(0,),(0,)),
        )
        metrics=analyze_p2q_vote_consensus(
            source_row=row,received_vote_matrices=views,
        )
        self.assertEqual(metrics["receiver_task_top_vote_ties"],1)
        self.assertEqual(metrics["receiver_task_zero_vote_support_count"],1)
        self.assertEqual(metrics["receiver_task_positive_support_count"],2)
        self.assertAlmostEqual(metrics["receiver_task_top_tie_percent"],50)

    def test_offline_evidence_validation_has_its_own_diagnostic_boundary(self):
        source={
            "robots":2,"tasks":2,"full_valid_allocation":1,
            "duplicate_task_count":0,"unassigned_task_count":0,
            "unique_task_completion_percent":100.0,
        }
        with self.assertRaises(ProtocolError) as exc:
            analyze_p2q_vote_consensus(
                source_row=source,
                received_vote_matrices=(
                    ((1,2),(3,4)),
                ),
            )
        self.assertEqual(
            exc.exception.diagnostic.function,
            "validate_p2q_received_vote_matrices",
        )
        self.assertEqual(
            exc.exception.diagnostic.code,"P2Q_INVALID_AUDIT_VIEW",
        )
        with self.assertRaises(ProtocolError) as exc:
            analyze_p2q_vote_consensus(
                source_row=source,
                received_vote_matrices=(
                    ((1,2),(3,-1)),
                    ((3,1),(2,4)),
                ),
            )
        self.assertEqual(
            exc.exception.diagnostic.code,
            "P2Q_NEGATIVE_OR_NONINTEGER_RECEIVED_VOTE",
        )

    def test_one_only_method_grid_and_summary(self):
        args=parse_args(["--output-root","results/_p2q_unit"])
        self.assertEqual(validate_p2q_axes(args),(0,30,50,90))
        self.assertEqual(args.k,5)
        self.assertEqual(args.epsilon,0)
        self.assertEqual(args.votes,"1000")
        self.assertIn("receiver_task_top_vote_ties",FIELDS)
        args.epsilon=0.10
        with self.assertRaises(ProtocolError):
            validate_p2q_axes(args)
        sample={
            "loss_percent":30,"full_valid_allocation":0,
            "unique_task_completion_percent":90,
            "duplicate_task_count":4,"unassigned_task_count":6,
            "assignment_agreement_percent":97,
            "receiver_task_top_tie_percent":1.5,
            "mean_positive_top_two_vote_margin":15,
            "receiver_task_zero_vote_support_count":0,
            "task_any_receiver_top_tie_count":2,
            "sender_bytes":186448,"native_stop_ms":1200,
        }
        summary=summarize_p2q_rows([sample])
        self.assertEqual(len(summary),1)
        self.assertEqual(summary[0]["full_valid_percent"],0)
        self.assertEqual(summary[0]["valid_cost_samples"],0)
        self.assertEqual(summary[0]["mean_cost_if_valid"],"")


if __name__=="__main__":
    unittest.main()

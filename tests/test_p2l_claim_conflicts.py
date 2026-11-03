"""P2L proof obligations: original votes only, lossy paid CLAIM/ACK and no repair."""
from __future__ import annotations

import unittest

from democracy_mrta.claim_resolution import (
    ACK_WIRE, CLAIM_WIRE, P2LClaim,
    coordinate_p2l_claims,decode_p2l_claim_packet,encode_p2l_claim_packet,
    resolve_p2l_claim_conflicts,transmit_p2l_claim_with_receipts,
)
from democracy_mrta.coordination import P2KLocalVoteResult
from democracy_mrta.diagnostics import ProtocolError
from democracy_mrta.network import (
    BernoulliLossSampler, EmpiricalLatencySampler, EmpiricalLatencyProfile,
)
from experiments.run_p2l_claim_conflicts import (
    analyze_p2l_actual_executions,compute_p2l_vote_view_similarity,
    validate_p2l_axes,
)
from types import SimpleNamespace


def synthetic_profile():
    return EmpiricalLatencyProfile(
        source_repository="test",source_commit="test",source_blob_sha="0"*40,
        location="2",location_label="p2l",config="ax_160mhz_6ghz",
        config_label="synthetic",steady_start_s=0.0,steady_end_s=4.0,
        samples_ms=(3.0,4.0,5.0,6.0),
    )


def local_conflict_fixture() -> P2KLocalVoteResult:
    views=(
        ((120,30,50),(50,90,40),(30,80,110)),
        ((10,70,50),(160,20,20),(30,110,130)),
        ((40,100,20),(50,30,60),(110,70,120)),
    )
    return P2KLocalVoteResult(
        local_assignments=(
            ((0,0),(1,1),(2,2)),
            ((1,0),(0,1),(2,2)),
            ((0,0),(1,1),(2,2)),
        ),
        robot_claims=((0,0),(1,0),(2,2)),
        local_vote_views=views,
        cost_visible_rows=tuple(frozenset((0,1,2)) for _ in range(3)),
        events=(),deliveries=(),decision_time_ms=10.0,
        cost_completion_ms=5.0,
    )


class P2LClaimTests(unittest.TestCase):
    def setUp(self):
        self.run=local_conflict_fixture()
        self.costs=((1.0,3.0,9.0),(2.0,8.0,9.0),(8.0,9.0,1.0))

    def test_claim_wire_validates_own_vote_fraction(self):
        claim=P2LClaim(2,1,0,160,1,200)
        data=encode_p2l_claim_packet(claim)
        self.assertEqual(len(data),28)
        self.assertEqual(CLAIM_WIRE.size,28)
        self.assertEqual(ACK_WIRE.size,16)
        self.assertEqual(decode_p2l_claim_packet(
            data,claim_round=2,sender_id=1,
            tasks=3,robots=3,tickets_per_task=200,
        ),claim)
        with self.assertRaises(ProtocolError):
            decode_p2l_claim_packet(
                data,claim_round=2,sender_id=0,
                tasks=3,robots=3,tickets_per_task=200,
            )
        with self.assertRaises(ProtocolError):
            encode_p2l_claim_packet(P2LClaim(0,0,0,201,1,200))

    def test_normalized_score_overrules_larger_raw_ticket_count(self):
        claims=(
            P2LClaim(0,0,0,90,1,10),
            P2LClaim(0,1,0,120,2,10),
        )
        winners,losers,conflicts=resolve_p2l_claim_conflicts(
            claims=claims,locked_tasks=frozenset(),
        )
        self.assertEqual(winners,((0,0),))
        self.assertEqual(losers,(1,))
        self.assertEqual(conflicts,1)

    def test_model_reliable_paid_claim_resolves_conflict_without_score(self):
        result=coordinate_p2l_claims(
            run=self.run,cost_matrix=self.costs,
            votes_per_voter=600,
            sampler=EmpiricalLatencySampler(synthetic_profile(),0),
            loss_sampler=BernoulliLossSampler(0),
            p_loss=0.90,channel="ideal_paid",
            max_attempts=2,max_rounds=5,
        )
        self.assertTrue(result.complete_exchange)
        self.assertEqual(set(result.assigned_pairs),
                         {(0,1),(1,0),(2,2)})
        self.assertEqual(result.initial_collision_tasks,1)
        self.assertEqual(result.rounds_executed,2)
        self.assertEqual(result.reassignment_claims,1)
        self.assertTrue(all(e.phase=="claim" for e in result.events))
        self.assertEqual(len(result.events),4)
        self.assertEqual(result.sender_bytes,4*28)
        self.assertEqual(len(result.public_claims),4)
        self.assertEqual(result.public_claims[-1].task_id,1)

    def test_bounded_ack_charges_real_sender_bytes_and_ack_sends(self):
        result=coordinate_p2l_claims(
            run=self.run,cost_matrix=self.costs,
            votes_per_voter=600,
            sampler=EmpiricalLatencySampler(synthetic_profile(),0),
            loss_sampler=BernoulliLossSampler(0),
            p_loss=0.0,channel="bounded_ack",
            max_attempts=2,max_rounds=5,
        )
        self.assertTrue(result.complete_exchange)
        self.assertEqual(len(result.assigned_pairs),3)
        self.assertEqual(sum(e.phase=="claim" for e in result.events),4)
        self.assertEqual(sum(e.phase=="claim_ack" for e in result.events),8)
        self.assertEqual(result.sender_bytes,4*28+8*16)
        self.assertEqual(sum(not obs.delivered for obs in result.deliveries),0)

    def test_incomplete_ack_fails_closed_without_external_repair(self):
        result=coordinate_p2l_claims(
            run=self.run,cost_matrix=self.costs,
            votes_per_voter=600,
            sampler=EmpiricalLatencySampler(synthetic_profile(),4),
            loss_sampler=BernoulliLossSampler(4),
            p_loss=1.0,channel="bounded_ack",
            max_attempts=2,max_rounds=5,
        )
        self.assertFalse(result.complete_exchange)
        self.assertEqual(result.assigned_pairs,())
        self.assertEqual(result.first_diagnostic.code,
                         "P2L_CLAIM_ACK_BUDGET_EXHAUSTED")
        self.assertEqual(sum(e.phase=="claim" for e in result.events),6)
        self.assertEqual(sum(e.phase=="claim_ack" for e in result.events),0)

    def test_scope_forbids_old_scores_and_commits(self):
        invalid=SimpleNamespace(
            **{**self.run.__dict__,"events":(
                SimpleNamespace(phase="vote_score_announcement"),)}
        )
        with self.assertRaises(ProtocolError) as ctx:
            coordinate_p2l_claims(
                run=invalid,cost_matrix=self.costs,votes_per_voter=600,
                sampler=EmpiricalLatencySampler(synthetic_profile(),0),
                loss_sampler=BernoulliLossSampler(0),
                p_loss=0.0,channel="ideal_paid",
            )
        self.assertEqual(ctx.exception.diagnostic.code,"P2L_INVALID_CLAIM_SCOPE")

    def test_offline_cost_only_for_valid_full_assignment(self):
        scene=SimpleNamespace(num_robots=3,num_tasks=3,
                              cost_matrix=self.costs)
        partial=analyze_p2l_actual_executions(
            scene=scene,pairs=((0,0),(1,0)),
            reference_cost=5.0,
        )
        self.assertEqual(partial["duplicate_task_count"],1)
        self.assertEqual(partial["full_valid_allocation"],0)
        self.assertEqual(partial["cost_gap_percent_if_valid"],"")

    def test_vote_similarity_is_not_double_divided_by_tasks(self):
        value=compute_p2l_vote_view_similarity(self.run.local_vote_views)
        self.assertTrue(0<=value<=100)
        all_equal=(self.run.local_vote_views[0],)*3
        self.assertAlmostEqual(compute_p2l_vote_view_similarity(all_equal),100.0)

    def test_config_is_1000_only_and_10_seeds_default(self):
        args=SimpleNamespace(
            losses="0.00,0.30,0.50,0.90",channels="bounded_ack,ideal_paid",
            robots=100,tasks=100,votes=1000,seeds=10,first_seed=0,
            temperature=5.0,max_claim_attempts=24,max_claim_rounds=100,
            audit_seeds=1,
        )
        self.assertEqual(validate_p2l_axes(args),
                         ((0,30,50,90),("bounded_ack","ideal_paid")))
        args.votes=500
        with self.assertRaises(ProtocolError):
            validate_p2l_axes(args)


if __name__=="__main__":
    unittest.main()

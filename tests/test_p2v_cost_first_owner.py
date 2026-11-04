"""P2V: physical own-cost INTENT and cost-first Task Owner regression."""
import unittest

from democracy_mrta.claim_resolution import (
    P2LClaim, attach_p2v_local_cost, encode_p2v_cost_intent,
    decode_p2v_cost_intent, encode_p2r_intent,
    choose_p2r_owner_responses, transmit_p2r_intent_window,
    coordinate_p2r_announced_intents,
)
from democracy_mrta.coordination import P2KLocalVoteResult
from democracy_mrta.diagnostics import ProtocolError


class FakeSampler:
    def sample_ms(self,key):
        return 1.0


class NoLoss:
    def is_delivered(self,key,p_loss):
        return True


class BlockR0ToOwner:
    def is_delivered(self,key,p_loss):
        return "broadcast|p2r_intent|0|1|1|round=1" not in key


def offer(robot,support,cost,task=1):
    return P2LClaim(
        0,robot,task,support,10,10,float(cost),
    )


def same_view():
    return ((30,0,0),(0,30,0),(0,0,30))


class P2VCostFirstOwnerTests(unittest.TestCase):
    def test_cost_winner_overrides_larger_local_vote_support(self):
        high_votes=offer(0,90,20.0)
        low_cost=offer(2,60,1.0)
        p2r=choose_p2r_owner_responses(
            owner_receipts={1:[high_votes,low_cost]},
            owner_alerts=set(),reserved={},previously_deferred=set(),
            robots=3,claim_round=0,
        )
        p2v=choose_p2r_owner_responses(
            owner_receipts={1:[high_votes,low_cost]},
            owner_alerts=set(),reserved={},previously_deferred=set(),
            robots=3,claim_round=0,
            owner_decision_policy="cost_first",
        )
        self.assertIn((0,1,True),p2r[0])
        self.assertIn((2,1,True),p2v[0])
        self.assertEqual(p2v[1][0]["winning_advertised_cost"],1.0)

    def test_equal_cost_preserves_exact_vote_support_tiebreak(self):
        a=offer(0,40,1.5)
        b=offer(2,80,1.5)
        result=choose_p2r_owner_responses(
            owner_receipts={1:[a,b]},
            owner_alerts=set(),reserved={},previously_deferred=set(),
            robots=3,claim_round=0,
            owner_decision_policy="cost_first",
        )
        self.assertIn((2,1,True),result[0])

    def test_cost_intent_36_bytes_roundtrip_and_legacy_28(self):
        base=P2LClaim(0,2,1,50,10,10)
        claimed=attach_p2v_local_cost(
            claim=base,own_cost_row=(20.,1.25,99.),
        )
        packet=encode_p2v_cost_intent(claimed)
        self.assertEqual(len(packet),36)
        self.assertEqual(packet[:4],b"P2VI")
        self.assertEqual(decode_p2v_cost_intent(
            packet,sender_id=2,claim_round=0,
            robots=3,tasks=3,tickets_per_task=10,
        ),claimed)
        self.assertEqual(len(encode_p2r_intent(base)),28)
        with self.assertRaises(ProtocolError):
            decode_p2v_cost_intent(
                packet,sender_id=1,claim_round=0,
                robots=3,tasks=3,tickets_per_task=10,
            )

    def test_missing_or_invalid_sender_cost_not_accepted(self):
        with self.assertRaises(ProtocolError) as cm:
            encode_p2v_cost_intent(P2LClaim(0,0,1,10,10,10))
        self.assertEqual(cm.exception.diagnostic.code,
                         "P2V_INVALID_COST_INTENT")
        with self.assertRaises(ProtocolError):
            attach_p2v_local_cost(
                claim=P2LClaim(0,0,1,10,10,10),
                own_cost_row=(1.,float("nan"),2.),
            )
        with self.assertRaises(ProtocolError) as cm:
            choose_p2r_owner_responses(
                owner_receipts={1:[P2LClaim(0,0,1,10,10,10)]},
                owner_alerts=set(),reserved={},previously_deferred=set(),
                robots=3,claim_round=0,
                owner_decision_policy="cost_first",
            )
        self.assertEqual(cm.exception.diagnostic.code,
                         "P2V_MISSING_OWNER_RECEIVED_COST")

    def test_physical_receipt_controls_cost_comparison_not_oracle(self):
        intents=(offer(0,90,20.),offer(2,60,1.))
        events,deliveries,received,peer,finish=transmit_p2r_intent_window(
            intents=intents,robots=3,tasks=3,votes_per_voter=30,
            repetitions=3,start_ms=5.,sampler=FakeSampler(),
            loss_sampler=BlockR0ToOwner(),p_loss=0.3,cost_intents=True,
        )
        self.assertEqual(len(events),6)
        self.assertEqual({e.payload_bytes for e in events},{36})
        self.assertEqual(
            [c.robot_id for c in received[1]],[2],
        )
        self.assertTrue(any(not d.delivered for d in deliveries))
        responses,_,_,_=choose_p2r_owner_responses(
            owner_receipts=received,owner_alerts=set(),
            reserved={},previously_deferred=set(),
            robots=3,claim_round=0,owner_decision_policy="cost_first",
        )
        self.assertEqual(responses,[(2,1,True)])

    def test_no_loss_full_matching_original_optimum_still_authorized(self):
        costs=((1.,100.,100.),(100.,1.,100.),(100.,100.,1.))
        rows=same_view()
        run=P2KLocalVoteResult(
            local_assignments=(((0,0),(1,1),(2,2)),)*3,
            robot_claims=((0,0),(1,1),(2,2)),
            local_vote_views=(rows,rows,rows),
            cost_visible_rows=(frozenset(range(3)),)*3,
            events=(),deliveries=(),decision_time_ms=10.,
            cost_completion_ms=5.,
        )
        result=coordinate_p2r_announced_intents(
            run=run,cost_matrix=costs,votes_per_voter=30,
            sampler=FakeSampler(),loss_sampler=NoLoss(),
            p_loss=0.,max_rounds=4,
            intent_repetitions=1,decision_repetitions=1,
            announcement_repetitions=1,
            owner_decision_policy="cost_first",
        )
        self.assertEqual(set(result.executed_pairs),
                         {(0,0),(1,1),(2,2)})
        self.assertEqual(result.rounds_executed,1)
        self.assertIsNone(result.first_diagnostic)


if __name__=="__main__":
    unittest.main()

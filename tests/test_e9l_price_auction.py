from __future__ import annotations

import math,random,unittest

from democracy_mrta.diagnostics import ProtocolError
from democracy_mrta.network import BernoulliLossSampler,SenderPayloadBudget
from democracy_mrta.price_auction import (
    BID_PHASE,AWARD_PHASE,PACKET,
    PriceBid,PriceAward,initialize_price_auction,propose_price_bid,
    accept_price_award,encode_price_bid,encode_price_award,
    price_auction_local_certified,simulate_price_auction,
)

class ConstantLatency:
    def sample_ms(self, key: str) -> float:
        return 1.0

def matrix(n:int,seed:int=0):
    rng=random.Random(seed)
    robots=[(rng.uniform(0,100),rng.uniform(0,100)) for _ in range(n)]
    tasks=[(rng.uniform(0,100),rng.uniform(0,100)) for _ in range(n)]
    return tuple(tuple(math.dist(robot,task) for task in tasks)
                 for robot in robots)

class E9LPriceAuctionTests(unittest.TestCase):
    def run_auction(self,costs,*,bid_loss=.30,award_loss=.30,epsilon=10.0,
                    rounds=160,capture=False,budget=None):
        return simulate_price_auction(
            cost_matrix=costs,sampler=ConstantLatency(),
            loss_sampler=BernoulliLossSampler(seed=17),
            bid_loss=bid_loss,award_loss=award_loss,epsilon=epsilon,
            stage_window_ms=12,safety_rounds=rounds,
            capture_audit=capture,send_budget=budget,
        )

    def test_packet_struct_is_native_28b_no_hidden_full_vector(self):
        bid=PriceBid(3,2,100.2,0,1)
        award=PriceAward(2,3,100.2,1,1)
        self.assertEqual(len(encode_price_bid(bid)),28)
        self.assertEqual(len(encode_price_award(award)),28)
        self.assertEqual(PACKET.size,28)
        self.assertNotEqual(encode_price_bid(bid),encode_price_award(award))

    def test_original_epsilon_bid_increases_local_best_price(self):
        bidders,_=initialize_price_auction(((1.,3.,100.),(1.,2.,3.),(3.,2.,1.)))
        bid=propose_price_bid(bidders[0],iteration=0,epsilon=10.0)
        self.assertEqual(bid.task,0)
        self.assertAlmostEqual(bid.offered_price,12.0)
        self.assertEqual(bid.observed_version,0)

    def test_one_unresolved_bid_per_robot_and_versioned_resolution(self):
        bidder=initialize_price_auction(((1.,3.),(3.,1.)))[0][0]
        bid=propose_price_bid(bidder,iteration=0,epsilon=2.)
        bidder.pending=bid
        next_bid=propose_price_bid(bidder,iteration=1,epsilon=2.)
        self.assertEqual(next_bid,bid)
        accept_price_award(bidder=bidder,award=PriceAward(0,1,0.2,0,1))
        self.assertEqual(bidder.pending,bid)
        accept_price_award(bidder=bidder,award=PriceAward(0,0,bid.offered_price,1,2))
        self.assertIsNone(bidder.pending)
        self.assertEqual(bidder.winners[0],0)

    def test_no_loss_reaches_bijection(self):
        result=self.run_auction(matrix(5),bid_loss=0.,award_loss=0.,capture=True)
        self.assertTrue(result.optimistic_local_stop)
        self.assertTrue(result.observer_full)
        self.assertEqual(result.local_certified_count,5)
        self.assertEqual(len(result.assignment),5)
        self.assertEqual(len({r for r,j in result.assignment}),5)
        self.assertEqual(result.sender_bytes,28*(result.bid_sends+result.award_sends))
        self.assertEqual(result.delivery_attempts,
                         result.bid_sends+result.award_sends*4)
        events=[e for e in result.audit_events if e.phase==AWARD_PHASE]
        self.assertEqual(len(events),result.award_sends)

    def test_30percent_receiver_loss_preserves_wire_ledger(self):
        result=self.run_auction(matrix(10),capture=True)
        self.assertTrue(result.optimistic_local_stop)
        self.assertTrue(result.observer_full)
        self.assertGreater(result.delivery_drops,0)
        self.assertEqual(len(result.audit_events),result.bid_sends+result.award_sends)
        self.assertEqual(len(result.audit_deliveries),result.delivery_attempts)
        self.assertEqual(result.sender_bytes,28*(result.bid_sends+result.award_sends))

    def test_total_loss_does_not_fabricate_local_certification(self):
        result=self.run_auction(matrix(5),bid_loss=1.,award_loss=1.,rounds=12)
        self.assertFalse(result.optimistic_local_stop)
        self.assertEqual(result.stop_reason,"round_safety_guard")
        self.assertEqual(result.local_certified_count,0)
        self.assertGreater(result.delivery_drops,0)

    def test_costs_and_stage_validation_have_named_diagnostics(self):
        with self.assertRaises(ProtocolError) as ctx:
            self.run_auction(((1.,2.),(1.,2.)),epsilon=-.1)
        self.assertEqual((ctx.exception.diagnostic.owner,
                          ctx.exception.diagnostic.function,
                          ctx.exception.diagnostic.category,
                          ctx.exception.diagnostic.code),(
            "democracy_mrta.price_auction",
            "validate_price_auction_configuration","data","E9L_INVALID_EPSILON",
        ))
        with self.assertRaises(ProtocolError) as ctx:
            self.run_auction(((1.,),))
        self.assertEqual(ctx.exception.diagnostic.code,"E9L_REQUIRES_SQUARE_ONE_TASK_CAPACITY")

    def test_original_sender_budget_censors_without_phantom_packets(self):
        budget=SenderPayloadBudget(140)
        out=self.run_auction(matrix(5),budget=budget,rounds=20,capture=True)
        self.assertIn("sender_budget_exhausted",out.stop_reason)
        self.assertEqual(out.sender_bytes,budget.sent_bytes)
        self.assertEqual(out.bid_sends+out.award_sends,budget.sent_messages)
        self.assertEqual(out.delivery_attempts,len(out.audit_deliveries))

if __name__=="__main__":unittest.main()

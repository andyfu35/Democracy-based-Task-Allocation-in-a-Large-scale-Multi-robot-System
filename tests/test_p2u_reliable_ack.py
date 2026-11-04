"""P2U reliable status/ACK and causal packet-release regression tests."""
import unittest

from democracy_mrta.claim_resolution import (
    P2LClaim, P2TIntent, P2UStatus, P2U_OFFER, P2U_EXECUTED, P2U_IDLE,
    encode_p2u_status, decode_p2u_status, transmit_p2u_reliable_statuses,
    select_p2u_ready_peer_candidates, encode_p2u_ack,
    encode_p2u_ack_bitmap, decode_p2u_ack_bitmap,
    transmit_p2u_reliable_statuses_bitmap,
)
from democracy_mrta.network import WifiCausalTimingSampler


class FakeSampler:
    def sample_ms(self, key):
        return 1.0


class StrictCausalSampler(WifiCausalTimingSampler):
    """Represent E9G release ordering without needing a Rady dataset."""
    def __init__(self):
        self.last_release = 0.0
        self.releases = []

    def sample_packet_ms(self, *, key, phase, sender_id,
                         receiver_id, send_time_ms, payload_bytes):
        if send_time_ms + 1e-9 < self.last_release:
            raise AssertionError(
                f"noncausal release={send_time_ms}, previous={self.last_release}"
            )
        self.last_release = send_time_ms
        self.releases.append((phase, send_time_ms))
        return 1.0


class FakeLoss:
    def is_delivered(self, key, p_loss):
        # A dropped first status receiver copy and one dropped ACK.
        return not (
            ("broadcast|p2u_status|1|0|" in key and "copy=1" not in key)
            or ("unicast|p2u_ack|" in key and "round=2" in key)
        )


class NoLoss:
    def is_delivered(self, key, p_loss):
        return True


class P2UReliableTests(unittest.TestCase):
    def offer(self, robot, task):
        return P2UStatus(
            P2TIntent(P2LClaim(0,robot,task,10,1,10),1.0+robot),
            P2U_OFFER,
        )

    def test_round_status_and_ack_packet_sizes(self):
        item=self.offer(1,1)
        wire=encode_p2u_status(item)
        self.assertEqual(len(wire),40)
        self.assertEqual(decode_p2u_status(
            wire,sender_id=1,claim_round=0,robots=3,tasks=3,
            tickets_per_task=10,
        ),item)
        self.assertEqual(len(encode_p2u_ack(
            claim_round=0,receiver=0,sender=1,
        )),16)

    def test_retransmission_charges_each_broadcast_and_ack(self):
        statuses=tuple(self.offer(i,i) for i in range(3))
        events,deliveries,views,end=transmit_p2u_reliable_statuses(
            statuses=statuses,robots=3,tasks=3,votes_per_voter=30,
            max_ack_retries=4,start_ms=0.0,
            sampler=FakeSampler(),loss_sampler=FakeLoss(),p_loss=0.3,
        )
        self.assertEqual(len(views[0]),3)
        self.assertTrue(any(e.phase=="p2u_ack" for e in events))
        self.assertTrue(any(e.phase=="p2u_status" for e in events))
        self.assertTrue(any(not d.delivered for d in deliveries))
        self.assertGreater(len(events),3)
        self.assertGreater(end,0.0)

    def test_wifi_causal_status_and_ack_release_order(self):
        statuses=tuple(self.offer(i,i) for i in range(3))
        sampler=StrictCausalSampler()
        events,deliveries,views,end=transmit_p2u_reliable_statuses(
            statuses=statuses,robots=3,tasks=3,votes_per_voter=30,
            max_ack_retries=2,start_ms=10.0,
            sampler=sampler,loss_sampler=NoLoss(),p_loss=0.0,
        )
        self.assertTrue(all(len(view)==3 for view in views.values()))
        self.assertEqual(len([e for e in events if e.phase=="p2u_status"]),3)
        self.assertEqual(len([e for e in events if e.phase=="p2u_ack"]),6)
        self.assertEqual(len(sampler.releases),len(events))
        self.assertGreater(end,10.0)
        self.assertEqual(
            [event.send_time_ms for event in events],
            [release for _,release in sampler.releases],
        )

    def test_bitmap_ack_exact_wire_and_identity(self):
        seen=frozenset({0,2,4})
        packet=encode_p2u_ack_bitmap(
            claim_round=4,receiver=2,robots=5,
            received_sender_ids=seen,
        )
        self.assertEqual(len(packet),17)
        self.assertEqual(
            decode_p2u_ack_bitmap(
                packet,claim_round=4,receiver=2,robots=5,
            ),seen,
        )
        from democracy_mrta.diagnostics import ProtocolError
        with self.assertRaises(ProtocolError):
            decode_p2u_ack_bitmap(
                packet,claim_round=4,receiver=1,robots=5,
            )

    def test_zero_loss_100_robots_emits_100_bitmap_ack_not_9900(self):
        statuses=tuple(self.offer(i,i) for i in range(100))
        sampler=StrictCausalSampler()
        events,deliveries,views,end=transmit_p2u_reliable_statuses_bitmap(
            statuses=statuses,robots=100,tasks=100,
            votes_per_voter=1000,max_ack_retries=24,start_ms=0.0,
            sampler=sampler,loss_sampler=NoLoss(),p_loss=0.0,
        )
        statuses_sent=[e for e in events if e.phase=="p2u_status"]
        acks=[e for e in events if e.phase=="p2u_ack_bitmap"]
        self.assertEqual(len(statuses_sent),100)
        self.assertEqual(len(acks),100)
        self.assertEqual({e.payload_bytes for e in statuses_sent},{40})
        self.assertEqual({e.payload_bytes for e in acks},{29})
        self.assertTrue(all(len(known)==100 for known in views.values()))
        self.assertEqual(len(events),200)
        self.assertEqual(sum(e.payload_bytes for e in events),6900)
        self.assertEqual(len(sampler.releases),200)
        self.assertGreater(end,0.0)

    def test_bitmap_ack_lost_data_and_lost_bitmap_retries(self):
        class SelectiveDrop:
            def is_delivered(self,key,p_loss):
                return not (
                    ("broadcast|p2u_status|1|0|1|round=1" in key
                     and "copy=1" not in key)
                    or ("broadcast|p2u_ack_bitmap|0|1|-|round=1" in key
                        and "copy=1" not in key)
                )

        statuses=tuple(self.offer(i,i) for i in range(3))
        sampler=StrictCausalSampler()
        events,receipts,views,end=transmit_p2u_reliable_statuses_bitmap(
            statuses=statuses,robots=3,tasks=3,
            votes_per_voter=30,max_ack_retries=5,start_ms=0.0,
            sampler=sampler,loss_sampler=SelectiveDrop(),p_loss=0.3,
        )
        self.assertTrue(any(not d.delivered for d in receipts))
        self.assertTrue(all(len(known)==3 for known in views.values()))
        self.assertGreater(sum(e.phase=="p2u_status" for e in events),3)
        self.assertTrue(any(e.transmission_index for e in events))
        self.assertTrue(all(
            events[i].send_time_ms<=events[i+1].send_time_ms
            for i in range(len(events)-1)
        ))

    def test_missing_roster_blocks_candidate_self_execution(self):
        a=self.offer(0,0).intent
        b=self.offer(1,0).intent
        views={0:{0:P2UStatus(a,P2U_OFFER)},
               1:{1:P2UStatus(b,P2U_OFFER),0:P2UStatus(a,P2U_OFFER)}}
        ready,blocked,offers,known=select_p2u_ready_peer_candidates(
            intents=(a,b),views=views,robots=3,
        )
        self.assertEqual(ready,())
        self.assertEqual(blocked,())

    def test_executed_status_reaches_already_finished_receiver(self):
        executed=P2UStatus(self.offer(0,0).intent,P2U_EXECUTED)
        # Receiver 2 has finished its own task. Physical P2US receipts
        # still update its local task-knowledge cache for the offline audit.
        ready,blocked,offers,known=select_p2u_ready_peer_candidates(
            intents=(),views={2:{0:executed}},robots=3,
        )
        self.assertEqual(ready,())
        self.assertEqual(blocked,())
        self.assertEqual(known[2],{0})

    def test_completed_status_prevents_later_reclaim(self):
        candidate=self.offer(1,0).intent
        done=P2UStatus(self.offer(0,0).intent,P2U_EXECUTED)
        idle=P2UStatus(P2TIntent(P2LClaim(0,2,None,0,0,10),0),P2U_IDLE)
        views={1:{0:done,1:P2UStatus(candidate,P2U_OFFER),2:idle}}
        ready,blocked,_,seen=select_p2u_ready_peer_candidates(
            intents=(candidate,),views=views,robots=3,
        )
        self.assertEqual(ready,())
        self.assertEqual(blocked,(candidate,))
        self.assertEqual(seen[1],{0})


if __name__=="__main__":
    unittest.main()

"""P2I ACK/retry transport invariants; original one-shot defaults stay unchanged."""
import unittest

from democracy_mrta.coordination import (
    encode_reliable_receipt_bitmap,
    decode_reliable_receipt_bitmap,
    transmit_acknowledged_broadcast_phase,
    validate_ack_retry_scope,
    capture_retirement_cost_snapshot,
    simulate_democracy_hungarian_retirement,
)
from democracy_mrta.diagnostics import ProtocolError
from democracy_mrta.network import (
    BernoulliLossSampler, EmpiricalLatencyProfile, WifiCausalTimingSampler,
    WifiTimingConfig,
)
from experiments.run_p2i_reliable_transport import validate_config, summarize
from types import SimpleNamespace


def profile():
    return EmpiricalLatencyProfile(
        source_repository="test", source_commit="test", source_blob_sha="0"*40,
        location="2", location_label="synthetic", config="ax_160mhz_6ghz",
        config_label="synthetic", steady_start_s=0.0, steady_end_s=4.0,
        samples_ms=(3.0,4.0,5.0,6.0),
    )


class P2IReliableTransportTests(unittest.TestCase):
    def test_ack_bitmap_exact_round_trip_and_identity(self):
        ids=(0,1,2,3,4,5,6,7,8,9)
        wire=encode_reliable_receipt_bitmap(
            sender_ids=ids,received=frozenset((0,2,8)),
            receiver_id=3,round_id=7,
        )
        self.assertEqual(len(wire),18)
        self.assertEqual(
            decode_reliable_receipt_bitmap(
                wire,sender_ids=ids,receiver_id=3,round_id=7),
            frozenset((0,2,8)),
        )
        with self.assertRaises(ProtocolError) as error:
            decode_reliable_receipt_bitmap(
                wire,sender_ids=ids,receiver_id=4,round_id=7)
        self.assertEqual(error.exception.diagnostic.code,"P2I_ACK_IDENTITY_MISMATCH")

    def test_scope_rejects_reliable_vote_without_cost(self):
        with self.assertRaises(ProtocolError) as error:
            validate_ack_retry_scope(
                reliable_cost=False,reliable_vote=True,retry_limit=300,
                voting_strategy="greedy_batch",preknown_snapshot=None,
                send_budget=None)
        self.assertEqual(error.exception.diagnostic.code,"P2I_RELIABLE_SCOPE_MISMATCH")

    def test_paid_data_and_ack_and_real_missing_loss_are_causal(self):
        sampler=WifiCausalTimingSampler(profile(),11,WifiTimingConfig(phy_rate_mbps=144.0))
        events,receipts,seen,end=transmit_acknowledged_broadcast_phase(
            phase="cost",sender_ids=(0,1,2),receiver_ids=(0,1,2),
            payload_bytes_by_sender={0:40,1:40,2:40},
            round_id=0,start_ms=0,retry_limit=10,sampler=sampler,
            loss_sampler=BernoulliLossSampler(11),p_loss=0.0)
        self.assertEqual(sum(e.phase=="cost" for e in events),3)
        self.assertEqual(sum(e.phase=="cost_ack" for e in events),3)
        self.assertTrue(all(seen[receiver]==frozenset((0,1,2))
                            for receiver in range(3)))
        self.assertEqual(len(receipts),6)
        self.assertGreaterEqual(end,max(e.arrival_time_ms for e in events))
        self.assertEqual(sum(e.payload_bytes for e in events),
                         sampler.summarize_network()["application_sender_bytes"])

    def test_retries_at_total_loss_are_never_faked_as_success(self):
        sampler=WifiCausalTimingSampler(profile(),11,WifiTimingConfig(phy_rate_mbps=144.0))
        with self.assertRaises(ProtocolError) as error:
            transmit_acknowledged_broadcast_phase(
                phase="cost",sender_ids=(0,1),receiver_ids=(0,1),
                payload_bytes_by_sender={0:32,1:32},
                round_id=0,start_ms=0,retry_limit=3,sampler=sampler,
                loss_sampler=BernoulliLossSampler(11),p_loss=1.0)
        self.assertEqual(error.exception.diagnostic.category,"time")
        self.assertEqual(error.exception.diagnostic.code,"P2I_ACK_RETRY_LIMIT_REACHED")
        ledger=sampler.summarize_network()
        self.assertEqual(ledger["sender_by_phase"]["cost"]["sender_sends"],6)
        self.assertEqual(ledger["sender_by_phase"]["cost_ack"]["sender_sends"],6)

    def test_old_default_cost_has_no_ack(self):
        sampler=WifiCausalTimingSampler(profile(),0,WifiTimingConfig(phy_rate_mbps=144.0))
        snapshot=capture_retirement_cost_snapshot(
            cost_matrix=((1.0,2.0),(2.0,1.0)),sampler=sampler,
            loss_sampler=BernoulliLossSampler(0),p_loss=0.0,
            phase_timeout_ms=1000.0)
        self.assertEqual(len(snapshot.events),2)
        self.assertFalse(any(e.phase.endswith("_ack") for e in snapshot.events))

    def test_frozen_formal_grid(self):
        args=SimpleNamespace(losses="0.00,0.90",seeds=2,
                             first_seed=0,retry_limit=300,formal=False)
        self.assertEqual(validate_config(args),(0,90))
        args.formal=True
        with self.assertRaises(ProtocolError) as error:
            validate_config(args)
        self.assertEqual(error.exception.diagnostic.code,"P2I_FORMAL_GRID_CHANGED")


if __name__=="__main__":
    unittest.main()

"""E9K paid READY/COMMIT protocol; real inbox evidence, no free halt gate."""
from __future__ import annotations

import unittest

from democracy_mrta.cbaa import simulate_cbaa
from democracy_mrta.cbaa_finalization import (
    CONTROL_PAYLOAD_BYTES, READY_PHASE, COMMIT_PHASE,
    create_paid_cbaa_finalization,
    exchange_paid_cbaa_control_packets,
)
from democracy_mrta.diagnostics import ProtocolError
from democracy_mrta.network import BernoulliLossSampler


class FixedLatency:
    def sample_ms(self, key: str) -> float:
        return 2.0


class PhaseDrop:
    """Pure deterministic source: drop specified phase only."""
    def __init__(self, forbidden_phase: str):
        self.forbidden_phase = forbidden_phase

    def is_delivered(self, key: str, p_loss: float) -> bool:
        return self.forbidden_phase not in key


class PaidFinalizationTests(unittest.TestCase):
    costs = ((1.0, 10.0), (10.0, 1.0))

    def run_paid(self, *, loss_sampler=None, ready_loss=.0, commit_loss=.0,
                 bid_loss=.0, guard=20, audit=True, budget=None):
        return simulate_cbaa(
            cost_matrix=self.costs, sampler=FixedLatency(),
            loss_sampler=loss_sampler or BernoulliLossSampler(seed=17),
            loss_probability=bid_loss, phase_timeout_ms=10.0,
            control_timeout_ms=10.0,
            ready_loss_probability=ready_loss,
            commit_loss_probability=commit_loss,
            max_iterations=guard, stop_mode="paid_termination",
            capture_audit=audit, send_budget=budget,
        )

    def test_zero_loss_requires_real_ready_and_commit_packets(self):
        old = simulate_cbaa(
            cost_matrix=self.costs, sampler=FixedLatency(),
            loss_sampler=BernoulliLossSampler(seed=17),
            loss_probability=0.0, phase_timeout_ms=10.0,
            max_iterations=20, stop_mode="local_certification",
        )
        paid = self.run_paid()
        self.assertEqual(old.stop_reason, "all_local_evidence_certified")
        self.assertEqual(paid.stop_reason, "all_paid_commit_proofs_received")
        self.assertTrue(paid.paid_termination_complete)
        self.assertEqual(paid.paid_confirmed_robots, 2)
        self.assertEqual(paid.observer_agreed_pairs, ((0, 0), (1, 1)))
        self.assertGreaterEqual(paid.iterations, old.iterations)
        self.assertGreater(paid.elapsed_ms, old.elapsed_ms)
        self.assertGreater(paid.paid_control_elapsed_ms, 0)
        self.assertGreater(paid.paid_sender_bytes, 0)
        self.assertEqual(paid.paid_receiver_attempts,
                         (paid.paid_ready_sends + paid.paid_commit_sends))
        events = [x for x in paid.audit_events
                  if x.phase in (READY_PHASE, COMMIT_PHASE)]
        self.assertEqual(len(events),
                         paid.paid_ready_sends + paid.paid_commit_sends)
        self.assertEqual(sum(e.payload_bytes for e in events),
                         paid.paid_sender_bytes)
        self.assertTrue(all(x.payload_bytes == CONTROL_PAYLOAD_BYTES
                            for x in events))
        self.assertTrue(any(x.phase == READY_PHASE for x in events))
        self.assertTrue(any(x.phase == COMMIT_PHASE for x in events))
        self.assertEqual(paid.payload_bytes,
                         paid.logical_message_count * (16 + 2 * 12))

    def test_ready_always_lost_blocks_commit_and_certification(self):
        outcome = self.run_paid(ready_loss=1.0)
        self.assertFalse(outcome.paid_termination_complete)
        self.assertNotEqual(outcome.stop_reason,
                            "all_paid_commit_proofs_received")
        self.assertEqual(outcome.paid_commit_sends, 0)
        self.assertGreater(outcome.paid_ready_sends, 0)
        self.assertGreater(outcome.paid_receiver_drops, 0)
        self.assertEqual(outcome.paid_confirmed_robots, 0)
        self.assertTrue(outcome.full_observer_agreement)

    def test_commit_always_lost_blocks_paid_finalization(self):
        outcome = self.run_paid(commit_loss=1.0, guard=16)
        self.assertFalse(outcome.paid_termination_complete)
        self.assertGreater(outcome.paid_commit_sends, 0)
        self.assertEqual(outcome.paid_confirmed_robots, 0)
        self.assertEqual(outcome.stop_reason, "paid_termination_safety_guard")

    def test_lost_native_consensus_cannot_be_repaired_by_control(self):
        out = self.run_paid(bid_loss=1.0, guard=7)
        self.assertFalse(out.paid_termination_complete)
        self.assertEqual(out.paid_ready_sends, 0)
        self.assertEqual(out.paid_commit_sends, 0)

    def test_independent_loss_30pct_is_reproducible(self):
        a = self.run_paid(bid_loss=.30, ready_loss=.30,
                          commit_loss=.30, guard=45, audit=False)
        b = self.run_paid(bid_loss=.30, ready_loss=.30,
                          commit_loss=.30, guard=45, audit=False)
        self.assertEqual(a, b)
        self.assertEqual(
            a.paid_receiver_attempts,
            (a.paid_ready_sends+a.paid_commit_sends),
        )
        self.assertGreaterEqual(a.paid_receiver_drops, 0)

    def test_invalid_control_window_fails_named_owner(self):
        with self.assertRaises(ProtocolError) as err:
            simulate_cbaa(
                cost_matrix=self.costs, sampler=FixedLatency(),
                loss_sampler=BernoulliLossSampler(seed=2),
                loss_probability=.30, phase_timeout_ms=10.0,
                max_iterations=10, stop_mode="paid_termination",
                control_timeout_ms=-1.0,
            )
        d=err.exception.diagnostic
        self.assertEqual((d.owner,d.function,d.category,d.code),(
            "democracy_mrta.cbaa_finalization",
            "validate_paid_cbaa_finalization_config",
            "time","E9K_INVALID_CONTROL_TIMEOUT",
        ))

    def test_control_knobs_cannot_change_legacy_cbaa(self):
        with self.assertRaises(ProtocolError) as err:
            simulate_cbaa(
                cost_matrix=self.costs, sampler=FixedLatency(),
                loss_sampler=BernoulliLossSampler(seed=2),
                loss_probability=0.0, phase_timeout_ms=10.0,
                max_iterations=10, stop_mode="local_certification",
                ready_loss_probability=.30,
            )
        self.assertEqual(err.exception.diagnostic.code,
                         "E9K_CONTROL_OPTIONS_REQUIRE_PAID_MODE")

    def test_no_unsent_control_proof(self):
        proof=create_paid_cbaa_finalization(2)
        # Two empty nodes cannot send COMMIT merely because the observer
        # thinks their latent state is converged.
        with self.assertRaises(ProtocolError) as err:
            exchange_paid_cbaa_control_packets(
                proof=proof, eligible=(True,False), phase=READY_PHASE,
                iteration=1, start_ms=0, timeout_ms=10,
                sampler=FixedLatency(),
                loss_sampler=BernoulliLossSampler(seed=0),
                loss_probability=.0, capture_audit=False,send_budget=None,
            )
        self.assertEqual(err.exception.diagnostic.code,
                         "E9K_CONTROL_WITHOUT_LOCAL_CERTIFICATE")


if __name__ == "__main__":
    unittest.main()

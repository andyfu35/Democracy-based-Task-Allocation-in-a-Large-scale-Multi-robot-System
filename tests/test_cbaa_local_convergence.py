"""E9D-1: peer-receipt-only local CBAA convergence, no observer oracle."""
from __future__ import annotations

import unittest
from unittest.mock import patch

from democracy_mrta.cbaa import (
    CBAALocalState, cbaa_local_convergence_certified,
    simulate_cbaa,
)
from democracy_mrta.diagnostics import ProtocolError
from democracy_mrta.network import BernoulliLossSampler, SenderPayloadBudget


class ImmediateLatency:
    def sample_ms(self, key: str) -> float:
        return 1.0


def run_auto(costs, *, p=0.0, seed=4, guard=80, budget=None, audit=False, mode="local_certification"):
    return simulate_cbaa(
        cost_matrix=costs, sampler=ImmediateLatency(),
        loss_sampler=BernoulliLossSampler(seed=seed),
        loss_probability=p, phase_timeout_ms=10.0,
        max_iterations=guard, stop_mode=mode,
        capture_audit=audit, send_budget=budget,
    )


class CBAALocalConvergenceTests(unittest.TestCase):
    def test_no_loss_all_agents_local_proof_stop_without_fixed_k(self):
        result = run_auto(((1.0, 10.0), (10.0, 1.0)), audit=True)
        self.assertEqual(result.stop_mode, "local_certification")
        self.assertEqual(result.stop_reason, "all_local_evidence_certified")
        self.assertEqual(result.locally_certified_count, 2)
        self.assertTrue(result.full_observer_agreement)
        self.assertLess(result.iterations, 80)
        self.assertEqual(result.logical_message_count, 2 * result.iterations)
        self.assertEqual(result.payload_bytes, 40 * result.logical_message_count)
        self.assertEqual(result.delivery_attempts, result.logical_message_count)
        self.assertFalse(any(event.phase == "commit" for event in result.audit_events))

    def test_origin_auction_conflict_is_resolved_before_local_certificate(self):
        result = run_auto(((1.0, 20.0), (1.1, 100.0)), guard=30)
        self.assertEqual(result.stop_reason, "all_local_evidence_certified")
        self.assertGreaterEqual(result.iterations, 2)
        self.assertEqual(result.observer_agreed_pairs, ((0, 0), (1, 1)))

    def test_local_certificate_requires_physically_received_peer_evidence(self):
        node = CBAALocalState(0, 0, (0.5, 0.25), (0, 1))
        peer = CBAALocalState(1, 1, (0.5, 0.25), (0, 1))
        self.assertFalse(cbaa_local_convergence_certified(
            state=node, peer_view={}, peers=2, own_last_change_iteration=0,
        ))
        self.assertFalse(cbaa_local_convergence_certified(
            state=node, peer_view={1:(0, peer)}, peers=2, own_last_change_iteration=0,
        ))
        self.assertFalse(cbaa_local_convergence_certified(
            state=node, peer_view={1:(1, CBAALocalState(1, 0, (0.5,0.25),(0,1)))},
            peers=2, own_last_change_iteration=0,
        ))
        self.assertTrue(cbaa_local_convergence_certified(
            state=node, peer_view={1:(1, peer)}, peers=2, own_last_change_iteration=0,
        ))

    def test_total_loss_must_stop_at_safety_guard_not_claim_completion(self):
        result = run_auto(((1.0, 20.0), (1.1, 100.0)), p=1.0, guard=6)
        self.assertEqual(result.stop_reason, "iteration_safety_guard")
        self.assertEqual(result.iterations, 6)
        self.assertEqual(result.locally_certified_count, 0)
        self.assertFalse(result.full_observer_agreement)
        self.assertEqual(result.delivery_drops, result.delivery_attempts)

    def test_partial_loss_recovery_is_deterministic_with_physically_paid_sends(self):
        costs = ((1.0, 20.0), (1.1, 100.0), (100.0, 1.0))
        a=run_auto(costs, p=0.5, seed=7, guard=90)
        b=run_auto(costs, p=0.5, seed=7, guard=90)
        self.assertEqual(a,b)
        self.assertEqual(a.payload_bytes, a.logical_message_count*(16+2*(8+4)))
        self.assertEqual(a.delivery_attempts, a.logical_message_count*2)
        self.assertTrue(a.full_observer_agreement)
        self.assertEqual(a.stop_reason, "all_local_evidence_certified")

    def test_observer_is_only_called_after_all_auctions_finish(self):
        with patch("democracy_mrta.cbaa.audit_cbaa_local_agreement", wraps=__import__(
            "democracy_mrta.cbaa", fromlist=["audit_cbaa_local_agreement"]
        ).audit_cbaa_local_agreement) as audit:
            result = run_auto(((1.0,10.0),(10.0,1.0)))
            self.assertEqual(audit.call_count, 1)
            self.assertEqual(result.stop_reason,"all_local_evidence_certified")

    def test_sender_budget_exhaustion_has_priority_over_local_stop(self):
        budget=SenderPayloadBudget(0)
        result=run_auto(((1.0,10.0),(10.0,1.0)), budget=budget)
        self.assertEqual(result.stop_reason,"sender_budget_exhausted")
        self.assertEqual(result.iterations,0)
        self.assertTrue(result.budget_exhausted)
        self.assertEqual(result.locally_certified_count,0)

    def test_invalid_stop_mode_first_cbaa_data_boundary(self):
        with self.assertRaises(ProtocolError) as cm:
            run_auto(((1.0,),),mode="oracle_terminate")
        d=cm.exception.diagnostic
        self.assertEqual(
            (d.owner,d.function,d.category,d.code),
            ("democracy_mrta.cbaa","validate_cbaa_stop_mode","data","CBAA_UNKNOWN_STOP_MODE"),
        )

    def test_original_fixed_iteration_mode_default_unchanged(self):
        a=run_auto(((1.0,10.0),(10.0,1.0)),guard=5,mode="fixed")
        self.assertEqual((a.iterations,a.stop_reason,a.locally_certified_count),
                         (5,"fixed_iteration_budget",0))
        self.assertEqual(a.logical_message_count,10)


if __name__=="__main__":
    unittest.main()

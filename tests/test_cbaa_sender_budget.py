"""E9B-3: sender-capped CBAA retains only actually transmitted bid vectors."""
from __future__ import annotations

import unittest

from democracy_mrta.cbaa import simulate_cbaa
from democracy_mrta.diagnostics import ProtocolError
from democracy_mrta.network import BernoulliLossSampler, SenderPayloadBudget


COSTS = ((1.0, 10.0), (10.0, 1.0))
PACKET_BYTES = 16 + 2 * (8 + 4)
TIMEOUT_MS = 10.0


class ConstantLatency:
    def __init__(self):
        self.sample_calls = []

    def sample_ms(self, key: str) -> float:
        self.sample_calls.append(key)
        return 5.0


def run_cbaa(*, cap=None, costs=COSTS, p=0.0, iterations=3, audit=True):
    budget = None if cap is None else SenderPayloadBudget(cap)
    delay = ConstantLatency()
    result = simulate_cbaa(
        cost_matrix=costs, sampler=delay,
        loss_sampler=BernoulliLossSampler(seed=11),
        loss_probability=p, phase_timeout_ms=TIMEOUT_MS,
        max_iterations=iterations, capture_audit=audit,
        send_budget=budget,
    )
    return result, budget, delay


class CBAASenderBudgetTests(unittest.TestCase):
    def check_physical(self, result, budget):
        self.assertLessEqual(result.payload_bytes, budget.limit_bytes)
        self.assertEqual(
            (result.logical_message_count, result.payload_bytes),
            (budget.sent_messages, budget.sent_bytes),
        )
        self.assertEqual(len(result.audit_events), budget.sent_messages)
        self.assertEqual(
            sum(e.payload_bytes for e in result.audit_events), budget.sent_bytes,
        )
        robots = len(result.states)
        self.assertEqual(result.delivery_attempts,
                         result.logical_message_count * (robots - 1))
        self.assertEqual(len(result.audit_deliveries), result.delivery_attempts)
        self.assertTrue(all(e.phase == "cbaa_consensus" for e in result.audit_events))
        self.assertTrue(all(e.receiver_id == -1 for e in result.audit_events))

    def test_zero_cap_has_no_auction_round_and_no_packet(self):
        result, budget, delay = run_cbaa(cap=0)
        self.check_physical(result, budget)
        self.assertEqual((result.iterations, result.elapsed_ms), (0, 0.0))
        self.assertEqual((result.logical_message_count, result.delivery_attempts), (0, 0))
        self.assertEqual(result.local_claims, ())
        self.assertEqual(result.observer_agreed_pairs, ())
        self.assertEqual(result.conflicting_task_ids, ())
        self.assertEqual(result.unconfirmed_task_ids, (0, 1))
        self.assertFalse(result.full_observer_agreement)
        self.assertTrue(result.budget_exhausted)
        self.assertEqual(result.budget_stop_phase, "cbaa_consensus")
        diagnostic = result.budget_stop_diagnostic
        self.assertEqual((diagnostic.owner, diagnostic.function, diagnostic.category, diagnostic.code),
            ("network", "reserve_sender_payload", "runtime", "SEND_PAYLOAD_BUDGET_EXHAUSTED"))
        self.assertEqual((budget.sent_messages, budget.denied_messages), (0, 1))
        self.assertEqual(delay.sample_calls, [])

    def test_undersized_first_packet_never_samples_network(self):
        result, budget, delay = run_cbaa(cap=PACKET_BYTES - 1)
        self.check_physical(result, budget)
        self.assertEqual((result.iterations, result.elapsed_ms), (0, 0.0))
        self.assertEqual((budget.sent_bytes, budget.remaining_bytes), (0, PACKET_BYTES - 1))
        self.assertEqual(delay.sample_calls, [])

    def test_one_packet_partial_round_has_real_receiver_local_update(self):
        result, budget, delay = run_cbaa(cap=PACKET_BYTES)
        self.check_physical(result, budget)
        self.assertEqual((result.iterations, result.elapsed_ms), (1, TIMEOUT_MS))
        self.assertEqual((result.logical_message_count, result.payload_bytes), (1, PACKET_BYTES))
        self.assertEqual((result.delivery_attempts, result.delivery_drops), (1, 0))
        self.assertEqual(len(delay.sample_calls), 1)
        self.assertEqual([(e.sender_id, e.round_id) for e in result.audit_events], [(0, 0)])
        self.assertEqual(
            [(d.sender_id, d.receiver_id, d.delivered) for d in result.audit_deliveries],
            [(0, 1, True)],
        )
        self.assertEqual(result.local_claims, ((0, 0), (1, 1)))
        self.assertEqual(result.states[0].winning_robots, (0, None))
        self.assertEqual(result.states[1].winning_robots, (0, 1))
        self.assertEqual(result.observer_agreed_pairs, ((0, 0),))
        self.assertEqual(result.unconfirmed_task_ids, (1,))
        self.assertTrue(result.budget_exhausted)
        self.assertEqual(budget.denied_messages, 1)

    def test_one_complete_round_then_next_first_send_denied(self):
        result, budget, _ = run_cbaa(cap=2 * PACKET_BYTES)
        self.check_physical(result, budget)
        self.assertEqual((result.iterations, result.elapsed_ms), (1, TIMEOUT_MS))
        self.assertEqual((result.logical_message_count, result.payload_bytes), (2, 80))
        self.assertTrue(result.budget_exhausted)
        self.assertEqual(budget.denied_messages, 1)
        self.assertTrue(result.full_observer_agreement)
        self.assertEqual(result.observer_agreed_pairs, ((0, 0), (1, 1)))
        self.assertFalse(any(e.phase == "commit" for e in result.audit_events))

    def test_partial_second_round_preserves_previous_beliefs(self):
        result, budget, _ = run_cbaa(cap=3 * PACKET_BYTES)
        self.check_physical(result, budget)
        self.assertEqual((result.iterations, result.elapsed_ms), (2, 2 * TIMEOUT_MS))
        self.assertEqual(
            [(e.round_id, e.sender_id) for e in result.audit_events],
            [(0, 0), (0, 1), (1, 0)],
        )
        self.assertEqual((result.logical_message_count, result.payload_bytes), (3, 120))
        self.assertTrue(result.budget_exhausted)
        self.assertEqual(result.observer_agreed_pairs, ((0, 0), (1, 1)))

    def test_full_exact_fit_matches_legacy_result_bit_for_bit(self):
        legacy, _, _ = run_cbaa()
        result, budget, _ = run_cbaa(cap=6 * PACKET_BYTES)
        self.check_physical(result, budget)
        self.assertFalse(result.budget_exhausted)
        self.assertIsNone(result.budget_stop_phase)
        self.assertIsNone(result.budget_stop_diagnostic)
        self.assertEqual((result.iterations, result.elapsed_ms), (3, 3 * TIMEOUT_MS))
        self.assertEqual((budget.sent_messages, budget.sent_bytes, budget.denied_messages), (6, 240, 0))
        self.assertEqual(result, legacy)

    def test_audit_disabled_still_counts_every_physical_packet(self):
        result, budget, _ = run_cbaa(cap=3 * PACKET_BYTES, audit=False)
        self.assertEqual(result.audit_events, ())
        self.assertEqual(result.audit_deliveries, ())
        self.assertEqual((result.logical_message_count, result.payload_bytes), (3, 120))
        self.assertEqual((budget.sent_messages, budget.sent_bytes, budget.denied_messages), (3, 120, 1))
        self.assertEqual(result.delivery_attempts, 3)
        self.assertTrue(result.budget_exhausted)

    def test_total_physical_loss_does_not_trigger_observer_rescue(self):
        result, budget, _ = run_cbaa(
            cap=PACKET_BYTES, costs=((1.0, 10.0), (1.1, 100.0)), p=1.0,
        )
        self.check_physical(result, budget)
        self.assertEqual(result.delivery_drops, 1)
        self.assertEqual(result.local_claims, ((0, 0), (1, 0)))
        self.assertEqual(result.conflicting_task_ids, (0,))
        self.assertEqual(result.observer_agreed_pairs, ())
        self.assertEqual(result.unconfirmed_task_ids, (0, 1))
        self.assertFalse(result.full_observer_agreement)

    def test_invalid_budget_object_fails_before_transmission(self):
        latency = ConstantLatency()
        with self.assertRaises(ProtocolError) as cm:
            simulate_cbaa(
                cost_matrix=COSTS, sampler=latency,
                loss_sampler=BernoulliLossSampler(seed=0),
                loss_probability=0.0, phase_timeout_ms=TIMEOUT_MS,
                max_iterations=3, send_budget=120,
            )
        d = cm.exception.diagnostic
        self.assertEqual((d.owner, d.function, d.category, d.code),
            ("democracy_mrta.cbaa", "validate_cbaa_sender_budget", "data", "CBAA_INVALID_SEND_BUDGET"))
        self.assertEqual(latency.sample_calls, [])


if __name__ == "__main__":
    unittest.main()

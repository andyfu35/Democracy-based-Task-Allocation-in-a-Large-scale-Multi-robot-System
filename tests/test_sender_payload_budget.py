"""E9B-1: opt-in, sender-side application payload admission only.

Runtime abort handling is intentionally NOT added in this stage; a refused
emission is a typed event and never charged as a successful physical SEND.
"""
from __future__ import annotations

import unittest

from democracy_mrta.coordination import _broadcast_event, _unicast_event
from democracy_mrta.diagnostics import ProtocolError
from democracy_mrta.network import (
    SenderBudgetExhausted,
    SenderPayloadBudget,
    reserve_sender_payload,
)


class DelayProbe:
    def __init__(self):
        self.keys = []

    def sample_ms(self, key: str) -> float:
        self.keys.append(key)
        return 5.0


class SenderPayloadBudgetTests(unittest.TestCase):
    def test_budget_accepts_zero_and_rejects_first_physical_packet(self):
        budget = SenderPayloadBudget(0)
        delay = DelayProbe()
        with self.assertRaises(SenderBudgetExhausted) as ctx:
            _broadcast_event(
                phase="cost", sender_id=0, send_time_ms=0.0,
                payload_bytes=24, sampler=delay, send_budget=budget,
            )
        failure = ctx.exception.diagnostic
        self.assertEqual((failure.owner, failure.function, failure.category, failure.code), (
            "network", "reserve_sender_payload", "runtime",
            "SEND_PAYLOAD_BUDGET_EXHAUSTED",
        ))
        self.assertEqual((budget.sent_bytes, budget.sent_messages, budget.denied_messages), (0, 0, 1))
        self.assertEqual(delay.keys, [])

    def test_exact_capacity_counts_broadcast_once_and_unicast_once(self):
        budget = SenderPayloadBudget(56)
        delay = DelayProbe()
        unicast = _unicast_event(
            phase="vote", sender_id=1, receiver_id=4,
            send_time_ms=10.0, payload_bytes=32, sampler=delay,
            send_budget=budget, task_id=0,
        )
        broadcast = _broadcast_event(
            phase="commit", sender_id=4, send_time_ms=20.0,
            payload_bytes=24, sampler=delay, send_budget=budget, task_id=0,
        )
        self.assertEqual((unicast.payload_bytes, broadcast.payload_bytes), (32, 24))
        self.assertEqual((budget.sent_messages, budget.sent_bytes, budget.remaining_bytes), (2, 56, 0))
        self.assertEqual(len(delay.keys), 2)
        with self.assertRaises(SenderBudgetExhausted):
            _unicast_event(
                phase="vote", sender_id=2, receiver_id=4,
                send_time_ms=30.0, payload_bytes=32,
                sampler=delay, send_budget=budget,
            )
        self.assertEqual((budget.sent_messages, budget.sent_bytes, budget.denied_messages), (2, 56, 1))
        self.assertEqual(len(delay.keys), 2)

    def test_crossing_cap_is_not_truncated_to_partial_message(self):
        budget = SenderPayloadBudget(31)
        reserve_sender_payload(budget, payload_bytes=16, phase="test")
        with self.assertRaises(SenderBudgetExhausted):
            reserve_sender_payload(budget, payload_bytes=16, phase="test")
        self.assertEqual((budget.sent_bytes, budget.remaining_bytes), (16, 15))

    def test_bad_limit_is_a_data_failure(self):
        for bad in (-1, True, 1.25, "500"):
            with self.subTest(bad=bad):
                with self.assertRaises(ProtocolError) as ctx:
                    SenderPayloadBudget(bad)
                self.assertEqual(ctx.exception.diagnostic.function, "validate_sender_payload_budget")
                self.assertEqual(ctx.exception.diagnostic.category, "data")

    def test_bad_payload_cannot_consume_budget(self):
        budget = SenderPayloadBudget(200)
        for bad in (0, -1, False, 5.0):
            with self.subTest(bad=bad):
                with self.assertRaises(ProtocolError) as ctx:
                    reserve_sender_payload(budget, payload_bytes=bad, phase="vote")
                self.assertEqual(ctx.exception.diagnostic.code, "INVALID_SENDER_PAYLOAD_SIZE")
        self.assertEqual((budget.sent_bytes, budget.sent_messages), (0, 0))

    def test_missing_opt_in_keeps_legacy_event_identity(self):
        a = _broadcast_event(
            phase="cost", sender_id=3, send_time_ms=1.0,
            payload_bytes=80, sampler=DelayProbe(), round_id=2,
        )
        b = _broadcast_event(
            phase="cost", sender_id=3, send_time_ms=1.0,
            payload_bytes=80, sampler=DelayProbe(), round_id=2,
            send_budget=None,
        )
        self.assertEqual(a, b)
        x = _unicast_event(
            phase="vote", sender_id=2, receiver_id=1,
            send_time_ms=5.0, payload_bytes=32, sampler=DelayProbe(),
            task_id=4, round_id=2,
        )
        y = _unicast_event(
            phase="vote", sender_id=2, receiver_id=1,
            send_time_ms=5.0, payload_bytes=32, sampler=DelayProbe(),
            task_id=4, round_id=2, send_budget=None,
        )
        self.assertEqual(x, y)

    def test_budget_ledgers_are_not_shared_across_runs(self):
        first = SenderPayloadBudget(56)
        second = SenderPayloadBudget(56)
        reserve_sender_payload(first, payload_bytes=32, phase="vote")
        self.assertEqual((first.sent_bytes, second.sent_bytes), (32, 0))


if __name__ == "__main__":
    unittest.main()

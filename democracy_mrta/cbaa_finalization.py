"""E9K optional *paid* distributed CBAA finalization, not original paper CBAA.

This owner handles only READY/COMMIT receipts and causal application SENDs.
It does not decide auction bids, resolve winners, or read another robot's
private state to grant a certificate.  Every peer proof comes from a
physically delivered, on-time packet with a matching assignment digest.

The simulator exits when each robot has its *own* complete COMMIT receipts.
That final observer stop is not common knowledge or a radio ACK protocol:
real-world MAC/PHY, collision, cryptographic authentication and an infinite
common-knowledge handshake remain outside this model.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import math

from .coordination import (
    CommunicationEvent, DeliveryObservation, _broadcast_event,
    _lossy_broadcast_deliveries,
)
from .diagnostics import Diagnostic, ProtocolError
from .network import (
    SenderBudgetExhausted, SenderPayloadBudget,
    validate_packet_loss_probability,
)

OWNER = "democracy_mrta.cbaa_finalization"
READY_PHASE = "cbaa_paid_ready"
COMMIT_PHASE = "cbaa_paid_commit"
CONTROL_PAYLOAD_BYTES = 48  # 16-byte application header + 32-byte SHA256 vector digest


@dataclass
class CBAAPaidFinalization:
    """Only per-robot *received* evidence; no global shared ready flag."""
    expected_digest: list[str | None]
    ready_seen: list[set[int]]
    commit_seen: list[set[int]]
    confirmed: list[bool]


@dataclass(frozen=True)
class CBAAPaidTick:
    ready_sends: int = 0
    commit_sends: int = 0
    bytes_sent: int = 0
    delivery_attempts: int = 0
    delivery_drops: int = 0
    late_deliveries: int = 0
    elapsed_ms: float = 0.0
    audit_events: tuple[CommunicationEvent, ...] = ()
    audit_deliveries: tuple[DeliveryObservation, ...] = ()
    budget_denied: bool = False
    denied_phase: str | None = None


def validate_paid_cbaa_finalization_config(
    *, control_timeout_ms: float, ready_loss: float, commit_loss: float,
) -> None:
    """Time + loss data gate belongs to the finalization owner."""
    if (type(control_timeout_ms) not in (int, float)
        or not math.isfinite(control_timeout_ms) or control_timeout_ms <= 0):
        raise ProtocolError(Diagnostic(
            owner=OWNER, function="validate_paid_cbaa_finalization_config",
            category="time", code="E9K_INVALID_CONTROL_TIMEOUT",
            expected="finite control phase window > 0 ms",
            actual=control_timeout_ms,
        ))
    validate_packet_loss_probability(ready_loss)
    validate_packet_loss_probability(commit_loss)


def create_paid_cbaa_finalization(robots: int) -> CBAAPaidFinalization:
    """Initialize only local proof ledgers, never a second auction machine."""
    if type(robots) is not int or robots < 1:
        raise ProtocolError(Diagnostic(
            owner=OWNER, function="create_paid_cbaa_finalization",
            category="data", code="E9K_INVALID_FINALIZATION_ROBOTS",
            expected="integer robots >= 1", actual=robots,
        ))
    return CBAAPaidFinalization(
        expected_digest=[None] * robots,
        ready_seen=[set() for _ in range(robots)],
        commit_seen=[set() for _ in range(robots)],
        confirmed=[False] * robots,
    )


def cbaa_paid_assignment_digest(state) -> str:
    """Only the common winning vectors belong in the shared fingerprint.

    Own assigned_task differs by robot; the native local certificate has
    already checked that each local claim agrees with this common vector.
    """
    raw = repr((state.winning_bids, state.winning_robots)).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def synchronize_paid_cbaa_local_proofs(
    *, proof: CBAAPaidFinalization, states: tuple,
    local_ready: tuple[bool, ...],
) -> None:
    """Invalidate ONLY this receiver's own old proof if local evidence changes."""
    robots = len(proof.expected_digest)
    if len(states) != robots or len(local_ready) != robots:
        raise ProtocolError(Diagnostic(
            owner=OWNER, function="synchronize_paid_cbaa_local_proofs",
            category="contract", code="E9K_LOCAL_PROOF_CARDINALITY",
            expected=robots, actual=(len(states), len(local_ready)),
        ))
    for robot_id, state in enumerate(states):
        digest = cbaa_paid_assignment_digest(state) if local_ready[robot_id] else None
        if proof.expected_digest[robot_id] != digest:
            proof.expected_digest[robot_id] = digest
            proof.ready_seen[robot_id].clear()
            proof.commit_seen[robot_id].clear()
            proof.confirmed[robot_id] = False
        if digest is not None:
            # Robot knows its own local certificate without a radio loopback.
            proof.ready_seen[robot_id].add(robot_id)


def exchange_paid_cbaa_control_packets(
    *, proof: CBAAPaidFinalization, eligible: tuple[bool, ...],
    phase: str, iteration: int, start_ms: float, timeout_ms: float,
    sampler, loss_sampler, loss_probability: float,
    capture_audit: bool, send_budget: SenderPayloadBudget | None,
) -> tuple[int, int, int, int, int, float, tuple, tuple, bool]:
    """One causal paid broadcast per eligible robot; receipts are local only."""
    robots = len(proof.expected_digest)
    if phase not in (READY_PHASE, COMMIT_PHASE) or len(eligible) != robots:
        raise ProtocolError(Diagnostic(
            owner=OWNER, function="exchange_paid_cbaa_control_packets",
            category="contract", code="E9K_INVALID_CONTROL_PHASE",
            expected={"phase": (READY_PHASE, COMMIT_PHASE), "robots": robots},
            actual={"phase": phase, "eligible": len(eligible)},
        ))
    ledger = proof.ready_seen if phase == READY_PHASE else proof.commit_seen
    sends = bytes_sent = attempts = drops = late = 0
    events: list[CommunicationEvent] = []
    observations: list[DeliveryObservation] = []
    denied = False
    for sender_id, allowed in enumerate(eligible):
        if not allowed:
            continue
        source_digest = proof.expected_digest[sender_id]
        if source_digest is None:
            raise ProtocolError(Diagnostic(
                owner=OWNER, function="exchange_paid_cbaa_control_packets",
                category="state", code="E9K_CONTROL_WITHOUT_LOCAL_CERTIFICATE",
                expected="nonempty local assignment digest",
                actual={"sender": sender_id, "phase": phase},
            ))
        try:
            event = _broadcast_event(
                phase=phase, sender_id=sender_id, send_time_ms=start_ms,
                payload_bytes=CONTROL_PAYLOAD_BYTES, sampler=sampler,
                round_id=iteration + 1, send_budget=send_budget,
            )
        except SenderBudgetExhausted:
            denied = True
            break
        sends += 1
        bytes_sent += event.payload_bytes
        # A local send is also one's own observed commitment, not a free
        # observation of any other robot's intention.
        ledger[sender_id].add(sender_id)
        receipts = _lossy_broadcast_deliveries(
            event=event, num_robots=robots,
            loss_sampler=loss_sampler, p_loss=loss_probability,
            round_id=iteration + 1,
        )
        attempts += len(receipts)
        drops += sum(int(not obs.delivered) for obs in receipts)
        if capture_audit:
            events.append(event)
            observations.extend(receipts)
        for obs in receipts:
            if not obs.delivered:
                continue
            if obs.arrival_time_ms is None:
                raise ProtocolError(Diagnostic(
                    owner=OWNER, function="exchange_paid_cbaa_control_packets",
                    category="contract", code="E9K_CONTROL_DELIVERED_WITHOUT_TIME",
                    expected="arrival timestamp", actual=obs,
                ))
            if obs.arrival_time_ms > start_ms + timeout_ms:
                late += 1
                continue
            # Only matching on-wire digests count.  The receiver cannot
            # inspect a peer's unsent local proof or its private flag.
            if proof.expected_digest[obs.receiver_id] == source_digest:
                ledger[obs.receiver_id].add(sender_id)
    window = float(timeout_ms) if sends else 0.0
    return (sends, bytes_sent, attempts, drops, late, window,
            tuple(events), tuple(observations), denied)


def advance_paid_cbaa_finalization(
    *, proof: CBAAPaidFinalization, states: tuple,
    local_ready: tuple[bool, ...], iteration: int, start_ms: float,
    timeout_ms: float, sampler, loss_sampler,
    ready_loss: float, commit_loss: float,
    capture_audit: bool = False,
    send_budget: SenderPayloadBudget | None = None,
) -> CBAAPaidTick:
    """Opt-in two-wave READY -> COMMIT with per-node receipt evidence.

    Native CBAA continues to execute between control waves; the global
    simulator cannot grant readiness and can only stop when *all local*
    ledgers independently contain every matching COMMIT receipt.
    """
    synchronize_paid_cbaa_local_proofs(
        proof=proof, states=states, local_ready=local_ready,
    )
    robots = len(states)
    ready_eligible = tuple(x is not None for x in proof.expected_digest)
    ready = exchange_paid_cbaa_control_packets(
        proof=proof, eligible=ready_eligible,
        phase=READY_PHASE, iteration=iteration, start_ms=start_ms,
        timeout_ms=timeout_ms, sampler=sampler, loss_sampler=loss_sampler,
        loss_probability=ready_loss, capture_audit=capture_audit,
        send_budget=send_budget,
    )
    ready_sends, ready_bytes, ra, rd, rl, ready_ms, re, ro, denied = ready
    commit_eligible = tuple(
        proof.expected_digest[i] is not None
        and len(proof.ready_seen[i]) == robots
        for i in range(robots)
    )
    commit = (0, 0, 0, 0, 0, 0.0, (), (), False)
    if not denied:
        commit = exchange_paid_cbaa_control_packets(
            proof=proof, eligible=commit_eligible,
            phase=COMMIT_PHASE, iteration=iteration,
            start_ms=start_ms + ready_ms, timeout_ms=timeout_ms,
            sampler=sampler, loss_sampler=loss_sampler,
            loss_probability=commit_loss, capture_audit=capture_audit,
            send_budget=send_budget,
        )
    cs, cb, ca, cd, cl, cm, ce, co, commit_denied = commit
    for i in range(robots):
        proof.confirmed[i] = (
            proof.expected_digest[i] is not None
            and len(proof.ready_seen[i]) == robots
            and len(proof.commit_seen[i]) == robots
        )
    return CBAAPaidTick(
        ready_sends=ready_sends, commit_sends=cs,
        bytes_sent=ready_bytes + cb,
        delivery_attempts=ra + ca, delivery_drops=rd + cd,
        late_deliveries=rl + cl, elapsed_ms=ready_ms + cm,
        audit_events=re + ce, audit_deliveries=ro + co,
        budget_denied=denied or commit_denied,
        denied_phase=(
            READY_PHASE if denied else COMMIT_PHASE if commit_denied else None
        ),
    )

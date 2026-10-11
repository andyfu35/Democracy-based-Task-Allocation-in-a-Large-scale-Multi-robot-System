"""Independent, synchronous single-assignment CBAA reference implementation.

Choi, Brunet & How, IEEE T-RO 2009, Sec. III: local auction followed by
max-consensus. This is NOT CBBA (no multi-task bundle), NOT our voting protocol,
and it never uses a central winner to correct a robot's local state.

Explicit engineering choices (see docs/EXPERIMENT_PROTOCOL.md Sec. 18):
- score = 1/(1+nonnegative Euclidean cost), shared deterministic ID tie break;
- winning bid origin ID accompanies y to preserve max-consensus provenance;
- complete graph and fixed number of synchronous auction/consensus iterations;
- broadcasts can be independently lost at each receiver, no hidden reliable
  assignment/Commit or centralized early-termination decision.
"""
from __future__ import annotations

from dataclasses import dataclass
import math

from .coordination import (
    APP_HEADER_BYTES,
    FLOAT64_BYTES,
    ID_BYTES,
    CommunicationEvent,
    DeliveryObservation,
    _broadcast_event,
    _lossy_broadcast_deliveries,
)
from .diagnostics import Diagnostic, ProtocolError
from .network import validate_packet_loss_probability
from .optimizer import validate_cost_matrix


OWNER = "democracy_mrta.cbaa"
PHASE = "cbaa_consensus"


@dataclass(frozen=True)
class CBAALocalState:
    robot_id: int
    assigned_task: int | None
    winning_bids: tuple[float, ...]
    winning_robots: tuple[int | None, ...]


@dataclass(frozen=True)
class CBAAResult:
    method: str
    states: tuple[CBAALocalState, ...]
    local_claims: tuple[tuple[int, int], ...]
    observer_agreed_pairs: tuple[tuple[int, int], ...]
    conflicting_task_ids: tuple[int, ...]
    unconfirmed_task_ids: tuple[int, ...]
    iterations: int
    elapsed_ms: float
    logical_message_count: int
    payload_bytes: int
    delivery_attempts: int
    delivery_drops: int
    late_deliveries: int
    audit_events: tuple[CommunicationEvent, ...] = ()
    audit_deliveries: tuple[DeliveryObservation, ...] = ()

    @property
    def full_observer_agreement(self) -> bool:
        return not self.unconfirmed_task_ids and not self.conflicting_task_ids

    @property
    def task_agreement_rate(self) -> float:
        return len(self.observer_agreed_pairs) / len(self.states[0].winning_bids)


def validate_cbaa_configuration(
    *,
    cost_matrix: tuple[tuple[float, ...], ...],
    loss_probability: float,
    max_iterations: int,
    phase_timeout_ms: float,
) -> tuple[int, int]:
    """Own CBAA-only input constraints, not shared optimizer/network rules."""
    robots, tasks = validate_cost_matrix(cost_matrix)
    validate_packet_loss_probability(loss_probability)
    invalid = (
        (robot_id, task_id, cost)
        for robot_id, row in enumerate(cost_matrix)
        for task_id, cost in enumerate(row)
        if cost < 0.0
    )
    first_negative = next(invalid, None)
    if first_negative is not None:
        raise ProtocolError(Diagnostic(
            owner=OWNER, function="validate_cbaa_configuration",
            category="data", code="CBAA_NEGATIVE_COST",
            expected="all costs >= 0 for score = 1/(1+cost)",
            actual=first_negative,
        ))
    if type(max_iterations) is not int or max_iterations < 1:
        raise ProtocolError(Diagnostic(
            owner=OWNER, function="validate_cbaa_configuration",
            category="data", code="CBAA_INVALID_ITERATION_BUDGET",
            expected="integer >= 1", actual=max_iterations,
        ))
    if (
        type(phase_timeout_ms) not in (float, int)
        or not math.isfinite(phase_timeout_ms)
        or phase_timeout_ms <= 0.0
    ):
        raise ProtocolError(Diagnostic(
            owner=OWNER, function="validate_cbaa_configuration",
            category="time", code="CBAA_INVALID_PHASE_TIMEOUT",
            expected="finite number > 0 ms", actual=phase_timeout_ms,
        ))
    return robots, tasks


def initial_cbaa_states(num_robots: int, num_tasks: int) -> tuple[CBAALocalState, ...]:
    """Each robot starts with its own independent, empty task/bid estimates."""
    return tuple(
        CBAALocalState(
            robot_id=robot_id,
            assigned_task=None,
            winning_bids=(0.0,) * num_tasks,
            winning_robots=(None,) * num_tasks,
        )
        for robot_id in range(num_robots)
    )


def cbaa_score(cost: float) -> float:
    """Strictly decreasing, positive utility; no global maximum cost needed."""
    return 1.0 / (1.0 + cost)


def cbaa_bid_outbids(
    proposed_bid: float,
    proposed_robot: int,
    incumbent_bid: float,
    incumbent_robot: int | None,
) -> bool:
    """Consistent maximum-bid + lowest-robot-ID tie resolution."""
    return (
        proposed_bid > incumbent_bid
        or (
            proposed_bid == incumbent_bid
            and incumbent_robot is not None
            and proposed_robot < incumbent_robot
        )
    )


def cbaa_auction_phase(
    *,
    state: CBAALocalState,
    cost_row: tuple[float, ...],
) -> CBAALocalState:
    """Paper CBAA Phase 1: unassigned agent bids on its best feasible task."""
    if state.assigned_task is not None:
        return state
    viable = tuple(
        (task_id, cbaa_score(cost))
        for task_id, cost in enumerate(cost_row)
        if cbaa_bid_outbids(
            cbaa_score(cost), state.robot_id,
            state.winning_bids[task_id],
            state.winning_robots[task_id],
        )
    )
    if not viable:
        return state
    task_id, score = max(viable, key=lambda item: (item[1], -item[0]))
    bids = list(state.winning_bids)
    origins = list(state.winning_robots)
    bids[task_id] = score
    origins[task_id] = state.robot_id
    return CBAALocalState(
        robot_id=state.robot_id,
        assigned_task=task_id,
        winning_bids=tuple(bids),
        winning_robots=tuple(origins),
    )


def exchange_cbaa_consensus_packets(
    *,
    states: tuple[CBAALocalState, ...],
    iteration: int,
    start_ms: float,
    phase_timeout_ms: float,
    sampler,
    loss_sampler,
    loss_probability: float,
    capture_audit: bool,
) -> tuple[
    tuple[tuple[CBAALocalState, ...], ...],
    int, int, int, int, int,
    tuple[CommunicationEvent, ...],
    tuple[DeliveryObservation, ...],
]:
    """Original broadcast transport owner, with CBAA full-vector payloads.

    One physical broadcast per robot, independently lost at each remote
    receiver. Only delivered and on-time snapshots reach that robot's inbox.
    Other agents' state is NEVER read by receivers except through this inbox.
    """
    robots = len(states)
    tasks = len(states[0].winning_bids)
    payload = APP_HEADER_BYTES + tasks * (FLOAT64_BYTES + ID_BYTES)
    inbox: list[list[CBAALocalState]] = [[] for _ in range(robots)]
    messages = bytes_sent = physical_attempts = drops = late = 0
    logged_events: list[CommunicationEvent] = []
    logged_deliveries: list[DeliveryObservation] = []

    for sender_state in states:
        event = _broadcast_event(
            phase=PHASE,
            sender_id=sender_state.robot_id,
            send_time_ms=start_ms,
            payload_bytes=payload,
            sampler=sampler,
            round_id=iteration,
        )
        deliveries = _lossy_broadcast_deliveries(
            event=event,
            num_robots=robots,
            loss_sampler=loss_sampler,
            p_loss=loss_probability,
            round_id=iteration,
        )
        messages += 1
        bytes_sent += event.payload_bytes
        physical_attempts += len(deliveries)
        drops += sum(int(not obs.delivered) for obs in deliveries)
        if capture_audit:
            logged_events.append(event)
            logged_deliveries.extend(deliveries)
        for observation in deliveries:
            if not observation.delivered:
                continue
            if observation.arrival_time_ms is None:
                raise ProtocolError(Diagnostic(
                    owner=OWNER, function="exchange_cbaa_consensus_packets",
                    category="contract", code="CBAA_DELIVERED_PACKET_WITHOUT_TIME",
                    expected="finite arrival_time_ms for delivered packet",
                    actual=observation,
                ))
            if observation.arrival_time_ms > start_ms + phase_timeout_ms:
                late += 1
                continue
            inbox[observation.receiver_id].append(sender_state)
    return (
        tuple(tuple(messages) for messages in inbox),
        messages, bytes_sent, physical_attempts, drops, late,
        tuple(logged_events), tuple(logged_deliveries),
    )


def cbaa_consensus_phase(
    *,
    state: CBAALocalState,
    received: tuple[CBAALocalState, ...],
) -> CBAALocalState:
    """Paper CBAA Phase 2: max-consensus and release if outbid.

    The origin ID travels with each maximum to distinguish genuinely equal
    original bidders from a relay merely forwarding the same highest bid.
    """
    bids = list(state.winning_bids)
    origins = list(state.winning_robots)
    for remote in received:
        for task_id, bid in enumerate(remote.winning_bids):
            proposed_owner = remote.winning_robots[task_id]
            if proposed_owner is None:
                continue
            if cbaa_bid_outbids(
                bid, proposed_owner, bids[task_id], origins[task_id]
            ):
                bids[task_id] = bid
                origins[task_id] = proposed_owner
    retained = state.assigned_task
    if retained is not None and origins[retained] != state.robot_id:
        retained = None
    return CBAALocalState(
        robot_id=state.robot_id,
        assigned_task=retained,
        winning_bids=tuple(bids),
        winning_robots=tuple(origins),
    )


def audit_cbaa_local_agreement(
    states: tuple[CBAALocalState, ...],
) -> tuple[
    tuple[tuple[int, int], ...],
    tuple[tuple[int, int], ...],
    tuple[int, ...],
    tuple[int, ...],
]:
    """Observer ONLY: report split-brain claims; never resolve them for agents."""
    tasks = len(states[0].winning_bids)
    claims = tuple(
        (state.robot_id, state.assigned_task)
        for state in states if state.assigned_task is not None
    )
    claimants = {j: tuple(r for r, task in claims if task == j) for j in range(tasks)}
    conflicts = tuple(j for j, robots in claimants.items() if len(robots) > 1)
    agreed: list[tuple[int, int]] = []
    unconfirmed: list[int] = []

    for task_id in range(tasks):
        owner_votes = {state.winning_robots[task_id] for state in states}
        bid_votes = {state.winning_bids[task_id] for state in states}
        if len(owner_votes) != 1 or len(bid_votes) != 1:
            unconfirmed.append(task_id)
            continue
        owner = next(iter(owner_votes))
        if (
            owner is None
            or claimants[task_id] != (owner,)
            or states[owner].assigned_task != task_id
        ):
            unconfirmed.append(task_id)
            continue
        agreed.append((owner, task_id))
    return claims, tuple(agreed), conflicts, tuple(unconfirmed)


def simulate_cbaa(
    *,
    cost_matrix: tuple[tuple[float, ...], ...],
    sampler,
    loss_sampler,
    loss_probability: float,
    phase_timeout_ms: float,
    max_iterations: int,
    capture_audit: bool = False,
) -> CBAAResult:
    """Fixed-budget, synchronous TWO-PHASE CBAA; no global termination feedback.

    The omniscient observer runs only AFTER all local auctions/consensus. It
    never fills missing messages, chooses assignments or sends a final Commit.
    """
    robots, tasks = validate_cbaa_configuration(
        cost_matrix=cost_matrix, loss_probability=loss_probability,
        phase_timeout_ms=phase_timeout_ms,
        max_iterations=max_iterations,
    )
    states = initial_cbaa_states(robots, tasks)
    logical_messages = payload_bytes = attempts = drops = late = 0
    audit_events: list[CommunicationEvent] = []
    audit_deliveries: list[DeliveryObservation] = []

    for iteration in range(max_iterations):
        bidding = tuple(
            cbaa_auction_phase(state=state, cost_row=cost_matrix[state.robot_id])
            for state in states
        )
        (
            received, nmessages, nbytes, nattempts, ndrops, nlate,
            events, observations,
        ) = exchange_cbaa_consensus_packets(
            states=bidding, iteration=iteration,
            start_ms=iteration * phase_timeout_ms,
            phase_timeout_ms=phase_timeout_ms,
            sampler=sampler,
            loss_sampler=loss_sampler,
            loss_probability=loss_probability,
            capture_audit=capture_audit,
        )
        states = tuple(
            cbaa_consensus_phase(state=bidding[robot_id], received=received[robot_id])
            for robot_id in range(robots)
        )
        logical_messages += nmessages
        payload_bytes += nbytes
        attempts += nattempts
        drops += ndrops
        late += nlate
        if capture_audit:
            audit_events.extend(events)
            audit_deliveries.extend(observations)

    claims, agreed, conflicts, unconfirmed = audit_cbaa_local_agreement(states)
    if len({r for r, _t in agreed}) != len(agreed):
        raise ProtocolError(Diagnostic(
            owner=OWNER, function="simulate_cbaa", category="safety",
            code="CBAA_DUPLICATE_OBSERVER_AGREEMENT",
            expected="each agreed robot appears at most once",
            actual=agreed,
        ))
    return CBAAResult(
        method="cbaa_sync_single_assignment",
        states=states,
        local_claims=claims,
        observer_agreed_pairs=agreed,
        conflicting_task_ids=conflicts,
        unconfirmed_task_ids=unconfirmed,
        iterations=max_iterations,
        elapsed_ms=max_iterations * phase_timeout_ms,
        logical_message_count=logical_messages,
        payload_bytes=payload_bytes,
        delivery_attempts=attempts,
        delivery_drops=drops,
        late_deliveries=late,
        audit_events=tuple(audit_events),
        audit_deliveries=tuple(audit_deliveries),
    )

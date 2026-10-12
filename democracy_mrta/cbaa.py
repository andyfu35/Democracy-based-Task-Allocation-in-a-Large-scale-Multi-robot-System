"""Independent, synchronous single-assignment CBAA reference implementation.

Choi, Brunet & How, IEEE T-RO 2009, Sec. III: local auction followed by
max-consensus. This is NOT CBBA (no multi-task bundle), NOT our voting protocol,
and it never uses a central winner to correct a robot's local state.

Explicit engineering choices (see docs/EXPERIMENT_PROTOCOL.md Sec. 18):
- score = 1/(1+nonnegative Euclidean cost), shared deterministic ID tie break;
- winning bid origin ID accompanies y to preserve max-consensus provenance;
- complete graph; fixed iteration mode retained, opt-in local evidence stop added;
- broadcasts can be independently lost at each receiver; there is no reliable
  final Commit or distributed shared halt/stop handshake.
- new local-certification mode is an explicitly labeled simulator stopping
  approximation: each robot uses only PHYSICALLY RECEIVED peer bids/claims
  to decide readiness; the scheduler terminates after every robot is ready.
  This is NOT a fully implemented distributed termination protocol.
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
from .cbaa_finalization import (
    create_paid_cbaa_finalization,
    validate_paid_cbaa_finalization_config,
    advance_paid_cbaa_finalization,
)
from .network import (
    SenderBudgetExhausted,
    SenderPayloadBudget,
    validate_packet_loss_probability,
)
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
    budget_exhausted: bool = False
    budget_stop_phase: str | None = None
    budget_stop_diagnostic: Diagnostic | None = None
    stop_mode: str = "fixed"
    stop_reason: str = "fixed_iteration_budget"
    locally_certified_count: int = 0
    # E9K optional physically delivered termination, not part of original CBAA.
    paid_ready_sends: int = 0
    paid_commit_sends: int = 0
    paid_sender_bytes: int = 0
    paid_receiver_attempts: int = 0
    paid_receiver_drops: int = 0
    paid_late_receipts: int = 0
    paid_control_elapsed_ms: float = 0.0
    paid_confirmed_robots: int = 0
    paid_termination_complete: bool = False

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



def validate_cbaa_sender_budget(
    send_budget: SenderPayloadBudget | None,
) -> None:
    """Check optional run-level physical sender budget before first emission."""
    if send_budget is not None and type(send_budget) is not SenderPayloadBudget:
        raise ProtocolError(Diagnostic(
            owner=OWNER, function="validate_cbaa_sender_budget",
            category="data", code="CBAA_INVALID_SEND_BUDGET",
            expected="SenderPayloadBudget or None",
            actual=type(send_budget).__name__,
        ))


def require_cbaa_sender_budget_accounting(
    *,
    send_budget: SenderPayloadBudget | None,
    logical_message_count: int,
    payload_bytes: int,
) -> None:
    """Original physical packet totals must equal the shared sender ledger."""
    if send_budget is None:
        return
    actual = (logical_message_count, payload_bytes)
    expected = (send_budget.sent_messages, send_budget.sent_bytes)
    if actual != expected:
        raise ProtocolError(Diagnostic(
            owner=OWNER, function="require_cbaa_sender_budget_accounting",
            category="contract", code="CBAA_SEND_BUDGET_LEDGER_MISMATCH",
            expected={"messages": expected[0], "bytes": expected[1]},
            actual={"messages": actual[0], "bytes": actual[1]},
        ))



def validate_cbaa_stop_mode(stop_mode: str) -> None:
    """Own convergence-policy configuration; legacy fixed mode is default."""
    if stop_mode not in ("fixed", "local_certification", "paid_termination"):
        raise ProtocolError(Diagnostic(
            owner=OWNER, function="validate_cbaa_stop_mode",
            category="data", code="CBAA_UNKNOWN_STOP_MODE",
            expected="fixed, local_certification or paid_termination", actual=stop_mode,
        ))


def update_cbaa_received_peer_evidence(
    *,
    receiver_views: list[dict[int, tuple[int, CBAALocalState]]],
    received: tuple[tuple[CBAALocalState, ...], ...],
    iteration: int,
) -> None:
    """Store ONLY each receiver's physically delivered peer states and epoch."""
    for receiver_id, remote_states in enumerate(received):
        for remote in remote_states:
            if remote.robot_id == receiver_id:
                raise ProtocolError(Diagnostic(
                    owner=OWNER, function="update_cbaa_received_peer_evidence",
                    category="contract", code="CBAA_SELF_ON_WIRE",
                    expected="received states only from other robots",
                    actual=(receiver_id, remote.robot_id),
                ))
            receiver_views[receiver_id][remote.robot_id] = (iteration, remote)


def cbaa_local_convergence_certified(
    *,
    state: CBAALocalState,
    peer_view: dict[int, tuple[int, CBAALocalState]],
    peers: int,
    own_last_change_iteration: int,
) -> bool:
    """Local evidence only: complete conflict-free claims and fresh peer proofs.

    Required peer packet must postdate THIS node's most recent bid/claim
    change. A missing packet never proves that a remote node is settled.
    This is a local diagnostic convergence certificate, not a network halt ACK.
    """
    owners = state.winning_robots
    if (any(owner is None or not 0 <= owner < peers for owner in owners)
        or len(set(owners)) != len(owners)
        or any(bid <= 0.0 for bid in state.winning_bids)):
        return False
    own_claims = [task_id for task_id, owner in enumerate(owners)
                  if owner == state.robot_id]
    if state.assigned_task != (own_claims[0] if own_claims else None):
        return False
    if len(peer_view) != peers - 1:
        return False
    for peer_id in range(peers):
        if peer_id == state.robot_id:
            continue
        evidence = peer_view.get(peer_id)
        if evidence is None:
            return False
        evidence_iteration, remote = evidence
        if evidence_iteration <= own_last_change_iteration:
            return False
        if (remote.winning_bids != state.winning_bids
            or remote.winning_robots != state.winning_robots):
            return False
        remote_claims = [task for task, owner in enumerate(owners)
                         if owner == peer_id]
        if remote.assigned_task != (remote_claims[0] if remote_claims else None):
            return False
    return True


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
    send_budget: SenderPayloadBudget | None = None,
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
        try:
            event = _broadcast_event(
                phase=PHASE,
                sender_id=sender_state.robot_id,
                send_time_ms=start_ms,
                payload_bytes=payload,
                sampler=sampler,
                round_id=iteration,
                send_budget=send_budget,
            )
        except SenderBudgetExhausted:
            # Denied packet has no event or receiver observations.
            # Previously emitted broadcasts preserve actual per-robot inboxes.
            break
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
    send_budget: SenderPayloadBudget | None = None,
    stop_mode: str = "fixed",
    control_timeout_ms: float | None = None,
    ready_loss_probability: float | None = None,
    commit_loss_probability: float | None = None,
) -> CBAAResult:
    """Original TWO-PHASE CBAA with opt-in local-evidence convergence monitor.

    The observer never supplies bids/winners; in opt-in local_certification,
    each node only sees delivered peer snapshots, while the simulation
    scheduler uses all independent local-ready flags to finish. The latter
    is an optimistic shared halt and NOT a real distributed stop protocol.
    max_iterations is only a safety guard in the opt-in mode.
    """
    robots, tasks = validate_cbaa_configuration(
        cost_matrix=cost_matrix, loss_probability=loss_probability,
        phase_timeout_ms=phase_timeout_ms,
        max_iterations=max_iterations,
    )
    validate_cbaa_sender_budget(send_budget)
    validate_cbaa_stop_mode(stop_mode)
    if stop_mode != "paid_termination" and any(
        value is not None for value in (
            control_timeout_ms, ready_loss_probability, commit_loss_probability
        )
    ):
        raise ProtocolError(Diagnostic(
            owner=OWNER, function="simulate_cbaa", category="contract",
            code="E9K_CONTROL_OPTIONS_REQUIRE_PAID_MODE",
            expected="stop_mode='paid_termination'",
            actual=stop_mode,
        ))
    if stop_mode == "paid_termination":
        control_timeout_ms = (
            phase_timeout_ms if control_timeout_ms is None
            else control_timeout_ms
        )
        ready_loss_probability = (
            loss_probability if ready_loss_probability is None
            else ready_loss_probability
        )
        commit_loss_probability = (
            loss_probability if commit_loss_probability is None
            else commit_loss_probability
        )
        validate_paid_cbaa_finalization_config(
            control_timeout_ms=control_timeout_ms,
            ready_loss=ready_loss_probability,
            commit_loss=commit_loss_probability,
        )
    paid_proof = (
        create_paid_cbaa_finalization(robots)
        if stop_mode == "paid_termination" else None
    )
    states = initial_cbaa_states(robots, tasks)
    logical_messages = payload_bytes = attempts = drops = late = 0
    processed_iterations = 0
    budget_exhausted = False
    audit_events: list[CommunicationEvent] = []
    audit_deliveries: list[DeliveryObservation] = []
    receiver_views: list[dict[int, tuple[int, CBAALocalState]]] = [
        {} for _ in range(robots)
    ]
    own_last_change = [-1] * robots
    locally_certified_count = 0
    paid_ready_sends = paid_commit_sends = paid_bytes = 0
    paid_attempts = paid_drops = paid_late = 0
    paid_elapsed_ms = 0.0
    clock_ms = 0.0
    paid_budget_phase = None
    stop_reason = (
        "fixed_iteration_budget" if stop_mode == "fixed" else
        "paid_termination_safety_guard" if stop_mode == "paid_termination" else
        "iteration_safety_guard"
    )

    for iteration in range(max_iterations):
        previous_states = states
        bidding = tuple(
            cbaa_auction_phase(state=state, cost_row=cost_matrix[state.robot_id])
            for state in states
        )
        (
            received, nmessages, nbytes, nattempts, ndrops, nlate,
            events, observations,
        ) = exchange_cbaa_consensus_packets(
            states=bidding, iteration=iteration,
            start_ms=clock_ms,
            phase_timeout_ms=phase_timeout_ms,
            sampler=sampler,
            loss_sampler=loss_sampler,
            loss_probability=loss_probability,
            capture_audit=capture_audit,
            send_budget=send_budget,
        )
        # A partial iteration is real only when >=1 physical broadcast exists.
        # Every robot completes its local auction/consensus from its own inbox.
        # With zero SENDs, discard newly proposed bids and keep former states.
        if nmessages:
            states = tuple(
                cbaa_consensus_phase(
                    state=bidding[robot_id], received=received[robot_id]
                )
                for robot_id in range(robots)
            )
            processed_iterations += 1
            if stop_mode in ("local_certification", "paid_termination"):
                update_cbaa_received_peer_evidence(
                    receiver_views=receiver_views,
                    received=received,
                    iteration=iteration,
                )
                for robot_id in range(robots):
                    if (states[robot_id] != previous_states[robot_id]
                        or bidding[robot_id] != previous_states[robot_id]):
                        own_last_change[robot_id] = iteration
        logical_messages += nmessages
        payload_bytes += nbytes
        attempts += nattempts
        drops += ndrops
        late += nlate
        if capture_audit:
            audit_events.extend(events)
            audit_deliveries.extend(observations)
        if nmessages:
            clock_ms += phase_timeout_ms
        if send_budget is not None and send_budget.denied_messages:
            budget_exhausted = True
            stop_reason = "sender_budget_exhausted"
            break
        if stop_mode in ("local_certification", "paid_termination"):
            ready = tuple(
                cbaa_local_convergence_certified(
                    state=states[robot_id],
                    peer_view=receiver_views[robot_id],
                    peers=robots,
                    own_last_change_iteration=own_last_change[robot_id],
                )
                for robot_id in range(robots)
            )
            locally_certified_count = sum(ready)
            if stop_mode == "local_certification":
                if locally_certified_count == robots:
                    stop_reason = "all_local_evidence_certified"
                    break
            else:
                # Never use the simulator-wide ready count as an E9K stop gate.
                # The true paid-finalization owner acts on each node's local
                # inbox and emits separately charged READY/COMMIT broadcasts.
                tick = advance_paid_cbaa_finalization(
                    proof=paid_proof, states=states, local_ready=ready,
                    iteration=iteration, start_ms=clock_ms,
                    timeout_ms=control_timeout_ms, sampler=sampler,
                    loss_sampler=loss_sampler,
                    ready_loss=ready_loss_probability,
                    commit_loss=commit_loss_probability,
                    capture_audit=capture_audit, send_budget=send_budget,
                )
                clock_ms += tick.elapsed_ms
                paid_elapsed_ms += tick.elapsed_ms
                paid_ready_sends += tick.ready_sends
                paid_commit_sends += tick.commit_sends
                paid_bytes += tick.bytes_sent
                paid_attempts += tick.delivery_attempts
                paid_drops += tick.delivery_drops
                paid_late += tick.late_deliveries
                if capture_audit:
                    audit_events.extend(tick.audit_events)
                    audit_deliveries.extend(tick.audit_deliveries)
                if tick.budget_denied:
                    budget_exhausted = True
                    paid_budget_phase = (
                        "cbaa_paid_ready" if not tick.commit_sends
                        else "cbaa_paid_commit"
                    )
                    stop_reason = "sender_budget_exhausted"
                    break
                if all(paid_proof.confirmed):
                    # Observer is a safety assertion only, NEVER an agent's
                    # input or an algorithmically free readiness signal.
                    _claims, agreed_now, conflicts_now, unconfirmed_now = (
                        audit_cbaa_local_agreement(states)
                    )
                    if (conflicts_now or unconfirmed_now
                        or len(agreed_now) != tasks):
                        raise ProtocolError(Diagnostic(
                            owner=OWNER, function="simulate_cbaa",
                            category="safety",
                            code="E9K_PAID_PROOFS_CONFLICT_WITH_OBSERVER",
                            expected=f"{tasks} consistent unique task claims",
                            actual={"agreed":len(agreed_now),
                                    "conflicts":conflicts_now,
                                    "unconfirmed":unconfirmed_now},
                        ))
                    stop_reason = "all_paid_commit_proofs_received"
                    break

    require_cbaa_sender_budget_accounting(
        send_budget=send_budget,
        logical_message_count=logical_messages + paid_ready_sends + paid_commit_sends,
        payload_bytes=payload_bytes + paid_bytes,
    )
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
        iterations=processed_iterations,
        elapsed_ms=clock_ms,
        logical_message_count=logical_messages,
        payload_bytes=payload_bytes,
        delivery_attempts=attempts,
        delivery_drops=drops,
        late_deliveries=late,
        audit_events=tuple(audit_events),
        audit_deliveries=tuple(audit_deliveries),
        budget_exhausted=budget_exhausted,
        budget_stop_phase=(
            paid_budget_phase or PHASE if budget_exhausted else None
        ),
        budget_stop_diagnostic=(
            send_budget.last_denied_diagnostic if budget_exhausted else None
        ),
        stop_mode=stop_mode,
        stop_reason=stop_reason,
        locally_certified_count=locally_certified_count,
        paid_ready_sends=paid_ready_sends,
        paid_commit_sends=paid_commit_sends,
        paid_sender_bytes=paid_bytes,
        paid_receiver_attempts=paid_attempts,
        paid_receiver_drops=paid_drops,
        paid_late_receipts=paid_late,
        paid_control_elapsed_ms=paid_elapsed_ms,
        paid_confirmed_robots=(
            sum(paid_proof.confirmed) if paid_proof is not None else 0
        ),
        paid_termination_complete=bool(
            paid_proof is not None and all(paid_proof.confirmed)
        ),
    )

from __future__ import annotations

from dataclasses import dataclass
import math
import struct

from .diagnostics import Diagnostic, ProtocolError

from .network import (
    WifiCausalTimingSampler,
    SenderPayloadBudget,
    SenderBudgetExhausted,
    reserve_sender_payload,
    validate_packet_loss_probability,
    validate_vote_repetitions,
)

from .optimizer import (
    AssignmentSolution,
    solve_visible_hungarian_assignment,
    solve_all_visible_greedy_task_votes,
    solve_visible_batched_greedy_assignment,
    sample_probabilistic_pair_votes,
    solve_visible_task_ordered_greedy_assignment,
    validate_cost_matrix,
)
from .protocol import (
    assignment_to_votes,
    find_unique_majority,
    CandidateVoteAnnouncement,
    PluralityResolution,
    quarter_vote_announcement_threshold,
    plurality_announcement_threshold,
    resolve_unique_plurality_claims,
    quorum_size,
    record_vote,
    validate_one_to_one_commits,
    initialize_retirement_membership,
    apply_announced_retirement_commits,
)


APP_HEADER_BYTES = 16
FLOAT64_BYTES = 8
ID_BYTES = 4

BROADCAST_RECEIVER_ID = -1

VOTE_PAYLOAD_BYTES = APP_HEADER_BYTES + 4 * ID_BYTES
COMMIT_PAYLOAD_BYTES = APP_HEADER_BYTES + 3 * ID_BYTES
VOTE_SCORE_ANNOUNCEMENT_BYTES = APP_HEADER_BYTES + 4 * ID_BYTES


@dataclass(frozen=True)
class CommunicationEvent:
    phase: str
    sender_id: int
    receiver_id: int
    send_time_ms: float
    latency_ms: float
    arrival_time_ms: float
    payload_bytes: int
    task_id: int | None = None
    round_id: int = 0
    announced_vote_count: int | None = None
    transmission_index: int = 0

    @property
    def is_broadcast(self) -> bool:
        return self.receiver_id == BROADCAST_RECEIVER_ID


@dataclass(frozen=True)
class CoordinationTimingResult:
    method: str
    cost_exchange_completion_ms: float
    actionable_decision_ms: float
    global_agreement_ms: float
    message_count: int
    payload_bytes: int
    events: tuple[CommunicationEvent, ...]

    @property
    def communication_ms(self) -> float:
        return self.global_agreement_ms



def validate_cost_repetitions(cost_repetitions: int) -> int:
    """Cost transport data boundary: fixed sender-paid physical copies."""
    if type(cost_repetitions) is not int or not 1 <= cost_repetitions <= 5:
        raise ProtocolError(Diagnostic(
            owner="coordination", function="validate_cost_repetitions",
            category="data", code="INVALID_COST_REPETITIONS",
            expected="integer in [1,5]", actual=cost_repetitions,
        ))
    return cost_repetitions


def validate_repeated_cost_scope(
    *,
    cost_repetitions: int,
    voting_strategy: str,
    preknown_cost_snapshot: RetirementCostSnapshot | None,
) -> None:
    """Only the original Greedy once-per-run Cost source can repeat."""
    if cost_repetitions != 1 and (
        voting_strategy != "greedy_task" or preknown_cost_snapshot is not None
    ):
        raise ProtocolError(Diagnostic(
            owner="coordination", function="validate_repeated_cost_scope",
            category="contract", code="REPEATED_COST_REQUIRES_GREEDY_COST_SOURCE",
            expected="greedy_task with physically emitted original Cost packets",
            actual={
                "voting_strategy": voting_strategy,
                "preknown_snapshot": preknown_cost_snapshot is not None,
                "cost_repetitions": cost_repetitions,
            },
        ))


def cost_row_payload_bytes(num_tasks: int) -> int:
    return APP_HEADER_BYTES + num_tasks * FLOAT64_BYTES


def assignment_payload_bytes(num_tasks: int) -> int:
    return APP_HEADER_BYTES + num_tasks * 2 * ID_BYTES


def _unicast_event(
    *,
    phase: str,
    sender_id: int,
    receiver_id: int,
    send_time_ms: float,
    payload_bytes: int,
    sampler,
    task_id: int | None = None,
    round_id: int = 0,
    transmission_index: int = 0,
    send_budget: SenderPayloadBudget | None = None,
) -> CommunicationEvent:
    key = (
        f"unicast|{phase}|{sender_id}|{receiver_id}|"
        f"{task_id if task_id is not None else '-'}"
    )
    if round_id:
        key += f"|round={round_id}"
    if transmission_index:
        if round_id == 0:
            key += "|round=0"
        key += f"|copy={transmission_index}"
    if send_budget is not None:
        reserve_sender_payload(send_budget, payload_bytes=payload_bytes, phase=phase)
    latency_ms = (
        float(sampler.sample_packet_ms(
            key=key, phase=phase, sender_id=sender_id,
            receiver_id=receiver_id, send_time_ms=send_time_ms,
            payload_bytes=payload_bytes,
        ))
        if isinstance(sampler, WifiCausalTimingSampler)
        else float(sampler.sample_ms(key))
    )
    return CommunicationEvent(
        phase=phase,
        sender_id=sender_id,
        receiver_id=receiver_id,
        send_time_ms=send_time_ms,
        latency_ms=latency_ms,
        arrival_time_ms=send_time_ms + latency_ms,
        payload_bytes=payload_bytes,
        task_id=task_id,
        round_id=round_id,
        transmission_index=transmission_index,
    )


def _broadcast_event(
    *,
    phase: str,
    sender_id: int,
    send_time_ms: float,
    payload_bytes: int,
    sampler,
    task_id: int | None = None,
    round_id: int = 0,
    announced_vote_count: int | None = None,
    transmission_index: int = 0,
    send_budget: SenderPayloadBudget | None = None,
) -> CommunicationEvent:
    key = (
        f"broadcast|{phase}|{sender_id}|"
        f"{task_id if task_id is not None else '-'}"
    )
    if round_id:
        key += f"|round={round_id}"
    if transmission_index:
        if round_id == 0:
            key += "|round=0"
        key += f"|copy={transmission_index}"
    if send_budget is not None:
        reserve_sender_payload(send_budget, payload_bytes=payload_bytes, phase=phase)
    latency_ms = (
        float(sampler.sample_packet_ms(
            key=key, phase=phase, sender_id=sender_id,
            receiver_id=BROADCAST_RECEIVER_ID, send_time_ms=send_time_ms,
            payload_bytes=payload_bytes,
        ))
        if isinstance(sampler, WifiCausalTimingSampler)
        else float(sampler.sample_ms(key))
    )
    return CommunicationEvent(
        phase=phase,
        sender_id=sender_id,
        receiver_id=BROADCAST_RECEIVER_ID,
        send_time_ms=send_time_ms,
        latency_ms=latency_ms,
        arrival_time_ms=send_time_ms + latency_ms,
        payload_bytes=payload_bytes,
        task_id=task_id,
        round_id=round_id,
        announced_vote_count=announced_vote_count,
        transmission_index=transmission_index,
    )


def _summarize_events(
    *,
    method: str,
    cost_exchange_completion_ms: float,
    actionable_decision_ms: float,
    global_agreement_ms: float,
    events: list[CommunicationEvent],
) -> CoordinationTimingResult:
    return CoordinationTimingResult(
        method=method,
        cost_exchange_completion_ms=cost_exchange_completion_ms,
        actionable_decision_ms=actionable_decision_ms,
        global_agreement_ms=global_agreement_ms,
        message_count=len(events),
        payload_bytes=sum(event.payload_bytes for event in events),
        events=tuple(events),
    )


def simulate_ideal_full_information() -> CoordinationTimingResult:
    return CoordinationTimingResult(
        method="ideal_full_information",
        cost_exchange_completion_ms=0.0,
        actionable_decision_ms=0.0,
        global_agreement_ms=0.0,
        message_count=0,
        payload_bytes=0,
        events=(),
    )


def simulate_leader_hungarian(
    *,
    num_robots: int,
    num_tasks: int,
    sampler,
    leader_id: int = 0,
) -> CoordinationTimingResult:
    events: list[CommunicationEvent] = []
    row_bytes = cost_row_payload_bytes(num_tasks)

    inbound: list[CommunicationEvent] = []
    for sender_id in range(num_robots):
        if sender_id == leader_id:
            continue
        event = _unicast_event(
            phase="cost",
            sender_id=sender_id,
            receiver_id=leader_id,
            send_time_ms=0.0,
            payload_bytes=row_bytes,
            sampler=sampler,
        )
        events.append(event)
        inbound.append(event)

    cost_end = max(
        (event.arrival_time_ms for event in inbound),
        default=0.0,
    )

    assignment_event = _broadcast_event(
        phase="leader_assignment",
        sender_id=leader_id,
        send_time_ms=cost_end,
        payload_bytes=assignment_payload_bytes(num_tasks),
        sampler=sampler,
    )
    events.append(assignment_event)

    return _summarize_events(
        method="leader_hungarian",
        cost_exchange_completion_ms=cost_end,
        actionable_decision_ms=assignment_event.arrival_time_ms,
        global_agreement_ms=assignment_event.arrival_time_ms,
        events=events,
    )


def _broadcast_cost_exchange(
    *,
    num_robots: int,
    num_tasks: int,
    sampler,
) -> tuple[list[CommunicationEvent], tuple[float, ...]]:
    events: list[CommunicationEvent] = []
    row_bytes = cost_row_payload_bytes(num_tasks)

    for sender_id in range(num_robots):
        events.append(
            _broadcast_event(
                phase="cost",
                sender_id=sender_id,
                send_time_ms=0.0,
                payload_bytes=row_bytes,
                sampler=sampler,
            )
        )

    ready_times: list[float] = []
    for receiver_id in range(num_robots):
        required_arrivals = [
            event.arrival_time_ms
            for event in events
            if event.sender_id != receiver_id
        ]
        ready_times.append(max(required_arrivals, default=0.0))

    return events, tuple(ready_times)


def simulate_full_view_hungarian(
    *,
    num_robots: int,
    num_tasks: int,
    sampler,
) -> CoordinationTimingResult:
    events, ready_times = _broadcast_cost_exchange(
        num_robots=num_robots,
        num_tasks=num_tasks,
        sampler=sampler,
    )
    cost_end = max(ready_times, default=0.0)

    return _summarize_events(
        method="full_view_hungarian",
        cost_exchange_completion_ms=cost_end,
        actionable_decision_ms=cost_end,
        global_agreement_ms=cost_end,
        events=events,
    )


def simulate_democracy_hungarian(
    *,
    num_robots: int,
    num_tasks: int,
    assignment: AssignmentSolution,
    sampler,
) -> CoordinationTimingResult:
    cost_events, ready_times = _broadcast_cost_exchange(
        num_robots=num_robots,
        num_tasks=num_tasks,
        sampler=sampler,
    )
    events = list(cost_events)
    cost_end = max(ready_times, default=0.0)
    quorum = quorum_size(num_robots)

    winner_by_task = {
        task_id: robot_id
        for robot_id, task_id in assignment.assigned_pairs
    }
    if len(winner_by_task) != num_tasks:
        raise ValueError("assignment must contain one winner for every task")

    quorum_time_by_task: dict[int, float] = {}

    for task_id in range(num_tasks):
        winner_id = winner_by_task[task_id]
        vote_arrivals: list[float] = []

        for voter_id in range(num_robots):
            send_time = ready_times[voter_id]
            if voter_id == winner_id:
                vote_arrivals.append(send_time)
                continue

            event = _unicast_event(
                phase="vote",
                sender_id=voter_id,
                receiver_id=winner_id,
                send_time_ms=send_time,
                payload_bytes=VOTE_PAYLOAD_BYTES,
                sampler=sampler,
                task_id=task_id,
            )
            events.append(event)
            vote_arrivals.append(event.arrival_time_ms)

        vote_arrivals.sort()
        quorum_time_by_task[task_id] = vote_arrivals[quorum - 1]

    actionable_end = max(quorum_time_by_task.values(), default=cost_end)

    commit_arrivals: list[float] = []
    for task_id in range(num_tasks):
        winner_id = winner_by_task[task_id]
        event = _broadcast_event(
            phase="commit",
            sender_id=winner_id,
            send_time_ms=quorum_time_by_task[task_id],
            payload_bytes=COMMIT_PAYLOAD_BYTES,
            sampler=sampler,
            task_id=task_id,
        )
        events.append(event)
        commit_arrivals.append(event.arrival_time_ms)

    agreement_end = max(commit_arrivals, default=actionable_end)

    return _summarize_events(
        method="democracy_hungarian",
        cost_exchange_completion_ms=cost_end,
        actionable_decision_ms=actionable_end,
        global_agreement_ms=agreement_end,
        events=events,
    )



@dataclass(frozen=True)
class DeliveryObservation:
    phase: str
    sender_id: int
    receiver_id: int
    delivered: bool
    arrival_time_ms: float | None
    task_id: int | None = None
    round_id: int = 0
    transmission_index: int = 0


@dataclass(frozen=True)
class LossyCoordinationResult:
    method: str
    assigned_pairs: tuple[tuple[int, int], ...]
    total_cost: float
    total_tasks: int
    cost_phase_completion_ms: float
    decision_completion_ms: float
    global_agreement_ms: float
    logical_message_count: int
    payload_bytes: int
    lossy_delivery_opportunities: int
    lossy_delivered: int
    lossy_dropped: int
    task_timeout_count: int
    mean_visible_robot_rows: float
    events: tuple[CommunicationEvent, ...]
    deliveries: tuple[DeliveryObservation, ...]
    audit_visible_rows_by_voter: tuple[frozenset[int], ...] = ()
    audit_proposals_by_voter: tuple[AssignmentSolution, ...] = ()
    audit_counted_vote_ledgers: tuple[tuple[int, int, tuple[int, ...]], ...] = ()
    vote_decision_rule: str = "strict_majority"
    announcement_threshold: int = 0
    qualified_announcement_count: int = 0
    plurality_tie_break_count: int = 0
    plurality_winner_vote_count: int = 0
    budget_exhausted: bool = False
    budget_stop_phase: str | None = None
    budget_stop_diagnostic: Diagnostic | None = None

    @property
    def committed_tasks(self) -> int:
        return len(self.assigned_pairs)

    @property
    def task_commit_rate(self) -> float:
        if self.total_tasks <= 0:
            return 0.0
        return self.committed_tasks / self.total_tasks

    @property
    def full_assignment_success(self) -> bool:
        return self.committed_tasks == self.total_tasks


def _lossy_broadcast_deliveries(
    *,
    event: CommunicationEvent,
    num_robots: int,
    loss_sampler,
    p_loss: float,
    round_id: int,
    receiver_ids: tuple[int, ...] | None = None,
) -> tuple[DeliveryObservation, ...]:
    observations: list[DeliveryObservation] = []
    for receiver_id in (range(num_robots) if receiver_ids is None else receiver_ids):
        if receiver_id == event.sender_id:
            continue
        key = (
            f"broadcast|{event.phase}|{event.sender_id}|{receiver_id}|"
            f"{event.task_id if event.task_id is not None else '-'}|round={round_id}"
        )
        if event.transmission_index:
            key += f"|copy={event.transmission_index}"
        delivered = bool(loss_sampler.is_delivered(key, p_loss))
        observations.append(
            DeliveryObservation(
                phase=event.phase,
                sender_id=event.sender_id,
                receiver_id=receiver_id,
                delivered=delivered,
                arrival_time_ms=event.arrival_time_ms if delivered else None,
                task_id=event.task_id,
                round_id=round_id,
                transmission_index=event.transmission_index,
            )
        )
    return tuple(observations)


def _lossy_unicast_delivery(
    *,
    event: CommunicationEvent,
    loss_sampler,
    p_loss: float,
    round_id: int,
) -> DeliveryObservation:
    key = (
        f"unicast|{event.phase}|{event.sender_id}|{event.receiver_id}|"
        f"{event.task_id if event.task_id is not None else '-'}|round={round_id}"
    )
    if event.transmission_index:
        key += f"|copy={event.transmission_index}"
    delivered = bool(loss_sampler.is_delivered(key, p_loss))
    return DeliveryObservation(
        phase=event.phase,
        sender_id=event.sender_id,
        receiver_id=event.receiver_id,
        delivered=delivered,
        arrival_time_ms=event.arrival_time_ms if delivered else None,
        task_id=event.task_id,
        round_id=round_id,
        transmission_index=event.transmission_index,
    )



def transmit_repeated_remote_vote(
    *,
    voter_id: int,
    candidate_id: int,
    task_id: int,
    round_id: int,
    send_time_ms: float,
    phase_timeout_ms: float,
    vote_repetitions: int,
    sampler,
    loss_sampler,
    p_vote_loss: float,
    send_budget: SenderPayloadBudget | None = None,
    global_vote_deadline_ms: float | None = None,
) -> tuple[list[CommunicationEvent], list[DeliveryObservation], DeliveryObservation | None]:
    """Send independent fixed copies, return FIRST delivered physical ballot.

    This is open-loop packet repetition, NOT stop-and-wait ARQ. Every copy
    consumes a physical unicast event and one packet-loss observation.
    Copies are time-slotted one original packet-timeout apart. The candidate
    ledger still receives at most one logical vote, regardless of successes.
    """
    copies = validate_vote_repetitions(vote_repetitions)
    events: list[CommunicationEvent] = []
    observations: list[DeliveryObservation] = []
    for copy_index in range(copies):
        try:
            event = _unicast_event(
                phase="vote",
                sender_id=voter_id,
                receiver_id=candidate_id,
                send_time_ms=send_time_ms + copy_index * phase_timeout_ms,
                payload_bytes=VOTE_PAYLOAD_BYTES,
                sampler=sampler,
                task_id=task_id,
                round_id=round_id,
                transmission_index=copy_index,
                send_budget=send_budget,
            )
        except SenderBudgetExhausted:
            # The epoch owner treats any denied physical ballot as a hard stop.
            break
        obs = _lossy_unicast_delivery(
            event=event,
            loss_sampler=loss_sampler,
            p_loss=p_vote_loss,
            round_id=round_id,
        )
        events.append(event)
        observations.append(obs)
    # In E9G, physically delivered but post-deadline packets cannot vote.
    # Historical E1-E9F on-time semantics remain byte-for-byte unchanged.
    deadline = (
        send_time_ms + copies * phase_timeout_ms
        if global_vote_deadline_ms is None else global_vote_deadline_ms
    )
    delivered = [
        obs for obs in observations
        if obs.delivered and (
            (global_vote_deadline_ms is None
             and not isinstance(sampler, WifiCausalTimingSampler))
            or (obs.arrival_time_ms is not None
                and obs.arrival_time_ms <= deadline)
        )
    ]
    first_delivery = min(
        delivered, key=lambda obs: float(obs.arrival_time_ms)
    ) if delivered else None
    return events, observations, first_delivery


def _summarize_lossy_result(
    *,
    method: str,
    cost_matrix: tuple[tuple[float, ...], ...],
    assigned_pairs: list[tuple[int, int]] | tuple[tuple[int, int], ...],
    cost_phase_completion_ms: float,
    decision_completion_ms: float,
    global_agreement_ms: float,
    task_timeout_count: int,
    visible_counts: list[int] | tuple[int, ...],
    events: list[CommunicationEvent],
    deliveries: list[DeliveryObservation],
    audit_visible_rows_by_voter: tuple[frozenset[int], ...] = (),
    audit_proposals_by_voter: tuple[AssignmentSolution, ...] = (),
    audit_counted_vote_ledgers: tuple[tuple[int, int, tuple[int, ...]], ...] = (),
    robot_ids: tuple[int, ...] | None = None,
    task_ids: tuple[int, ...] | None = None,
    vote_decision_rule: str = "strict_majority",
    announcement_threshold: int = 0,
    qualified_announcement_count: int = 0,
    plurality_tie_break_count: int = 0,
    plurality_winner_vote_count: int = 0,
    budget_exhausted: bool = False,
    budget_stop_phase: str | None = None,
    budget_stop_diagnostic: Diagnostic | None = None,
) -> LossyCoordinationResult:
    pairs = tuple(sorted(tuple(assigned_pairs), key=lambda pair: (pair[1], pair[0])))
    validate_one_to_one_commits(pairs)
    total_tasks = len(cost_matrix[0])
    if robot_ids is None and task_ids is None:
        total_cost = float(sum(cost_matrix[r][t] for r, t in pairs))
    else:
        assert robot_ids is not None and task_ids is not None
        robot_to_local = {original: idx for idx, original in enumerate(robot_ids)}
        task_to_local = {original: idx for idx, original in enumerate(task_ids)}
        total_cost = float(sum(
            cost_matrix[robot_to_local[r]][task_to_local[t]] for r, t in pairs
        ))
    delivered = sum(int(observation.delivered) for observation in deliveries)
    opportunities = len(deliveries)
    mean_visible = (
        sum(visible_counts) / len(visible_counts)
        if visible_counts
        else 0.0
    )
    return LossyCoordinationResult(
        method=method,
        assigned_pairs=pairs,
        total_cost=total_cost,
        total_tasks=total_tasks,
        cost_phase_completion_ms=cost_phase_completion_ms,
        decision_completion_ms=decision_completion_ms,
        global_agreement_ms=global_agreement_ms,
        logical_message_count=len(events),
        payload_bytes=sum(event.payload_bytes for event in events),
        lossy_delivery_opportunities=opportunities,
        lossy_delivered=delivered,
        lossy_dropped=opportunities - delivered,
        task_timeout_count=task_timeout_count,
        mean_visible_robot_rows=mean_visible,
        events=tuple(events),
        deliveries=tuple(deliveries),
        audit_visible_rows_by_voter=audit_visible_rows_by_voter,
        audit_proposals_by_voter=audit_proposals_by_voter,
        audit_counted_vote_ledgers=audit_counted_vote_ledgers,
        vote_decision_rule=vote_decision_rule,
        announcement_threshold=announcement_threshold,
        qualified_announcement_count=qualified_announcement_count,
        plurality_tie_break_count=plurality_tie_break_count,
        plurality_winner_vote_count=plurality_winner_vote_count,
        budget_exhausted=budget_exhausted,
        budget_stop_phase=budget_stop_phase,
        budget_stop_diagnostic=budget_stop_diagnostic,
    )


def snapshot_counted_vote_ledgers(
    ledgers_by_task: dict[int, dict[int, set[int]]],
) -> tuple[tuple[int, int, tuple[int, ...]], ...]:
    return tuple(
        (task_id, candidate_id, tuple(sorted(voters)))
        for task_id, by_candidate in sorted(ledgers_by_task.items())
        for candidate_id, voters in sorted(by_candidate.items())
    )


def simulate_ideal_full_information_lossy_reference(
    *,
    cost_matrix: tuple[tuple[float, ...], ...],
    assignment: AssignmentSolution,
) -> LossyCoordinationResult:
    num_robots = len(cost_matrix)
    return _summarize_lossy_result(
        method="ideal_full_information",
        cost_matrix=cost_matrix,
        assigned_pairs=assignment.assigned_pairs,
        cost_phase_completion_ms=0.0,
        decision_completion_ms=0.0,
        global_agreement_ms=0.0,
        task_timeout_count=0,
        visible_counts=[num_robots],
        events=[],
        deliveries=[],
    )


def simulate_leader_hungarian_lossy(
    *,
    cost_matrix: tuple[tuple[float, ...], ...],
    sampler,
    loss_sampler,
    p_loss: float,
    phase_timeout_ms: float,
    leader_id: int = 0,
    round_id: int = 0,
) -> LossyCoordinationResult:
    num_robots = len(cost_matrix)
    num_tasks = len(cost_matrix[0])
    events: list[CommunicationEvent] = []
    deliveries: list[DeliveryObservation] = []
    visible = {leader_id}
    arrival_times: list[float] = []
    row_bytes = cost_row_payload_bytes(num_tasks)

    for sender_id in range(num_robots):
        if sender_id == leader_id:
            continue
        event = _unicast_event(
            phase="cost",
            sender_id=sender_id,
            receiver_id=leader_id,
            send_time_ms=0.0,
            payload_bytes=row_bytes,
            sampler=sampler,
        )
        events.append(event)
        observation = _lossy_unicast_delivery(
            event=event,
            loss_sampler=loss_sampler,
            p_loss=p_loss,
            round_id=round_id,
        )
        deliveries.append(observation)
        if observation.delivered:
            visible.add(sender_id)
            arrival_times.append(float(observation.arrival_time_ms))

    all_costs_received = len(visible) == num_robots
    cost_ready = (
        max(arrival_times, default=0.0)
        if all_costs_received
        else phase_timeout_ms
    )

    assignment = solve_visible_hungarian_assignment(
        cost_matrix,
        frozenset(visible),
    )

    announcement = _broadcast_event(
        phase="leader_assignment",
        sender_id=leader_id,
        send_time_ms=cost_ready,
        payload_bytes=assignment_payload_bytes(assignment.assigned_tasks),
        sampler=sampler,
    )
    events.append(announcement)

    task_timeouts = num_tasks - assignment.assigned_tasks
    return _summarize_lossy_result(
        method="leader_hungarian",
        cost_matrix=cost_matrix,
        assigned_pairs=assignment.assigned_pairs,
        cost_phase_completion_ms=cost_ready,
        decision_completion_ms=cost_ready,
        global_agreement_ms=announcement.arrival_time_ms,
        task_timeout_count=task_timeouts,
        visible_counts=[len(visible)],
        events=events,
        deliveries=deliveries,
    )


def transmit_cost_row_copies(
    *,
    sender_id: int,
    receiver_ids: tuple[int, ...],
    num_tasks: int,
    num_robots: int,
    sampler,
    loss_sampler,
    p_loss: float,
    phase_timeout_ms: float,
    round_id: int,
    cost_repetitions: int,
    send_budget: SenderPayloadBudget | None,
) -> tuple[list[CommunicationEvent], list[DeliveryObservation]]:
    """Physically emit each paid Cost copy; independent receiver loss per copy.

    This is fixed open-loop sender repetition, NOT reliable ACK/ARQ. Repeat
    copies never create extra cost rows, each copy has a unique physical key.
    """
    events: list[CommunicationEvent] = []
    deliveries: list[DeliveryObservation] = []
    for copy_index in range(cost_repetitions):
        try:
            event = _broadcast_event(
                phase="cost",
                sender_id=sender_id,
                send_time_ms=copy_index * phase_timeout_ms,
                payload_bytes=cost_row_payload_bytes(num_tasks),
                sampler=sampler,
                round_id=round_id,
                transmission_index=copy_index,
                send_budget=send_budget,
            )
        except SenderBudgetExhausted:
            break
        events.append(event)
        deliveries.extend(_lossy_broadcast_deliveries(
            event=event,
            num_robots=num_robots,
            loss_sampler=loss_sampler,
            p_loss=p_loss,
            round_id=round_id,
            receiver_ids=receiver_ids,
        ))
    return events, deliveries


def _simulate_lossy_cost_broadcasts(
    *,
    num_robots: int,
    num_tasks: int,
    sampler,
    loss_sampler,
    p_loss: float,
    phase_timeout_ms: float,
    round_id: int,
    robot_ids: tuple[int, ...] | None = None,
    send_budget: SenderPayloadBudget | None = None,
    cost_repetitions: int = 1,
    enforce_cost_deadline: bool = False,
) -> tuple[
    list[CommunicationEvent],
    list[DeliveryObservation],
    tuple[frozenset[int], ...],
    tuple[float, ...],
]:
    """Own each receiver's union of physically received Cost rows."""
    copies = validate_cost_repetitions(cost_repetitions)
    physical_ids = tuple(range(num_robots)) if robot_ids is None else robot_ids
    local_index = {robot_id: idx for idx, robot_id in enumerate(physical_ids)}
    events: list[CommunicationEvent] = []
    deliveries: list[DeliveryObservation] = []
    visible_by_receiver: list[set[int]] = [
        {robot_id} for robot_id in range(num_robots)
    ]
    arrivals_by_receiver: list[list[float]] = [
        [] for _ in range(num_robots)
    ]

    for sender_id in physical_ids:
        sent, observed = transmit_cost_row_copies(
            sender_id=sender_id,
            receiver_ids=physical_ids,
            num_tasks=num_tasks,
            num_robots=num_robots,
            sampler=sampler,
            loss_sampler=loss_sampler,
            p_loss=p_loss,
            phase_timeout_ms=phase_timeout_ms,
            round_id=round_id,
            cost_repetitions=copies,
            send_budget=send_budget,
        )
        events.extend(sent)
        deliveries.extend(observed)
        for observation in observed:
            # App-delivered frames received after the original Cost window
            # remain in the physical ledger but not in the voter Cost view.
            on_time = (
                (not enforce_cost_deadline and not isinstance(sampler, WifiCausalTimingSampler))
                or (observation.arrival_time_ms is not None
                    and observation.arrival_time_ms <= copies * phase_timeout_ms)
            )
            if observation.delivered and on_time:
                receiver_local_id = local_index[observation.receiver_id]
                visible_by_receiver[receiver_local_id].add(local_index[sender_id])
                arrivals_by_receiver[receiver_local_id].append(
                    float(observation.arrival_time_ms)
                )
        if send_budget is not None and send_budget.denied_messages:
            break

    visible = tuple(frozenset(rows) for rows in visible_by_receiver)
    if copies == 1:
        # Preserve EXACT original one-Cost-copy vote-ready deadline semantics.
        ready_times = tuple(
            max(arrivals_by_receiver[receiver_id], default=0.0)
            if len(visible[receiver_id]) == num_robots
            else phase_timeout_ms
            for receiver_id in range(num_robots)
        )
    else:
        # All open-loop copies run through the final Cost phase timeout window.
        # Never vote using a peer Cost that was not physically delivered.
        deadline = copies * phase_timeout_ms
        ready_times = tuple(
            max(deadline, max(arrivals_by_receiver[receiver_id], default=0.0))
            for receiver_id in range(num_robots)
        )
    return events, deliveries, visible, ready_times

def simulate_full_view_hungarian_lossy(
    *,
    cost_matrix: tuple[tuple[float, ...], ...],
    assignment: AssignmentSolution,
    sampler,
    loss_sampler,
    p_loss: float,
    phase_timeout_ms: float,
    round_id: int = 0,
) -> LossyCoordinationResult:
    num_robots = len(cost_matrix)
    num_tasks = len(cost_matrix[0])
    events, deliveries, visible, ready_times = _simulate_lossy_cost_broadcasts(
        num_robots=num_robots,
        num_tasks=num_tasks,
        sampler=sampler,
        loss_sampler=loss_sampler,
        p_loss=p_loss,
        phase_timeout_ms=phase_timeout_ms,
        round_id=round_id,
    )

    every_robot_has_full_view = all(
        len(rows) == num_robots for rows in visible
    )
    assigned_pairs = assignment.assigned_pairs if every_robot_has_full_view else ()
    timeout_count = 0 if every_robot_has_full_view else num_tasks
    completion = max(ready_times, default=0.0)

    return _summarize_lossy_result(
        method="full_view_hungarian",
        cost_matrix=cost_matrix,
        assigned_pairs=assigned_pairs,
        cost_phase_completion_ms=completion,
        decision_completion_ms=completion,
        global_agreement_ms=completion,
        task_timeout_count=timeout_count,
        visible_counts=[len(rows) for rows in visible],
        events=events,
        deliveries=deliveries,
    )




@dataclass(frozen=True)
class RetirementCostSnapshot:
    """One full cost-row broadcast epoch, retained independently at each voter."""
    robot_ids: tuple[int, ...]
    visible_by_voter: tuple[frozenset[int], ...]
    ready_times_ms: tuple[float, ...]
    events: tuple[CommunicationEvent, ...]
    deliveries: tuple[DeliveryObservation, ...]
    budget_exhausted: bool = False



def build_received_pose_retirement_snapshot(
    *,
    per_robot_positions: tuple[tuple[tuple[float, float], ...], ...],
) -> RetirementCostSnapshot:
    """Original Greedy cost-visibility owner: accept only physically full peer poses.

    Information transport must have decoded every peer pose for every voter
    BEFORE calling this function. No Cost rows are then transmitted: each
    voter can locally derive every cost from the received tasks and poses.
    """
    robots = len(per_robot_positions)
    full = frozenset(range(robots))
    if not robots or any(len(view) != robots for view in per_robot_positions):
        raise ProtocolError(Diagnostic(
            owner="coordination", function="build_received_pose_retirement_snapshot",
            category="dependency", code="INCOMPLETE_PEER_POSE_VIEWS",
            expected=f"complete {robots}x{robots} physically received robot poses",
            actual=tuple(len(view) for view in per_robot_positions),
        ))
    for voter_id, view in enumerate(per_robot_positions):
        for owner_id, claimed_pose in enumerate(view):
            if claimed_pose != per_robot_positions[owner_id][owner_id]:
                raise ProtocolError(Diagnostic(
                    owner="coordination", function="build_received_pose_retirement_snapshot",
                    category="contract", code="INCONSISTENT_PEER_POSE_SOURCE",
                    expected=per_robot_positions[owner_id][owner_id],
                    actual=claimed_pose,
                    details=f"voter={voter_id}; source={owner_id}",
                ))
    return RetirementCostSnapshot(
        robot_ids=tuple(range(robots)),
        visible_by_voter=tuple(full for _ in range(robots)),
        ready_times_ms=tuple(0.0 for _ in range(robots)),
        events=(),
        deliveries=(),
    )


def validate_preknown_retirement_cost_snapshot(
    *,
    snapshot: RetirementCostSnapshot,
    num_robots: int,
    voting_strategy: str,
) -> None:
    """Require an all-peer, sender-accounted external information provenance."""
    expected_ids = tuple(range(num_robots))
    if (
        type(snapshot) is not RetirementCostSnapshot
        or voting_strategy != "greedy_task"
        or snapshot.robot_ids != expected_ids
        or snapshot.visible_by_voter != tuple(frozenset(expected_ids) for _ in expected_ids)
        or snapshot.ready_times_ms != tuple(0.0 for _ in expected_ids)
        or snapshot.events or snapshot.deliveries or snapshot.budget_exhausted
    ):
        raise ProtocolError(Diagnostic(
            owner="coordination", function="validate_preknown_retirement_cost_snapshot",
            category="contract", code="INVALID_PREKNOWN_COST_PROVENANCE",
            expected="Greedy all-robot physically received poses; no unpaid Cost events",
            actual=(type(snapshot).__name__, voting_strategy,
                    getattr(snapshot, "robot_ids", None)),
        ))


def capture_retirement_cost_snapshot(
    *,
    cost_matrix: tuple[tuple[float, ...], ...],
    sampler,
    loss_sampler,
    p_loss: float,
    phase_timeout_ms: float,
    send_budget: SenderPayloadBudget | None = None,
    cost_repetitions: int = 1,
    enforce_cost_deadline: bool = False,
) -> RetirementCostSnapshot:
    """Build retained snapshot from only physically delivered original Costs."""
    num_robots, num_tasks = validate_cost_matrix(cost_matrix)
    events, deliveries, visible, ready_times = _simulate_lossy_cost_broadcasts(
        num_robots=num_robots,
        num_tasks=num_tasks,
        sampler=sampler,
        loss_sampler=loss_sampler,
        p_loss=p_loss,
        phase_timeout_ms=phase_timeout_ms,
        round_id=0,
        send_budget=send_budget,
        cost_repetitions=cost_repetitions,
        enforce_cost_deadline=enforce_cost_deadline,
    )
    return RetirementCostSnapshot(
        robot_ids=tuple(range(num_robots)),
        visible_by_voter=visible,
        ready_times_ms=ready_times,
        events=tuple(events),
        deliveries=tuple(deliveries),
        budget_exhausted=(send_budget is not None and send_budget.denied_messages > 0),
    )


def resolve_retirement_cost_view(
    *,
    snapshot: RetirementCostSnapshot,
    active_robot_ids: tuple[int, ...],
    round_id: int,
) -> tuple[
    list[CommunicationEvent],
    list[DeliveryObservation],
    tuple[frozenset[int], ...],
    tuple[float, ...],
]:
    """Discard retired candidates from each local view, never restore missing rows."""
    source_index = {r: i for i, r in enumerate(snapshot.robot_ids)}
    if (
        len(set(active_robot_ids)) != len(active_robot_ids)
        or not set(active_robot_ids).issubset(source_index)
        or (round_id == 0 and active_robot_ids != snapshot.robot_ids)
    ):
        raise ProtocolError(
            Diagnostic(
                owner="coordination",
                function="resolve_retirement_cost_view",
                category="state",
                code="INVALID_RETAINED_COST_ELECTORATE",
                expected="active IDs in initial snapshot; complete team in epoch 0",
                actual=(round_id, active_robot_ids),
            )
        )
    active_local = {r: i for i, r in enumerate(active_robot_ids)}
    visible = tuple(
        frozenset(
            active_local[snapshot.robot_ids[source_row]]
            for source_row in snapshot.visible_by_voter[source_index[voter]]
            if snapshot.robot_ids[source_row] in active_local
        )
        for voter in active_robot_ids
    )
    if round_id == 0:
        return (
            list(snapshot.events),
            list(snapshot.deliveries),
            visible,
            snapshot.ready_times_ms,
        )
    return [], [], visible, tuple(0.0 for _ in active_robot_ids)


def validate_epoch_voting_strategy(
    *,
    strategy: str,
    num_tasks: int,
) -> None:
    if strategy not in ("hungarian", "greedy_task", "greedy_batch", "greedy_batch_task_order", "probabilistic_batch"):
        raise ProtocolError(
            Diagnostic(
                owner="coordination",
                function="validate_epoch_voting_strategy",
                category="data",
                code="UNKNOWN_VOTING_STRATEGY",
                expected=("hungarian", "greedy_task", "greedy_batch", "greedy_batch_task_order", "probabilistic_batch"),
                actual=strategy,
            )
        )
    if strategy == "greedy_task" and num_tasks != 1:
        raise ProtocolError(
            Diagnostic(
                owner="coordination",
                function="validate_epoch_voting_strategy",
                category="planning",
                code="GREEDY_EPOCH_REQUIRES_SINGLE_TASK",
                expected=1,
                actual=num_tasks,
            )
        )


def build_epoch_local_proposals(
    *,
    cost_matrix: tuple[tuple[float, ...], ...],
    visible: tuple[frozenset[int], ...],
    physical_robots: tuple[int, ...],
    physical_tasks: tuple[int, ...],
    strategy: str,
) -> tuple[AssignmentSolution, ...]:
    if strategy == "greedy_batch":
        local_solutions = tuple(
            solve_visible_batched_greedy_assignment(cost_matrix, rows)
            for rows in visible
        )
    elif strategy == "greedy_batch_task_order":
        local_solutions = tuple(
            solve_visible_task_ordered_greedy_assignment(cost_matrix, rows)
            for rows in visible
        )
    elif strategy == "greedy_task":
        local_solutions = solve_all_visible_greedy_task_votes(
            cost_matrix=cost_matrix,
            visible_by_voter=visible,
        )
    else:
        local_solutions = tuple(
            solve_visible_hungarian_assignment(cost_matrix, rows)
            for rows in visible
        )
    return tuple(
        map_epoch_local_proposal(
            assignment=local_solutions[voter_local_id],
            robot_ids=physical_robots,
            task_ids=physical_tasks,
        )
        for voter_local_id in range(len(physical_robots))
    )



def validate_probabilistic_batch_scope(
    *, voting_strategy: str, max_rounds: int, cost_repetitions: int,
    vote_repetitions: int, batch_vote_scope: str,
    probabilistic_seed: int | None, votes_per_voter: int,
    temperature: float, margin_rule: str, enforce_vote_deadline: bool,
    send_budget: SenderPayloadBudget | None,
    preknown_cost_snapshot: RetirementCostSnapshot | None,
) -> None:
    """One-shot probabilistic mode cannot silently acquire retries or hidden Cost."""
    if voting_strategy != "probabilistic_batch":
        return
    valid=(
        max_rounds == 1 and cost_repetitions == 1 and vote_repetitions == 1
        and batch_vote_scope == "all" and enforce_vote_deadline
        and send_budget is None and preknown_cost_snapshot is None
        and type(probabilistic_seed) is int and probabilistic_seed >= 0
        and type(votes_per_voter) is int and 1 <= votes_per_voter <= 255
        and type(temperature) in (int,float) and math.isfinite(temperature)
        and temperature > 0 and margin_rule in ("absolute","normalized")
    )
    if not valid:
        raise ProtocolError(Diagnostic(
            owner="coordination", function="validate_probabilistic_batch_scope",
            category="contract", code="P2J_ONE_SHOT_SCOPE_VIOLATION",
            expected="one Cost and one Vote Batch, one epoch, finite tau>0, "
                     "tickets 1..255, seed>=0, absolute/normalized margin, "
                     "received cutoff, no external Cost, no send budget",
            actual={"max_rounds":max_rounds,"cost_repetitions":cost_repetitions,
                    "vote_repetitions":vote_repetitions,"batch_vote_scope":batch_vote_scope,
                    "seed":probabilistic_seed,"votes_per_voter":votes_per_voter,
                    "temperature":temperature,"margin_rule":margin_rule,
                    "enforce_vote_deadline":enforce_vote_deadline,
                    "send_budget":send_budget is not None,
                    "preknown_cost_snapshot":preknown_cost_snapshot is not None},
        ))


def build_epoch_probabilistic_ballots(
    *, cost_matrix: tuple[tuple[float, ...], ...],
    visible: tuple[frozenset[int], ...],
    physical_robots: tuple[int, ...],
    physical_tasks: tuple[int, ...],
    seed: int, votes_per_voter: int, temperature: float, round_id: int,
) -> tuple[tuple[tuple[int, int, int], ...], ...]:
    """Plan only from each voter's received Cost; map local IDs to real IDs."""
    if len(visible)!=len(physical_robots):
        raise ProtocolError(Diagnostic(
            owner="coordination", function="build_epoch_probabilistic_ballots",
            category="contract", code="P2J_LOCAL_VIEW_COUNT_MISMATCH",
            expected=len(physical_robots), actual=len(visible),
        ))
    ballots=[]
    for voter_local_id, rows in enumerate(visible):
        weighted=sample_probabilistic_pair_votes(
            cost_matrix=cost_matrix, visible_robot_ids=rows,
            voter_id=voter_local_id, seed=seed, votes_per_voter=votes_per_voter,
            temperature=temperature, round_id=round_id,
        )
        ballots.append(tuple((physical_tasks[task],physical_robots[robot],count)
                             for task,robot,count in weighted))
    return tuple(ballots)


def validate_batch_vote_scope(*, voting_strategy: str, batch_vote_scope: str) -> None:
    """Only Global Greedy batch proposals may opt into single-task voting."""
    if (batch_vote_scope not in ("all", "one_task")
            or (batch_vote_scope == "one_task" and voting_strategy != "greedy_batch")):
        raise ProtocolError(Diagnostic(
            owner="coordination", function="validate_batch_vote_scope",
            category="planning", code="P2F_INVALID_BATCH_VOTE_SCOPE",
            expected="all for any strategy; one_task only for greedy_batch",
            actual={"strategy": voting_strategy, "scope": batch_vote_scope},
        ))


def validate_batch_vote_task_ids(
    *, voting_strategy: str, physical_tasks: tuple[int, ...],
    voted_task_ids: tuple[int, ...] | None,
) -> None:
    """Only one physically pending task can be chosen for serial batch voting."""
    if voted_task_ids is None:
        return
    if (voting_strategy != "greedy_batch" or type(voted_task_ids) is not tuple
            or len(voted_task_ids) != 1 or voted_task_ids[0] not in physical_tasks):
        raise ProtocolError(Diagnostic(
            owner="coordination", function="validate_batch_vote_task_ids",
            category="contract", code="P2F_INVALID_VOTED_TASK_ID",
            expected="one pending physical task for greedy_batch",
            actual={"strategy": voting_strategy, "pending": physical_tasks,
                    "voted": voted_task_ids},
        ))


def validate_epoch_identity_mapping(
    *,
    num_robots: int,
    num_tasks: int,
    robot_ids: tuple[int, ...] | None,
    task_ids: tuple[int, ...] | None,
) -> tuple[tuple[int, ...], tuple[int, ...]]:
    physical_robots = tuple(range(num_robots)) if robot_ids is None else tuple(robot_ids)
    physical_tasks = tuple(range(num_tasks)) if task_ids is None else tuple(task_ids)

    if (
        len(physical_robots) != num_robots
        or len(set(physical_robots)) != num_robots
        or any(r < 0 for r in physical_robots)
        or len(physical_tasks) != num_tasks
        or len(set(physical_tasks)) != num_tasks
        or any(t < 0 for t in physical_tasks)
    ):
        raise ProtocolError(
            Diagnostic(
                owner="coordination",
                function="validate_epoch_identity_mapping",
                category="data",
                code="INVALID_EPOCH_ID_MAPPING",
                expected=f"{num_robots} unique nonnegative robot IDs; {num_tasks} unique nonnegative task IDs",
                actual=(physical_robots, physical_tasks),
            )
        )
    return physical_robots, physical_tasks


def map_epoch_local_proposal(
    *,
    assignment: AssignmentSolution,
    robot_ids: tuple[int, ...],
    task_ids: tuple[int, ...],
) -> AssignmentSolution:
    return AssignmentSolution(
        assigned_pairs=tuple(
            sorted(
                ((robot_ids[r], task_ids[t]) for r, t in assignment.assigned_pairs),
                key=lambda pair: (pair[1], pair[0]),
            )
        ),
        total_cost=assignment.total_cost,
    )



def validate_vote_decision_rule(
    *,
    rule: str,
    voting_strategy: str,
    num_tasks: int,
) -> None:
    """Reject the removed fallback rule instead of silently reinterpreting it."""
    if rule == "quarter_plurality_fallback":
        raise ProtocolError(
            Diagnostic(
                owner="coordination",
                function="validate_vote_decision_rule",
                category="contract",
                code="REMOVED_PLURALITY_FALLBACK_RULE",
                expected="quarter_plurality (no winner if no announcement)",
                actual=rule,
            )
        )
    if rule not in ("strict_majority", "quarter_plurality", "received_plurality"):
        raise ProtocolError(
            Diagnostic(
                owner="coordination",
                function="validate_vote_decision_rule",
                category="data",
                code="UNKNOWN_VOTE_DECISION_RULE",
                expected=("strict_majority", "quarter_plurality", "received_plurality"),
                actual=rule,
            )
        )
    if voting_strategy in ("greedy_batch", "greedy_batch_task_order", "probabilistic_batch") and rule != "received_plurality":
        raise ProtocolError(Diagnostic(
            owner="coordination", function="validate_vote_decision_rule",
            category="planning", code="BATCH_GREEDY_REQUIRES_RECEIVED_PLURALITY",
            expected="received_plurality", actual=rule,
        ))
    if rule in ("quarter_plurality", "received_plurality") and (
        (voting_strategy == "greedy_task" and num_tasks != 1)
        or (voting_strategy in ("greedy_batch", "greedy_batch_task_order", "probabilistic_batch")
            and rule != "received_plurality")
        or voting_strategy not in ("greedy_task", "greedy_batch", "greedy_batch_task_order", "probabilistic_batch")
    ):
        raise ProtocolError(
            Diagnostic(
                owner="coordination",
                function="validate_vote_decision_rule",
                category="planning",
                code="PLURALITY_REQUIRES_ONE_TASK_GREEDY",
                expected="one-task Greedy, or multi-task Greedy batch using received_plurality",
                actual=(voting_strategy, num_tasks),
            )
        )


def build_quarter_plurality_claims(
    *,
    ledgers_by_candidate: dict[int, set[int]],
    eligible_robots: frozenset[int],
    decision_rule: str = "quarter_plurality",
) -> tuple[CandidateVoteAnnouncement, ...]:
    """Announce original quarter or E9H positive-receipt claims."""
    threshold = plurality_announcement_threshold(len(eligible_robots), decision_rule)
    return tuple(
        CandidateVoteAnnouncement(
            candidate_id=candidate_id,
            received_votes=len(ledgers_by_candidate.get(candidate_id, set())),
        )
        for candidate_id in sorted(eligible_robots)
        if len(ledgers_by_candidate.get(candidate_id, set())) >= threshold
    )


def simulate_quarter_plurality_announcement_phase(
    *,
    ledgers_by_candidate: dict[int, set[int]],
    eligible_robots: frozenset[int],
    task_id: int,
    round_id: int,
    vote_deadline_ms: float,
    sampler,
    send_budget: SenderPayloadBudget | None = None,
    decision_rule: str = "quarter_plurality",
) -> tuple[PluralityResolution | None, tuple[CommunicationEvent, ...], float]:
    """Compare ONLY qualified candidates; nobody qualifies means timeout.

    Reliable score announcements are sent after the vote deadline so they
    contain final scores. With zero announcements there are zero extra
    messages, zero commits, and no self-election or backup communication.
    """
    claims = build_quarter_plurality_claims(
        ledgers_by_candidate=ledgers_by_candidate,
        eligible_robots=eligible_robots,
        decision_rule=decision_rule,
    )
    resolution = resolve_unique_plurality_claims(
        announcements=claims,
        eligible_robots=eligible_robots,
        task_id=task_id,
        round_id=round_id,
        decision_rule=decision_rule,
    )
    if resolution is None:
        return None, (), vote_deadline_ms

    events: list[CommunicationEvent] = []
    for claim in claims:
        try:
            event = _broadcast_event(
                phase="vote_score_announcement",
                sender_id=claim.candidate_id,
                send_time_ms=vote_deadline_ms,
                payload_bytes=VOTE_SCORE_ANNOUNCEMENT_BYTES,
                sampler=sampler,
                task_id=task_id,
                round_id=round_id,
                announced_vote_count=claim.received_votes,
                send_budget=send_budget,
            )
        except SenderBudgetExhausted:
            # An incomplete score-announcement set cannot select a valid executor.
            return None, tuple(events), max(
                (item.arrival_time_ms for item in events), default=vote_deadline_ms
            )
        events.append(event)
    # All qualified final scores are reliably broadcast in this opt-in model.
    return resolution, tuple(events), max(event.arrival_time_ms for event in events)



def validate_budgeted_retirement_scope(
    *,
    send_budget: SenderPayloadBudget | None,
    voting_strategy: str,
    vote_decision_rule: str,
    vote_repetitions: int,
) -> None:
    """E9B-2 only covers Greedy single-task pure 25% with one Vote copy."""
    if send_budget is None:
        return
    if (
        type(send_budget) is not SenderPayloadBudget
        or voting_strategy != "greedy_task"
        or vote_decision_rule != "quarter_plurality"
        or vote_repetitions != 1
    ):
        raise ProtocolError(Diagnostic(
            owner="coordination",
            function="validate_budgeted_retirement_scope",
            category="planning",
            code="BUDGETED_RETIREMENT_REQUIRES_GREEDY_QUARTER_K1",
            expected="SenderPayloadBudget, greedy_task, quarter_plurality, vote_repetitions=1",
            actual=(type(send_budget).__name__, voting_strategy,
                    vote_decision_rule, vote_repetitions),
        ))


def summarize_budget_exhausted_epoch(
    *,
    cost_matrix: tuple[tuple[float, ...], ...],
    events: list[CommunicationEvent],
    deliveries: list[DeliveryObservation],
    visible: tuple[frozenset[int], ...],
    cost_completion_ms: float,
    stop_phase: str,
    send_budget: SenderPayloadBudget,
) -> LossyCoordinationResult:
    """Preserve every emitted packet while refusing all uncommitted task claims.

    A denied transmission never creates an event. This function does not
    run any voting, optimizer, or retirement logic. Its stage accounting is
    conservative: elapsed time is the last actually emitted event arrival.
    """
    diagnostic = send_budget.last_denied_diagnostic
    if diagnostic is None or diagnostic.code != "SEND_PAYLOAD_BUDGET_EXHAUSTED":
        raise ProtocolError(Diagnostic(
            owner="coordination", function="summarize_budget_exhausted_epoch",
            category="contract", code="MISSING_PHYSICAL_BUDGET_FAILURE",
            expected="network.reserve_sender_payload SEND_PAYLOAD_BUDGET_EXHAUSTED",
            actual=diagnostic,
        ))
    last_emitted_ms = max((event.arrival_time_ms for event in events), default=0.0)
    return _summarize_lossy_result(
        method="democracy_greedy_quarter_plurality",
        cost_matrix=cost_matrix,
        assigned_pairs=(),
        cost_phase_completion_ms=min(cost_completion_ms, last_emitted_ms),
        decision_completion_ms=last_emitted_ms,
        global_agreement_ms=last_emitted_ms,
        task_timeout_count=len(cost_matrix[0]),
        visible_counts=[len(rows) for rows in visible],
        events=events,
        deliveries=deliveries,
        vote_decision_rule="quarter_plurality",
        announcement_threshold=quarter_vote_announcement_threshold(len(visible)),
        budget_exhausted=True,
        budget_stop_phase=stop_phase,
        budget_stop_diagnostic=diagnostic,
    )


_BATCH_HEADER = struct.Struct("<4sIII")
_BATCH_RECORD = struct.Struct("<II")
_BATCH_MAX_PACKET_BYTES = 1200



_PROB_HEADER = struct.Struct("<4sIII")
_PROB_VOTE_RECORD = struct.Struct("<BBH")
_PROB_SCORE_RECORD = struct.Struct("<BHd")


def encode_probabilistic_vote_packet(
    *, round_id: int, sender_id: int,
    records: tuple[tuple[int, int, int], ...],
    votes_per_voter: int,
) -> bytes:
    """One physical PVOT DATA frame; 100 tickets need at most 416 bytes."""
    try:
        valid=(
            1 <= len(records) <= votes_per_voter <= 255
            and sum(count for _task,_robot,count in records)==votes_per_voter
            and len({(task,robot) for task,robot,_count in records})==len(records)
            and all(type(task) is int and 0 <= task <= 255
                    and type(robot) is int and 0 <= robot <= 255
                    and type(count) is int and 1 <= count <= 65535
                    for task,robot,count in records)
        )
    except (TypeError, ValueError):
        valid=False
    if not valid:
        raise ProtocolError(Diagnostic(
            owner="coordination", function="encode_probabilistic_vote_packet",
            category="data", code="P2J_INVALID_VOTE_TICKETS",
            expected=f"{votes_per_voter} positive aggregated tickets with unique uint8 pairs",
            actual=records[:8] if isinstance(records,tuple) else type(records).__name__,
        ))
    try:
        packet=_PROB_HEADER.pack(b"PVOT",round_id,sender_id,len(records))+b"".join(
            _PROB_VOTE_RECORD.pack(task,robot,count) for task,robot,count in records
        )
    except (struct.error, TypeError, ValueError) as exc:
        raise ProtocolError(Diagnostic(
            owner="coordination", function="encode_probabilistic_vote_packet",
            category="data", code="P2J_INVALID_VOTE_PACKET_FIELDS",
            expected="uint32 epoch/sender and uint8 task/robot, uint16 vote count",
            actual=str(exc),
        )) from exc
    if len(packet)>_BATCH_MAX_PACKET_BYTES:
        raise ProtocolError(Diagnostic(
            owner="coordination", function="encode_probabilistic_vote_packet",
            category="contract", code="P2J_VOTE_PACKET_OVER_MTU",
            expected=f"<= {_BATCH_MAX_PACKET_BYTES} B one SEND",
            actual=len(packet),
        ))
    return packet


def decode_probabilistic_vote_packet(
    packet: bytes, *, round_id: int, sender_id: int,
    physical_robots: tuple[int, ...], physical_tasks: tuple[int, ...],
    votes_per_voter: int,
) -> tuple[tuple[int, int, int], ...]:
    """No receiver can count a Vote without a genuine decoded delivered frame."""
    valid=isinstance(packet,bytes) and len(packet)>=_PROB_HEADER.size
    if valid:
        magic,observed_round,observed_sender,record_count=_PROB_HEADER.unpack_from(packet)
        valid=(
            magic==b"PVOT" and observed_round==round_id
            and observed_sender==sender_id and 1 <= record_count <= votes_per_voter
            and len(packet)==_PROB_HEADER.size+record_count*_PROB_VOTE_RECORD.size
        )
    if not valid:
        raise ProtocolError(Diagnostic(
            owner="coordination", function="decode_probabilistic_vote_packet",
            category="contract", code="P2J_INVALID_RECEIVED_VOTE",
            expected=(b"PVOT",round_id,sender_id,"valid count/size"),
            actual={"size":len(packet) if isinstance(packet,bytes) else None},
        ))
    records=tuple(_PROB_VOTE_RECORD.unpack_from(
        packet,_PROB_HEADER.size+i*_PROB_VOTE_RECORD.size
    ) for i in range(record_count))
    if (sum(v for _t,_r,v in records)!=votes_per_voter
            or len({(t,r) for t,r,_v in records})!=len(records)
            or any(t not in physical_tasks or r not in physical_robots or v==0
                   for t,r,v in records)):
        raise ProtocolError(Diagnostic(
            owner="coordination", function="decode_probabilistic_vote_packet",
            category="contract", code="P2J_RECEIVED_VOTE_CONTENT_INVALID",
            expected=f"{votes_per_voter} tickets for pending physical IDs, unique pairs",
            actual=records[:8],
        ))
    return records


def encode_probabilistic_score_packet(
    *, round_id: int, sender_id: int,
    records: tuple[tuple[int, int, float], ...],
) -> bytes:
    """Candidate-signed positive Vote counts and its own local executor Cost.

    At 100 tasks a physically paid PSCR packet is at most 1116 B:
    16B header + 100*(1B task + 2B votes + 8B own Cost). No secret Cost
    row from another candidate may be placed in the announcement.
    """
    if (not records or len(records)>255
            or len({task for task,_,_ in records})!=len(records)
            or any(type(task) is not int or not 0<=task<=255
                   or type(count) is not int or not 1<=count<=65535
                   or type(cost) not in (int,float) or not math.isfinite(cost)
                   or cost<0 for task,count,cost in records)):
        raise ProtocolError(Diagnostic(
            owner="coordination", function="encode_probabilistic_score_packet",
            category="data", code="P2J_INVALID_SCORE_RECORDS",
            expected="one finite own cost and positive uint16 count per uint8 task",
            actual=records[:8],
        ))
    try:
        packet=_PROB_HEADER.pack(b"PSCR",round_id,sender_id,len(records))+b"".join(
            _PROB_SCORE_RECORD.pack(task,count,cost) for task,count,cost in records
        )
    except (struct.error,TypeError,ValueError) as exc:
        raise ProtocolError(Diagnostic(
            owner="coordination", function="encode_probabilistic_score_packet",
            category="data", code="P2J_SCORE_ENCODE_FAILED",
            expected="uint32 epoch/sender, uint8 task, uint16 count, float64 self Cost",
            actual=str(exc),
        )) from exc
    if len(packet)>_BATCH_MAX_PACKET_BYTES:
        raise ProtocolError(Diagnostic(
            owner="coordination", function="encode_probabilistic_score_packet",
            category="contract", code="P2J_SCORE_PACKET_OVER_MTU",
            expected=f"<= {_BATCH_MAX_PACKET_BYTES} B one SEND",
            actual=len(packet),
        ))
    return packet


def decode_probabilistic_score_packet(
    packet: bytes, *, round_id: int, sender_id: int,
    physical_tasks: tuple[int, ...],
) -> tuple[tuple[int, int, float], ...]:
    valid=isinstance(packet,bytes) and len(packet)>=_PROB_HEADER.size
    if valid:
        magic,observed_round,observed_sender,record_count=_PROB_HEADER.unpack_from(packet)
        valid=(
            magic==b"PSCR" and observed_round==round_id
            and observed_sender==sender_id and 1<=record_count<=255
            and len(packet)==_PROB_HEADER.size+record_count*_PROB_SCORE_RECORD.size
        )
    if not valid:
        raise ProtocolError(Diagnostic(
            owner="coordination", function="decode_probabilistic_score_packet",
            category="contract", code="P2J_INVALID_RECEIVED_SCORE",
            expected=(b"PSCR",round_id,sender_id,"valid count/size"),
            actual={"size":len(packet) if isinstance(packet,bytes) else None},
        ))
    records=tuple(_PROB_SCORE_RECORD.unpack_from(
        packet,_PROB_HEADER.size+i*_PROB_SCORE_RECORD.size
    ) for i in range(record_count))
    if (len({task for task,_,_ in records})!=len(records)
            or any(task not in physical_tasks or votes==0
                   or not math.isfinite(cost) or cost<0
                   for task,votes,cost in records)):
        raise ProtocolError(Diagnostic(
            owner="coordination", function="decode_probabilistic_score_packet",
            category="contract", code="P2J_RECEIVED_SCORE_CONTENT_INVALID",
            expected="distinct pending tasks, positive votes and finite own Cost",
            actual=records[:8],
        ))
    return records


def collect_probabilistic_batch_votes(
    *, ballots: tuple[tuple[tuple[int, int, int], ...], ...],
    physical_robots: tuple[int, ...], physical_tasks: tuple[int, ...],
    ready_times: tuple[float, ...], round_id: int, cutoff_ms: float,
    sampler, loss_sampler, p_vote_loss: float, votes_per_voter: int,
) -> tuple[list[CommunicationEvent], list[DeliveryObservation],
           dict[tuple[int,int],int]]:
    """One real Vote broadcast per voter, candidate receives counted tickets."""
    if len(ballots)!=len(physical_robots) or len(ready_times)!=len(physical_robots):
        raise ProtocolError(Diagnostic(
            owner="coordination", function="collect_probabilistic_batch_votes",
            category="contract", code="P2J_VOTER_BALLOT_COUNT_MISMATCH",
            expected=len(physical_robots), actual=(len(ballots),len(ready_times)),
        ))
    events=[]
    deliveries=[]
    counts: dict[tuple[int,int],int]={}
    order=(
        sorted(range(len(physical_robots)),key=lambda i:(ready_times[i],physical_robots[i]))
        if isinstance(sampler,WifiCausalTimingSampler) else range(len(physical_robots))
    )
    for i in order:
        sender=physical_robots[i]
        packet=encode_probabilistic_vote_packet(
            round_id=round_id,sender_id=sender,
            records=ballots[i],votes_per_voter=votes_per_voter,
        )
        event=_broadcast_event(
            phase="vote",sender_id=sender,round_id=round_id,task_id=None,
            send_time_ms=ready_times[i],payload_bytes=len(packet),sampler=sampler,
        )
        events.append(event)
        observations=_lossy_broadcast_deliveries(
            event=event,num_robots=len(physical_robots),
            receiver_ids=physical_robots,loss_sampler=loss_sampler,
            p_loss=p_vote_loss,round_id=round_id,
        )
        deliveries.extend(observations)
        records=decode_probabilistic_vote_packet(
            packet,round_id=round_id,sender_id=sender,
            physical_robots=physical_robots,physical_tasks=physical_tasks,
            votes_per_voter=votes_per_voter,
        )
        if ready_times[i]<=cutoff_ms:
            for task,candidate,tickets in records:
                if candidate==sender:
                    key=(task,candidate)
                    counts[key]=counts.get(key,0)+tickets
        for receipt in observations:
            if (not receipt.delivered or receipt.arrival_time_ms is None
                    or receipt.arrival_time_ms>cutoff_ms):
                continue
            for task,candidate,tickets in records:
                if candidate==receipt.receiver_id:
                    key=(task,candidate)
                    counts[key]=counts.get(key,0)+tickets
    return events,deliveries,counts


def publish_probabilistic_batch_scores(
    *, counted_votes: dict[tuple[int,int],int],
    cost_matrix: tuple[tuple[float,...],...],
    physical_robots: tuple[int,...],physical_tasks: tuple[int,...],
    round_id: int,release_ms: float,sampler,
) -> tuple[list[CommunicationEvent],dict[tuple[int,int],tuple[int,float]]]:
    """One reliable positive Score broadcast per candidate using OWN Cost only."""
    robot_index={robot:i for i,robot in enumerate(physical_robots)}
    task_index={task:i for i,task in enumerate(physical_tasks)}
    events=[]
    certified={}
    for candidate in physical_robots:
        records=tuple(sorted(
            (task,count,float(cost_matrix[robot_index[candidate]][task_index[task]]))
            for (task,robot),count in counted_votes.items()
            if robot==candidate and task in task_index and count>0
        ))
        if not records:
            continue
        packet=encode_probabilistic_score_packet(
            round_id=round_id,sender_id=candidate,records=records,
        )
        event=_broadcast_event(
            phase="vote_score_announcement",sender_id=candidate,
            task_id=None,round_id=round_id,send_time_ms=release_ms,
            payload_bytes=len(packet),sampler=sampler,
            announced_vote_count=sum(count for _task,count,_cost in records),
        )
        events.append(event)
        for task,count,own_cost in decode_probabilistic_score_packet(
            packet,round_id=round_id,sender_id=candidate,
            physical_tasks=physical_tasks,
        ):
            certified[(task,candidate)]=(count,own_cost)
    return events,certified


def resolve_dynamic_probability_margin_winners(
    *, scores: dict[tuple[int,int],tuple[int,float]],
    physical_tasks: tuple[int,...],physical_robots: tuple[int,...],
    margin_rule: str="absolute",
) -> tuple[tuple[tuple[int,int],...],int]:
    """No task-ID order: recompute EACH task's top-two margin after retirement.

    Select highest task margin, then top-voted candidate on that task, with
    announced own Cost breaking same-vote candidate ties. Remove robot and
    task, recompute every remaining margin from eligible Score packets. Zero
    positive votes = no candidate; never reconstruct missing Cost or Vote.
    """
    if margin_rule not in ("absolute","normalized"):
        raise ProtocolError(Diagnostic(
            owner="coordination",function="resolve_dynamic_probability_margin_winners",
            category="data",code="P2J_UNKNOWN_MARGIN_RULE",
            expected=("absolute","normalized"),actual=margin_rule,
        ))
    robots=set(physical_robots)
    tasks=set(physical_tasks)
    if any((task not in tasks or robot not in robots or
            type(count) is not int or count<=0 or
            type(cost) not in (int,float) or not math.isfinite(cost) or cost<0)
           for (task,robot),(count,cost) in scores.items()):
        raise ProtocolError(Diagnostic(
            owner="coordination",function="resolve_dynamic_probability_margin_winners",
            category="contract",code="P2J_INVALID_CERTIFIED_SCORE",
            expected="positive physically certified votes and nonnegative own Cost",
            actual=list(scores.items())[:8],
        ))
    winners=[]
    ties=0
    while tasks and robots:
        priorities=[]
        for task in tasks:
            candidates=sorted(
                ((count,cost,robot) for (scored_task,robot),(count,cost) in scores.items()
                 if scored_task==task and robot in robots),
                key=lambda x:(-x[0],x[1],x[2]),
            )
            if not candidates:
                continue
            top_count,top_cost,top_robot=candidates[0]
            second_count=candidates[1][0] if len(candidates)>1 else 0
            margin=top_count-second_count
            if margin_rule=="normalized":
                margin=margin/sum(item[0] for item in candidates)
            priorities.append((
                -margin,-top_count,top_cost,task,top_robot,
                sum(item[0]==top_count for item in candidates)>1,
            ))
        if not priorities:
            break
        _margin,_votes,_cost,task,robot,was_tied=min(priorities)
        ties+=int(was_tied)
        winners.append((robot,task))
        robots.remove(robot)
        tasks.remove(task)
    validate_one_to_one_commits(winners)
    return tuple(sorted(winners,key=lambda pair:(pair[1],pair[0]))),ties


def encode_greedy_batch_packet(
    *, kind: bytes, round_id: int, sender_id: int,
    records: tuple[tuple[int, int], ...],
) -> bytes:
    """Serialize one physically charged batch Vote/Score packet, not N hidden unicasts."""
    if kind not in (b"BVOT", b"BSCR") or len(records) > 0xFFFFFFFF:
        raise ProtocolError(Diagnostic(
            owner="coordination", function="encode_greedy_batch_packet",
            category="data", code="BATCH_GREEDY_INVALID_PACKET_KIND",
            expected="BVOT/BSCR and 32-bit record count", actual=(kind, len(records)),
        ))
    try:
        data = _BATCH_HEADER.pack(kind, round_id, sender_id, len(records)) + b"".join(
            _BATCH_RECORD.pack(a, b) for a, b in records
        )
    except (struct.error, TypeError, ValueError) as exc:
        raise ProtocolError(Diagnostic(
            owner="coordination", function="encode_greedy_batch_packet",
            category="data", code="BATCH_GREEDY_INVALID_PACKET_RECORD",
            expected="uint32 sender/epoch and (task, candidate-or-count) pairs",
            actual=str(exc),
        )) from exc
    if len(data) > _BATCH_MAX_PACKET_BYTES:
        raise ProtocolError(Diagnostic(
            owner="coordination", function="encode_greedy_batch_packet",
            category="contract", code="BATCH_GREEDY_PACKET_EXCEEDS_LIMIT",
            expected=f"<= {_BATCH_MAX_PACKET_BYTES} sender application bytes",
            actual=len(data),
        ))
    return data


def decode_greedy_batch_packet(
    packet: bytes, *, kind: bytes, round_id: int, sender_id: int,
) -> tuple[tuple[int, int], ...]:
    """A receiver uses a decoded delivered frame, never the sender's invisible state."""
    valid = isinstance(packet, bytes) and len(packet) >= _BATCH_HEADER.size
    if valid:
        magic, observed_round, observed_sender, count = _BATCH_HEADER.unpack_from(packet)
        valid = (magic == kind and observed_round == round_id
                 and observed_sender == sender_id
                 and len(packet) == _BATCH_HEADER.size + count * _BATCH_RECORD.size)
    if not valid:
        raise ProtocolError(Diagnostic(
            owner="coordination", function="decode_greedy_batch_packet",
            category="contract", code="BATCH_GREEDY_INVALID_RECEIVED_PACKET",
            expected=(kind, round_id, sender_id, "valid count and size"),
            actual={"length": len(packet) if isinstance(packet, bytes) else None},
        ))
    return tuple(
        _BATCH_RECORD.unpack_from(packet, _BATCH_HEADER.size + i * _BATCH_RECORD.size)
        for i in range(count)
    )


def collect_greedy_batch_votes(
    *, proposals: tuple[AssignmentSolution, ...],
    physical_robots: tuple[int, ...],
    ready_times: tuple[float, ...], round_id: int,
    cutoff_ms: float, sampler, loss_sampler, p_vote_loss: float,
    voted_task_ids: tuple[int, ...] | None = None,
) -> tuple[list[CommunicationEvent], list[DeliveryObservation], dict[tuple[int, int], int]]:
    """One broadcast ballot per voter; only timely delivered votes enter recipient tallies."""
    events: list[CommunicationEvent] = []
    deliveries: list[DeliveryObservation] = []
    counts: dict[tuple[int, int], int] = {}
    order = (
        sorted(range(len(physical_robots)), key=lambda i: (ready_times[i], physical_robots[i]))
        if isinstance(sampler, WifiCausalTimingSampler) else range(len(physical_robots))
    )
    for voter_local_id in order:
        proposal = proposals[voter_local_id]
        sender_id = physical_robots[voter_local_id]
        send_time_ms = ready_times[voter_local_id]
        if not proposal.assigned_pairs:
            continue
        records = tuple(
            (task_id, candidate_id) for candidate_id, task_id in proposal.assigned_pairs
            if voted_task_ids is None or task_id in voted_task_ids
        )
        if not records:
            continue
        packet = encode_greedy_batch_packet(
            kind=b"BVOT", round_id=round_id, sender_id=sender_id, records=records,
        )
        event = _broadcast_event(
            phase="vote", sender_id=sender_id, round_id=round_id,
            task_id=None, send_time_ms=send_time_ms,
            payload_bytes=len(packet), sampler=sampler,
        )
        events.append(event)
        attempts = _lossy_broadcast_deliveries(
            event=event, num_robots=len(physical_robots),
            receiver_ids=physical_robots, loss_sampler=loss_sampler,
            p_loss=p_vote_loss, round_id=round_id,
        )
        deliveries.extend(attempts)
        if send_time_ms <= cutoff_ms:
            for task_id, candidate_id in records:
                if candidate_id == sender_id:
                    key = (task_id, candidate_id)
                    counts[key] = counts.get(key, 0) + 1
        for observation in attempts:
            if (not observation.delivered or observation.arrival_time_ms is None
                    or observation.arrival_time_ms > cutoff_ms):
                continue
            for task_id, candidate_id in decode_greedy_batch_packet(
                packet, kind=b"BVOT", round_id=round_id, sender_id=sender_id,
            ):
                if candidate_id == observation.receiver_id:
                    key = (task_id, candidate_id)
                    counts[key] = counts.get(key, 0) + 1
    return events, deliveries, counts


def publish_greedy_batch_scores(
    *, counted_votes: dict[tuple[int, int], int],
    physical_robots: tuple[int, ...], round_id: int,
    release_ms: float, sampler,
) -> tuple[list[CommunicationEvent], dict[tuple[int, int], int]]:
    """Each candidate publishes one reliable score vector from its received votes."""
    events: list[CommunicationEvent] = []
    certified: dict[tuple[int, int], int] = {}
    for candidate_id in physical_robots:
        scores = tuple(sorted(
            (task_id, count) for (task_id, candidate), count in counted_votes.items()
            if candidate == candidate_id and count > 0
        ))
        if not scores:
            continue
        packet = encode_greedy_batch_packet(
            kind=b"BSCR", round_id=round_id, sender_id=candidate_id, records=scores,
        )
        event = _broadcast_event(
            phase="vote_score_announcement", sender_id=candidate_id,
            task_id=None, round_id=round_id, send_time_ms=release_ms,
            payload_bytes=len(packet), sampler=sampler,
            announced_vote_count=sum(count for _task_id, count in scores),
        )
        events.append(event)
        for task_id, count in decode_greedy_batch_packet(
            packet, kind=b"BSCR", round_id=round_id, sender_id=candidate_id,
        ):
            certified[(task_id, candidate_id)] = count
    return events, certified


def resolve_capacity_one_batch_winners(
    *, scores: dict[tuple[int, int], int],
    physical_tasks: tuple[int, ...],
    physical_robots: tuple[int, ...],
) -> tuple[tuple[tuple[int, int], ...], int]:
    """Select ALL available voted pairs globally by score, then enforce capacity one.

    Scores are candidate-reported *received* ballots, not invisible full Cost
    rows. Higher vote count ranks first; equal counts break deterministically
    by task ID then robot ID. Unlike the old task-by-task resolver, a strong
    later-task candidate is not discarded just because an earlier task used
    its robot first. Hungarian and unreceived Cost are never used.
    """
    eligible_robots = set(physical_robots)
    eligible_tasks = set(physical_tasks)
    ranked = sorted(
        ((count, task_id, candidate_id)
         for (task_id, candidate_id), count in scores.items()
         if count > 0 and task_id in eligible_tasks and candidate_id in eligible_robots),
        key=lambda item: (-item[0], item[1], item[2]),
    )
    winners: list[tuple[int, int]] = []
    ties = 0
    for count, task_id, candidate_id in ranked:
        if task_id not in eligible_tasks or candidate_id not in eligible_robots:
            continue
        if any(
            other_task == task_id and other_robot != candidate_id
            and other_count == count and other_robot in eligible_robots
            for other_count, other_task, other_robot in ranked
        ):
            ties += 1
        winners.append((candidate_id, task_id))
        eligible_robots.remove(candidate_id)
        eligible_tasks.remove(task_id)
    validate_one_to_one_commits(winners)
    return tuple(sorted(winners, key=lambda pair: (pair[1], pair[0]))), ties



def resolve_capacity_one_task_ordered_winners(
    *, scores: dict[tuple[int, int], int],
    physical_tasks: tuple[int, ...],
    physical_robots: tuple[int, ...],
) -> tuple[tuple[tuple[int, int], ...], int]:
    """One-shot task-ID-order voting resolution from positive delivered Score only.

    Walk T0,T1,... once, assign the free candidate with highest received Vote
    count for that task. Tie: smallest robot ID. A missing eligible score
    leaves a task unassigned; never invent unseen votes or substitute costs.
    """
    eligible = set(physical_robots)
    winners: list[tuple[int, int]] = []
    ties = 0
    for task_id in sorted(physical_tasks):
        choices = sorted(
            ((count, robot_id) for (task, robot_id), count in scores.items()
             if task == task_id and robot_id in eligible and count > 0),
            key=lambda entry: (-entry[0], entry[1]),
        )
        if not choices:
            continue
        count, robot_id = choices[0]
        if sum(item[0] == count for item in choices) > 1:
            ties += 1
        winners.append((robot_id, task_id))
        eligible.remove(robot_id)
    validate_one_to_one_commits(winners)
    return tuple(winners), ties


def emit_greedy_batch_commits(
    *, winners: tuple[tuple[int, int], ...], round_id: int,
    release_ms: float, sampler,
) -> list[CommunicationEvent]:
    """Charge each final reliable executor Commit after all batch Scores have arrived."""
    return [
        _broadcast_event(
            phase="commit", sender_id=winner_id, task_id=task_id,
            round_id=round_id, send_time_ms=release_ms,
            payload_bytes=COMMIT_PAYLOAD_BYTES, sampler=sampler,
        )
        for winner_id, task_id in winners
    ]


def simulate_greedy_batch_vote_epoch(
    *, cost_matrix: tuple[tuple[float, ...], ...],
    cost_events: list[CommunicationEvent],
    cost_deliveries: list[DeliveryObservation],
    visible: tuple[frozenset[int], ...],
    ready_times: tuple[float, ...],
    proposals: tuple[AssignmentSolution, ...],
    physical_robots: tuple[int, ...], physical_tasks: tuple[int, ...],
    phase_timeout_ms: float, round_id: int,
    sampler, loss_sampler, p_vote_loss: float,
    capture_vote_audit: bool,
    voted_task_ids: tuple[int, ...] | None = None,
    task_ordered: bool = False,
    probabilistic_ballots: tuple[tuple[tuple[int, int, int], ...], ...] | None = None,
    votes_per_voter: int = 100,
    margin_rule: str = "absolute",
) -> LossyCoordinationResult:
    """One Cost snapshot -> one Vote batch -> reliable Score -> capacity-one Commit."""
    eligible_vote_tasks = physical_tasks if voted_task_ids is None else voted_task_ids
    cost_finished_ms = max(ready_times, default=0.0)
    vote_cutoff_ms = cost_finished_ms + phase_timeout_ms
    if probabilistic_ballots is None:
        votes, observed_votes, counts = collect_greedy_batch_votes(
            proposals=proposals, physical_robots=physical_robots, ready_times=ready_times,
            round_id=round_id, cutoff_ms=vote_cutoff_ms, sampler=sampler,
            loss_sampler=loss_sampler, p_vote_loss=p_vote_loss,
            voted_task_ids=voted_task_ids,
        )
    else:
        votes, observed_votes, counts = collect_probabilistic_batch_votes(
            ballots=probabilistic_ballots, physical_robots=physical_robots,
            physical_tasks=physical_tasks, ready_times=ready_times,
            round_id=round_id, cutoff_ms=vote_cutoff_ms, sampler=sampler,
            loss_sampler=loss_sampler, p_vote_loss=p_vote_loss,
            votes_per_voter=votes_per_voter,
        )
    score_release_ms = max(
        vote_cutoff_ms,
        max((event.arrival_time_ms for event in votes), default=0.0),
    )
    if probabilistic_ballots is None:
        scores, certified = publish_greedy_batch_scores(
            counted_votes=counts, physical_robots=physical_robots,
            round_id=round_id, release_ms=score_release_ms, sampler=sampler,
        )
        winner_selector = (
            resolve_capacity_one_task_ordered_winners if task_ordered
            else resolve_capacity_one_batch_winners
        )
        winners, tied = winner_selector(
            scores=certified, physical_tasks=eligible_vote_tasks,
            physical_robots=physical_robots,
        )
    else:
        scores, certified = publish_probabilistic_batch_scores(
            counted_votes=counts, cost_matrix=cost_matrix,
            physical_robots=physical_robots, physical_tasks=physical_tasks,
            round_id=round_id, release_ms=score_release_ms, sampler=sampler,
        )
        winners, tied = resolve_dynamic_probability_margin_winners(
            scores=certified, physical_tasks=eligible_vote_tasks,
            physical_robots=physical_robots, margin_rule=margin_rule,
        )
    scores_done_ms = max(
        score_release_ms, max((event.arrival_time_ms for event in scores), default=score_release_ms),
    )
    commits = emit_greedy_batch_commits(
        winners=winners, round_id=round_id,
        release_ms=scores_done_ms, sampler=sampler,
    )
    events = cost_events + votes + scores + commits
    deliveries = cost_deliveries + observed_votes
    elapsed = max(
        scores_done_ms, max((event.arrival_time_ms for event in commits), default=scores_done_ms),
    )
    return _summarize_lossy_result(
        method=("democracy_probabilistic_margin_one_batch"
                if probabilistic_ballots is not None else
                "democracy_task_ordered_batch_received_plurality" if task_ordered
                else "democracy_batched_greedy_received_plurality"),
        cost_matrix=cost_matrix, assigned_pairs=winners,
        cost_phase_completion_ms=cost_finished_ms,
        decision_completion_ms=scores_done_ms,
        global_agreement_ms=elapsed,
        task_timeout_count=len(eligible_vote_tasks) - len(winners),
        visible_counts=[len(ids) for ids in visible],
        events=events, deliveries=deliveries,
        robot_ids=physical_robots, task_ids=physical_tasks,
        vote_decision_rule="received_plurality",
        announcement_threshold=1,
        qualified_announcement_count=len(scores),
        plurality_tie_break_count=tied,
        plurality_winner_vote_count=max(certified.values(), default=0),
        audit_visible_rows_by_voter=(
            tuple(frozenset(physical_robots[r] for r in rows) for rows in visible)
            if capture_vote_audit else ()
        ),
        audit_proposals_by_voter=proposals if capture_vote_audit else (),
    )


def simulate_democracy_hungarian_lossy(
    *,
    cost_matrix: tuple[tuple[float, ...], ...],
    sampler,
    loss_sampler,
    p_loss: float,
    phase_timeout_ms: float,
    round_id: int = 0,
    capture_vote_audit: bool = False,
    p_vote_loss: float | None = None,
    robot_ids: tuple[int, ...] | None = None,
    task_ids: tuple[int, ...] | None = None,
    voting_strategy: str = "hungarian",
    cost_snapshot: RetirementCostSnapshot | None = None,
    vote_decision_rule: str = "strict_majority",
    vote_repetitions: int = 1,
    send_budget: SenderPayloadBudget | None = None,
    enforce_vote_deadline: bool = False,
    batch_vote_task_ids: tuple[int, ...] | None = None,
    probabilistic_seed: int | None = None,
    votes_per_voter: int = 100,
    temperature: float = 5.0,
    margin_rule: str = "absolute",
) -> LossyCoordinationResult:
    num_robots, num_tasks = validate_cost_matrix(cost_matrix)
    physical_robots, physical_tasks = validate_epoch_identity_mapping(
        num_robots=num_robots,
        num_tasks=num_tasks,
        robot_ids=robot_ids,
        task_ids=task_ids,
    )
    validate_batch_vote_task_ids(
        voting_strategy=voting_strategy, physical_tasks=physical_tasks,
        voted_task_ids=batch_vote_task_ids,
    )
    validate_epoch_voting_strategy(strategy=voting_strategy, num_tasks=num_tasks)
    validate_vote_decision_rule(
        rule=vote_decision_rule,
        voting_strategy=voting_strategy,
        num_tasks=num_tasks,
    )
    validate_vote_repetitions(vote_repetitions)
    if vote_decision_rule == "received_plurality" and not enforce_vote_deadline:
        raise ProtocolError(Diagnostic(
            owner="coordination", function="simulate_democracy_hungarian_lossy",
            category="contract", code="E9H_RECEIVED_PLURALITY_REQUIRES_CUTOFF",
            expected=True, actual=enforce_vote_deadline,
        ))
    validate_budgeted_retirement_scope(
        send_budget=send_budget, voting_strategy=voting_strategy,
        vote_decision_rule=vote_decision_rule, vote_repetitions=vote_repetitions,
    )
    if send_budget is not None and cost_snapshot is None:
        raise ProtocolError(Diagnostic(
            owner="coordination", function="simulate_democracy_hungarian_lossy",
            category="planning", code="BUDGETED_EPOCH_REQUIRES_RETAINED_COSTS",
            expected="one prior recorded Greedy cost snapshot",
            actual=None,
        ))
    quorum = quorum_size(num_robots)
    eligible = frozenset(physical_robots)
    vote_loss_probability = (
        p_loss if p_vote_loss is None
        else validate_packet_loss_probability(p_vote_loss)
    )

    if cost_snapshot is None:
        events, deliveries, visible, ready_times = _simulate_lossy_cost_broadcasts(
            num_robots=num_robots,
            num_tasks=num_tasks,
            sampler=sampler,
            loss_sampler=loss_sampler,
            p_loss=p_loss,
            phase_timeout_ms=phase_timeout_ms,
            round_id=round_id,
            robot_ids=physical_robots,
            enforce_cost_deadline=enforce_vote_deadline,
        )
    else:
        events, deliveries, visible, ready_times = resolve_retirement_cost_view(
            snapshot=cost_snapshot,
            active_robot_ids=physical_robots,
            round_id=round_id,
        )
    cost_completion = max(ready_times, default=0.0)
    voting_cutoff_ms = cost_completion + vote_repetitions * phase_timeout_ms
    if send_budget is not None and cost_snapshot is not None and cost_snapshot.budget_exhausted:
        return summarize_budget_exhausted_epoch(
            cost_matrix=cost_matrix, events=events, deliveries=deliveries,
            visible=visible, cost_completion_ms=cost_completion,
            stop_phase="cost", send_budget=send_budget,
        )
    if voting_strategy == "probabilistic_batch":
        ballots = build_epoch_probabilistic_ballots(
            cost_matrix=cost_matrix, visible=visible,
            physical_robots=physical_robots, physical_tasks=physical_tasks,
            seed=probabilistic_seed, votes_per_voter=votes_per_voter,
            temperature=temperature, round_id=round_id,
        )
        proposals: tuple[AssignmentSolution, ...] = ()
    else:
        ballots = None
        proposals = build_epoch_local_proposals(
            cost_matrix=cost_matrix, visible=visible,
            physical_robots=physical_robots,
            physical_tasks=physical_tasks,
            strategy=voting_strategy,
        )
    if voting_strategy in ("greedy_batch", "greedy_batch_task_order", "probabilistic_batch"):
        return simulate_greedy_batch_vote_epoch(
            cost_matrix=cost_matrix, cost_events=events,
            cost_deliveries=deliveries, visible=visible, ready_times=ready_times,
            proposals=proposals, physical_robots=physical_robots,
            physical_tasks=physical_tasks, phase_timeout_ms=phase_timeout_ms,
            round_id=round_id, sampler=sampler, loss_sampler=loss_sampler,
            p_vote_loss=vote_loss_probability, capture_vote_audit=capture_vote_audit,
            voted_task_ids=batch_vote_task_ids,
            task_ordered=(voting_strategy == "greedy_batch_task_order"),
            probabilistic_ballots=ballots, votes_per_voter=votes_per_voter,
            margin_rule=margin_rule,
        )

    ledgers_by_task: dict[int, dict[int, set[int]]] = {
        task_id: {} for task_id in physical_tasks
    }
    arrivals_by_task_candidate: dict[int, dict[int, list[float]]] = {
        task_id: {} for task_id in physical_tasks
    }

    # For shared-medium scheduling, put original physical votes on air in
    # increasing release time. This only affects opt-in Wi-Fi timing, never
    # the proposals, their keys, quorum, score, or default legacy ordering.
    vote_order = (
        sorted(enumerate(proposals), key=lambda pair: (
            ready_times[pair[0]], physical_robots[pair[0]]
        ))
        if isinstance(sampler, WifiCausalTimingSampler)
        else enumerate(proposals)
    )
    for voter_local_id, proposal in vote_order:
        voter_id = physical_robots[voter_local_id]
        for vote in assignment_to_votes(
            assignment=proposal,
            voter_id=voter_id,
            round_id=round_id,
        ):
            send_time = ready_times[voter_local_id]
            if vote.candidate_id == voter_id:
                if enforce_vote_deadline and send_time > voting_cutoff_ms:
                    continue
                status = record_vote(
                    vote=vote,
                    current_task_id=vote.task_id,
                    current_round_id=round_id,
                    eligible_robots=eligible,
                    ledgers_by_candidate=ledgers_by_task[vote.task_id],
                )
                if status == "ACCEPTED":
                    arrivals_by_task_candidate[vote.task_id].setdefault(
                        vote.candidate_id, []
                    ).append(send_time)
                continue

            physical_events, physical_deliveries, observation = transmit_repeated_remote_vote(
                voter_id=voter_id,
                candidate_id=vote.candidate_id,
                task_id=vote.task_id,
                round_id=round_id,
                send_time_ms=send_time,
                phase_timeout_ms=phase_timeout_ms,
                vote_repetitions=vote_repetitions,
                sampler=sampler,
                loss_sampler=loss_sampler,
                p_vote_loss=vote_loss_probability,
                send_budget=send_budget,
                global_vote_deadline_ms=(
                    voting_cutoff_ms if enforce_vote_deadline else None
                ),
            )
            events.extend(physical_events)
            deliveries.extend(physical_deliveries)
            if send_budget is not None and send_budget.denied_messages:
                return summarize_budget_exhausted_epoch(
                    cost_matrix=cost_matrix, events=events, deliveries=deliveries,
                    visible=visible, cost_completion_ms=cost_completion,
                    stop_phase="vote", send_budget=send_budget,
                )
            if observation is None:
                continue

            status = record_vote(
                vote=vote,
                current_task_id=vote.task_id,
                current_round_id=round_id,
                eligible_robots=eligible,
                ledgers_by_candidate=ledgers_by_task[vote.task_id],
            )
            if status == "ACCEPTED":
                arrivals_by_task_candidate[vote.task_id].setdefault(
                    vote.candidate_id, []
                ).append(float(observation.arrival_time_ms))

    committed_pairs: list[tuple[int, int]] = []
    quorum_times: dict[int, float] = {}
    plurality_resolutions: list[PluralityResolution] = []
    # Sender-side fixed repetition never cancels copies after an early receipt.
    # Decisions wait for the physically scheduled final vote transmission.
    vote_transmit_completion_ms = max(
        (event.arrival_time_ms for event in events if event.phase == "vote"),
        default=max(ready_times, default=0.0),
    )

    for task_id in physical_tasks:
        if vote_decision_rule in ("quarter_plurality", "received_plurality"):
            vote_deadline = voting_cutoff_ms
            resolution, announcements, ready_ms = simulate_quarter_plurality_announcement_phase(
                ledgers_by_candidate=ledgers_by_task[task_id],
                eligible_robots=eligible,
                task_id=task_id,
                round_id=round_id,
                vote_deadline_ms=vote_deadline,
                sampler=sampler,
                send_budget=send_budget,
                decision_rule=vote_decision_rule,
            )
            events.extend(announcements)
            if send_budget is not None and send_budget.denied_messages:
                return summarize_budget_exhausted_epoch(
                    cost_matrix=cost_matrix, events=events, deliveries=deliveries,
                    visible=visible, cost_completion_ms=cost_completion,
                    stop_phase="vote_score_announcement", send_budget=send_budget,
                )
            if resolution is None:
                continue
            committed_pairs.append((resolution.winner_id, task_id))
            quorum_times[task_id] = ready_ms
            plurality_resolutions.append(resolution)
            continue

        winner = find_unique_majority(
            ledgers_by_candidate=ledgers_by_task[task_id],
            quorum=quorum,
            task_id=task_id,
            round_id=round_id,
        )
        if winner is None:
            continue
        winner_id, _counted_votes = winner
        accepted_arrivals = sorted(
            arrivals_by_task_candidate[task_id][winner_id]
        )
        quorum_times[task_id] = (
            accepted_arrivals[quorum - 1] if vote_repetitions == 1
            else max(accepted_arrivals[quorum - 1], vote_transmit_completion_ms)
        )
        committed_pairs.append((winner_id, task_id))

    validate_one_to_one_commits(committed_pairs)

    commit_arrivals: list[float] = []
    for winner_id, task_id in committed_pairs:
        try:
            event = _broadcast_event(
                phase="commit",
                sender_id=winner_id,
                send_time_ms=quorum_times[task_id],
                payload_bytes=COMMIT_PAYLOAD_BYTES,
                sampler=sampler,
                task_id=task_id,
                round_id=round_id,
                send_budget=send_budget,
            )
        except SenderBudgetExhausted:
            # In this bounded single-task Greedy mode NO Commit has been emitted.
            return summarize_budget_exhausted_epoch(
                cost_matrix=cost_matrix, events=events, deliveries=deliveries,
                visible=visible, cost_completion_ms=cost_completion,
                stop_phase="commit", send_budget=send_budget,
            )
        events.append(event)
        commit_arrivals.append(event.arrival_time_ms)

    timeout_count = num_tasks - len(committed_pairs)
    vote_deadline = max(ready_times, default=0.0) + vote_repetitions * phase_timeout_ms
    if timeout_count:
        decision_completion = max(
            max(quorum_times.values(), default=0.0),
            vote_deadline,
        )
    else:
        decision_completion = max(quorum_times.values(), default=cost_completion)

    global_agreement = max(
        decision_completion,
        max(commit_arrivals, default=0.0),
    )

    return _summarize_lossy_result(
        method=(
            "democracy_greedy_received_plurality"
            if vote_decision_rule == "received_plurality"
            else ("democracy_greedy_quarter_plurality"
                  if vote_decision_rule == "quarter_plurality"
                  else ("democracy_greedy" if voting_strategy == "greedy_task"
                        else "democracy_hungarian"))
        ),
        cost_matrix=cost_matrix,
        assigned_pairs=committed_pairs,
        cost_phase_completion_ms=cost_completion,
        decision_completion_ms=decision_completion,
        global_agreement_ms=global_agreement,
        task_timeout_count=timeout_count,
        visible_counts=[len(rows) for rows in visible],
        events=events,
        deliveries=deliveries,
        audit_visible_rows_by_voter=(
            tuple(frozenset(physical_robots[r] for r in rows) for rows in visible)
            if capture_vote_audit else ()
        ),
        audit_proposals_by_voter=proposals if capture_vote_audit else (),
        audit_counted_vote_ledgers=(
            snapshot_counted_vote_ledgers(ledgers_by_task)
            if capture_vote_audit else ()
        ),
        robot_ids=(physical_robots if robot_ids is not None or task_ids is not None else None),
        task_ids=(physical_tasks if robot_ids is not None or task_ids is not None else None),
        vote_decision_rule=vote_decision_rule,
        announcement_threshold=(
            quarter_vote_announcement_threshold(len(eligible))
            if vote_decision_rule == "quarter_plurality"
            else (1 if vote_decision_rule == "received_plurality" else 0)
        ),
        qualified_announcement_count=sum(
            p.announced_candidate_count for p in plurality_resolutions
        ),
        plurality_tie_break_count=sum(
            int(p.tied_highest) for p in plurality_resolutions
        ),
        plurality_winner_vote_count=(
            plurality_resolutions[0].counted_votes if plurality_resolutions else 0
        ),
    )



@dataclass(frozen=True)
class RetirementRoundTrace:
    round_id: int
    active_robot_ids: tuple[int, ...]
    pending_task_ids: tuple[int, ...]
    quorum: int
    newly_committed_pairs: tuple[tuple[int, int], ...]
    elapsed_start_ms: float
    elapsed_end_ms: float
    coordination: LossyCoordinationResult
    voted_task_id: int | None = None
    announcement_threshold: int = 0


@dataclass(frozen=True)
class MultiRoundRetirementResult:
    method: str
    assigned_pairs: tuple[tuple[int, int], ...]
    total_cost: float
    total_tasks: int
    remaining_task_ids: tuple[int, ...]
    active_robot_ids: tuple[int, ...]
    rounds: tuple[RetirementRoundTrace, ...]
    global_agreement_ms: float
    logical_message_count: int
    payload_bytes: int
    lossy_delivered: int
    lossy_dropped: int
    vote_repetitions: int = 1
    budget_exhausted: bool = False
    budget_stop_phase: str | None = None
    budget_stop_diagnostic: Diagnostic | None = None

    @property
    def committed_tasks(self) -> int:
        return len(self.assigned_pairs)

    @property
    def full_assignment_success(self) -> bool:
        return len(self.remaining_task_ids) == 0

    @property
    def task_commit_rate(self) -> float:
        return self.committed_tasks / self.total_tasks


def build_retirement_round_cost_matrix(
    *,
    cost_matrix: tuple[tuple[float, ...], ...],
    active_robot_ids: tuple[int, ...],
    pending_task_ids: tuple[int, ...],
) -> tuple[tuple[float, ...], ...]:
    """Only currently eligible robots/tasks may enter the local optimizer."""
    return tuple(
        tuple(cost_matrix[robot_id][task_id] for task_id in pending_task_ids)
        for robot_id in active_robot_ids
    )


def require_retirement_commit_announcements(
    *,
    round_result: LossyCoordinationResult,
    round_id: int,
) -> None:
    """A retired executor must have already broadcast its reliable commit."""
    announced_pairs = {
        (event.sender_id, event.task_id)
        for event in round_result.events
        if event.phase == "commit" and event.round_id == round_id
    }
    expected_pairs = set(round_result.assigned_pairs)
    if announced_pairs != expected_pairs:
        raise ProtocolError(
            Diagnostic(
                owner="coordination",
                function="require_retirement_commit_announcements",
                category="contract",
                code="RETIREMENT_COMMIT_ANNOUNCEMENT_MISMATCH",
                expected=tuple(sorted(expected_pairs)),
                actual=tuple(sorted(announced_pairs)),
                details=f"round_id={round_id}",
            )
        )



def require_retirement_sender_accounting(
    *,
    send_budget: SenderPayloadBudget | None,
    rounds: list[RetirementRoundTrace],
) -> None:
    """Hard-cap ledger and all actual physical SEND events must match exactly."""
    if send_budget is None:
        return
    transmitted = tuple(
        event for item in rounds for event in item.coordination.events
    )
    expected = (len(transmitted), sum(event.payload_bytes for event in transmitted))
    actual = (send_budget.sent_messages, send_budget.sent_bytes)
    if expected != actual:
        raise ProtocolError(Diagnostic(
            owner="coordination",
            function="require_retirement_sender_accounting",
            category="contract",
            code="BUDGET_LEDGER_EVENT_MISMATCH",
            expected={"messages": expected[0], "bytes": expected[1]},
            actual={"messages": actual[0], "bytes": actual[1]},
        ))


def validate_e9h_deadline_schedule(
    *, schedule_ms: tuple[float, ...] | None,
    initial_robots: int, initial_phase_timeout_ms: float,
    enforce_vote_deadline: bool,
) -> None:
    """Original membership owner's optional immutable per-active-count time contract."""
    if schedule_ms is None:
        return
    ok = (
        enforce_vote_deadline and type(schedule_ms) is tuple
        and len(schedule_ms) == initial_robots
        and all(type(x) in (float, int) and math.isfinite(x) and x > 0 for x in schedule_ms)
        and all(a <= b for a,b in zip(schedule_ms,schedule_ms[1:]))
        and schedule_ms[-1] <= initial_phase_timeout_ms + 1e-7
    )
    if not ok:
        raise ProtocolError(Diagnostic(
            owner="coordination",function="validate_e9h_deadline_schedule",
            category="contract",code="E9H_INVALID_DEADLINE_SCHEDULE",
            expected=f"{initial_robots} positive monotone Vote deadlines <= initial Cost timeout; cutoff enabled",
            actual={"schedule":schedule_ms,"cost_timeout":initial_phase_timeout_ms,
                    "cutoff":enforce_vote_deadline},
        ))


def simulate_democracy_hungarian_retirement(
    *,
    cost_matrix: tuple[tuple[float, ...], ...],
    sampler,
    loss_sampler,
    p_loss: float,
    p_vote_loss: float,
    phase_timeout_ms: float,
    max_rounds: int,
    voting_strategy: str = "hungarian",
    vote_decision_rule: str = "strict_majority",
    vote_repetitions: int = 1,
    send_budget: SenderPayloadBudget | None = None,
    preknown_cost_snapshot: RetirementCostSnapshot | None = None,
    cost_repetitions: int = 1,
    per_active_round_deadline_ms: tuple[float, ...] | None = None,
    enforce_vote_deadline: bool = False,
    batch_vote_scope: str = "all",
    probabilistic_seed: int | None = None,
    votes_per_voter: int = 100,
    temperature: float = 5.0,
    margin_rule: str = "absolute",
) -> MultiRoundRetirementResult:
    """Multi-round membership owner; reuses the same E2 single-round vote engine.

    Successful reliable commits retire both assigned robots and completed tasks
    only between complete voting epochs; pending tasks retry with fresh packet keys.
    This model records assignment/execution eligibility, not physical task motion.
    """
    num_robots, num_tasks = validate_cost_matrix(cost_matrix)
    if max_rounds < 1:
        raise ProtocolError(
            Diagnostic(
                owner="coordination",
                function="simulate_democracy_hungarian_retirement",
                category="data",
                code="INVALID_RETIREMENT_ROUND_LIMIT",
                expected="max_rounds >= 1",
                actual=max_rounds,
            )
        )

    validate_packet_loss_probability(p_loss)
    validate_packet_loss_probability(p_vote_loss)
    validate_vote_repetitions(vote_repetitions)
    validate_cost_repetitions(cost_repetitions)
    validate_e9h_deadline_schedule(
        schedule_ms=per_active_round_deadline_ms, initial_robots=num_robots,
        initial_phase_timeout_ms=phase_timeout_ms, enforce_vote_deadline=enforce_vote_deadline,
    )
    if isinstance(sampler, WifiCausalTimingSampler) and (
        cost_repetitions != 1 or vote_repetitions != 1 or
        voting_strategy not in ("greedy_task", "greedy_batch", "greedy_batch_task_order", "probabilistic_batch")
    ):
        raise ProtocolError(Diagnostic(
            owner="coordination", function="simulate_democracy_hungarian_retirement",
            category="contract", code="E9G_WIRE_TIMING_ORIGINAL_GREEDY_ONLY",
            expected="greedy_task with one Cost copy and one Vote copy",
            actual={"voting_strategy": voting_strategy,
                    "cost_repetitions": cost_repetitions,
                    "vote_repetitions": vote_repetitions},
        ))
    validate_repeated_cost_scope(
        cost_repetitions=cost_repetitions,
        voting_strategy=voting_strategy,
        preknown_cost_snapshot=preknown_cost_snapshot,
    )
    validate_budgeted_retirement_scope(
        send_budget=send_budget, voting_strategy=voting_strategy,
        vote_decision_rule=vote_decision_rule, vote_repetitions=vote_repetitions,
    )
    validate_epoch_voting_strategy(
        strategy=voting_strategy, num_tasks=(1 if voting_strategy == "greedy_task" else num_tasks)
    )
    validate_vote_decision_rule(
        rule=vote_decision_rule,
        voting_strategy=voting_strategy,
        num_tasks=(1 if voting_strategy == "greedy_task" else num_tasks),
    )
    validate_batch_vote_scope(
        voting_strategy=voting_strategy, batch_vote_scope=batch_vote_scope,
    )
    validate_probabilistic_batch_scope(
        voting_strategy=voting_strategy, max_rounds=max_rounds,
        cost_repetitions=cost_repetitions, vote_repetitions=vote_repetitions,
        batch_vote_scope=batch_vote_scope, probabilistic_seed=probabilistic_seed,
        votes_per_voter=votes_per_voter, temperature=temperature,
        margin_rule=margin_rule, enforce_vote_deadline=enforce_vote_deadline,
        send_budget=send_budget, preknown_cost_snapshot=preknown_cost_snapshot,
    )
    if preknown_cost_snapshot is not None:
        validate_preknown_retirement_cost_snapshot(
            snapshot=preknown_cost_snapshot, num_robots=num_robots,
            voting_strategy=voting_strategy,
        )
        snapshot = preknown_cost_snapshot
    else:
        snapshot = (
            capture_retirement_cost_snapshot(
                cost_matrix=cost_matrix,
                sampler=sampler,
                loss_sampler=loss_sampler,
                p_loss=p_loss,
                phase_timeout_ms=phase_timeout_ms,
                send_budget=send_budget,
                cost_repetitions=cost_repetitions,
                enforce_cost_deadline=enforce_vote_deadline,
            )
            if voting_strategy in ("greedy_task", "greedy_batch", "greedy_batch_task_order", "probabilistic_batch") else None
        )
    membership = initialize_retirement_membership(
        num_robots=num_robots,
        num_tasks=num_tasks,
    )
    elapsed_ms = 0.0
    rounds: list[RetirementRoundTrace] = []

    for _ in range(max_rounds):
        if not membership.pending_task_ids:
            break
        active_robots = membership.active_robot_ids
        pending_tasks = (
            membership.pending_task_ids[:1]
            if voting_strategy == "greedy_task"
            else membership.pending_task_ids
        )
        round_id = membership.epoch_index

        round_costs = build_retirement_round_cost_matrix(
            cost_matrix=cost_matrix,
            active_robot_ids=active_robots,
            pending_task_ids=pending_tasks,
        )
        if isinstance(sampler, WifiCausalTimingSampler):
            sampler.set_epoch_start_ms(elapsed_ms)
        current_phase_timeout_ms = (
            per_active_round_deadline_ms[len(active_robots)-1]
            if per_active_round_deadline_ms is not None else phase_timeout_ms
        )
        round_result = simulate_democracy_hungarian_lossy(
            cost_matrix=round_costs,
            sampler=sampler,
            loss_sampler=loss_sampler,
            p_loss=p_loss,
            p_vote_loss=p_vote_loss,
            phase_timeout_ms=current_phase_timeout_ms,
            round_id=round_id,
            robot_ids=active_robots,
            task_ids=pending_tasks,
            voting_strategy=voting_strategy,
            cost_snapshot=snapshot,
            vote_decision_rule=vote_decision_rule,
            vote_repetitions=vote_repetitions,
            send_budget=send_budget,
            enforce_vote_deadline=enforce_vote_deadline,
            batch_vote_task_ids=(pending_tasks[:1] if batch_vote_scope == "one_task" else None),
            probabilistic_seed=probabilistic_seed, votes_per_voter=votes_per_voter,
            temperature=temperature, margin_rule=margin_rule,
        )
        require_retirement_commit_announcements(
            round_result=round_result,
            round_id=round_id,
        )
        next_elapsed = elapsed_ms + round_result.global_agreement_ms
        rounds.append(
            RetirementRoundTrace(
                round_id=round_id,
                active_robot_ids=active_robots,
                pending_task_ids=membership.pending_task_ids,
                voted_task_id=(pending_tasks[0] if voting_strategy == "greedy_task"
                               or batch_vote_scope == "one_task" else None),
                quorum=(quorum_size(len(active_robots)) if vote_decision_rule == "strict_majority" else 0),
                announcement_threshold=round_result.announcement_threshold,
                newly_committed_pairs=round_result.assigned_pairs,
                elapsed_start_ms=elapsed_ms,
                elapsed_end_ms=next_elapsed,
                coordination=round_result,
            )
        )
        if round_result.budget_exhausted:
            # Neither rotate a pending task nor retire any uncommitted executor.
            elapsed_ms = next_elapsed
            break
        membership = apply_announced_retirement_commits(
            membership=membership,
            announced_pairs=round_result.assigned_pairs,
            attempted_task_id=(pending_tasks[0] if voting_strategy == "greedy_task"
                               or batch_vote_scope == "one_task" else None),
        )
        elapsed_ms = next_elapsed

    require_retirement_sender_accounting(send_budget=send_budget, rounds=rounds)
    stopped_round = next(
        (item.coordination for item in rounds if item.coordination.budget_exhausted),
        None,
    )
    return MultiRoundRetirementResult(
        method=(
            "democracy_probabilistic_margin_one_batch_retirement"
            if voting_strategy == "probabilistic_batch" else
            "democracy_task_ordered_batch_received_plurality_retirement"
            if voting_strategy == "greedy_batch_task_order" else
            ("democracy_serial_global_greedy_received_plurality_retirement"
             if batch_vote_scope == "one_task"
             else "democracy_batched_greedy_received_plurality_retirement")
            if voting_strategy == "greedy_batch"
            else "democracy_greedy_received_plurality_retirement"
            if vote_decision_rule == "received_plurality"
            else (
                "democracy_greedy_quarter_plurality_retirement"
                if vote_decision_rule == "quarter_plurality"
                else (
                "democracy_greedy_retirement"
                if voting_strategy == "greedy_task"
                else "democracy_hungarian_retirement"
                )
            )
        ),
        assigned_pairs=membership.committed_pairs,
        total_cost=float(
            sum(cost_matrix[robot_id][task_id] for robot_id, task_id in membership.committed_pairs)
        ),
        total_tasks=num_tasks,
        remaining_task_ids=membership.pending_task_ids,
        active_robot_ids=membership.active_robot_ids,
        rounds=tuple(rounds),
        global_agreement_ms=elapsed_ms,
        logical_message_count=sum(
            item.coordination.logical_message_count for item in rounds
        ),
        payload_bytes=sum(item.coordination.payload_bytes for item in rounds),
        lossy_delivered=sum(item.coordination.lossy_delivered for item in rounds),
        lossy_dropped=sum(item.coordination.lossy_dropped for item in rounds),
        vote_repetitions=vote_repetitions,
        budget_exhausted=stopped_round is not None,
        budget_stop_phase=(stopped_round.budget_stop_phase if stopped_round else None),
        budget_stop_diagnostic=(stopped_round.budget_stop_diagnostic if stopped_round else None),
    )

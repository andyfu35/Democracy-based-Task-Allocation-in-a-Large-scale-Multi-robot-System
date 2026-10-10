from __future__ import annotations

from dataclasses import dataclass

from .diagnostics import Diagnostic, ProtocolError

from .network import validate_packet_loss_probability

from .optimizer import (
    AssignmentSolution,
    solve_visible_hungarian_assignment,
    validate_cost_matrix,
)
from .protocol import (
    assignment_to_votes,
    find_unique_majority,
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
) -> CommunicationEvent:
    key = (
        f"unicast|{phase}|{sender_id}|{receiver_id}|"
        f"{task_id if task_id is not None else '-'}"
    )
    if round_id:
        key += f"|round={round_id}"
    latency_ms = float(sampler.sample_ms(key))
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
) -> CommunicationEvent:
    key = (
        f"broadcast|{phase}|{sender_id}|"
        f"{task_id if task_id is not None else '-'}"
    )
    if round_id:
        key += f"|round={round_id}"
    latency_ms = float(sampler.sample_ms(key))
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
    delivered = bool(loss_sampler.is_delivered(key, p_loss))
    return DeliveryObservation(
        phase=event.phase,
        sender_id=event.sender_id,
        receiver_id=event.receiver_id,
        delivered=delivered,
        arrival_time_ms=event.arrival_time_ms if delivered else None,
        task_id=event.task_id,
        round_id=round_id,
    )


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
) -> tuple[
    list[CommunicationEvent],
    list[DeliveryObservation],
    tuple[frozenset[int], ...],
    tuple[float, ...],
]:
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

    for sender_local_id, sender_id in enumerate(physical_ids):
        event = _broadcast_event(
            phase="cost",
            sender_id=sender_id,
            send_time_ms=0.0,
            payload_bytes=cost_row_payload_bytes(num_tasks),
            sampler=sampler,
            round_id=round_id,
        )
        events.append(event)
        observations = _lossy_broadcast_deliveries(
            event=event,
            num_robots=num_robots,
            loss_sampler=loss_sampler,
            p_loss=p_loss,
            round_id=round_id,
            receiver_ids=physical_ids,
        )
        deliveries.extend(observations)
        for observation in observations:
            if observation.delivered:
                receiver_local_id = local_index[observation.receiver_id]
                visible_by_receiver[receiver_local_id].add(sender_local_id)
                arrivals_by_receiver[receiver_local_id].append(
                    float(observation.arrival_time_ms)
                )

    visible = tuple(frozenset(rows) for rows in visible_by_receiver)
    ready_times = tuple(
        max(arrivals_by_receiver[receiver_id], default=0.0)
        if len(visible[receiver_id]) == num_robots
        else phase_timeout_ms
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
) -> LossyCoordinationResult:
    num_robots, num_tasks = validate_cost_matrix(cost_matrix)
    physical_robots, physical_tasks = validate_epoch_identity_mapping(
        num_robots=num_robots,
        num_tasks=num_tasks,
        robot_ids=robot_ids,
        task_ids=task_ids,
    )
    quorum = quorum_size(num_robots)
    eligible = frozenset(physical_robots)
    vote_loss_probability = (
        p_loss if p_vote_loss is None
        else validate_packet_loss_probability(p_vote_loss)
    )

    events, deliveries, visible, ready_times = _simulate_lossy_cost_broadcasts(
        num_robots=num_robots,
        num_tasks=num_tasks,
        sampler=sampler,
        loss_sampler=loss_sampler,
        p_loss=p_loss,
        phase_timeout_ms=phase_timeout_ms,
        round_id=round_id,
        robot_ids=physical_robots,
    )
    cost_completion = max(ready_times, default=0.0)

    proposals = tuple(
        map_epoch_local_proposal(
            assignment=solve_visible_hungarian_assignment(cost_matrix, visible[voter_local_id]),
            robot_ids=physical_robots,
            task_ids=physical_tasks,
        )
        for voter_local_id in range(num_robots)
    )

    ledgers_by_task: dict[int, dict[int, set[int]]] = {
        task_id: {} for task_id in physical_tasks
    }
    arrivals_by_task_candidate: dict[int, dict[int, list[float]]] = {
        task_id: {} for task_id in physical_tasks
    }

    for voter_local_id, proposal in enumerate(proposals):
        voter_id = physical_robots[voter_local_id]
        for vote in assignment_to_votes(
            assignment=proposal,
            voter_id=voter_id,
            round_id=round_id,
        ):
            send_time = ready_times[voter_local_id]
            if vote.candidate_id == voter_id:
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

            event = _unicast_event(
                phase="vote",
                sender_id=voter_id,
                receiver_id=vote.candidate_id,
                send_time_ms=send_time,
                payload_bytes=VOTE_PAYLOAD_BYTES,
                sampler=sampler,
                task_id=vote.task_id,
                round_id=round_id,
            )
            events.append(event)
            observation = _lossy_unicast_delivery(
                event=event,
                loss_sampler=loss_sampler,
                p_loss=vote_loss_probability,
                round_id=round_id,
            )
            deliveries.append(observation)
            if not observation.delivered:
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

    for task_id in physical_tasks:
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
        quorum_times[task_id] = accepted_arrivals[quorum - 1]
        committed_pairs.append((winner_id, task_id))

    validate_one_to_one_commits(committed_pairs)

    commit_arrivals: list[float] = []
    for winner_id, task_id in committed_pairs:
        event = _broadcast_event(
            phase="commit",
            sender_id=winner_id,
            send_time_ms=quorum_times[task_id],
            payload_bytes=COMMIT_PAYLOAD_BYTES,
            sampler=sampler,
            task_id=task_id,
            round_id=round_id,
        )
        events.append(event)
        commit_arrivals.append(event.arrival_time_ms)

    timeout_count = num_tasks - len(committed_pairs)
    vote_deadline = max(ready_times, default=0.0) + phase_timeout_ms
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
        method="democracy_hungarian",
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
    lossy_delivered: int
    lossy_dropped: int

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


def simulate_democracy_hungarian_retirement(
    *,
    cost_matrix: tuple[tuple[float, ...], ...],
    sampler,
    loss_sampler,
    p_loss: float,
    p_vote_loss: float,
    phase_timeout_ms: float,
    max_rounds: int,
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
        pending_tasks = membership.pending_task_ids
        round_id = membership.epoch_index

        round_costs = build_retirement_round_cost_matrix(
            cost_matrix=cost_matrix,
            active_robot_ids=active_robots,
            pending_task_ids=pending_tasks,
        )
        round_result = simulate_democracy_hungarian_lossy(
            cost_matrix=round_costs,
            sampler=sampler,
            loss_sampler=loss_sampler,
            p_loss=p_loss,
            p_vote_loss=p_vote_loss,
            phase_timeout_ms=phase_timeout_ms,
            round_id=round_id,
            robot_ids=active_robots,
            task_ids=pending_tasks,
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
                pending_task_ids=pending_tasks,
                quorum=quorum_size(len(active_robots)),
                newly_committed_pairs=round_result.assigned_pairs,
                elapsed_start_ms=elapsed_ms,
                elapsed_end_ms=next_elapsed,
                coordination=round_result,
            )
        )
        membership = apply_announced_retirement_commits(
            membership=membership,
            announced_pairs=round_result.assigned_pairs,
        )
        elapsed_ms = next_elapsed

    return MultiRoundRetirementResult(
        method="democracy_hungarian_retirement",
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
        lossy_delivered=sum(item.coordination.lossy_delivered for item in rounds),
        lossy_dropped=sum(item.coordination.lossy_dropped for item in rounds),
    )

from __future__ import annotations

from dataclasses import dataclass

from .optimizer import AssignmentSolution
from .protocol import quorum_size


APP_HEADER_BYTES = 16
FLOAT64_BYTES = 8
ID_BYTES = 4

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


def _network_event(
    *,
    phase: str,
    sender_id: int,
    receiver_id: int,
    send_time_ms: float,
    payload_bytes: int,
    sampler,
    task_id: int | None = None,
) -> CommunicationEvent:
    key = f"{phase}|{sender_id}|{receiver_id}|{task_id if task_id is not None else '-'}"
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
        event = _network_event(
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

    assignment_bytes = assignment_payload_bytes(num_tasks)
    outbound: list[CommunicationEvent] = []
    for receiver_id in range(num_robots):
        if receiver_id == leader_id:
            continue
        event = _network_event(
            phase="leader_assignment",
            sender_id=leader_id,
            receiver_id=receiver_id,
            send_time_ms=cost_end,
            payload_bytes=assignment_bytes,
            sampler=sampler,
        )
        events.append(event)
        outbound.append(event)

    agreement_end = max(
        (event.arrival_time_ms for event in outbound),
        default=cost_end,
    )

    return _summarize_events(
        method="leader_hungarian",
        cost_exchange_completion_ms=cost_end,
        actionable_decision_ms=agreement_end,
        global_agreement_ms=agreement_end,
        events=events,
    )


def _all_to_all_cost_exchange(
    *,
    num_robots: int,
    num_tasks: int,
    sampler,
) -> tuple[list[CommunicationEvent], tuple[float, ...]]:
    events: list[CommunicationEvent] = []
    inbound_by_receiver: dict[int, list[float]] = {
        robot_id: [] for robot_id in range(num_robots)
    }
    row_bytes = cost_row_payload_bytes(num_tasks)

    for sender_id in range(num_robots):
        for receiver_id in range(num_robots):
            if sender_id == receiver_id:
                continue
            event = _network_event(
                phase="cost",
                sender_id=sender_id,
                receiver_id=receiver_id,
                send_time_ms=0.0,
                payload_bytes=row_bytes,
                sampler=sampler,
            )
            events.append(event)
            inbound_by_receiver[receiver_id].append(event.arrival_time_ms)

    ready_times = tuple(
        max(inbound_by_receiver[robot_id], default=0.0)
        for robot_id in range(num_robots)
    )
    return events, ready_times


def simulate_full_view_hungarian(
    *,
    num_robots: int,
    num_tasks: int,
    sampler,
) -> CoordinationTimingResult:
    events, ready_times = _all_to_all_cost_exchange(
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
    cost_events, ready_times = _all_to_all_cost_exchange(
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

            event = _network_event(
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
        send_time = quorum_time_by_task[task_id]
        for receiver_id in range(num_robots):
            if receiver_id == winner_id:
                continue
            event = _network_event(
                phase="commit",
                sender_id=winner_id,
                receiver_id=receiver_id,
                send_time_ms=send_time,
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

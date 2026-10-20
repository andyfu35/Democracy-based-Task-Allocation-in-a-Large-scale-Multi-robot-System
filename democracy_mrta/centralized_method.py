"""P2D Centralized Method: one-shot receiver-paid Cost acquisition, no retries.

Robot 0 gathers only physically delivered remote Cost rows, runs the existing
minimum-pair greedy owner and sends one assignment announcement and one
executor Commit per selected pair. This is a *one-shot* central comparator,
not a resilient centralized consensus or ideal full-information oracle.
"""
from __future__ import annotations

from dataclasses import dataclass
import math

from .coordination import (
    CommunicationEvent, DeliveryObservation, COMMIT_PAYLOAD_BYTES,
    _broadcast_event, _unicast_event, _lossy_unicast_delivery,
    cost_row_payload_bytes, assignment_payload_bytes,
)
from .diagnostics import Diagnostic, ProtocolError
from .network import (
    BernoulliLossSampler, EmpiricalLatencyProfile, WifiCausalTimingSampler,
    WifiTimingConfig, estimate_e9h_guarded_initial_cost_ms,
    validate_packet_loss_probability,
)
from .optimizer import (
    solve_visible_batched_greedy_assignment,
    solve_visible_task_ordered_greedy_assignment,
    select_cheapest_visible_greedy_row,
    validate_cost_matrix,
)
from .protocol import validate_one_to_one_commits
from .task_information import broadcast_task_information

OWNER = "democracy_mrta.centralized_method"


@dataclass(frozen=True)
class CentralizedCostReceipt:
    visible_rows: tuple[tuple[int, tuple[float, ...]], ...]
    cost_events: tuple[CommunicationEvent, ...]
    cost_deliveries: tuple[DeliveryObservation, ...]
    cost_start_ms: float
    cost_cutoff_ms: float
    cost_phase_end_ms: float
    cost_rounds_executed: int = 1

    @property
    def received_robot_ids(self) -> tuple[int, ...]:
        return tuple(robot_id for robot_id, _row in self.visible_rows)


@dataclass(frozen=True)
class CentralizedResult:
    assignment: tuple[tuple[int, int], ...]
    received_robot_ids: tuple[int, ...]
    native_success: bool
    task_coverage: float
    native_stop_ms: float
    stop_reason: str
    sender_sends: int
    sender_bytes: int
    receiver_attempts: int
    receiver_drops: int
    cost_sender_sends: int
    cost_sender_bytes: int
    cost_receiver_drops: int
    decision_sender_sends: int
    commit_sender_sends: int
    cost_airtime_ms: float
    event_ledger: dict
    phase_times: dict[str, float]
    cost_rounds_executed: int = 1


def validate_centralized_retry_limit(*, max_cost_rounds: int) -> int:
    """Bound opt-in coordinator Cost retry epochs, keeping the default one-shot."""
    if type(max_cost_rounds) is not int or not 1 <= max_cost_rounds <= 300:
        raise ProtocolError(Diagnostic(
            owner=OWNER, function="validate_centralized_retry_limit",
            category="data", code="P2G_INVALID_CENTRAL_COST_ROUNDS",
            expected="integer in [1,300] (one-shot default=1)",
            actual=max_cost_rounds,
        ))
    return max_cost_rounds


def validate_centralized_cost_window(*, cost_start_ms: float, cutoff_ms: float) -> None:
    """First invalid Cost timing boundary before emitting any physical SEND."""
    if (not math.isfinite(cost_start_ms) or not math.isfinite(cutoff_ms)
            or cutoff_ms <= cost_start_ms):
        raise ProtocolError(Diagnostic(
            owner=OWNER, function="validate_centralized_cost_window",
            category="time", code="P2G_INVALID_COST_WINDOW",
            expected="finite cutoff_ms > cost_start_ms",
            actual=(cost_start_ms, cutoff_ms),
        ))


def validate_centralized_configuration(
    *, cost_matrix: tuple[tuple[float, ...], ...],
    task_positions: tuple[tuple[float, float], ...],
    coordinator_id: int, p_loss: float,
) -> int:
    """Data boundary; never turn a missing Cost row into simulation truth."""
    robots, tasks = validate_cost_matrix(cost_matrix)
    validate_packet_loss_probability(p_loss)
    if (robots != tasks or coordinator_id != 0
            or len(task_positions) != tasks or robots < 2
            or any(len(pos) != 2 or any(not math.isfinite(float(v)) for v in pos)
                   for pos in task_positions)):
        raise ProtocolError(Diagnostic(
            owner=OWNER, function="validate_centralized_configuration",
            category="data", code="P2D_INVALID_CENTRALIZED_GRID",
            expected="N=T>=2, coordinator=0 and N finite task positions",
            actual={"robots":robots,"tasks":tasks,"coordinator":coordinator_id,
                    "task_positions":len(task_positions)},
        ))
    return robots


def collect_one_shot_cost_rows(
    *, cost_matrix: tuple[tuple[float, ...], ...],
    coordinator_id: int, cost_start_ms: float, cutoff_ms: float,
    sampler: WifiCausalTimingSampler, loss_sampler: BernoulliLossSampler,
    p_loss: float, max_cost_rounds: int = 1,
) -> CentralizedCostReceipt:
    """Receive only physical Costs; opt-in repeats ONLY missing senders.

    Each attempt is sender-paid before checking delivery. One-shot
    max_cost_rounds=1 retains original event keys, SENDs and cutoff exactly.
    """
    limit = validate_centralized_retry_limit(max_cost_rounds=max_cost_rounds)
    robots = len(cost_matrix)
    validate_centralized_cost_window(
        cost_start_ms=cost_start_ms, cutoff_ms=cutoff_ms,
    )
    known = {coordinator_id: tuple(cost_matrix[coordinator_id])}
    events: list[CommunicationEvent] = []
    deliveries: list[DeliveryObservation] = []
    round_window_ms = cutoff_ms - cost_start_ms
    start_ms = cost_start_ms
    last_cutoff_ms = cutoff_ms
    rounds = 0
    for round_id in range(limit):
        if len(known) == robots:
            break
        rounds += 1
        deadline_ms = start_ms + round_window_ms
        new_events: list[CommunicationEvent] = []
        for sender in range(robots):
            if sender in known:
                continue
            event = _unicast_event(
                phase="centralized_cost", sender_id=sender,
                receiver_id=coordinator_id, round_id=round_id,
                send_time_ms=start_ms,
                payload_bytes=cost_row_payload_bytes(len(cost_matrix[sender])),
                sampler=sampler,
            )
            events.append(event)
            new_events.append(event)
            observation = _lossy_unicast_delivery(
                event=event, loss_sampler=loss_sampler,
                p_loss=p_loss, round_id=round_id,
            )
            deliveries.append(observation)
            if (observation.delivered and observation.arrival_time_ms is not None
                    and observation.arrival_time_ms <= deadline_ms):
                known[sender] = tuple(cost_matrix[sender])
        last_cutoff_ms = deadline_ms
        start_ms = max(deadline_ms, max(
            (event.arrival_time_ms for event in new_events), default=start_ms
        ))
    if rounds < 1 or len(events) < robots - 1:
        raise ProtocolError(Diagnostic(
            owner=OWNER, function="collect_one_shot_cost_rows",
            category="contract", code="P2G_INITIAL_COST_SEND_COUNT_MISMATCH",
            expected=f">={robots-1} physical Cost SENDs",
            actual=len(events),
        ))
    if limit == 1 and len(events) != robots - 1:
        raise ProtocolError(Diagnostic(
            owner=OWNER, function="collect_one_shot_cost_rows",
            category="contract", code="P2D_ONE_SHOT_SEND_COUNT_MISMATCH",
            expected=robots - 1, actual=len(events),
        ))
    return CentralizedCostReceipt(
        visible_rows=tuple(sorted(known.items())),
        cost_events=tuple(events), cost_deliveries=tuple(deliveries),
        cost_start_ms=cost_start_ms, cost_cutoff_ms=last_cutoff_ms,
        cost_phase_end_ms=start_ms, cost_rounds_executed=rounds,
    )

def validate_centralized_planning_rule(*, planning_rule: str) -> None:
    """Keep Global Greedy default; task-ID priority is an explicit P2G opt-in."""
    if planning_rule not in ("global", "task_ordered"):
        raise ProtocolError(Diagnostic(
            owner=OWNER, function="validate_centralized_planning_rule",
            category="planning", code="P2G_INVALID_CENTRAL_GREEDY_RULE",
            expected=("global", "task_ordered"), actual=planning_rule,
        ))


def plan_from_received_cost_rows(
    *, receipt: CentralizedCostReceipt, planning_rule: str = "global",
) -> tuple[tuple[int, int], ...]:
    """Reuse original greedy planner on actually visible, physical-ID-sorted rows."""
    real_ids = receipt.received_robot_ids
    if not real_ids:
        raise ProtocolError(Diagnostic(
            owner=OWNER, function="plan_from_received_cost_rows",
            category="state", code="P2D_NO_CENTRALIZED_COST_ROWS",
            expected="coordinator's own row", actual=real_ids,
        ))
    validate_centralized_planning_rule(planning_rule=planning_rule)
    cost_rows = tuple(row for _robot, row in receipt.visible_rows)
    planner = (solve_visible_task_ordered_greedy_assignment
               if planning_rule == "task_ordered"
               else solve_visible_batched_greedy_assignment)
    local_pairs = planner(
        cost_rows, frozenset(range(len(real_ids))),
    ).assigned_pairs
    physical_pairs = tuple(
        sorted(((real_ids[local_id], task_id) for local_id, task_id in local_pairs),
               key=lambda x: (x[1], x[0]))
    )
    validate_one_to_one_commits(physical_pairs)
    if any(robot not in real_ids for robot, _task in physical_pairs):
        raise ProtocolError(Diagnostic(
            owner=OWNER, function="plan_from_received_cost_rows",
            category="contract", code="P2D_HIDDEN_COST_ROW_USED",
            expected=real_ids, actual=physical_pairs,
        ))
    return physical_pairs


def validate_centralized_assignment_scope(
    *, assignment_scope: str, planning_rule: str, max_cost_rounds: int,
) -> None:
    """Explicit per-task paid assignment/Commit; default batch does not change."""
    if assignment_scope not in ("batch", "task_sequence"):
        raise ProtocolError(Diagnostic(
            owner=OWNER, function="validate_centralized_assignment_scope",
            category="data", code="P2H_UNKNOWN_CENTRAL_ASSIGNMENT_SCOPE",
            expected=("batch", "task_sequence"), actual=assignment_scope,
        ))
    if (assignment_scope == "task_sequence"
            and (planning_rule != "task_ordered" or max_cost_rounds != 1)):
        raise ProtocolError(Diagnostic(
            owner=OWNER, function="validate_centralized_assignment_scope",
            category="planning", code="P2H_SEQUENTIAL_CENTRAL_REQUIRES_ONESHOT_GREEDY",
            expected={"planning_rule":"task_ordered","max_cost_rounds":1},
            actual={"planning_rule":planning_rule,"max_cost_rounds":max_cost_rounds},
        ))


def select_next_task_ordered_centralized_pair(
    *, receipt: CentralizedCostReceipt,
    task_id: int, remaining_robot_ids: frozenset[int],
) -> tuple[int, int] | None:
    """Planner: choose cheapest unretired physical Cost receipt for this task."""
    rows=receipt.visible_rows
    if type(task_id) is not int or task_id < 0 or (
        rows and task_id >= len(rows[0][1])
    ):
        raise ProtocolError(Diagnostic(
            owner=OWNER, function="select_next_task_ordered_centralized_pair",
            category="data", code="P2H_CENTRAL_TASK_INDEX_INVALID",
            expected=f"task in [0,{len(rows[0][1]) if rows else 0})",
            actual=task_id,
        ))
    eligible=frozenset(
        local_id for local_id,(robot_id,_cost_row) in enumerate(rows)
        if robot_id in remaining_robot_ids
    )
    if not eligible:
        return None
    local_id,_cost=select_cheapest_visible_greedy_row(
        cost_column=tuple(cost_row[task_id] for _robot,cost_row in rows),
        visible_robot_ids=eligible,
    )
    return rows[local_id][0],task_id


def run_task_ordered_centralized_sequence(
    *, receipt: CentralizedCostReceipt, coordinator_id: int,
    num_tasks: int, sampler: WifiCausalTimingSampler,
) -> tuple[tuple[tuple[int,int],...],tuple[CommunicationEvent,...],tuple[CommunicationEvent,...]]:
    """T0 assignment -> executor Commit -> T1; no retry or hidden Cost."""
    remaining=frozenset(receipt.received_robot_ids)
    announced: list[tuple[int,int]]=[]
    decisions: list[CommunicationEvent]=[]
    commits: list[CommunicationEvent]=[]
    ready_ms=receipt.cost_phase_end_ms
    for task_id in range(num_tasks):
        pair=select_next_task_ordered_centralized_pair(
            receipt=receipt,task_id=task_id,remaining_robot_ids=remaining,
        )
        if pair is None:
            continue
        decision=publish_centralized_assignment(
            pairs=(pair,),coordinator_id=coordinator_id,
            release_ms=ready_ms,sampler=sampler,
        )
        commit=emit_centralized_commits(
            pairs=(pair,),release_ms=decision.arrival_time_ms,sampler=sampler,
        )[0]
        if (decision.send_time_ms+1e-9 < ready_ms
                or commit.send_time_ms+1e-9 < decision.arrival_time_ms):
            raise ProtocolError(Diagnostic(
                owner=OWNER,function="run_task_ordered_centralized_sequence",
                category="time",code="P2H_CENTRAL_COMMIT_BEFORE_DECISION",
                expected={"task":task_id,"decision_after_ms":ready_ms,
                          "commit_after_ms":decision.arrival_time_ms},
                actual={"decision_ms":decision.send_time_ms,
                        "commit_ms":commit.send_time_ms},
            ))
        announced.append(pair)
        decisions.append(decision)
        commits.append(commit)
        ready_ms=commit.arrival_time_ms
        remaining=remaining.difference((pair[0],))
    validate_one_to_one_commits(announced)
    if any(pair[0] not in receipt.received_robot_ids for pair in announced):
        raise ProtocolError(Diagnostic(
            owner=OWNER,function="run_task_ordered_centralized_sequence",
            category="contract",code="P2H_CENTRAL_HIDDEN_COST_USED",
            expected=receipt.received_robot_ids,actual=announced,
        ))
    return tuple(announced),tuple(decisions),tuple(commits)


def publish_centralized_assignment(
    *, pairs: tuple[tuple[int, int], ...], coordinator_id: int,
    release_ms: float, sampler: WifiCausalTimingSampler,
) -> CommunicationEvent:
    """One sender-accounted broadcast of current pairs; no second attempt."""
    payload = assignment_payload_bytes(len(pairs))
    if payload > 1200:
        raise ProtocolError(Diagnostic(
            owner=OWNER, function="publish_centralized_assignment",
            category="data", code="P2D_ASSIGNMENT_FRAME_TOO_LARGE",
            expected="<=1200B", actual=payload,
        ))
    return _broadcast_event(
        phase="centralized_assignment", sender_id=coordinator_id,
        send_time_ms=release_ms, payload_bytes=payload, sampler=sampler,
    )


def emit_centralized_commits(
    *, pairs: tuple[tuple[int, int], ...],
    release_ms: float, sampler: WifiCausalTimingSampler,
) -> tuple[CommunicationEvent, ...]:
    """One paid reliable native Commit per selected executor."""
    validate_one_to_one_commits(pairs)
    return tuple(
        _broadcast_event(
            phase="commit", sender_id=robot_id, task_id=task_id,
            send_time_ms=release_ms, payload_bytes=COMMIT_PAYLOAD_BYTES,
            sampler=sampler,
        )
        for robot_id, task_id in pairs
    )


def simulate_one_shot_centralized(
    *, cost_matrix: tuple[tuple[float, ...], ...],
    task_positions: tuple[tuple[float, float], ...],
    profile: EmpiricalLatencyProfile, seed: int, p_loss: float,
    coordinator_id: int = 0,
    max_cost_rounds: int = 1,
    planning_rule: str = "global",
    assignment_scope: str = "batch",
) -> CentralizedResult:
    """TASK once -> Cost once/retry -> batch or true per-task paid Commit."""
    validate_centralized_retry_limit(max_cost_rounds=max_cost_rounds)
    validate_centralized_planning_rule(planning_rule=planning_rule)
    validate_centralized_assignment_scope(
        assignment_scope=assignment_scope,planning_rule=planning_rule,
        max_cost_rounds=max_cost_rounds,
    )
    robots = validate_centralized_configuration(
        cost_matrix=cost_matrix, task_positions=task_positions,
        coordinator_id=coordinator_id, p_loss=p_loss,
    )
    sampler = WifiCausalTimingSampler(
        profile=profile, seed=seed,
        config=WifiTimingConfig(phy_rate_mbps=144.0),
    )
    losses = BernoulliLossSampler(seed)
    task = broadcast_task_information(
        task_positions=task_positions, num_robots=robots,
        sampler=sampler, loss_sampler=losses, p_loss=0.0,
        phase_timeout_ms=max(profile.samples_ms) + 1000.0,
    )
    task_ms = max((e.arrival_time_ms for e in task.events), default=0.0)
    before_cost = sampler.summarize_network()
    cost_budget_ms = estimate_e9h_guarded_initial_cost_ms(
        profile=profile, total_robots=robots, total_tasks=robots,
        reference_phy_mbps=144.0,
    )
    receipt = collect_one_shot_cost_rows(
        cost_matrix=cost_matrix, coordinator_id=coordinator_id,
        cost_start_ms=task_ms, cutoff_ms=task_ms + cost_budget_ms,
        sampler=sampler, loss_sampler=losses, p_loss=p_loss,
        max_cost_rounds=max_cost_rounds,
    )
    after_cost = sampler.summarize_network()
    if assignment_scope=="task_sequence":
        pairs,decisions,commits=run_task_ordered_centralized_sequence(
            receipt=receipt,coordinator_id=coordinator_id,
            num_tasks=robots,sampler=sampler,
        )
        stop_ms=max(receipt.cost_phase_end_ms,
                    max((e.arrival_time_ms for e in commits),default=0.0))
        assignment_ms=sum(e.arrival_time_ms-e.send_time_ms for e in decisions)
        commit_ms=sum(e.arrival_time_ms-e.send_time_ms for e in commits)
    else:
        pairs=plan_from_received_cost_rows(
            receipt=receipt,planning_rule=planning_rule,
        )
        decision=publish_centralized_assignment(
            pairs=pairs,coordinator_id=coordinator_id,
            release_ms=receipt.cost_phase_end_ms,sampler=sampler,
        )
        decisions=(decision,)
        commits=emit_centralized_commits(
            pairs=pairs,release_ms=decision.arrival_time_ms,sampler=sampler,
        )
        stop_ms=max(decision.arrival_time_ms,
                    max((e.arrival_time_ms for e in commits),default=0.0))
        assignment_ms=decision.arrival_time_ms-receipt.cost_phase_end_ms
        commit_ms=stop_ms-decision.arrival_time_ms
    all_events=(*task.events,*receipt.cost_events,*decisions,*commits)
    physical = sampler.summarize_network()
    expected_sends = len(all_events)
    expected_bytes = sum(e.payload_bytes for e in all_events)
    if (int(physical["packet_count"]) != expected_sends or
            int(physical["application_sender_bytes"]) != expected_bytes):
        raise ProtocolError(Diagnostic(
            owner=OWNER, function="simulate_one_shot_centralized",
            category="contract", code="P2D_SENDER_LEDGER_MISMATCH",
            expected=(expected_sends, expected_bytes),
            actual=(physical["packet_count"], physical["application_sender_bytes"]),
        ))
    cost_drops = sum(not o.delivered for o in receipt.cost_deliveries)
    # Physical application SENDs, including dropped Cost, are all charged.
    total_attempts = len(task.events) * robots + len(receipt.cost_events) + (
        len(decisions) + len(commits)) * (robots - 1)
    complete = len(pairs) == robots
    return CentralizedResult(
        assignment=pairs, received_robot_ids=receipt.received_robot_ids,
        native_success=complete, task_coverage=len(pairs) / robots,
        native_stop_ms=stop_ms,
        stop_reason=(
            ("task_sequence_full_commit" if complete else "task_sequence_incomplete")
            if assignment_scope=="task_sequence"
            else ("one_shot_full_commit" if complete else "one_shot_incomplete")
            if max_cost_rounds == 1
            else ("retry_full_commit" if complete else "retry_limit_incomplete")
        ),
        sender_sends=expected_sends, sender_bytes=expected_bytes,
        receiver_attempts=total_attempts, receiver_drops=cost_drops,
        cost_sender_sends=len(receipt.cost_events),
        cost_sender_bytes=sum(e.payload_bytes for e in receipt.cost_events),
        cost_receiver_drops=cost_drops,
        decision_sender_sends=len(decisions), commit_sender_sends=len(commits),
        cost_airtime_ms=(float(after_cost["total_airtime_ms"]) -
                         float(before_cost["total_airtime_ms"])),
        event_ledger={
            "task_sender_frames":len(task.events),
            "cost_sender_frames":len(receipt.cost_events),
            "assignment_sender_frames":len(decisions),
            "commit_sender_frames":len(commits),
            "received_cost_rows":receipt.received_robot_ids,
            **({"sequential_decision_commit_trace":tuple(
                {
                    "task_id":pair[1],
                    "assignment_send_ms":d.send_time_ms,
                    "assignment_arrival_ms":d.arrival_time_ms,
                    "commit_send_ms":c.send_time_ms,
                    "commit_arrival_ms":c.arrival_time_ms,
                }
                for pair,d,c in zip(pairs,decisions,commits)
            )} if assignment_scope=="task_sequence" else {}),
            "cost_receiver_attempts":len(receipt.cost_deliveries),
            "cost_receiver_drops":cost_drops,
            **({"cost_rounds_executed":receipt.cost_rounds_executed,
                "planning_rule":planning_rule,
                "assignment_scope":assignment_scope}
               if max_cost_rounds != 1 or planning_rule != "global" or
               assignment_scope!="batch" else {}),
            "network":physical,
        },
        phase_times={
            "task_ms":task_ms,
            ("cost_once_ms" if max_cost_rounds == 1 else "cost_retry_ms"):
                receipt.cost_phase_end_ms-task_ms,
            "assignment_ms":assignment_ms,
            "commit_ms":commit_ms,
            "total_ms":stop_ms,
        },
        cost_rounds_executed=receipt.cost_rounds_executed,
    )

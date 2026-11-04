"""P2L: small, sender-paid conflict CLAIMs after P2K Cost/Softmax/Vote.

This module owns ONLY task ownership negotiation. It never receives a
global Vote matrix for matching: each robot publishes its own support
numerator/denominator for its own proposed task. Claimed winners are
confirmed only if every expected claimant's wire packet reaches all peers
(and, for bounded_ack, the claimant receives each peer's lossy ACK).
"""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
import heapq
import math
import struct

from .coordination import (
    CommunicationEvent, DeliveryObservation, P2KLocalVoteResult,
    _broadcast_event, _lossy_broadcast_deliveries,
    _unicast_event, _lossy_unicast_delivery,
)
from .diagnostics import Diagnostic, ProtocolError
from .network import validate_packet_loss_probability
from .optimizer import validate_cost_matrix
from .protocol import validate_one_to_one_commits

OWNER = "democracy_mrta.claim_resolution"
CLAIM_WIRE = struct.Struct("<4sIIIIII")  # 28B
ACK_WIRE = struct.Struct("<4sIII")       # 16B
NO_TASK = 0xffffffff


@dataclass(frozen=True)
class P2LClaim:
    claim_round: int
    robot_id: int
    task_id: int | None
    support_votes: int
    received_ballots: int
    tickets_per_task: int


@dataclass(frozen=True)
class P2LClaimResult:
    assigned_pairs: tuple[tuple[int, int], ...]
    events: tuple[CommunicationEvent, ...]
    deliveries: tuple[DeliveryObservation, ...]
    complete_exchange: bool
    rounds_executed: int
    conflict_task_rounds: int
    reassignment_claims: int
    initial_collision_tasks: int
    public_claims: tuple[P2LClaim, ...]
    finish_ms: float
    first_diagnostic: Diagnostic | None = None

    @property
    def sender_bytes(self) -> int:
        return sum(e.payload_bytes for e in self.events)


def validate_p2l_claim_scope(
    *, run: P2KLocalVoteResult, cost_matrix: tuple[tuple[float, ...], ...],
    votes_per_voter: int, p_loss: float, channel: str,
    max_attempts: int, max_rounds: int,
) -> tuple[int, int]:
    """Data/contract gate: original Cost/Vote and local views only."""
    robots, tasks = validate_cost_matrix(cost_matrix)
    validate_packet_loss_probability(p_loss)
    valid = (
        type(votes_per_voter) is int and votes_per_voter > 0
        and votes_per_voter % tasks == 0
        and type(max_attempts) is int and 1 <= max_attempts <= 128
        and type(max_rounds) is int and 1 <= max_rounds <= 255
        and channel in ("bounded_ack", "ideal_paid")
        and robots <= 255 and tasks <= robots
        and len(run.local_vote_views) == robots
        and len(run.local_assignments) == robots
        and len(run.cost_visible_rows) == robots
        and all(len(view) == robots and all(len(row) == tasks for row in view)
                for view in run.local_vote_views)
        and all(event.phase in ("cost", "vote") for event in run.events)
        and len({r for r, _t in run.robot_claims}) == len(run.robot_claims)
        and all(0 <= r < robots and 0 <= t < tasks for r, t in run.robot_claims)
    )
    if not valid:
        raise ProtocolError(Diagnostic(
            owner=OWNER, function="validate_p2l_claim_scope",
            category="contract", code="P2L_INVALID_CLAIM_SCOPE",
            expected="P2K Cost/Vote-only native epoch, task-divisible tickets, "
                     "valid 100R/100T capacity1, bounded_ack/ideal_paid, "
                     "attempts 1..128 and rounds 1..255",
            actual={"robots":robots, "tasks":tasks, "votes":votes_per_voter,
                    "channel":channel, "attempts":max_attempts,
                    "rounds":max_rounds, "events":sorted({e.phase for e in run.events})},
        ))
    return robots, tasks


def make_p2l_claim(
    *, run: P2KLocalVoteResult, robot_id: int, task_id: int | None,
    claim_round: int, votes_per_voter: int,
) -> P2LClaim:
    """Only the *sending* robot's physically received votes may form its CLAIM."""
    view = run.local_vote_views[robot_id]
    tasks = len(view[0])
    total = sum(sum(row) for row in view)
    if total % votes_per_voter:
        raise ProtocolError(Diagnostic(
            owner=OWNER, function="make_p2l_claim",
            category="contract", code="P2L_LOCAL_BALLOT_TOTAL_INVALID",
            expected=f"multiple of {votes_per_voter} tickets",
            actual=total, details=f"robot_id={robot_id}",
        ))
    received = total // votes_per_voter
    slots = votes_per_voter // tasks
    support = view[robot_id][task_id] if task_id is not None else 0
    return P2LClaim(claim_round, robot_id, task_id, support, received, slots)


def encode_p2l_claim_packet(claim: P2LClaim) -> bytes:
    """28B authenticated-in-model sender-owned CLAIM; no Cost matrix or Score."""
    valid = (
        type(claim.claim_round) is int and 0 <= claim.claim_round <= 0xffffffff
        and type(claim.robot_id) is int and 0 <= claim.robot_id <= 255
        and (claim.task_id is None or (type(claim.task_id) is int
                                       and 0 <= claim.task_id <= 255))
        and type(claim.support_votes) is int and claim.support_votes >= 0
        and type(claim.received_ballots) is int and claim.received_ballots >= 0
        and type(claim.tickets_per_task) is int and claim.tickets_per_task > 0
        and claim.support_votes <= claim.received_ballots * claim.tickets_per_task
        and (claim.task_id is not None or claim.support_votes == 0)
    )
    if not valid:
        raise ProtocolError(Diagnostic(
            owner=OWNER, function="encode_p2l_claim_packet",
            category="data", code="P2L_INVALID_CLAIM_FIELDS",
            expected="nonnegative epoch/IDs, valid task or idle, "
                     "0<=support<=received_ballots*tickets_per_task",
            actual=repr(claim),
        ))
    return CLAIM_WIRE.pack(
        b"P2LC", claim.claim_round, claim.robot_id,
        NO_TASK if claim.task_id is None else claim.task_id,
        claim.support_votes, claim.received_ballots, claim.tickets_per_task,
    )


def decode_p2l_claim_packet(
    packet: bytes, *, claim_round: int, sender_id: int,
    tasks: int, robots: int, tickets_per_task: int,
) -> P2LClaim:
    """Reject stale/injected/out-of-scope receipt before selecting any winner."""
    if not isinstance(packet, bytes) or len(packet) != CLAIM_WIRE.size:
        raise ProtocolError(Diagnostic(
            owner=OWNER, function="decode_p2l_claim_packet",
            category="data", code="P2L_CLAIM_PACKET_SIZE_INVALID",
            expected=CLAIM_WIRE.size, actual=len(packet)
            if isinstance(packet, bytes) else type(packet).__name__,
        ))
    tag, rnd, robot, task, votes, receipts, slots = CLAIM_WIRE.unpack(packet)
    if (tag != b"P2LC" or rnd != claim_round or robot != sender_id
            or not (0 <= robot < robots)
            or (task != NO_TASK and not (0 <= task < tasks))
            or slots != tickets_per_task or receipts > robots
            or votes > receipts * slots or (task == NO_TASK and votes != 0)):
        raise ProtocolError(Diagnostic(
            owner=OWNER, function="decode_p2l_claim_packet",
            category="contract", code="P2L_RECEIVED_CLAIM_INVALID",
            expected={"round":claim_round, "sender":sender_id,
                      "robots":robots, "tasks":tasks, "slots":tickets_per_task},
            actual={"tag":tag, "round":rnd, "robot":robot, "task":task,
                    "votes":votes, "receipts":receipts, "slots":slots},
        ))
    return P2LClaim(rnd, robot, None if task == NO_TASK else task,
                    votes, receipts, slots)


def encode_p2l_ack_packet(
    *, claim_round: int, ack_sender_id: int, claim_robot_id: int,
) -> bytes:
    """16B physical ACK, independently subject to loss in bounded_ack."""
    return ACK_WIRE.pack(b"P2AK", claim_round, ack_sender_id, claim_robot_id)


def validate_p2l_ack_packet(
    packet: bytes, *, claim_round: int, ack_sender_id: int, claim_robot_id: int,
) -> None:
    """ACK data contract: no synthetic acknowledgement for a lost packet."""
    valid = (isinstance(packet, bytes) and len(packet) == ACK_WIRE.size
             and ACK_WIRE.unpack(packet) == (
                 b"P2AK", claim_round, ack_sender_id, claim_robot_id
             ))
    if not valid:
        raise ProtocolError(Diagnostic(
            owner=OWNER, function="validate_p2l_ack_packet",
            category="contract", code="P2L_ACK_CONTENT_INVALID",
            expected=(claim_round, ack_sender_id, claim_robot_id),
            actual=packet,
        ))


def transmit_p2l_claim_with_receipts(
    *, claim: P2LClaim, robots: int, tasks: int,
    sampler, loss_sampler, p_loss: float, channel: str,
    max_attempts: int, release_ms: float,
) -> tuple[list[CommunicationEvent], list[DeliveryObservation],
           P2LClaim | None, float, Diagnostic | None]:
    """One candidate's original CLAIM + all charged retry and ACK SENDs.

    The sender only regards the CLAIM as universally confirmed after its
    own ACK receipt from every other robot. Unlike ideal_paid, bounded_ack
    actually drops BOTH the CLAIM broadcast and each unicast ACK. On budget
    exhaustion, no network repair or pretend-success is allowed.
    """
    packet = encode_p2l_claim_packet(claim)
    pending = set(range(robots)) - {claim.robot_id}
    events: list[CommunicationEvent] = []
    deliveries: list[DeliveryObservation] = []
    current = release_ms
    for attempt in range(1 if channel == "ideal_paid" else max_attempts):
        event = _broadcast_event(
            phase="claim", sender_id=claim.robot_id,
            round_id=claim.claim_round + 1, task_id=None,
            send_time_ms=current, payload_bytes=len(packet),
            sampler=sampler, transmission_index=attempt,
        )
        events.append(event)
        seen = _lossy_broadcast_deliveries(
            event=event, num_robots=robots, loss_sampler=loss_sampler,
            p_loss=0.0 if channel == "ideal_paid" else p_loss,
            round_id=claim.claim_round + 1,
        )
        deliveries.extend(seen)
        latest = event.arrival_time_ms
        for receipt in seen:
            if not receipt.delivered or receipt.receiver_id not in pending:
                continue
            decode_p2l_claim_packet(
                packet, claim_round=claim.claim_round,
                sender_id=claim.robot_id, tasks=tasks, robots=robots,
                tickets_per_task=claim.tickets_per_task,
            )
            if channel == "ideal_paid":
                pending.discard(receipt.receiver_id)
                continue
            ack_packet = encode_p2l_ack_packet(
                claim_round=claim.claim_round,
                ack_sender_id=receipt.receiver_id,
                claim_robot_id=claim.robot_id,
            )
            ack_event = _unicast_event(
                phase="claim_ack", sender_id=receipt.receiver_id,
                receiver_id=claim.robot_id, task_id=None,
                round_id=claim.claim_round + 1,
                send_time_ms=event.arrival_time_ms,
                payload_bytes=len(ack_packet), sampler=sampler,
                transmission_index=attempt,
            )
            events.append(ack_event)
            latest = max(latest, ack_event.arrival_time_ms)
            delivered_ack = _lossy_unicast_delivery(
                event=ack_event, loss_sampler=loss_sampler, p_loss=p_loss,
                round_id=claim.claim_round + 1,
            )
            deliveries.append(delivered_ack)
            if delivered_ack.delivered:
                validate_p2l_ack_packet(
                    ack_packet, claim_round=claim.claim_round,
                    ack_sender_id=receipt.receiver_id,
                    claim_robot_id=claim.robot_id,
                )
                pending.discard(receipt.receiver_id)
        current = max(current, latest)
        if not pending:
            break
    if pending:
        diagnostic = Diagnostic(
            owner=OWNER, function="transmit_p2l_claim_with_receipts",
            category="time", code="P2L_CLAIM_ACK_BUDGET_EXHAUSTED",
            expected={"pending_ack_receivers":0, "max_attempts":max_attempts},
            actual={"pending_ack_receivers":len(pending),
                    "robot_id":claim.robot_id, "claim_round":claim.claim_round},
            details=f"unconfirmed_robot_ids={tuple(sorted(pending))[:20]}",
        )
        return events, deliveries, None, current, diagnostic
    return events, deliveries, decode_p2l_claim_packet(
        packet, claim_round=claim.claim_round,
        sender_id=claim.robot_id, tasks=tasks, robots=robots,
        tickets_per_task=claim.tickets_per_task,
    ), current, None


def resolve_p2l_claim_conflicts(
    *, claims: tuple[P2LClaim, ...], locked_tasks: frozenset[int],
) -> tuple[tuple[tuple[int, int], ...], tuple[int, ...], int]:
    """Only decoded public claim scores determine each contested task winner.

    Compare exact rational S = support / (tickets_per_task * receipts).
    For tied S prefer raw support, more ballots, then smaller robot ID.
    No other candidate's private votes/Cost rows enter this resolution.
    """
    if len({claim.robot_id for claim in claims}) != len(claims):
        raise ProtocolError(Diagnostic(
            owner=OWNER, function="resolve_p2l_claim_conflicts",
            category="contract", code="P2L_DUPLICATE_ROBOT_CLAIM",
            expected="one claim per robot per round",
            actual=tuple(c.robot_id for c in claims),
        ))
    if any(c.task_id in locked_tasks for c in claims if c.task_id is not None):
        raise ProtocolError(Diagnostic(
            owner=OWNER, function="resolve_p2l_claim_conflicts",
            category="safety", code="P2L_RECLAIMED_LOCKED_TASK",
            expected="only previously unclaimed tasks", actual=repr(claims),
        ))
    by_task: dict[int, list[P2LClaim]] = {}
    for claim in claims:
        if claim.task_id is not None:
            by_task.setdefault(claim.task_id, []).append(claim)
    winners = []
    losers = {claim.robot_id for claim in claims if claim.task_id is None}
    conflicts = 0
    for task, contenders in sorted(by_task.items()):
        if len(contenders) > 1:
            conflicts += 1
        winner = max(contenders, key=lambda c: (
            Fraction(c.support_votes, max(1, c.received_ballots*c.tickets_per_task)),
            c.support_votes, c.received_ballots, -c.robot_id,
        ))
        winners.append((winner.robot_id, task))
        losers.update(c.robot_id for c in contenders if c.robot_id != winner.robot_id)
    validate_one_to_one_commits(winners)
    return tuple(winners), tuple(sorted(losers)), conflicts


def choose_p2l_next_task(
    *, available_tasks: frozenset[int], own_received_vote_row: tuple[int, ...],
    own_cost_row: tuple[float, ...],
) -> int | None:
    """Unsuccessful robot reclaims only a free task using its OWN local data."""
    if not available_tasks:
        return None
    return max(sorted(available_tasks), key=lambda task: (
        own_received_vote_row[task], -own_cost_row[task], -task,
    ))


def coordinate_p2l_claims(
    *, run: P2KLocalVoteResult,
    cost_matrix: tuple[tuple[float, ...], ...],
    votes_per_voter: int, sampler, loss_sampler,
    p_loss: float, channel: str = "bounded_ack",
    max_attempts: int = 24, max_rounds: int = 101,
) -> P2LClaimResult:
    """Single bounded CLAIM ownership concern after P2K; no PSCR or global Score.

    Each round has only current contenders. Prior winners retain task
    ownership. Each expected claim needs universal receipt before ANY robot
    may execute; failure returns zero safe executions rather than inventing
    a common view. The synchronous round barrier is a model assumption.
    """
    robots, tasks = validate_p2l_claim_scope(
        run=run, cost_matrix=cost_matrix, votes_per_voter=votes_per_voter,
        p_loss=p_loss, channel=channel, max_attempts=max_attempts,
        max_rounds=max_rounds,
    )
    by_robot = dict(run.robot_claims)
    initial_frequency: dict[int, int] = {}
    for _robot, task in run.robot_claims:
        initial_frequency[task] = initial_frequency.get(task, 0) + 1
    initial_conflicts = sum(count > 1 for count in initial_frequency.values())
    locked: dict[int, int] = {}  # task -> robot, derived ONLY from public claims
    pending = set(range(robots))
    events: list[CommunicationEvent] = []
    deliveries: list[DeliveryObservation] = []
    certified_claims: list[P2LClaim] = []
    clock = max(run.decision_time_ms,
                max((event.arrival_time_ms for event in run.events), default=0.0))
    rounds = 0
    conflict_task_rounds = 0
    reassignment_claims = 0
    first_error: Diagnostic | None = None
    for claim_round in range(max_rounds):
        if len(locked) == tasks or not pending:
            break
        available = frozenset(range(tasks)) - locked.keys()
        new_claims: list[P2LClaim] = []
        for robot in sorted(pending):
            if claim_round == 0:
                task = by_robot.get(robot)
            else:
                task = choose_p2l_next_task(
                    available_tasks=available,
                    own_received_vote_row=run.local_vote_views[robot][robot],
                    own_cost_row=cost_matrix[robot],
                )
                reassignment_claims += 1
            new_claims.append(make_p2l_claim(
                run=run, robot_id=robot, task_id=task,
                claim_round=claim_round, votes_per_voter=votes_per_voter,
            ))
        public_claims: list[P2LClaim] = []
        for claim in new_claims:
            sent, observed, published, clock, error = transmit_p2l_claim_with_receipts(
                claim=claim, robots=robots, tasks=tasks,
                sampler=sampler, loss_sampler=loss_sampler, p_loss=p_loss,
                channel=channel, max_attempts=max_attempts, release_ms=clock,
            )
            events.extend(sent)
            deliveries.extend(observed)
            if error is not None and first_error is None:
                first_error = error
            if published is not None:
                public_claims.append(published)
        rounds += 1
        if first_error is not None:
            break
        certified_claims.extend(public_claims)
        winners, losers, new_conflicts = resolve_p2l_claim_conflicts(
            claims=tuple(public_claims), locked_tasks=frozenset(locked),
        )
        conflict_task_rounds += new_conflicts
        for robot, task in winners:
            locked[task] = robot
        pending = set(losers)
    if first_error is None and len(locked) < tasks:
        first_error = Diagnostic(
            owner=OWNER, function="coordinate_p2l_claims",
            category="planning", code="P2L_UNRESOLVED_TASKS_AFTER_ROUNDS",
            expected=tasks, actual=len(locked),
            details=f"rounds={rounds}, remaining_robots={len(pending)}",
        )
    assigned = (
        tuple(sorted(((robot, task) for task, robot in locked.items()),
                     key=lambda pair: (pair[1], pair[0])))
        if first_error is None else ()
    )
    validate_one_to_one_commits(assigned)
    if any(event.phase not in ("claim", "claim_ack") for event in events):
        raise ProtocolError(Diagnostic(
            owner=OWNER, function="coordinate_p2l_claims",
            category="contract", code="P2L_FORBIDDEN_CONTROL_MESSAGE",
            expected=("claim", "claim_ack"),
            actual=sorted({e.phase for e in events}),
        ))
    return P2LClaimResult(
        assigned_pairs=assigned, events=tuple(events),
        deliveries=tuple(deliveries), complete_exchange=first_error is None,
        rounds_executed=rounds, conflict_task_rounds=conflict_task_rounds,
        reassignment_claims=reassignment_claims,
        initial_collision_tasks=initial_conflicts,
        public_claims=tuple(certified_claims),
        finish_ms=clock, first_diagnostic=first_error,
    )


# P2M: one deterministic owner per task (NOT an all-peer CLAIM quorum).
# This is an alternative owner-specific arbitration path inside the existing
# claim-resolution owner, NOT a second retirement or voting state machine.
_OWNER_DECISION_WIRE = struct.Struct("<4sIIII")  # 20B
_OWNER_DECISION_ACK_WIRE = struct.Struct("<4sIII")  # 16B
_P2N_EXECUTING_WIRE = struct.Struct("<4sIIII")     # 20B


@dataclass(frozen=True)
class P2MTaskOwnerResult:
    executed_pairs: tuple[tuple[int, int], ...]
    reserved_pairs: tuple[tuple[int, int], ...]
    events: tuple[CommunicationEvent, ...]
    deliveries: tuple[DeliveryObservation, ...]
    rounds_executed: int
    conflicted_task_rounds: int
    reassignment_requests: int
    request_receipt_ack_timeouts: int
    blocked_robot_ids: tuple[int, ...]
    owner_decisions: tuple[dict, ...]
    finish_ms: float
    first_diagnostic: Diagnostic | None
    announced_executions: tuple[tuple[int, int], ...] = ()
    recipient_seen_executing_tasks: tuple[tuple[int, ...], ...] = ()
    avoided_announced_requests: int = 0
    timing_mode: str = "serial"
    request_window_total_ms: float = 0.0
    decision_window_total_ms: float = 0.0
    timeout_wait_total_ms: float = 0.0
    last_first_grant_arrival_ms: float | None = None

    @property
    def sender_bytes(self) -> int:
        return sum(e.payload_bytes for e in self.events)


def p2m_task_owner_id(*, task_id: int, robots: int) -> int:
    """Fixed task ownership, known before Cost/Vote: no leader election."""
    if (type(task_id) is not int or task_id < 0
            or type(robots) is not int or robots < 1):
        raise ProtocolError(Diagnostic(
            owner=OWNER, function="p2m_task_owner_id",
            category="data", code="P2M_INVALID_OWNER_MAP",
            expected="nonnegative task and positive robot count",
            actual=(task_id, robots),
        ))
    return task_id % robots


def validate_p2m_owner_scope(
    *, run: P2KLocalVoteResult, cost_matrix: tuple[tuple[float, ...], ...],
    votes_per_voter: int, p_loss: float, max_attempts: int, max_rounds: int,
) -> tuple[int, int]:
    """Bounded one-Cost/one-Vote + unicast-only owner scope."""
    robots, tasks = validate_cost_matrix(cost_matrix)
    validate_packet_loss_probability(p_loss)
    valid = (
        1 <= tasks <= robots <= 255 and type(votes_per_voter) is int
        and votes_per_voter >= tasks and votes_per_voter <= 1184
        and votes_per_voter % tasks == 0
        and type(max_attempts) is int and 1 <= max_attempts <= 128
        and type(max_rounds) is int and 1 <= max_rounds <= 255
        and len(run.local_vote_views) == robots
        and len(run.local_assignments) == robots
        and len(run.cost_visible_rows) == robots
        and all(len(view) == robots and all(len(row) == tasks for row in view)
                for view in run.local_vote_views)
        and all(e.phase in ("cost", "vote") for e in run.events)
        and len({r for r, _t in run.robot_claims}) == len(run.robot_claims)
    )
    if not valid:
        raise ProtocolError(Diagnostic(
            owner=OWNER, function="validate_p2m_owner_scope",
            category="contract", code="P2M_INVALID_OWNER_SCOPE",
            expected="native P2K Cost/Vote-only result, robots>=tasks, "
                     "uint8 robot/task IDs, divisible 1..1184 tickets, "
                     "1..128 attempts, 1..255 rounds",
            actual={"robots":robots,"tasks":tasks,"votes":votes_per_voter,
                    "max_attempts":max_attempts,"max_rounds":max_rounds,
                    "phases":tuple(sorted({e.phase for e in run.events}))},
        ))
    return robots, tasks


def encode_p2m_owner_decision(
    *, round_id: int, owner_id: int, robot_id: int,
    task_id: int, granted: bool,
) -> bytes:
    """20B task-owner decision; owner ID is verified from public task map."""
    if (any(type(i) is not int or i < 0 or i > 0xffffffff
            for i in (round_id,owner_id,robot_id,task_id))
            or type(granted) is not bool):
        raise ProtocolError(Diagnostic(
            owner=OWNER, function="encode_p2m_owner_decision",
            category="data", code="P2M_INVALID_DECISION_FIELDS",
            expected="uint32 round/owner/robot/task and boolean grant",
            actual=(round_id,owner_id,robot_id,task_id,granted),
        ))
    return _OWNER_DECISION_WIRE.pack(
        b"P2MD",round_id,robot_id,task_id,int(granted),
    )


def decode_p2m_owner_decision(
    packet: bytes, *, round_id: int, owner_id: int,
    robot_id: int, task_id: int, robots: int,
) -> bool:
    """The only grant accepted by a requester comes from task's fixed owner."""
    if not isinstance(packet,bytes) or len(packet)!=_OWNER_DECISION_WIRE.size:
        raise ProtocolError(Diagnostic(
            owner=OWNER, function="decode_p2m_owner_decision",
            category="data", code="P2M_DECISION_WIRE_SIZE_INVALID",
            expected=_OWNER_DECISION_WIRE.size,
            actual=len(packet) if isinstance(packet,bytes) else type(packet).__name__,
        ))
    tag,rnd,recipient,task,flag=_OWNER_DECISION_WIRE.unpack(packet)
    if (tag!=b"P2MD" or rnd!=round_id or recipient!=robot_id
            or task!=task_id or flag not in (0,1)
            or owner_id!=p2m_task_owner_id(task_id=task_id,robots=robots)):
        raise ProtocolError(Diagnostic(
            owner=OWNER, function="decode_p2m_owner_decision",
            category="contract", code="P2M_UNAUTHORISED_OWNER_DECISION",
            expected={"round":round_id,"owner":p2m_task_owner_id(
                task_id=task_id,robots=robots),
                "robot":robot_id,"task":task_id,"flag":(0,1)},
            actual={"tag":tag,"round":rnd,"owner":owner_id,
                    "robot":recipient,"task":task,"flag":flag},
        ))
    return bool(flag)


def transmit_p2m_owner_request(
    *, claim: P2LClaim, robots: int, tasks: int,
    sampler, loss_sampler, p_loss: float, max_attempts: int,
    release_ms: float,
) -> tuple[list[CommunicationEvent],list[DeliveryObservation],
           P2LClaim | None,float,Diagnostic | None]:
    """Request -> deterministic task owner -> single receipt ACK.

    A requester retries only after a failed ACK round trip. An owner
    considers a CLAIM whenever its REQUEST physically reached it,
    irrespective of whether the receipt ACK reached the requester.
    The ACK tells only the requester that the owner has seen its bid;
    a later delivered GRANT/DENY also proves owner receipt. No owner
    reads the ACK channel's hidden receiver observation to pick a winner.
    """
    if claim.task_id is None:
        raise ProtocolError(Diagnostic(
            owner=OWNER,function="transmit_p2m_owner_request",
            category="data",code="P2M_IDLE_OWNER_REQUEST",
            expected="concrete task",actual=claim,
        ))
    owner=p2m_task_owner_id(task_id=claim.task_id,robots=robots)
    packet=encode_p2l_claim_packet(claim)
    if claim.robot_id==owner:
        return [],[],decode_p2l_claim_packet(
            packet,claim_round=claim.claim_round,sender_id=claim.robot_id,
            tasks=tasks,robots=robots,tickets_per_task=claim.tickets_per_task,
        ),release_ms,None
    events=[]
    deliveries=[]
    clock=release_ms
    owner_received=None
    for copy in range(max_attempts):
        sent=_unicast_event(
            phase="owner_request",sender_id=claim.robot_id,receiver_id=owner,
            send_time_ms=clock,payload_bytes=len(packet),sampler=sampler,
            task_id=claim.task_id,round_id=claim.claim_round+1,
            transmission_index=copy,
        )
        events.append(sent)
        receipt=_lossy_unicast_delivery(
            event=sent,loss_sampler=loss_sampler,p_loss=p_loss,
            round_id=claim.claim_round+1,
        )
        deliveries.append(receipt)
        clock=max(clock,sent.arrival_time_ms)
        if not receipt.delivered:
            continue
        decoded=decode_p2l_claim_packet(
            packet,claim_round=claim.claim_round,sender_id=claim.robot_id,
            tasks=tasks,robots=robots,tickets_per_task=claim.tickets_per_task,
        )
        # This state belongs solely to the owner who received the wire;
        # it MUST NOT depend on whether its later ACK reaches the robot.
        owner_received=decoded
        ack=encode_p2l_ack_packet(
            claim_round=claim.claim_round,ack_sender_id=owner,
            claim_robot_id=claim.robot_id,
        )
        sent_ack=_unicast_event(
            phase="owner_request_ack",sender_id=owner,
            receiver_id=claim.robot_id,send_time_ms=clock,
            payload_bytes=len(ack),sampler=sampler,
            task_id=claim.task_id,round_id=claim.claim_round+1,
            transmission_index=copy,
        )
        events.append(sent_ack)
        ack_receipt=_lossy_unicast_delivery(
            event=sent_ack,loss_sampler=loss_sampler,p_loss=p_loss,
            round_id=claim.claim_round+1,
        )
        deliveries.append(ack_receipt)
        clock=max(clock,sent_ack.arrival_time_ms)
        if ack_receipt.delivered:
            validate_p2l_ack_packet(
                ack,claim_round=claim.claim_round,
                ack_sender_id=owner,claim_robot_id=claim.robot_id,
            )
            return events,deliveries,owner_received,clock,None
    diagnostic=Diagnostic(
        owner=OWNER,function="transmit_p2m_owner_request",
        category="time",code="P2M_REQUEST_ACK_LIMIT",
        expected="bidder's receipt ACK after physically sent owner request",
        actual={"robot":claim.robot_id,"task":claim.task_id,
                "attempts":max_attempts,
                "owner_physically_received_request":owner_received is not None},
        details=("No request reached the owner; robot must block"
                 if owner_received is None else
                 "Owner saw bid; bidder may still learn via owner GRANT/DENY"),
    )
    # If REQUEST arrived, owner MAY consider it; lost ACK is not an
    # owner-side rejection. Candidate never changes task absent a
    # physically received owner GRANT or DENY response.
    return events,deliveries,owner_received,clock,diagnostic


def transmit_p2m_owner_decision(
    *, claim: P2LClaim, robots: int, granted: bool,
    sampler, loss_sampler, p_loss: float, max_attempts: int,
    release_ms: float,
) -> tuple[list[CommunicationEvent],list[DeliveryObservation],
           bool,float,Diagnostic | None]:
    """Owner -> claimant GRANT/DENY, claimant -> owner ACK.

    Owner makes GRANT irrevocable BEFORE transmission. Candidate acts
    only after a physically delivered GRANT. If final ACK is lost,
    the owner retransmits but NEVER reallocates the reserved task.
    Thus an uncertain result may be incomplete but cannot duplicate a
    task or exceed robot capacity. No other robot sees this decision.
    """
    task=claim.task_id
    if task is None:
        raise ProtocolError(Diagnostic(
            owner=OWNER,function="transmit_p2m_owner_decision",
            category="data",code="P2M_IDLE_OWNER_DECISION",
            expected="concrete task",actual=claim,
        ))
    owner=p2m_task_owner_id(task_id=task,robots=robots)
    wire=encode_p2m_owner_decision(
        round_id=claim.claim_round,owner_id=owner,
        robot_id=claim.robot_id,task_id=task,granted=granted,
    )
    if claim.robot_id==owner:
        accepted=decode_p2m_owner_decision(
            wire,round_id=claim.claim_round,owner_id=owner,
            robot_id=claim.robot_id,task_id=task,robots=robots,
        )
        return [],[],accepted if granted else True,release_ms,None
    events=[]
    deliveries=[]
    clock=release_ms
    receiver_got_decision=False
    for copy in range(max_attempts):
        sent=_unicast_event(
            phase="owner_decision",sender_id=owner,
            receiver_id=claim.robot_id,send_time_ms=clock,
            payload_bytes=len(wire),sampler=sampler,
            task_id=task,round_id=claim.claim_round+1,
            transmission_index=copy,
        )
        events.append(sent)
        obs=_lossy_unicast_delivery(
            event=sent,loss_sampler=loss_sampler,p_loss=p_loss,
            round_id=claim.claim_round+1,
        )
        deliveries.append(obs)
        clock=max(clock,sent.arrival_time_ms)
        if not obs.delivered:
            continue
        decoded_grant=decode_p2m_owner_decision(
            wire,round_id=claim.claim_round,owner_id=owner,
            robot_id=claim.robot_id,task_id=task,robots=robots,
        )
        if decoded_grant!=granted:
            raise ProtocolError(Diagnostic(
                owner=OWNER,function="transmit_p2m_owner_decision",
                category="contract",code="P2M_DECISION_FLAG_CHANGED",
                expected=granted,actual=decoded_grant,
            ))
        receiver_got_decision=True
        ack=_OWNER_DECISION_ACK_WIRE.pack(
            b"P2MA",claim.claim_round,claim.robot_id,task,
        )
        sent_ack=_unicast_event(
            phase="owner_decision_ack",sender_id=claim.robot_id,
            receiver_id=owner,send_time_ms=clock,
            payload_bytes=len(ack),sampler=sampler,
            task_id=task,round_id=claim.claim_round+1,
            transmission_index=copy,
        )
        events.append(sent_ack)
        ack_obs=_lossy_unicast_delivery(
            event=sent_ack,loss_sampler=loss_sampler,p_loss=p_loss,
            round_id=claim.claim_round+1,
        )
        deliveries.append(ack_obs)
        clock=max(clock,sent_ack.arrival_time_ms)
        if ack_obs.delivered:
            if _OWNER_DECISION_ACK_WIRE.unpack(ack)!=(
                    b"P2MA",claim.claim_round,claim.robot_id,task):
                raise ProtocolError(Diagnostic(
                    owner=OWNER,function="transmit_p2m_owner_decision",
                    category="contract",code="P2M_DECISION_ACK_MALFORMED",
                    expected="P2MA round/robot/task",
                    actual=ack,
                ))
            return events,deliveries,True,clock,None
    # An actually delivered grant remains safe even if the final ACK
    # is lost: owner irrevocably reserves this task, and robot knows it.
    if receiver_got_decision:
        return events,deliveries,True,clock,None
    diagnostic=Diagnostic(
        owner=OWNER,function="transmit_p2m_owner_decision",
        category="time",code="P2M_DECISION_DELIVERY_LIMIT",
        expected="physical delivery of owner GRANT/DENY",
        actual={"robot":claim.robot_id,"task":task,"granted":granted,
                "attempts":max_attempts},
        details="Robot gets no decision and is BLOCKED; GRANT reserved forever",
    )
    return events,deliveries,False,clock,diagnostic




def validate_p2n_announcement_repetitions(repetitions: int) -> int:
    """One opt-in protocol knob. P2M default 0 preserves all old behavior."""
    if type(repetitions) is not int or not 0 <= repetitions <= 5:
        raise ProtocolError(Diagnostic(
            owner=OWNER, function="validate_p2n_announcement_repetitions",
            category="data", code="P2N_INVALID_ANNOUNCEMENT_REPETITIONS",
            expected="integer 0 (legacy P2M) or 1..5 physical broadcasts",
            actual=repetitions,
        ))
    return repetitions


def encode_p2n_execution_announcement(
    *, claim_round: int, robot_id: int, task_id: int, robots: int,
) -> bytes:
    """20B EXECUTING notice, authored ONLY after the claimant got a GRANT.

    Wire is tag, claim_round, actual executor, task ID, public owner ID.
    Announcement is advisory; it is NEVER authority to execute.
    """
    if (type(robots) is not int or not 1 <= robots <= 255
            or type(claim_round) is not int
            or not 0 <= claim_round <= 0xffffffff
            or type(robot_id) is not int or not 0 <= robot_id < robots
            or type(task_id) is not int or not 0 <= task_id <= 255):
        raise ProtocolError(Diagnostic(
            owner=OWNER, function="encode_p2n_execution_announcement",
            category="data", code="P2N_INVALID_EXECUTING_FIELDS",
            expected="uint32 claim_round, valid robot/task and robot count 1..255",
            actual={"round":claim_round,"robot":robot_id,"task":task_id,
                    "robots":robots},
        ))
    return _P2N_EXECUTING_WIRE.pack(
        b"P2NX", claim_round, robot_id, task_id,
        p2m_task_owner_id(task_id=task_id, robots=robots),
    )


def decode_p2n_execution_announcement(
    packet: bytes, *, claim_round: int, sender_id: int,
    task_id: int, robots: int, tasks: int,
) -> tuple[int, int]:
    """Validate *received wire*, sender identity and task-owner mapping.

    This function cannot infer that other peers received the notice.
    Sender was previously approved by its owner in the live actor.
    """
    if not isinstance(packet, bytes) or len(packet) != _P2N_EXECUTING_WIRE.size:
        raise ProtocolError(Diagnostic(
            owner=OWNER, function="decode_p2n_execution_announcement",
            category="data", code="P2N_BAD_EXECUTING_PACKET_SIZE",
            expected=_P2N_EXECUTING_WIRE.size,
            actual=len(packet) if isinstance(packet, bytes) else type(packet).__name__,
        ))
    tag, actual_round, robot, task, owner = _P2N_EXECUTING_WIRE.unpack(packet)
    if (tag != b"P2NX" or actual_round != claim_round
            or robot != sender_id or task != task_id
            or not 0 <= robot < robots or not 0 <= task < tasks
            or owner != p2m_task_owner_id(task_id=task, robots=robots)):
        raise ProtocolError(Diagnostic(
            owner=OWNER, function="decode_p2n_execution_announcement",
            category="contract", code="P2N_EXECUTING_IDENTITY_MISMATCH",
            expected={"tag":"P2NX","round":claim_round,"sender":sender_id,
                      "task":task_id,"owner":p2m_task_owner_id(
                          task_id=task_id,robots=robots)},
            actual={"tag":tag,"round":actual_round,"sender":robot,
                    "task":task,"owner":owner},
        ))
    return robot, task


def transmit_p2n_execution_announcement(
    *, robot_id: int, task_id: int, claim_round: int,
    robots: int, tasks: int, repetitions: int,
    sampler, loss_sampler, p_loss: float, release_ms: float,
) -> tuple[list[CommunicationEvent], list[DeliveryObservation],
           tuple[int, ...], float]:
    """Actual repeated EXECUTING broadcasts; charge EVERY attempted SEND.

    Remote receiver caches only its own truly delivered notices;
    consecutive repeats are deduplicated by task ID. The physical
    announcements contain no global Score or vote distribution.
    This helper is called only AFTER receipt of an owner GRANT.
    """
    valid_repetitions=validate_p2n_announcement_repetitions(repetitions)
    if not valid_repetitions:
        raise ProtocolError(Diagnostic(
            owner=OWNER, function="transmit_p2n_execution_announcement",
            category="contract", code="P2N_CANNOT_SEND_ZERO_REPETITIONS",
            expected="1..5 actual broadcast attempts",actual=repetitions,
        ))
    packet=encode_p2n_execution_announcement(
        claim_round=claim_round, robot_id=robot_id,
        task_id=task_id, robots=robots,
    )
    # This is the physically received TASK dimension, not an extra
    # task availability oracle. No true global reservation map is sent.
    receivers=set()
    events=[]
    deliveries=[]
    clock=release_ms
    for copy in range(valid_repetitions):
        event=_broadcast_event(
            phase="execution_announce",sender_id=robot_id,
            task_id=task_id,round_id=claim_round+1,
            send_time_ms=clock,payload_bytes=len(packet),sampler=sampler,
            transmission_index=copy,
        )
        events.append(event)
        observed=_lossy_broadcast_deliveries(
            event=event,num_robots=robots,
            loss_sampler=loss_sampler,p_loss=p_loss,
            round_id=claim_round+1,
        )
        deliveries.extend(observed)
        clock=max(clock,event.arrival_time_ms)
        for receipt in observed:
            if receipt.delivered and receipt.arrival_time_ms is not None:
                _executor, actual_task=decode_p2n_execution_announcement(
                    packet,claim_round=claim_round,
                    sender_id=robot_id,task_id=task_id,
                    robots=robots,tasks=tasks,
                )
                if actual_task!=task_id:
                    raise ProtocolError(Diagnostic(
                        owner=OWNER,function="transmit_p2n_execution_announcement",
                        category="contract",code="P2N_RECEIVED_TASK_CHANGED",
                        expected=task_id,actual=actual_task,
                    ))
                receivers.add(receipt.receiver_id)
    return events, deliveries, tuple(sorted(receivers)), clock


def select_p2m_local_request_task(
    *, run: P2KLocalVoteResult, robot_id: int,
    own_cost_row: tuple[float, ...],
    tried_tasks: frozenset[int], first_attempt: bool,
    known_executing_tasks: frozenset[int] = frozenset(),
) -> int | None:
    """Candidate uses ONLY own votes, own cost, own DENYs and received EXECUTING.

    Announcements are advisory negatives, NOT a proof that unknown tasks
    are available. The fixed task owner still makes every GRANT.
    """
    tasks=len(own_cost_row)
    excluded=tried_tasks | known_executing_tasks
    if first_attempt:
        original=dict(run.robot_claims).get(robot_id)
        if original is not None and original not in excluded:
            return original
    return choose_p2l_next_task(
        available_tasks=frozenset(range(tasks))-excluded,
        own_received_vote_row=run.local_vote_views[robot_id][robot_id],
        own_cost_row=own_cost_row,
    )



# P2O: temporal transport of the SAME P2M fixed-owner CLAIM and GRANT.
# The message, ticket, winner, and reservation owners are unchanged.
@dataclass(frozen=True)
class P2OExchangeWindow:
    events: tuple[CommunicationEvent, ...]
    deliveries: tuple[DeliveryObservation, ...]
    owner_received: frozenset[int]
    robot_received: frozenset[int]
    ack_confirmed: frozenset[int]
    announced_executions: tuple[tuple[int, int], ...]
    first_grant_arrivals: tuple[tuple[int, float], ...]
    finish_ms: float
    timeout_wait_ms: float


def validate_p2o_timing_scope(
    *, retry_timeout_ms: float, plans: tuple[tuple[P2LClaim, bool | None], ...],
    phase: str, robots: int, max_attempts: int, start_ms: float,
) -> None:
    """Time + message-plan boundary, before any physical SEND is created."""
    valid = (
        phase in ("request", "decision")
        and type(retry_timeout_ms) in (int, float)
        and math.isfinite(retry_timeout_ms) and retry_timeout_ms > 0
        and math.isfinite(start_ms) and start_ms >= 0
        and type(max_attempts) is int and 1 <= max_attempts <= 128
        and type(robots) is int and robots >= 1
        and len({c.robot_id for c, _ in plans}) == len(plans)
        and all(
            c.task_id is not None and 0 <= c.robot_id < robots
            and (granted is None if phase == "request"
                 else type(granted) is bool)
            for c, granted in plans
        )
    )
    if not valid:
        raise ProtocolError(Diagnostic(
            owner=OWNER, function="validate_p2o_timing_scope",
            category="time", code="P2O_INVALID_TEMPORAL_SCOPE",
            expected="request/decision; finite positive timeout; unique "
                     "candidate per task-owner round; valid 1..128 attempts",
            actual={"phase":phase,"timeout_ms":retry_timeout_ms,
                    "robots":robots,"attempts":max_attempts,
                    "start_ms":start_ms,"claim_count":len(plans)},
        ))


def encode_p2o_exchange_payloads(
    *, claim: P2LClaim, granted: bool | None,
    robots: int, phase: str,
) -> tuple[bytes, bytes]:
    """Preserve P2M's original on-wire schemas, not another protocol."""
    task=claim.task_id
    if task is None:
        raise ProtocolError(Diagnostic(
            owner=OWNER,function="encode_p2o_exchange_payloads",
            category="data",code="P2O_CANNOT_SEND_IDLE_CLAIM",
            expected="concrete task",actual=claim,
        ))
    owner=p2m_task_owner_id(task_id=task,robots=robots)
    if phase=="request":
        return (encode_p2l_claim_packet(claim),
                encode_p2l_ack_packet(
                    claim_round=claim.claim_round,ack_sender_id=owner,
                    claim_robot_id=claim.robot_id))
    return (
        encode_p2m_owner_decision(
            round_id=claim.claim_round,owner_id=owner,
            robot_id=claim.robot_id,task_id=task,granted=bool(granted),
        ),
        _OWNER_DECISION_ACK_WIRE.pack(
            b"P2MA",claim.claim_round,claim.robot_id,task),
    )


def validate_p2o_received_payload(
    *, claim: P2LClaim, payload: bytes, phase: str,
    granted: bool | None, robots: int, tasks: int,
) -> None:
    """Only a physically delivered packet may authorize an owner/robot action."""
    task=claim.task_id
    if task is None:
        raise ProtocolError(Diagnostic(
            owner=OWNER,function="validate_p2o_received_payload",
            category="data",code="P2O_IDLE_DELIVERY",
            expected="concrete task",actual=claim,
        ))
    if phase=="request":
        received=decode_p2l_claim_packet(
            payload,claim_round=claim.claim_round,
            sender_id=claim.robot_id,tasks=tasks,robots=robots,
            tickets_per_task=claim.tickets_per_task,
        )
        if received!=claim:
            raise ProtocolError(Diagnostic(
                owner=OWNER,function="validate_p2o_received_payload",
                category="contract",code="P2O_RECEIVED_CLAIM_CHANGED",
                expected=claim,actual=received,
            ))
    else:
        decoded=decode_p2m_owner_decision(
            payload,round_id=claim.claim_round,
            owner_id=p2m_task_owner_id(task_id=task,robots=robots),
            robot_id=claim.robot_id,task_id=task,robots=robots,
        )
        if decoded!=granted:
            raise ProtocolError(Diagnostic(
                owner=OWNER,function="validate_p2o_received_payload",
                category="contract",code="P2O_RECEIVED_GRANT_CHANGED",
                expected=granted,actual=decoded,
            ))


def schedule_p2o_exchange_window(
    *, plans: tuple[tuple[P2LClaim, bool | None], ...],
    phase: str, robots: int, tasks: int, sampler, loss_sampler,
    p_loss: float, max_attempts: int, retry_timeout_ms: float,
    start_ms: float, announcement_repetitions: int,
) -> P2OExchangeWindow:
    """Shared-radio, causally ordered transport of ONE owner round phase.

    At start_ms, all robots may independently start. The existing
    WifiCausalTimingSampler serializes PHYSICAL media service but does
    not serialize end-to-end waits. One (t, ordinal, kind, robot, copy)
    priority queue schedules sender retry deadlines, actual packet
    deliveries, ACK generation and first-delivered-GRANT announcements.

    This function does NOT arbitrate task ownership, replan, retire
    robots or consult any global Cost/Vote/locked-task state.
    """
    validate_p2o_timing_scope(
        retry_timeout_ms=retry_timeout_ms,plans=plans,phase=phase,
        robots=robots,max_attempts=max_attempts,start_ms=start_ms,
    )
    repeat_count=validate_p2n_announcement_repetitions(
        announcement_repetitions,
    )
    by_robot={claim.robot_id:(claim,granted) for claim,granted in plans}
    packets={
        robot:encode_p2o_exchange_payloads(
            claim=claim,granted=granted,robots=robots,phase=phase)
        for robot,(claim,granted) in by_robot.items()
    }
    requests=frozenset(by_robot)
    owner_received=set()
    robot_received=set()
    ack_confirmed=set()
    announced=set()
    announcements=[]
    first_grants={}
    events=[]
    deliveries=[]
    queue=[]
    ordinal=0
    finish=start_ms
    timeout_wait=0.0
    last_time=start_ms

    def enqueue(at_ms: float, kind: str, robot: int, copy: int) -> None:
        nonlocal ordinal
        if not math.isfinite(at_ms) or at_ms<start_ms-1e-9:
            raise ProtocolError(Diagnostic(
                owner=OWNER,function="schedule_p2o_exchange_window",
                category="time",code="P2O_NONCAUSAL_EVENT_TIME",
                expected={"minimum_ms":start_ms},
                actual={"at_ms":at_ms,"kind":kind,"robot":robot},
            ))
        heapq.heappush(queue,(at_ms,ordinal,kind,robot,copy))
        ordinal+=1

    for robot,(claim,granted) in sorted(by_robot.items()):
        owner=p2m_task_owner_id(task_id=claim.task_id,robots=robots)
        if owner==robot:
            if phase=="request":
                owner_received.add(robot)
            else:
                robot_received.add(robot)
                if granted and repeat_count:
                    first_grants[robot]=start_ms
                    announced.add(robot)
                    announcements.append((robot,claim.task_id))
                    for copy in range(repeat_count):
                        enqueue(start_ms,"announce",robot,copy)
        else:
            enqueue(start_ms,"send",robot,0)

    while queue:
        at_ms,_ord,kind,robot,copy=heapq.heappop(queue)
        if at_ms+1e-9<last_time:
            raise ProtocolError(Diagnostic(
                owner=OWNER,function="schedule_p2o_exchange_window",
                category="time",code="P2O_EVENT_ORDER_REVERSED",
                expected=f">={last_time}",actual=at_ms,
            ))
        last_time=at_ms
        claim,granted=by_robot[robot]
        task=claim.task_id
        owner=p2m_task_owner_id(task_id=task,robots=robots)
        data_packet,ack_packet=packets[robot]
        round_id=claim.claim_round+1
        if kind=="send":
            if robot in ack_confirmed:
                continue
            event=_unicast_event(
                phase="owner_request" if phase=="request" else "owner_decision",
                sender_id=robot if phase=="request" else owner,
                receiver_id=owner if phase=="request" else robot,
                send_time_ms=at_ms,payload_bytes=len(data_packet),
                sampler=sampler,task_id=task,round_id=round_id,
                transmission_index=copy,
            )
            events.append(event)
            finish=max(finish,event.arrival_time_ms)
            obs=_lossy_unicast_delivery(
                event=event,loss_sampler=loss_sampler,p_loss=p_loss,
                round_id=round_id,
            )
            deliveries.append(obs)
            if obs.delivered:
                enqueue(event.arrival_time_ms,"received_data",robot,copy)
            if copy+1<max_attempts:
                enqueue(at_ms+retry_timeout_ms,"send",robot,copy+1)
            else:
                # Last attempt must be allowed its ACK timeout before
                # declaring a terminal missing-receipt condition.
                enqueue(at_ms+retry_timeout_ms,"last_timeout",robot,copy)
        elif kind=="received_data":
            validate_p2o_received_payload(
                claim=claim,payload=data_packet,phase=phase,
                granted=granted,robots=robots,tasks=tasks,
            )
            if phase=="request":
                owner_received.add(robot)
            else:
                if robot not in robot_received:
                    robot_received.add(robot)
                    if granted:
                        first_grants[robot]=at_ms
                        if repeat_count:
                            announced.add(robot)
                            announcements.append((robot,task))
                            for attempt in range(repeat_count):
                                enqueue(at_ms,"announce",robot,attempt)
            # The receiver owns this ACK SEND. It cannot know whether
            # the peer will actually receive it until a physical receipt.
            enqueue(at_ms,"send_ack",robot,copy)
        elif kind=="send_ack":
            event=_unicast_event(
                phase=("owner_request_ack" if phase=="request"
                       else "owner_decision_ack"),
                sender_id=owner if phase=="request" else robot,
                receiver_id=robot if phase=="request" else owner,
                send_time_ms=at_ms,payload_bytes=len(ack_packet),
                sampler=sampler,task_id=task,round_id=round_id,
                transmission_index=copy,
            )
            events.append(event)
            finish=max(finish,event.arrival_time_ms)
            obs=_lossy_unicast_delivery(
                event=event,loss_sampler=loss_sampler,p_loss=p_loss,
                round_id=round_id,
            )
            deliveries.append(obs)
            if obs.delivered:
                enqueue(event.arrival_time_ms,"received_ack",robot,copy)
        elif kind=="received_ack":
            if phase=="request":
                validate_p2l_ack_packet(
                    ack_packet,claim_round=claim.claim_round,
                    ack_sender_id=owner,claim_robot_id=robot,
                )
            elif _OWNER_DECISION_ACK_WIRE.unpack(ack_packet)!=(
                b"P2MA",claim.claim_round,robot,task):
                raise ProtocolError(Diagnostic(
                    owner=OWNER,function="schedule_p2o_exchange_window",
                    category="contract",code="P2O_DECISION_ACK_INVALID",
                    expected=("P2MA",claim.claim_round,robot,task),
                    actual=_OWNER_DECISION_ACK_WIRE.unpack(ack_packet),
                ))
            ack_confirmed.add(robot)
        elif kind=="announce":
            wire=encode_p2n_execution_announcement(
                claim_round=claim.claim_round,robot_id=robot,
                task_id=task,robots=robots,
            )
            event=_broadcast_event(
                phase="execution_announce",sender_id=robot,
                task_id=task,round_id=round_id,
                send_time_ms=at_ms,payload_bytes=len(wire),
                sampler=sampler,transmission_index=copy,
            )
            events.append(event)
            finish=max(finish,event.arrival_time_ms)
            observed=_lossy_broadcast_deliveries(
                event=event,num_robots=robots,loss_sampler=loss_sampler,
                p_loss=p_loss,round_id=round_id,
            )
            deliveries.extend(observed)
            for observation in observed:
                if observation.delivered:
                    decode_p2n_execution_announcement(
                        wire,claim_round=claim.claim_round,
                        sender_id=robot,task_id=task,
                        robots=robots,tasks=tasks,
                    )
        elif kind=="last_timeout":
            if robot not in ack_confirmed:
                timeout_wait=max(timeout_wait,at_ms-start_ms)
                finish=max(finish,at_ms)
        else:
            raise ProtocolError(Diagnostic(
                owner=OWNER,function="schedule_p2o_exchange_window",
                category="runtime",code="P2O_UNKNOWN_EVENT_KIND",
                expected=("send","received_data","send_ack","received_ack",
                          "announce","last_timeout"),
                actual=kind,
            ))
    if (len(announced)!=len(announcements) or
            any(robot not in robot_received for robot in announced) or
            any(robot not in requests for robot in ack_confirmed)):
        raise ProtocolError(Diagnostic(
            owner=OWNER,function="schedule_p2o_exchange_window",
            category="safety",code="P2O_UNAUTHORIZED_ANNOUNCEMENT",
            expected="one announcement owner per first delivered GRANT",
            actual={"announced":announcements,
                    "received":sorted(robot_received),
                    "confirmed":sorted(ack_confirmed)},
        ))
    return P2OExchangeWindow(
        events=tuple(events),deliveries=tuple(deliveries),
        owner_received=frozenset(owner_received),
        robot_received=frozenset(robot_received),
        ack_confirmed=frozenset(ack_confirmed),
        announced_executions=tuple(announcements),
        first_grant_arrivals=tuple(sorted(first_grants.items())),
        finish_ms=finish,timeout_wait_ms=timeout_wait,
    )


def validate_p2o_announcement_receipts(
    *, window: P2OExchangeWindow,
    claims: tuple[tuple[P2LClaim,bool|None], ...],
    robots: int, seen_executing: list[set[int]],
) -> None:
    """Apply ONLY physically delivered, original owner-authorized notices."""
    expected={(claim.robot_id,claim.task_id)
              for claim,granted in claims
              if granted and claim.robot_id in window.robot_received}
    if set(window.announced_executions)!=expected:
        raise ProtocolError(Diagnostic(
            owner=OWNER,function="validate_p2o_announcement_receipts",
            category="safety",code="P2O_NOTICE_WITHOUT_DELIVERED_GRANT",
            expected=tuple(sorted(expected)),
            actual=window.announced_executions,
        ))
    for robot,task in window.announced_executions:
        seen_executing[robot].add(task)
    for obs in window.deliveries:
        if obs.phase=="execution_announce" and obs.delivered:
            if not 0<=obs.receiver_id<robots:
                raise ProtocolError(Diagnostic(
                    owner=OWNER,function="validate_p2o_announcement_receipts",
                    category="contract",code="P2O_INVALID_NOTICE_RECEIVER",
                    expected="0 <= receiver < robots",actual=obs.receiver_id,
                ))
            seen_executing[obs.receiver_id].add(obs.task_id)


def coordinate_p2m_task_owners(
    *, run: P2KLocalVoteResult, cost_matrix: tuple[tuple[float, ...], ...],
    votes_per_voter: int, sampler, loss_sampler,
    p_loss: float, max_attempts: int = 24, max_rounds: int = 101,
    execution_announce_repetitions: int = 0,
    timing_mode: str = "serial", retry_timeout_ms: float = 100.0,
) -> P2MTaskOwnerResult:
    """ONE fixed-task-owner state machine; opt-in P2O transport chronology.

    P2M/P2N default serial timing and protocol behavior are preserved.
    P2O timing_mode='causal' schedules original CLAIM, ACK, GRANT/DENY
    and P2NX events by physical release/receipt time. Only the shared
    radio service is serialized; remote receiver waits overlap.
    Owner reservation, locally received Vote and execution safety are
    all still enforced HERE, never in the time scheduler.
    """
    robots,tasks=validate_p2m_owner_scope(
        run=run,cost_matrix=cost_matrix,votes_per_voter=votes_per_voter,
        p_loss=p_loss,max_attempts=max_attempts,max_rounds=max_rounds,
    )
    repetitions=validate_p2n_announcement_repetitions(
        execution_announce_repetitions,
    )
    if timing_mode not in ("serial","causal"):
        raise ProtocolError(Diagnostic(
            owner=OWNER,function="coordinate_p2m_task_owners",
            category="data",code="P2O_UNKNOWN_TIMING_MODE",
            expected=("serial","causal"),actual=timing_mode,
        ))
    if timing_mode=="causal":
        validate_p2o_timing_scope(
            retry_timeout_ms=retry_timeout_ms,plans=(),phase="request",
            robots=robots,max_attempts=max_attempts,start_ms=0.0,
        )
    pending=set(range(robots))
    blocked=set()
    tried=[set() for _ in range(robots)]
    seen_executing=[set() for _ in range(robots)]
    announced_executions=[]
    avoided_announced_requests=0
    reserved:dict[int,int]={}  # task -> robot, maintained ONLY by task owner
    executed:dict[int,int]={}  # robot -> task, from physically received grant
    owner_decisions=[]
    events=[]
    deliveries=[]
    clock=max(run.decision_time_ms,
              max((e.arrival_time_ms for e in run.events),default=0.0))
    rounds=0
    conflicts=0
    reassignments=0
    request_ack_timeouts=0
    request_window_total=0.0
    decision_window_total=0.0
    timeout_wait_total=0.0
    last_first_grant_arrival=None
    first_error=None
    for claim_round in range(max_rounds):
        if not pending or len(executed)==tasks:
            break
        inbound:dict[int,list[P2LClaim]]={}
        causal_request_plans=[]
        causal_decision_plans=[]
        rounds+=1
        for robot in sorted(pending):
            task=select_p2m_local_request_task(
                run=run,robot_id=robot,own_cost_row=cost_matrix[robot],
                tried_tasks=frozenset(tried[robot]),
                first_attempt=(claim_round==0),
                known_executing_tasks=frozenset(seen_executing[robot]),
            )
            if repetitions:
                unfiltered=select_p2m_local_request_task(
                    run=run,robot_id=robot,own_cost_row=cost_matrix[robot],
                    tried_tasks=frozenset(tried[robot]),
                    first_attempt=(claim_round==0),
                )
                if (unfiltered is not None
                        and unfiltered in seen_executing[robot]
                        and unfiltered!=task):
                    avoided_announced_requests+=1
            if task is None:
                blocked.add(robot)
                if first_error is None:
                    first_error=Diagnostic(
                        owner=OWNER,function="select_p2m_local_request_task",
                        category="planning",code="P2M_ALL_LOCAL_TASKS_REJECTED",
                        expected="another task not previously denied",
                        actual={"robot":robot,"tried":len(tried[robot])},
                    )
                continue
            if claim_round>0:
                reassignments+=1
            claim=make_p2l_claim(
                run=run,robot_id=robot,task_id=task,
                claim_round=claim_round,votes_per_voter=votes_per_voter,
            )
            if timing_mode=="causal":
                causal_request_plans.append((claim,None))
                continue
            sent,observed,delivered,clock,error=transmit_p2m_owner_request(
                claim=claim,robots=robots,tasks=tasks,
                sampler=sampler,loss_sampler=loss_sampler,p_loss=p_loss,
                max_attempts=max_attempts,release_ms=clock,
            )
            events.extend(sent)
            deliveries.extend(observed)
            if delivered is not None:
                # Owner reads ONLY actual REQUEST receipt, never hidden
                # status of bidder's incoming owner ACK.
                inbound.setdefault(task,[]).append(delivered)
            else:
                blocked.add(robot)
            if error is not None:
                if delivered is None:
                    if first_error is None:
                        first_error=error
                else:
                    # ACK was missing at bidder, but the owner genuinely
                    # received the request and can later confirm by GRANT.
                    # This is a nonfatal communication diagnostic, not
                    # a failed allocation once an owner reply arrives.
                    request_ack_timeouts+=1
        if timing_mode=="causal":
            request_start=clock
            exchange=schedule_p2o_exchange_window(
                plans=tuple(causal_request_plans),phase="request",
                robots=robots,tasks=tasks,sampler=sampler,
                loss_sampler=loss_sampler,p_loss=p_loss,
                max_attempts=max_attempts,
                retry_timeout_ms=retry_timeout_ms,start_ms=clock,
                announcement_repetitions=0,
            )
            events.extend(exchange.events)
            deliveries.extend(exchange.deliveries)
            clock=exchange.finish_ms
            request_window_total+=clock-request_start
            timeout_wait_total+=exchange.timeout_wait_ms
            for claim,_unused in causal_request_plans:
                robot=claim.robot_id
                if robot in exchange.owner_received:
                    inbound.setdefault(claim.task_id,[]).append(claim)
                    if (robot not in exchange.ack_confirmed
                            and p2m_task_owner_id(
                                task_id=claim.task_id,robots=robots)!=robot):
                        request_ack_timeouts+=1
                else:
                    blocked.add(robot)
                    if first_error is None:
                        first_error=Diagnostic(
                            owner=OWNER,
                            function="schedule_p2o_exchange_window",
                            category="time",code="P2O_REQUEST_NOT_DELIVERED",
                            expected="owner physically receives CLAIM "
                                     "within bounded retry window",
                            actual={"robot":robot,"task":claim.task_id,
                                    "attempts":max_attempts,
                                    "retry_timeout_ms":retry_timeout_ms},
                        )
        next_pending=set()
        for task,claims in sorted(inbound.items()):
            owner=p2m_task_owner_id(task_id=task,robots=robots)
            previously_reserved=(task in reserved)
            if not previously_reserved:
                winners,losers,collision=resolve_p2l_claim_conflicts(
                    claims=tuple(claims),locked_tasks=frozenset(),
                )
                if len(winners)!=1 or winners[0][1]!=task:
                    raise ProtocolError(Diagnostic(
                        owner=OWNER,function="coordinate_p2m_task_owners",
                        category="contract",code="P2M_TASK_OWNER_NO_UNIQUE_WINNER",
                        expected={"task":task,"winner_count":1},
                        actual=winners,
                    ))
                winner=winners[0][0]
                reserved[task]=winner  # irreversible BEFORE sending GRANT
                conflicts+=collision
            else:
                winner=reserved[task]
            owner_decisions.append({
                "round":claim_round,"task":task,"owner":owner,
                "confirmed_claimants":[
                    {"robot":c.robot_id,"votes":c.support_votes,
                     "received_ballots":c.received_ballots,
                     "tickets_per_task":c.tickets_per_task}
                    for c in claims
                ],"reserved_winner":winner,
                "already_locked":previously_reserved,
            })
            for claim in claims:
                granted=(claim.robot_id==winner)
                if timing_mode=="causal":
                    causal_decision_plans.append((claim,granted))
                    continue
                sent,observed,received,clock,error=transmit_p2m_owner_decision(
                    claim=claim,robots=robots,granted=granted,
                    sampler=sampler,loss_sampler=loss_sampler,p_loss=p_loss,
                    max_attempts=max_attempts,release_ms=clock,
                )
                events.extend(sent)
                deliveries.extend(observed)
                if error is not None:
                    blocked.add(claim.robot_id)
                    if first_error is None: first_error=error
                elif received and granted:
                    if claim.robot_id in executed and executed[claim.robot_id]!=task:
                        raise ProtocolError(Diagnostic(
                            owner=OWNER,function="coordinate_p2m_task_owners",
                            category="safety",code="P2M_ROBOT_DOUBLE_GRANT",
                            expected="at most one GRANT per robot",
                            actual={"robot":claim.robot_id,
                                    "old":executed[claim.robot_id],"new":task},
                        ))
                    executed[claim.robot_id]=task
                    if repetitions:
                        # Owner has already reserved this task and the
                        # robot actually received its GRANT. Only now
                        # can an EXECUTING announcement be transmitted.
                        ae,ad,receivers,clock=transmit_p2n_execution_announcement(
                            robot_id=claim.robot_id,task_id=task,
                            claim_round=claim_round,robots=robots,tasks=tasks,
                            repetitions=repetitions,sampler=sampler,
                            loss_sampler=loss_sampler,p_loss=p_loss,
                            release_ms=clock,
                        )
                        events.extend(ae)
                        deliveries.extend(ad)
                        announced_executions.append((claim.robot_id,task))
                        seen_executing[claim.robot_id].add(task)
                        for receiver in receivers:
                            seen_executing[receiver].add(task)
                elif received:
                    tried[claim.robot_id].add(task)
                    next_pending.add(claim.robot_id)
        if timing_mode=="causal":
            decision_start=clock
            exchange=schedule_p2o_exchange_window(
                plans=tuple(causal_decision_plans),phase="decision",
                robots=robots,tasks=tasks,sampler=sampler,
                loss_sampler=loss_sampler,p_loss=p_loss,
                max_attempts=max_attempts,
                retry_timeout_ms=retry_timeout_ms,start_ms=clock,
                announcement_repetitions=repetitions,
            )
            events.extend(exchange.events)
            deliveries.extend(exchange.deliveries)
            clock=exchange.finish_ms
            decision_window_total+=clock-decision_start
            timeout_wait_total+=exchange.timeout_wait_ms
            if repetitions:
                validate_p2o_announcement_receipts(
                    window=exchange,claims=tuple(causal_decision_plans),
                    robots=robots,seen_executing=seen_executing,
                )
                announced_executions.extend(exchange.announced_executions)
            for robot,arrival in exchange.first_grant_arrivals:
                last_first_grant_arrival=max(
                    last_first_grant_arrival or 0.0,arrival,
                )
            for claim,granted in causal_decision_plans:
                robot=claim.robot_id
                if robot not in exchange.robot_received:
                    blocked.add(robot)
                    if first_error is None:
                        first_error=Diagnostic(
                            owner=OWNER,function="schedule_p2o_exchange_window",
                            category="time",code="P2O_OWNER_DECISION_NOT_DELIVERED",
                            expected="robot physically receives owner GRANT/DENY "
                                     "within bounded retry window",
                            actual={"robot":robot,"task":claim.task_id,
                                    "granted":granted,"attempts":max_attempts,
                                    "retry_timeout_ms":retry_timeout_ms},
                        )
                elif granted:
                    if robot in executed and executed[robot]!=claim.task_id:
                        raise ProtocolError(Diagnostic(
                            owner=OWNER,function="coordinate_p2m_task_owners",
                            category="safety",code="P2M_ROBOT_DOUBLE_GRANT",
                            expected="at most one owner GRANT per robot",
                            actual={"robot":robot,"prior":executed[robot],
                                    "new":claim.task_id},
                        ))
                    executed[robot]=claim.task_id
                else:
                    tried[robot].add(claim.task_id)
                    next_pending.add(robot)
        pending=next_pending
        if not pending:
            break
    pairs=tuple(sorted(((robot,task) for robot,task in executed.items()),
                       key=lambda x:(x[1],x[0])))
    locked_pairs=tuple(sorted(((robot,task) for task,robot in reserved.items()),
                              key=lambda x:(x[1],x[0])))
    validate_one_to_one_commits(pairs)
    validate_one_to_one_commits(locked_pairs)
    if (any(robot in blocked for robot,_task in pairs)
            or any(event.phase not in (
                "owner_request","owner_request_ack",
                "owner_decision","owner_decision_ack")
                + (("execution_announce",) if repetitions else ())
                for event in events)
            or any(reserved.get(task)!=robot for robot,task in pairs)
            or (repetitions and
                (len(announced_executions)!=len(pairs)
                 or set(announced_executions)!=set(pairs)
                 or sum(e.phase=="execution_announce" for e in events)
                    !=len(pairs)*repetitions))):
        raise ProtocolError(Diagnostic(
            owner=OWNER,function="coordinate_p2m_task_owners",
            category="safety",code="P2M_INVALID_RESERVED_EXECUTION",
            expected="each execution backed by a unique owner reservation and "
                     "physically delivered GRANT; original four owner unicast "
                     "phases plus optional three-copy P2NX only after GRANT",
            actual={"executed":pairs,"reserved":locked_pairs,
                    "blocked":sorted(blocked),
                    "phases":sorted({e.phase for e in events})},
        ))
    if len(pairs)<tasks and first_error is None:
        first_error=Diagnostic(
            owner=OWNER,function="coordinate_p2m_task_owners",
            category="planning",code="P2M_TASK_OWNER_ALLOCATION_INCOMPLETE",
            expected=tasks,actual=len(pairs),
            details=f"rounds={rounds}, blocked={len(blocked)}, "
                    f"reserved={len(locked_pairs)}",
        )
    return P2MTaskOwnerResult(
        executed_pairs=pairs,reserved_pairs=locked_pairs,
        events=tuple(events),deliveries=tuple(deliveries),
        rounds_executed=rounds,conflicted_task_rounds=conflicts,
        reassignment_requests=reassignments,
        request_receipt_ack_timeouts=request_ack_timeouts,
        blocked_robot_ids=tuple(sorted(blocked)),
        owner_decisions=tuple(owner_decisions),
        finish_ms=clock,first_diagnostic=first_error,
        announced_executions=tuple(announced_executions),
        recipient_seen_executing_tasks=(
            tuple(tuple(sorted(tasks)) for tasks in seen_executing)
            if repetitions else ()),
        avoided_announced_requests=avoided_announced_requests,
        timing_mode=timing_mode,
        request_window_total_ms=request_window_total,
        decision_window_total_ms=decision_window_total,
        timeout_wait_total_ms=timeout_wait_total,
        last_first_grant_arrival_ms=last_first_grant_arrival,
    )


# P2R is a NEW opt-in announcement protocol in the EXISTING ownership
# owner module. No new Cost/Vote optimizer, hidden global matching, or
# copy of P2M's CLAIM/ACK transaction machinery is introduced.
_P2R_CHALLENGE_WIRE = struct.Struct("<4sIII")  # 16B


@dataclass(frozen=True)
class P2RAnnouncementResult:
    executed_pairs: tuple[tuple[int, int], ...]
    reserved_pairs: tuple[tuple[int, int], ...]
    events: tuple[CommunicationEvent, ...]
    deliveries: tuple[DeliveryObservation, ...]
    rounds_executed: int
    owner_observed_conflicts: int
    peer_observed_challenges: int
    challenge_deferrals: int
    denial_receipts: int
    retargeted_intents: int
    intents_seen_by_owner: int
    decisions: tuple[dict, ...]
    recipient_seen_executing_tasks: tuple[tuple[int, ...], ...]
    finish_ms: float
    first_diagnostic: Diagnostic | None

    @property
    def sender_bytes(self) -> int:
        return sum(event.payload_bytes for event in self.events)


def validate_p2r_announcement_scope(
    *, run: P2KLocalVoteResult, cost_matrix: tuple[tuple[float, ...], ...],
    votes_per_voter: int, p_loss: float, max_rounds: int,
    intent_repetitions: int, decision_repetitions: int,
    announcement_repetitions: int,
) -> tuple[int, int]:
    """One data/contract boundary; vote contents remain sender-private."""
    robots,tasks=validate_cost_matrix(cost_matrix)
    validate_packet_loss_probability(p_loss)
    if (not 1 <= tasks <= robots <= 255
            or type(votes_per_voter) is not int
            or not tasks <= votes_per_voter <= 1184
            or votes_per_voter % tasks
            or type(max_rounds) is not int or not 1 <= max_rounds <= 255
            or any(type(n) is not int or not 1 <= n <= 5
                   for n in (intent_repetitions,decision_repetitions,
                             announcement_repetitions))
            or len(run.local_vote_views)!=robots
            or len(run.local_assignments)!=robots
            or len(run.cost_visible_rows)!=robots
            or any(len(view)!=robots or
                   any(len(row)!=tasks for row in view)
                   for view in run.local_vote_views)
            or any(event.phase not in ("cost","vote") for event in run.events)
            or len({r for r,_task in run.robot_claims})!=len(run.robot_claims)
            or any(type(r) is not int or not 0<=r<robots
                   or type(task) is not int or not 0<=task<tasks
                   for r,task in run.robot_claims)):
        raise ProtocolError(Diagnostic(
            owner=OWNER,function="validate_p2r_announcement_scope",
            category="contract",code="P2R_INVALID_ANNOUNCEMENT_SCOPE",
            expected="native P2Q 1000-ticket Cost/Vote-only epoch; "
                     "capacity1; rounds 1..255; repetitions 1..5",
            actual={"robots":robots,"tasks":tasks,
                    "votes":votes_per_voter,"rounds":max_rounds,
                    "intent_copies":intent_repetitions,
                    "decision_copies":decision_repetitions,
                    "executing_copies":announcement_repetitions},
        ))
    return robots,tasks


def encode_p2r_intent(intent: P2LClaim) -> bytes:
    """Same validated local support fields as P2L but NEW 28B INTENT tag."""
    return b"P2RI"+encode_p2l_claim_packet(intent)[4:]


def decode_p2r_intent(
    packet: bytes, *, sender_id: int, claim_round: int,
    robots: int, tasks: int, tickets_per_task: int,
) -> P2LClaim:
    """Only a directly delivered, sender-owned INTENT can be a candidate."""
    if not isinstance(packet,bytes) or len(packet)!=CLAIM_WIRE.size:
        raise ProtocolError(Diagnostic(
            owner=OWNER,function="decode_p2r_intent",
            category="data",code="P2R_INVALID_INTENT_PACKET",
            expected=CLAIM_WIRE.size,actual=(
                len(packet) if isinstance(packet,bytes) else type(packet).__name__),
        ))
    if packet[:4]!=b"P2RI":
        raise ProtocolError(Diagnostic(
            owner=OWNER,function="decode_p2r_intent",
            category="contract",code="P2R_WRONG_INTENT_TAG",
            expected="P2RI",actual=packet[:4],
        ))
    return decode_p2l_claim_packet(
        b"P2LC"+packet[4:],claim_round=claim_round,
        sender_id=sender_id,tasks=tasks,robots=robots,
        tickets_per_task=tickets_per_task,
    )


def encode_p2r_challenge(
    *, round_id: int, challenger: int, task_id: int,
) -> bytes:
    """One unicast conflict alert; advisory ONLY, never winner authority."""
    if any(type(x) is not int or not 0 <= x <= 0xffffffff
           for x in (round_id,challenger,task_id)):
        raise ProtocolError(Diagnostic(
            owner=OWNER,function="encode_p2r_challenge",
            category="data",code="P2R_INVALID_CHALLENGE",
            expected="nonnegative uint32 round/challenger/task",
            actual=(round_id,challenger,task_id),
        ))
    return _P2R_CHALLENGE_WIRE.pack(
        b"P2RH",round_id,challenger,task_id,
    )


def decode_p2r_challenge(
    packet: bytes, *, sender_id: int, task_id: int,
    claim_round: int, robots: int, tasks: int,
) -> None:
    """Alert cannot be spoofed into an allocation, even if delivered."""
    if (not isinstance(packet,bytes) or
            len(packet)!=_P2R_CHALLENGE_WIRE.size or
            _P2R_CHALLENGE_WIRE.unpack(packet)!=(
                b"P2RH",claim_round,sender_id,task_id) or
            not 0 <= sender_id < robots or
            not 0 <= task_id < tasks):
        raise ProtocolError(Diagnostic(
            owner=OWNER,function="decode_p2r_challenge",
            category="contract",code="P2R_CHALLENGE_IDENTITY_MISMATCH",
            expected=("P2RH",claim_round,sender_id,task_id),
            actual=packet,
        ))


def encode_p2r_owner_response(
    *, round_id: int, owner_id: int, robot_id: int,
    task_id: int, commit: bool,
) -> bytes:
    """20B original validated P2M fields; P2RC/P2RD are NOT P2MD."""
    packet=encode_p2m_owner_decision(
        round_id=round_id,owner_id=owner_id,
        robot_id=robot_id,task_id=task_id,granted=commit,
    )
    return (b"P2RC" if commit else b"P2RD")+packet[4:]


def decode_p2r_owner_response(
    packet: bytes, *, sender_id: int, robot_id: int, task_id: int,
    claim_round: int, robots: int,
) -> bool:
    """Actual physical sender must be task's one fixed safety owner."""
    if not isinstance(packet,bytes) or len(packet)!=_OWNER_DECISION_WIRE.size:
        raise ProtocolError(Diagnostic(
            owner=OWNER,function="decode_p2r_owner_response",
            category="data",code="P2R_INVALID_RESPONSE_PACKET",
            expected=_OWNER_DECISION_WIRE.size,
            actual=(len(packet) if isinstance(packet,bytes)
                    else type(packet).__name__),
        ))
    tag=packet[:4]
    if tag not in (b"P2RC",b"P2RD"):
        raise ProtocolError(Diagnostic(
            owner=OWNER,function="decode_p2r_owner_response",
            category="contract",code="P2R_INVALID_RESPONSE_TAG",
            expected=("P2RC","P2RD"),actual=tag,
        ))
    owner=p2m_task_owner_id(task_id=task_id,robots=robots)
    if sender_id!=owner:
        raise ProtocolError(Diagnostic(
            owner=OWNER,function="decode_p2r_owner_response",
            category="safety",code="P2R_NOT_FIXED_OWNER",
            expected=owner,actual=sender_id,
        ))
    received=decode_p2m_owner_decision(
        b"P2MD"+packet[4:],
        round_id=claim_round,owner_id=sender_id,
        robot_id=robot_id,task_id=task_id,robots=robots,
    )
    if received!=(tag==b"P2RC"):
        raise ProtocolError(Diagnostic(
            owner=OWNER,function="decode_p2r_owner_response",
            category="contract",code="P2R_RESPONSE_FLAG_MISMATCH",
            expected=(tag==b"P2RC"),actual=received,
        ))
    return received


def transmit_p2r_intent_window(
    *, intents: tuple[P2LClaim, ...],
    robots: int, tasks: int, votes_per_voter: int,
    repetitions: int, start_ms: float,
    sampler, loss_sampler, p_loss: float,
) -> tuple[list[CommunicationEvent],list[DeliveryObservation],
           dict[int,list[P2LClaim]],dict[int,set[int]],float]:
    """Physical P2RI broadcasts; each receiver learns ONLY its receipts.

    Return the task owner's own observed candidate set and each
    contender's locally observed other contenders, never global votes.
    """
    copies=[]
    for intent in sorted(intents,key=lambda x:x.robot_id):
        if intent.task_id is None:
            continue
        for copy in range(repetitions):
            copies.append((intent,copy))
    events=[]
    observations=[]
    owner_receipts:dict[int,dict[int,P2LClaim]]={}
    heard_by_robot:dict[int,dict[int,set[int]]]={}
    finish=start_ms
    for intent,copy in copies:
        task=intent.task_id
        wire=encode_p2r_intent(intent)
        event=_broadcast_event(
            phase="p2r_intent",sender_id=intent.robot_id,
            task_id=task,round_id=intent.claim_round+1,
            send_time_ms=start_ms,payload_bytes=len(wire),
            sampler=sampler,transmission_index=copy,
        )
        events.append(event)
        finish=max(finish,event.arrival_time_ms)
        observed=_lossy_broadcast_deliveries(
            event=event,num_robots=robots,
            loss_sampler=loss_sampler,p_loss=p_loss,
            round_id=intent.claim_round+1,
        )
        observations.extend(observed)
        # The sending robot knows its own local INTENT without radio receipt.
        heard_by_robot.setdefault(intent.robot_id,{}).setdefault(
            task,set()).add(intent.robot_id)
        owner=p2m_task_owner_id(task_id=task,robots=robots)
        if intent.robot_id==owner:
            owner_receipts.setdefault(task,{})[intent.robot_id]=intent
        for obs in observed:
            if not obs.delivered:
                continue
            decoded=decode_p2r_intent(
                wire,sender_id=intent.robot_id,
                claim_round=intent.claim_round,robots=robots,
                tasks=tasks,tickets_per_task=votes_per_voter//tasks,
            )
            heard_by_robot.setdefault(obs.receiver_id,{}).setdefault(
                task,set()).add(decoded.robot_id)
            if obs.receiver_id==owner:
                owner_receipts.setdefault(task,{})[decoded.robot_id]=decoded
    return (
        events,observations,
        {task:list(claims.values()) for task,claims in owner_receipts.items()},
        {robot:by_task.get(next(
            (intent.task_id for intent in intents
             if intent.robot_id==robot),-1),set())
         for robot,by_task in heard_by_robot.items()},
        finish,
    )


def transmit_p2r_conflict_challenges(
    *, intents: tuple[P2LClaim, ...],
    peer_seen: dict[int,set[int]], robots: int, tasks: int,
    start_ms: float,sampler,loss_sampler,p_loss: float,
) -> tuple[list[CommunicationEvent],list[DeliveryObservation],
           set[int],int,float]:
    """ONLY a contestant who personally saw a rival emits an alert."""
    events=[]
    deliveries=[]
    owner_alerts=set()
    challenge_count=0
    finish=start_ms
    for intent in sorted(intents,key=lambda x:x.robot_id):
        task=intent.task_id
        if task is None:
            continue
        local=peer_seen.get(intent.robot_id,set())
        if len(local)<2 or intent.robot_id not in local:
            continue
        owner=p2m_task_owner_id(task_id=task,robots=robots)
        if owner==intent.robot_id:
            # Fixed owner already knows its own received competing INTENT.
            owner_alerts.add(task)
            continue
        wire=encode_p2r_challenge(
            round_id=intent.claim_round,challenger=intent.robot_id,
            task_id=task,
        )
        event=_unicast_event(
            phase="p2r_challenge",sender_id=intent.robot_id,
            receiver_id=owner,task_id=task,round_id=intent.claim_round+1,
            send_time_ms=start_ms,payload_bytes=len(wire),sampler=sampler,
        )
        events.append(event)
        finish=max(finish,event.arrival_time_ms)
        obs=_lossy_unicast_delivery(
            event=event,loss_sampler=loss_sampler,p_loss=p_loss,
            round_id=intent.claim_round+1,
        )
        deliveries.append(obs)
        challenge_count+=1
        if obs.delivered:
            decode_p2r_challenge(
                wire,sender_id=intent.robot_id,task_id=task,
                claim_round=intent.claim_round,robots=robots,tasks=tasks,
            )
            owner_alerts.add(task)
    return events,deliveries,owner_alerts,challenge_count,finish


def choose_p2r_owner_responses(
    *, owner_receipts: dict[int,list[P2LClaim]],
    owner_alerts: set[int], reserved: dict[int,int],
    previously_deferred: set[int], robots: int,
    claim_round: int,
) -> tuple[list[tuple[int,int,bool]],list[dict],set[int],int]:
    """Only REAL owner-received INTENTs can compete and reserve a task.

    A delivered peer CHALLENGE is advisory; if owner knows only one
    candidate it may defer ONE round to gather more evidence. It can
    NEVER nominate an unreceived or fabricated contestant.
    """
    responses=[]
    decisions=[]
    deferrals=set()
    conflicts=0
    for task,claims in sorted(owner_receipts.items()):
        owner=p2m_task_owner_id(task_id=task,robots=robots)
        if len({c.robot_id for c in claims})!=len(claims):
            raise ProtocolError(Diagnostic(
                owner=OWNER,function="choose_p2r_owner_responses",
                category="contract",code="P2R_DUPLICATE_OWNER_INTENT",
                expected="deduplicated one INTENT per robot/task/round",
                actual={"task":task,"robots":[c.robot_id for c in claims]},
            ))
        existing=reserved.get(task)
        if existing is None:
            if (len(claims)==1 and task in owner_alerts
                    and task not in previously_deferred):
                deferrals.add(task)
                decisions.append({
                    "round":claim_round,"task":task,"owner":owner,
                    "status":"DEFER_CHALLENGE","received":[c.robot_id for c in claims],
                })
                continue
            winners,losers,collided=resolve_p2l_claim_conflicts(
                claims=tuple(claims),locked_tasks=frozenset(),
            )
            if len(winners)!=1 or winners[0][1]!=task:
                raise ProtocolError(Diagnostic(
                    owner=OWNER,function="choose_p2r_owner_responses",
                    category="contract",code="P2R_INVALID_OWNER_WINNER",
                    expected={"task":task,"winner_count":1},
                    actual=winners,
                ))
            winner=winners[0][0]
            reserved[task]=winner
            conflicts+=collided
        else:
            winner=existing
            losers=tuple(c.robot_id for c in claims if c.robot_id!=winner)
            if len(claims)>1:
                conflicts+=1
        decisions.append({
            "round":claim_round,"task":task,"owner":owner,
            "status":"CONFLICT" if len(claims)>1 else "SOLO",
            "received":[{"robot":c.robot_id,
                         "support":c.support_votes,
                         "ballots":c.received_ballots}
                        for c in claims],
            "reserved_winner":winner,"previously_reserved":existing is not None,
        })
        for claim in claims:
            responses.append((claim.robot_id,task,claim.robot_id==winner))
    return responses,decisions,deferrals,conflicts


def transmit_p2r_owner_responses(
    *, responses: tuple[tuple[int,int,bool], ...],
    claim_round: int, robots: int, repetitions: int,
    start_ms: float,sampler,loss_sampler,p_loss: float,
) -> tuple[list[CommunicationEvent],list[DeliveryObservation],
           dict[int,tuple[int,bool]],float]:
    """COMMIT for reserved winner, DENY only owner-seen rival/locked intent.

    No ACK stage: sender repeats up to fixed repetitions. The owner
    keeps its irreversible task reservation if all COMMIT copies drop.
    """
    events=[]
    deliveries=[]
    received={}
    finish=start_ms
    for robot,task,commit in sorted(responses,key=lambda x:(x[1],x[0])):
        owner=p2m_task_owner_id(task_id=task,robots=robots)
        wire=encode_p2r_owner_response(
            round_id=claim_round,owner_id=owner,
            robot_id=robot,task_id=task,commit=commit,
        )
        if robot==owner:
            actually_committed=decode_p2r_owner_response(
                wire,sender_id=owner,robot_id=robot,
                task_id=task,claim_round=claim_round,robots=robots,
            )
            received[robot]=(task,actually_committed)
            continue
        for copy in range(repetitions):
            phase="p2r_commit" if commit else "p2r_deny"
            event=_unicast_event(
                phase=phase,sender_id=owner,
                receiver_id=robot,task_id=task,round_id=claim_round+1,
                send_time_ms=start_ms,payload_bytes=len(wire),sampler=sampler,
                transmission_index=copy,
            )
            events.append(event)
            finish=max(finish,event.arrival_time_ms)
            obs=_lossy_unicast_delivery(
                event=event,loss_sampler=loss_sampler,p_loss=p_loss,
                round_id=claim_round+1,
            )
            deliveries.append(obs)
            if obs.delivered:
                actually_committed=decode_p2r_owner_response(
                    wire,sender_id=owner,robot_id=robot,
                    task_id=task,claim_round=claim_round,robots=robots,
                )
                if robot in received and received[robot]!=(task,actually_committed):
                    raise ProtocolError(Diagnostic(
                        owner=OWNER,function="transmit_p2r_owner_responses",
                        category="safety",code="P2R_CONFLICTING_OWNER_DECISIONS",
                        expected=received[robot],
                        actual=(task,actually_committed),
                    ))
                received[robot]=(task,actually_committed)
    return events,deliveries,received,finish


def transmit_p2r_execution_announcements(
    *, newly_executed: tuple[tuple[int,int],...], claim_round: int,
    robots: int, tasks: int, repetitions: int,
    start_ms: float,sampler,loss_sampler,p_loss: float,
) -> tuple[list[CommunicationEvent],list[DeliveryObservation],
           dict[int,set[int]],float]:
    """P2NX only for physically COMMIT-receiving executors."""
    events=[]
    deliveries=[]
    known={}
    finish=start_ms
    for robot,task in sorted(newly_executed):
        wire=encode_p2n_execution_announcement(
            claim_round=claim_round,robot_id=robot,
            task_id=task,robots=robots,
        )
        known.setdefault(robot,set()).add(task)
        for copy in range(repetitions):
            event=_broadcast_event(
                phase="execution_announce",sender_id=robot,
                task_id=task,round_id=claim_round+1,
                send_time_ms=start_ms,payload_bytes=len(wire),
                sampler=sampler,transmission_index=copy,
            )
            events.append(event)
            finish=max(finish,event.arrival_time_ms)
            observed=_lossy_broadcast_deliveries(
                event=event,num_robots=robots,
                loss_sampler=loss_sampler,p_loss=p_loss,
                round_id=claim_round+1,
            )
            deliveries.extend(observed)
            for obs in observed:
                if obs.delivered:
                    decode_p2n_execution_announcement(
                        wire,claim_round=claim_round,
                        sender_id=robot,task_id=task,
                        robots=robots,tasks=tasks,
                    )
                    known.setdefault(obs.receiver_id,set()).add(task)
    return events,deliveries,known,finish


def select_p2r_local_intent_task(
    *, run:P2KLocalVoteResult, robot_id:int,
    own_cost_row:tuple[float,...], tried:frozenset[int],
    known_executing:frozenset[int], first_attempt:bool,
    active_task:int|None,
) -> int|None:
    """A robot cannot request another task while its INTENT is unresolved.

    A real received P2NX may eliminate an outstanding tentative
    intent. The robot changes target otherwise ONLY on actual DENY.
    """
    if active_task is not None and active_task not in (tried | known_executing):
        return active_task
    return select_p2m_local_request_task(
        run=run,robot_id=robot_id,own_cost_row=own_cost_row,
        tried_tasks=tried,first_attempt=first_attempt,
        known_executing_tasks=known_executing,
    )


def validate_p2r_unique_execution(
    *, reserved:dict[int,int],executed:dict[int,int],
    events:tuple[CommunicationEvent,...], rounds:int,
) -> None:
    """Safety gate: only true irreversible owner COMMIT can execute."""
    pairs=tuple((robot,task) for robot,task in executed.items())
    validate_one_to_one_commits(pairs)
    validate_one_to_one_commits(tuple(
        (robot,task) for task,robot in reserved.items()
    ))
    if (any(reserved.get(task)!=robot for robot,task in pairs)
            or any(event.phase not in (
                "p2r_intent","p2r_challenge","p2r_commit",
                "p2r_deny","execution_announce",
            ) for event in events)):
        raise ProtocolError(Diagnostic(
            owner=OWNER,function="validate_p2r_unique_execution",
            category="safety",code="P2R_UNAUTHORISED_EXECUTION",
            expected="every actual executor receives unique task-owner COMMIT "
                     "and every physical phase is explicitly permitted",
            actual={"reserved":reserved,"executed":executed,
                    "phases":sorted({e.phase for e in events}),
                    "rounds":rounds},
        ))


def coordinate_p2r_announced_intents(
    *, run:P2KLocalVoteResult,cost_matrix:tuple[tuple[float,...],...],
    votes_per_voter:int,sampler,loss_sampler,p_loss:float,
    max_rounds:int=101,intent_repetitions:int=3,
    decision_repetitions:int=3,announcement_repetitions:int=3,
) -> P2RAnnouncementResult:
    """ONE P2R task-ownership lifecycle in the existing real owner module.

    This is not a second copy of P2M's CLAIM/ACK/GRANT state machine:
    it uses public one-to-one Task Owner authorization but new
    P2RI broadcast, contestant-only P2RH, P2RC/P2RD only where
    physically received P2RI exists, and P2NX after actual COMMIT.
    Only the robot's OWN P2Q private vote view can nominate a task;
    only real owner-received intents can reserve it. Lack of a
    response leads to repeating the SAME intent, not moving to a
    new task (prevents multiple hidden task reservations per robot).
    """
    robots,tasks=validate_p2r_announcement_scope(
        run=run,cost_matrix=cost_matrix,
        votes_per_voter=votes_per_voter,p_loss=p_loss,
        max_rounds=max_rounds,intent_repetitions=intent_repetitions,
        decision_repetitions=decision_repetitions,
        announcement_repetitions=announcement_repetitions,
    )
    pending=set(range(robots))
    tried=[set() for _ in range(robots)]
    active:dict[int,int]={}
    seen_executing=[set() for _ in range(robots)]
    reserved:dict[int,int]={}  # one fixed owner's irreversible reservations
    executed:dict[int,int]={}  # only delivered authentic P2RC
    previously_deferred=set()
    events=[]
    deliveries=[]
    decisions=[]
    finish=max(run.decision_time_ms,
               max((e.arrival_time_ms for e in run.events),default=0.0))
    conflicts=0
    challenges=0
    deferred_count=0
    denial_receipts=0
    retargets=0
    received_intents=0
    first_diagnostic=None
    rounds=0
    for claim_round in range(max_rounds):
        if not pending or len(executed)>=tasks:
            break
        round_intents=[]
        rounds+=1
        for robot in sorted(pending):
            # Actual, per-robot P2NX delivery cache only.
            if robot in active and active[robot] in seen_executing[robot]:
                tried[robot].add(active.pop(robot))
            old_task=active.get(robot)
            task=select_p2r_local_intent_task(
                run=run,robot_id=robot,own_cost_row=cost_matrix[robot],
                tried=frozenset(tried[robot]),
                known_executing=frozenset(seen_executing[robot]),
                first_attempt=robot not in active and not tried[robot]
                              and claim_round==0,
                active_task=active.get(robot),
            )
            if task is None:
                # Incomplete is a real observable outcome, not a
                # model-assisted search for globally unclaimed tasks.
                continue
            if old_task is not None and old_task!=task:
                retargets+=1
            active[robot]=task
            round_intents.append(make_p2l_claim(
                run=run,robot_id=robot,task_id=task,
                claim_round=claim_round,votes_per_voter=votes_per_voter,
            ))
        if not round_intents:
            break
        packet_events,packet_deliveries,by_owner,peer_seen,finish=(
            transmit_p2r_intent_window(
                intents=tuple(round_intents),robots=robots,tasks=tasks,
                votes_per_voter=votes_per_voter,
                repetitions=intent_repetitions,start_ms=finish,
                sampler=sampler,loss_sampler=loss_sampler,p_loss=p_loss,
            )
        )
        events.extend(packet_events)
        deliveries.extend(packet_deliveries)
        received_intents+=sum(len(v) for v in by_owner.values())
        ch_events,ch_deliveries,alerts,challenge_count,finish=(
            transmit_p2r_conflict_challenges(
                intents=tuple(round_intents),peer_seen=peer_seen,
                robots=robots,tasks=tasks,start_ms=finish,
                sampler=sampler,loss_sampler=loss_sampler,p_loss=p_loss,
            )
        )
        events.extend(ch_events)
        deliveries.extend(ch_deliveries)
        challenges+=challenge_count
        responses,owner_decisions,deferred,collisions=(
            choose_p2r_owner_responses(
                owner_receipts=by_owner,owner_alerts=alerts,
                reserved=reserved,previously_deferred=previously_deferred,
                robots=robots,claim_round=claim_round,
            )
        )
        decisions.extend(owner_decisions)
        conflicts+=collisions
        deferred_count+=len(deferred)
        previously_deferred.update(deferred)
        response_events,response_deliveries,actual_responses,finish=(
            transmit_p2r_owner_responses(
                responses=tuple(responses),claim_round=claim_round,
                robots=robots,repetitions=decision_repetitions,
                start_ms=finish,sampler=sampler,loss_sampler=loss_sampler,
                p_loss=p_loss,
            )
        )
        events.extend(response_events)
        deliveries.extend(response_deliveries)
        newly_executed=[]
        for robot,(task,committed) in sorted(actual_responses.items()):
            if active.get(robot)!=task:
                raise ProtocolError(Diagnostic(
                    owner=OWNER,function="coordinate_p2r_announced_intents",
                    category="state",code="P2R_STALE_DECISION_FOR_DIFFERENT_TASK",
                    expected=active.get(robot),
                    actual={"robot":robot,"decision_task":task},
                ))
            if committed:
                if (reserved.get(task)!=robot or
                        (robot in executed and executed[robot]!=task)):
                    raise ProtocolError(Diagnostic(
                        owner=OWNER,function="coordinate_p2r_announced_intents",
                        category="safety",code="P2R_COMMIT_NOT_RESERVED",
                        expected={"owner_reservation":(task,robot),
                                  "robot_single_task":True},
                        actual={"reserved":reserved.get(task),
                                "robot":robot,"prior":executed.get(robot)},
                    ))
                if robot not in executed:
                    executed[robot]=task
                    newly_executed.append((robot,task))
                pending.discard(robot)
                active.pop(robot,None)
            else:
                denial_receipts+=1
                tried[robot].add(task)
                active.pop(robot,None)
        announce_events,announce_deliveries,known,finish=(
            transmit_p2r_execution_announcements(
                newly_executed=tuple(newly_executed),
                claim_round=claim_round,robots=robots,tasks=tasks,
                repetitions=announcement_repetitions,
                start_ms=finish,sampler=sampler,
                loss_sampler=loss_sampler,p_loss=p_loss,
            )
        )
        events.extend(announce_events)
        deliveries.extend(announce_deliveries)
        for robot,received in known.items():
            seen_executing[robot].update(received)
        if len(executed)>=tasks:
            break
    validate_p2r_unique_execution(
        reserved=reserved,executed=executed,
        events=tuple(events),rounds=rounds,
    )
    pairs=tuple(sorted(
        ((robot,task) for robot,task in executed.items()),
        key=lambda x:(x[1],x[0]),
    ))
    reserved_pairs=tuple(sorted(
        ((robot,task) for task,robot in reserved.items()),
        key=lambda x:(x[1],x[0]),
    ))
    if len(pairs)!=tasks:
        unreached=tuple(sorted(task for task in range(tasks)
                               if task not in reserved))
        undelivered=tuple(sorted(task for task,robot in reserved.items()
                                 if executed.get(robot)!=task))
        first_diagnostic=Diagnostic(
            owner=OWNER,function="coordinate_p2r_announced_intents",
            category="time" if undelivered else "planning",
            code=("P2R_COMMIT_NOT_DELIVERED" if undelivered else
                  "P2R_INCOMPLETE_AFTER_ROUNDS"),
            expected={"executed_tasks":tasks,"duplicated_tasks":0},
            actual={"executed":len(executed),"reserved":len(reserved),
                    "missing_owner_intents":unreached,
                    "reserved_but_not_executed":undelivered,
                    "rounds":rounds},
            details="No silence-as-approval, no oracle task replacement.",
        )
    return P2RAnnouncementResult(
        executed_pairs=pairs,reserved_pairs=reserved_pairs,
        events=tuple(events),deliveries=tuple(deliveries),
        rounds_executed=rounds,owner_observed_conflicts=conflicts,
        peer_observed_challenges=challenges,
        challenge_deferrals=deferred_count,
        denial_receipts=denial_receipts,
        retargeted_intents=retargets,
        intents_seen_by_owner=received_intents,
        decisions=tuple(decisions),
        recipient_seen_executing_tasks=tuple(
            tuple(sorted(known)) for known in seen_executing
        ),
        finish_ms=finish,first_diagnostic=first_diagnostic,
    )


# P2T: peer-only experiment.  This is intentionally NOT a P2R task-owner
# grant/deny protocol.  It simulates direct peer choice and audits unsafe
# collisions instead of secretly obtaining a global winner.

P2T_INTENT_WIRE = struct.Struct("<4sIIIIIId")  # 36B: P2L support plus own cost
P2T_EXECUTION_WIRE = struct.Struct("<4sIII")  # 16B: round, sender, task


@dataclass(frozen=True)
class P2TIntent:
    claim: P2LClaim
    own_cost: float


@dataclass(frozen=True)
class P2TPeerResult:
    """Tentative peer actions, NOT authenticated real-robot execution grants."""

    attempted_pairs: tuple[tuple[int, int], ...]
    events: tuple[CommunicationEvent, ...]
    deliveries: tuple[DeliveryObservation, ...]
    rounds_executed: int
    locally_observed_conflicts: int
    yielded_candidates: int
    retargeted_intents: int
    initial_candidate_count: int
    unique_task_count: int
    duplicate_task_count: int
    unassigned_task_count: int
    recipient_seen_executing_tasks: tuple[tuple[int, ...], ...]
    finish_ms: float
    first_diagnostic: Diagnostic | None = None

    @property
    def sender_bytes(self) -> int:
        return sum(event.payload_bytes for event in self.events)


def validate_p2t_peer_scope(
    *, run: P2KLocalVoteResult, cost_matrix: tuple[tuple[float, ...], ...],
    votes_per_voter: int, p_loss: float, max_rounds: int,
    intent_repetitions: int, announcement_repetitions: int,
) -> tuple[int, int]:
    """The Cost/Vote source is native; a P2T peer cannot read unknown rows."""
    robots, tasks = validate_cost_matrix(cost_matrix)
    validate_packet_loss_probability(p_loss)
    if (not 1 <= tasks <= robots <= 255
            or type(votes_per_voter) is not int
            or not tasks <= votes_per_voter <= 1184
            or votes_per_voter % tasks
            or type(max_rounds) is not int or not 1 <= max_rounds <= 255
            or type(intent_repetitions) is not int
            or not 1 <= intent_repetitions <= 5
            or type(announcement_repetitions) is not int
            or not 1 <= announcement_repetitions <= 5
            or len(run.local_vote_views) != robots
            or len(run.local_assignments) != robots
            or len(run.cost_visible_rows) != robots
            or any(len(view) != robots or
                   any(len(row) != tasks for row in view)
                   for view in run.local_vote_views)
            or any(event.phase not in ("cost", "vote") for event in run.events)
            or len({robot for robot, _ in run.robot_claims}) != len(run.robot_claims)
            or any(type(robot) is not int or not 0 <= robot < robots
                   or type(task) is not int or not 0 <= task < tasks
                   for robot, task in run.robot_claims)):
        raise ProtocolError(Diagnostic(
            owner=OWNER, function="validate_p2t_peer_scope",
            category="contract", code="P2T_INVALID_PEER_SCOPE",
            expected="native Cost/Vote-only per-receiver views, capacity one, "
                     "1..5 intent/execution copies, 1..255 rounds",
            actual={"robots":robots, "tasks":tasks,
                    "votes":votes_per_voter, "rounds":max_rounds,
                    "intent_copies":intent_repetitions,
                    "execution_copies":announcement_repetitions},
        ))
    return robots, tasks


def encode_p2t_peer_intent(intent: P2TIntent) -> bytes:
    """Send own rational vote support AND own task cost, never peer Cost rows."""
    claim = intent.claim
    validated = encode_p2l_claim_packet(claim)
    if (type(intent.own_cost) not in (float, int)
            or not math.isfinite(intent.own_cost) or intent.own_cost < 0
            or claim.task_id is None):
        raise ProtocolError(Diagnostic(
            owner=OWNER, function="encode_p2t_peer_intent",
            category="data", code="P2T_INVALID_OWN_COST",
            expected="finite nonnegative own task cost and non-idle claim",
            actual={"claim":repr(claim), "cost":intent.own_cost},
        ))
    _tag, rnd, robot, task, votes, receipts, slots = CLAIM_WIRE.unpack(validated)
    return P2T_INTENT_WIRE.pack(
        b"P2TI", rnd, robot, task, votes, receipts, slots, intent.own_cost,
    )


def decode_p2t_peer_intent(
    wire: bytes, *, sender_id: int, claim_round: int,
    robots: int, tasks: int, tickets_per_task: int,
) -> P2TIntent:
    if not isinstance(wire, bytes) or len(wire) != P2T_INTENT_WIRE.size:
        raise ProtocolError(Diagnostic(
            owner=OWNER, function="decode_p2t_peer_intent",
            category="data", code="P2T_INTENT_SIZE_INVALID",
            expected=P2T_INTENT_WIRE.size,
            actual=len(wire) if isinstance(wire, bytes) else type(wire).__name__,
        ))
    tag, rnd, robot, task, votes, receipts, slots, own_cost = (
        P2T_INTENT_WIRE.unpack(wire)
    )
    if tag != b"P2TI" or not math.isfinite(own_cost) or own_cost < 0:
        raise ProtocolError(Diagnostic(
            owner=OWNER, function="decode_p2t_peer_intent",
            category="contract", code="P2T_INTENT_TAG_OR_COST_INVALID",
            expected="P2TI, finite own cost >= 0",
            actual={"tag":tag, "own_cost":own_cost},
        ))
    claim = decode_p2l_claim_packet(
        CLAIM_WIRE.pack(b"P2LC", rnd, robot, task, votes, receipts, slots),
        claim_round=claim_round, sender_id=sender_id,
        robots=robots, tasks=tasks, tickets_per_task=tickets_per_task,
    )
    if claim.task_id is None:
        raise ProtocolError(Diagnostic(
            owner=OWNER, function="decode_p2t_peer_intent",
            category="contract", code="P2T_IDLE_INTENT_ON_WIRE",
            expected="actual selected task", actual=None,
        ))
    return P2TIntent(claim=claim, own_cost=own_cost)


def transmit_p2t_peer_intents(
    *, intents: tuple[P2TIntent, ...], robots: int, tasks: int,
    votes_per_voter: int, repetitions: int, start_ms: float,
    sampler, loss_sampler, p_loss: float,
) -> tuple[list[CommunicationEvent], list[DeliveryObservation],
           dict[int, dict[int, P2TIntent]], float]:
    """Real per-recipient physical P2TI broadcasts; no fixed task owner.

    Every sender knows its own payload for free, but other offers are
    available ONLY after their P2TI is physically received.
    """
    events: list[CommunicationEvent] = []
    deliveries: list[DeliveryObservation] = []
    received: dict[int, dict[int, P2TIntent]] = {
        intent.claim.robot_id: {intent.claim.robot_id: intent}
        for intent in intents
    }
    finish = start_ms
    for intent in sorted(intents, key=lambda x: x.claim.robot_id):
        claim = intent.claim
        wire = encode_p2t_peer_intent(intent)
        for copy in range(repetitions):
            event = _broadcast_event(
                phase="p2t_intent", sender_id=claim.robot_id,
                task_id=claim.task_id, round_id=claim.claim_round + 1,
                send_time_ms=start_ms, payload_bytes=len(wire),
                sampler=sampler, transmission_index=copy,
            )
            events.append(event)
            finish = max(finish, event.arrival_time_ms)
            observed = _lossy_broadcast_deliveries(
                event=event, num_robots=robots, loss_sampler=loss_sampler,
                p_loss=p_loss, round_id=claim.claim_round + 1,
            )
            deliveries.extend(observed)
            for observation in observed:
                if observation.delivered:
                    decoded = decode_p2t_peer_intent(
                        wire, sender_id=claim.robot_id,
                        claim_round=claim.claim_round, robots=robots,
                        tasks=tasks, tickets_per_task=votes_per_voter // tasks,
                    )
                    received.setdefault(observation.receiver_id, {})[
                        claim.robot_id
                    ] = decoded
    return events, deliveries, received, finish


def choose_p2t_peer_winners(
    *, intents: tuple[P2TIntent, ...],
    locally_received: dict[int, dict[int, P2TIntent]],
) -> tuple[tuple[P2TIntent, ...], tuple[P2TIntent, ...], int]:
    """Each actual candidate compares only same-task P2TI it received.

    Higher normalized local vote support wins; tied ratios use raw vote,
    lower OWN task cost, then lower robot ID.  No shared oracle table.
    """
    winners: list[P2TIntent] = []
    losers: list[P2TIntent] = []
    conflicts = 0

    def rank(intent: P2TIntent) -> tuple:
        claim = intent.claim
        return (
            Fraction(claim.support_votes,
                     max(1, claim.received_ballots * claim.tickets_per_task)),
            claim.support_votes, -intent.own_cost, -claim.robot_id,
        )

    for intent in sorted(intents, key=lambda x: x.claim.robot_id):
        claim = intent.claim
        received = locally_received.get(claim.robot_id, {})
        if received.get(claim.robot_id) != intent:
            raise ProtocolError(Diagnostic(
                owner=OWNER, function="choose_p2t_peer_winners",
                category="state", code="P2T_OWN_INTENT_NOT_VISIBLE",
                expected=repr(intent),
                actual=repr(received.get(claim.robot_id)),
            ))
        contenders = tuple(candidate for candidate in received.values()
                           if candidate.claim.task_id == claim.task_id)
        if len(contenders) > 1:
            conflicts += 1
        best = max(contenders, key=rank)
        (winners if best.claim.robot_id == claim.robot_id else losers).append(intent)
    return tuple(winners), tuple(losers), conflicts


def encode_p2t_execution_notice(*, claim_round: int, robot_id: int,
                                task_id: int) -> bytes:
    if (type(claim_round) is not int or not 0 <= claim_round <= 0xffffffff
            or type(robot_id) is not int or not 0 <= robot_id <= 255
            or type(task_id) is not int or not 0 <= task_id <= 255):
        raise ProtocolError(Diagnostic(
            owner=OWNER, function="encode_p2t_execution_notice",
            category="data", code="P2T_INVALID_EXECUTION_NOTICE",
            expected="uint32 round, uint8 robot/task IDs",
            actual=(claim_round, robot_id, task_id),
        ))
    return P2T_EXECUTION_WIRE.pack(
        b"P2TE", claim_round, robot_id, task_id,
    )


def decode_p2t_execution_notice(
    wire: bytes, *, sender_id: int, claim_round: int,
    robots: int, tasks: int,
) -> int:
    if not isinstance(wire, bytes) or len(wire) != P2T_EXECUTION_WIRE.size:
        raise ProtocolError(Diagnostic(
            owner=OWNER, function="decode_p2t_execution_notice",
            category="data", code="P2T_EXEC_NOTICE_SIZE_INVALID",
            expected=P2T_EXECUTION_WIRE.size,
            actual=len(wire) if isinstance(wire, bytes) else type(wire).__name__,
        ))
    tag, rnd, robot, task = P2T_EXECUTION_WIRE.unpack(wire)
    if (tag != b"P2TE" or rnd != claim_round or robot != sender_id
            or not 0 <= robot < robots or not 0 <= task < tasks):
        raise ProtocolError(Diagnostic(
            owner=OWNER, function="decode_p2t_execution_notice",
            category="contract", code="P2T_EXEC_NOTICE_IDENTITY_MISMATCH",
            expected={"tag":"P2TE","round":claim_round,"sender":sender_id},
            actual={"tag":tag,"round":rnd,"robot":robot,"task":task},
        ))
    return task


def transmit_p2t_execution_notices(
    *, attempted: tuple[tuple[int, int], ...], claim_round: int,
    robots: int, tasks: int, repetitions: int, start_ms: float,
    sampler, loss_sampler, p_loss: float,
) -> tuple[list[CommunicationEvent], list[DeliveryObservation],
           dict[int, set[int]], float]:
    """P2TE is a statement of *attempted* execution, not a safety grant."""
    events: list[CommunicationEvent] = []
    deliveries: list[DeliveryObservation] = []
    observed: dict[int, set[int]] = {}
    finish = start_ms
    for robot, task in sorted(attempted):
        wire = encode_p2t_execution_notice(
            claim_round=claim_round, robot_id=robot, task_id=task,
        )
        observed.setdefault(robot, set()).add(task)
        for copy in range(repetitions):
            event = _broadcast_event(
                phase="p2t_execution", sender_id=robot, task_id=task,
                round_id=claim_round + 1, send_time_ms=start_ms,
                payload_bytes=len(wire), sampler=sampler,
                transmission_index=copy,
            )
            events.append(event)
            finish = max(finish, event.arrival_time_ms)
            delivered_to = _lossy_broadcast_deliveries(
                event=event, num_robots=robots, loss_sampler=loss_sampler,
                p_loss=p_loss, round_id=claim_round + 1,
            )
            deliveries.extend(delivered_to)
            for receipt in delivered_to:
                if receipt.delivered:
                    decoded_task = decode_p2t_execution_notice(
                        wire, sender_id=robot, claim_round=claim_round,
                        robots=robots, tasks=tasks,
                    )
                    observed.setdefault(receipt.receiver_id, set()).add(
                        decoded_task
                    )
    return events, deliveries, observed, finish


def validate_p2t_attempts(
    *, attempts: tuple[tuple[int, int], ...], robots: int, tasks: int,
) -> tuple[int, int, int, Diagnostic | None]:
    """Offline audit only. Duplicate attempts are EXPOSED, never repaired."""
    if (len({robot for robot, _ in attempts}) != len(attempts)
            or any(type(robot) is not int or not 0 <= robot < robots
                   or type(task) is not int or not 0 <= task < tasks
                   for robot, task in attempts)):
        raise ProtocolError(Diagnostic(
            owner=OWNER, function="validate_p2t_attempts",
            category="safety", code="P2T_ROBOT_CAPACITY_VIOLATION",
            expected="each robot attempts <= 1 valid task", actual=attempts,
        ))
    counts = [0] * tasks
    for _robot, task in attempts:
        counts[task] += 1
    unique = sum(count == 1 for count in counts)
    duplicates = sum(count > 1 for count in counts)
    unassigned = sum(count == 0 for count in counts)
    diagnostic = None
    if duplicates:
        diagnostic = Diagnostic(
            owner=OWNER, function="validate_p2t_attempts",
            category="safety", code="P2T_UNOBSERVED_PEER_COLLISION",
            expected="at most one peer attempts each task",
            actual={"duplicate_tasks":duplicates,"unassigned":unassigned},
            details="Different receiver-local P2TI sets permitted multiple winners.",
        )
    elif unassigned:
        diagnostic = Diagnostic(
            owner=OWNER, function="validate_p2t_attempts",
            category="planning", code="P2T_INCOMPLETE_PEER_COVERAGE",
            expected={"uniquely_covered_tasks":tasks},
            actual={"unique":unique,"unassigned":unassigned},
        )
    return unique, duplicates, unassigned, diagnostic


def coordinate_p2t_peer_conflicts(
    *, run: P2KLocalVoteResult, cost_matrix: tuple[tuple[float, ...], ...],
    votes_per_voter: int, sampler, loss_sampler, p_loss: float,
    max_rounds: int = 101, intent_repetitions: int = 3,
    announcement_repetitions: int = 3,
) -> P2TPeerResult:
    """Direct peer-only intent -> compare -> yield/act -> broadcast.

    There is NO fixed task owner and NO P2RC/P2RD/ACK/GRANT. Each robot
    chooses from its own Vote/Cost and observed P2TI/P2TE ONLY.
    Tentative acts are simulated; collisions are reported rather than hidden.
    """
    robots, tasks = validate_p2t_peer_scope(
        run=run, cost_matrix=cost_matrix,
        votes_per_voter=votes_per_voter, p_loss=p_loss,
        max_rounds=max_rounds, intent_repetitions=intent_repetitions,
        announcement_repetitions=announcement_repetitions,
    )
    pending = set(range(robots))
    rejected = [set() for _ in range(robots)]
    locally_executing = [set() for _ in range(robots)]
    last_task: dict[int, int] = {}
    attempts: dict[int, int] = {}  # observer ledger, never used for local choice
    events: list[CommunicationEvent] = []
    deliveries: list[DeliveryObservation] = []
    finish = max(run.decision_time_ms,
                 max((event.arrival_time_ms for event in run.events), default=0.0))
    conflicts = 0
    yielded = 0
    retargeted = 0
    initial_candidates = 0
    rounds = 0
    for claim_round in range(max_rounds):
        if not pending:
            break
        intents: list[P2TIntent] = []
        for robot in sorted(pending):
            task = select_p2m_local_request_task(
                run=run, robot_id=robot, own_cost_row=cost_matrix[robot],
                tried_tasks=frozenset(rejected[robot]),
                first_attempt=claim_round == 0,
                known_executing_tasks=frozenset(locally_executing[robot]),
            )
            if task is None:
                pending.discard(robot)
                continue
            if robot in last_task and last_task[robot] != task:
                retargeted += 1
            last_task[robot] = task
            claim = make_p2l_claim(
                run=run, robot_id=robot, task_id=task,
                claim_round=claim_round, votes_per_voter=votes_per_voter,
            )
            intents.append(P2TIntent(claim=claim,
                                     own_cost=float(cost_matrix[robot][task])))
        if not intents:
            break
        rounds += 1
        if claim_round == 0:
            initial_candidates = len(intents)
        sent, received, local_intents, finish = transmit_p2t_peer_intents(
            intents=tuple(intents), robots=robots, tasks=tasks,
            votes_per_voter=votes_per_voter, repetitions=intent_repetitions,
            start_ms=finish, sampler=sampler, loss_sampler=loss_sampler,
            p_loss=p_loss,
        )
        events.extend(sent)
        deliveries.extend(received)
        winners, losers, observed_conflicts = choose_p2t_peer_winners(
            intents=tuple(intents), locally_received=local_intents,
        )
        conflicts += observed_conflicts
        yielded += len(losers)
        for intent in losers:
            rejected[intent.claim.robot_id].add(intent.claim.task_id)
        acted = []
        for intent in winners:
            robot = intent.claim.robot_id
            task = intent.claim.task_id
            if robot not in pending:
                raise ProtocolError(Diagnostic(
                    owner=OWNER, function="coordinate_p2t_peer_conflicts",
                    category="state", code="P2T_ROBOT_REACTED_TWICE",
                    expected="new pending robot", actual=robot,
                ))
            pending.remove(robot)
            attempts[robot] = task
            acted.append((robot, task))
        sent_exec, received_exec, seen_exec, finish = (
            transmit_p2t_execution_notices(
                attempted=tuple(acted), claim_round=claim_round,
                robots=robots, tasks=tasks,
                repetitions=announcement_repetitions,
                start_ms=finish, sampler=sampler, loss_sampler=loss_sampler,
                p_loss=p_loss,
            )
        )
        events.extend(sent_exec)
        deliveries.extend(received_exec)
        for robot, tasks_seen in seen_exec.items():
            locally_executing[robot].update(tasks_seen)
    attempted = tuple(sorted(attempts.items(), key=lambda pair: (pair[1],pair[0])))
    unique, duplicates, unassigned, first_failure = validate_p2t_attempts(
        attempts=attempted, robots=robots, tasks=tasks,
    )
    return P2TPeerResult(
        attempted_pairs=attempted,
        events=tuple(events), deliveries=tuple(deliveries),
        rounds_executed=rounds, locally_observed_conflicts=conflicts,
        yielded_candidates=yielded, retargeted_intents=retargeted,
        initial_candidate_count=initial_candidates,
        unique_task_count=unique, duplicate_task_count=duplicates,
        unassigned_task_count=unassigned,
        recipient_seen_executing_tasks=tuple(
            tuple(sorted(known)) for known in locally_executing
        ),
        finish_ms=finish, first_diagnostic=first_failure,
    )

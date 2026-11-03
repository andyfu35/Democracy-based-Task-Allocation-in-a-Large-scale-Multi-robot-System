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
) -> P2MTaskOwnerResult:
    """Single fixed task-owner grant actor, with optional P2N advisory P2NX.

    P2M default repetitions=0 is unchanged. P2N repetitions>0 adds
    only post-GRANT physical EXECUTING broadcasts and receiver-local
    known-task exclusion. Neither branch supplies global Cost/Vote
    or reservation data to other robots. Synchronous known-roster
    shared-radio model is not a crash-tolerant consensus proof.
    """
    robots,tasks=validate_p2m_owner_scope(
        run=run,cost_matrix=cost_matrix,votes_per_voter=votes_per_voter,
        p_loss=p_loss,max_attempts=max_attempts,max_rounds=max_rounds,
    )
    repetitions=validate_p2n_announcement_repetitions(
        execution_announce_repetitions,
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
    first_error=None
    for claim_round in range(max_rounds):
        if not pending or len(executed)==tasks:
            break
        inbound:dict[int,list[P2LClaim]]={}
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
    )

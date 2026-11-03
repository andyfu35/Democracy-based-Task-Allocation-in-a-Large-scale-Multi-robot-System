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


@dataclass(frozen=True)
class P2MTaskOwnerResult:
    executed_pairs: tuple[tuple[int, int], ...]
    reserved_pairs: tuple[tuple[int, int], ...]
    events: tuple[CommunicationEvent, ...]
    deliveries: tuple[DeliveryObservation, ...]
    rounds_executed: int
    conflicted_task_rounds: int
    reassignment_requests: int
    blocked_robot_ids: tuple[int, ...]
    owner_decisions: tuple[dict, ...]
    finish_ms: float
    first_diagnostic: Diagnostic | None

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


def select_p2m_local_request_task(
    *, run: P2KLocalVoteResult, robot_id: int,
    own_cost_row: tuple[float, ...],
    tried_tasks: frozenset[int], first_attempt: bool,
) -> int | None:
    """Candidate knows ONLY its own Vote view, own Cost and local rejects."""
    tasks=len(own_cost_row)
    if first_attempt:
        original=dict(run.robot_claims).get(robot_id)
        if original is not None and original not in tried_tasks:
            return original
    return choose_p2l_next_task(
        available_tasks=frozenset(range(tasks))-tried_tasks,
        own_received_vote_row=run.local_vote_views[robot_id][robot_id],
        own_cost_row=own_cost_row,
    )


def coordinate_p2m_task_owners(
    *, run: P2KLocalVoteResult, cost_matrix: tuple[tuple[float, ...], ...],
    votes_per_voter: int, sampler, loss_sampler,
    p_loss: float, max_attempts: int = 24, max_rounds: int = 101,
) -> P2MTaskOwnerResult:
    """One authoritative owner per task, unicast-only CLAIM and decisions.

    Same original P2K local Softmax Votes; owner(task) = task % robots.
    Each owner sees ONLY confirmed request packets addressed to its task.
    Robots see ONLY their own received decision/own Cost/Vote and local
    rejected-task list; no global locked-task visibility, global vote
    matrix, all-peer ACK, task Score broadcast or hidden recovery.
    This is a synchronous known-roster experiment with serial radio
    scheduling, not a proof of asynchronous crash tolerance.
    """
    robots,tasks=validate_p2m_owner_scope(
        run=run,cost_matrix=cost_matrix,votes_per_voter=votes_per_voter,
        p_loss=p_loss,max_attempts=max_attempts,max_rounds=max_rounds,
    )
    pending=set(range(robots))
    blocked=set()
    tried=[set() for _ in range(robots)]
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
            )
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
            if error is not None and first_error is None:
                first_error=error
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
                "owner_decision","owner_decision_ack") for event in events)
            or any(reserved.get(task)!=robot for robot,task in pairs)):
        raise ProtocolError(Diagnostic(
            owner=OWNER,function="coordinate_p2m_task_owners",
            category="safety",code="P2M_INVALID_RESERVED_EXECUTION",
            expected="each execution backed by unique task-owner reservation and "
                     "physical grant delivery, only four owner unicast phases",
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
        blocked_robot_ids=tuple(sorted(blocked)),
        owner_decisions=tuple(owner_decisions),
        finish_ms=clock,first_diagnostic=first_error,
    )

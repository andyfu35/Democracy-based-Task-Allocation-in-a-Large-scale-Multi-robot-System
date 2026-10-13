"""E9L per-task-home distributed Bertsekas-style epsilon price auction.

Separate native PRICE / BID / AWARD method, not CBAA and not CBBA. Every task
is administered by its deterministic home robot (task_id for N == T). Robots
bid from ONLY their own costs and physically received auction prices. Task
homes alone award bids. No central winner assignment, global cost input to
an agent, or simulated relaying of undelivered packets.

The epsilon increment is from Bertsekas' classical auction. The packetized
per-task-home deployment, independent loss/repetition, and local-evidence
stop are explicit benchmark adaptations (not the original paper's wire format
or a claim of actual distributed termination / common knowledge).
"""
from __future__ import annotations

from dataclasses import dataclass
import math
import struct

from .coordination import (
    CommunicationEvent, DeliveryObservation,
    _broadcast_event, _unicast_event,
    _lossy_broadcast_deliveries, _lossy_unicast_delivery,
)
from .diagnostics import Diagnostic, ProtocolError
from .network import (
    SenderBudgetExhausted, SenderPayloadBudget,
    validate_packet_loss_probability,
)
from .optimizer import validate_cost_matrix

OWNER = "democracy_mrta.price_auction"
BID_PHASE = "e9l_price_bid"
AWARD_PHASE = "e9l_price_award"
PACKET = struct.Struct("<4sIIIdI")
BID_MAGIC = b"BID1"
AWARD_MAGIC = b"AWD1"
NO_WINNER = (1 << 32) - 1


@dataclass(frozen=True)
class PriceBid:
    bidder: int
    task: int
    offered_price: float
    observed_version: int
    round_id: int


@dataclass(frozen=True)
class PriceAward:
    task: int
    winner: int | None
    price: float
    version: int
    round_id: int


@dataclass
class TaskHome:
    task: int
    winner: int | None = None
    price: float = 0.0
    version: int = 0


@dataclass
class BidderLocal:
    robot: int
    cost_row: tuple[float, ...]
    prices: list[float]
    winners: list[int | None]
    versions: list[int]
    heard_rounds: list[int]
    pending: PriceBid | None = None
    last_own_bid_round: int = -1


@dataclass(frozen=True)
class AuctionWave:
    sends: int = 0
    sender_bytes: int = 0
    receiver_attempts: int = 0
    receiver_drops: int = 0
    late_deliveries: int = 0
    budget_denied: bool = False
    events: tuple[CommunicationEvent, ...] = ()
    deliveries: tuple[DeliveryObservation, ...] = ()


@dataclass(frozen=True)
class PriceAuctionResult:
    method: str
    assignment: tuple[tuple[int, int], ...]
    observer_full: bool
    optimistic_local_stop: bool
    local_certified_count: int
    round_count: int
    stop_reason: str
    elapsed_ms: float
    bid_sends: int
    award_sends: int
    sender_bytes: int
    delivery_attempts: int
    delivery_drops: int
    late_deliveries: int
    pending_bidder_count: int
    audit_events: tuple[CommunicationEvent, ...] = ()
    audit_deliveries: tuple[DeliveryObservation, ...] = ()


def validate_price_auction_configuration(
    *, cost_matrix, bid_loss, award_loss, epsilon,
    stage_window_ms, safety_rounds,
) -> int:
    """Square 1:1 experiment, independent source-unit epsilon and time gate."""
    robots, tasks = validate_cost_matrix(cost_matrix)
    if robots != tasks or robots < 2:
        raise ProtocolError(Diagnostic(
            owner=OWNER, function="validate_price_auction_configuration",
            category="data", code="E9L_REQUIRES_SQUARE_ONE_TASK_CAPACITY",
            expected="N=T>=2, each robot at most one task", actual=(robots,tasks),
        ))
    if any(not math.isfinite(c) or c < 0 for row in cost_matrix for c in row):
        raise ProtocolError(Diagnostic(
            owner=OWNER, function="validate_price_auction_configuration",
            category="data", code="E9L_INVALID_COSTS",
            expected="finite nonnegative physical Euclidean costs", actual="invalid entry",
        ))
    validate_packet_loss_probability(bid_loss)
    validate_packet_loss_probability(award_loss)
    if type(epsilon) not in (int,float) or not math.isfinite(epsilon) or epsilon <= 0:
        raise ProtocolError(Diagnostic(
            owner=OWNER, function="validate_price_auction_configuration",
            category="data", code="E9L_INVALID_EPSILON",
            expected="positive finite fixed cost-unit epsilon", actual=epsilon,
        ))
    if (type(stage_window_ms) not in (int,float)
        or not math.isfinite(stage_window_ms) or stage_window_ms <= 0):
        raise ProtocolError(Diagnostic(
            owner=OWNER, function="validate_price_auction_configuration",
            category="time", code="E9L_INVALID_STAGE_WINDOW",
            expected="positive finite milliseconds", actual=stage_window_ms,
        ))
    if type(safety_rounds) is not int or not 1 <= safety_rounds <= 2000:
        raise ProtocolError(Diagnostic(
            owner=OWNER, function="validate_price_auction_configuration",
            category="data", code="E9L_INVALID_SAFETY_ROUNDS",
            expected="integer 1..2000 (safety guard only)", actual=safety_rounds,
        ))
    return robots


def encode_price_bid(bid: PriceBid) -> bytes:
    """Actual canonical 28-byte E9L BID application representation."""
    return PACKET.pack(BID_MAGIC, bid.round_id, bid.task, bid.bidder,
                       bid.offered_price, bid.observed_version)


def encode_price_award(award: PriceAward) -> bytes:
    """Actual canonical 28-byte E9L AWARD application representation."""
    owner = NO_WINNER if award.winner is None else award.winner
    return PACKET.pack(AWARD_MAGIC, award.round_id, award.task, owner,
                       award.price, award.version)


def initialize_price_auction(cost_matrix) -> tuple[list[BidderLocal],list[TaskHome]]:
    """Only row-local costs reach a bidder. A home sees bids, not peers' costs."""
    n=len(cost_matrix)
    bidders=[BidderLocal(
        robot=i,cost_row=cost_matrix[i],prices=[0.0]*n,
        winners=[None]*n,versions=[0]*n,heard_rounds=[-1]*n,
    ) for i in range(n)]
    homes=[TaskHome(task=j) for j in range(n)]
    return bidders, homes


def propose_price_bid(state: BidderLocal, *, iteration: int, epsilon: float) -> PriceBid | None:
    """Bertsekas epsilon bid using only locally observed task prices.

    Do not bid for a second task while a first bid is unresolved; only the
    task home can resolve the pending bid via its physically delivered AWARD.
    This removes speculative multiple-winner claims in the lossy extension.
    """
    if state.pending is not None:
        return state.pending
    if any(winner == state.robot for winner in state.winners):
        return None
    utilities=[-cost-price for cost,price in zip(state.cost_row,state.prices)]
    order=sorted(range(len(utilities)),key=lambda j:(-utilities[j],j))
    best,runner_up=order[:2]
    bump=utilities[best]-utilities[runner_up]+epsilon
    offered=state.prices[best]+bump
    if not math.isfinite(offered) or offered <= state.prices[best]:
        raise ProtocolError(Diagnostic(
            owner=OWNER, function="propose_price_bid",
            category="planning", code="E9L_NONPOSITIVE_AUCTION_BID",
            expected="finite offer > locally seen task price",
            actual=(state.robot,best,offered),
        ))
    return PriceBid(state.robot,best,offered,state.versions[best],iteration)


def apply_price_auction_bids(*, homes: list[TaskHome], bids: list[PriceBid]) -> None:
    """Only each task's own home resolves its physically received bids."""
    grouped: dict[int,list[PriceBid]]={}
    for bid in bids:
        grouped.setdefault(bid.task,[]).append(bid)
    for home in homes:
        proposals=[b for b in grouped.get(home.task,())
                   if b.offered_price>home.price+1e-12]
        if not proposals:
            continue
        winner=max(proposals,key=lambda b:(b.offered_price,-b.bidder))
        home.price=winner.offered_price
        home.winner=winner.bidder
        home.version+=1


def accept_price_award(*, bidder: BidderLocal, award: PriceAward) -> None:
    """Own-local monotone AWARD evidence; no read of another home state."""
    j=award.task
    old_version=bidder.versions[j]
    if award.version<old_version:
        return
    if (award.version==old_version and bidder.heard_rounds[j]>=0
        and (bidder.prices[j]!=award.price or bidder.winners[j]!=award.winner)):
        raise ProtocolError(Diagnostic(
            owner=OWNER, function="accept_price_award",
            category="contract", code="E9L_SAME_VERSION_CONFLICT",
            expected=(old_version,bidder.winners[j],bidder.prices[j]),
            actual=(award.version,award.winner,award.price),
        ))
    bidder.prices[j]=award.price
    bidder.winners[j]=award.winner
    bidder.versions[j]=award.version
    bidder.heard_rounds[j]=max(bidder.heard_rounds[j],award.round_id)
    if (bidder.pending is not None and bidder.pending.task==j
        and award.version>bidder.pending.observed_version):
        bidder.pending=None


def transmit_price_bids(
    *, bidders, loss_sampler, sampler, p_loss, iteration, start_ms,
    window_ms, epsilon, capture_audit=False, send_budget=None,
) -> tuple[list[PriceBid],AuctionWave]:
    """Physically send one pending price offer per unassigned bidder."""
    n=len(bidders)
    received=[]
    sends=bytes_sent=attempts=drops=late=0
    events=[]
    obslog=[]
    denied=False
    for bidder in bidders:
        offer=propose_price_bid(bidder,iteration=iteration,epsilon=epsilon)
        if offer is None:
            continue
        owner=offer.task  # Square N=T: task j's auctioneer is robot j.
        if bidder.robot==owner:
            received.append(offer)  # Local bidder + task-home, no radio packet.
            if bidder.pending is None:
                bidder.pending=offer
                bidder.last_own_bid_round=iteration
            continue
        packet=encode_price_bid(offer)
        try:
            event=_unicast_event(
                phase=BID_PHASE,sender_id=bidder.robot,receiver_id=owner,
                send_time_ms=start_ms,payload_bytes=len(packet),sampler=sampler,
                task_id=offer.task,round_id=iteration+1,send_budget=send_budget,
            )
        except SenderBudgetExhausted:
            denied=True
            break
        if bidder.pending is None:
            bidder.pending=offer
            bidder.last_own_bid_round=iteration
        observed=_lossy_unicast_delivery(
            event=event,loss_sampler=loss_sampler,p_loss=p_loss,
            round_id=iteration+1,
        )
        sends+=1
        bytes_sent+=event.payload_bytes
        attempts+=1
        drops+=int(not observed.delivered)
        if capture_audit:
            events.append(event)
            obslog.append(observed)
        if observed.delivered:
            if observed.arrival_time_ms is None:
                raise ProtocolError(Diagnostic(
                    owner=OWNER,function="transmit_price_bids",
                    category="contract",code="E9L_BID_DELIVERED_WITHOUT_TIME",
                    expected="valid timestamp",actual=observed,
                ))
            if observed.arrival_time_ms<=start_ms+window_ms:
                received.append(offer)
            else:
                late+=1
    return received,AuctionWave(
        sends=sends,sender_bytes=bytes_sent,
        receiver_attempts=attempts,receiver_drops=drops,
        late_deliveries=late,budget_denied=denied,
        events=tuple(events),deliveries=tuple(obslog),
    )


def transmit_price_awards(
    *, homes, bidders, sampler, loss_sampler, p_loss,
    iteration, start_ms, window_ms, capture_audit=False, send_budget=None,
) -> AuctionWave:
    """The task home broadcasts its own price/winner every iteration.

    Repeated native award announcements are needed because an earlier AWARD
    may have been lost; a bidder cannot read an undelivered home state.
    """
    n=len(bidders)
    sends=bytes_sent=attempts=drops=late=0
    events=[]
    obslog=[]
    denied=False
    for home in homes:
        award=PriceAward(home.task,home.winner,home.price,home.version,iteration)
        packet=encode_price_award(award)
        try:
            event=_broadcast_event(
                phase=AWARD_PHASE,sender_id=home.task,
                send_time_ms=start_ms,payload_bytes=len(packet),sampler=sampler,
                task_id=home.task,round_id=iteration+1,send_budget=send_budget,
            )
        except SenderBudgetExhausted:
            denied=True
            break
        sends+=1
        bytes_sent+=event.payload_bytes
        # Own task-home state is locally available; no phantom loopback SEND.
        accept_price_award(bidder=bidders[home.task],award=award)
        observations=_lossy_broadcast_deliveries(
            event=event,num_robots=n,loss_sampler=loss_sampler,
            p_loss=p_loss,round_id=iteration+1,
        )
        attempts+=len(observations)
        drops+=sum(not o.delivered for o in observations)
        if capture_audit:
            events.append(event)
            obslog.extend(observations)
        for observed in observations:
            if not observed.delivered:
                continue
            if observed.arrival_time_ms is None:
                raise ProtocolError(Diagnostic(
                    owner=OWNER,function="transmit_price_awards",
                    category="contract",code="E9L_AWARD_DELIVERED_WITHOUT_TIME",
                    expected="valid timestamp",actual=observed,
                ))
            if observed.arrival_time_ms<=start_ms+window_ms:
                accept_price_award(bidder=bidders[observed.receiver_id],award=award)
            else:
                late+=1
    return AuctionWave(
        sends=sends,sender_bytes=bytes_sent,
        receiver_attempts=attempts,receiver_drops=drops,
        late_deliveries=late,budget_denied=denied,
        events=tuple(events),deliveries=tuple(obslog),
    )


def price_auction_local_certified(bidder: BidderLocal) -> bool:
    """Each robot uses only physically received own versioned AWARD ledger."""
    winners=bidder.winners
    n=len(winners)
    return bool(
        bidder.pending is None
        and all(w is not None and 0<=w<n for w in winners)
        and len(set(winners))==n
        and winners.count(bidder.robot)==1
        and all(r>bidder.last_own_bid_round for r in bidder.heard_rounds)
    )


def audit_price_auction_homes(homes: list[TaskHome]) -> tuple[tuple[int,int],...]:
    """Observer-only final assignment. Never used to correct a bidder/home."""
    return tuple((home.winner,home.task) for home in homes
                 if home.winner is not None)


def simulate_price_auction(
    *, cost_matrix, sampler, loss_sampler,
    bid_loss: float, award_loss: float, epsilon: float,
    stage_window_ms: float, safety_rounds: int,
    capture_audit: bool = False, send_budget: SenderPayloadBudget | None = None,
    external_observer=None,
) -> PriceAuctionResult:
    """Native BID/AWARD simulation with optimistic local-evidence halt.

    Stop is FREE simulator aggregation of separately local certificates, as
    in E9J native CBAA; it is NOT a paid global Commit, common knowledge,
    or an actual 802.11 collision/ACK/retransmission protocol.
    """
    n=validate_price_auction_configuration(
        cost_matrix=cost_matrix,bid_loss=bid_loss,award_loss=award_loss,
        epsilon=epsilon,stage_window_ms=stage_window_ms,
        safety_rounds=safety_rounds,
    )
    if send_budget is not None and type(send_budget) is not SenderPayloadBudget:
        raise ProtocolError(Diagnostic(
            owner=OWNER,function="simulate_price_auction",
            category="data",code="E9L_INVALID_SENDER_BUDGET",
            expected="SenderPayloadBudget or None",actual=type(send_budget).__name__,
        ))
    bidders,homes=initialize_price_auction(cost_matrix)
    clock=0.0
    round_count=bid_sends=award_sends=bytes_sent=attempts=drops=late=0
    events=[]
    deliveries=[]
    reason="round_safety_guard"
    local_count=0
    for iteration in range(safety_rounds):
        received,bid_wave=transmit_price_bids(
            bidders=bidders,sampler=sampler,loss_sampler=loss_sampler,
            p_loss=bid_loss,iteration=iteration,start_ms=clock,
            window_ms=stage_window_ms,epsilon=epsilon,
            capture_audit=capture_audit,send_budget=send_budget,
        )
        bid_sends+=bid_wave.sends
        bytes_sent+=bid_wave.sender_bytes
        attempts+=bid_wave.receiver_attempts
        drops+=bid_wave.receiver_drops
        late+=bid_wave.late_deliveries
        if capture_audit:
            events.extend(bid_wave.events)
            deliveries.extend(bid_wave.deliveries)
        if bid_wave.budget_denied:
            reason="sender_budget_exhausted_bid"
            if bid_wave.sends:
                clock+=stage_window_ms
            round_count+=1
            break
        apply_price_auction_bids(homes=homes,bids=received)
        if bid_wave.sends:
            clock+=stage_window_ms
        if external_observer is not None and bid_wave.sends:
            # Actual bid-phase end; observer only sees immutable home winners.
            external_observer(clock, audit_price_auction_homes(homes))
        award_wave=transmit_price_awards(
            homes=homes,bidders=bidders,sampler=sampler,
            loss_sampler=loss_sampler,p_loss=award_loss,
            iteration=iteration,start_ms=clock,
            window_ms=stage_window_ms,capture_audit=capture_audit,
            send_budget=send_budget,
        )
        award_sends+=award_wave.sends
        bytes_sent+=award_wave.sender_bytes
        attempts+=award_wave.receiver_attempts
        drops+=award_wave.receiver_drops
        late+=award_wave.late_deliveries
        if capture_audit:
            events.extend(award_wave.events)
            deliveries.extend(award_wave.deliveries)
        if award_wave.sends:
            clock+=stage_window_ms
        if external_observer is not None and award_wave.sends:
            # No state is returned to bidders or their homes.
            external_observer(clock, audit_price_auction_homes(homes))
        round_count+=1
        if award_wave.budget_denied:
            reason="sender_budget_exhausted_award"
            break
        ready=tuple(price_auction_local_certified(b) for b in bidders)
        local_count=sum(ready)
        if local_count==n:
            reason="all_local_award_evidence_certified_optimistic"
            break
    pairs=audit_price_auction_homes(homes)
    observer_full=(
        len(pairs)==n and len({r for r,_ in pairs})==n
        and len({j for _,j in pairs})==n
    )
    if send_budget is not None and (
        send_budget.sent_messages!=bid_sends+award_sends
        or send_budget.sent_bytes!=bytes_sent
    ):
        raise ProtocolError(Diagnostic(
            owner=OWNER,function="simulate_price_auction",
            category="contract",code="E9L_PHYSICAL_SENDER_LEDGER_MISMATCH",
            expected=(send_budget.sent_messages,send_budget.sent_bytes),
            actual=(bid_sends+award_sends,bytes_sent),
        ))
    return PriceAuctionResult(
        method="bertsekas_epsilon_price_auction_task_home_lossy",
        assignment=pairs,observer_full=observer_full,
        optimistic_local_stop=reason=="all_local_award_evidence_certified_optimistic",
        local_certified_count=local_count,round_count=round_count,
        stop_reason=reason,elapsed_ms=clock,
        bid_sends=bid_sends,award_sends=award_sends,
        sender_bytes=bytes_sent,delivery_attempts=attempts,
        delivery_drops=drops,late_deliveries=late,
        pending_bidder_count=sum(b.pending is not None for b in bidders),
        audit_events=tuple(events),audit_deliveries=tuple(deliveries),
    )

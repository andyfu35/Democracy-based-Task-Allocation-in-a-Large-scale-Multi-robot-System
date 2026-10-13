"""Genuine Choi/Brunet/How (2009) CBBA two-phase multi-assignment owner.

Consensus action table transcribed from T-RO 2009 p.917 Table 1. Snapshot wire
format, round timing and lossy receivers are explicitly E9M extensions.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .diagnostics import Diagnostic, ProtocolError
from .multitask_scenario import MultiTaskScene, best_insertion
from .multitask_evaluation import MethodRun
from .multitask_wire import E9MChannel, encode_cbba_snapshot, decode_cbba_snapshot, announce_tasks

EPS = 1e-9


@dataclass
class CBBALocal:
    robot_id: int
    tasks: int
    robots: int
    bundle: list[int] = field(default_factory=list)
    path: list[int] = field(default_factory=list)
    winners: list[int] = field(init=False)
    bids: list[float] = field(init=False)
    stamps: list[float] = field(init=False)

    def __post_init__(self) -> None:
        self.winners = [-1] * self.tasks
        self.bids = [0.0] * self.tasks
        self.stamps = [0.0] * self.robots


def build_bundle(scene: MultiTaskScene, agent: CBBALocal) -> None:
    """Auction incremental marginal best-position insertion, until capacity."""
    while len(agent.bundle) < scene.capacity:
        best = None
        for task in range(scene.tasks):
            if task in agent.bundle:
                continue
            marginal, position = best_insertion(scene, agent.robot_id, agent.path, task)
            if marginal <= agent.bids[task] + EPS:
                continue
            if best is None or marginal > best[0] + EPS or (abs(marginal - best[0]) <= EPS and task < best[1]):
                best = (marginal, task, position)
        if best is None:
            break
        value, task, position = best
        agent.bundle.append(task)
        agent.path.insert(position, task)
        agent.bids[task] = value
        agent.winners[task] = agent.robot_id


def resolve_cbba_action(*, receiver: int, sender: int,
                        local_winner: int, remote_winner: int,
                        local_bid: float, remote_bid: float,
                        local_stamps: list[float], remote_stamps: list[float]) -> str:
    """Exact 2009 Table 1 cases: winner k/i/m/none vs i/k/m/n/none."""
    i, k = receiver, sender
    m, n = remote_winner, local_winner
    fresh = lambda agent: remote_stamps[agent] > local_stamps[agent]
    higher = remote_bid > local_bid + EPS
    if m == k:
        if n == i:
            return "update" if higher else "leave"
        if n in (k, -1):
            return "update"
        return "update" if fresh(n) or higher else "leave"
    if m == i:
        if n in (i, -1):
            return "leave"
        if n == k:
            return "reset"
        return "reset" if fresh(n) else "leave"
    if m >= 0:  # sender claims third party m, m not i/k
        if n == i:
            return "update" if fresh(m) and higher else "leave"
        if n == k:
            return "update" if fresh(m) else "reset"
        if n in (m, -1):
            return "update" if fresh(m) else "leave"
        if (fresh(m) and fresh(n)) or (fresh(m) and higher):
            return "update"
        if fresh(n) and local_stamps[m] > remote_stamps[m]:
            return "reset"
        return "leave"
    if n in (i, -1):
        return "leave"
    if n == k:
        return "update"
    return "update" if fresh(n) else "leave"


def release_dependent_suffix(agent: CBBALocal) -> int:
    """After losing an earlier bundle task release it AND all later additions."""
    first_lost = next((idx for idx, task in enumerate(agent.bundle)
                       if agent.winners[task] != agent.robot_id), None)
    if first_lost is None:
        return 0
    abandoned = agent.bundle[first_lost:]
    for task in abandoned[1:]:
        agent.winners[task] = -1
        agent.bids[task] = 0.0
    for task in abandoned:
        agent.path.remove(task)
    del agent.bundle[first_lost:]
    return len(abandoned)


def accept_consensus(agent: CBBALocal, sender: int, message: dict,
                     arrival_ms: float) -> int:
    """Process only a complete physically received matching sender snapshot."""
    before_bundle = len(agent.bundle)
    previous_stamps = list(agent.stamps)
    for task in range(agent.tasks):
        action = resolve_cbba_action(
            receiver=agent.robot_id, sender=sender,
            local_winner=agent.winners[task], remote_winner=message["z"][task],
            local_bid=agent.bids[task], remote_bid=message["y"][task],
            local_stamps=previous_stamps, remote_stamps=message["s"])
        if action == "update":
            agent.winners[task] = message["z"][task]
            agent.bids[task] = message["y"][task]
        elif action == "reset":
            agent.winners[task] = -1
            agent.bids[task] = 0.0
    release_dependent_suffix(agent)
    for peer in range(agent.robots):
        agent.stamps[peer] = max(agent.stamps[peer],
                                arrival_ms if peer == sender else message["s"][peer])
    return before_bundle - len(agent.bundle)


def cbba_local_certificate(agent: CBBALocal, capacity: int) -> bool:
    """Local evidence only: full unique winner vector and locally owned tasks."""
    if any(w < 0 for w in agent.winners):
        return False
    if len(agent.bundle) > capacity or len(set(agent.bundle)) != len(agent.bundle):
        return False
    if set(agent.path) != set(agent.bundle):
        return False
    if any(agent.winners[t] != agent.robot_id for t in agent.bundle):
        return False
    return all(sum(w == robot for w in agent.winners) <= capacity
               for robot in range(agent.robots))


def observer_cbba_agreement(agents: list[CBBALocal], capacity: int) -> bool:
    """Posthoc only: no assignments or state are changed by the observer."""
    if not all(cbba_local_certificate(agent, capacity) for agent in agents):
        return False
    reference = agents[0].winners
    return (all(agent.winners == reference for agent in agents) and
            all(set(a.bundle) == {task for task, winner in enumerate(reference)
                                   if winner == a.robot_id} for a in agents))


def run_cbba(scene: MultiTaskScene, channel: E9MChannel,
             p_loss: float, max_rounds: int) -> MethodRun:
    local_announcements = announce_tasks(channel, scene.task_positions)
    agents = [CBBALocal(i, scene.tasks, scene.robots) for i in range(scene.robots)]
    for agent in agents:
        if local_announcements[agent.robot_id] != scene.task_positions:
            raise ProtocolError(Diagnostic("cbba_multitask", "run_cbba", "dependency",
                                           "E9M_CBBA_LOCAL_TASK_DIFFERENCE"))
    rounds = 0
    for round_id in range(1, max_rounds + 1):
        rounds = round_id
        for agent in agents:
            build_bundle(scene, agent)
        # Frozen messages: no recipient sees sender state mutated during same phase.
        messages = [encode_cbba_snapshot(round_id, a.robot_id, a.winners, a.bids,
                                         a.stamps) for a in agents]
        inbox: dict[tuple[int, int], list[bytes]] = {}
        channel.begin_phase()
        for sender, frames in enumerate(messages):
            for frame_id, frame in enumerate(frames):
                delivered = channel.send(phase="cbba_consensus", sender=sender,
                                         frame=frame, round_id=round_id,
                                         frame_id=frame_id, p_loss=p_loss)
                for receiver, packet in delivered.items():
                    inbox.setdefault((receiver, sender), []).append(packet)
        channel.end_phase()
        for receiver, agent in enumerate(agents):
            for sender in range(scene.robots):
                if receiver == sender:
                    continue
                decoded = decode_cbba_snapshot(inbox.get((receiver, sender), []),
                                               round_id=round_id, sender_id=sender,
                                               robots=scene.robots, tasks=scene.tasks)
                if decoded is not None:
                    accept_consensus(agent, sender, decoded, channel.clock_ms)
        if observer_cbba_agreement(agents, scene.capacity):
            break
    agreed = observer_cbba_agreement(agents, scene.capacity)
    channel.audit_physical_bytes()
    return MethodRun(
        method="cbba", routes=tuple(tuple(a.path) for a in agents),
        rounds=rounds, observer_agreement=agreed,
        local_certificates=sum(cbba_local_certificate(a, scene.capacity) for a in agents),
        guard_censored=not agreed, failure_code="" if agreed else "E9M_CBBA_ROUND_GUARD",
        elapsed_ms=channel.clock_ms, ledger=channel.ledger(),
    )

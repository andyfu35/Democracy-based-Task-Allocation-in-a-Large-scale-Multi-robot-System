"""E9M capacity-aware MULTI-TASK extension of democratic task allocation.

Not the frozen one-task E9I method: one physically transmitted Cost and Vote
wave per task, reliable charged Score and Commit, updated insertion utility.
"""
from __future__ import annotations

from collections import defaultdict

from .diagnostics import Diagnostic, ProtocolError
from .multitask_scenario import MultiTaskScene, best_insertion
from .multitask_evaluation import MethodRun
from .multitask_wire import (E9MChannel, announce_tasks, encode_small_packet,
                             decode_small_packet)


def choose_received_cost_winner(observed: dict[int, float]) -> int:
    """Each robot votes for max physically known marginal utility; ties by ID."""
    if not observed:
        raise ProtocolError(Diagnostic("voting_multitask", "choose_received_cost_winner",
                                       "dependency", "E9M_NO_LOCAL_COST"))
    return min(observed, key=lambda rid: (-observed[rid], rid))


def choose_plurality(scores: dict[int, int]) -> int:
    """Decentralized decision from reliably published physical vote counts."""
    if not scores:
        raise ProtocolError(Diagnostic("voting_multitask", "choose_plurality",
                                       "state", "E9M_NO_ELIGIBLE_CANDIDATE"))
    return min(scores, key=lambda rid: (-scores[rid], rid))


def transmit_costs(scene: MultiTaskScene, channel: E9MChannel, task: int,
                   routes: list[list[int]], counts: list[int], loss: float
                   ) -> dict[int, dict[int, float]]:
    """Agent-specific local route marginal and receiver-specific cost views."""
    views: dict[int, dict[int, float]] = {i: {} for i in range(scene.robots)}
    channel.begin_phase()
    for sender in range(scene.robots):
        if counts[sender] >= scene.capacity:
            continue
        cost, _ = best_insertion(scene, sender, routes[sender], task)
        views[sender][sender] = cost  # own computed cost needs no SEND receipt
        packet = encode_small_packet("voting_cost", task, sender, sender, cost)
        received = channel.send(phase="voting_cost", sender=sender, frame=packet,
                                round_id=task, frame_id=0, p_loss=loss)
        for receiver, frame in received.items():
            candidate, value = decode_small_packet("voting_cost", frame, task, sender)
            views[receiver][candidate] = value
    channel.end_phase()
    return views


def transmit_votes(scene: MultiTaskScene, channel: E9MChannel, task: int,
                   views: dict[int, dict[int, float]], counts: list[int],
                   loss: float) -> dict[int, int]:
    """Candidate collects actual delivered ballots directed to itself."""
    received_scores: dict[int, int] = defaultdict(int)
    channel.begin_phase()
    for sender in range(scene.robots):
        if counts[sender] >= scene.capacity:
            continue
        candidate = choose_received_cost_winner(views[sender])
        if counts[candidate] >= scene.capacity:
            raise ProtocolError(Diagnostic("voting_multitask", "transmit_votes",
                                           "contract", "E9M_VOTE_FOR_FULL_ROBOT",
                                           expected="eligible candidate", actual=candidate))
        if candidate == sender:
            received_scores[candidate] += 1  # physically local
        frame = encode_small_packet("voting_vote", task, sender, candidate, 1.0)
        delivered = channel.send(phase="voting_vote", sender=sender, frame=frame,
                                 round_id=task, frame_id=0, p_loss=loss)
        if candidate in delivered:
            voted_candidate, _ = decode_small_packet("voting_vote", delivered[candidate],
                                                     task, sender)
            if voted_candidate != candidate:
                raise ProtocolError(Diagnostic("voting_multitask", "transmit_votes",
                                               "contract", "E9M_VOTE_CANDIDATE_MISMATCH"))
            received_scores[candidate] += 1
    channel.end_phase()
    if not sum(received_scores.values()):
        raise ProtocolError(Diagnostic("voting_multitask", "transmit_votes",
                                       "safety", "E9M_NO_PHYSICALLY_RECEIVED_BALLOTS"))
    return received_scores


def transmit_scores(scene: MultiTaskScene, channel: E9MChannel, task: int,
                    counts: list[int], received_scores: dict[int, int]
                    ) -> tuple[int, ...]:
    """Reliable actual score broadcasts; each agent independently selects winner."""
    local_scores: list[dict[int, int]] = [dict() for _ in range(scene.robots)]
    channel.begin_phase()
    for sender in range(scene.robots):
        if counts[sender] >= scene.capacity:
            continue
        score = received_scores.get(sender, 0)
        local_scores[sender][sender] = score
        frame = encode_small_packet("voting_score", task, sender, sender, score)
        delivered = channel.send(phase="voting_score", sender=sender, frame=frame,
                                 round_id=task, frame_id=0, p_loss=0.0)
        for receiver, wire in delivered.items():
            candidate, value = decode_small_packet("voting_score", wire, task, sender)
            local_scores[receiver][candidate] = int(value)
    channel.end_phase()
    eligible = {rid for rid, count in enumerate(counts) if count < scene.capacity}
    if any(set(view) != eligible for view in local_scores):
        raise ProtocolError(Diagnostic("voting_multitask", "transmit_scores",
                                       "dependency", "E9M_SCORE_NOT_DELIVERED"))
    decisions = tuple(choose_plurality(scores) for scores in local_scores)
    if len(set(decisions)) != 1:
        raise ProtocolError(Diagnostic("voting_multitask", "transmit_scores",
                                       "contract", "E9M_SCORE_VIEW_DISAGREEMENT"))
    return decisions


def transmit_commit(scene: MultiTaskScene, channel: E9MChannel, task: int,
                    decisions: tuple[int, ...], routes: list[list[int]],
                    counts: list[int]) -> None:
    """Only physically elected agent modifies own path after reliable Commit SEND."""
    winner = decisions[0]
    if counts[winner] >= scene.capacity:
        raise ProtocolError(Diagnostic("voting_multitask", "transmit_commit",
                                       "safety", "E9M_WINNER_CAPACITY_EXCEEDED"))
    _, position = best_insertion(scene, winner, routes[winner], task)
    frame = encode_small_packet("voting_commit", task, winner, winner, position)
    channel.begin_phase()
    delivered = channel.send(phase="voting_commit", sender=winner, frame=frame,
                             round_id=task, frame_id=0, p_loss=0.0)
    channel.end_phase()
    for receiver in range(scene.robots):
        if receiver == winner:
            continue
        if receiver not in delivered:
            raise ProtocolError(Diagnostic("voting_multitask", "transmit_commit",
                                           "dependency", "E9M_COMMIT_NOT_DELIVERED"))
        candidate, spot = decode_small_packet("voting_commit", delivered[receiver],
                                              task, winner)
        if candidate != winner or int(spot) != position:
            raise ProtocolError(Diagnostic("voting_multitask", "transmit_commit",
                                           "contract", "E9M_COMMIT_PAYLOAD_DIFFERENCE"))
    routes[winner].insert(position, task)
    counts[winner] += 1


def run_voting_multitask(scene: MultiTaskScene, channel: E9MChannel,
                        p_loss: float) -> MethodRun:
    announcements = announce_tasks(channel, scene.task_positions)
    routes: list[list[int]] = [[] for _ in range(scene.robots)]
    counts = [0] * scene.robots
    for task in range(scene.tasks):
        if any(local != scene.task_positions for local in announcements):
            raise ProtocolError(Diagnostic("voting_multitask", "run_voting_multitask",
                                           "dependency", "E9M_VOTING_TASK_INCOMPLETE"))
        cost_views = transmit_costs(scene, channel, task, routes, counts, p_loss)
        votes = transmit_votes(scene, channel, task, cost_views, counts, p_loss)
        winners = transmit_scores(scene, channel, task, counts, votes)
        transmit_commit(scene, channel, task, winners, routes, counts)
    channel.audit_physical_bytes()
    return MethodRun(
        method="voting_multitask", routes=tuple(tuple(route) for route in routes),
        rounds=scene.tasks, observer_agreement=True, local_certificates=scene.robots,
        guard_censored=False, failure_code="", elapsed_ms=channel.clock_ms,
        ledger=channel.ledger(),
    )

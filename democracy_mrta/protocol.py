from __future__ import annotations

from dataclasses import dataclass

from .diagnostics import Diagnostic, ProtocolError


@dataclass(frozen=True)
class Vote:
    task_id: int
    round_id: int
    voter_id: int
    candidate_id: int


@dataclass(frozen=True)
class TaskDecision:
    task_id: int
    round_id: int
    winner_id: int
    quorum: int
    counted_votes: int
    eligible_count: int


@dataclass(frozen=True)
class AllocationResult:
    decisions: tuple[TaskDecision, ...]
    total_cost: float
    assigned_pairs: tuple[tuple[int, int], ...]
    multiple_winner_failures: int
    duplicate_execution_failures: int
    duplicate_vote_counted_failures: int
    stale_vote_accepted_failures: int

    @property
    def assigned_tasks(self) -> int:
        return len(self.assigned_pairs)


def quorum_size(eligible_count: int) -> int:
    if eligible_count <= 0:
        raise ValueError("eligible_count must be positive")
    return eligible_count // 2 + 1


def select_visible_candidate(
    *,
    cost_matrix: tuple[tuple[float, ...], ...],
    task_id: int,
    visible_candidates: tuple[int, ...],
) -> int:
    if not visible_candidates:
        raise ProtocolError(
            Diagnostic(
                owner="protocol",
                function="select_visible_candidate",
                category="state",
                code="NO_VISIBLE_CANDIDATE",
                expected="at least one visible eligible robot",
                actual=0,
            )
        )
    return min(
        visible_candidates,
        key=lambda robot_id: (cost_matrix[robot_id][task_id], robot_id),
    )


def record_vote(
    *,
    vote: Vote,
    current_task_id: int,
    current_round_id: int,
    eligible_robots: frozenset[int],
    ledgers_by_candidate: dict[int, set[int]],
) -> str:
    if vote.task_id != current_task_id or vote.round_id != current_round_id:
        return "STALE_REJECTED"
    if vote.voter_id not in eligible_robots or vote.candidate_id not in eligible_robots:
        return "INELIGIBLE_REJECTED"

    voter_ledgers = [candidate for candidate, voters in ledgers_by_candidate.items() if vote.voter_id in voters]
    if voter_ledgers:
        return "DUPLICATE_REJECTED"

    ledgers_by_candidate.setdefault(vote.candidate_id, set()).add(vote.voter_id)
    return "ACCEPTED"


def resolve_unique_majority(
    *,
    ledgers_by_candidate: dict[int, set[int]],
    quorum: int,
    task_id: int,
    round_id: int,
) -> tuple[int, int]:
    winners = [
        (candidate_id, len(voters))
        for candidate_id, voters in ledgers_by_candidate.items()
        if len(voters) >= quorum
    ]
    if len(winners) != 1:
        raise ProtocolError(
            Diagnostic(
                owner="protocol",
                function="resolve_unique_majority",
                category="safety" if len(winners) > 1 else "state",
                code="MULTIPLE_QUORUM_WINNERS" if len(winners) > 1 else "NO_QUORUM",
                expected=1,
                actual=len(winners),
                details=f"task_id={task_id}, round_id={round_id}, quorum={quorum}",
            )
        )
    return winners[0]


def run_zero_loss_task_round(
    *,
    cost_matrix: tuple[tuple[float, ...], ...],
    task_id: int,
    round_id: int,
    eligible_robots: frozenset[int],
) -> TaskDecision:
    quorum = quorum_size(len(eligible_robots))
    visible_candidates = tuple(sorted(eligible_robots))
    ledgers_by_candidate: dict[int, set[int]] = {}

    for voter_id in visible_candidates:
        candidate_id = select_visible_candidate(
            cost_matrix=cost_matrix,
            task_id=task_id,
            visible_candidates=visible_candidates,
        )
        status = record_vote(
            vote=Vote(
                task_id=task_id,
                round_id=round_id,
                voter_id=voter_id,
                candidate_id=candidate_id,
            ),
            current_task_id=task_id,
            current_round_id=round_id,
            eligible_robots=eligible_robots,
            ledgers_by_candidate=ledgers_by_candidate,
        )
        if status != "ACCEPTED":
            raise ProtocolError(
                Diagnostic(
                    owner="protocol",
                    function="run_zero_loss_task_round",
                    category="contract",
                    code="UNEXPECTED_VOTE_REJECTION",
                    expected="ACCEPTED",
                    actual=status,
                    details=f"task_id={task_id}, voter_id={voter_id}",
                )
            )

    winner_id, counted_votes = resolve_unique_majority(
        ledgers_by_candidate=ledgers_by_candidate,
        quorum=quorum,
        task_id=task_id,
        round_id=round_id,
    )
    return TaskDecision(
        task_id=task_id,
        round_id=round_id,
        winner_id=winner_id,
        quorum=quorum,
        counted_votes=counted_votes,
        eligible_count=len(eligible_robots),
    )


def run_zero_loss_allocation_epoch(
    cost_matrix: tuple[tuple[float, ...], ...],
) -> AllocationResult:
    num_robots = len(cost_matrix)
    if num_robots == 0:
        raise ValueError("cost_matrix must contain robots")
    num_tasks = len(cost_matrix[0])
    if any(len(row) != num_tasks for row in cost_matrix):
        raise ValueError("cost_matrix must be rectangular")
    if num_tasks > num_robots:
        raise ValueError("E0 requires num_tasks <= num_robots")

    eligible = set(range(num_robots))
    used_winners: set[int] = set()
    decisions: list[TaskDecision] = []
    assigned_pairs: list[tuple[int, int]] = []
    total_cost = 0.0
    duplicate_execution_failures = 0

    for task_id in range(num_tasks):
        decision = run_zero_loss_task_round(
            cost_matrix=cost_matrix,
            task_id=task_id,
            round_id=0,
            eligible_robots=frozenset(eligible),
        )
        if decision.winner_id in used_winners:
            duplicate_execution_failures += 1
            raise ProtocolError(
                Diagnostic(
                    owner="protocol",
                    function="run_zero_loss_allocation_epoch",
                    category="safety",
                    code="DUPLICATE_EXECUTION",
                    expected="winner not previously assigned in epoch",
                    actual=decision.winner_id,
                    details=f"task_id={task_id}",
                )
            )

        used_winners.add(decision.winner_id)
        eligible.remove(decision.winner_id)
        decisions.append(decision)
        assigned_pairs.append((decision.winner_id, task_id))
        total_cost += cost_matrix[decision.winner_id][task_id]

    return AllocationResult(
        decisions=tuple(decisions),
        total_cost=total_cost,
        assigned_pairs=tuple(assigned_pairs),
        multiple_winner_failures=0,
        duplicate_execution_failures=duplicate_execution_failures,
        duplicate_vote_counted_failures=0,
        stale_vote_accepted_failures=0,
    )

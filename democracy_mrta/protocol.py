from __future__ import annotations

from dataclasses import dataclass

from .diagnostics import Diagnostic, ProtocolError
from .optimizer import AssignmentSolution, solve_hungarian_assignment, validate_cost_matrix


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


def assignment_to_votes(
    *,
    assignment: AssignmentSolution,
    voter_id: int,
    round_id: int,
) -> tuple[Vote, ...]:
    return tuple(
        Vote(
            task_id=task_id,
            round_id=round_id,
            voter_id=voter_id,
            candidate_id=robot_id,
        )
        for robot_id, task_id in assignment.assigned_pairs
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

    already_counted = any(
        vote.voter_id in voters for voters in ledgers_by_candidate.values()
    )
    if already_counted:
        return "DUPLICATE_REJECTED"

    ledgers_by_candidate.setdefault(vote.candidate_id, set()).add(vote.voter_id)
    return "ACCEPTED"


def find_unique_majority(
    *,
    ledgers_by_candidate: dict[int, set[int]],
    quorum: int,
    task_id: int,
    round_id: int,
) -> tuple[int, int] | None:
    winners = [
        (candidate_id, len(voters))
        for candidate_id, voters in ledgers_by_candidate.items()
        if len(voters) >= quorum
    ]
    if len(winners) > 1:
        raise ProtocolError(
            Diagnostic(
                owner="protocol",
                function="find_unique_majority",
                category="safety",
                code="MULTIPLE_QUORUM_WINNERS",
                expected="at most one strict-majority winner",
                actual=len(winners),
                details=f"task_id={task_id}, round_id={round_id}, quorum={quorum}",
            )
        )
    if not winners:
        return None
    return winners[0]


def resolve_unique_majority(
    *,
    ledgers_by_candidate: dict[int, set[int]],
    quorum: int,
    task_id: int,
    round_id: int,
) -> tuple[int, int]:
    winner = find_unique_majority(
        ledgers_by_candidate=ledgers_by_candidate,
        quorum=quorum,
        task_id=task_id,
        round_id=round_id,
    )
    if winner is None:
        raise ProtocolError(
            Diagnostic(
                owner="protocol",
                function="resolve_unique_majority",
                category="state",
                code="NO_QUORUM",
                expected=1,
                actual=0,
                details=f"task_id={task_id}, round_id={round_id}, quorum={quorum}",
            )
        )
    return winner


def validate_one_to_one_commits(
    assigned_pairs: tuple[tuple[int, int], ...] | list[tuple[int, int]],
) -> None:
    pairs = tuple(assigned_pairs)
    robot_ids = [robot_id for robot_id, _task_id in pairs]
    task_ids = [task_id for _robot_id, task_id in pairs]

    if len(robot_ids) != len(set(robot_ids)):
        raise ProtocolError(
            Diagnostic(
                owner="protocol",
                function="validate_one_to_one_commits",
                category="safety",
                code="DUPLICATE_ROBOT_COMMIT",
                expected="at most one committed task per robot",
                actual=pairs,
            )
        )

    if len(task_ids) != len(set(task_ids)):
        raise ProtocolError(
            Diagnostic(
                owner="protocol",
                function="validate_one_to_one_commits",
                category="safety",
                code="DUPLICATE_TASK_COMMIT",
                expected="at most one committed robot per task",
                actual=pairs,
            )
        )


def compute_zero_loss_local_proposals(
    cost_matrix: tuple[tuple[float, ...], ...],
) -> tuple[AssignmentSolution, ...]:
    num_robots, _ = validate_cost_matrix(cost_matrix)
    proposals = tuple(
        solve_hungarian_assignment(cost_matrix)
        for _voter_id in range(num_robots)
    )

    expected = proposals[0].assigned_pairs
    for voter_id, proposal in enumerate(proposals[1:], start=1):
        if proposal.assigned_pairs != expected:
            raise ProtocolError(
                Diagnostic(
                    owner="protocol",
                    function="compute_zero_loss_local_proposals",
                    category="contract",
                    code="ZERO_LOSS_PROPOSAL_MISMATCH",
                    expected=expected,
                    actual=proposal.assigned_pairs,
                    details=f"voter_id={voter_id}",
                )
            )
    return proposals


def collect_zero_loss_vote_ledgers(
    *,
    proposals: tuple[AssignmentSolution, ...],
    num_robots: int,
    num_tasks: int,
    round_id: int,
) -> dict[int, dict[int, set[int]]]:
    eligible_robots = frozenset(range(num_robots))
    ledgers_by_task: dict[int, dict[int, set[int]]] = {
        task_id: {} for task_id in range(num_tasks)
    }

    if len(proposals) != num_robots:
        raise ProtocolError(
            Diagnostic(
                owner="protocol",
                function="collect_zero_loss_vote_ledgers",
                category="contract",
                code="PROPOSAL_COUNT_MISMATCH",
                expected=num_robots,
                actual=len(proposals),
            )
        )

    for voter_id, proposal in enumerate(proposals):
        for vote in assignment_to_votes(
            assignment=proposal,
            voter_id=voter_id,
            round_id=round_id,
        ):
            status = record_vote(
                vote=vote,
                current_task_id=vote.task_id,
                current_round_id=round_id,
                eligible_robots=eligible_robots,
                ledgers_by_candidate=ledgers_by_task[vote.task_id],
            )
            if status != "ACCEPTED":
                raise ProtocolError(
                    Diagnostic(
                        owner="protocol",
                        function="collect_zero_loss_vote_ledgers",
                        category="contract",
                        code="UNEXPECTED_ZERO_LOSS_VOTE_REJECTION",
                        expected="ACCEPTED",
                        actual=status,
                        details=(
                            f"task_id={vote.task_id}, voter_id={voter_id}, "
                            f"candidate_id={vote.candidate_id}"
                        ),
                    )
                )

    return ledgers_by_task


def resolve_zero_loss_epoch(
    *,
    cost_matrix: tuple[tuple[float, ...], ...],
    ledgers_by_task: dict[int, dict[int, set[int]]],
    round_id: int,
) -> AllocationResult:
    num_robots, num_tasks = validate_cost_matrix(cost_matrix)
    quorum = quorum_size(num_robots)
    decisions: list[TaskDecision] = []
    assigned_pairs: list[tuple[int, int]] = []

    for task_id in range(num_tasks):
        winner_id, counted_votes = resolve_unique_majority(
            ledgers_by_candidate=ledgers_by_task[task_id],
            quorum=quorum,
            task_id=task_id,
            round_id=round_id,
        )

        if counted_votes != num_robots:
            raise ProtocolError(
                Diagnostic(
                    owner="protocol",
                    function="resolve_zero_loss_epoch",
                    category="contract",
                    code="ZERO_LOSS_VOTE_NOT_UNANIMOUS",
                    expected=num_robots,
                    actual=counted_votes,
                    details=f"task_id={task_id}, winner_id={winner_id}",
                )
            )

        decisions.append(
            TaskDecision(
                task_id=task_id,
                round_id=round_id,
                winner_id=winner_id,
                quorum=quorum,
                counted_votes=counted_votes,
                eligible_count=num_robots,
            )
        )
        assigned_pairs.append((winner_id, task_id))

    validate_one_to_one_commits(assigned_pairs)

    total_cost = float(
        sum(cost_matrix[robot_id][task_id] for robot_id, task_id in assigned_pairs)
    )
    return AllocationResult(
        decisions=tuple(decisions),
        total_cost=total_cost,
        assigned_pairs=tuple(assigned_pairs),
        multiple_winner_failures=0,
        duplicate_execution_failures=0,
        duplicate_vote_counted_failures=0,
        stale_vote_accepted_failures=0,
    )


def run_zero_loss_allocation_epoch(
    cost_matrix: tuple[tuple[float, ...], ...],
) -> AllocationResult:
    num_robots, num_tasks = validate_cost_matrix(cost_matrix)
    round_id = 0

    proposals = compute_zero_loss_local_proposals(cost_matrix)
    ledgers_by_task = collect_zero_loss_vote_ledgers(
        proposals=proposals,
        num_robots=num_robots,
        num_tasks=num_tasks,
        round_id=round_id,
    )
    return resolve_zero_loss_epoch(
        cost_matrix=cost_matrix,
        ledgers_by_task=ledgers_by_task,
        round_id=round_id,
    )

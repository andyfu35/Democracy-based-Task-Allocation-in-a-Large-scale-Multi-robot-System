from __future__ import annotations

from dataclasses import dataclass
from collections import Counter

from .diagnostics import Diagnostic, ProtocolError
from .optimizer import AssignmentSolution, solve_hungarian_assignment
from .coordination import LossyCoordinationResult
from .protocol import AllocationResult


@dataclass(frozen=True)
class E0Metrics:
    protocol_cost: float
    oracle_cost: float
    optimality_gap_percent: float
    assignment_success_rate: float


def optimality_gap_percent(protocol_cost: float, oracle_cost: float) -> float:
    if oracle_cost < 0:
        raise ValueError("oracle_cost must be non-negative")
    if oracle_cost == 0:
        return 0.0 if protocol_cost == 0 else float("inf")
    return (protocol_cost - oracle_cost) / oracle_cost * 100.0


def require_zero_loss_optimality(
    *,
    protocol_cost: float,
    oracle_cost: float,
    tolerance: float = 1e-12,
) -> None:
    difference = abs(protocol_cost - oracle_cost)
    if difference > tolerance:
        raise ProtocolError(
            Diagnostic(
                owner="metrics",
                function="require_zero_loss_optimality",
                category="contract",
                code="ZERO_LOSS_OPTIMALITY_MISMATCH",
                expected=oracle_cost,
                actual=protocol_cost,
                details=f"absolute_difference={difference}, tolerance={tolerance}",
            )
        )


def evaluate_e0(
    *,
    cost_matrix: tuple[tuple[float, ...], ...],
    allocation: AllocationResult,
) -> E0Metrics:
    oracle = solve_hungarian_assignment(cost_matrix)
    require_zero_loss_optimality(
        protocol_cost=allocation.total_cost,
        oracle_cost=oracle.total_cost,
    )

    num_tasks = len(cost_matrix[0])
    success_rate = allocation.assigned_tasks / num_tasks
    return E0Metrics(
        protocol_cost=allocation.total_cost,
        oracle_cost=oracle.total_cost,
        optimality_gap_percent=optimality_gap_percent(
            allocation.total_cost,
            oracle.total_cost,
        ),
        assignment_success_rate=success_rate,
    )



@dataclass(frozen=True)
class AssignmentCorrectnessMetrics:
    total_tasks: int
    committed_tasks: int
    correct_committed_tasks: int
    incorrect_committed_tasks: int
    correct_executor_rate: float
    correctness_among_committed: float


def evaluate_assignment_correctness(
    *,
    assigned_pairs: tuple[tuple[int, int], ...],
    oracle_assignment: AssignmentSolution,
    total_tasks: int,
) -> AssignmentCorrectnessMetrics:
    if total_tasks <= 0:
        raise ProtocolError(
            Diagnostic(
                owner="metrics",
                function="evaluate_assignment_correctness",
                category="data",
                code="INVALID_TOTAL_TASKS",
                expected="positive total_tasks",
                actual=total_tasks,
            )
        )

    oracle_by_task = {
        task_id: robot_id
        for robot_id, task_id in oracle_assignment.assigned_pairs
    }
    if len(oracle_by_task) != total_tasks:
        raise ProtocolError(
            Diagnostic(
                owner="metrics",
                function="evaluate_assignment_correctness",
                category="contract",
                code="ORACLE_ASSIGNMENT_INCOMPLETE",
                expected=total_tasks,
                actual=len(oracle_by_task),
            )
        )

    assigned_task_ids = [task_id for _robot_id, task_id in assigned_pairs]
    if len(assigned_task_ids) != len(set(assigned_task_ids)):
        raise ProtocolError(
            Diagnostic(
                owner="metrics",
                function="evaluate_assignment_correctness",
                category="contract",
                code="DUPLICATE_TASK_IN_EVALUATED_ASSIGNMENT",
                expected="unique committed task ids",
                actual=tuple(assigned_pairs),
            )
        )

    unknown_tasks = tuple(
        task_id
        for task_id in assigned_task_ids
        if task_id not in oracle_by_task
    )
    if unknown_tasks:
        raise ProtocolError(
            Diagnostic(
                owner="metrics",
                function="evaluate_assignment_correctness",
                category="data",
                code="COMMITTED_TASK_OUT_OF_ORACLE_RANGE",
                expected=tuple(sorted(oracle_by_task)),
                actual=unknown_tasks,
            )
        )

    correct = sum(
        int(oracle_by_task[task_id] == robot_id)
        for robot_id, task_id in assigned_pairs
    )
    committed = len(assigned_pairs)
    incorrect = committed - correct
    conditional = (
        correct / committed
        if committed > 0
        else float("nan")
    )

    return AssignmentCorrectnessMetrics(
        total_tasks=total_tasks,
        committed_tasks=committed,
        correct_committed_tasks=correct,
        incorrect_committed_tasks=incorrect,
        correct_executor_rate=correct / total_tasks,
        correctness_among_committed=conditional,
    )



@dataclass(frozen=True)
class E2VoteAuditReport:
    summary: dict[str, float | int]
    voters: tuple[dict[str, float | int], ...]
    tasks: tuple[dict[str, float | int], ...]
    candidates: tuple[dict[str, float | int], ...]


def require_e2_vote_audit(
    *,
    result: LossyCoordinationResult,
    num_robots: int,
) -> None:
    actual = (
        len(result.audit_visible_rows_by_voter),
        len(result.audit_proposals_by_voter),
    )
    if actual != (num_robots, num_robots):
        raise ProtocolError(
            Diagnostic(
                owner="metrics",
                function="require_e2_vote_audit",
                category="contract",
                code="E2_AUDIT_NOT_CAPTURED",
                expected=(num_robots, num_robots),
                actual=actual,
                details="run simulate_democracy_hungarian_lossy with capture_vote_audit=True",
            )
        )


def index_e2_vote_deliveries(
    result: LossyCoordinationResult,
) -> dict[tuple[int, int, int], bool]:
    outcome: dict[tuple[int, int, int], bool] = {}
    for event in result.deliveries:
        if event.phase != "vote":
            continue
        key = (event.sender_id, int(event.task_id), event.receiver_id)
        if key in outcome:
            raise ProtocolError(
                Diagnostic(
                    owner="metrics",
                    function="index_e2_vote_deliveries",
                    category="contract",
                    code="E2_AUDIT_DUPLICATE_VOTE_DELIVERY",
                    expected="unique voter/task/candidate packet",
                    actual=key,
                )
            )
        outcome[key] = bool(event.delivered)
    return outcome


def verify_e2_vote_ledgers(
    *,
    result: LossyCoordinationResult,
    received_by_candidate: dict[tuple[int, int], set[int]],
    num_tasks: int,
    quorum: int,
) -> None:
    saved = {
        (task_id, candidate_id): set(voters)
        for task_id, candidate_id, voters in result.audit_counted_vote_ledgers
    }
    saved = {key: voters for key, voters in saved.items() if voters}
    calculated = {
        key: voters for key, voters in received_by_candidate.items() if voters
    }
    if saved != calculated:
        raise ProtocolError(
            Diagnostic(
                owner="metrics",
                function="verify_e2_vote_ledgers",
                category="contract",
                code="E2_AUDIT_LEDGER_MISMATCH",
                expected=calculated,
                actual=saved,
                details="delivered votes differ from votes actually counted by protocol",
            )
        )

    committed = {task_id: robot_id for robot_id, task_id in result.assigned_pairs}
    for task_id in range(num_tasks):
        winners = [
            candidate_id
            for (ledger_task, candidate_id), voters in calculated.items()
            if ledger_task == task_id and len(voters) >= quorum
        ]
        expected_winner = winners[0] if len(winners) == 1 else None
        actual_winner = committed.get(task_id)
        if len(winners) > 1 or expected_winner != actual_winner:
            raise ProtocolError(
                Diagnostic(
                    owner="metrics",
                    function="verify_e2_vote_ledgers",
                    category="contract",
                    code="E2_AUDIT_QUORUM_MISMATCH",
                    expected=expected_winner,
                    actual=actual_winner,
                    details=f"task_id={task_id}, quorum={quorum}, winners={winners}",
                )
            )


def evaluate_e2_vote_audit(
    *,
    result: LossyCoordinationResult,
    oracle_assignment: AssignmentSolution,
    num_robots: int,
    num_tasks: int,
) -> E2VoteAuditReport:
    """Observe one existing E2 result; never recalculate local Hungarian or voting."""
    require_e2_vote_audit(result=result, num_robots=num_robots)

    oracle_by_task = {
        task_id: robot_id for robot_id, task_id in oracle_assignment.assigned_pairs
    }
    if len(oracle_by_task) != num_tasks:
        raise ProtocolError(
            Diagnostic(
                owner="metrics",
                function="evaluate_e2_vote_audit",
                category="contract",
                code="E2_AUDIT_ORACLE_INCOMPLETE",
                expected=num_tasks,
                actual=len(oracle_by_task),
            )
        )

    received_rows = [{voter_id} for voter_id in range(num_robots)]
    for observation in result.deliveries:
        if observation.phase == "cost" and observation.delivered:
            received_rows[observation.receiver_id].add(observation.sender_id)
    for voter_id in range(num_robots):
        recorded = result.audit_visible_rows_by_voter[voter_id]
        if received_rows[voter_id] != set(recorded):
            raise ProtocolError(
                Diagnostic(
                    owner="metrics",
                    function="evaluate_e2_vote_audit",
                    category="contract",
                    code="E2_AUDIT_LOCAL_VIEW_MISMATCH",
                    expected=tuple(sorted(received_rows[voter_id])),
                    actual=tuple(sorted(recorded)),
                    details=f"voter_id={voter_id}",
                )
            )

    remaining_packets = index_e2_vote_deliveries(result)
    before = Counter()
    after = Counter()
    received_by_candidate: dict[tuple[int, int], set[int]] = {}
    voter_rows: list[dict[str, float | int]] = []
    remote_attempts = remote_delivered = self_votes = 0

    for voter_id, proposal in enumerate(result.audit_proposals_by_voter):
        correct = 0
        delivered_correct = 0
        voter_delivered = 0
        voter_remote_attempts = 0
        voter_remote_delivered = 0
        voter_self_votes = 0
        task_ids_seen: set[int] = set()
        for candidate_id, task_id in proposal.assigned_pairs:
            if task_id in task_ids_seen or not 0 <= task_id < num_tasks:
                raise ProtocolError(
                    Diagnostic(
                        owner="metrics",
                        function="evaluate_e2_vote_audit",
                        category="contract",
                        code="E2_AUDIT_INVALID_LOCAL_PROPOSAL",
                        expected="unique tasks in [0,num_tasks)",
                        actual=proposal.assigned_pairs,
                        details=f"voter_id={voter_id}",
                    )
                )
            task_ids_seen.add(task_id)
            before[(task_id, candidate_id)] += 1
            is_correct = candidate_id == oracle_by_task[task_id]
            correct += int(is_correct)

            if candidate_id == voter_id:
                delivered = True
                self_votes += 1
                voter_self_votes += 1
            else:
                key = (voter_id, task_id, candidate_id)
                if key not in remaining_packets:
                    raise ProtocolError(
                        Diagnostic(
                            owner="metrics",
                            function="evaluate_e2_vote_audit",
                            category="contract",
                            code="E2_AUDIT_MISSING_VOTE_PACKET",
                            expected=key,
                            actual="no vote delivery observation",
                        )
                    )
                delivered = remaining_packets.pop(key)
                remote_attempts += 1
                voter_remote_attempts += 1
                remote_delivered += int(delivered)
                voter_remote_delivered += int(delivered)

            if delivered:
                after[(task_id, candidate_id)] += 1
                received_by_candidate.setdefault((task_id, candidate_id), set()).add(
                    voter_id
                )
                delivered_correct += int(is_correct)
                voter_delivered += 1

        voter_rows.append({
            "voter_id": voter_id,
            "visible_rows": len(result.audit_visible_rows_by_voter[voter_id]),
            "proposals": len(proposal.assigned_pairs),
            "oracle_matching_proposals": correct,
            "incorrect_proposals": len(proposal.assigned_pairs) - correct,
            "raw_correct_rate": correct / len(proposal.assigned_pairs)
                if proposal.assigned_pairs else 0.0,
            "delivered_votes": voter_delivered,
            "delivered_correct_votes": delivered_correct,
            "remote_vote_attempts": voter_remote_attempts,
            "remote_vote_delivered": voter_remote_delivered,
            "remote_vote_dropped": voter_remote_attempts - voter_remote_delivered,
            "self_votes": voter_self_votes,
        })

    if remaining_packets:
        raise ProtocolError(
            Diagnostic(
                owner="metrics",
                function="evaluate_e2_vote_audit",
                category="contract",
                code="E2_AUDIT_UNEXPECTED_VOTE_PACKET",
                expected="no unmatched vote transport observation",
                actual=tuple(sorted(remaining_packets))[:10],
            )
        )

    quorum = num_robots // 2 + 1
    verify_e2_vote_ledgers(
        result=result,
        received_by_candidate=received_by_candidate,
        num_tasks=num_tasks,
        quorum=quorum,
    )

    committed = {task_id: robot_id for robot_id, task_id in result.assigned_pairs}
    task_rows: list[dict[str, float | int]] = []
    candidate_rows: list[dict[str, float | int]] = []
    pre_quorum = post_quorum = 0
    oracle_pre_quorum = oracle_post_quorum = 0
    for task_id in range(num_tasks):
        choices = sorted(
            {candidate_id for (t, candidate_id) in before if t == task_id}
        )
        ranked_pre = sorted(
            choices, key=lambda candidate_id: (-before[(task_id, candidate_id)], candidate_id)
        )
        ranked_post = sorted(
            choices, key=lambda candidate_id: (-after[(task_id, candidate_id)], candidate_id)
        )
        top_before = ranked_pre[0] if ranked_pre else -1
        top_after = ranked_post[0] if ranked_post else -1
        before_top_votes = before[(task_id, top_before)] if ranked_pre else 0
        after_top_votes = after[(task_id, top_after)] if ranked_post else 0
        oracle_robot = oracle_by_task[task_id]
        before_oracle = before[(task_id, oracle_robot)]
        after_oracle = after[(task_id, oracle_robot)]
        n_proposals = sum(before[(task_id, candidate_id)] for candidate_id in choices)
        n_received = sum(after[(task_id, candidate_id)] for candidate_id in choices)

        pre_quorum += int(before_top_votes >= quorum)
        post_quorum += int(after_top_votes >= quorum)
        oracle_pre_quorum += int(before_oracle >= quorum)
        oracle_post_quorum += int(after_oracle >= quorum)
        task_rows.append({
            "task_id": task_id,
            "oracle_robot": oracle_robot,
            "raw_total_votes": n_proposals,
            "raw_oracle_votes": before_oracle,
            "raw_correct_rate": before_oracle / n_proposals if n_proposals else 0.0,
            "raw_top_robot": top_before,
            "raw_top_votes": before_top_votes,
            "received_total_votes": n_received,
            "received_oracle_votes": after_oracle,
            "received_top_robot": top_after,
            "received_top_votes": after_top_votes,
            "distinct_candidates": len(choices),
            "pre_vote_quorum_possible": int(before_top_votes >= quorum),
            "post_vote_quorum": int(after_top_votes >= quorum),
            "lost_quorum_during_vote_transport": int(
                before_top_votes >= quorum and after_top_votes < quorum
            ),
            "committed_robot": committed.get(task_id, -1),
            "quorum": quorum,
        })
        for candidate_id in choices:
            candidate_rows.append({
                "task_id": task_id,
                "candidate_id": candidate_id,
                "oracle_candidate": int(candidate_id == oracle_robot),
                "raw_votes": before[(task_id, candidate_id)],
                "received_votes": after[(task_id, candidate_id)],
                "quorum": quorum,
                "committed": int(candidate_id == committed.get(task_id, -1)),
            })

    proposals_total = sum(int(row["proposals"]) for row in voter_rows)
    correct_total = sum(int(row["oracle_matching_proposals"]) for row in voter_rows)
    received_total = sum(int(row["delivered_votes"]) for row in voter_rows)
    correct_received = sum(int(row["delivered_correct_votes"]) for row in voter_rows)
    return E2VoteAuditReport(
        summary={
            "robots": num_robots,
            "tasks": num_tasks,
            "quorum": quorum,
            "visible_rows_mean": sum(int(row["visible_rows"]) for row in voter_rows) / num_robots,
            "raw_total_votes": proposals_total,
            "raw_correct_votes": correct_total,
            "raw_correct_vote_rate": correct_total / proposals_total if proposals_total else 0.0,
            "received_total_votes": received_total,
            "received_correct_votes": correct_received,
            "received_correct_vote_rate": correct_received / received_total if received_total else 0.0,
            "remote_vote_attempts": remote_attempts,
            "remote_vote_delivered": remote_delivered,
            "remote_delivery_rate": remote_delivered / remote_attempts if remote_attempts else 0.0,
            "self_votes": self_votes,
            "tasks_with_raw_quorum": pre_quorum,
            "tasks_with_received_quorum": post_quorum,
            "tasks_with_oracle_raw_quorum": oracle_pre_quorum,
            "tasks_with_oracle_received_quorum": oracle_post_quorum,
            "tasks_lost_quorum_to_vote_transport": sum(
                int(row["lost_quorum_during_vote_transport"]) for row in task_rows
            ),
            "committed_tasks": len(result.assigned_pairs),
        },
        voters=tuple(voter_rows),
        tasks=tuple(task_rows),
        candidates=tuple(candidate_rows),
    )

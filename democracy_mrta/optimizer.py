from __future__ import annotations

from dataclasses import dataclass
import math
import hashlib
import random
import bisect

from scipy.optimize import linear_sum_assignment

from .diagnostics import Diagnostic, ProtocolError


@dataclass(frozen=True)
class AssignmentSolution:
    assigned_pairs: tuple[tuple[int, int], ...]
    total_cost: float

    @property
    def assigned_tasks(self) -> int:
        return len(self.assigned_pairs)


def validate_cost_matrix(
    cost_matrix: tuple[tuple[float, ...], ...],
    *, allow_tasks_exceed_robots: bool = False,
) -> tuple[int, int]:
    """Validate finite rectangular costs; default requires full capacity-one feasibility.

    Batched Greedy alone may accept fewer *received* robot rows than tasks
    to produce a partial one-shot allocation without inventing lost Cost rows.
    """
    if not cost_matrix:
        raise ProtocolError(
            Diagnostic(
                owner="optimizer",
                function="validate_cost_matrix",
                category="data",
                code="EMPTY_COST_MATRIX",
                expected="at least one robot row",
                actual=0,
            )
        )

    num_robots = len(cost_matrix)
    num_tasks = len(cost_matrix[0])
    if num_tasks <= 0:
        raise ProtocolError(
            Diagnostic(
                owner="optimizer",
                function="validate_cost_matrix",
                category="data",
                code="EMPTY_TASK_SET",
                expected="at least one task column",
                actual=0,
            )
        )

    if any(len(row) != num_tasks for row in cost_matrix):
        raise ProtocolError(
            Diagnostic(
                owner="optimizer",
                function="validate_cost_matrix",
                category="data",
                code="NON_RECTANGULAR_COST_MATRIX",
                expected=num_tasks,
                actual=tuple(len(row) for row in cost_matrix),
            )
        )

    if num_tasks > num_robots and not allow_tasks_exceed_robots:
        raise ProtocolError(
            Diagnostic(
                owner="optimizer",
                function="validate_cost_matrix",
                category="contract",
                code="TASKS_EXCEED_ROBOTS",
                expected="num_tasks <= num_robots",
                actual=f"{num_tasks}>{num_robots}",
            )
        )

    for robot_id, row in enumerate(cost_matrix):
        for task_id, value in enumerate(row):
            if not math.isfinite(value):
                raise ProtocolError(
                    Diagnostic(
                        owner="optimizer",
                        function="validate_cost_matrix",
                        category="data",
                        code="NONFINITE_COST",
                        expected="finite cost",
                        actual=value,
                        details=f"robot_id={robot_id}, task_id={task_id}",
                    )
                )

    return num_robots, num_tasks


def solve_hungarian_assignment(
    cost_matrix: tuple[tuple[float, ...], ...],
) -> AssignmentSolution:
    _, num_tasks = validate_cost_matrix(cost_matrix)

    row_indices, column_indices = linear_sum_assignment(cost_matrix)
    assigned_pairs = tuple(
        sorted(
            (
                (int(robot_id), int(task_id))
                for robot_id, task_id in zip(row_indices, column_indices)
            ),
            key=lambda pair: (pair[1], pair[0]),
        )
    )

    if len(assigned_pairs) != num_tasks:
        raise ProtocolError(
            Diagnostic(
                owner="optimizer",
                function="solve_hungarian_assignment",
                category="contract",
                code="INCOMPLETE_HUNGARIAN_ASSIGNMENT",
                expected=num_tasks,
                actual=len(assigned_pairs),
            )
        )

    total_cost = float(
        sum(cost_matrix[robot_id][task_id] for robot_id, task_id in assigned_pairs)
    )
    return AssignmentSolution(
        assigned_pairs=assigned_pairs,
        total_cost=total_cost,
    )


def solve_visible_hungarian_assignment(
    cost_matrix: tuple[tuple[float, ...], ...],
    visible_robot_ids: frozenset[int] | set[int] | tuple[int, ...],
) -> AssignmentSolution:
    num_robots, num_tasks = validate_cost_matrix(cost_matrix)
    visible = tuple(sorted(set(int(robot_id) for robot_id in visible_robot_ids)))

    if not visible:
        raise ProtocolError(
            Diagnostic(
                owner="optimizer",
                function="solve_visible_hungarian_assignment",
                category="state",
                code="NO_VISIBLE_ROBOTS",
                expected="at least one visible robot row",
                actual=0,
            )
        )

    invalid = tuple(robot_id for robot_id in visible if robot_id < 0 or robot_id >= num_robots)
    if invalid:
        raise ProtocolError(
            Diagnostic(
                owner="optimizer",
                function="solve_visible_hungarian_assignment",
                category="data",
                code="VISIBLE_ROBOT_ID_OUT_OF_RANGE",
                expected=f"0 <= robot_id < {num_robots}",
                actual=invalid,
            )
        )

    local_matrix = tuple(cost_matrix[robot_id] for robot_id in visible)
    row_indices, column_indices = linear_sum_assignment(local_matrix)

    assigned_pairs = tuple(
        sorted(
            (
                (visible[int(local_row_id)], int(task_id))
                for local_row_id, task_id in zip(row_indices, column_indices)
            ),
            key=lambda pair: (pair[1], pair[0]),
        )
    )

    expected_assignments = min(len(visible), num_tasks)
    if len(assigned_pairs) != expected_assignments:
        raise ProtocolError(
            Diagnostic(
                owner="optimizer",
                function="solve_visible_hungarian_assignment",
                category="contract",
                code="PARTIAL_HUNGARIAN_CARDINALITY_MISMATCH",
                expected=expected_assignments,
                actual=len(assigned_pairs),
                details=f"visible_robot_count={len(visible)}, num_tasks={num_tasks}",
            )
        )

    total_cost = float(
        sum(cost_matrix[robot_id][task_id] for robot_id, task_id in assigned_pairs)
    )
    return AssignmentSolution(
        assigned_pairs=assigned_pairs,
        total_cost=total_cost,
    )


def select_cheapest_visible_greedy_row(
    *,
    cost_column: tuple[float, ...],
    visible_robot_ids: frozenset[int] | set[int] | tuple[int, ...],
) -> tuple[int, float]:
    """One pass over only this voter's known active candidate rows."""
    if not visible_robot_ids:
        raise ProtocolError(
            Diagnostic(
                owner="optimizer",
                function="select_cheapest_visible_greedy_row",
                category="state",
                code="NO_VISIBLE_GREEDY_CANDIDATES",
                expected="at least one eligible visible row",
                actual=0,
            )
        )
    best: tuple[float, int] | None = None
    for row_id in visible_robot_ids:
        if not isinstance(row_id, int) or row_id < 0 or row_id >= len(cost_column):
            raise ProtocolError(
                Diagnostic(
                    owner="optimizer",
                    function="select_cheapest_visible_greedy_row",
                    category="data",
                    code="GREEDY_VISIBLE_ROBOT_OUT_OF_RANGE",
                    expected=f"integer 0 <= row_id < {len(cost_column)}",
                    actual=row_id,
                )
            )
        item = (cost_column[row_id], row_id)
        if best is None or item < best:
            best = item
    assert best is not None
    return best[1], float(best[0])


def require_one_greedy_task(num_tasks: int) -> None:
    if num_tasks != 1:
        raise ProtocolError(
            Diagnostic(
                owner="optimizer",
                function="require_one_greedy_task",
                category="planning",
                code="GREEDY_REQUIRES_ONE_TASK",
                expected=1,
                actual=num_tasks,
            )
        )


def solve_visible_greedy_task(
    cost_matrix: tuple[tuple[float, ...], ...],
    visible_robot_ids: frozenset[int] | set[int] | tuple[int, ...],
) -> AssignmentSolution:
    """Public one-task solver; never substitutes unseen rows."""
    _, num_tasks = validate_cost_matrix(cost_matrix)
    require_one_greedy_task(num_tasks)
    row_id, value = select_cheapest_visible_greedy_row(
        cost_column=tuple(row[0] for row in cost_matrix),
        visible_robot_ids=visible_robot_ids,
    )
    return AssignmentSolution(assigned_pairs=((row_id, 0),), total_cost=value)


def solve_all_visible_greedy_task_votes(
    cost_matrix: tuple[tuple[float, ...], ...],
    visible_by_voter: tuple[frozenset[int], ...],
) -> tuple[AssignmentSolution, ...]:
    """Validate the epoch ONCE, then make one independent local choice per voter."""
    num_robots, num_tasks = validate_cost_matrix(cost_matrix)
    require_one_greedy_task(num_tasks)
    if len(visible_by_voter) != num_robots:
        raise ProtocolError(
            Diagnostic(
                owner="optimizer",
                function="solve_all_visible_greedy_task_votes",
                category="contract",
                code="GREEDY_LOCAL_VIEW_COUNT_MISMATCH",
                expected=num_robots,
                actual=len(visible_by_voter),
            )
        )
    costs = tuple(row[0] for row in cost_matrix)
    proposals: list[AssignmentSolution] = []
    for voter_id, rows in enumerate(visible_by_voter):
        row_id, value = select_cheapest_visible_greedy_row(
            cost_column=costs,
            visible_robot_ids=rows,
        )
        proposals.append(AssignmentSolution(
            assigned_pairs=((row_id, 0),),
            total_cost=value,
        ))
    return tuple(proposals)


def solve_visible_batched_greedy_assignment(
    cost_matrix: tuple[tuple[float, ...], ...],
    visible_robot_ids: frozenset[int] | set[int] | tuple[int, ...],
) -> AssignmentSolution:
    """Global minimum-pair Greedy over this voter's physically visible Cost rows.

    Across ALL remaining robot-task pairs select minimum (cost, task_id, robot_id),
    remove both endpoints, and repeat until no eligible robot or task remains.
    This removes Task-ID-first planning priority; missing Cost rows are NEVER
    reconstructed. Each local proposal remains capacity-one, even at high loss.
    """
    num_robots, num_tasks = validate_cost_matrix(
        cost_matrix, allow_tasks_exceed_robots=True,
    )
    visible = tuple(sorted(set(visible_robot_ids)))
    if not visible:
        raise ProtocolError(Diagnostic(
            owner="optimizer", function="solve_visible_batched_greedy_assignment",
            category="state", code="BATCH_GREEDY_NO_VISIBLE_ROWS",
            expected="at least own physically known Cost row", actual=visible,
        ))
    if any(type(r) is not int or r < 0 or r >= num_robots for r in visible):
        raise ProtocolError(Diagnostic(
            owner="optimizer", function="solve_visible_batched_greedy_assignment",
            category="data", code="BATCH_GREEDY_INVALID_VISIBLE_ROW",
            expected=f"robot IDs in [0,{num_robots})", actual=visible,
        ))
    remaining_robots = set(visible)
    remaining_tasks = set(range(num_tasks))
    assigned: list[tuple[int, int]] = []
    ranked_edges = sorted(
        (cost_matrix[robot_id][task_id], task_id, robot_id)
        for robot_id in visible for task_id in range(num_tasks)
    )
    for _cost, task_id, robot_id in ranked_edges:
        if robot_id not in remaining_robots or task_id not in remaining_tasks:
            continue
        assigned.append((robot_id, task_id))
        remaining_robots.remove(robot_id)
        remaining_tasks.remove(task_id)
        if not remaining_robots or not remaining_tasks:
            break
    expected_count = min(len(visible), num_tasks)
    if len(assigned) != expected_count:
        raise ProtocolError(Diagnostic(
            owner="optimizer", function="solve_visible_batched_greedy_assignment",
            category="planning", code="GLOBAL_GREEDY_CARDINALITY_MISMATCH",
            expected=expected_count, actual=len(assigned),
        ))
    pairs = tuple(sorted(assigned, key=lambda pair: (pair[1], pair[0])))
    return AssignmentSolution(
        assigned_pairs=pairs,
        total_cost=float(sum(cost_matrix[r][t] for r, t in pairs)),
    )



def solve_visible_task_ordered_greedy_assignment(
    cost_matrix: tuple[tuple[float, ...], ...],
    visible_robot_ids: frozenset[int] | set[int] | tuple[int, ...],
) -> AssignmentSolution:
    """One local planning pass over ascending task IDs, then batch all choices.

    For task T0,T1,... choose the cheapest still-free *visible* robot, remove
    it locally, and continue. Unlike Global minimum-edge Greedy, tasks take
    priority over costs across different tasks. This does not transmit a Vote
    yet, and it never reconstructs unseen robot Cost rows.
    """
    num_robots, num_tasks = validate_cost_matrix(
        cost_matrix, allow_tasks_exceed_robots=True,
    )
    visible = tuple(sorted(set(visible_robot_ids)))
    if not visible:
        raise ProtocolError(Diagnostic(
            owner="optimizer", function="solve_visible_task_ordered_greedy_assignment",
            category="state", code="TASK_ORDER_GREEDY_NO_VISIBLE_ROWS",
            expected="at least the voter's own physically known Cost row",
            actual=visible,
        ))
    if any(type(r) is not int or r < 0 or r >= num_robots for r in visible):
        raise ProtocolError(Diagnostic(
            owner="optimizer", function="solve_visible_task_ordered_greedy_assignment",
            category="data", code="TASK_ORDER_GREEDY_INVALID_VISIBLE_ROW",
            expected=f"robot IDs in [0,{num_robots})",
            actual=visible,
        ))
    remaining = set(visible)
    chosen: list[tuple[int, int]] = []
    for task_id in range(num_tasks):
        if not remaining:
            break
        robot_id, _value = select_cheapest_visible_greedy_row(
            cost_column=tuple(row[task_id] for row in cost_matrix),
            visible_robot_ids=remaining,
        )
        chosen.append((robot_id, task_id))
        remaining.remove(robot_id)
    expected_count = min(len(visible), num_tasks)
    if len(chosen) != expected_count:
        raise ProtocolError(Diagnostic(
            owner="optimizer", function="solve_visible_task_ordered_greedy_assignment",
            category="planning", code="TASK_ORDER_GREEDY_CARDINALITY_MISMATCH",
            expected=expected_count, actual=len(chosen),
        ))
    return AssignmentSolution(
        assigned_pairs=tuple(chosen),
        total_cost=float(sum(cost_matrix[r][t] for r, t in chosen)),
    )



def validate_probabilistic_vote_policy(
    *, votes_per_voter: int, temperature: float, seed: int,
    voter_id: int, num_robots: int,
) -> None:
    """Data boundary for the optional one-batch multi-ticket stochastic policy."""
    if (type(votes_per_voter) is not int or not 1 <= votes_per_voter <= 255
            or type(seed) is not int or seed < 0
            or type(voter_id) is not int or not 0 <= voter_id < num_robots
            or type(temperature) not in (int, float)
            or not math.isfinite(temperature) or temperature <= 0):
        raise ProtocolError(Diagnostic(
            owner="optimizer", function="validate_probabilistic_vote_policy",
            category="data", code="P2J_INVALID_PROBABILITY_POLICY",
            expected={"votes_per_voter":"integer 1..255",
                      "seed":"nonnegative integer","voter_id":f"0..{num_robots-1}",
                      "temperature":"finite positive number"},
            actual={"votes_per_voter":votes_per_voter,"seed":seed,
                    "voter_id":voter_id,"temperature":temperature},
        ))


def sample_probabilistic_pair_votes(
    *, cost_matrix: tuple[tuple[float, ...], ...],
    visible_robot_ids: frozenset[int] | set[int] | tuple[int, ...],
    voter_id: int, seed: int, votes_per_voter: int = 100,
    temperature: float = 5.0, round_id: int = 0,
) -> tuple[tuple[int, int, int], ...]:
    """Choose exactly N tickets from one voter's *visible* Task x Robot pairs.

    P(task, robot) = (1 / task_count) * softmax(-cost / temperature |
    visible robots, task). Task-balanced sampling avoids suppressing difficult
    tasks solely because their absolute costs exceed costs of other tasks.
    Duplicate tickets are aggregated as (task_id, candidate_id, count).
    No unavailable Cost row is read, assigned or sampled. All RNG state is
    local and SHA256-keyed by seed/voter/epoch; neither Python global random
    state nor the network loss sampler is used.
    """
    num_robots, num_tasks = validate_cost_matrix(
        cost_matrix, allow_tasks_exceed_robots=True,
    )
    validate_probabilistic_vote_policy(
        votes_per_voter=votes_per_voter, temperature=temperature,
        seed=seed, voter_id=voter_id, num_robots=num_robots,
    )
    if type(round_id) is not int or round_id < 0:
        raise ProtocolError(Diagnostic(
            owner="optimizer", function="sample_probabilistic_pair_votes",
            category="data", code="P2J_INVALID_BALLOT_ROUND",
            expected="nonnegative integer", actual=round_id,
        ))
    visible=tuple(sorted(set(visible_robot_ids)))
    if (not visible or voter_id not in visible or
            any(type(r) is not int or r < 0 or r >= num_robots for r in visible)):
        raise ProtocolError(Diagnostic(
            owner="optimizer", function="sample_probabilistic_pair_votes",
            category="state", code="P2J_INVALID_LOCAL_COST_VIEW",
            expected="only valid physically visible robot IDs, including voter self",
            actual={"voter_id":voter_id,"visible":visible},
        ))
    digest=hashlib.sha256(
        f"P2J|{seed}|{voter_id}|{round_id}|{votes_per_voter}|{temperature:.17g}"
        .encode("ascii")
    ).digest()
    rng=random.Random(int.from_bytes(digest, "big"))
    counts: dict[tuple[int, int], int]={}
    cumulative_by_task: dict[int, tuple[tuple[float, ...], float]]={}
    for _ in range(votes_per_voter):
        task_id=rng.randrange(num_tasks)
        if task_id not in cumulative_by_task:
            minimum=min(cost_matrix[robot][task_id] for robot in visible)
            subtotal=0.0
            cumulative=[]
            for robot in visible:
                subtotal+=math.exp(-(cost_matrix[robot][task_id]-minimum)/temperature)
                cumulative.append(subtotal)
            cumulative_by_task[task_id]=(tuple(cumulative),subtotal)
        cumulative,total=cumulative_by_task[task_id]
        selected=bisect.bisect_left(cumulative,rng.random()*total)
        robot_id=visible[min(selected,len(visible)-1)]
        key=(task_id,robot_id)
        counts[key]=counts.get(key,0)+1
    if sum(counts.values())!=votes_per_voter:
        raise ProtocolError(Diagnostic(
            owner="optimizer", function="sample_probabilistic_pair_votes",
            category="contract", code="P2J_BALLOT_TICKET_SUM_MISMATCH",
            expected=votes_per_voter, actual=sum(counts.values()),
        ))
    return tuple((task_id,robot_id,count) for (task_id,robot_id),count in sorted(counts.items()))




def compute_p2q_rank_squared_proposal_weights(
    proposals: tuple[tuple[float, tuple[tuple[int, int], ...]], ...],
) -> tuple[float, ...]:
    """Rank 1 receives 1, rank 2 receives 1/4, rank 3 receives 1/9.

    These are existing locally visible K candidate assignments
    sorted by cost and deterministic pair tie breaks, NOT exact K-best.
    No hidden cost rows, global Vote matrix or control packets.
    """
    if not proposals or any(
        not math.isfinite(cost) or (i and (cost,pairs)<proposals[i-1])
        for i,(cost,pairs) in enumerate(proposals)
    ):
        raise ProtocolError(Diagnostic(
            owner="optimizer",
            function="compute_p2q_rank_squared_proposal_weights",
            category="contract",code="P2Q_INVALID_RANKED_PROPOSALS",
            expected="nonempty finite proposals sorted by (cost,pairs)",
            actual=proposals,
        ))
    return tuple(1.0 / (rank * rank)
                 for rank in range(1, len(proposals) + 1))


def apportion_p2q_task_tickets(
    *, visible_robots: tuple[int, ...], weights: tuple[float, ...],
    tickets_per_task: int,
) -> tuple[int, ...]:
    """Largest-remainder vote allocation, integer tickets, ID tie break.

    Each task sends exactly tickets_per_task one-byte candidate IDs on
    the ORIGINAL P2KV wire. Discrete ballots can STILL tie in a
    receiver's aggregated received votes; no uniqueness guarantee.
    """
    if (not visible_robots or len(visible_robots)!=len(weights)
            or len(set(visible_robots))!=len(visible_robots)
            or any(type(robot) is not int or not 0<=robot<=255
                   for robot in visible_robots)
            or type(tickets_per_task) is not int or tickets_per_task<=0
            or any(not isinstance(weight,(int,float))
                   or not math.isfinite(weight) or weight<0
                   for weight in weights)
            or sum(weights)<=0):
        raise ProtocolError(Diagnostic(
            owner="optimizer",function="apportion_p2q_task_tickets",
            category="data",code="P2Q_INVALID_TASK_WEIGHTS",
            expected="unique uint8 visible IDs; positive finite total "
                     "weights; positive integer ticket budget",
            actual={"robots":visible_robots,"weights":weights,
                    "slots":tickets_per_task},
        ))
    total=sum(weights)
    quotas=[tickets_per_task*float(weight)/total for weight in weights]
    whole=[math.floor(q) for q in quotas]
    remaining=tickets_per_task-sum(whole)
    if not 0<=remaining<len(visible_robots)+1:
        raise ProtocolError(Diagnostic(
            owner="optimizer",function="apportion_p2q_task_tickets",
            category="contract",code="P2Q_INVALID_REMAINDER_BUDGET",
            expected="remaining tickets in [0, count of robot IDs]",
            actual=remaining,
        ))
    order=sorted(
        range(len(visible_robots)),
        key=lambda i:(-(quotas[i]-whole[i]),visible_robots[i]),
    )
    for idx in order[:remaining]:
        whole[idx]+=1
    ballot=tuple(robot for robot,count in zip(visible_robots,whole)
                 for _ in range(count))
    if len(ballot)!=tickets_per_task:
        raise ProtocolError(Diagnostic(
            owner="optimizer",function="apportion_p2q_task_tickets",
            category="contract",code="P2Q_APPORTIONMENT_COUNT_MISMATCH",
            expected=tickets_per_task,actual=len(ballot),
        ))
    return ballot



def sample_p2s_adaptive_matching_votes(
    *, cost_matrix: tuple[tuple[float, ...], ...],
    visible_robot_ids: frozenset[int] | set[int] | tuple[int, ...],
    voter_id: int, votes_per_voter: int,
) -> tuple[int, ...]:
    """Local maximum-cardinality min-cost matching plus visibility-based backup.

    For each task: matching edge weight 1, cheapest visible Cost row backup
    weight gamma = (total_robots - visible_count)/(total_robots - 1).
    A task omitted by a partial matching gets the cheapest *visible* candidate.
    Exactly B / tasks uint8 tickets per task; no global ground truth is read.
    """
    robots, tasks = validate_cost_matrix(cost_matrix)
    visible = tuple(sorted(set(visible_robot_ids)))
    if (not visible or voter_id not in visible or
            any(type(r) is not int or not 0 <= r < robots for r in visible) or
            type(votes_per_voter) is not int or votes_per_voter < tasks or
            votes_per_voter % tasks or votes_per_voter > 1184 or robots > 255):
        raise ProtocolError(Diagnostic(
            owner="optimizer", function="sample_p2s_adaptive_matching_votes",
            category="data", code="P2S_INVALID_VISIBLE_SCOPE",
            expected="self-inclusive valid received rows; task-divisible B<=1184",
            actual={"visible":visible,"self":voter_id,"B":votes_per_voter},
        ))
    local = tuple(tuple(float(cost_matrix[robot][t]) for t in range(tasks))
                  for robot in visible)
    local_rows, task_cols = linear_sum_assignment(local)
    matched = {int(task): visible[int(local_row)]
               for local_row, task in zip(local_rows, task_cols)}
    gamma = (robots-len(visible))/max(1,robots-1)
    slots = votes_per_voter//tasks
    ticket_ids: list[int] = []
    for task in range(tasks):
        cheapest = min(visible, key=lambda robot: (cost_matrix[robot][task],robot))
        # No matching proposal for this task is not treated as a zero ballot.
        primary = matched.get(task)
        support = {r: 0.0 for r in visible}
        if primary is not None:
            support[primary] += 1.0
        support[cheapest] += gamma if primary is not None else 1.0
        ticket_ids.extend(apportion_p2q_task_tickets(
            visible_robots=visible,
            weights=tuple(support[r] for r in visible),
            tickets_per_task=slots,
        ))
    if len(ticket_ids) != votes_per_voter:
        raise ProtocolError(Diagnostic(
            owner="optimizer",function="sample_p2s_adaptive_matching_votes",
            category="contract",code="P2S_TICKET_CARDINALITY_MISMATCH",
            expected=votes_per_voter,actual=len(ticket_ids),
        ))
    return tuple(ticket_ids)


def sample_p2k_task_balanced_votes(
    *, cost_matrix: tuple[tuple[float, ...], ...],
    visible_robot_ids: frozenset[int] | set[int] | tuple[int, ...],
    voter_id: int, seed: int, votes_per_voter: int,
    policy: str = "optimized_kbest", k: int = 5,
    epsilon: float = 0.10, temperature: float = 5.0,
    round_id: int = 0,
) -> tuple[int, ...]:
    """Pure P2K local policy: one candidate ID per task-balanced ticket.

    Only cost rows in visible_robot_ids enter the local candidate solver or
    per-task proposal distribution. Candidate solutions are distinct feasible
    perturb-and-MAP assignments, NOT claimed to be exact k-best. Every task
    receives exactly votes_per_voter / num_tasks tickets, including when the
    voter sees too few robots to produce a full assignment.
    """
    num_robots, num_tasks = validate_cost_matrix(
        cost_matrix, allow_tasks_exceed_robots=True,
    )
    rows = tuple(sorted(set(visible_robot_ids)))
    if (policy not in ("cost_softmax", "optimized_kbest", "optimized_rank_square", "adaptive_local_matching")
            or type(votes_per_voter) is not int
            or votes_per_voter < num_tasks or votes_per_voter % num_tasks
            or votes_per_voter > 1184
            or type(k) is not int or not 1 <= k <= 10
            or type(epsilon) not in (int, float)
            or not math.isfinite(epsilon) or not 0 <= epsilon <= 1
            or type(temperature) not in (int, float)
            or not math.isfinite(temperature) or temperature <= 0
            or type(seed) is not int or seed < 0
            or type(round_id) is not int or round_id < 0
            or type(voter_id) is not int or not 0 <= voter_id < num_robots
            or voter_id not in rows or not rows or num_robots > 255
            or any(type(r) is not int or r < 0 or r >= num_robots for r in rows)):
        raise ProtocolError(Diagnostic(
            owner="optimizer", function="sample_p2k_task_balanced_votes",
            category="data", code="P2K_INVALID_LOCAL_VOTE_POLICY",
            expected="known self-inclusive robot rows; valid cost_softmax/optimized_kbest/optimized_rank_square; "
                     "1..10 proposals, epsilon 0..1, positive tau, and task-divisible "
                     "votes up to 1184 in one compact packet",
            actual={"policy":policy,"tickets":votes_per_voter,"k":k,
                    "epsilon":epsilon,"temperature":temperature,"visible":rows,
                    "voter":voter_id,"tasks":num_tasks},
        ))
    if policy == "adaptive_local_matching":
        return sample_p2s_adaptive_matching_votes(
            cost_matrix=cost_matrix, visible_robot_ids=rows,
            voter_id=voter_id, votes_per_voter=votes_per_voter,
        )
    digest = hashlib.sha256(
        f"P2K|{seed}|{round_id}|{voter_id}|{votes_per_voter}|"
        f"{policy}|{k}|{epsilon:.17g}|{temperature:.17g}".encode("ascii")
    ).digest()
    rng = random.Random(int.from_bytes(digest, "big"))
    local = tuple(tuple(float(x) for x in cost_matrix[r]) for r in rows)
    proposals: list[tuple[float, tuple[tuple[int, int], ...]]] = []
    if policy in ("optimized_kbest", "optimized_rank_square"):
        distinct: dict[tuple[tuple[int, int], ...], float] = {}
        # First solution is exact optimal over locally visible rows. The
        # remaining distinct assignments use bounded seeded perturbations.
        # They are approximate near-optimal proposals; no hidden row is read.
        for attempt in range(max(12, k * 16)):
            matrix = (
                local if attempt == 0 else
                tuple(tuple(value + rng.uniform(-temperature, temperature)
                            for value in row) for row in local)
            )
            local_rows, task_cols = linear_sum_assignment(matrix)
            pairs = tuple(sorted(
                (int(task), int(rows[int(r)]))
                for r, task in zip(local_rows, task_cols)
            ))
            if pairs not in distinct:
                distinct[pairs] = sum(
                    float(cost_matrix[robot][task]) for task, robot in pairs
                )
            if len(distinct) >= k:
                break
        proposals = sorted(
            ((total, pairs) for pairs, total in distinct.items()),
            key=lambda entry: (entry[0], entry[1]),
        )[:k]
        if not proposals:
            raise ProtocolError(Diagnostic(
                owner="optimizer", function="sample_p2k_task_balanced_votes",
                category="planning", code="P2K_NO_VISIBLE_PROPOSAL",
                expected="at least one local maximum-cardinality assignment",
                actual={"visible":rows,"tasks":num_tasks},
            ))
    proposal_weights: list[float] = []
    if proposals:
        best = proposals[0][0]
        cardinality = len(proposals[0][1])
        if any(len(pairs) != cardinality for _, pairs in proposals):
            raise ProtocolError(Diagnostic(
                owner="optimizer", function="sample_p2k_task_balanced_votes",
                category="contract", code="P2K_INCOMPARABLE_PROPOSALS",
                expected=cardinality, actual=[len(pairs) for _,pairs in proposals],
            ))
        proposal_weights = (
            list(compute_p2q_rank_squared_proposal_weights(
                tuple(proposals),
            ))
            if policy == "optimized_rank_square"
            else [
                math.exp(-max(0.0, cost - best) / (cardinality * temperature))
                for cost, _pairs in proposals
            ]
        )
    slots = votes_per_voter // num_tasks
    ballot: list[int] = []
    for task_id in range(num_tasks):
        minimum = min(local[ri][task_id] for ri in range(len(rows)))
        base = [
            math.exp(-(local[ri][task_id] - minimum) / temperature)
            for ri in range(len(rows))
        ]
        base_total = sum(base)
        support = {r: 0.0 for r in rows}
        if proposals:
            for weight, (_cost, pairs) in zip(proposal_weights, proposals):
                for task, robot in pairs:
                    if task == task_id:
                        support[robot] += weight
                        break
        support_total = sum(support.values())
        if support_total:
            weights = [
                (1.0 - epsilon) * support[robot] / support_total
                + epsilon * base[ri] / base_total
                for ri, robot in enumerate(rows)
            ]
        else:
            # The locally optimized partial assignments may omit this task.
            # Falling back to *visible* task-cost probabilities retains
            # support without fabricating a missing candidate or Cost row.
            weights = [weight / base_total for weight in base]
        if policy == "optimized_rank_square":
            ballot.extend(apportion_p2q_task_tickets(
                visible_robots=rows,
                weights=tuple(weights),
                tickets_per_task=slots,
            ))
        else:
            ballot.extend(rng.choices(rows, weights=weights, k=slots))
    if len(ballot) != votes_per_voter:
        raise ProtocolError(Diagnostic(
            owner="optimizer", function="sample_p2k_task_balanced_votes",
            category="contract", code="P2K_TICKET_TOTAL_MISMATCH",
            expected=votes_per_voter, actual=len(ballot),
        ))
    return tuple(ballot)


def solve_sequential_greedy_reference(
    cost_matrix: tuple[tuple[float, ...], ...],
) -> AssignmentSolution:
    """Offline full-information oracle for ascending-task sequential Greedy.

    Unlike Hungarian, this is not globally optimal. It is only used to
    assess whether lossy-vote Greedy reproduced the *Greedy* decision rule.
    """
    num_robots, num_tasks = validate_cost_matrix(cost_matrix)
    available = set(range(num_robots))
    pairs: list[tuple[int, int]] = []
    for task_id in range(num_tasks):
        robot_id = min(
            available, key=lambda r: (cost_matrix[r][task_id], r)
        )
        pairs.append((robot_id, task_id))
        available.remove(robot_id)
    return AssignmentSolution(
        assigned_pairs=tuple(pairs),
        total_cost=float(sum(cost_matrix[r][t] for r, t in pairs)),
    )

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import gzip
import math
from pathlib import Path
import statistics
import subprocess

from democracy_mrta.coordination import (
    MultiRoundRetirementResult,
    simulate_democracy_hungarian_retirement,
)
from democracy_mrta.diagnostics import Diagnostic, ProtocolError
from democracy_mrta.metrics import (
    evaluate_assignment_correctness,
    optimality_gap_percent,
)
from democracy_mrta.network import (
    BernoulliLossSampler,
    EmpiricalLatencySampler,
    ensure_rady_dataset,
    load_rady_latency_profile,
    summarize_latency_profile,
    validate_packet_loss_probability,
)
from democracy_mrta.optimizer import (
    solve_hungarian_assignment,
    solve_sequential_greedy_reference,
)
from democracy_mrta.scenario import generate_e0_scenario
from experiments.run_e2 import parse_probabilities, write_csv


DEFAULT_COST_LOSSES = tuple(i / 100 for i in range(0, 71, 2))



def build_retirement_loss_conditions(
    *,
    cost_losses: tuple[float, ...],
    vote_losses: tuple[float, ...],
    pairing: str,
) -> tuple[tuple[float, float], ...]:
    """Choose independent grid or genuinely equal cost/vote loss pairs."""
    if not cost_losses or not vote_losses:
        raise ProtocolError(
            Diagnostic(
                owner="experiments.run_e2_retirement",
                function="build_retirement_loss_conditions",
                category="data",
                code="EMPTY_PACKET_LOSS_SWEEP",
                expected="nonempty cost and vote loss axes",
                actual=(cost_losses, vote_losses),
            )
        )
    for probability in (*cost_losses, *vote_losses):
        validate_packet_loss_probability(probability)

    if pairing not in ("grid", "diagonal"):
        raise ProtocolError(
            Diagnostic(
                owner="experiments.run_e2_retirement",
                function="build_retirement_loss_conditions",
                category="data",
                code="INVALID_PACKET_LOSS_PAIRING",
                expected=("grid", "diagonal"),
                actual=pairing,
            )
        )
    if pairing == "diagonal":
        if cost_losses != vote_losses:
            raise ProtocolError(
                Diagnostic(
                    owner="experiments.run_e2_retirement",
                    function="build_retirement_loss_conditions",
                    category="contract",
                    code="DIAGONAL_LOSS_AXES_DIFFER",
                    expected=cost_losses,
                    actual=vote_losses,
                    details="diagonal requires p_cost_loss = p_vote_loss at every point",
                )
            )
        conditions = tuple(zip(cost_losses, vote_losses))
    else:
        conditions = tuple(
            (cost, vote) for cost in cost_losses for vote in vote_losses
        )

    if len(conditions) != len(set(conditions)):
        raise ProtocolError(
            Diagnostic(
                owner="experiments.run_e2_retirement",
                function="build_retirement_loss_conditions",
                category="data",
                code="DUPLICATE_PACKET_LOSS_CONDITION",
                expected="unique (p_cost_loss, p_vote_loss) conditions",
                actual=conditions,
            )
        )
    return conditions


def retirement_transport_stage_metrics(
    result: MultiRoundRetirementResult,
) -> dict[str, float | int]:
    """Observe real delivery outcomes without changing cost or vote sampling."""
    cost_attempts = cost_drops = vote_attempts = vote_drops = 0
    for trace in result.rounds:
        for observation in trace.coordination.deliveries:
            if observation.phase == "cost":
                cost_attempts += 1
                cost_drops += int(not observation.delivered)
            elif observation.phase == "vote":
                vote_attempts += 1
                vote_drops += int(not observation.delivered)
            else:
                raise ProtocolError(
                    Diagnostic(
                        owner="experiments.run_e2_retirement",
                        function="retirement_transport_stage_metrics",
                        category="contract",
                        code="UNKNOWN_RETIREMENT_DELIVERY_PHASE",
                        expected=("cost", "vote"),
                        actual=observation.phase,
                    )
                )

    if (
        cost_attempts + vote_attempts
        != result.lossy_delivered + result.lossy_dropped
        or cost_drops + vote_drops != result.lossy_dropped
    ):
        raise ProtocolError(
            Diagnostic(
                owner="experiments.run_e2_retirement",
                function="retirement_transport_stage_metrics",
                category="contract",
                code="RETIREMENT_DELIVERY_TOTAL_MISMATCH",
                expected=(result.lossy_delivered, result.lossy_dropped),
                actual=(
                    cost_attempts + vote_attempts - cost_drops - vote_drops,
                    cost_drops + vote_drops,
                ),
            )
        )
    # A single-task Greedy epoch generates one ballot per eligible voter;
    # self-votes are counted locally and deliberately have no transport event.
    voter_ballots = sum(len(trace.active_robot_ids) for trace in result.rounds)
    self_votes = voter_ballots - vote_attempts
    if self_votes < 0:
        raise ProtocolError(
            Diagnostic(
                owner="experiments.run_e2_retirement",
                function="retirement_transport_stage_metrics",
                category="contract",
                code="RETIREMENT_NEGATIVE_SELF_VOTE_COUNT",
                expected="self_votes >= 0",
                actual=self_votes,
            )
        )
    return {
        "cost_packet_attempts": cost_attempts,
        "cost_packet_dropped": cost_drops,
        "observed_cost_drop_rate": cost_drops / cost_attempts if cost_attempts else 0.0,
        "remote_vote_attempts": vote_attempts,
        "remote_vote_dropped": vote_drops,
        "observed_vote_drop_rate": vote_drops / vote_attempts if vote_attempts else 0.0,
        "self_votes": self_votes,
        "quorum_failed_attempts": sum(
            int(not trace.newly_committed_pairs) for trace in result.rounds
        ),
    }

def read_retirement_revision() -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"], text=True,
    ).strip()


def retirement_result_row(
    *,
    seed: int,
    robots: int,
    tasks: int,
    p_cost_loss: float,
    p_vote_loss: float,
    max_rounds: int,
    oracle,
    greedy_oracle,
    result: MultiRoundRetirementResult,
    git_sha: str,
    timestamp: str,
) -> dict[str, object]:
    correctness = evaluate_assignment_correctness(
        assigned_pairs=result.assigned_pairs,
        oracle_assignment=oracle,
        total_tasks=tasks,
    )
    greedy_correctness = evaluate_assignment_correctness(
        assigned_pairs=result.assigned_pairs,
        oracle_assignment=greedy_oracle,
        total_tasks=tasks,
    )
    first = result.rounds[0].coordination
    first_committed = first.assigned_pairs
    greedy_by_task = {task: robot for robot, task in greedy_oracle.assigned_pairs}
    first_greedy_matches = sum(
        greedy_by_task[task] == robot for robot, task in first_committed
    )
    transport = retirement_transport_stage_metrics(result)
    full = result.full_assignment_success
    gap = (
        optimality_gap_percent(result.total_cost, oracle.total_cost)
        if full else float("nan")
    )
    greedy_gap = (
        optimality_gap_percent(result.total_cost, greedy_oracle.total_cost)
        if full else float("nan")
    )
    return {
        "timestamp_utc": timestamp,
        "git_sha": git_sha,
        "seed": seed,
        "robots": robots,
        "tasks": tasks,
        "p_cost_loss": p_cost_loss,
        "p_vote_loss": p_vote_loss,
        "max_rounds": max_rounds,
        "method": result.method,
        "local_optimizer": "greedy_min_visible_cost_per_task",
        "task_order": "ascending_task_id_with_failed_tasks_rotated",
        "cost_exchange_count": 1,
        "first_task_vote_success": int(bool(first_committed)),
        "first_task_matches_full_greedy": first_greedy_matches,
        "committed_tasks": result.committed_tasks,
        "task_commit_rate": result.task_commit_rate,
        "correct_committed_tasks": correctness.correct_committed_tasks,
        "incorrect_committed_tasks": correctness.incorrect_committed_tasks,
        "correct_executor_rate": correctness.correct_executor_rate,
        "greedy_correct_executor_rate": greedy_correctness.correct_executor_rate,
        "greedy_correctness_among_committed": greedy_correctness.correctness_among_committed,
        "correctness_among_committed": correctness.correctness_among_committed,
        "full_assignment_success": int(full),
        "optimal_solution": int(full and abs(gap) <= 1e-9),
        "total_cost": result.total_cost,
        "oracle_cost": oracle.total_cost,
        "greedy_reference_cost": greedy_oracle.total_cost,
        "optimality_gap_percent_successful": gap,
        "greedy_gap_percent_successful": greedy_gap,
        "rounds_executed": len(result.rounds),
        "rounds_with_commits": sum(
            bool(round_trace.newly_committed_pairs) for round_trace in result.rounds
        ),
        "remaining_tasks": len(result.remaining_task_ids),
        "total_elapsed_ms": result.global_agreement_ms,
        "logical_message_count": result.logical_message_count,
        "payload_bytes": result.payload_bytes,
        "lossy_delivered": result.lossy_delivered,
        "lossy_dropped": result.lossy_dropped,
        **transport,
        "safety_failures": 0,
    }


def retirement_round_rows(
    *,
    seed: int,
    p_cost_loss: float,
    p_vote_loss: float,
    result: MultiRoundRetirementResult,
) -> list[dict[str, object]]:
    return [
        {
            "seed": seed,
            "p_cost_loss": p_cost_loss,
            "p_vote_loss": p_vote_loss,
            "round_id": item.round_id,
            "active_robot_count": len(item.active_robot_ids),
            "pending_task_count": len(item.pending_task_ids),
            "voted_task_id": item.voted_task_id,
            "quorum": item.quorum,
            "new_committed_tasks": len(item.newly_committed_pairs),
            "newly_committed_pairs": repr(item.newly_committed_pairs),
            "active_robot_ids": repr(item.active_robot_ids),
            "pending_task_ids": repr(item.pending_task_ids),
            "time_start_ms": item.elapsed_start_ms,
            "time_end_ms": item.elapsed_end_ms,
            "logical_message_count": item.coordination.logical_message_count,
            "lossy_delivered": item.coordination.lossy_delivered,
            "lossy_dropped": item.coordination.lossy_dropped,
        }
        for item in result.rounds
    ]


def summarize_retirement_results(
    rows: list[dict[str, object]],
) -> list[dict[str, object]]:
    groups = sorted({(float(r["p_cost_loss"]), float(r["p_vote_loss"])) for r in rows})
    summary: list[dict[str, object]] = []
    for cost_loss, vote_loss in groups:
        selected = [
            r for r in rows
            if float(r["p_cost_loss"]) == cost_loss
            and float(r["p_vote_loss"]) == vote_loss
        ]
        gaps = [
            float(r["optimality_gap_percent_successful"])
            for r in selected
            if math.isfinite(float(r["optimality_gap_percent_successful"]))
        ]
        greedy_gaps = [
            float(r["greedy_gap_percent_successful"])
            for r in selected
            if math.isfinite(float(r["greedy_gap_percent_successful"]))
        ]

        def mean(key: str) -> float:
            return statistics.fmean(float(r[key]) for r in selected)

        def observed_loss_rate(*, dropped_key: str, attempts_key: str) -> float:
            dropped = sum(int(r[dropped_key]) for r in selected)
            attempts = sum(int(r[attempts_key]) for r in selected)
            return dropped / attempts if attempts else 0.0

        summary.append({
            "robots": selected[0]["robots"],
            "tasks": selected[0]["tasks"],
            "seeds": len(selected),
            "p_cost_loss": cost_loss,
            "p_vote_loss": vote_loss,
            "max_rounds": selected[0]["max_rounds"],
            "method": "democracy_greedy_retirement",
            "local_optimizer": "greedy_min_visible_cost_per_task",
            "mean_first_task_vote_success": mean("first_task_vote_success"),
            "mean_first_task_matches_full_greedy": mean("first_task_matches_full_greedy"),
            "mean_task_commit_rate": mean("task_commit_rate"),
            "mean_correct_executor_rate": mean("correct_executor_rate"),
            "mean_greedy_correct_executor_rate": mean("greedy_correct_executor_rate"),
            "mean_greedy_correctness_among_committed": (
                statistics.fmean(
                    float(r["greedy_correctness_among_committed"])
                    for r in selected
                    if math.isfinite(float(r["greedy_correctness_among_committed"]))
                )
                if any(
                    math.isfinite(float(r["greedy_correctness_among_committed"]))
                    for r in selected
                )
                else float("nan")
            ),
            "mean_correctness_among_committed": (
                statistics.fmean(
                    float(r["correctness_among_committed"]) for r in selected
                    if math.isfinite(float(r["correctness_among_committed"]))
                )
                if any(
                    math.isfinite(float(r["correctness_among_committed"]))
                    for r in selected
                )
                else float("nan")
            ),
            "full_assignment_success_rate": mean("full_assignment_success"),
            "optimal_solution_rate": mean("optimal_solution"),
            "mean_optimality_gap_percent_successful": (
                statistics.fmean(gaps) if gaps else float("nan")
            ),
            "mean_greedy_gap_percent_successful": (
                statistics.fmean(greedy_gaps) if greedy_gaps else float("nan")
            ),
            "mean_rounds_executed": mean("rounds_executed"),
            "mean_rounds_with_commits": mean("rounds_with_commits"),
            "mean_elapsed_ms": mean("total_elapsed_ms"),
            "mean_logical_message_count": mean("logical_message_count"),
            "mean_payload_bytes": mean("payload_bytes"),
            "mean_lossy_dropped": mean("lossy_dropped"),
            "observed_cost_drop_rate": observed_loss_rate(
                dropped_key="cost_packet_dropped", attempts_key="cost_packet_attempts"
            ),
            "observed_vote_drop_rate": observed_loss_rate(
                dropped_key="remote_vote_dropped", attempts_key="remote_vote_attempts"
            ),
            "mean_remote_vote_attempts": mean("remote_vote_attempts"),
            "mean_remote_vote_dropped": mean("remote_vote_dropped"),
            "mean_self_votes": mean("self_votes"),
            "mean_quorum_failed_attempts": mean("quorum_failed_attempts"),
            "safety_failures": int(sum(int(r["safety_failures"]) for r in selected)),
        })
    return summary


def write_retirement_audit_events(
    writer: csv.DictWriter,
    *,
    seed: int,
    p_cost_loss: float,
    p_vote_loss: float,
    result: MultiRoundRetirementResult,
) -> None:
    for trace in result.rounds:
        for event in trace.coordination.events:
            writer.writerow({
                "kind": "logical_message",
                "seed": seed,
                "p_cost_loss": p_cost_loss,
                "p_vote_loss": p_vote_loss,
                "round_id": trace.round_id,
                "active_robots": len(trace.active_robot_ids),
                "quorum": trace.quorum,
                "phase": event.phase,
                "sender_id": event.sender_id,
                "receiver_id": event.receiver_id,
                "task_id": event.task_id if event.task_id is not None else "",
                "delivered": "",
                "send_ms": trace.elapsed_start_ms + event.send_time_ms,
                "arrival_ms": trace.elapsed_start_ms + event.arrival_time_ms,
            })
        for obs in trace.coordination.deliveries:
            writer.writerow({
                "kind": "delivery",
                "seed": seed,
                "p_cost_loss": p_cost_loss,
                "p_vote_loss": p_vote_loss,
                "round_id": trace.round_id,
                "active_robots": len(trace.active_robot_ids),
                "quorum": trace.quorum,
                "phase": obs.phase,
                "sender_id": obs.sender_id,
                "receiver_id": obs.receiver_id,
                "task_id": obs.task_id if obs.task_id is not None else "",
                "delivered": int(obs.delivered),
                "send_ms": "",
                "arrival_ms": (
                    trace.elapsed_start_ms + obs.arrival_time_ms
                    if obs.arrival_time_ms is not None else ""
                ),
            })


def run_retirement_experiment(
    *,
    robots: int,
    tasks: int,
    seeds: int,
    cost_losses: tuple[float, ...],
    p_vote_loss: float,
    max_rounds: int,
    dataset_path: Path,
    output_root: Path,
    allow_download: bool,
    vote_losses: tuple[float, ...] | None = None,
    loss_pairing: str = "grid",
) -> list[dict[str, object]]:
    if seeds < 1:
        raise ValueError("seeds must be >= 1")
    conditions = build_retirement_loss_conditions(
        cost_losses=cost_losses,
        vote_losses=(p_vote_loss,) if vote_losses is None else vote_losses,
        pairing=loss_pairing,
    )

    dataset = ensure_rady_dataset(dataset_path, allow_download=allow_download)
    profile = load_rady_latency_profile(dataset)
    phase_timeout_ms = float(summarize_latency_profile(profile)["max_ms"])
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    git_sha = read_retirement_revision()

    output_root.mkdir(parents=True, exist_ok=True)
    raw_path = output_root / "raw" / f"retirement_{timestamp}.csv"
    round_path = output_root / "rounds" / f"retirement_rounds_{timestamp}.csv"
    audit_path = output_root / "events" / f"retirement_audit_{timestamp}.csv.gz"
    summary_path = output_root / "summary.csv"
    raw_rows: list[dict[str, object]] = []
    round_rows: list[dict[str, object]] = []
    audit_path.parent.mkdir(parents=True, exist_ok=True)

    fields = [
        "kind", "seed", "p_cost_loss", "p_vote_loss", "round_id",
        "active_robots", "quorum", "phase", "sender_id", "receiver_id",
        "task_id", "delivered", "send_ms", "arrival_ms",
    ]
    with gzip.open(audit_path, "wt", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()

        for seed in range(seeds):
            scenario = generate_e0_scenario(seed, robots, tasks)
            oracle = solve_hungarian_assignment(scenario.cost_matrix)
            greedy_oracle = solve_sequential_greedy_reference(scenario.cost_matrix)

            for p_loss, vote_loss in conditions:
                result = simulate_democracy_hungarian_retirement(
                    cost_matrix=scenario.cost_matrix,
                    sampler=EmpiricalLatencySampler(profile, seed=seed),
                    loss_sampler=BernoulliLossSampler(seed=seed),
                    p_loss=p_loss,
                    p_vote_loss=vote_loss,
                    phase_timeout_ms=phase_timeout_ms,
                    max_rounds=max_rounds,
                    voting_strategy="greedy_task",
                )
                raw_rows.append(retirement_result_row(
                    seed=seed, robots=robots, tasks=tasks,
                    p_cost_loss=p_loss, p_vote_loss=vote_loss,
                    max_rounds=max_rounds, oracle=oracle,
                    greedy_oracle=greedy_oracle, result=result,
                    git_sha=git_sha, timestamp=timestamp,
                ))
                round_rows.extend(retirement_round_rows(
                    seed=seed, p_cost_loss=p_loss,
                    p_vote_loss=vote_loss, result=result,
                ))
                if seed == 0:
                    write_retirement_audit_events(
                        writer, seed=seed, p_cost_loss=p_loss,
                        p_vote_loss=vote_loss, result=result,
                    )
            if (seed + 1) % 10 == 0 or seed + 1 == seeds:
                print(f"GREEDY_RETIREMENT_PROGRESS seeds={seed + 1}/{seeds}", flush=True)

    write_csv(raw_path, raw_rows)
    write_csv(round_path, round_rows)
    summary_rows = summarize_retirement_results(raw_rows)
    write_csv(summary_path, summary_rows)

    print(f"RETIREMENT_LOSS_PAIRING={loss_pairing}")
    print(f"RETIREMENT_LOSS_CONDITIONS={len(conditions)}")
    print(f"RETIREMENT_TOTAL_SCENARIOS={len(conditions) * seeds}")
    print(f"RETIREMENT_HEAD={git_sha}")
    print(f"RETIREMENT_RAW={raw_path}")
    print(f"RETIREMENT_ROUNDS={round_path}")
    print(f"RETIREMENT_EVENTS={audit_path}")
    print(f"RETIREMENT_SUMMARY={summary_path}")
    for row in summary_rows:
        print(
            "RETIREMENT_RESULT "
            f"robots={row['robots']} tasks={row['tasks']} "
            f"p_cost_loss={float(row['p_cost_loss']):.2f} "
            f"p_vote_loss={float(row['p_vote_loss']):.2f} "
            f"first_task_success={float(row['mean_first_task_vote_success']):.6f} "
            f"eventual_commit={float(row['mean_task_commit_rate']):.6f} "
            f"hungarian_cer={float(row['mean_correct_executor_rate']):.6f} "
            f"greedy_cer={float(row['mean_greedy_correct_executor_rate']):.6f} "
            f"full_success={float(row['full_assignment_success_rate']):.6f} "
            f"global_optimal_rate={float(row['optimal_solution_rate']):.6f} "
            f"global_gap={float(row['mean_optimality_gap_percent_successful']):.4f}% "
            f"greedy_gap={float(row['mean_greedy_gap_percent_successful']):.4f}% "
            f"rounds_mean={float(row['mean_rounds_executed']):.2f} "
            f"vote_drop_actual={float(row['observed_vote_drop_rate']):.4f} "
            f"cost_drop_actual={float(row['observed_cost_drop_rate']):.4f} "
            f"elapsed_ms={float(row['mean_elapsed_ms']):.2f} "
            f"safety_failures={row['safety_failures']}"
        )
    return summary_rows


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Sequential Greedy task voting with executor retirement"
    )
    parser.add_argument("--robots", type=int, default=100)
    parser.add_argument("--tasks", type=int, default=50)
    parser.add_argument("--seeds", type=int, default=100)
    parser.add_argument(
        "--cost-loss-probabilities", type=parse_probabilities,
        default=DEFAULT_COST_LOSSES,
    )
    parser.add_argument("--vote-loss-probability", type=float, default=0.0)
    parser.add_argument("--max-rounds", type=int, default=None)
    parser.add_argument(
        "--dataset", type=Path,
        default=Path("data/external/rady/perama_range_testing.json"),
    )
    parser.add_argument("--no-download", action="store_true")
    parser.add_argument(
        "--output-root", type=Path,
        default=Path("results/e2_greedy_retirement_100r50t"),
    )
    args = parser.parse_args()

    max_rounds = args.max_rounds if args.max_rounds is not None else 2 * args.tasks
    print(
        f"GREEDY_RETIREMENT_CONFIG tasks={args.tasks} max_rounds={max_rounds} "
        f"min_rounds_without_retries={args.tasks} initial_cost_exchange_once=true",
        flush=True,
    )
    run_retirement_experiment(
        robots=args.robots,
        tasks=args.tasks,
        seeds=args.seeds,
        cost_losses=args.cost_loss_probabilities,
        p_vote_loss=args.vote_loss_probability,
        max_rounds=max_rounds,
        dataset_path=args.dataset,
        output_root=args.output_root,
        allow_download=not args.no_download,
    )


if __name__ == "__main__":
    main()

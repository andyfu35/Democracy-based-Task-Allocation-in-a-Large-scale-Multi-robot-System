from __future__ import annotations

import argparse
from collections import defaultdict
from pathlib import Path

from democracy_mrta.coordination import simulate_democracy_hungarian_lossy
from democracy_mrta.metrics import evaluate_e2_vote_audit
from democracy_mrta.network import (
    BernoulliLossSampler,
    EmpiricalLatencySampler,
    ensure_rady_dataset,
    load_rady_latency_profile,
    summarize_latency_profile,
    validate_packet_loss_probability,
)
from democracy_mrta.optimizer import solve_hungarian_assignment
from democracy_mrta.scenario import generate_e0_scenario
from experiments.run_e2 import write_csv


def add_seed_column(
    seed: int,
    rows: tuple[dict[str, int | float], ...],
) -> list[dict[str, int | float]]:
    return [{"seed": seed, **row} for row in rows]


def aggregate_robot_rows(
    *,
    voter_rows: list[dict[str, int | float]],
    seeds: int,
) -> list[dict[str, int | float]]:
    totals: dict[int, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for row in voter_rows:
        voter_id = int(row["voter_id"])
        for field in (
            "visible_rows", "proposals", "oracle_matching_proposals",
            "incorrect_proposals", "delivered_votes", "delivered_correct_votes",
            "remote_vote_attempts", "remote_vote_delivered",
            "remote_vote_dropped", "self_votes",
        ):
            totals[voter_id][field] += float(row[field])

    output: list[dict[str, int | float]] = []
    for voter_id, total in sorted(totals.items()):
        proposals = total["proposals"]
        delivered = total["delivered_votes"]
        attempts = total["remote_vote_attempts"]
        output.append({
            "voter_id": voter_id,
            "seeds": seeds,
            "mean_visible_rows": total["visible_rows"] / seeds,
            "mean_proposals": proposals / seeds,
            "raw_correct_vote_rate": (
                total["oracle_matching_proposals"] / proposals if proposals else 0.0
            ),
            "mean_remote_vote_attempts": attempts / seeds,
            "remote_delivery_rate": (
                total["remote_vote_delivered"] / attempts if attempts else 0.0
            ),
            "mean_remote_vote_dropped": total["remote_vote_dropped"] / seeds,
            "mean_self_votes": total["self_votes"] / seeds,
            "mean_delivered_votes": delivered / seeds,
            "mean_delivered_correct_votes": total["delivered_correct_votes"] / seeds,
        })
    return output


def aggregate_seed_summaries(
    *,
    seed_rows: list[dict[str, int | float]],
) -> dict[str, int | float]:
    total_seeds = len(seed_rows)
    total_tasks = sum(int(row["tasks"]) for row in seed_rows)
    raw_votes = sum(int(row["raw_total_votes"]) for row in seed_rows)
    raw_correct = sum(int(row["raw_correct_votes"]) for row in seed_rows)
    received_votes = sum(int(row["received_total_votes"]) for row in seed_rows)
    received_correct = sum(int(row["received_correct_votes"]) for row in seed_rows)
    remote_attempts = sum(int(row["remote_vote_attempts"]) for row in seed_rows)
    remote_delivered = sum(int(row["remote_vote_delivered"]) for row in seed_rows)

    def task_rate(key: str) -> float:
        return sum(int(row[key]) for row in seed_rows) / total_tasks

    return {
        "seeds": total_seeds,
        "robots": int(seed_rows[0]["robots"]),
        "tasks": int(seed_rows[0]["tasks"]),
        "p_loss": float(seed_rows[0]["p_loss"]),
        "quorum": int(seed_rows[0]["quorum"]),
        "mean_visible_rows": (
            sum(float(row["visible_rows_mean"]) for row in seed_rows) / total_seeds
        ),
        "raw_correct_vote_rate": raw_correct / raw_votes if raw_votes else 0.0,
        "received_correct_vote_rate": (
            received_correct / received_votes if received_votes else 0.0
        ),
        "remote_vote_delivery_rate": (
            remote_delivered / remote_attempts if remote_attempts else 0.0
        ),
        "mean_raw_correct_votes_per_task": raw_correct / total_tasks,
        "mean_received_correct_votes_per_task": received_correct / total_tasks,
        "mean_received_votes_per_task": received_votes / total_tasks,
        "task_rate_raw_any_candidate_quorum": task_rate("tasks_with_raw_quorum"),
        "task_rate_raw_oracle_quorum": task_rate("tasks_with_oracle_raw_quorum"),
        "task_rate_received_any_candidate_quorum": task_rate(
            "tasks_with_received_quorum"
        ),
        "task_rate_received_oracle_quorum": task_rate(
            "tasks_with_oracle_received_quorum"
        ),
        "task_rate_vote_transport_destroyed_quorum": task_rate(
            "tasks_lost_quorum_to_vote_transport"
        ),
        "task_rate_no_raw_majority": (
            1.0 - task_rate("tasks_with_raw_quorum")
        ),
        "task_commit_rate": task_rate("committed_tasks"),
    }


def run_vote_audit(
    *,
    robots: int,
    tasks: int,
    p_loss: float,
    seeds: int,
    candidate_audit_seed: int,
    output_root: Path,
    dataset_path: Path,
    allow_download: bool,
) -> dict[str, int | float]:
    p_loss = validate_packet_loss_probability(p_loss)
    dataset = ensure_rady_dataset(dataset_path, allow_download=allow_download)
    profile = load_rady_latency_profile(dataset)
    phase_timeout_ms = float(summarize_latency_profile(profile)["max_ms"])

    seed_rows: list[dict[str, int | float]] = []
    voter_rows: list[dict[str, int | float]] = []
    task_rows: list[dict[str, int | float]] = []
    candidates_selected: list[dict[str, int | float]] = []
    ballots_selected: list[dict[str, int | float]] = []

    for seed in range(seeds):
        scenario = generate_e0_scenario(seed, robots, tasks)
        oracle = solve_hungarian_assignment(scenario.cost_matrix)
        result = simulate_democracy_hungarian_lossy(
            cost_matrix=scenario.cost_matrix,
            sampler=EmpiricalLatencySampler(profile, seed=seed),
            loss_sampler=BernoulliLossSampler(seed=seed),
            p_loss=p_loss,
            phase_timeout_ms=phase_timeout_ms,
            capture_vote_audit=True,
        )
        audit = evaluate_e2_vote_audit(
            result=result,
            oracle_assignment=oracle,
            num_robots=robots,
            num_tasks=tasks,
        )
        seed_rows.append({"seed": seed, "p_loss": p_loss, **audit.summary})
        voter_rows.extend(add_seed_column(seed, audit.voters))
        task_rows.extend(add_seed_column(seed, audit.tasks))
        if seed == candidate_audit_seed:
            candidates_selected = add_seed_column(seed, audit.candidates)
            ballots_selected = add_seed_column(seed, audit.ballots)

    summary = aggregate_seed_summaries(seed_rows=seed_rows)
    output_paths = {
        "summary": output_root / "summary.csv",
        "seed": output_root / "seed_summary.csv",
        "voter": output_root / "voters_by_seed.csv",
        "voter_summary": output_root / "voters_summary.csv",
        "task": output_root / "tasks_by_seed.csv",
        "candidate": output_root / f"candidates_seed{candidate_audit_seed:03d}.csv",
        "ballot": output_root / f"ballots_seed{candidate_audit_seed:03d}.csv",
    }
    write_csv(output_paths["summary"], [summary])
    write_csv(output_paths["seed"], seed_rows)
    write_csv(output_paths["voter"], voter_rows)
    write_csv(
        output_paths["voter_summary"],
        aggregate_robot_rows(voter_rows=voter_rows, seeds=seeds),
    )
    write_csv(output_paths["task"], task_rows)
    if candidates_selected:
        write_csv(output_paths["candidate"], candidates_selected)
    if ballots_selected:
        write_csv(output_paths["ballot"], ballots_selected)

    for label, path in output_paths.items():
        if label == "candidate" and not candidates_selected:
            continue
        if label == "ballot" and not ballots_selected:
            continue
        print(f"E2_VOTE_AUDIT_{label.upper()}={path}")
    for key, value in summary.items():
        print(f"E2_VOTE_AUDIT {key}={value}")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Audit each E2 Democracy voter and task from actual protocol state"
    )
    parser.add_argument("--robots", type=int, default=100)
    parser.add_argument("--tasks", type=int, default=50)
    parser.add_argument("--p-loss", type=float, default=0.30)
    parser.add_argument("--seeds", type=int, default=100)
    parser.add_argument("--candidate-audit-seed", type=int, default=0)
    parser.add_argument(
        "--output-root", type=Path, default=Path("results/e2_vote_audit")
    )
    parser.add_argument(
        "--dataset", type=Path,
        default=Path("data/external/rady/perama_range_testing.json"),
    )
    parser.add_argument("--no-download", action="store_true")
    args = parser.parse_args()

    if args.seeds <= 0:
        parser.error("--seeds must be positive")
    if args.candidate_audit_seed < 0 or args.candidate_audit_seed >= args.seeds:
        parser.error("--candidate-audit-seed must be in range [0, seeds)")
    run_vote_audit(
        robots=args.robots,
        tasks=args.tasks,
        p_loss=args.p_loss,
        seeds=args.seeds,
        candidate_audit_seed=args.candidate_audit_seed,
        output_root=args.output_root,
        dataset_path=args.dataset,
        allow_download=not args.no_download,
    )


if __name__ == "__main__":
    main()

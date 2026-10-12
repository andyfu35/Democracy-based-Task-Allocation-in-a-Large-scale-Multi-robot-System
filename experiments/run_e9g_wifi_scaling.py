"""E9G Voting-only 1:1 scaling: original protocol + opt-in shared-medium sensitivity.

NOT ns-3 and NOT real RF timing. Published Rady 2024 application-delay
samples are de-overlapped against a modeled reference frame. Bianchi 2000
motivates backoff; NIST IR 8506 and Liu/Choi 2023 inform limitations and
future validation. Never describe modeled PHY rates as measured Rady rates.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import statistics
import subprocess

from democracy_mrta.coordination import simulate_democracy_hungarian_retirement
from democracy_mrta.diagnostics import Diagnostic, ProtocolError
from democracy_mrta.network import (
    BernoulliLossSampler, EmpiricalLatencySampler, WifiCausalTimingSampler,
    WifiTimingConfig, ensure_rady_dataset, load_rady_latency_profile,
    percentile, summarize_latency_profile, RADY_SOURCE_BLOB_SHA,
    RADY_SOURCE_COMMIT,
)
from democracy_mrta.scenario import generate_e0_scenario
from democracy_mrta.task_information import (
    broadcast_task_information, reconstruct_local_cost_rows,
    require_local_source_consistency,
)

OWNER = "experiments.run_e9g_wifi_scaling"
DEFAULT_SIZES = tuple(range(5, 101, 5))
DEFAULT_RATES = (144.0, 600.0, 1200.0)
DEFAULT_ROOT = Path("results/e9g_wifi_scaling")


def parse_e9g_sizes(value: str) -> tuple[int, ...]:
    try:
        sizes = tuple(int(x.strip()) for x in value.split(","))
    except (TypeError, ValueError) as exc:
        raise ProtocolError(Diagnostic(
            owner=OWNER, function="parse_e9g_sizes", category="data",
            code="E9G_INVALID_SIZE_GRID", expected="ascending unique integers 2..100",
            actual=value,
        )) from exc
    if not sizes or sizes != tuple(sorted(set(sizes))) or any(
        not 2 <= n <= 100 for n in sizes
    ):
        raise ProtocolError(Diagnostic(
            owner=OWNER, function="parse_e9g_sizes", category="data",
            code="E9G_INVALID_SIZE_GRID", expected="ascending unique integers 2..100",
            actual=value,
        ))
    return sizes


def parse_e9g_rates(value: str) -> tuple[float, ...]:
    try:
        rates = tuple(float(x.strip()) for x in value.split(","))
    except (TypeError, ValueError) as exc:
        raise ProtocolError(Diagnostic(
            owner=OWNER, function="parse_e9g_rates", category="data",
            code="E9G_INVALID_RATE_GRID", expected="ascending unique 0<Mbps<=10000",
            actual=value,
        )) from exc
    if not rates or rates != tuple(sorted(set(rates))) or any(
        not math.isfinite(x) or not 0 < x <= 10000 for x in rates
    ):
        raise ProtocolError(Diagnostic(
            owner=OWNER, function="parse_e9g_rates", category="data",
            code="E9G_INVALID_RATE_GRID", expected="ascending unique 0<Mbps<=10000",
            actual=value,
        ))
    return rates


def validate_e9g_run(*, sizes: tuple[int, ...], rates: tuple[float, ...],
                     seeds: int, first_seed: int, max_rounds: int) -> None:
    """Experiment axis gate independent of network/PHY validation."""
    if (type(seeds) is not int or not 1 <= seeds <= 10000
        or type(first_seed) is not int or first_seed < 0
        or type(max_rounds) is not int or max_rounds < 1):
        raise ProtocolError(Diagnostic(
            owner=OWNER, function="validate_e9g_run",
            category="data", code="E9G_INVALID_EXPERIMENT_AXES",
            expected="1<=seeds<=10000, first_seed>=0, max_rounds>=1",
            actual=(seeds, first_seed, max_rounds),
        ))
    parse_e9g_sizes(",".join(map(str, sizes)))
    parse_e9g_rates(",".join(map(str, rates)))


def prepare_e9g_output(root: Path) -> None:
    """Never overwrite the user's original 100-seed or previous E9G evidence."""
    if root.exists() and (not root.is_dir() or any(root.iterdir())):
        raise ProtocolError(Diagnostic(
            owner=OWNER, function="prepare_e9g_output",
            category="state", code="E9G_OUTPUT_EXISTS",
            expected="nonexistent or empty output directory", actual=str(root),
        ))
    root.mkdir(parents=True, exist_ok=True)


def create_e9g_sampler(*, profile, seed: int,
                       phy_rate_mbps: float | None):
    """One network model per actual original application experiment."""
    return (
        EmpiricalLatencySampler(profile, seed)
        if phy_rate_mbps is None
        else WifiCausalTimingSampler(
            profile=profile, seed=seed,
            config=WifiTimingConfig(phy_rate_mbps=phy_rate_mbps),
        )
    )


def run_e9g_one_voting_case(*, profile, n: int, seed: int, max_rounds: int,
                            phy_rate_mbps: float | None,
                            timeout_ms: float) -> dict[str, object]:
    """Calls original task wire and original Greedy Vote/Score/Commit owners.

    TASK is reliable and precedes Cost, but is sender-paid. The same modeled
    transport is applied to TASK and coordination in two causally sequential
    phases; the latter begins only after complete TASK receipt. No sampled
    network time is incorrectly treated as computational optimization cost.
    """
    scenario = generate_e0_scenario(seed, n, n)
    task_sampler = create_e9g_sampler(
        profile=profile, seed=seed, phy_rate_mbps=phy_rate_mbps,
    )
    loss_sampler = BernoulliLossSampler(seed)
    task_trace = broadcast_task_information(
        task_positions=scenario.task_positions, num_robots=n,
        sampler=task_sampler, loss_sampler=loss_sampler, p_loss=0.0,
        # TASK is explicitly reliable before any source Cost is available;
        # this is NOT a new receiver-side retransmission algorithm.
        phase_timeout_ms=1.0e9,
    )
    costs = reconstruct_local_cost_rows(
        local_robot_positions=scenario.robot_positions,
        announced_tasks_by_robot=task_trace.per_robot_tasks,
    )
    require_local_source_consistency(
        reconstructed=costs, expected=scenario.cost_matrix,
    )
    task_arrival = max((event.arrival_time_ms for event in task_trace.events),
                       default=0.0)
    coord_sampler = create_e9g_sampler(
        profile=profile, seed=seed, phy_rate_mbps=phy_rate_mbps,
    )
    deadline = timeout_ms
    result = simulate_democracy_hungarian_retirement(
        cost_matrix=costs, sampler=coord_sampler, loss_sampler=loss_sampler,
        p_loss=0.0, p_vote_loss=0.0, phase_timeout_ms=deadline,
        max_rounds=max_rounds, voting_strategy="greedy_task",
        vote_decision_rule="quarter_plurality", vote_repetitions=1,
        cost_repetitions=1,
    )
    task_count = len(task_trace.events)
    packets = task_count + result.logical_message_count
    application_bytes = task_trace.sender_bytes + result.payload_bytes
    full = int(result.full_assignment_success)
    model = (
        "rady_bootstrap_no_shared_channel"
        if phy_rate_mbps is None else "e9g_shared_medium_backoff_proxy"
    )

    metrics: dict[str, float | int] = {}
    if isinstance(task_sampler, WifiCausalTimingSampler):
        a = task_sampler.summarize_network()
        b = coord_sampler.summarize_network()
        if ((a["packet_count"] + b["packet_count"]) != packets
            or (a["application_sender_bytes"] + b["application_sender_bytes"])
               != application_bytes):
            raise ProtocolError(Diagnostic(
                owner=OWNER, function="run_e9g_one_voting_case",
                category="contract", code="E9G_PACKET_LEDGER_MISMATCH",
                expected={"packets": packets, "sender_bytes": application_bytes},
                actual={"packets": a["packet_count"] + b["packet_count"],
                        "sender_bytes": (
                            a["application_sender_bytes"]
                            + b["application_sender_bytes"]
                        )},
                details=f"n={n} seed={seed} rate={phy_rate_mbps}",
            ))
        for key in (
            "radio_hop_count", "radio_payload_equivalent_bytes",
            "total_airtime_ms", "total_backoff_ms", "total_ack_ms",
            "total_queue_ms", "total_residual_ms",
        ):
            metrics[key] = a[key] + b[key]
        metrics["task_radio_media_finish_ms"] = a["medium_busy_until_ms"]
        metrics["coord_radio_media_finish_ms"] = b["medium_busy_until_ms"]

    return {
        "seed": seed, "robots": n, "tasks": n, "model": model,
        "modeled_phy_rate_mbps": "" if phy_rate_mbps is None else phy_rate_mbps,
        "loss_probability": 0.0, "cost_copies": 1,
        "full_commit": full, "tasks_committed": result.committed_tasks,
        "guard_hit": int(not full and len(result.rounds) >= max_rounds),
        "rounds_executed": len(result.rounds),
        "task_announcement_ms": task_arrival,
        "coordination_ms": result.global_agreement_ms,
        "phase_timeout_ms": timeout_ms,
        "allocation_ms": task_arrival + result.global_agreement_ms,
        "task_send_count": task_count,
        "coord_send_count": result.logical_message_count,
        "total_send_count": packets,
        "task_sender_bytes": task_trace.sender_bytes,
        "coord_sender_bytes": result.payload_bytes,
        "total_sender_bytes": application_bytes,
        **{name: metrics.get(name, "") for name in (
            "radio_hop_count", "radio_payload_equivalent_bytes",
            "total_airtime_ms", "total_backoff_ms", "total_ack_ms",
            "total_queue_ms", "total_residual_ms",
            "task_radio_media_finish_ms", "coord_radio_media_finish_ms",
        )},
    }


def summarize_e9g_scaling(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    """Statistics across ALL seeds; incomplete runs never vanish."""
    groups: dict[tuple[int, str, str], list[dict[str, object]]] = {}
    for row in rows:
        groups.setdefault(
            (int(row["robots"]), str(row["model"]),
             str(row["modeled_phy_rate_mbps"])), [],
        ).append(row)
    result = []
    for (n, model, rate), group in sorted(groups.items()):
        times = [float(r["allocation_ms"]) for r in group]
        sender = [int(r["total_sender_bytes"]) for r in group]
        full = [int(r["full_commit"]) for r in group]
        good_times = [float(r["allocation_ms"]) for r in group
                      if int(r["full_commit"])]
        entry: dict[str, object] = {
            "robots": n, "tasks": n, "model": model,
            "modeled_phy_rate_mbps": rate, "seeds": len(group),
            "full_commit_count": sum(full),
            "full_commit_rate": sum(full) / len(group),
            "mean_all_seed_elapsed_ms": statistics.mean(times),
            "p50_all_seed_elapsed_ms": percentile(tuple(times), 0.50),
            "p95_all_seed_elapsed_ms": percentile(tuple(times), 0.95),
            "completed_only_mean_elapsed_ms": (
                statistics.mean(good_times) if good_times else ""
            ),
            "mean_application_sender_bytes": statistics.mean(sender),
            "mean_send_count": statistics.mean(
                int(r["total_send_count"]) for r in group
            ),
            "mean_confirmed_tasks": statistics.mean(
                int(r["tasks_committed"]) for r in group
            ),
            "guard_hit_count": sum(int(r["guard_hit"]) for r in group),
        }
        for field in ("total_airtime_ms", "total_queue_ms",
                      "total_backoff_ms", "total_ack_ms", "radio_hop_count"):
            entry["mean_" + field] = (
                statistics.mean(float(r[field]) for r in group)
                if model == "e9g_shared_medium_backoff_proxy" else ""
            )
        result.append(entry)
    return result


def e9g_loglog_exponent(points: list[tuple[int, float]]) -> tuple[float, float]:
    """Finite-range empirical slope and R^2, NOT asymptotic Big-O proof."""
    if len(points) < 2 or any(n <= 0 or y <= 0 for n, y in points):
        return float("nan"), float("nan")
    xs = [math.log(n) for n, _ in points]
    ys = [math.log(y) for _, y in points]
    xbar, ybar = statistics.mean(xs), statistics.mean(ys)
    xx = sum((x-xbar)**2 for x in xs)
    slope = sum((x-xbar)*(y-ybar) for x, y in zip(xs, ys)) / xx
    residual = sum(
        (y-ybar-slope*(x-xbar))**2 for x, y in zip(xs, ys)
    )
    yy = sum((y-ybar)**2 for y in ys)
    return slope, (1.0 - residual/yy if yy else 1.0)


def summarize_e9g_exponents(summary: list[dict[str, object]]) -> list[dict[str, object]]:
    groups: dict[tuple[str, str], list[dict[str, object]]] = {}
    for row in summary:
        groups.setdefault(
            (str(row["model"]), str(row["modeled_phy_rate_mbps"])), []
        ).append(row)
    output = []
    for (model, rate), cells in sorted(groups.items()):
        cells.sort(key=lambda r: int(r["robots"]))
        item: dict[str, object] = {
            "model": model, "modeled_phy_rate_mbps": rate,
            "points": len(cells), "empirical_only_not_theoretical_big_o": True,
        }
        for field in (
            "mean_all_seed_elapsed_ms", "mean_application_sender_bytes",
            "mean_send_count",
        ):
            beta, r2 = e9g_loglog_exponent([
                (int(c["robots"]), float(c[field])) for c in cells
            ])
            item[field + "_beta"] = beta
            item[field + "_r_squared"] = r2
        output.append(item)
    return output


def calculate_e9g_phase_timeout_ms(*, profile, sizes, rates) -> float:
    """A shared fixed deadline, bounded from the largest selected radio burst.

    This is a stated protocol sensitivity assumption, not a result measured
    by Rady or an undocumented per-N timeout that manufactures scaling.
    """
    config = WifiTimingConfig(phy_rate_mbps=min(rates))
    maximum_n = max(sizes)
    maximum_cost_bytes = 16 + 8 * maximum_n
    hop_service_us = (
        config.phy_preamble_us + config.aifs_us +
        config.cw_min * config.slot_us + config.mac_ack_us +
        8 * (maximum_cost_bytes + config.mac_overhead_bytes) /
        config.phy_rate_mbps
    )
    worst_single_stage_radio_burst_ms = 2 * maximum_n * hop_service_us / 1000.0
    return max(profile.samples_ms) + worst_single_stage_radio_burst_ms + 1.0


def write_e9g_evidence(*, root: Path, rows: list[dict[str, object]],
                       summary: list[dict[str, object]],
                       exponents: list[dict[str, object]],
                       profile, sizes, rates, seeds, first_seed, max_rounds,
                       source_sha: str, timeout_ms: float) -> None:
    """Immutable exact raw, CSV/checksums, manifest; no fabricated ns-3 results."""
    targets = (
        ("per_seed_wifi_timing.csv", rows),
        ("scaling_by_size_mode.csv", summary),
        ("empirical_scaling_exponents.csv", exponents),
    )
    checksums: dict[str, str] = {}
    for name, values in targets:
        path = root / name
        with path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=tuple(values[0].keys()))
            writer.writeheader()
            writer.writerows(values)
        checksums[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    manifest = {
        "experiment": "E9G-1_simplified_wifi_shared_medium_sensitive_Voting_only",
        "evidence_status": "MODELED_NOT_NS3_AND_NOT_REAL_100_ROBOT_WIFI",
        "source_git_sha": source_sha,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "robots_equals_tasks_sizes": list(sizes),
        "seeds_per_size": seeds, "first_seed": first_seed,
        "rates_mbps_hypothetical_not_measured": list(rates),
        "max_rounds": max_rounds,
        "packet_loss": 0.0, "cost_copies": 1,
        "phase_timeout_ms": timeout_ms,
        "phase_timeout_policy": "fixed_Rady_max_plus_max_grid_single_stage_radio_burst_bound",
        "no_claim_timeout_measured_in_papers": True,
        "task_announcement_policy": "reliable_paid_no_deadline_before_cost",
        "rady_git_commit": RADY_SOURCE_COMMIT,
        "rady_source_blob_sha": RADY_SOURCE_BLOB_SHA,
        "rady_samples": len(profile.samples_ms),
        "model_not_supported": [
            "ns3", "OFDMA", "actual_collision_and_retries",
            "spatial_RF_model", "measured_100_station_load",
        ],
        "config": WifiTimingConfig(phy_rate_mbps=rates[0]).__dict__,
        "checksums_sha256": checksums,
        "rows": len(rows), "summary_rows": len(summary),
    }
    (root / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def run_e9g_wifi_scaling(*, sizes: tuple[int, ...], rates: tuple[float, ...],
                         seeds: int, first_seed: int, max_rounds: int,
                         dataset: Path, output_root: Path,
                         allow_download: bool = True) -> list[dict[str, object]]:
    validate_e9g_run(
        sizes=sizes, rates=rates, seeds=seeds,
        first_seed=first_seed, max_rounds=max_rounds,
    )
    prepare_e9g_output(output_root)
    path = ensure_rady_dataset(dataset, allow_download=allow_download)
    profile = load_rady_latency_profile(path)
    source_sha = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], text=True,
    ).strip()
    if len(source_sha) != 40:
        raise ProtocolError(Diagnostic(
            owner=OWNER, function="run_e9g_wifi_scaling", category="dependency",
            code="E9G_INVALID_SOURCE_SHA", expected="40-hex Git HEAD",
            actual=source_sha,
        ))
    timeout_ms = calculate_e9g_phase_timeout_ms(
        profile=profile, sizes=sizes, rates=rates,
    )
    rows: list[dict[str, object]] = []
    partial = output_root / "per_seed_wifi_timing.partial.csv"
    with partial.open("w", newline="", encoding="utf-8") as f:
        writer = None
        for n in sizes:
            for seed in range(first_seed, first_seed+seeds):
                for rate in (None, *rates):
                    row = run_e9g_one_voting_case(
                        profile=profile, n=n, seed=seed,
                        max_rounds=max_rounds, phy_rate_mbps=rate,
                        timeout_ms=timeout_ms,
                    )
                    rows.append(row)
                    if writer is None:
                        writer = csv.DictWriter(f, fieldnames=list(row.keys()))
                        writer.writeheader()
                    writer.writerow(row)
                    f.flush()
            print(f"E9G_DONE size={n} seeds={seeds} rows={len(rows)}",
                  flush=True)
    expected = len(sizes) * seeds * (1 + len(rates))
    if len(rows) != expected:
        raise ProtocolError(Diagnostic(
            owner=OWNER, function="run_e9g_wifi_scaling",
            category="contract", code="E9G_INCOMPLETE_PAIRED_GRID",
            expected=expected, actual=len(rows),
        ))
    summary = summarize_e9g_scaling(rows)
    exponents = summarize_e9g_exponents(summary)
    write_e9g_evidence(
        root=output_root, rows=rows, summary=summary, exponents=exponents,
        profile=profile, sizes=sizes, rates=rates, seeds=seeds,
        first_seed=first_seed, max_rounds=max_rounds,
        source_sha=source_sha, timeout_ms=timeout_ms,
    )
    partial.unlink()
    print(f"E9G_COMPLETE={output_root} source={source_sha} rows={len(rows)}")
    for entry in exponents:
        print(
            f"E9G_EMPIRICAL_EXPONENT model={entry['model']}"
            f" rate_mbps={entry['modeled_phy_rate_mbps']}"
            f" time_beta={entry['mean_all_seed_elapsed_ms_beta']:.5f}"
            f" sender_bytes_beta={entry['mean_application_sender_bytes_beta']:.5f}"
        )
    return rows


def main() -> None:
    p = argparse.ArgumentParser(
        description="Voting-only original Rady vs hypothesized Wi-Fi shared-medium timing"
    )
    p.add_argument("--sizes", type=parse_e9g_sizes, default=DEFAULT_SIZES)
    p.add_argument("--rates-mbps", type=parse_e9g_rates, default=DEFAULT_RATES)
    p.add_argument("--seeds", type=int, default=100)
    p.add_argument("--first-seed", type=int, default=0)
    p.add_argument("--max-rounds", type=int, default=300)
    p.add_argument("--dataset", type=Path,
                   default=Path("data/external/rady/perama_range_testing.json"))
    p.add_argument("--no-download", action="store_true")
    p.add_argument("--output-root", type=Path, default=DEFAULT_ROOT)
    args = p.parse_args()
    run_e9g_wifi_scaling(
        sizes=args.sizes, rates=args.rates_mbps, seeds=args.seeds,
        first_seed=args.first_seed, max_rounds=args.max_rounds,
        dataset=args.dataset, output_root=args.output_root,
        allow_download=not args.no_download,
    )


if __name__ == "__main__":
    main()

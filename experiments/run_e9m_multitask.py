"""Reproducible E9M 25R100T capacity-four original CBBA versus Voting runner."""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import subprocess
import sys

from democracy_mrta.cbba_multitask import run_cbba
from democracy_mrta.diagnostics import Diagnostic, ProtocolError
from democracy_mrta.multitask_evaluation import audit_routes
from democracy_mrta.multitask_scenario import generate_multitask_scene, validate_multitask_shape
from democracy_mrta.multitask_wire import E9MChannel
from democracy_mrta.network import (WifiCausalTimingSampler, WifiTimingConfig,
                                     ensure_rady_dataset, load_rady_latency_profile,
                                     validate_packet_loss_probability)
from democracy_mrta.voting_multitask import run_voting_multitask

METHODS = ("voting_multitask", "cbba")
FIELDS = (
    "seed", "method", "success", "failure_code", "diagnostic", "rounds",
    "guard_censored", "observer_agreement", "local_certificates", "covered_tasks",
    "duplicate_tasks", "missing_tasks", "capacity_violations", "total_distance_m",
    "makespan_s", "discounted_reward", "allocation_ms", "sender_sends",
    "sender_bytes", "receiver_attempts", "receiver_delivered", "receiver_dropped",
    "per_phase_ledger", "routes_json",
)


def validate_e9m_arguments(args: argparse.Namespace) -> tuple[str, ...]:
    validate_multitask_shape(args.robots, args.tasks, args.capacity, 100.0)
    validate_packet_loss_probability(args.loss)
    if args.seeds <= 0 or args.max_rounds <= 0:
        raise ProtocolError(Diagnostic("run_e9m_multitask", "validate_e9m_arguments",
                                       "data", "E9M_INVALID_RUN_LENGTH",
                                       expected="seeds>0 and max_rounds>0",
                                       actual=(args.seeds, args.max_rounds)))
    methods = tuple(args.methods.split(","))
    if len(methods) != len(set(methods)) or not methods or any(m not in METHODS for m in methods):
        raise ProtocolError(Diagnostic("run_e9m_multitask", "validate_e9m_arguments",
                                       "data", "E9M_INVALID_METHODS",
                                       expected=METHODS, actual=methods))
    return methods


def prepare_e9m_output(path: Path) -> Path:
    """Never overwrite old raw evidence, even if directory is empty."""
    try:
        path.mkdir(parents=True, exist_ok=False)
    except FileExistsError as exc:
        raise ProtocolError(Diagnostic("run_e9m_multitask", "prepare_e9m_output",
                                       "state", "E9M_OUTPUT_EXISTS",
                                       expected="new output directory", actual=str(path))) from exc
    return path


def get_e9m_git_sha() -> str:
    try:
        sha = subprocess.check_output(["git", "rev-parse", "HEAD"],
                                      text=True, stderr=subprocess.DEVNULL).strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        raise ProtocolError(Diagnostic("run_e9m_multitask", "get_e9m_git_sha",
                                       "dependency", "E9M_GIT_SHA_UNAVAILABLE")) from exc
    if len(sha) != 40 or any(c not in "0123456789abcdef" for c in sha):
        raise ProtocolError(Diagnostic("run_e9m_multitask", "get_e9m_git_sha",
                                       "contract", "E9M_INVALID_GIT_SHA", actual=sha))
    return sha


def run_e9m_case(scene, method: str, profile, loss: float,
                 max_rounds: int) -> dict:
    seed = scene.seed
    salt = 0 if method == "voting_multitask" else 1
    timing = WifiCausalTimingSampler(profile, seed * 2 + salt,
                                     WifiTimingConfig(phy_rate_mbps=144.0))
    channel = E9MChannel(robots=scene.robots, timing=timing,
                         loss_seed=seed * 2 + salt, method=method)
    try:
        if method == "cbba":
            result = run_cbba(scene, channel, loss, max_rounds)
        else:
            result = run_voting_multitask(scene, channel, loss)
        audit = audit_routes(scene, result.routes)
        ok = bool(audit.feasible and result.observer_agreement and
                  result.local_certificates == scene.robots and not result.guard_censored)
        failure = "" if ok else (result.failure_code or "E9M_ROUTE_OR_CONSENSUS_INVALID")
        diagnostic = "" if ok else json.dumps({
            "owner": "cbba_multitask" if method == "cbba" else "voting_multitask",
            "function": "run_cbba" if method == "cbba" else "run_voting_multitask",
            "category": "safety" if result.guard_censored else "contract",
            "code": failure})
        routes = result.routes
        fields = {"rounds": result.rounds, "guard_censored": int(result.guard_censored),
                  "observer_agreement": int(result.observer_agreement),
                  "local_certificates": result.local_certificates,
                  "covered_tasks": audit.covered_tasks, "duplicate_tasks": audit.duplicate_tasks,
                  "missing_tasks": audit.missing_tasks,
                  "capacity_violations": audit.capacity_violations,
                  "total_distance_m": audit.total_distance_m, "makespan_s": audit.makespan_s,
                  "discounted_reward": audit.discounted_reward, "allocation_ms": result.elapsed_ms}
    except ProtocolError as exc:
        ok, failure, diagnostic = False, exc.diagnostic.code, json.dumps(exc.diagnostic.__dict__)
        routes = tuple(tuple() for _ in range(scene.robots))
        fields = {"rounds": 0, "guard_censored": 0,
                  "observer_agreement": 0, "local_certificates": 0,
                  "covered_tasks": 0, "duplicate_tasks": 0, "missing_tasks": scene.tasks,
                  "capacity_violations": 0, "total_distance_m": 0.0,
                  "makespan_s": 0.0, "discounted_reward": 0.0,
                  "allocation_ms": channel.clock_ms}
    ledger = channel.ledger()
    sums = {name: sum(row[name] for row in ledger.values()) for name in (
        "sender_sends", "sender_bytes", "receiver_attempts",
        "receiver_delivered", "receiver_dropped")}
    if sums["receiver_attempts"] != sums["receiver_delivered"] + sums["receiver_dropped"]:
        raise ProtocolError(Diagnostic("run_e9m_multitask", "run_e9m_case", "contract",
                                       "E9M_RECEIPT_LEDGER_MISMATCH"))
    if not (not ok or sums["sender_bytes"] == timing.summarize_network()["application_sender_bytes"]):
        raise ProtocolError(Diagnostic("run_e9m_multitask", "run_e9m_case", "contract",
                                       "E9M_SENDER_LEDGER_MISMATCH"))
    return {"seed": seed, "method": method, "success": int(ok),
            "failure_code": failure, "diagnostic": diagnostic, **fields, **sums,
            "per_phase_ledger": json.dumps(ledger, sort_keys=True),
            "routes_json": json.dumps(routes, separators=(",", ":"))}


def summarize_e9m(rows: list[dict], methods: tuple[str, ...]) -> list[dict]:
    """All-seed denominator for completion/time/Bytes; quality success-only."""
    summary = []
    for method in methods:
        selected = [row for row in rows if row["method"] == method]
        passed = [row for row in selected if row["success"]]
        n = len(selected)
        avg = lambda cohort, key: (sum(float(r[key]) for r in cohort) / len(cohort)
                                   if cohort else None)
        summary.append({
            "method": method, "total_seeds": n, "completed_seeds": len(passed),
            "completion_rate": len(passed) / n if n else 0.0,
            "guard_censored_seeds": sum(r["guard_censored"] for r in selected),
            "mean_all_seed_stop_ms": avg(selected, "allocation_ms"),
            "mean_all_seed_sender_bytes": avg(selected, "sender_bytes"),
            "mean_all_seed_sender_sends": avg(selected, "sender_sends"),
            "mean_success_only_ms": avg(passed, "allocation_ms"),
            "mean_success_only_total_distance_m": avg(passed, "total_distance_m"),
            "mean_success_only_makespan_s": avg(passed, "makespan_s"),
            "mean_success_only_discounted_reward": avg(passed, "discounted_reward"),
        })
    return summary


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_e9m_evidence(output: Path, rows: list[dict], methods: tuple[str, ...],
                       params: argparse.Namespace, git_sha: str, profile,
                       started: str) -> None:
    summary_file = output / "summary_e9m.csv"
    summary = summarize_e9m(rows, methods)
    with summary_file.open("x", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(summary[0].keys()))
        writer.writeheader()
        writer.writerows(summary)
    raw_file = output / "per_seed_e9m.csv"
    manifest = {
        "study": "E9M", "status": "complete_with_guard_failures_recorded",
        "git_sha": git_sha, "started_utc": started,
        "completed_utc": datetime.now(timezone.utc).isoformat(),
        "python": sys.version, "platform": platform.platform(),
        "configuration": {"robots": params.robots, "tasks": params.tasks,
                          "capacity": params.capacity, "seeds": list(range(params.seeds)),
                          "loss": params.loss, "max_rounds": params.max_rounds,
                          "methods": methods, "world_size_m": 100,
                          "speed_m_per_s": 1, "task_service_s": 0,
                          "wifi_phy_assumed_mbps": 144,
                          "observer_stop": "CBBA unpaid observer, Voting reliable Score/Commit"},
        "rady_profile": {"source_commit": profile.source_commit,
                         "source_blob_sha": profile.source_blob_sha,
                         "sample_count": profile.sample_count},
        "sha256": {raw_file.name: sha256_file(raw_file),
                   summary_file.name: sha256_file(summary_file)},
        "per_seed_method_packet_ledgers": [
            {"seed": row["seed"], "method": row["method"],
             "phase": json.loads(row["per_phase_ledger"])} for row in rows],
        "guard_censored_or_failed": [
            {"seed": row["seed"], "method": row["method"], "code": row["failure_code"]}
            for row in rows if not row["success"]],
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--robots", type=int, default=25)
    parser.add_argument("--tasks", type=int, default=100)
    parser.add_argument("--capacity", type=int, default=4)
    parser.add_argument("--seeds", type=int, default=3)
    parser.add_argument("--loss", type=float, default=0.30)
    parser.add_argument("--max-rounds", type=int, default=160)
    parser.add_argument("--methods", default=",".join(METHODS))
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--rady-json", type=Path,
                        default=Path("data") / "e9m_rady_perama_range_testing.json")
    return parser.parse_args(argv)


def run_e9m(args: argparse.Namespace) -> list[dict]:
    methods = validate_e9m_arguments(args)
    git_sha = get_e9m_git_sha()
    dataset = ensure_rady_dataset(args.rady_json)
    profile = load_rady_latency_profile(dataset)
    output = prepare_e9m_output(args.output_root)
    started = datetime.now(timezone.utc).isoformat()
    rows: list[dict] = []
    with (output / "per_seed_e9m.csv").open("x", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS)
        writer.writeheader()
        stream.flush()
        for seed in range(args.seeds):
            scene = generate_multitask_scene(seed, args.robots, args.tasks, args.capacity)
            for method in methods:
                row = run_e9m_case(scene, method, profile, args.loss, args.max_rounds)
                writer.writerow(row)
                stream.flush()
                os.fsync(stream.fileno())
                rows.append(row)
                print(f"E9M seed={seed}/{args.seeds - 1} method={method} "
                      f"success={row['success']} coverage={row['covered_tasks']}/{args.tasks} "
                      f"rounds={row['rounds']} elapsed_s={row['allocation_ms'] / 1000:.3f} "
                      f"bytes={row['sender_bytes']} failure={row['failure_code']}", flush=True)
    write_e9m_evidence(output, rows, methods, args, git_sha, profile, started)
    print(f"E9M_RESULTS={output} SHA={git_sha}", flush=True)
    return rows


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    rows = run_e9m(args)
    if args.loss == 0.0 and any(not r["success"] for r in rows):
        raise SystemExit("E9M_ZERO_LOSS_SMOKE_FAILED: inspect per_seed_e9m.csv")


if __name__ == "__main__":
    main()

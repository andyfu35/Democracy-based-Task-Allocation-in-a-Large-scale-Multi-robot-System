"""P2-B: batched Greedy Voting versus three unchanged native baseline methods."""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path

from democracy_mrta.diagnostics import Diagnostic, ProtocolError
from democracy_mrta.network import ensure_rady_dataset, load_rady_latency_profile
from democracy_mrta.scenario import generate_e0_scenario
from experiments.run_p1_matched_five import (
    DEFAULT_RADY, OUTPUT_FIELDS, read_source_sha, run_matched_case,
    verify_one_scene, scene_sha256, write_csv, sha256_file,
)
from experiments.p2_packet_loss_plot import render_p2_figure

OWNER = "experiments.run_p2_packet_loss"
METHODS = ("voting", "cbaa", "cbba", "price_auction")
LOSSES = tuple(range(0, 91, 10))
P2_VOTING_STRATEGY = "greedy_batch"
FIELDS = ("loss_percent",) + OUTPUT_FIELDS


def fail(fn, cat, code, expected=None, actual=None):
    raise ProtocolError(Diagnostic(OWNER, fn, cat, code, expected=expected, actual=actual))


def validate_config(args):
    try:
        values = tuple(float(x) for x in args.losses.split(","))
    except (ValueError, AttributeError):
        fail("validate_config", "data", "P2_INVALID_LOSS_GRID", "0%..90% at 10%", args.losses)
    percentages = tuple(round(x * 100) for x in values)
    if (not percentages or any(abs(v * 100 - p) > 1e-9 for v, p in zip(values, percentages))
            or any(p not in LOSSES for p in percentages)
            or percentages != tuple(sorted(set(percentages)))):
        fail("validate_config", "data", "P2_INVALID_LOSS_GRID", LOSSES, percentages)
    if not (1 <= args.seeds <= 100 and 0 <= args.first_seed < 100
            and args.seeds + args.first_seed <= 100):
        fail("validate_config", "data", "P2_INVALID_SEED_RANGE", "seeds 0..99",
             (args.first_seed, args.seeds))
    if args.formal and (percentages != LOSSES or args.seeds != 100 or args.first_seed != 0):
        fail("validate_config", "contract", "P2_FORMAL_GRID_NOT_FROZEN",
             (LOSSES, 100, 0), (percentages, args.seeds, args.first_seed))
    if args.formal and args.voting_strategy != P2_VOTING_STRATEGY:
        fail("validate_config", "contract", "P2_BATCH_FORMAL_VOTING_STRATEGY",
             P2_VOTING_STRATEGY, args.voting_strategy)
    return percentages


def keys(percentages, first_seed, seeds):
    return [(p, seed, method) for p in percentages
            for seed in range(first_seed, first_seed + seeds) for method in METHODS]


def prepare_evidence(args, sha, percentages):
    identity = {"git_sha": sha, "loss_percent": percentages, "seeds": args.seeds,
                "first_seed": args.first_seed, "methods": METHODS, "robots": 100,
                "tasks": 100, "capacity": 1, "formal": args.formal,
                "voting_strategy": args.voting_strategy,
                "rady_json": str(args.rady_json)}
    root = args.output_root
    configuration = root / "run_config_p2.json"
    raw = root / "per_seed_p2.csv"
    if not args.resume:
        if root.exists():
            fail("prepare_evidence", "state", "P2_OUTPUT_EXISTS", "new directory", str(root))
        root.mkdir(parents=True)
        configuration.write_text(json.dumps(identity, indent=2), encoding="utf-8")
        with raw.open("x", newline="", encoding="utf-8") as f:
            csv.DictWriter(f, fieldnames=FIELDS).writeheader()
        return [], identity
    if not (configuration.is_file() and raw.is_file()) or (root / "manifest_p2.json").exists():
        fail("prepare_evidence", "state", "P2_INVALID_RESUME_STATE", "unfinished valid P2", str(root))
    old = json.loads(configuration.read_text(encoding="utf-8"))
    if old != json.loads(json.dumps(identity)):
        fail("prepare_evidence", "contract", "P2_RESUME_CONFIG_MISMATCH", old, identity)
    with raw.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if tuple(reader.fieldnames or ()) != FIELDS:
            fail("prepare_evidence", "contract", "P2_RESUME_FIELDS_CHANGED", FIELDS, reader.fieldnames)
        rows = list(reader)
    expected = keys(percentages, args.first_seed, args.seeds)
    if len(rows) > len(expected):
        fail("prepare_evidence", "contract", "P2_RESUME_INVALID_PREFIX", len(expected), len(rows))
    for r, key in zip(rows, expected):
        actual = (int(r["loss_percent"]), int(r["seed"]), r["method"])
        expected_scene = scene_sha256(generate_e0_scenario(key[1], 100, 100))
        if (actual != key or r["scene_sha256"] != expected_scene
                or int(r["robots"]) != 100 or int(r["tasks"]) != 100
                or int(r["capacity"]) != 1
                or abs(float(r["p_loss"]) - key[0] / 100) > 1e-12):
            fail("prepare_evidence", "contract", "P2_RESUME_INVALID_PREFIX", key, actual)
    return rows, identity


def validate_complete_grid(rows, percentages, first_seed, seeds):
    expected = keys(percentages, first_seed, seeds)
    actual = [(int(r["loss_percent"]), int(r["seed"]), r["method"]) for r in rows]
    if actual != expected:
        fail("validate_complete_grid", "contract", "P2_INCOMPLETE_OR_DUPLICATE_GRID",
             len(expected), len(actual))
    scene_by_seed = {}
    for r in rows:
        seed = int(r["seed"])
        digest = r["scene_sha256"]
        if digest != scene_by_seed.setdefault(seed, digest):
            fail("validate_complete_grid", "contract", "P2_SCENE_NOT_PAIRED",
                 scene_by_seed[seed], digest)


def summarize(rows, percentages):
    out = []
    for p in percentages:
        group = [r for r in rows if int(r["loss_percent"]) == p]
        seeds = {int(r["seed"]) for r in group}
        common = {seed for seed in seeds if all(any(
            int(r["seed"]) == seed and r["method"] == method
            and int(r["native_success"]) and int(r["final_feasible"])
            for r in group) for method in METHODS)}
        for method in METHODS:
            cohort = [r for r in group if r["method"] == method]
            successes = [r for r in cohort if int(r["native_success"]) and int(r["final_feasible"])]
            time = [float(r["native_stop_ms"]) for r in cohort if r["native_stop_ms"] != ""]
            traffic = [float(r["native_sender_bytes"]) for r in cohort if r["native_sender_bytes"] != ""]
            quality = [float(r["final_hungarian_ratio"]) for r in successes
                       if int(r["seed"]) in common]
            mean = lambda x: sum(x) / len(x) if x else ""
            n = len(cohort)
            out.append({
                "loss_percent": p, "method": method, "trials": n,
                "native_complete": len(successes), "completion_rate": len(successes)/n if n else "",
                "first_feasible_observed": sum(int(r["first_feasible_seen"]) for r in cohort),
                "guard_censored": sum(int(r["native_guard_censored"]) for r in cohort),
                "native_error": sum(bool(r["native_diagnostic"]) for r in cohort),
                "native_stop_record_count": len(time),
                "mean_all_seed_native_stop_ms": mean(time) if len(time) == n else "",
                "sender_bytes_record_count": len(traffic),
                "mean_all_seed_sender_bytes": mean(traffic) if len(traffic) == n else "",
                "same_four_success_seeds": len(common),
                "mean_same_four_success_hungarian_ratio": mean(quality),
                "native_endpoint": " / ".join(sorted({r["method_contract"] for r in cohort})),
            })
    return out


def run_p2(args):
    percentages = validate_config(args)
    sha = read_source_sha()
    profile = load_rady_latency_profile(ensure_rady_dataset(args.rady_json))
    rows, identity = prepare_evidence(args, sha, percentages)
    expected = keys(percentages, args.first_seed, args.seeds)
    raw = args.output_root / "per_seed_p2.csv"
    with raw.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        for p, seed, method in expected[len(rows):]:
            scene = generate_e0_scenario(seed, 100, 100)
            verify_one_scene(scene)
            r = {"loss_percent": p,
                 **run_matched_case(scene, profile, method, p / 100, 160, 300,
                                    voting_strategy=args.voting_strategy)}
            writer.writerow(r)
            f.flush()
            os.fsync(f.fileno())
            rows.append(r)
            print(f"P2 PL={p}% seed={seed} method={method} native={r['native_success']} "
                  f"guard={r['native_guard_censored']} time_ms={r['native_stop_ms']} "
                  f"bytes={r['native_sender_bytes']}", flush=True)
    validate_complete_grid(rows, percentages, args.first_seed, args.seeds)
    summary = summarize(rows, percentages)
    summary_path = args.output_root / "summary_p2.csv"
    write_csv(summary_path, summary)
    attested = [raw, args.output_root / "run_config_p2.json", summary_path]
    if args.formal:
        fig = args.output_root / "packet_loss_robustness.svg"
        fig.write_text(render_p2_figure(summary, percentages), encoding="utf-8")
        attested.append(fig)
    manifest = {
        "study": "P2_batch_greedy_versus_three_original_native_C1",
        "source_sha": sha,
        "config": identity,
        "completed_utc": datetime.now(timezone.utc).isoformat(),
        "cases": len(rows),
        "failures": sum(not int(r["native_success"]) for r in rows),
        "sha256": {p.name: sha256_file(p) for p in attested},
        "native_stop_caveat": "Batched Greedy Voting reliable paid Score/Commit; CBAA/CBBA/Auction original native stops differ",
    }
    (args.output_root / "manifest_p2.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"P2_COMPLETE cases={len(rows)} root={args.output_root}", flush=True)
    return rows


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--formal", action="store_true")
    parser.add_argument("--voting-strategy", choices=("greedy_batch", "greedy_task"),
                        default=P2_VOTING_STRATEGY)
    parser.add_argument("--losses", default=",".join(f"{p/100:.2f}" for p in LOSSES))
    parser.add_argument("--seeds", type=int, default=2)
    parser.add_argument("--first-seed", type=int, default=0)
    parser.add_argument("--rady-json", type=Path, default=DEFAULT_RADY)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--resume", action="store_true")
    return parser.parse_args(argv)


if __name__ == "__main__":
    run_p2(parse_args())

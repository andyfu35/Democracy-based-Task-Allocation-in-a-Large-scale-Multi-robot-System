"""Read-only P2-C forensic audit. No optimizer, transport or scenario changes."""
from __future__ import annotations

import argparse
import csv
import io
import json
from pathlib import Path
import statistics
import zipfile

from democracy_mrta.diagnostics import Diagnostic, ProtocolError

OWNER = "experiments.p2c_loss_diagnostics"
PHASES = ("task_announcement_sender_frames", "cost_sender_frames",
          "vote_sender_frames", "score_sender_frames", "commit_sender_frames")


def fail(fn, category, code, expected=None, actual=None):
    raise ProtocolError(Diagnostic(OWNER, fn, category, code,
                                   expected=expected, actual=actual))


def load_voting_rows(source: Path) -> list[dict]:
    """Load original per-seed rows, never the publication rounded summary."""
    if not source.is_file():
        fail("load_voting_rows", "dependency", "P2C_SOURCE_NOT_FOUND", "existing CSV or ZIP", str(source))
    if source.suffix.lower() == ".zip":
        with zipfile.ZipFile(source) as archive:
            choices = [n for n in archive.namelist()
                       if n.endswith("/per_seed_p2.csv") or n == "per_seed_p2.csv"]
            if len(choices) != 1:
                fail("load_voting_rows", "data", "P2C_SOURCE_AMBIGUOUS", 1, choices)
            with archive.open(choices[0]) as stream:
                rows = list(csv.DictReader(io.TextIOWrapper(stream, encoding="utf-8")))
    else:
        with source.open(newline="", encoding="utf-8") as stream:
            rows = list(csv.DictReader(stream))
    selected = [r for r in rows if r.get("method") == "voting"]
    if not selected:
        fail("load_voting_rows", "data", "P2C_NO_VOTING_ROWS", "Voting per-seed evidence", len(rows))
    return selected


def validate_paired_grid(rows: list[dict]) -> dict[int, dict[int, dict]]:
    """Reject missing/duplicate/unpaired cases before claiming causality."""
    by_loss: dict[int, dict[int, dict]] = {}
    seen = set()
    scenes = {}
    for row in rows:
        try:
            loss, seed = int(row["loss_percent"]), int(row["seed"])
            key = (loss, seed)
            if key in seen:
                fail("validate_paired_grid", "contract", "P2C_DUPLICATE_CASE", "unique PL+seed", key)
            seen.add(key)
            if row["native_diagnostic"] or int(row["native_success"]) != 1 or int(row["final_feasible"]) != 1:
                fail("validate_paired_grid", "contract", "P2C_INCOMPLETE_NATIVE_CASE", "native successful/feasible", key)
            digest = row["scene_sha256"]
            if seed in scenes and scenes[seed] != digest:
                fail("validate_paired_grid", "contract", "P2C_UNPAIRED_SCENE", scenes[seed], digest)
            scenes[seed] = digest
            if not row["native_sender_bytes"] or not row["final_hungarian_ratio"]:
                fail("validate_paired_grid", "data", "P2C_MISSING_METRIC", "sender bytes and cost", key)
            by_loss.setdefault(loss, {})[seed] = row
        except (KeyError, ValueError, TypeError) as exc:
            fail("validate_paired_grid", "data", "P2C_INVALID_ROW", "valid P2C raw row", str(exc))
    if 0 not in by_loss:
        fail("validate_paired_grid", "contract", "P2C_ZERO_LOSS_REFERENCE_REQUIRED", "PL0", sorted(by_loss))
    reference = set(by_loss[0])
    for loss, cohort in by_loss.items():
        if set(cohort) != reference:
            fail("validate_paired_grid", "contract", "P2C_SEED_SET_MISMATCH", sorted(reference), {"loss": loss, "seeds": sorted(cohort)})
    return by_loss


def audit_traffic(row: dict) -> dict:
    """Report authentic sender counts; do not invent unrecorded phase byte totals."""
    key = (row["loss_percent"], row["seed"])
    try:
        ledger = json.loads(row["original_traffic_ledger_json"])
        batch = ledger["batch"]
        counts = {phase: int(batch[phase]) for phase in PHASES}
        if counts["cost_sender_frames"] != 100 or counts["task_announcement_sender_frames"] != 3:
            fail("audit_traffic", "contract", "P2C_ONE_TIME_SEND_COUNT_MISMATCH",
                 {"TASK": 3, "Cost": 100}, {"key": key, "counts": counts})
        native = ledger["native"]
        if int(native["sender_bytes"]) != int(row["native_sender_bytes"]):
            fail("audit_traffic", "contract", "P2C_SENDER_LEDGER_MISMATCH",
                 row["native_sender_bytes"], native["sender_bytes"])
        return {**counts, "epochs": float(batch["phase_timing"]["epochs"])}
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        fail("audit_traffic", "data", "P2C_PHASE_LEDGER_MISSING", "original batch ledger", str(exc))


def audit_paired_quality(by_loss: dict[int, dict[int, dict]]) -> list[dict]:
    """Seed-wise ratio and actual assignment changes versus PL0."""
    result = []
    for loss in sorted(by_loss):
        for seed, row in sorted(by_loss[loss].items()):
            base = by_loss[0][seed]
            actual = float(row["final_hungarian_ratio"])
            baseline = float(base["final_hungarian_ratio"])
            try:
                pairs = json.loads(row["native_assignment_json"])
                base_pairs = json.loads(base["native_assignment_json"])
            except (ValueError, TypeError) as exc:
                fail("audit_paired_quality", "data", "P2C_ASSIGNMENT_JSON_INVALID", "valid assignments", str(exc))
            traffic = audit_traffic(row)
            result.append({
                "loss_percent": loss, "seed": seed,
                "base_cost_over_hungarian": baseline,
                "actual_cost_over_hungarian": actual,
                "paired_cost_delta": actual - baseline,
                "assignment_changed": int(sorted(map(tuple, pairs)) != sorted(map(tuple, base_pairs))),
                "base_sender_bytes": int(base["native_sender_bytes"]),
                "actual_sender_bytes": int(row["native_sender_bytes"]),
                "paired_sender_bytes_delta": int(row["native_sender_bytes"]) - int(base["native_sender_bytes"]),
                **traffic,
            })
    return result


def summarize_diagnostics(rows: list[dict]) -> list[dict]:
    """Descriptive statistics only; no confidence/significance claims."""
    result = []
    for loss in sorted({int(r["loss_percent"]) for r in rows}):
        cohort = [r for r in rows if int(r["loss_percent"]) == loss]
        deltas = [float(r["paired_cost_delta"]) for r in cohort]
        result.append({
            "loss_percent": loss, "paired_seeds": len(cohort),
            "improved_seed_count": sum(d < -1e-10 for d in deltas),
            "worsened_seed_count": sum(d > 1e-10 for d in deltas),
            "same_cost_seed_count": sum(abs(d) <= 1e-10 for d in deltas),
            "assignment_changed_count": sum(int(r["assignment_changed"]) for r in cohort),
            "mean_paired_cost_delta": statistics.mean(deltas),
            "mean_sender_bytes": statistics.mean(int(r["actual_sender_bytes"]) for r in cohort),
            "mean_paired_sender_bytes_delta": statistics.mean(int(r["paired_sender_bytes_delta"]) for r in cohort),
            **{"mean_" + p: statistics.mean(float(r[p]) for r in cohort) for p in (*PHASES, "epochs")},
        })
    return result


def write_diagnostic_csv(path: Path, rows: list[dict]) -> None:
    with path.open("x", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True, help="Original P2-C ZIP or per_seed_p2.csv")
    parser.add_argument("--output-root", type=Path, required=True, help="New output directory; never overwritten")
    args = parser.parse_args()
    paired = validate_paired_grid(load_voting_rows(args.source))
    detail = audit_paired_quality(paired)
    summary = summarize_diagnostics(detail)
    args.output_root.mkdir(parents=True, exist_ok=False)
    write_diagnostic_csv(args.output_root / "paired_seed_diagnostics.csv", detail)
    write_diagnostic_csv(args.output_root / "by_loss_diagnostics.csv", summary)
    (args.output_root / "limitations.txt").write_text(
        "Phase sender FRAME counts and all-phase aggregate sender Bytes are recorded. "
        "Original per-phase Sender Bytes are NOT recorded in P2-C raw ledger: "
        "do not infer them by dividing total bytes or multiplying guessed payload sizes. "
        "No bootstrap or causal claim is made. These are observational paired diagnostics.\n",
        encoding="utf-8")
    for r in summary:
        print(f"PL={r['loss_percent']:>2}% improved={r['improved_seed_count']} "
              f"worsened={r['worsened_seed_count']} changed={r['assignment_changed_count']} "
              f"delta_cost={r['mean_paired_cost_delta']:+.6f} "
              f"delta_bytes={r['mean_paired_sender_bytes_delta']:+.1f}")
    print(f"P2C_DIAGNOSTIC_COMPLETE root={args.output_root}")


if __name__ == "__main__":
    main()

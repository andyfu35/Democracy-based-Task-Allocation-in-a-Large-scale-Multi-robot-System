"""Read-only, provenance-pinned P2 baseline reuse; never re-execute old native methods."""
from __future__ import annotations

import csv
import hashlib
import io
from pathlib import Path
import zipfile

from democracy_mrta.diagnostics import Diagnostic, ProtocolError
from democracy_mrta.scenario import generate_e0_scenario
from experiments.run_p1_matched_five import OUTPUT_FIELDS, scene_sha256

OWNER = "experiments.p2_baseline_reuse"
BASELINE_METHODS = ("cbaa", "cbba", "price_auction")
COMPARISON_METHODS = ("voting",) + BASELINE_METHODS
ORIGINAL_GIT_SHA = "f514cfa3613e7b0bad5c739d136b09fea8c3f92c"
ORIGINAL_ZIP_SHA256 = "1d08a167308b9368ee2a764737066223ac041a5bd6508621c7b6cd0320036bb9"
ORIGINAL_RAW_SHA256 = "78c4871a9f0e391c11c92ace9c2b532695d2a2c4ca40d31166e31bf89901e5fc"
ORIGINAL_LOSSES = tuple(range(0, 91, 10))
RAW_FIELDS = ("loss_percent",) + OUTPUT_FIELDS


def _failure(function: str, category: str, code: str, expected=None, actual=None):
    raise ProtocolError(Diagnostic(
        owner=OWNER, function=function, category=category, code=code,
        expected=expected, actual=actual,
    ))


def read_verified_original_baselines(
    archive_path: Path, percentages: tuple[int, ...], first_seed: int, seeds: int,
) -> tuple[list[dict], dict]:
    """SHA-pin complete original P2 ZIP/CSV before taking only 3 original method rows."""
    path = Path(archive_path).expanduser()
    if not path.is_file():
        _failure("read_verified_original_baselines", "dependency", "P2_BASELINE_ZIP_NOT_FOUND",
                 "existing full original P2 ZIP", str(path))
    file_sha = hashlib.sha256(path.read_bytes()).hexdigest()
    if file_sha != ORIGINAL_ZIP_SHA256:
        _failure("read_verified_original_baselines", "contract", "P2_BASELINE_ZIP_SHA_MISMATCH",
                 ORIGINAL_ZIP_SHA256, file_sha)
    try:
        with zipfile.ZipFile(path) as archive:
            bad = archive.testzip()
            if bad is not None:
                _failure("read_verified_original_baselines", "data", "P2_BASELINE_ZIP_CRC",
                         "CRC valid for every file", bad)
            names = [name for name in archive.namelist()
                     if name.endswith("/per_seed_p2.csv") or name == "per_seed_p2.csv"]
            manifests = [name for name in archive.namelist()
                         if name.endswith("/manifest_p2.json") or name == "manifest_p2.json"]
            if len(names) != 1 or len(manifests) != 1:
                _failure("read_verified_original_baselines", "contract",
                         "P2_BASELINE_ZIP_MEMBERS_MISSING",
                         "one per_seed_p2.csv and one manifest_p2.json",
                         {"csv": names, "manifests": manifests})
            import json
            metadata = json.loads(archive.read(manifests[0]).decode("utf-8"))
            original_raw = archive.read(names[0])
    except (OSError, zipfile.BadZipFile, UnicodeError, ValueError) as exc:
        _failure("read_verified_original_baselines", "data", "P2_BASELINE_ZIP_INVALID",
                 "valid original P2 ZIP", str(exc))
    observed_raw_sha = hashlib.sha256(original_raw).hexdigest()
    if observed_raw_sha != ORIGINAL_RAW_SHA256 or metadata.get("source_sha") != ORIGINAL_GIT_SHA:
        _failure("read_verified_original_baselines", "contract",
                 "P2_BASELINE_SOURCE_IDENTITY_MISMATCH",
                 {"source_sha": ORIGINAL_GIT_SHA, "raw_sha256": ORIGINAL_RAW_SHA256},
                 {"source_sha": metadata.get("source_sha"), "raw_sha256": observed_raw_sha})
    if metadata.get("cases") != 4000 or metadata.get("sha256", {}).get("per_seed_p2.csv") != ORIGINAL_RAW_SHA256:
        _failure("read_verified_original_baselines", "contract",
                 "P2_BASELINE_MANIFEST_INVALID",
                 {"cases": 4000, "per_seed_sha256": ORIGINAL_RAW_SHA256}, metadata.get("sha256"))
    original_config = metadata.get("config", {})
    if (original_config.get("robots") != 100 or original_config.get("tasks") != 100
            or original_config.get("capacity") != 1
            or original_config.get("seeds") != 100
            or original_config.get("first_seed") != 0
            or list(original_config.get("loss_percent", ())) != list(ORIGINAL_LOSSES)
            or set(original_config.get("methods", ())) != set(COMPARISON_METHODS)):
        _failure("read_verified_original_baselines", "contract",
                 "P2_BASELINE_CONFIG_MISMATCH",
                 "original 100R100T C1 / 10 PL / 100 paired Seeds / four methods",
                 original_config)
    with io.StringIO(original_raw.decode("utf-8"), newline="") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != RAW_FIELDS:
            _failure("read_verified_original_baselines", "contract",
                     "P2_BASELINE_CSV_SCHEMA_MISMATCH", RAW_FIELDS, reader.fieldnames)
        all_rows = list(reader)
    original_keys = {(p, seed, method) for p in ORIGINAL_LOSSES for seed in range(100)
                     for method in COMPARISON_METHODS}
    observed_keys = [
        (int(row["loss_percent"]), int(row["seed"]), row["method"]) for row in all_rows
    ]
    if len(all_rows) != 4000 or set(observed_keys) != original_keys:
        _failure("read_verified_original_baselines", "contract", "P2_BASELINE_INCOMPLETE_GRID",
                 {"rows": 4000, "unique": 4000}, {
                     "rows": len(all_rows), "unique": len(set(observed_keys)),
                 })
    digests = {seed: scene_sha256(generate_e0_scenario(seed, 100, 100))
               for seed in range(first_seed, first_seed + seeds)}
    wanted = {(p, seed, method) for p in percentages
              for seed in range(first_seed, first_seed + seeds)
              for method in BASELINE_METHODS}
    selected = []
    for row, key in zip(all_rows, observed_keys):
        if key not in wanted:
            continue
        if (row["scene_sha256"] != digests[key[1]] or int(row["robots"]) != 100
                or int(row["tasks"]) != 100 or int(row["capacity"]) != 1
                or abs(float(row["p_loss"]) - key[0] / 100) > 1e-12):
            _failure("read_verified_original_baselines", "contract",
                     "P2_BASELINE_PAIRED_SCENE_MISMATCH", key,
                     (row["scene_sha256"], row["robots"], row["tasks"], row["p_loss"]))
        selected.append(row)
    if len(selected) != len(wanted):
        _failure("read_verified_original_baselines", "contract",
                 "P2_BASELINE_SELECTED_GRID_INCOMPLETE", len(wanted), len(selected))
    return selected, {
        "baseline_original_zip_name": path.name,
        "baseline_original_zip_sha256": file_sha,
        "baseline_original_per_seed_sha256": observed_raw_sha,
        "baseline_executed_git_sha": ORIGINAL_GIT_SHA,
        "baseline_reused_rows": len(selected),
    }


def merge_paired_baseline_evidence(
    voting_rows: list[dict], old_baselines: list[dict],
    percentages: tuple[int, ...], first_seed: int, seeds: int, new_source_sha: str,
) -> list[dict]:
    """Compose one new Voting + three unchanged old native methods with per-row origin."""
    fresh = {(int(row["loss_percent"]), int(row["seed"]), row["method"]): row
             for row in voting_rows}
    old = {(int(row["loss_percent"]), int(row["seed"]), row["method"]): row
           for row in old_baselines}
    expected_new = {(p, seed, "voting") for p in percentages
                    for seed in range(first_seed, first_seed + seeds)}
    expected_old = {(p, seed, m) for p in percentages
                    for seed in range(first_seed, first_seed + seeds)
                    for m in BASELINE_METHODS}
    if (len(voting_rows) != len(expected_new) or len(fresh) != len(expected_new)
            or set(fresh) != expected_new
            or len(old_baselines) != len(expected_old) or len(old) != len(expected_old)
            or set(old) != expected_old):
        _failure("merge_paired_baseline_evidence", "contract", "P2_COMBINED_SOURCE_GRID_MISMATCH",
                 {"new": len(expected_new), "reused": len(expected_old)},
                 {"new": len(voting_rows), "reused": len(old_baselines)})
    combined = []
    for p in percentages:
        for seed in range(first_seed, first_seed + seeds):
            control = fresh[(p, seed, "voting")]["scene_sha256"]
            for method in COMPARISON_METHODS:
                key = (p, seed, method)
                original = fresh[key] if method == "voting" else old[key]
                if original["scene_sha256"] != control:
                    _failure("merge_paired_baseline_evidence", "contract",
                             "P2_COMBINED_SEED_SCENE_MISMATCH", control,
                             {"key": key, "actual": original["scene_sha256"]})
                combined.append({
                    **original, "source_role": ("new_batched_voting" if method == "voting"
                                               else "verified_reused_baseline"),
                    "source_git_sha": (new_source_sha if method == "voting"
                                       else ORIGINAL_GIT_SHA),
                })
    return combined

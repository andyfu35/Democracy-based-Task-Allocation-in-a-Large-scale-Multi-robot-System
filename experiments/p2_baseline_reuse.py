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


# P2D: the *original* P2-C user-run archive, not rounded publication rows.
P2C_ZIP_SHA256 = "f50068e4569771538f3083b8434bc91bce1f42bdec44e8feb74407be90682055"
P2C_RAW_SHA256 = "a5f6c59837b80596066752c6546a37a387b4ccf177f8d4f1c03c527309a4a5fe"
P2C_EXECUTED_GIT_SHA = "8038370205d586c697295b42eb255812be7aa88e"


def read_verified_p2c_voting(
    archive_path: Path, percentages: tuple[int, ...], first_seed: int, seeds: int,
) -> tuple[list[dict], dict]:
    """First original-source SHA/CRC/manifests, then return only native P2-C Voting."""
    path = Path(archive_path).expanduser()
    if not path.is_file():
        _failure("read_verified_p2c_voting", "dependency", "P2D_P2C_ARCHIVE_NOT_FOUND",
                 "original 1,705,448-byte P2-C user ZIP", str(path))
    observed_zip_sha = hashlib.sha256(path.read_bytes()).hexdigest()
    if observed_zip_sha != P2C_ZIP_SHA256:
        _failure("read_verified_p2c_voting", "contract", "P2D_P2C_ZIP_SHA_MISMATCH",
                 P2C_ZIP_SHA256, observed_zip_sha)
    try:
        with zipfile.ZipFile(path) as archive:
            bad = archive.testzip()
            if bad is not None:
                _failure("read_verified_p2c_voting", "data", "P2D_P2C_ZIP_CRC",
                         "all members pass ZIP CRC", bad)
            def member(suffix):
                names = [name for name in archive.namelist()
                         if name == suffix or name.endswith("/" + suffix)]
                if len(names) != 1:
                    _failure("read_verified_p2c_voting", "contract",
                             "P2D_P2C_ARCHIVE_MEMBER_AMBIGUOUS", suffix, names)
                return archive.read(names[0])
            raw = member("per_seed_p2.csv")
            import json
            manifest = json.loads(member("manifest_p2.json").decode("utf-8"))
            config = json.loads(member("run_config_p2.json").decode("utf-8"))
    except (OSError, ValueError, UnicodeError, zipfile.BadZipFile) as exc:
        _failure("read_verified_p2c_voting", "data", "P2D_P2C_INVALID_ZIP",
                 "valid native P2-C archive", str(exc))
    raw_sha = hashlib.sha256(raw).hexdigest()
    if (raw_sha != P2C_RAW_SHA256
            or manifest.get("source_sha") != P2C_EXECUTED_GIT_SHA
            or manifest.get("sha256", {}).get("per_seed_p2.csv") != P2C_RAW_SHA256
            or manifest.get("cases") != 1000):
        _failure("read_verified_p2c_voting", "contract", "P2D_P2C_SOURCE_MISMATCH",
                 {"raw":P2C_RAW_SHA256,"git":P2C_EXECUTED_GIT_SHA,"cases":1000},
                 {"raw":raw_sha,"git":manifest.get("source_sha"),"cases":manifest.get("cases")})
    if (config.get("robots") != 100 or config.get("tasks") != 100
            or config.get("capacity") != 1 or config.get("first_seed") != 0
            or config.get("seeds") != 100
            or config.get("voting_strategy") != "greedy_batch"
            or list(config.get("loss_percent", ())) != list(ORIGINAL_LOSSES)):
        _failure("read_verified_p2c_voting", "contract", "P2D_P2C_CONFIG_MISMATCH",
                 "100R/100T C1, 100 Seeds, P2-C greedy_batch, 10 loss levels", config)
    with io.StringIO(raw.decode("utf-8"), newline="") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != RAW_FIELDS:
            _failure("read_verified_p2c_voting", "contract", "P2D_P2C_FIELDS_CHANGED",
                     RAW_FIELDS, reader.fieldnames)
        all_rows = list(reader)
    keys = [(int(r["loss_percent"]),int(r["seed"]),r["method"]) for r in all_rows]
    expected = {(p,s,"voting") for p in ORIGINAL_LOSSES for s in range(100)}
    if len(all_rows) != 1000 or len(set(keys)) != 1000 or set(keys) != expected:
        _failure("read_verified_p2c_voting", "contract", "P2D_P2C_INCOMPLETE_GRID",
                 {"count":1000,"keys":1000}, {"count":len(all_rows),"keys":len(set(keys))})
    wanted = {(p,s,"voting") for p in percentages
              for s in range(first_seed,first_seed+seeds)}
    scene_shas = {s:scene_sha256(generate_e0_scenario(s,100,100))
                  for s in range(first_seed,first_seed+seeds)}
    selected = []
    for row,key in zip(all_rows,keys):
        if key not in wanted:
            continue
        if (row["scene_sha256"] != scene_shas[key[1]]
                or int(row["robots"]) != 100 or int(row["tasks"]) != 100
                or int(row["capacity"]) != 1
                or abs(float(row["p_loss"])-key[0]/100) > 1e-12):
            _failure("read_verified_p2c_voting", "contract",
                     "P2D_P2C_PAIRED_SCENE_MISMATCH", key, row.get("scene_sha256"))
        selected.append(row)
    if len(selected) != len(wanted):
        _failure("read_verified_p2c_voting", "contract",
                 "P2D_P2C_SELECTED_INCOMPLETE", len(wanted), len(selected))
    return selected, {
        "p2c_original_zip_sha256":observed_zip_sha,
        "p2c_original_raw_sha256":raw_sha,
        "p2c_executed_git_sha":P2C_EXECUTED_GIT_SHA,
        "p2c_selected_rows":len(selected),
    }


def merge_p2d_paired_evidence(
    *, voting_rows: list[dict], native_baselines: list[dict],
    centralized_rows: list[dict], percentages: tuple[int, ...],
    first_seed: int, seeds: int, centralized_source_sha: str,
) -> list[dict]:
    """Only the specified four methods; original method fields unaltered."""
    groups = (
        ("voting", voting_rows, P2C_EXECUTED_GIT_SHA, "verified_original_p2c"),
        ("cbaa", [r for r in native_baselines if r["method"] == "cbaa"],
         ORIGINAL_GIT_SHA, "verified_original_p2"),
        ("cbba", [r for r in native_baselines if r["method"] == "cbba"],
         ORIGINAL_GIT_SHA, "verified_original_p2"),
        ("centralized", centralized_rows, centralized_source_sha, "new_p2d_native"),
    )
    lookups = {}
    expected_scales = {(p,seed) for p in percentages
                       for seed in range(first_seed,first_seed+seeds)}
    for method,values,_sha,_source in groups:
        keys = [(int(r["loss_percent"]), int(r["seed"])) for r in values
                if r["method"] == method]
        if len(keys) != len(values) or len(keys) != len(expected_scales) or set(keys) != expected_scales:
            _failure("merge_p2d_paired_evidence", "contract", "P2D_SOURCE_GRID_MISMATCH",
                     {"method":method,"cases":len(expected_scales)},
                     {"method":method,"cases":len(keys),"unique":len(set(keys))})
        lookups[method] = {(int(r["loss_percent"]),int(r["seed"])):r for r in values}
    if len(native_baselines) != 2*len(expected_scales):
        _failure("merge_p2d_paired_evidence","contract","P2D_EXTRA_NATIVE_BASELINE",
                 2*len(expected_scales),len(native_baselines))
    merged = []
    for loss,seed in sorted(expected_scales):
        matching = {lookups[method][(loss,seed)]["scene_sha256"]
                    for method, *_ in groups}
        if len(matching) != 1:
            _failure("merge_p2d_paired_evidence","contract","P2D_SCENE_MISMATCH",
                     "one scene SHA across all methods",
                     {"loss":loss,"seed":seed,"scene_shas":sorted(matching)})
        for method,_rows,sha,source in groups:
            merged.append({**lookups[method][(loss,seed)],
                           "source_git_sha":sha, "source_role":source})
    return merged

"""Immutable E9J original CBAA evidence, for E9K and future ablations.

This owner validates external archived source identity only; no CBAA, Voting,
network, or allocation state is implemented here.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
from pathlib import Path
import zipfile

from democracy_mrta.diagnostics import Diagnostic, ProtocolError

OWNER = "experiments.cbaa_baseline_registry"
E9J_ZIP_SHA256 = "106fc14aa9088edf980a744bf9e129c516ce8cabf9c23322baa76be9b33c82bb"
E9J_SOURCE_SHA = "3a69bdef32fa4f430de5949768bf38a54987ffd1"
E9J_RAW_SHA256 = "a586b364a5861fc383c62f5f327afa16a796b46076e42d15ef4722dad40ba189"
E9J_E9I_ZIP_SHA256 = "5d275bebd8d6f985e8eef1bbba9a0947991cd71660c1cc49817619e6bc276ee5"


def load_pinned_e9j_cbaa_baseline(
    *, archive: Path, sizes: tuple[int, ...], seeds: int, first_seed: int,
) -> dict[tuple[int, int], dict]:
    """Load *original*, SHA256-hard-pinned 2,000-case native CBAA outcome."""
    if not archive.is_file():
        raise ProtocolError(Diagnostic(
            owner=OWNER, function="load_pinned_e9j_cbaa_baseline",
            category="dependency", code="E9K_E9J_ARCHIVE_MISSING",
            expected="user-run E9J original 100-seed ZIP",
            actual=str(archive),
        ))
    digest=hashlib.sha256(archive.read_bytes()).hexdigest()
    if digest != E9J_ZIP_SHA256:
        raise ProtocolError(Diagnostic(
            owner=OWNER, function="load_pinned_e9j_cbaa_baseline",
            category="contract", code="E9K_E9J_ZIP_SHA_MISMATCH",
            expected=E9J_ZIP_SHA256, actual=digest,
        ))
    try:
        with zipfile.ZipFile(archive) as z:
            manifest_files=[name for name in z.namelist()
                            if name.endswith("/manifest.json")]
            raw_files=[name for name in z.namelist()
                       if name.endswith("/per_seed_original_cbaa.csv")]
            if len(manifest_files)!=1 or len(raw_files)!=1:
                raise ValueError("expected one E9J manifest and original CBAA CSV")
            manifest=json.loads(z.read(manifest_files[0]))
            blob=z.read(raw_files[0])
            rows=list(csv.DictReader(io.StringIO(blob.decode("utf-8"))))
    except (OSError, zipfile.BadZipFile, UnicodeError, ValueError,
            KeyError, json.JSONDecodeError) as exc:
        raise ProtocolError(Diagnostic(
            owner=OWNER, function="load_pinned_e9j_cbaa_baseline",
            category="data", code="E9K_E9J_ARCHIVE_INVALID",
            expected="one original manifest+2000-case CBAA CSV", actual=str(exc),
        )) from exc
    valid=(
        manifest.get("source_git_sha")==E9J_SOURCE_SHA
        and manifest.get("baseline_original_zip_sha256")==E9J_E9I_ZIP_SHA256
        and manifest.get("result_status")=="PAIRED"
        and manifest.get("CBAA_bid_receiver_Bernoulli_p")==.30
        and manifest.get("cbaa_original_cases")==2000
        and manifest.get("sha256_source_files",{}).get(
            "per_seed_original_cbaa.csv")==E9J_RAW_SHA256
        and hashlib.sha256(blob).hexdigest()==E9J_RAW_SHA256
        and len(rows)==2000
    )
    if not valid:
        raise ProtocolError(Diagnostic(
            owner=OWNER, function="load_pinned_e9j_cbaa_baseline",
            category="contract", code="E9K_E9J_SOURCE_CONTRACT",
            expected="original pinned 2000-row CBAA + E9I source hashes",
            actual={"source":manifest.get("source_git_sha"),
                    "cases":len(rows),"zip":digest},
        ))
    all_keys={}
    for row in rows:
        try:
            key=(int(row["robots"]),int(row["seed"]))
            good=(
                key[0] in range(5,101,5) and 0<=key[1]<100
                and int(row["tasks"])==key[0]
                and row["method"]=="cbaa_original_local_bid_winner"
                and float(row["Bid_receiver_loss_probability"])==.30
                and float(row["phy_mbps_ASSUMED"])==144.0
            )
        except (ValueError, TypeError, KeyError) as exc:
            raise ProtocolError(Diagnostic(
                owner=OWNER, function="load_pinned_e9j_cbaa_baseline",
                category="data", code="E9K_E9J_ROW_INVALID",
                expected="native E9J N/seed/packet model",actual=str(exc),
            )) from exc
        if not good or key in all_keys:
            raise ProtocolError(Diagnostic(
                owner=OWNER, function="load_pinned_e9j_cbaa_baseline",
                category="contract", code="E9K_E9J_DUPLICATE_OR_INVALID_KEY",
                expected="unique native N=5..100/seed=0..99 with pBid=.30",
                actual=key,
            ))
        all_keys[key]=row
    if len(all_keys)!=2000:
        raise ProtocolError(Diagnostic(
            owner=OWNER, function="load_pinned_e9j_cbaa_baseline",
            category="contract", code="E9K_E9J_INCOMPLETE_FULL_ARCHIVE",
            expected=2000,actual=len(all_keys),
        ))
    requested={(n,seed) for n in sizes
               for seed in range(first_seed,first_seed+seeds)}
    if not requested.issubset(all_keys):
        raise ProtocolError(Diagnostic(
            owner=OWNER, function="load_pinned_e9j_cbaa_baseline",
            category="contract", code="E9K_E9J_MISSING_MATCHED_CASE",
            expected=len(requested),
            actual=len(requested.intersection(all_keys)),
        ))
    return {key:all_keys[key] for key in sorted(requested)}

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

# E9L reuses the true CBAA original-archive owner instead of copying baseline
# source validation into the E9L auction runner. Frozen user-run E9K only.
E9K_ZIP_SHA = "1495612c65a4fb40733af225b2121275e2b2309070695f2594c620079a6b8281"
E9K_SOURCE_SHA = "715dfa6c262b7081c241b54a7bddec16354990a3"
E9K_RAW_SHA = "c6183a59177b37aaaf1ff2cd723ce4913f22646f137b4260813999df023be39b"
E9K_OLD_E9J_SHA = "106fc14aa9088edf980a744bf9e129c516ce8cabf9c23322baa76be9b33c82bb"
E9K_OLD_E9I_SHA = "5d275bebd8d6f985e8eef1bbba9a0947991cd71660c1cc49817619e6bc276ee5"


def load_pinned_e9k_paid_baseline(*, archive: Path,
                                   sizes: tuple[int,...], seeds:int,
                                   first_seed:int) -> dict[tuple[int,int],dict]:
    """Contract-owning archive loader. Never reconstructs or modifies E9K."""
    owner="experiments.cbaa_baseline_registry"
    fn="load_pinned_e9k_paid_baseline"
    if not archive.is_file():
        raise ProtocolError(Diagnostic(owner=owner,function=fn,category="dependency",
            code="E9L_E9K_ARCHIVE_MISSING",expected="original E9K ZIP",actual=str(archive)))
    sha=hashlib.sha256(archive.read_bytes()).hexdigest()
    if sha!=E9K_ZIP_SHA:
        raise ProtocolError(Diagnostic(owner=owner,function=fn,category="contract",
            code="E9L_E9K_ZIP_SHA_MISMATCH",expected=E9K_ZIP_SHA,actual=sha))
    try:
        with zipfile.ZipFile(archive) as z:
            manifests=[p for p in z.namelist() if p.endswith("/manifest.json")]
            sources=[p for p in z.namelist() if p.endswith("/per_seed_e9k.csv")]
            if len(manifests)!=1 or len(sources)!=1:
                raise ValueError("one E9K manifest and one original raw required")
            metadata=json.loads(z.read(manifests[0]))
            raw=z.read(sources[0])
        records=list(csv.DictReader(io.StringIO(raw.decode("utf-8"))))
    except (OSError,UnicodeError,KeyError,ValueError,zipfile.BadZipFile) as e:
        raise ProtocolError(Diagnostic(owner=owner,function=fn,category="data",
            code="E9L_E9K_INVALID_ARCHIVE",expected="valid manifest and raw",actual=str(e))) from e
    if (metadata.get("status")!="FORMAL_PAIRED_SIMULATED"
        or metadata.get("executed_git_sha")!=E9K_SOURCE_SHA
        or metadata.get("immutable_e9i_voting_zip_SHA256")!=E9K_OLD_E9I_SHA
        or metadata.get("immutable_e9j_cbaa_zip_SHA256")!=E9K_OLD_E9J_SHA
        or metadata.get("bid_loss")!=.30 or metadata.get("ready_loss")!=.30
        or metadata.get("commit_loss")!=.30
        or metadata.get("user_original_files_sha256",{}).get("per_seed_e9k.csv")!=E9K_RAW_SHA
        or hashlib.sha256(raw).hexdigest()!=E9K_RAW_SHA or len(records)!=2000):
        raise ProtocolError(Diagnostic(owner=owner,function=fn,category="contract",
            code="E9L_E9K_SOURCE_CONTRACT",expected="pinned 2000 original p30 E9K cases",
            actual={"sha":sha,"rows":len(records),"source":metadata.get("executed_git_sha")}))
    rows={}
    for row in records:
        try:
            n=int(row["robots"]);t=int(row["tasks"]);seed=int(row["seed"])
            same=(n==t and n in range(5,101,5) and 0<=seed<100
                  and row["method"]=="cbaa_original_auction_plus_paid_ready_commit"
                  and float(row["bid_receiver_loss"])==.30
                  and float(row["ready_receiver_loss"])==.30
                  and float(row["commit_receiver_loss"])==.30
                  and float(row["assumed_phy_mbps"])==144.0)
            send_ok=(int(row["paid_control_sender_bytes"])==48*(
                        int(row["paid_ready_sender_SENDs"])+int(row["paid_commit_sender_SENDs"]))
                     and int(row["full_physical_sender_bytes"])==(
                        int(row["original_TASK_sender_bytes"])
                        +int(row["native_bid_sender_bytes"])
                        +int(row["paid_control_sender_bytes"])))
        except (KeyError,ValueError,TypeError) as e:
            raise ProtocolError(Diagnostic(owner=owner,function=fn,category="data",
                code="E9L_E9K_INVALID_RAW_ROW",expected="native E9K typed source",actual=str(e))) from e
        if not same or not send_ok or (n,seed) in rows:
            raise ProtocolError(Diagnostic(owner=owner,function=fn,category="contract",
                code="E9L_E9K_DUPLICATE_OR_INVALID_ROW",expected="distinct native raw n/seed and paid ledger",
                actual=(n,t,seed)))
        rows[n,seed]=row
    if len(rows)!=2000:
        raise ProtocolError(Diagnostic(owner=owner,function=fn,category="contract",
            code="E9L_E9K_INCOMPLETE_GRID",expected=2000,actual=len(rows)))
    wanted={(n,seed) for n in sizes for seed in range(first_seed,first_seed+seeds)}
    if not wanted.issubset(rows):
        raise ProtocolError(Diagnostic(owner=owner,function=fn,category="contract",
            code="E9L_E9K_UNPAIRED_SOURCE",expected=len(wanted),
            actual=len(wanted.intersection(rows))))
    return {key:rows[key] for key in sorted(wanted)}

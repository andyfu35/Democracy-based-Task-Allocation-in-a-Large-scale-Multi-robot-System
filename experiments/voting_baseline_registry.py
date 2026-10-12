"""Only owner of immutable source E9I Voting baseline identity and row pairing.

All later method comparisons must share this exact historical original source:
SHA256 hard-gated 16,000-row E9I user archive and exact 100 seeds. No
network/assignment state machine, baseline rerun or algorithm-specific logic.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
from pathlib import Path
import zipfile

from democracy_mrta.diagnostics import Diagnostic, ProtocolError

OWNER="experiments.voting_baseline_registry"
BASE_ZIP_SHA = "5d275bebd8d6f985e8eef1bbba9a0947991cd71660c1cc49817619e6bc276ee5"
BASE_GIT_SHA = "408ff70a31e8c2957602cae3f09ad8f239cd3224"
BASE_CSV_SHA = "1249661d6efeee70c377e76b04176f0923a8051fd983e4aeef3571918041d3f7"
BASE_ARM_NAMES = ("adaptive_guarded_k1_received", "fixed_received")
BASE_VOTE_LOSSES = (0.0, 0.30)
BASE_COST_RECEIVER_LOSS=.30
BASE_ASSUMED_PHY_Mbps=144.0

def load_pinned_e9i_voting_baseline(*, archive: Path, sizes, seeds,
                                first_seed) -> dict[tuple[int,int,float,str],dict]:
    """Strict raw original archival proof; no replanned baseline runs."""
    if not archive.is_file():
        raise ProtocolError(Diagnostic(
            owner=OWNER,function="load_pinned_e9i_voting_baseline",
            category="dependency",code="E9J_E9I_ORIGINAL_ARCHIVE_MISSING",
            expected="user-run original e9i_cost30_formal_100seed.zip",
            actual=str(archive),
        ))
    digest=hashlib.sha256(archive.read_bytes()).hexdigest()
    if digest != BASE_ZIP_SHA:
        raise ProtocolError(Diagnostic(
            owner=OWNER,function="load_pinned_e9i_voting_baseline",
            category="contract",code="E9J_BASELINE_ARCHIVE_SHA_MISMATCH",
            expected=BASE_ZIP_SHA,actual=digest,
        ))
    try:
        with zipfile.ZipFile(archive) as z:
            manifest=json.loads(z.read("manifest.json"))
            raw=z.read("per_seed_e9i_cost30.csv")
            source_hash=hashlib.sha256(raw).hexdigest()
            rows=list(csv.DictReader(io.StringIO(raw.decode("utf-8"))))
    except (OSError,zipfile.BadZipFile,KeyError,UnicodeError,
            ValueError,json.JSONDecodeError) as exc:
        raise ProtocolError(Diagnostic(
            owner=OWNER,function="load_pinned_e9i_voting_baseline",
            category="data",code="E9J_INVALID_BASELINE_SOURCE",
            expected="original manifest.json + complete original CSV",
            actual=str(exc),
        )) from exc
    good=(
        manifest.get("source_git_sha")==BASE_GIT_SHA
        and manifest.get("cost_loss_probability_fixed")==BASE_COST_RECEIVER_LOSS
        and manifest.get("vote_loss_probabilities_paired")==[0.0,0.3]
        and manifest.get("phy_rate_mbps_assumed_not_measured")==BASE_ASSUMED_PHY_Mbps
        and manifest.get("source_files_sha256",{}).get("per_seed_e9i_cost30.csv")
              ==BASE_CSV_SHA==source_hash
        and manifest.get("raw_cases")==16000 and len(rows)==16000
    )
    if not good:
        raise ProtocolError(Diagnostic(
            owner=OWNER,function="load_pinned_e9i_voting_baseline",
            category="contract",code="E9J_BASELINE_SOURCE_CONTRACT",
            expected={"git_sha":BASE_GIT_SHA,"Cost_p":.3,"rate":144,
                      "raw_sha":BASE_CSV_SHA,"rows":16000},
            actual={"git_sha":manifest.get("source_git_sha"),
                    "Cost_p":manifest.get("cost_loss_probability_fixed"),
                    "rate":manifest.get("phy_rate_mbps_assumed_not_measured"),
                    "raw_sha":source_hash,"rows":len(rows)},
        ))
    requested={(n,seed,vote,arm)
               for n in sizes for seed in range(first_seed,first_seed+seeds)
               for vote in BASE_VOTE_LOSSES for arm in BASE_ARM_NAMES}
    found={}
    for row in rows:
        try:
            key=(int(row["robots"]),int(row["seed"]),
                 float(row["vote_loss_probability"]),str(row["arm"]))
        except (ValueError,TypeError,KeyError) as exc:
            raise ProtocolError(Diagnostic(
                owner=OWNER,function="load_pinned_e9i_voting_baseline",
                category="data",code="E9J_INVALID_BASELINE_ROW",
                expected="N,seed,Vote_loss,arm",actual=str(exc),
            )) from exc
        if key in requested:
            if key in found or row["model"]!="e9g_shared_medium_backoff_proxy":
                raise ProtocolError(Diagnostic(
                    owner=OWNER,function="load_pinned_e9i_voting_baseline",
                    category="contract",code="E9J_DUPLICATE_BASELINE_KEY",
                    expected="one original source row per matched scene",actual=key,
                ))
            found[key]=row
    if set(found)!=requested:
        raise ProtocolError(Diagnostic(
            owner=OWNER,function="load_pinned_e9i_voting_baseline",
            category="contract",code="E9J_INCOMPLETE_BASELINE_PAIRING",
            expected=len(requested),actual=len(found),
            details=f"missing first={list(sorted(requested-set(found)))[:3]}",
        ))
    return found



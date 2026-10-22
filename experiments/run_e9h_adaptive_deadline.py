"""E9H original decentralized Voting: quantitative Rady deadline × score rule ablation.

Primary experiment is ONLY our original Greedy Voting (not CBAA, not ns-3).
All candidate messages and actual SENDs originate from original owners.
E9G's uploaded 8,000-row data is used to pin prior traffic and 609ms control
conditions, NOT to train/tune on this run's success outcomes.
"""
from __future__ import annotations

import argparse
import csv
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import statistics
import subprocess
import zipfile

from democracy_mrta.coordination import simulate_democracy_hungarian_retirement
from democracy_mrta.diagnostics import Diagnostic, ProtocolError
from democracy_mrta.network import (
    BernoulliLossSampler, EmpiricalLatencySampler, WifiCausalTimingSampler,
    RADY_SOURCE_BLOB_SHA, RADY_SOURCE_COMMIT, ensure_rady_dataset,
    estimate_e9h_adaptive_deadline, load_rady_latency_profile,
    percentile, estimate_e9h_guarded_initial_cost_ms,
)
from democracy_mrta.optimizer import solve_hungarian_assignment
from democracy_mrta.scenario import generate_e0_scenario
from democracy_mrta.task_information import (
    broadcast_task_information, reconstruct_local_cost_rows,
)
from experiments.run_e9c_real_information import require_local_source_consistency
from experiments.run_e9g_wifi_scaling import (
    parse_e9g_sizes, parse_e9g_rates, create_e9g_sampler,
    e9g_loglog_exponent,
)

OWNER = "experiments.run_e9h_adaptive_deadline"
DEFAULT_SIZES = tuple(range(5,101,5))
DEFAULT_RATES = (144.0,600.0,1200.0)
DEFAULT_LOSSES = (0.0,0.30)
DEFAULT_MARGIN_FACTORS = (1.0,)
DEFAULT_OLD_FIXED_MS = 609.1129007777778
E9G_REFERENCE_ZIP_SHA256 = "c0d9722d13242a67eb9b2662df124ff0174701912a5275d348d1c68d26cec6fd"
E9G_REFERENCE_PER_SEED_SHA256 = "ba79fd138d84d6d3bb7f04430a36a8c3e973d7ca0978834d4ad3a3b1d3f85be6"
E9G_REFERENCE_SOURCE_SHA = "910c5eac738367738907b18fce86e56adf86697d"


def parse_e9h_floats(text: str, *, is_loss: bool) -> tuple[float,...]:
    """One experiment data boundary for frozen predeclared loss/margin grids."""
    try:
        values=tuple(float(x.strip()) for x in text.split(","))
    except (ValueError,AttributeError) as exc:
        raise ProtocolError(Diagnostic(
            owner=OWNER,function="parse_e9h_floats",category="data",
            code="E9H_INVALID_LOSS_OR_MARGIN_GRID",
            expected="unique ascending finite CSV float values",
            actual=text,
        )) from exc
    valid=(len(values)>0 and values==tuple(sorted(set(values)))
           and all(math.isfinite(v) and (0<=v<=1 if is_loss else 0<=v<=4)
                   for v in values))
    if not valid:
        raise ProtocolError(Diagnostic(
            owner=OWNER,function="parse_e9h_floats",category="data",
            code="E9H_INVALID_LOSS_OR_MARGIN_GRID",
            expected="unique ascending losses in [0,1] or margins in [0,4]",
            actual=text,
        ))
    return values


def validate_e9h_experiment(*, sizes, rates, losses, margins, seeds,
                             first_seed, max_rounds, design_rate_mbps) -> None:
    """Reject malformed design before allocating any formal evidence root."""
    parse_e9g_sizes(",".join(str(n) for n in sizes))
    parse_e9g_rates(",".join(str(x) for x in rates))
    parse_e9h_floats(",".join(str(x) for x in losses),is_loss=True)
    parse_e9h_floats(",".join(str(x) for x in margins),is_loss=False)
    if (type(seeds) is not int or not 1 <= seeds <= 10000
        or type(first_seed) is not int or first_seed < 0
        or type(max_rounds) is not int or max_rounds < max(sizes)
        or type(design_rate_mbps) not in (int,float)
        or not math.isfinite(design_rate_mbps) or design_rate_mbps <= 0):
        raise ProtocolError(Diagnostic(
            owner=OWNER,function="validate_e9h_experiment",category="data",
            code="E9H_INVALID_EXPERIMENT_AXES",
            expected="positive seeds, valid design rate, max_rounds>=max robots",
            actual={"seeds":seeds,"first_seed":first_seed,
                    "max_rounds":max_rounds,"design_rate_mbps":design_rate_mbps},
        ))


def verify_historical_e9g_zip(path: Path | None) -> dict[str,object]:
    """Optional *independent* source-provenance gate, never a calibration fit."""
    if path is None:
        return {"archive_path":"","verified_against_uploaded_source":False,
                "pinned_archive_sha256":E9G_REFERENCE_ZIP_SHA256,
                "pinned_raw_sha256":E9G_REFERENCE_PER_SEED_SHA256}
    if not path.is_file():
        raise ProtocolError(Diagnostic(
            owner=OWNER,function="verify_historical_e9g_zip",category="dependency",
            code="E9H_PREVIOUS_E9G_ZIP_MISSING",expected="existing previous E9G formal ZIP",
            actual=str(path),
        ))
    actual=hashlib.sha256(path.read_bytes()).hexdigest()
    try:
        with zipfile.ZipFile(path) as z:
            m=json.loads(z.read("manifest.json"))
            raw=hashlib.sha256(z.read("per_seed_wifi_timing.csv")).hexdigest()
            expected_rows=m["rows"]
            expected_source=m["source_git_sha"]
            old_timeout=float(m["phase_timeout_ms"])
    except (zipfile.BadZipFile,KeyError,ValueError,json.JSONDecodeError) as exc:
        raise ProtocolError(Diagnostic(
            owner=OWNER,function="verify_historical_e9g_zip",category="contract",
            code="E9H_UNVERIFIED_HISTORICAL_SOURCE",
            expected="pinned complete E9G ZIP and source manifest",
            actual=str(exc),
        )) from exc
    if (actual!=E9G_REFERENCE_ZIP_SHA256 or raw!=E9G_REFERENCE_PER_SEED_SHA256
        or expected_rows!=8000 or expected_source!=E9G_REFERENCE_SOURCE_SHA
        or not math.isclose(old_timeout,DEFAULT_OLD_FIXED_MS,abs_tol=1e-9)):
        raise ProtocolError(Diagnostic(
            owner=OWNER,function="verify_historical_e9g_zip",category="contract",
            code="E9H_UNVERIFIED_HISTORICAL_SOURCE",
            expected={"archive_sha":E9G_REFERENCE_ZIP_SHA256,
                      "per_seed_sha":E9G_REFERENCE_PER_SEED_SHA256,
                      "rows":8000,"source":E9G_REFERENCE_SOURCE_SHA,
                      "timeout_ms":DEFAULT_OLD_FIXED_MS},
            actual={"archive_sha":actual,"per_seed_sha":raw,
                    "rows":expected_rows,"source":expected_source,
                    "timeout_ms":old_timeout},
        ))
    return {"archive_path":str(path),"verified_against_uploaded_source":True,
            "pinned_archive_sha256":actual,"pinned_raw_sha256":raw}


def build_e9h_deadline_schedule(*, profile, robots: int,
                               design_rate_mbps: float, margin_factor: float,
                               voting_strategy: str = "greedy_task",
                               batch_vote_scope: str = "all"):
    """Use actual per-epoch vote size for the selected serial or batched strategy."""
    cost=estimate_e9h_adaptive_deadline(
        profile=profile,active_robots=robots,total_tasks=robots,
        reference_phy_mbps=design_rate_mbps,margin_factor=margin_factor,
        phase="cost",
    )
    votes=tuple(
        estimate_e9h_adaptive_deadline(
            profile=profile,active_robots=n,total_tasks=robots,
            reference_phy_mbps=design_rate_mbps,margin_factor=margin_factor,
            phase=("vote_batch" if voting_strategy in ("greedy_batch", "greedy_batch_task_order", "probabilistic_batch")
                   and batch_vote_scope == "all" else "vote"),
        ) for n in range(1,robots+1)
    )
    if votes[-1].deadline_ms > cost.deadline_ms + 1e-9:
        raise ProtocolError(Diagnostic(
            owner=OWNER,function="build_e9h_deadline_schedule",
            category="contract",code="E9H_COST_VOTE_DEADLINE_ORDER",
            expected="initial full Cost row deadline >= full team Vote deadline",
            actual=(cost.deadline_ms,votes[-1].deadline_ms),
        ))
    return cost,votes


def iter_e9h_arms(margins: tuple[float,...]) -> tuple[tuple[str,str,float|None,bool],...]:
    """Frozen long/short/once-guarded-cost x quarter/positive-claim comparison."""
    return (
        ("fixed_quarter","quarter_plurality",None,False),
        ("fixed_received","received_plurality",None,False),
        *tuple(
            (f"adaptive_k{k:g}_{label}",rule,k,True)
            for k in margins
            for label,rule in (
                ("quarter","quarter_plurality"),
                ("received","received_plurality"),
            )
        ),
        *tuple(
            (f"adaptive_guarded_k{k:g}_{label}",rule,k,True)
            for k in margins
            for label,rule in (
                ("quarter","quarter_plurality"),
                ("received","received_plurality"),
            )
        ),
    )


def summarize_e9h_phase_timing(*, task_ms: float, result) -> dict:
    """Decompose physically scheduled native stages without charging Cost twice."""
    epochs = tuple(result.rounds)
    cost_ms = sum(e.coordination.cost_phase_completion_ms for e in epochs)
    vote_score_ms = sum(
        e.coordination.decision_completion_ms - e.coordination.cost_phase_completion_ms
        for e in epochs
    )
    commit_ms = sum(
        e.coordination.global_agreement_ms - e.coordination.decision_completion_ms
        for e in epochs
    )
    pieces = (task_ms, cost_ms, vote_score_ms, commit_ms)
    if any(not math.isfinite(value) or value < -1e-7 for value in pieces):
        raise ProtocolError(Diagnostic(
            owner=OWNER, function="summarize_e9h_phase_timing",
            category="time", code="P2_BATCH_NEGATIVE_PHASE_DURATION",
            expected="finite nonnegative TASK/Cost/Vote+Score/Commit durations",
            actual=pieces,
        ))
    expected = task_ms + result.global_agreement_ms
    actual = sum(pieces)
    if abs(expected-actual) > 1e-5:
        raise ProtocolError(Diagnostic(
            owner=OWNER, function="summarize_e9h_phase_timing",
            category="time", code="P2_BATCH_STAGE_TIME_MISMATCH",
            expected=expected, actual=actual,
        ))
    return {
        "task_ms":task_ms, "cost_once_ms":cost_ms,
        "vote_and_score_ms":vote_score_ms, "commit_ms":commit_ms,
        "total_ms":expected, "epochs":len(epochs),
    }


def summarize_e9h_sender_phase_breakdown(
    *, task_network: dict, coordination_network: dict,
    expected_sends: int, expected_bytes: int,
) -> dict[str, dict[str, int]]:
    """Sum true physically emitted SEND frames/bytes, never receiver reports."""
    phase_names = {
        "task_announcement": "task",
        "cost": "cost",
        "vote": "vote",
        "vote_score_announcement": "score",
        "commit": "commit",
    }
    stages = {
        label: {"sender_sends": 0, "sender_bytes": 0}
        for label in phase_names.values()
    }
    for network in (task_network, coordination_network):
        for physical_phase, counts in network["sender_by_phase"].items():
            label = phase_names.get(physical_phase)
            if label is None:
                raise ProtocolError(Diagnostic(
                    owner=OWNER, function="summarize_e9h_sender_phase_breakdown",
                    category="contract", code="P2E_UNEXPECTED_SENDER_PHASE",
                    expected=tuple(phase_names), actual=physical_phase,
                ))
            stages[label]["sender_sends"] += int(counts["sender_sends"])
            stages[label]["sender_bytes"] += int(counts["sender_bytes"])
    actual = (sum(s["sender_sends"] for s in stages.values()),
              sum(s["sender_bytes"] for s in stages.values()))
    expected = (expected_sends, expected_bytes)
    if actual != expected:
        raise ProtocolError(Diagnostic(
            owner=OWNER, function="summarize_e9h_sender_phase_breakdown",
            category="contract", code="P2E_SENDER_PHASE_TOTAL_MISMATCH",
            expected=expected, actual=actual,
        ))
    return stages


def fingerprint_e9h_first_epoch(*, task_events, result) -> str:
    """Fingerprint actual first native Cost/Vote/Score/Commit and receptions.

    Exclude all later epochs so paired 1-vs-300 runs must hash identically.
    """
    if not result.rounds:
        raise ProtocolError(Diagnostic(
            owner=OWNER, function="fingerprint_e9h_first_epoch",
            category="state", code="P2E_FIRST_EPOCH_MISSING",
            expected="one executed native voting epoch", actual=0,
        ))
    first = result.rounds[0]
    sha = hashlib.sha256()
    for event in (*task_events, *first.coordination.events):
        sha.update(repr((
            "SEND", event.phase, event.sender_id, event.receiver_id,
            event.task_id, event.round_id, event.transmission_index,
            event.payload_bytes, event.send_time_ms, event.arrival_time_ms,
        )).encode("utf-8"))
        sha.update(b"\\n")
    for observation in first.coordination.deliveries:
        sha.update(repr((
            "RECEIVE", observation.phase, observation.sender_id,
            observation.receiver_id, observation.task_id,
            observation.round_id, observation.transmission_index,
            observation.delivered, observation.arrival_time_ms,
        )).encode("utf-8"))
        sha.update(b"\\n")
    sha.update(repr(("COMMITTED", first.newly_committed_pairs)).encode("utf-8"))
    return sha.hexdigest()


def run_e9h_original_voting_case(*, scenario, profile, n, seed, p_loss,
                                rate, max_rounds, fixed_timeout_ms,
                                arm, schedules, oracle_total_cost,
                                guarded_cost_ms=None, p_vote_loss=None,
                                external_observer=None, voting_strategy="greedy_task",
                                batch_vote_scope="all", capture_task_epoch_ids=False,
                                capture_assignment_pairs=False,
                                votes_per_voter=100, temperature=5.0,
                                margin_rule="absolute", completion_policy="none"):
    """Original TASK, local cost, physical ballots, Score and Commit only.

    Opt-in p_vote_loss separates Vote drop from Cost p_loss; the original
    E9H behavior defaults p_vote_loss to p_loss without runtime changes.
    """
    name,decision_rule,margin_factor,is_adaptive=arm
    if voting_strategy not in ("greedy_task", "greedy_batch", "greedy_batch_task_order", "probabilistic_batch"):
        raise ProtocolError(Diagnostic(
            owner=OWNER, function="run_e9h_original_voting_case",
            category="data", code="P2_UNKNOWN_VOTING_SCHEDULE",
            expected=("greedy_task", "greedy_batch", "greedy_batch_task_order", "probabilistic_batch"), actual=voting_strategy,
        ))
    vote_loss = p_loss if p_vote_loss is None else p_vote_loss
    task_sampler=create_e9g_sampler(profile=profile,seed=seed,phy_rate_mbps=rate)
    loss_sampler=BernoulliLossSampler(seed=seed)
    task_trace=broadcast_task_information(
        task_positions=scenario.task_positions,num_robots=n,sampler=task_sampler,
        loss_sampler=loss_sampler,p_loss=0.0,phase_timeout_ms=1.0e9,
    )
    costs=reconstruct_local_cost_rows(
        local_robot_positions=scenario.robot_positions,
        announced_tasks_by_robot=task_trace.per_robot_tasks,
    )
    require_local_source_consistency(
        reconstructed=costs,expected=scenario.cost_matrix,
    )
    task_ms=max((e.arrival_time_ms for e in task_trace.events),default=0.0)
    coord_sampler=create_e9g_sampler(profile=profile,seed=seed,phy_rate_mbps=rate)
    if is_adaptive:
        cost_deadline,vote_schedule=schedules[margin_factor]
        cost_timeout=cost_deadline.deadline_ms
        active_schedule=tuple(v.deadline_ms for v in vote_schedule)
        if name.startswith("adaptive_guarded_"):
            if (type(guarded_cost_ms) not in (int,float)
                or not math.isfinite(guarded_cost_ms)
                or guarded_cost_ms < cost_timeout):
                raise ProtocolError(Diagnostic(
                    owner=OWNER,function="run_e9h_original_voting_case",
                    category="dependency",code="E9H_GUARDED_COST_UNAVAILABLE",
                    expected=f"guarded Cost >= {cost_timeout:.6f}ms",
                    actual=guarded_cost_ms,
                ))
            cost_timeout=guarded_cost_ms
    else:
        cost_timeout=fixed_timeout_ms
        active_schedule=None
    result=simulate_democracy_hungarian_retirement(
        cost_matrix=costs,sampler=coord_sampler,loss_sampler=loss_sampler,
        p_loss=p_loss,p_vote_loss=vote_loss,phase_timeout_ms=cost_timeout,
        max_rounds=max_rounds,voting_strategy=voting_strategy,
        vote_decision_rule=decision_rule,vote_repetitions=1,cost_repetitions=1,
        per_active_round_deadline_ms=active_schedule,
        enforce_vote_deadline=True,
        batch_vote_scope=batch_vote_scope,
        probabilistic_seed=(seed if voting_strategy=="probabilistic_batch" else None),
        votes_per_voter=votes_per_voter,temperature=temperature,margin_rule=margin_rule,
        completion_policy=completion_policy,
    )
    if external_observer is not None:
        # Read-only replay of *original* committed-round immutable traces.
        # No additional message, selector, actor or stop condition.
        committed = ()
        for epoch in result.rounds:
            if not epoch.coordination.budget_exhausted:
                committed += epoch.newly_committed_pairs
            external_observer(task_ms + epoch.elapsed_end_ms, committed)
    if isinstance(coord_sampler,WifiCausalTimingSampler):
        a=task_sampler.summarize_network()
        b=coord_sampler.summarize_network()
        expected=(len(task_trace.events)+result.logical_message_count,
                  task_trace.sender_bytes+result.payload_bytes)
        actual=(a["packet_count"]+b["packet_count"],
                a["application_sender_bytes"]+b["application_sender_bytes"])
        if expected!=actual:
            raise ProtocolError(Diagnostic(
                owner=OWNER,function="run_e9h_original_voting_case",
                category="contract",code="E9H_PACKET_LEDGER_MISMATCH",
                expected=expected,actual=actual,
                details=f"n={n} seed={seed} arm={name} loss={p_loss} rate={rate}",
            ))
        sender_by_phase=summarize_e9h_sender_phase_breakdown(
            task_network=a, coordination_network=b,
            expected_sends=expected[0], expected_bytes=expected[1],
        )
        radio={
            "radio_hop_count":a["radio_hop_count"]+b["radio_hop_count"],
            "total_airtime_ms":a["total_airtime_ms"]+b["total_airtime_ms"],
            "total_backoff_ms":a["total_backoff_ms"]+b["total_backoff_ms"],
            "total_queue_ms":a["total_queue_ms"]+b["total_queue_ms"],
        }
    else:
        sender_by_phase=None
        radio={k:"" for k in (
            "radio_hop_count","total_airtime_ms",
            "total_backoff_ms","total_queue_ms",
        )}
    original_physical_late=0
    counted_remote=0
    announced_votes=0
    score_sends=0
    commit_sends=0
    tie_count=0
    winner_votes=[]
    missing_cost=0
    physically_lost_cost=0
    physically_lost_vote=0
    cost_receiver_observations=0
    for epoch in result.rounds:
        active=len(epoch.active_robot_ids)
        d=active_schedule[active-1] if active_schedule is not None else fixed_timeout_ms
        vote_cutoff=epoch.coordination.cost_phase_completion_ms+d
        for obs in epoch.coordination.deliveries:
            if obs.phase == "cost":
                cost_receiver_observations += 1
                if not obs.delivered:
                    physically_lost_cost += 1
            if obs.phase == "vote" and not obs.delivered:
                physically_lost_vote += 1
            if obs.phase=="vote" and obs.delivered and obs.arrival_time_ms is not None:
                if obs.arrival_time_ms > vote_cutoff+1e-9:
                    original_physical_late+=1
                else:
                    counted_remote+=1
            if obs.phase=="cost" and obs.delivered and obs.arrival_time_ms is not None:
                if obs.arrival_time_ms>cost_timeout+1e-9:
                    missing_cost+=1
        for ev in epoch.coordination.events:
            if ev.phase=="vote_score_announcement":
                score_sends+=1
                announced_votes+=int(ev.announced_vote_count or 0)
            if ev.phase=="commit":
                commit_sends+=1
        tie_count+=epoch.coordination.plurality_tie_break_count
        if epoch.coordination.plurality_winner_vote_count:
            winner_votes.append((
                epoch.coordination.plurality_winner_vote_count,
                (active*votes_per_voter if voting_strategy=="probabilistic_batch" else active),
            ))
    expected_cost_receivers = n*(n-1)
    if cost_receiver_observations != expected_cost_receivers:
        raise ProtocolError(Diagnostic(
            owner=OWNER,function="run_e9h_original_voting_case",
            category="contract",code="E9I_COST_RECEIVER_LEDGER_MISMATCH",
            expected=expected_cost_receivers,actual=cost_receiver_observations,
            details=f"n={n} seed={seed} cost_loss={p_loss} vote_loss={vote_loss}",
        ))
    if voting_strategy in ("greedy_batch", "greedy_batch_task_order", "probabilistic_batch"):
        phase_timing = summarize_e9h_phase_timing(task_ms=task_ms, result=result)
    else:
        phase_timing = None
    if commit_sends!=len(result.assigned_pairs):
        raise ProtocolError(Diagnostic(
            owner=OWNER,function="run_e9h_original_voting_case",
            category="safety",code="E9H_COMMIT_LEDGER_MISMATCH",
            expected=len(result.assigned_pairs),actual=commit_sends,
        ))
    full=int(result.full_assignment_success)
    identity=json.dumps(result.assigned_pairs,separators=(",",":"))
    digest=hashlib.sha256(identity.encode("utf-8")).hexdigest()
    margin_str="" if margin_factor is None else margin_factor
    return {
        "seed":seed,"robots":n,"tasks":n,
        "model":("rady_bootstrap_no_shared_channel" if rate is None
                 else "e9g_shared_medium_backoff_proxy"),
        "modeled_phy_rate_mbps":"" if rate is None else rate,
        "loss_probability":p_loss,
        "cost_loss_probability":p_loss,
        "vote_loss_probability":vote_loss,
        "cost_remote_receiver_observation_count":cost_receiver_observations,
        "cost_remote_packet_drop_count":physically_lost_cost,
        "vote_remote_packet_drop_count":physically_lost_vote,
        "cost_effective_peer_view_fraction":(
            (cost_receiver_observations-physically_lost_cost-missing_cost)
            /cost_receiver_observations if cost_receiver_observations else 1.0
        ),
        "arm":name,"decision_rule":decision_rule,
        "margin_factor":margin_str,
        "deadline_cost_ms":cost_timeout,
        "deadline_vote_initial_ms":(
            active_schedule[-1] if active_schedule is not None else fixed_timeout_ms
        ),
        "deadline_vote_final_ms":(
            active_schedule[0] if active_schedule is not None else fixed_timeout_ms
        ),
        "full_commit":full,
        "tasks_committed":len(result.assigned_pairs),
        "guard_hit":int(not full and len(result.rounds)>=max_rounds),
        "rounds_executed":len(result.rounds),
        "certified_score_edge_count":(
            result.rounds[0].coordination.certified_score_edge_count
            if voting_strategy=="probabilistic_batch" and result.rounds else ""
        ),
        "certified_score_supported_tasks":(
            result.rounds[0].coordination.certified_score_supported_tasks
            if voting_strategy=="probabilistic_batch" and result.rounds else ""
        ),
        "certified_score_max_matching":(
            result.rounds[0].coordination.certified_score_max_matching
            if voting_strategy=="probabilistic_batch" and result.rounds else ""
        ),
        "completion_fallback_pairs":(
            result.rounds[0].coordination.completion_fallback_pairs
            if voting_strategy=="probabilistic_batch" and result.rounds else ()
        ),
        "completion_fallback_count":(
            len(result.rounds[0].coordination.completion_fallback_pairs)
            if voting_strategy=="probabilistic_batch" and result.rounds else 0
        ),
        "task_announcement_ms":task_ms,
        "allocation_or_stop_ms":task_ms+result.global_agreement_ms,
        "successful_allocation_ms":(
            task_ms+result.global_agreement_ms if full else ""
        ),
        "total_sender_application_bytes":task_trace.sender_bytes+result.payload_bytes,
        "total_original_send_count":len(task_trace.events)+result.logical_message_count,
        "sender_by_phase":sender_by_phase,
        "first_epoch_sha256":fingerprint_e9h_first_epoch(
            task_events=task_trace.events, result=result,
        ),
        "voting_strategy":voting_strategy,
        **({"native_assignment_pairs":tuple(result.assigned_pairs)}
           if capture_assignment_pairs else {}),
        "votes_per_voter":(votes_per_voter if voting_strategy=="probabilistic_batch" else ""),
        "vote_temperature":(temperature if voting_strategy=="probabilistic_batch" else ""),
        "margin_rule":(margin_rule if voting_strategy=="probabilistic_batch" else ""),
        **({"voted_task_ids":tuple(epoch.voted_task_id for epoch in result.rounds),
            "newly_committed_by_epoch":tuple(epoch.newly_committed_pairs for epoch in result.rounds)}
           if capture_task_epoch_ids else {}),
        "task_announcement_sender_frames":len(task_trace.events),
        "cost_sender_frames":sum(e.phase=="cost" for epoch in result.rounds for e in epoch.coordination.events),
        "vote_sender_frames":sum(e.phase=="vote" for epoch in result.rounds for e in epoch.coordination.events),
        "phase_timing":phase_timing,
        "vote_score_send_count":score_sends,
        "commit_send_count":commit_sends,
        "late_remote_vote_delivery_count":original_physical_late,
        "counted_remote_vote_delivery_count":counted_remote,
        "late_cost_delivery_count":missing_cost,
        "announced_valid_candidate_votes":announced_votes,
        "candidate_tie_count":tie_count,
        "mean_winner_support_share":(
            statistics.mean(v/active for v,active in winner_votes)
            if winner_votes else ""
        ),
        "winner_vote_share_denominator":("total emitted vote tickets" if voting_strategy=="probabilistic_batch" else "active voters"),
        "minimum_winner_votes":(
            min(v for v,_active in winner_votes) if winner_votes else ""
        ),
        "assignment_digest_sha256":digest,
        "total_assignment_cost":result.total_cost,
        "full_information_hungarian_cost":oracle_total_cost,
        "total_cost_over_hungarian_ratio":(
            result.total_cost/oracle_total_cost if full and oracle_total_cost>0 else ""
        ),
        **radio,
    }


def pair_e9h_against_fixed(rows: list[dict[str,object]]) -> None:
    """Never use future outcomes to select deadlines; this is observer-only QA."""
    by_key={}
    for row in rows:
        key=(row["seed"],row["robots"],row["model"],
             row["modeled_phy_rate_mbps"],row["loss_probability"])
        if row["arm"]=="fixed_quarter":
            by_key[key]=row
    for row in rows:
        key=(row["seed"],row["robots"],row["model"],
             row["modeled_phy_rate_mbps"],row["loss_probability"])
        baseline=by_key.get(key)
        if baseline is None:
            raise ProtocolError(Diagnostic(
                owner=OWNER,function="pair_e9h_against_fixed",
                category="contract",code="E9H_MISSING_PAIRED_BASELINE",
                expected="one fixed_quarter for every matched seed/model/loss",
                actual=key,
            ))
        row["matched_fixed_quarter_full"]=baseline["full_commit"]
        row["matched_fixed_quarter_ms"]=baseline["allocation_or_stop_ms"]
        row["paired_time_delta_ms"]=(
            float(row["allocation_or_stop_ms"])-float(baseline["allocation_or_stop_ms"])
        )
        row["same_assignment_as_fixed"]=(
            int(row["assignment_digest_sha256"]==baseline["assignment_digest_sha256"])
            if row["full_commit"] and baseline["full_commit"] else ""
        )
        row["cost_delta_vs_fixed"]=(
            float(row["total_assignment_cost"])-float(baseline["total_assignment_cost"])
            if row["full_commit"] and baseline["full_commit"] else ""
        )


def summarize_e9h_cases(rows: list[dict[str,object]]) -> list[dict[str,object]]:
    """Summary separates successful time from incomplete censored stop time."""
    groups={}
    for row in rows:
        key=(row["robots"],row["model"],str(row["modeled_phy_rate_mbps"]),
             row["loss_probability"],row["arm"])
        groups.setdefault(key,[]).append(row)
    out=[]
    for (n,model,rate,p,arm),part in sorted(groups.items()):
        full=[r for r in part if r["full_commit"]]
        times=[float(r["allocation_or_stop_ms"]) for r in part]
        good=[float(r["successful_allocation_ms"]) for r in full]
        matches=[int(r["same_assignment_as_fixed"]) for r in part
                 if r["same_assignment_as_fixed"]!=""]
        support=[float(r["mean_winner_support_share"]) for r in part
                 if r["mean_winner_support_share"]!=""]
        out.append({
            "robots":n,"tasks":n,"model":model,"modeled_phy_rate_mbps":rate,
            "loss_probability":p,"arm":arm,"seeds":len(part),
            "full_commit_count":len(full),
            "full_commit_rate":len(full)/len(part),
            "guard_hits":sum(int(r["guard_hit"]) for r in part),
            "mean_all_seed_stop_ms":statistics.mean(times),
            "p95_all_seed_stop_ms":percentile(times,0.95),
            "mean_successful_allocation_ms":(
                statistics.mean(good) if good else ""
            ),
            "p95_successful_allocation_ms":(
                percentile(good,0.95) if good else ""
            ),
            "mean_sender_bytes":statistics.mean(
                int(r["total_sender_application_bytes"]) for r in part
            ),
            "mean_sender_sends":statistics.mean(
                int(r["total_original_send_count"]) for r in part
            ),
            "mean_committed_tasks":statistics.mean(
                int(r["tasks_committed"]) for r in part
            ),
            "mean_rounds_executed":statistics.mean(
                int(r["rounds_executed"]) for r in part
            ),
            "mean_late_remote_votes":statistics.mean(
                int(r["late_remote_vote_delivery_count"]) for r in part
            ),
            "mean_late_cost_receipts":statistics.mean(
                int(r["late_cost_delivery_count"]) for r in part
            ),
            "mean_candidate_score_sends":statistics.mean(
                int(r["vote_score_send_count"]) for r in part
            ),
            "mean_winner_support_share":statistics.mean(support) if support else "",
            "mean_full_cost_over_hungarian":statistics.mean(
                float(r["total_cost_over_hungarian_ratio"]) for r in full
                if r["total_cost_over_hungarian_ratio"]!=""
            ) if full else "",
            "agreement_with_fixed_completed_pair_count":len(matches),
            "agreement_with_fixed_when_both_full":(
                statistics.mean(matches) if matches else ""
            ),
            "deadline_cost_ms":part[0]["deadline_cost_ms"],
            "deadline_vote_initial_ms":part[0]["deadline_vote_initial_ms"],
        })
    return out


def summarize_e9h_scaling(summary: list[dict[str,object]]) -> list[dict[str,object]]:
    """Finite observed slopes only where every N has full completion."""
    bins={}
    for r in summary:
        key=(r["model"],str(r["modeled_phy_rate_mbps"]),
             r["loss_probability"],r["arm"])
        bins.setdefault(key,[]).append(r)
    out=[]
    for (model,rate,p,arm),group in sorted(bins.items()):
        group.sort(key=lambda x:x["robots"])
        complete=all(r["full_commit_count"]==r["seeds"] for r in group)
        mean_column="mean_successful_allocation_ms" if complete else "mean_all_seed_stop_ms"
        b,rsq=e9g_loglog_exponent([
            (int(r["robots"]),float(r[mean_column])) for r in group
        ])
        out.append({
            "model":model,"modeled_phy_rate_mbps":rate,
            "loss_probability":p,"arm":arm,
            "points":len(group),"all_scales_100pct_commit":int(complete),
            "time_series_kind":("successful_allocation" if complete
                                else "censored_all_seed_stop_NOT_allocation"),
            "empirical_time_beta":b,"loglog_r_squared":rsq,
            "NOT_A_MATHEMATICAL_BIG_O_PROOF":True,
        })
    return out


def create_e9h_deadline_curve(*, profile, sizes, design_rate_mbps, margins):
    """Explicit plot-ready deadline phase formula table, frozen before runs."""
    lines=[]
    for n in sizes:
        for margin in margins:
            cost,votes=build_e9h_deadline_schedule(
                profile=profile,robots=n,design_rate_mbps=design_rate_mbps,
                margin_factor=margin,
            )
            row=asdict(cost)
            row["vote_deadline_initial_ms"]=votes[-1].deadline_ms
            row["vote_deadline_last_ms"]=votes[0].deadline_ms
            row["legacy_fixed_ms"]=DEFAULT_OLD_FIXED_MS
            row["one_time_guarded_initial_cost_ms"]=estimate_e9h_guarded_initial_cost_ms(
                profile=profile,total_robots=n,total_tasks=n,
                reference_phy_mbps=design_rate_mbps,
            )
            row["expected_original_sender_bytes_if_full_zero_loss"]=(
                24*n*n+92*n+16*math.ceil(n/37)
            )
            row["expected_original_sender_sends_if_full_zero_loss"]=(
                n*(n-1)//2+3*n+math.ceil(n/37)
            )
            lines.append(row)
    return lines


def save_e9h_evidence(*, root, rows, summary, exponents, deadlines,
                      source_sha, profile, rates, sizes, losses, margins,
                      design_rate_mbps, seeds, first_seed,
                      historical, max_rounds) -> None:
    """Formal evidence manifest hashes every original row, not just plots."""
    files=[
        ("per_seed_e9h.csv",rows),
        ("summary_e9h.csv",summary),
        ("empirical_exponents_e9h.csv",exponents),
        ("deadline_curve_e9h.csv",deadlines),
    ]
    hashes={}
    for name,data in files:
        if not data:
            raise ProtocolError(Diagnostic(
                owner=OWNER,function="save_e9h_evidence",
                category="contract",code="E9H_EMPTY_EVIDENCE_TABLE",
                expected="nonempty rows",actual=name,
            ))
        path=root/name
        with path.open("w",newline="",encoding="utf-8") as fh:
            w=csv.DictWriter(fh,fieldnames=tuple(data[0].keys()))
            w.writeheader();w.writerows(data)
        hashes[name]=hashlib.sha256(path.read_bytes()).hexdigest()
    m={
        "study":"E9H_variable_deadline_received_plurality_ABLATION_original_Voting_only",
        "evidence_kind":"SIMULATED_ORIGINAL_GREEDY_NOT_NS3_NOT_MEASURED_WIFI",
        "created_utc":datetime.now(timezone.utc).isoformat(),
        "source_git_sha":source_sha,
        "baseline_e9g_original_source_sha":E9G_REFERENCE_SOURCE_SHA,
        "baseline_fixed_timeout_ms":DEFAULT_OLD_FIXED_MS,
        "original_historical_e9g_100seed":historical,
        "rady_original_repo_commit":RADY_SOURCE_COMMIT,
        "rady_original_file_blob_sha":RADY_SOURCE_BLOB_SHA,
        "rady_sample_count":len(profile.samples_ms),
        "rady_mean_ms":statistics.mean(profile.samples_ms),
        "rady_p95_ms":percentile(profile.samples_ms,0.95),
        "deadlines_formula":"mean_Rady + k*(p95_Rady-mean_Rady) + 2*n*(PHY_preamble + AIFS + CWmin/2*slot + ACK + 8*(payload+64)/(1000*reference_Mbps))",
        "one_time_guarded_cost_formula":"max_Rady + 2*N*(PHY_preamble + AIFS + CWmin*slot + ACK + 8*(full_cost_row+64)/(1000*design_Mbps)) + 1ms",
        "unit":"ms",
        "max_robots_equals_tasks":max(sizes),
        "sizes":list(sizes),"seeds_per_cell":seeds,"first_seed":first_seed,
        "loss_probabilities":list(losses),
        "assumed_phy_rates_mbps_not_measured":list(rates),
        "design_phy_rate_mbps_ASSUMED":design_rate_mbps,
        "predeclared_tail_margin_k":list(margins),
        "actual_original_voting_arms":[x[0] for x in iter_e9h_arms(margins)],
        "max_rounds":max_rounds,
        "tasks_reliable_initial":True,
        "cost_and_vote_loss_independent_Bernoulli":True,
        "old_protocol_baseline_frozen_from_E9G":True,
        "received_plurality":"highest positive on-time received candidate tally; tie lowest candidate ID; never force zero votes",
        "comparison_rules":"matched seeds per N/loss/network; same credible Rady profile; external Hungarian observer never supplied to voters",
        "fixed_and_adaptive_both_enforce_true_global_deadline":True,
        "no_actual_ns3_edca_ofdma_wifi_client_calibration":True,
        "original_csv_sha256":hashes,
        "actual_rows":len(rows),"summary_rows":len(summary),
        "no_results_written_to_README_until_independently_verified":True,
    }
    (root/"manifest.json").write_text(
        json.dumps(m,ensure_ascii=False,indent=2)+"\n",encoding="utf-8",
    )


def run_e9h_experiment(*,sizes,rates,losses,margins,seeds,first_seed,
                       max_rounds,dataset,output_root,design_rate_mbps,
                       historical_e9g_zip=None,allow_download=True):
    validate_e9h_experiment(
        sizes=sizes,rates=rates,losses=losses,margins=margins,
        seeds=seeds,first_seed=first_seed,max_rounds=max_rounds,
        design_rate_mbps=design_rate_mbps,
    )
    if output_root.exists() and (
        not output_root.is_dir() or any(output_root.iterdir())
    ):
        raise ProtocolError(Diagnostic(
            owner=OWNER,function="run_e9h_experiment",category="state",
            code="E9H_OUTPUT_EXISTS",expected="new/empty output directory",
            actual=str(output_root),
        ))
    historical=verify_historical_e9g_zip(historical_e9g_zip)
    profile=load_rady_latency_profile(
        ensure_rady_dataset(dataset,allow_download=allow_download)
    )
    src=subprocess.check_output(["git","rev-parse","HEAD"],text=True).strip()
    if len(src)!=40 or any(ch not in "0123456789abcdef" for ch in src):
        raise ProtocolError(Diagnostic(
            owner=OWNER,function="run_e9h_experiment",category="dependency",
            code="E9H_GIT_SHA_UNVERIFIED",expected="40 hex HEAD",actual=src,
        ))
    output_root.mkdir(parents=True,exist_ok=True)
    curve=create_e9h_deadline_curve(
        profile=profile,sizes=sizes,design_rate_mbps=design_rate_mbps,
        margins=margins,
    )
    rows=[]
    partial=output_root/"per_seed_e9h.partial.csv"
    with partial.open("w",newline="",encoding="utf-8") as fp:
        writer=None
        for n in sizes:
            schedules={
                margin:build_e9h_deadline_schedule(
                    profile=profile,robots=n,design_rate_mbps=design_rate_mbps,
                    margin_factor=margin,
                ) for margin in margins
            }
            once_guard_cost=estimate_e9h_guarded_initial_cost_ms(
                profile=profile,total_robots=n,total_tasks=n,
                reference_phy_mbps=design_rate_mbps,
            )
            for seed in range(first_seed,first_seed+seeds):
                scenario=generate_e0_scenario(seed,n,n)
                oracle_total=solve_hungarian_assignment(
                    scenario.cost_matrix
                ).total_cost
                for p_loss in losses:
                    for rate in (None,*rates):
                        key_rows=[]
                        for arm in iter_e9h_arms(margins):
                            row=run_e9h_original_voting_case(
                                scenario=scenario,profile=profile,n=n,seed=seed,
                                p_loss=p_loss,rate=rate,max_rounds=max_rounds,
                                fixed_timeout_ms=DEFAULT_OLD_FIXED_MS,
                                arm=arm,schedules=schedules,
                                oracle_total_cost=oracle_total,
                                guarded_cost_ms=once_guard_cost,
                            )
                            key_rows.append(row)
                        pair_e9h_against_fixed(key_rows)
                        for row in key_rows:
                            rows.append(row)
                            if writer is None:
                                writer=csv.DictWriter(fp,fieldnames=tuple(row.keys()))
                                writer.writeheader()
                            writer.writerow(row)
                            fp.flush()
            print(f"E9H_DONE N={n} seeds={seeds} accumulated_rows={len(rows)}",flush=True)
    expected=len(sizes)*seeds*len(losses)*(1+len(rates))*len(iter_e9h_arms(margins))
    if len(rows)!=expected:
        raise ProtocolError(Diagnostic(
            owner=OWNER,function="run_e9h_experiment",category="contract",
            code="E9H_INCOMPLETE_FACTORIZED_GRID",
            expected=expected,actual=len(rows),
        ))
    summary=summarize_e9h_cases(rows)
    exponents=summarize_e9h_scaling(summary)
    save_e9h_evidence(
        root=output_root,rows=rows,summary=summary,
        exponents=exponents,deadlines=curve,source_sha=src,
        profile=profile,rates=rates,sizes=sizes,losses=losses,
        margins=margins,design_rate_mbps=design_rate_mbps,
        seeds=seeds,first_seed=first_seed,
        historical=historical,max_rounds=max_rounds,
    )
    partial.unlink()
    print(f"E9H_COMPLETE rows={len(rows)} root={output_root} source={src}",flush=True)
    return rows


def main() -> None:
    p=argparse.ArgumentParser(
        description="E9H original Greedy Voting: deadline x plurality x network x loss"
    )
    p.add_argument("--sizes",type=parse_e9g_sizes,default=DEFAULT_SIZES)
    p.add_argument("--rates-mbps",type=parse_e9g_rates,default=DEFAULT_RATES)
    p.add_argument("--loss-probabilities",
                   type=lambda v:parse_e9h_floats(v,is_loss=True),
                   default=DEFAULT_LOSSES)
    p.add_argument("--margin-factors",
                   type=lambda v:parse_e9h_floats(v,is_loss=False),
                   default=DEFAULT_MARGIN_FACTORS)
    p.add_argument("--design-rate-mbps",type=float,default=144.0)
    p.add_argument("--seeds",type=int,default=100)
    p.add_argument("--first-seed",type=int,default=0)
    p.add_argument("--max-rounds",type=int,default=300)
    p.add_argument("--historical-e9g-zip",type=Path)
    p.add_argument("--dataset",type=Path,
                   default=Path("data/external/rady/perama_range_testing.json"))
    p.add_argument("--no-download",action="store_true")
    p.add_argument("--output-root",type=Path,
                   default=Path("results/e9h_adaptive_plurality"))
    args=p.parse_args()
    run_e9h_experiment(
        sizes=args.sizes,rates=args.rates_mbps,
        losses=args.loss_probabilities,margins=args.margin_factors,
        seeds=args.seeds,first_seed=args.first_seed,
        max_rounds=args.max_rounds,dataset=args.dataset,
        output_root=args.output_root,design_rate_mbps=args.design_rate_mbps,
        historical_e9g_zip=args.historical_e9g_zip,
        allow_download=not args.no_download,
    )


if __name__=="__main__":
    main()

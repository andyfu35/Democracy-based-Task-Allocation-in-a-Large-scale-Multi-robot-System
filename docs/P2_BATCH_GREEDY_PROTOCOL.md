# P2-B — One-shot task and Cost intake, batched Greedy voting (revised comparison)

**Status:** runner now executes **1,000 fresh Voting simulations** and reuses **3,000 SHA-verified baseline rows** for the complete four-method comparison; new Voting test/formal results are **not yet validated**. The previous 2026-10-13 source-audited P2 4,000-case results are **immutable historical evidence**, not new P2-B results. Do not silently reuse their Voting 20.13s at PL30 or 27.50s at PL90, because those times include up to 100 sequential per-task voting epochs.

## Discovered cause and explicit change

The previous P2 execution **already announced the entire task set once** with `task_information.broadcast_task_information` (one logical TASK broadcast, naturally fragmented into as many <=1,200-byte application frames as needed). Each robot calculated its own cost to *every* task; the existing `coordination.capture_retirement_cost_snapshot` **already broadcast exactly one Cost row per robot per run**, preserving only receiver-delivered rows. The actual temporal issue was `coordination.simulate_democracy_hungarian_retirement`: `greedy_task` took `pending_task_ids[:1]` and paid serial Vote/Score/Commit delays for up to 100 successive tasks. Original P2's Stop seconds are genuinely the times for that serial protocol, **not** incorrectly counted TASK or Cost 100 times.

P2-B is a **deliberate new Voting protocol version** `greedy_batch`, not a cosmetic correction or an unchanged "Original Voting." We keep capacity=1 and use a single initial snapshot. Every active robot plans its entire remaining task list locally using ascending-task sequential Greedy **only on the Cost rows physically visible to that robot**. The local proposal is a partial one-to-one assignment if fewer Cost rows than pending tasks were delivered; no hidden missing data are supplied.

Each membership epoch now physically charges the following actual application messages:

1. TASK: all 100 task positions reliably announced once before allocation (one **logical** announcement, multiple frames only if required by 1,200B packet size), and retained.
2. Cost: 100 robots each broadcast their entire local 100-task Cost row **once**, with original receiver loss and initial guarded deadline; a row is never broadcast again during retries.
3. Vote: each currently active robot broadcasts **one framed batch Vote** packet containing its planned pairs. 16B header + 8B for every `(task_id,candidate_id)`; physically lost/late per-receiver arrivals are **not counted**, local self-votes are counted.
4. Score: each candidate broadcasts **one reliable framed Score vector** (16B + 8B per `(task_id,count)`) containing only votes that the candidate actually received. All parties observe these Score broadcasts and apply a deterministic task-order, descending received-vote-count, lower-ID tie break, with already assigned robots excluded. Never commit the same robot twice. If no positive-score eligible candidate remains for a task, the task stays pending.
5. Commit: each selected executor broadcasts its own reliable 28B Commit packet after all Score frames arrive, retiring both robot and task using the **existing** `protocol.apply_announced_retirement_commits` owner. Retry the remaining tasks in a later batch epoch using **only the original retained Cost snapshot**, up to the existing 300-epoch Voting guard. No second state machine or simulator-only global forced assignment was introduced.

The frames are <=1,200 application Bytes. For 100 tasks, a full Vote payload is 816B. Physical Vote/Score timing uses existing `WifiCausalTimingSampler`; the independent predeclared batch Vote deadline uses the actual 16+8×active frame width in `network.estimate_e9h_adaptive_deadline`, not a falsely fast 32B single-task deadline. All original baseline message owners, payloads, native stop rules and stage guards remain unchanged. This is **not** a claim of a measured physical Wi-Fi network.

## Verified baseline reuse — no re-execution of CBAA, CBBA or Price Auction

The formal run requires `--baseline-zip "$HOME/Downloads/p2_loss10_100seed.zip"`, pointing to the exact **immutable historical P2 ZIP**: ZIP SHA256 `1d08a167308b9368ee2a764737066223ac041a5bd6508621c7b6cd0320036bb9`, raw 4,000-row CSV SHA256 `78c4871a9f0e391c11c92ace9c2b532695d2a2c4ca40d31166e31bf89901e5fc`, and executed original SHA `f514cfa3613e7b0bad5c739d136b09fea8c3f92c`. Dedicated read-only source owner `experiments.p2_baseline_reuse.read_verified_original_baselines` checks ZIP SHA/CRC, original manifest, all 4,000 original keys, 100R100T/C1/PL/seed contract and the 3,000 selected baseline rows against deterministic scene SHA. If missing, tampered, incomplete or re-zipped, **abort before any simulation**. It never re-executes baseline code or imports the 1,000 historical sequential Voting rows.

The revised runner writes new `per_seed_p2.csv` (**1,000 Voting-only rows, append-only/resumable**), `summary_voting_p2b.csv` (10 rows), and read-only evidence-derived `per_seed_p2_combined.csv` (4,000 rows) with explicit `source_role` and `source_git_sha` for **every** new/reused row. Recalculate `summary_p2.csv` (40 groups, including complete original four-way paired-success cost cohort) and regenerate `packet_loss_robustness.svg` **all four panels from scratch**. The new `manifest_p2.json` SHA-attests outputs and records `new_voting_executions=1000`, `baseline_reused_rows=3000`, `combined_comparison_rows=4000`, old archive SHA256, and distinct original/new source identities.

**Chart scope:** regenerate the entire P2 four-panel B comparison after the 1,000 new Voting cases. Do **not** relabel other old A/C/D manuscript charts as batched Voting merely by copying this P2 cohort: their robot counts, task counts, time budgets, or controls may differ. For any other figure that uses old Voting, rerun **Voting only on those exact scenarios** and replot against independently verified unchanged baseline evidence. Preserve all historical original-version plots, and publish new ones with a visible new source version.

## Study freeze and complete-evidence contract

- Exactly `voting` **(new batched Greedy implementation)** vs `cbaa`, `cbba`, `price_auction` **(unchanged original native baselines)**. The old user-authored `voting_multitask` capacity-one extension and team-authored Paid CBAA remain excluded. Chart names: **Voting (Batched Greedy), CBAA, CBBA, Price Auction**, without 'Original' prefixes.
- 100 robots/100 tasks; robot capacity one; 100 paired Seeds per PL; original deterministic 100m scenes. PL 0%,10%,...,90% = 10×100×1=**1,000 fresh Voting simulations** and 10×100×3=**3,000 reused original native baseline rows**, yielding **4,000 source-attributed comparison rows** and 40 derived summary rows.
- Packet-loss probabilities applied to physically announced Cost and Vote as before; reliable TASK/Score/Commit retained as explicitly specified. Voting guard 300 epochs, other baseline guard 160. Never assume time or feasibility of other algorithms' terminal guarantees are equivalent to the paid Voting Commit.
- Task/Cost/Vote/Score/Commit event sender Bytes and native modeled time are *measured from the new source events*, not estimated by subtracting N times an old task wait. For each newly run Voting row, `original_traffic_ledger_json.batch` contains `task_announcement_sender_frames`, `cost_sender_frames` (must =100), `vote_sender_frames`, `score_sender_frames`, `commit_sender_frames` and additive `phase_timing` with `task_ms, cost_once_ms, vote_and_score_ms, commit_ms, total_ms, epochs`.
- At PL0 the 100-task one-epoch batch must produce exactly the full-information **sequential Greedy reference assignment**. This does not imply Hungarian optimality: independent Euclidean/Hungarian ratio can still be >1. The relevant no-loss logic sanity is Voting / full-information Greedy=1, not necessarily Voting / Hungarian=1.
- All failures and guard timeouts remain in the all-seed native-success denominators. Cost ratio of different algorithms is reported only with explicit per-method native-success condition (and/or four-way matched successful seed intersections); no failure imputed zero. P2-B has a **new executed Git source SHA** and **new output directory**; original P2 10%-grid raw SHA and published README figure are archival until revised original ZIP is audited.

## Focused local tests and experiment commands (NO CI)

Run from the existing repo directory, after switching to `experiment/p2-batched-greedy-voting` (no assumption about home directory):

```bash
git fetch origin
git switch experiment/p2-batched-greedy-voting
git pull --ff-only
python3 -m compileall -q democracy_mrta experiments tests
python3 -m unittest discover -s tests -p 'test_p1_*.py' -v
python3 -m unittest discover -s tests -p 'test_p2_*.py' -v

# Critical 0% / 30% / 90% short smoke. Fresh directory required:
python3 -m experiments.run_p2_packet_loss \
  --losses 0.00,0.30,0.90 --seeds 2 \
  --output-root "results/p2_batch_smoke_$(date +%Y%m%d_%H%M%S)"

# Official revised formal run, only after every smoke/test passes:
set -o pipefail
P2B_ROOT="results/p2_batched_greedy_10pct_100seed_$(date +%Y%m%d_%H%M%S)"
python3 -m experiments.run_p2_packet_loss \
  --formal --seeds 100 \
  --baseline-zip "$HOME/Downloads/p2_loss10_100seed.zip" \
  --output-root "$P2B_ROOT" 2>&1 | tee "$P2B_ROOT.log"
test -f "$P2B_ROOT/manifest_p2.json" && \
  zip -r "$HOME/Downloads/p2_batched_greedy_10pct_100seed.zip" "$P2B_ROOT" "$P2B_ROOT.log"
```

If interrupted, `--formal --seeds 100 --baseline-zip "$HOME/Downloads/p2_loss10_100seed.zip" --output-root "$P2B_ROOT" --resume` resumes only an exact source/config/prefix, and the log must use a fresh path. Never resume an old original P2 (Git `f514cfa...`) partial directory after this protocol change; old experiment data is immutable.

**Required independent checks before README promotion:** exactly 1,000 new Voting rows (no other methods executed), 3,000 source-attested original baseline rows, 4,000 combined provenance-marked rows and 40 derived summary groups, all paired task geometries and Hungarian oracles; native packet framing, sender/receiver ledger sums including dropped batch Vote broadcasts, unique candidate & task Commit for capacity1, TASK broadcasts only once, Cost exactly 100 frames (no more across retries), `phase_timing` summation, no-loss full-Greedy assignment parity, source SHA matching exactly new manifest, and original baselines' paired result preservation. Publication data should not alter the old original P2 raw ZIP/graph.

## Named true owners and first failing diagnostics

- `optimizer.solve_visible_batched_greedy_assignment`: `state/BATCH_GREEDY_NO_VISIBLE_ROWS`, `data/BATCH_GREEDY_INVALID_VISIBLE_ROW` (the actual local-planning owner).
- `coordination.validate_epoch_voting_strategy`, `build_epoch_local_proposals`, `simulate_democracy_hungarian_retirement` (same original membership and Cost owner); new `encode_greedy_batch_packet`, `decode_greedy_batch_packet`, `collect_greedy_batch_votes`, `publish_greedy_batch_scores`, `resolve_capacity_one_batch_winners`, `emit_greedy_batch_commits`, `simulate_greedy_batch_vote_epoch` each own one physical/decision operation. Diagnostics `data/BATCH_GREEDY_INVALID_PACKET_KIND,BATCH_GREEDY_INVALID_PACKET_RECORD`, `contract/BATCH_GREEDY_PACKET_EXCEEDS_LIMIT,BATCH_GREEDY_INVALID_RECEIVED_PACKET`; original `protocol.validate_one_to_one_commits` safety invariant, original cost validation and native stop categories remain.
- `network.estimate_e9h_adaptive_deadline`: `phase=vote_batch` and 816B payload at active100, preserving prior original vote/time-owner diagnostics.
- `experiments.run_e9h_adaptive_deadline.build_e9h_deadline_schedule` and `run_e9h_original_voting_case` accept an opt-in `voting_strategy`; `summarize_e9h_phase_timing`: `time/P2_BATCH_NEGATIVE_PHASE_DURATION,P2_BATCH_STAGE_TIME_MISMATCH`. Original P1 `run_original_voting` defaults unchanged `greedy_task`.
- `experiments.run_p2_packet_loss.validate_config`: `contract/P2_BATCH_FORMAL_VOTING_STRATEGY`; new study identity includes `voting_strategy` so previous P2 raw cannot be silently resumed as new protocol.
- `experiments.p2_packet_loss_plot.panel/render_p2_figure`: graphical overlap representation uses distinct dash segments and concentric rings at exactly the same measured data coordinate; there is **no numeric point shifting** and no Original prefix.

**Unfinished:** new code has not been proven on the user's Mac, no formal 1,000 new Voting runs executed, and no revised result or claim of measured timing improvement is asserted. High-loss batch retries or large score vectors can still be substantial; receiver-independent Bernoulli drops and hypothetical 144Mbps remain experimental limitations.

## Per-seed result gates

Before writing each revised Voting row, `experiments.run_p2_packet_loss.validate_batched_voting_evidence` verifies task-frame count, exactly N initial Cost SENDs, each Commit matching a task, and additive TASK/Cost/Vote-and-Score/Commit milliseconds. At zero packet loss it requires a single voting epoch and the identical full-information sequential Greedy pairing. Failures identify the original diagnostic or their validation category/code; old P2 evidence must not be substituted.

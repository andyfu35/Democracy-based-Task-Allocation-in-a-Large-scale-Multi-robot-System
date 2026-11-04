# P2T — P2S Direct Peer Conflict Comparison (No Task Owner)

**Branch:** `experiment/p2t-peer-conflict-no-task-owner-20261104`

**Status:** GitHub source and focused tests prepared, **native P2T smoke and 100-seed runs pending local execution**. P2S baseline below is from an already executed separate 400-case user archive, NOT a result of P2T.

## Research question and scope

User proposal: after independent local Hungarian optimization and P2S statistical Cost/Vote exchange, each prospective executor announces its target. **Only those robots who actually receive a same-task competitor's announcement directly compare** their support scores and locally announced execution costs, and the losers select another task. No fixed per-task owner, COMMIT/DENY sender, GRANT/ACK, global Score matrix, invisible result synchronization, or oracle repair.

As originally requested, this is an intentionally **unsafe under loss proof-of-concept**. A robot that misses an opposing announcement can mistake a contested task as uncontested. Its subsequent P2TE is an attempted action, NOT authoritative permission to actuate a physical robot. The experiment must count simultaneous duplicate attempts as failures, rather than silently use global knowledge to prevent them.

One change concern: **post-vote direct-peer coordination only**. The original physical P2S Cost/Vote owner and 1,000-ticket `adaptive_local_matching` policy remain unchanged.

## Precise per-receiver information

Each voter knows its own full Cost row, and only physically received peer Cost rows. A `democracy_mrta.coordination.simulate_p2k_local_vote_epoch` call generates one sender-paid Cost and one sender-paid 1016B P2KV Vote per robot, each per receiver subject to the original Bernoulli packet loss and time window.

Each potential executor considers ONLY its own `run.local_assignments` / self-received Vote support / own true Cost row, and personally received actual P2TI or P2TE messages. There is no shared magic list of active peers, received peer bids or globally executing tasks during decisions. An offline observer sees all attempted pairs only to compute validation metrics.

## Protocol

1. Every unassigned robot selects one task from its own receiver-local Hungarian result or the existing `select_p2m_local_request_task` vote-support/own-cost fallback, excluding personally rejected and personally received executing tasks.
2. It physically broadcasts **three 36-byte P2TI copies** (`tag,round,robot,task,support_votes,received_ballots,tickets_per_task,own_task_cost`) by default. Every attempted SEND counts, including packets lost by all receivers. An originator knows only its own message for free.
3. Each current candidate (i) compares only physically received *current-round* P2TI candidates for its own task (t). Define
   ```
   S_i(t) = support_votes_i(t) / max(1, received_ballots_i * tickets_per_task)
   ```
   Prefer **larger S**, then larger raw support, then **lower announced own task cost**, then smaller robot ID. These are deterministic local comparisons; the inputs are not guaranteed identical across receivers.
4. A candidate that personally sees a stronger same-task candidate **yields without task-owner denial**, adds this task to its local rejection set, and chooses another task next round. A locally highest candidate attempts execution and exits further selection.
5. Every attempted winner physically sends **three 16-byte P2TE** executing notices. Only actually delivered notices update another robot's knowledge. There is NO P2RC, DENY, ACK, GRANT or owner reservation, and no implicit safety guarantee for those winners.
6. Stop after no selectable candidate or max 101 rounds, with native append-only evidence of original attempted SENDs, receiver drops, peer conflicts, duplicate attempts, missing tasks and conditional costs. No offline repair is permitted.

**Important limitation:** A missing competitor announcement is not evidence of absence. With packet loss, two or more robots can each conclude they won the same task. Even if all received announcements are correctly decoded and rankings are deterministic, this algorithm cannot guarantee unique physical execution without a common accepted decision or another safety mechanism.

## Mathematical objective and primary benchmark

Same **100 robots / 100 tasks / capacity=1**, same `generate_e0_scenario(seed,100,100)`, loss `0/30/50/90%`, seeds `0..99`, same Rady empirical-delay samples + modeled single 144 Mbps radio proxy. Not real Wi-Fi validation. Planning CPU time is excluded.

**Primary quality metric = relative increase over global optimum, never Greedy:**

```text
C_opt(seed) = min_{one-to-one full X} sum_i,t C[i,t] X[i,t]
            = offline scipy.optimize.linear_sum_assignment(C)
G(seed,loss) = 100 * (C_P2T(seed,loss) / C_opt(seed) - 1)
```

Report `G` ONLY if every task was attempted **exactly once** (`full_valid_allocation=1`), with no duplicates or missing tasks. Otherwise set `actual_cost_if_valid`, `optimality_gap_percent_if_valid` and `greedy_gap_percent_if_valid` to empty. **Do not use a partial attempted sum as proof of lower allocation cost.**

Per loss, `mean_valid_optimality_gap_percent` is the arithmetic mean of the individual per-seed valid-case ratios, NOT ratio of pooled costs. Always report `valid_cost_samples`. Secondary reference `global_greedy_cost` and `greedy_gap_percent_if_valid` are retained but NOT the headline measure.

Completeness is a separate metric: `unique_task_count` counts tasks with exactly one recorded tentative attempt, `duplicate_task_count` tasks with >1 attempts, `unassigned_task_count` tasks with no attempt. `distinct_coverage_percent` includes duplicated tasks; it MUST NOT be called safe completion. The local decision protocol is intentionally allowed to have errors; the observer MUST NOT replace assignments.

## Matched previous P2S baseline for later comparisons

Archive: `p2s_formal_100seed.zip`, SHA256 `92537c8fea3983d7adebd4c5ee1164ef007b2829a2d20b9b94b4a9eb8f25d7da`, source SHA `3e4c067a9dd18bd32c0546af60dbfafeee363622`. Using its PL0 exact Hungarian per-seed result as the offline reference:

| PL | P2S true full safe execution | Mean gap to Hungarian optimal, valid-case only |
|---|---:|---:|
| 0% | 100/100 | 0.000% |
| 30% | 100/100 | +12.874% |
| 50% | 100/100 | +15.385% |
| 90% | 0/100 | undefined / no full-case samples |

These are historical P2S values, **not P2T outcome**. Compare P2T and P2S at the same seeds/loss/100R100T, but label their **different safety and termination contracts**. P2T's possibly shorter stop time does not imply equivalent safe execution.

## Owners and error contracts

- `optimizer.sample_p2s_adaptive_matching_votes` unchanged: optimize only locally received Cost rows; `coordination.simulate_p2k_local_vote_epoch` unchanged: physically deliver Cost/Vote and private local matching.
- `democracy_mrta.claim_resolution::validate_p2t_peer_scope` – `contract/P2T_INVALID_PEER_SCOPE`.
- `encode_p2t_peer_intent / decode_p2t_peer_intent` – `data/P2T_INVALID_OWN_COST`, `data/P2T_INTENT_SIZE_INVALID`, `contract/P2T_INTENT_TAG_OR_COST_INVALID`, `contract/P2T_IDLE_INTENT_ON_WIRE`; reuses original validated self-support envelope.
- `transmit_p2t_peer_intents` – original charged broadcast SEND and independent per-receiver Cost/Vote/announcement loss semantics.
- `choose_p2t_peer_winners` – `state/P2T_OWN_INTENT_NOT_VISIBLE`; exactly one local peer-comparison concern.
- `encode_p2t_execution_notice/decode_p2t_execution_notice` – `data/P2T_INVALID_EXECUTION_NOTICE`, `data/P2T_EXEC_NOTICE_SIZE_INVALID`, `contract/P2T_EXEC_NOTICE_IDENTITY_MISMATCH`.
- `transmit_p2t_execution_notices` – actual P2TE SEND/receipt only.
- `validate_p2t_attempts` – `safety/P2T_ROBOT_CAPACITY_VIOLATION` (invalid source), diagnostic `safety/P2T_UNOBSERVED_PEER_COLLISION` (observed unsafe duplicate) or `planning/P2T_INCOMPLETE_PEER_COVERAGE`; **diagnostics do not repair the outcome**.
- `coordinate_p2t_peer_conflicts` – single opt-in peer lifecycle in true task coordination owner, `state/P2T_ROBOT_REACTED_TWICE`; does not use existing P2R fixed owner / reservation machine or duplicate that state.
- `experiments.run_p2t_peer_conflicts::validate_p2t_axes` – `data/P2T_INVALID_STUDY_AXES`. `audit_p2t_case` – independent safety/contract/source SEND audit; `summarize_p2t`, `save_p2t_evidence`, `run_p2t` are report owner; `state/P2T_OUTPUT_ALREADY_EXISTS`.

Diagnostic fields: first failing owner/function/category/code plus expected/actual/details as applicable; allowed categories data/time/state/dependency/planning/safety/runtime/contract.

## Local Mac runbook

```bash
git fetch origin
git switch --track origin/experiment/p2t-peer-conflict-no-task-owner-20261104
python3 -m compileall -q democracy_mrta experiments tests
python3 -m unittest discover -s tests -p 'test_p2t*.py' -v
python3 -m unittest discover -s tests -p 'test_p2s*.py' -v
python3 -m unittest discover -s tests -p 'test_p2r*.py' -v
```

If already tracked locally, use `git switch experiment/p2t-peer-conflict-no-task-owner-20261104` and `git pull --ff-only`.

Smoke with PL0/30/90 and seeds 0,1 (6 cases); it should **not fail** merely for observed duplicate attempts at nonzero PL, but the zero-loss optimal assignment parity IS mandatory:

```bash
P2T_SMOKE="results/p2t_smoke_$(date +%Y%m%d_%H%M%S)"
python3 -m experiments.run_p2t_peer_conflicts \
  --losses 0.00,0.30,0.90 --seeds 2 \
  --robots 100 --tasks 100 \
  --output-root "$P2T_SMOKE"
```

If focused tests and smoke pass, formal PL0/30/50/90 ×100 seeds = 400 cases:

```bash
set -o pipefail
P2T_FORMAL="results/p2t_formal_$(date +%Y%m%d_%H%M%S)"
python3 -m experiments.run_p2t_peer_conflicts \
  --losses 0.00,0.30,0.50,0.90 --seeds 100 \
  --robots 100 --tasks 100 \
  --output-root "$P2T_FORMAL" 2>&1 | tee "$P2T_FORMAL.log"

zip -j "$HOME/Downloads/p2t_peer_conflicts_100seed.zip" \
  "$P2T_FORMAL/per_seed_p2t.csv" \
  "$P2T_FORMAL/summary_p2t.csv" \
  "$P2T_FORMAL/audit_p2t.jsonl" \
  "$P2T_FORMAL/run_config_p2t.json" \
  "$P2T_FORMAL/manifest_p2t.json" \
  "$P2T_FORMAL.log"
```

**Acceptance conditions:** PL0 100/100 exact Hungarian parity; all attempted SENDs (including dropped) physically billed; no hidden full-cost repair; report independent unique/duplicate/missing and objective gap to Hungarian; no P2R owner/commit control messages in P2T; no claim that tests passed until local run completes.


## P2U — Optional reliable all-roster announcements with paid ACK and causal timing

**Branch:** `experiment/p2u-peer-ack-reliable-announcement-20261104`. P2T is unchanged unless `--reliable-announcements` is enabled. P2S adaptive-local-matching Cost/Vote and legacy P2R fixed Task Owner are untouched.

### Contract and bounded liveness

For each decision round `q`, every **known** robot (including already attempted or currently idle robots) sends exactly one logical status:
- `P2US` **40 bytes**, `(tag, round, robot, task or NO_TASK, self_support, ballots_received, tickets_per_task, mode, own_cost)`;
- mode `OFFER / EXECUTED / IDLE`; each sender supplies **its own** candidate Cost and status, never another robot's hidden Cost;
- a receiver sends a physical `P2UA` **16-byte** ACK for each actual P2US delivery; both successful and dropped SEND/ACK attempts count toward sender Bytes;
- at most `max_ack_retries` (1..256) windows are attempted. A sender stops retransmitting to peers whose ACK actually arrived. A receiver de-duplicates repeated statuses from the same sender in the same round.

**Safety boundary:** A robot with an OFFER may elect itself or yield ONLY if it has physically received `N/N` same-round statuses from the entire fixed known roster, including its own. If missing even one, it holds its tentative task without attempting execution. If a later received `EXECUTED` status advertises an already attempted task, an OFFER for that task is rejected and locally retargeted. The winner rule is the unchanged P2T rational normalized-vote support, raw support, lower own announced cost, smaller ID. There is no fixed per-task owner, P2RC, P2RD or free global consensus.

This is a conservative **known-roster synchronous** trial, not a crash-tolerant distributed consensus proof. With nonzero packet loss and finite retries, no unconditional delivery or completion guarantee exists. Even at 0% loss the ACK overhead is O(N²) unicast sends per round.

### Causal radio service: first failed owner / function / code

The user's first native P2U smoke originally stopped at:
`network.WifiCausalTimingSampler.sample_packet_ms / time / E9G_NONCAUSAL_PACKET_RELEASE`.

The root owner was `claim_resolution.transmit_p2u_reliable_statuses` incorrectly sending later broadcasts and ACKs at an earlier *batch* release timestamp after preceding ACKs had already entered the single shared-medium queue. The correct owner solution is:
- schedule **each** next sender broadcast at the current `finish`, not a stale per-attempt `release`;
- after actually receiving P2US, schedule the next ACK at `max(finish, status_arrival)` and update `finish` with its actual modeled arrival;
- preserve the strict original `WifiCausalTimingSampler.sample_packet_ms` time guard; **do not suppress E9G diagnostics**.

The owner and diagnostic boundaries remain:
- `claim_resolution.validate_p2u_ack_scope/data/P2U_INVALID_RELIABLE_ROSTER`;
- `claim_resolution.encode_p2u_status/data/P2U_INVALID_STATUS_FIELDS`;
- `claim_resolution.decode_p2u_status/data/P2U_STATUS_SIZE_INVALID` or `contract/P2U_STATUS_TAG_INVALID`;
- `claim_resolution.validate_p2u_ack_receipt/contract/P2U_ACK_CONTENT_MISMATCH`;
- `network.WifiCausalTimingSampler.sample_packet_ms/time/E9G_NONCAUSAL_PACKET_RELEASE` must not occur for valid P2U event order;
- `claim_resolution.validate_p2t_attempts/safety/P2T_UNOBSERVED_PEER_COLLISION` remains the real offline collision alarm, never an oracle repair.

### Evidence and acceptance

Original baseline fields are preserved without the flag; P2U adds `reliable_announcements`, `max_ack_retries`, physical `p2u_status_*`, `p2u_ack_*` SEND/Bytes/drop columns and conditional summaries. An offline auditor may add executed task knowledge only from an actually received **later-round** P2US EXECUTED status after a physically attempted P2TE, not from a same-round OFFER. All attempted physical Cost/Vote/Status/ACK/P2TE transmissions (including drops) are charged. Experiment manifest must label the P2U opt-in study.

**Primary cost metric** remains `optimality_gap_percent_if_valid=100*(C_P2U/C_Hungarian_optimal-1)`, only when all tasks are uniquely attempted with zero collisions. Do not assign a cost-quality gap to incomplete or duplicate allocations. Overall completion rate, duplicates, missing tasks, ACK bytes and modeled coordination time must be shown separately.

### Mac local validation

The remote branch is the source of truth; **no downloadable patch is required**. Execute compile + `test_p2u*.py`, `test_p2t*.py`, `test_p2s*.py`, `test_p2r*.py` first, then 2 seeds x 0/30/50% smoke:

```bash
python3 -m compileall -q democracy_mrta experiments tests
python3 -m unittest discover -s tests -p 'test_p2u*.py' -v
python3 -m unittest discover -s tests -p 'test_p2t*.py' -v
python3 -m unittest discover -s tests -p 'test_p2s*.py' -v
python3 -m unittest discover -s tests -p 'test_p2r*.py' -v
P2U_SMOKE="results/p2u_ack_smoke_$(date +%Y%m%d_%H%M%S)"
python3 -m experiments.run_p2t_peer_conflicts \
  --reliable-announcements --max-ack-retries 24 \
  --losses 0.00,0.30,0.50 --seeds 2 \
  --robots 100 --tasks 100 --max-rounds 20 \
  --output-root "$P2U_SMOKE"
```

100-seed formal evidence remains pending real native test and smoke verification, including genuine Rady profile; no performance claims before that.


**P2U receiver-cache clarification (same protocol):** `select_p2u_ready_peer_candidates` records a physically delivered `EXECUTED` status for *every receiver*, even if the receiver is already finished and is not a current candidate. Eligibility checks remain restricted to current candidates, and all decisions still require their full N/N current-round roster. The experiment's execution-knowledge audit uses this identical actual-receipt rule, so it cannot invent or drop knowledge at a non-candidate receiver. A dedicated regression verifies this cache consistency.


## P2U Bitmap ACK optimization — separate optional experimental transport

**Reason for change:** In the first real P2U native smoke, 100R/100T with guaranteed all-roster status + individual unicast ACKs required 341.863/342.346s even with PL0; 30% needed 2064.102/3568.536s and 50% needed 3670.169/5124.797s. This is **modeled coordination time, not CPU compute time nor real RF measurement**. At PL0, O(N²) individual ACKs (N*(N-1)=9,900 for N=100) dominate the serialized Rady/144Mbps timing, not Hungarian planning.

**Preserve original as a named baseline:** `--reliable-announcements --ack-mode unicast` is the original 16-byte P2UA per-receiver ACK model, still the default mode. P2S/P2T and P2R behaviors are unaffected. Do **not** silently re-label any previously gathered P2U unicast evidence as Bitmap. The new mode is `--reliable-announcements --ack-mode bitmap`.

**Only the ACK transport changes:**
- Data still uses the same honest 40B P2US OFFER/EXECUTED/IDLE broadcast, with original `_lossy_broadcast_deliveries` independent per-receiver Bernoulli loss. The receiver's own local status is self-known.
- Each receiver `r` accumulates `H_r={i: P2US_i	ext{ was physically received by }r}cup{r}`.
- Instead of N-1 separate unicast P2UA, **each robot broadcasts one cumulative ACK bitmap P2UB per retry window**. Header `<4sIII>` is 16B containing literal `P2UB`, current round, physical sender (the receiver acknowledging), and total N. Payload is `ceil(N/8)` bytes, little-endian bitset `H_r`; thus **29B at N=100**. The packet's sending identity, round, roster N, length, self bit and out-of-range bits are checked.
- Every physical P2UB broadcast is charged as one application sender-SEND even if all other peers drop it. Each recipient's P2UB delivery is independently sampled with the exact original Bernoulli model and recorded. A sending robot `i` marks recipient `r` confirmed **only when P2UB_r was actually received by i AND bit i is set**; a bit in a lost P2UB is never used.
- A P2US sender whose every known recipient has acknowledged its status may cease retransmitting. Unconfirmed senders send the original P2US again in the next window (to all peers physically, even if only some ACKs are pending). Duplicates are harmless: the same sender/round status simply replaces its prior identical local entry. One P2UB is sent by **every** roster robot each active retry window; no hidden aggregation node, centralized arbiter, MAC reliability or free shared bitsets.
- Even if P2UB confirmation is lost, the receiver may have actually received P2US; **only the receiver's actual local view determines its N/N decision gate**. Thus missing ACKs may cause redundant physical transmissions but cannot fabricate an unknown status.
- Every `_broadcast_event` starts at current `finish` from prior physical SEND, and `finish` advances with modeled arrival. Strict `WifiCausalTimingSampler.sample_packet_ms / time / E9G_NONCAUSAL_PACKET_RELEASE` remains active and unmodified.
- Finite `--max-ack-retries` 1..256 still bounds communication; PL>0 does not guarantee liveness, and missing N/N status means HOLD, not execution.

**0%-loss wire expectation for a 100-robot single status round (P2U sub-protocol only):**
- Original P2U: 100 P2US (4,000B) + 100*99=9,900 P2UA (158,400B) = 10,000 SENDs / **162,400B**.
- P2U Bitmap: 100 P2US (4,000B) + 100 P2UB (100*29=2,900B) = **200 SENDs / 6,900B**.
This omits the shared TASK, Cost, Vote and P2TE transmissions, and is a deterministic protocol count, NOT a claim of measured model time. At PL>0, *every retransmission and dropped sender-SEND remains billed*; completion/cost must be re-measured.

**Responsible names:** `claim_resolution.encode_p2u_ack_bitmap` (`data/P2U_INVALID_BITMAP_ACK`), `decode_p2u_ack_bitmap` (`data/P2U_ACK_BITMAP_SIZE_INVALID`, `contract/P2U_ACK_BITMAP_IDENTITY_MISMATCH`), `transmit_p2u_reliable_statuses_bitmap` (physical sender-pay radio events and actual receiver-only status/ACK evidence), and the existing `coordinate_p2t_peer_conflicts` mode dispatch (`data/P2U_INVALID_ACK_MODE`). Experiment owner `validate_p2t_axes` validates `--ack-mode`, `audit_p2t_case` counts actual `p2u_ack_bitmap` packets/Bytes/receiver drops, and `run_p2t` identifies a distinct `_BITMAP_ACK` study suffix; original `p2u_ack` counts are zero in bitmap mode, never relabeled as new traffic. Strict Network time owner is unchanged.

**Cost and completion evaluation:** report full safe task completion, actual duplicates/missing, all physical application SEND/Bytes, modeled coordination time, and `100*(C_alloc/C_Hungarian_opt -1)` **only when all 100 tasks are uniquely attempted**. 0% optimality parity test remains. Do not compare partial-cost totals as improved optimization.

**Validation:**
```bash
python3 -m unittest discover -s tests -p 'test_p2u*.py' -v
python3 -m unittest discover -s tests -p 'test_p2t*.py' -v
python3 -m unittest discover -s tests -p 'test_p2s*.py' -v
python3 -m unittest discover -s tests -p 'test_p2r*.py' -v
P2U_FAST="results/p2u_bitmap_smoke_$(date +%Y%m%d_%H%M%S)"
python3 -m experiments.run_p2t_peer_conflicts \
  --reliable-announcements --ack-mode bitmap --max-ack-retries 24 \
  --losses 0.00,0.30,0.50 --seeds 2 --robots 100 --tasks 100 \
  --max-rounds 20 --output-root "$P2U_FAST"
```

**Status:** Source and tests committed on GitHub; this container cannot run the complete repo checkout with the original Rady profile. Native P2U Bitmap performance and results are pending local smoke validation. No observed time reduction, completion guarantees or ACK superiority are claimed before direct native data.

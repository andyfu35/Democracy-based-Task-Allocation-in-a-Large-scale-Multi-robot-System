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

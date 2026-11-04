# P2V — Cost-first Task Owner arbitration on P2S visible Hungarian votes

**Branch:** `experiment/p2v-cost-first-owner-20261104`.

**Status:** New opt-in owner arbitration protocol and native test runner are committed; native 2-seed / 100-seed runs MUST still be executed on the local Mac. The goal of reducing 30% loss Hungarian cost gap below the original P2S 12.87% is a hypothesis, not an achieved result.

## Objective and one bounded concern

After the **unchanged** P2S Cost-row broadcast, per-receiver locally visible Hungarian matching, adaptive backup voting and 1016B P2KV Vote broadcasts, existing P2R fixed task owners currently arbitrate simultaneous contenders primarily by rational vote support, regardless of the physical cost of each candidate's offered task.

P2V tests ONE optimization change: among genuinely delivered candidate INTENTs for a task, choose the **minimum sender-advertised own task cost**, using rational own vote support as a tie breaker. A sender can know its own full Cost row; the owner can use that scalar cost ONLY if its associated 36B candidate INTENT is physically received. The owner cannot read unknown robot rows, nor can it exploit the offline global Hungarian matrix as an arbitration oracle.

The original P2S+P2R support-first owner policy remains default, and the old 28B P2RI packets remain exactly 28B. P2V is explicitly opt-in; it never modifies default P2R claims, winner rules, message lengths, reservations or historical data.

## Exact new physical wire

`P2VI` Cost-bearing Intent: `struct.Struct("<4sIIIIIId")`, 36 bytes:
- 4 byte tag `P2VI` (distinct from original `P2RI`);
- 6 uint32 values: sender's claim round, sender robot ID, target task ID, sender-local support ticket count, number of originally physically received ballots, and task-balanced ticket count;
- 1 binary64 scalar: **this sender's own Cost for this task only**.

The new scalar is validated finite and nonnegative. The recipient decodes the packet's sender identity/round and validates ticket support via the original `decode_p2l_claim_packet` contract. The originally validated `P2LClaim` is reused with one optional `own_task_cost` field defaulting to `None`, ensuring original P2R and P2L code paths remain unchanged.

One original INTENT broadcast phase per pending sender/round is preserved, with 3 repeated physical sends by default; every attempted 36B SEND counts toward sender bytes even if all recipients lose it. P2V introduces **no Cost-row rebroadcast, global all-roster ACK, extra vote or central controller**. Existing same-task peer challenge P2RH, owner P2RC/P2RD, and P2NX after authentic COMMIT remain unchanged.

## Precise optimization

Let `A_t` contain ONLY candidate P2VI claims physically observed by task `t`'s fixed Owner in that owner round, with `c_(r,t)` the **claimed sender's own finite cost**:

```text
r*(t) = argmin_{r in A_t} (
   c_(r,t),
   - support_votes(r,t)/max(1, ballots_received(r)*tickets_per_task),
   - support_votes(r,t),
   - ballots_received(r),
    robot_id(r)
)
```

This is a *local contested-task cost optimization*, not a new globally optimal assignment solver. It cannot guarantee lower full global cost: a cheap winner may displace another candidate to an even more costly task. It also cannot compare peers whose physical P2VI dropped; previous owner reservations are still irreversible. What it CAN test cleanly is whether **prefer actual low-cost received contenders** yields lower formal 100R100T total cost under packet loss.

P2S's zero-loss complete-information Hungarian solution has no contender conflict by design, so P2V must reproduce the exact same global Hungarian one-to-one matching at 0% loss.

### Explicit owner/function diagnostic boundary

- `claim_resolution.attach_p2v_local_cost`: `data/P2V_OWN_TASK_COST_UNAVAILABLE` or `data/P2V_INVALID_OWN_TASK_COST` for an invalid sender OWN row/task.
- `claim_resolution.encode_p2v_cost_intent`: `data/P2V_INVALID_COST_INTENT` for missing/invalid cost, with existing `encode_p2l_claim_packet` support validation retained.
- `claim_resolution.decode_p2v_cost_intent`: `data/P2V_INVALID_COST_INTENT_LENGTH` or `contract/P2V_COST_INTENT_CONTENT_INVALID`, plus original validated P2L claim identity/round/ticket diagnostics.
- `claim_resolution.choose_p2v_cost_owner_winner`: `contract/P2V_MISSING_OWNER_RECEIVED_COST` if any candidate entered the new owner comparison without a genuinely validated scalar cost.
- `claim_resolution.coordinate_p2r_announced_intents`: `data/P2V_INVALID_OWNER_POLICY` for unsupported policy; otherwise the existing true P2R owner state machine, irreversible reservation, physical responses and retry semantics remain unchanged.
- `experiments.run_p2v_cost_first_owner.evaluate_p2v_cost_evidence`: `contract/P2V_COST_INTENT_BYTES_MISMATCH` if physical P2RI phase's bytes are not exactly 36×attempted sends, and `contract/P2V_WRONG_BALLOT_POLICY` / `P2V_EVIDENCE_SCHEMA_MISMATCH` for wrong experiment evidence. P2S native `P2S_ZERO_LOSS_OPTIMAL_PARITY` remains mandatory.
- `experiments.run_p2v_cost_first_owner.run_p2v`: `state/P2V_OUTPUT_ALREADY_EXISTS` for an output directory that is not fresh.

All errors include first failing owner/function/category/code, expected/actual where relevant. Categories data/time/state/dependency/planning/safety/runtime/contract only.

## Fair cost baseline and matched native 100 seeds

Frozen 100 robots, 100 tasks, capacity=1, same scene seeds 0..99 and loss probabilities `0/30/50%`, one original Cost + 1016B Vote broadcast per robot, unchanged 3/3/3 P2R intent/decision/P2NX repetitions and original Rady/144Mbps sampled hypothetical shared medium.

Only full and collision-free physical COMMIT execution can be cost-scored:

```text
C_opt(seed) = Hungarian(C_full(seed))
Gap_v(seed,loss) = 100 * (C_executed_v(seed,loss)/C_opt(seed) - 1)
MeanGap_v(loss) = arithmetic mean of per-seed Gap_v over valid fully completed seeds
```

No partial cost gap, no zero-filled missing task costs, and no falsely comparing different seed cohorts. **The primary benchmark is Hungarian full-information global optimum, not Global Greedy**. Report full completion count out of 100, valid cost sample count, duplicate count, physically attempted sender Bytes, native modeled stop, and task-owner denial counts.

Historical P2S+P2R native baseline from user's earlier formal archive (`p2s_formal_100seed.zip`), reanalyzed against full Hungarian per seed:

| Packet loss | P2S full safe | P2S mean cost above true global optimum |
|---|---:|---:|
| 0% | 100/100 | +0.000% |
| 30% | 100/100 | +12.874% |
| 50% | 100/100 | +15.385% |
| 90% | 0/100 | not applicable |

These are **historical P2S results**, NOT P2V results. P2V may reduce or increase gap and could change completion; only native formal measurements establish the outcome.

## Native runbook (no ZIP patch)

```bash
git fetch origin
git switch --track origin/experiment/p2v-cost-first-owner-20261104
python3 -m compileall -q democracy_mrta experiments tests
python3 -m unittest discover -s tests -p 'test_p2v*.py' -v
python3 -m unittest discover -s tests -p 'test_p2s*.py' -v
python3 -m unittest discover -s tests -p 'test_p2r*.py' -v
```

If already tracking this branch locally, use `git switch experiment/p2v-cost-first-owner-20261104` followed by `git pull --ff-only`.

First run six native cases: 2 seeds × 0%,30%,50% loss.

```bash
P2V_SMOKE="results/p2v_cost_first_smoke_$(date +%Y%m%d_%H%M%S)"
python3 -m experiments.run_p2v_cost_first_owner \
  --losses 0.00,0.30,0.50 --seeds 2 --robots 100 --tasks 100 \
  --output-root "$P2V_SMOKE"
```

Only after smoke succeeds, formal 300 cases: 100 paired seeds ×0%,30%,50% loss.

```bash
P2V_FORMAL="results/p2v_cost_first_formal_$(date +%Y%m%d_%H%M%S)"
python3 -m experiments.run_p2v_cost_first_owner \
  --losses 0.00,0.30,0.50 --seeds 100 --robots 100 --tasks 100 \
  --output-root "$P2V_FORMAL"
zip -j "$HOME/Downloads/p2v_cost_first_100seed.zip" \
  "$P2V_FORMAL/per_seed_p2v.csv" "$P2V_FORMAL/summary_p2v.csv" \
  "$P2V_FORMAL/audit_p2v.jsonl" "$P2V_FORMAL/run_config_p2v.json" \
  "$P2V_FORMAL/manifest_p2v.json"
```

## Acceptance gates

1. `--losses 0`: exact full Hungarian pairing for each seed, no exceptions, real physical P2RC, no duplicate robots/tasks.
2. `30/50%`: **do not assume** 100% complete; record the actual 100-seed full-completion rate before comparing cost. If any condition loses completion, the cost-only gains on its successful subset must be qualified.
3. Compare 30% `mean_valid_optimality_gap_percent` to original P2S **12.874%**, 50% to **15.385%**, with exact matching seeds and source cost generator. A 5% goal is a stretch target, not a result or acceptance override.
4. Count the full 36B each SEND vs old 28B, including dropped packets and retries; no unexplained hidden Cost traffic.
5. Native timing is Rady-profiled Wi-Fi proxy, not real measured robot WLAN performance, and optimizer CPU is not included.

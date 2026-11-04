# P2S — Adaptive Local Matching Votes with Native P2R Conflict/COMMIT

Branch: `experiment/p2s-adaptive-local-matching-voting-20261104`

**Status: integrated source and focused tests prepared; native formal data pending local execution.** No statement that P2S outperforms P2R is warranted until original native sender/receiver results have been run and audited.

## Bounded research question

Can a robot with its own complete cost row and only physically received **whole peer Cost-row packets** produce better task assignments by voting its **local maximum-cardinality minimum-cost matching** plus an adaptive visible-only cheapest-task backup?

This P2S is a new ballot-generation arm, NOT a new Cost, Vote, INTENT, CHALLENGE, DENY, COMMIT or EXECUTING transport. It preserves the 100 robot / 100 task / capacity-one P2R comparison cohort (different from the earlier isolated 100/50 synthetic prototype).

## Canonical owners

- `optimizer.sample_p2s_adaptive_matching_votes`: only local received Cost rows; solve rectangular Hungarian (max cardinality, min local cost); add backup and deterministically apportion task tickets. No network or runtime state.
- `optimizer.sample_p2k_task_balanced_votes`: policy dispatch; original `optimized_rank_square`, `optimized_kbest`, and `cost_softmax` modes preserved.
- `coordination.validate_p2k_local_scope`: accepts named new policy without changing packet budget; `simulate_p2k_local_vote_epoch` remains one physically lossy Cost and Vote broadcast per robot, separate receiver local matrices.
- `claim_resolution.coordinate_p2r_announced_intents`: original, unchanged physical INTENT -> CHALLENGE -> owner COMMIT/DENY -> EXECUTING control flow. Only actual received COMMIT authorizes execution.
- `experiments.run_p2r_intent_conflict_commit.run_one_p2r_case`: existing single native case, optional **named policy** parameter with original rank-square default fully retained. `make_p2r_evidence_row` records actual policy and unchanged physical sender-byte audit.
- `experiments.run_p2s_adaptive_local_matching`: P2S-specific configuration, validation, run, conditional summary and immutable per-run evidence.

Every diagnostic first indicates owner/function/category/code, with data/time/state/dependency/planning/safety/runtime/contract categories.

## Ballot equation

Let `S_r` be robot `r`'s physically received Cost-row IDs, including its own row. Only entries `C[i,t]` for `i in S_r` are read.

Local matching:

```text
M_r = max-cardinality minimum-cost matching of C[S_r, all tasks]
gamma_r = (N - |S_r|)/(N-1)
b_r(t) = argmin_{i in S_r} (C[i,t], i)
W_r(i,t) = 1[i = M_r(t)] + gamma_r * 1[i = b_r(t)]
```

If `M_r(t)` has no assignment because `|S_r| < tasks`, use `W_r(i,t)=1[i=b_r(t)]` to avoid a guaranteed empty nomination. Each task's weights are converted to **exactly 10 one-byte candidate tickets** by the existing `optimizer.apportion_p2q_task_tickets` deterministic largest-remainder owner; 100 tasks -> 1000 tickets -> original **1016B P2KV physical broadcast**. If all rows are visible, `gamma=0`, thus votes reproduce exact local Hungarian proposals, with no backup. There is no extra Cost/Vote SEND.

P2S is distinct from the synthetic prototype's global reliable vote pooling: votes are physically received per receiver, and the physical task-owner COMMIT protocol can still fail under packet loss.

## Ground-truth separation and safety

The global scene cost matrix is passed as a pure cost source only to the exact previously received row indices. `validate_p2s_native_row` uses ground truth for **offline** zero-loss optimal parity and capacity-one/duplicate execution verification after the native result, never as an execution fallback.

No unknown cost is substituted or zero-filled; no global oracle receives votes at runtime. Original P2R failure/incomplete semantics and physical SEND accounting remain in force. Lost commit may leave a task reserved but unexecuted. P2S also does not guarantee full completion, global optimality or distribution-free robustness.

## Test commands (run locally)

```bash
git fetch origin
git switch --track origin/experiment/p2s-adaptive-local-matching-voting-20261104
git pull --ff-only
python3 -m compileall -q democracy_mrta experiments tests
python3 -m unittest discover -s tests -p 'test_p2s*.py' -v
python3 -m unittest discover -s tests -p 'test_p2r*.py' -v
```

If the branch is already local, use `git switch experiment/p2s-adaptive-local-matching-voting-20261104` instead of `git switch --track`.

Smoke: 100 robots, 100 tasks, seeds 0 and 1, packet loss 0/30/90, **six physically modeled P2S cases**:

```bash
P2S_SMOKE="results/p2s_smoke_$(date +%Y%m%d_%H%M%S)"
python3 -m experiments.run_p2s_adaptive_local_matching \
  --losses 0.00,0.30,0.90 --seeds 2 \
  --robots 100 --tasks 100 \
  --output-root "$P2S_SMOKE"
```

Formal run only after smoke passes: 0/30/50/90% x seeds 0..99 = **400 P2S native cases**. No historical baseline rerun or results replacement.

```bash
P2S_FORMAL="results/p2s_formal_$(date +%Y%m%d_%H%M%S)"
python3 -m experiments.run_p2s_adaptive_local_matching \
  --losses 0.00,0.30,0.50,0.90 --seeds 100 \
  --robots 100 --tasks 100 \
  --output-root "$P2S_FORMAL" 2>&1 | tee "$P2S_FORMAL.log"
zip -j "$HOME/Downloads/p2s_adaptive_local_matching_100seed.zip" \
  "$P2S_FORMAL/per_seed_p2s.csv" \
  "$P2S_FORMAL/summary_p2s.csv" \
  "$P2S_FORMAL/audit_p2s.jsonl" \
  "$P2S_FORMAL/run_config_p2s.json" \
  "$P2S_FORMAL/manifest_p2s.json" \
  "$P2S_FORMAL.log"
```

## Acceptance gates

1. Loss 0%: 100/100 full native execution and **exact Hungarian pairing** per seed; otherwise fail `experiments.run_p2s_adaptive_local_matching/validate_p2s_native_row/contract/P2S_ZERO_LOSS_OPTIMAL_PARITY`.
2. One original Cost and one original Vote SEND per robot, all physical retransmits and dropped sends included in sender bytes.
3. Loss 30/50/90%: report true full native completion, mean task coverage, sender bytes, modeled coordination time and full-completed-only cost gap against offline Global Greedy. No partial cost misrepresented as full quality.
4. Compare historical P2R only at same seeds/robots/tasks/loss, and label P2R status separately. Different study cohorts (synthetic 100/50 or different control guarantee) must not be silently compared as identical.
5. No experiments or full regression suite can be called passed until actually run in a local checkout with pinned Rady latency dataset. This is simulated WiFi timing, **not real RF evidence**.

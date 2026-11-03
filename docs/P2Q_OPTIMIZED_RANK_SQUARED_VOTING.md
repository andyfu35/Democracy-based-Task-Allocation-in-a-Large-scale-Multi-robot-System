# P2Q — Optimized Rank-Squared Votes, NO CLAIM or Owner Safety

Branch: experiment/p2q-optimized-rank-square-votes
Study ID: P2Q_OPTIMIZED_KBEST_RANK_SQUARED_NO_CLAIM_ONLY
Status: Source and targeted test authored in GitHub; actual native
Python unit and 10-seed experimental validation pending user Mac run.

## Research hypothesis, and what MUST NOT be concluded

User asks whether increasing the gap between rank 1 / rank 2 /
rank 3 candidates, after a local optimized assignment, can remove
observed equal received vote counts and prevent the duplicated task
executions of P2K. This study changes ONLY the voter-side
optimized-proposal-to-ticket allocation. It deliberately contains
NO CLAIM, ACK, GRANT, DENY, EXECUTING, PSCR, reliable Score,
Commit, global fusion, retransmission or owner state machine.

There are TWO distinct hypotheses; never conflate them:
- Local received TOP-VOTE TIE reduction. Even this is NOT
  guaranteed with discrete 10-votes-per-task and lossy ballots.
- Cross-robot full matching AGREEMENT and zero duplicated tasks.
  Even when every receiver has zero vote-score ties, receivers
  may have DIFFERENT unambiguous winners. Their independent
  matching self-claims can still collide or leave tasks empty.

A P2Q observed complete 100/100 one-to-one union is a result
for that Seed and Loss, NOT proof of safe asynchronous
exactly-once execution. Without a unique reliable COMMIT or
coordination, robots cannot distinguish silence from a lost
conflicting ballot. Report missing and duplicate tasks honestly.

## Original physical vote protocol (unchanged)

100 robots,100 tasks,one robot per task (capacity1), each voter
sends exactly ONE Cost row physical lossy broadcast and ONE
1016B P2KV physical lossy Vote broadcast (1000 candidate
uint8 tickets plus 16B original header), identical to P2K.
Each task has exactly 1000/100=10 integer tickets per voter.
Physical per-receiver Cost and Vote losses are Bernoulli
p_loss 0/30/50/90%; each robot sees ONLY truly received rows
and vote packets, including its own original Cost and ballot.
An external TASK startup is still model-reliable and sender
paid, unchanged and disclosed. All original physically
attempted sender Bytes count regardless of receiver success.
The same Rady hypothetical Wi-Fi6 shared 144 Mbps timing
proxy is used; CPU Hungarian optimization time excluded.

## Ranked-square vote construction (NEW opt-in policy only)

The true voter optimizer function is
democracy_mrta.optimizer.sample_p2k_task_balanced_votes
(policy="optimized_rank_square", k=5, epsilon=0.0,
temperature=5.0, votes_per_voter=1000).
This uses the existing policy="optimized_kbest" PROPOSAL
CONSTRUCTION; no new optimizer state machine:

1. Each voter reconstructs its OWN actually delivered Cost rows.
2. Solve the exact locally visible Hungarian minimum-cost
   assignment as candidate proposal A1. Use the existing seeded
   perturb-and-MAP sampling to obtain up to K=5 distinct
   locally feasible (maximum-cardinality) proposals.
   Candidate proposals are sorted by their ORIGINAL cost,
   then by assigned pairs; these are NOT the provably exact
   global K-best assignments. If fewer than 5 distinct
   proposals exist, use the actual lower count, not imaginary
   candidates.
3. Rank proposals by that local cost, assign weight

       w_k = 1 / k^2, k = 1,2,...,K<=5.

   For five proposals:
       weights = 1, .25, .111111, .0625, .04
       probability of proposal 1 = 68.32%.
   This ratio gives rank 1 four times rank 2, nine
   times rank 3. Squaring the unnormalized **ordinal
   rank itself** would reward WORSE options; therefore
   inverse-square ranks are used intentionally.
4. For each task t, compute support over the robot IDs
   assigned to t by each candidate proposal:

       S(r,t) = SUM over k for which A_k(t)=r of 1/k^2.

   Normalize S(r,t) across locally visible robot IDs.
   Epsilon=0 means NO unrelated cost-softmax exploration
   when at least one proposal contains task t.
   If no feasible proposal covers task t (common under
   missing Cost rows when visible robots < tasks),
   fall back ONLY to that voter's VISIBLE COST row
   local Cost-Softmax, never any hidden Cost row.
5. Divide the fixed 10 task tickets among visible
   candidates using deterministic Hamilton (largest
   remainder) apportionment:
       quota(r,t) = 10 * S(r,t) / SUM S(*,t);
       n_r = FLOOR(quota(r,t));
       allocate remaining tickets by descending
       fractional remainder, ties broken by smaller robot ID.
   Exactly 10 per task: sum_r n_r(t)=10. In the
   illustrative case five proposals choose five
   distinct executors for a task, the allocation is
       (7,2,1,0,0) for ranks 1..5.
   This avoids additional RANDOM TICKET sampling noise
   while preserving the original P2KV frame and
   each robot's self-contained local vote ownership.
   A local preference rank is NOT a global execution right.

## Locally received execution hypothesis, offline-only diagnosis

After a single native physical Cost/Vote epoch:
- EACH receiver decodes only its actually received P2KV
  packets and builds a task-by-robot positive integer ticket
  matrix. Its own packet always counts locally when timely.
- EACH receiver runs the exact original P2K
  resolve_p2k_local_assignment: positive-only,
  maximum-cardinality, maximize summed actually
  received votes, deterministic ID tie break. This
  makes its OWN matching one-to-one.
- EACH ROBOT considers ONLY the task assigned to ITSELF
  in ITS OWN receiver's matching to be its intended
  executed task. No other party sees/repairs this plan.
- An OFFLINE experimental observer measures per task
  how many robots independently claim it (exactly 1,
  >1 duplicated, 0 missing). This observer is never
  involved in producing votes or assignment decisions.
- A separately recorded per receiver/task TOP-VOTE TIE
  is when two or more candidate robots share the
  HIGHEST STRICTLY POSITIVE received ticket count.
  Per receiver/task zero-positive-support is recorded
  separately and NOT classified as a tie.
  "Tie fraction" denominator is ONLY receiver/tasks
  where positive vote support exists. Mean gap between
  top two counts is a separate independent statistic.
  These per-task ties are NOT the same as matching
  objective ties or cross-robot execution collisions.
- Full allocation cost and cost gap relative to
  original full-info Global Greedy are reported ONLY
  if ALL tasks have exactly one true self-executor.
  Partial sum is distinct and never interpreted as
  a fully valid allocation cost.

For incomplete results, new observer records nonfatal
structured safety/P2Q_LOCAL_EXECUTIONS_NOT_ONE_TO_ONE
(owner experiments.run_p2q_rank_square_voting,
 function analyze_p2q_vote_consensus, expected tasks
 and actual duplicate/missing/unique percentage).
This is a result of the tested hypothesis, NOT a
synthetic protocol error to be magically repaired.

## One named function/diagnostic boundary

Owner module democracy_mrta.optimizer:
- compute_p2q_rank_squared_proposal_weights:
  contract/P2Q_INVALID_RANKED_PROPOSALS checks finite,
  nonempty, sorted original-cost feasible proposal ranks,
  returns weights 1/k^2 (no networking).
- apportion_p2q_task_tickets:
  data/P2Q_INVALID_TASK_WEIGHTS, contract/
  P2Q_INVALID_REMAINDER_BUDGET and
  P2Q_APPORTIONMENT_COUNT_MISMATCH check exact
  fixed per-task discrete integer allocation and
  visible recipient IDs, deterministic tie break.
- sample_p2k_task_balanced_votes: the EXISTING true
  voter owner adds opt-in optimized_rank_square policy.
  It keeps SAME locally visible Hungarian and seeded
  perturb-and-MAP proposals. Existing cost_softmax
  and optimized_kbest policies are unchanged.

Original physical owner democracy_mrta.coordination:
- validate_p2k_local_scope accepts the new opt-in
  policy string; original Cost+P2KV physical sender,
  recipient-level Bernoulli loss and receiver-local
  resolve_p2k_local_assignment are unchanged.
- No change to existing P2M/P2N/P2O owner/GRANT paths.

New observational experiment
experiments.run_p2q_rank_square_voting:
- validate_p2q_axes: data/P2Q_INVALID_RANK_SQUARE_SCOPE.
- analyze_p2q_vote_consensus:
  contract/P2Q_INVALID_AUDIT_VIEW,
  data/P2Q_NEGATIVE_OR_NONINTEGER_RECEIVED_VOTE,
  contract/P2Q_INCONSISTENT_TIE_DENOMINATOR;
  nonfatal safety/P2Q_LOCAL_EXECUTIONS_NOT_ONE_TO_ONE.
- run_p2q:
  state/P2Q_OUTPUT_ALREADY_EXISTS,
  contract/P2Q_SOURCE_AUDIT_MISSING,
  contract/P2Q_RAW_SCHEMA_OR_POLICY_MISMATCH.
- summarize_p2q_rows and save_p2q_evidence own
  append-only new-method-only results and hashes;
  each (loss,seed) runs exactly ONE real native
  optimized_rank_square Cost/Vote experiment via
  the original run_one_p2k_case source. Its
  receiver-local audit is analyzed OFFLINE
  without a rerun or second legacy method arm.

All diagnostic categories are ONLY
data/time/state/dependency/planning/safety/runtime/
contract and record first failing owner/function/code,
expected/actual/details where relevant.

## Mac exact runbook: ONLY P2Q (NO old arms)

From project root:

    git fetch origin
    git switch --track origin/experiment/p2q-optimized-rank-square-votes
    git pull --ff-only
    git rev-parse --short HEAD

If branch exists locally:
    git switch experiment/p2q-optimized-rank-square-votes
    git pull --ff-only

Compile and P2Q-only targeted unit tests:

    python3 -m compileall -q democracy_mrta experiments tests
    python3 -m unittest discover -s tests -p 'test_p2q*.py' -v

Two-seed smoke, PL 0/30/90, 6 P2Q-only cases:

    P2Q_SMOKE="results/p2q_smoke_$(date +%Y%m%d_%H%M%S)"
    python3 -m experiments.run_p2q_rank_square_voting \
      --losses 0.00,0.30,0.90 --votes 1000 \
      --seeds 2 --k 5 --epsilon 0 \
      --output-root "$P2Q_SMOKE"

Formal preliminary 10 seeds (4 losses x10=40 P2Q-only):

    set -o pipefail
    P2Q_RUN="results/p2q_10seed_$(date +%Y%m%d_%H%M%S)"
    python3 -m experiments.run_p2q_rank_square_voting \
      --losses 0.00,0.30,0.50,0.90 \
      --votes 1000 --seeds 10 \
      --k 5 --epsilon 0 --audit-seeds 1 \
      --output-root "$P2Q_RUN" 2>&1 | tee "$P2Q_RUN.log"

Pack all actual raw/summary and native receipt audit:

    test -f "$P2Q_RUN/manifest_p2q.json" && \
    zip -j "$HOME/Downloads/p2q_rank_square_10seed.zip" \
      "$P2Q_RUN/per_seed_p2q.csv" \
      "$P2Q_RUN/summary_p2q.csv" \
      "$P2Q_RUN/audit_p2q.jsonl" \
      "$P2Q_RUN/run_config_p2q.json" \
      "$P2Q_RUN/manifest_p2q.json" \
      "$P2Q_RUN.log"

No claim of no ties, no collisions, complete allocation,
improved cost, or lower physical communication until
full native test/smoke and uploaded 40-row evidence.
No experiment SHOULD force a 100% completion result
by repairing a duplicate or dropping a conflicting
robot from the final measured execution counts.

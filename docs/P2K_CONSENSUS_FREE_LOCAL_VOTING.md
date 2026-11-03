# P2K: Consensus-Free Local Voting Experiment

Branch: experiment/p2k-consensus-free-local-voting
Study ID: P2K_CONSENSUS_FREE_LOCAL_OPTIMIZATION

## Research question

Can 100 robots independently infer highly similar one-to-one assignments from
different lossy Vote deliveries, without any reliable PSCR Score, Commit,
global Vote matrix, retransmission or repair? This is a hypothesis: a high
match of received proportions does not mathematically imply an identical
capacity-one matching.

## Compared policies

- cost_softmax: baseline per-task softmax over only received robot Cost rows.
- optimized_kbest: optimize up to K=5 distinct candidate assignments over
  received Cost rows, using the exact local minimum-cost Hungarian assignment
  plus seeded perturb-and-MAP alternatives. These are not claimed to be the
  exact K globally best assignments. Local proposal costs (for equally
  maximum-cardinality assignments) are weighted by exp(-(C-Cmin)/(q*tau)),
  q being the local matching size; per-task support is normalized and
  combined with epsilon=0.10 visible-cost softmax exploration. When no
  local proposal supports a task, only locally visible per-task costs
  may provide its fallback vote probability. Missing Cost is never filled.

All voters use task-balanced sampling: each of M tasks has exactly B/M
tickets where B is divisible by M. Both policies share exactly the same
wire representation and same receiver-specific network drop model.

## P2KV wire and coordination contract

- External TASK is model-reliable and sender-paid, as in historical P2J.
  This initial assumption is deliberately retained and disclosed.
- Each robot sends exactly one original Cost broadcast, with per-remote-
  receiver Bernoulli loss; each robot always knows its own Cost row.
- Each voter emits one 16B-header P2KV Vote broadcast, with one uint8
  candidate robot ID per logical ticket. Task ID is implicit from
  ticket index: each task has B/M contiguous ticket slots. At 100 tasks
  and 500 tickets, a packet is 16+500=516 application bytes, one SEND.
  Max tickets 1184 under 1200B MTU. Historical P2J PVOT <=255 stays
  completely unchanged.
- Each recipient receives or drops each Vote broadcast independently.
  Only actual timely delivered and decoded Vote data enters that
  recipient's matrix; its own timely Vote is a local event.
- There is NO PSCR, NO Score, NO Commit, NO ACK-based retransmission,
  NO global fallback, NO global observer correction.
- Every receiver computes a positive-observed-edge maximum-cardinality
  one-to-one matching, then maximizes total received ticket votes and
  applies deterministic robot ID tie resolution.
- Each robot only claims the task assigned to itself in its OWN local
  matching. The union of independent claims can collide or leave tasks
  unassigned. No algorithm stage is allowed to repair these conflicts.
- Cost, Vote and initial TASK attempted sender Bytes count even if
  packets drop. Rady profile plus hypothetical serialized 144Mbps
  shared-medium approximation is used. Solver CPU time is NOT counted
  by the communication timing model.

## Measurement contract

- task coverage: tasks with >=1 claimant divided by tasks
- unique completion: tasks with exactly one claimant divided by tasks
- duplicates: tasks with >=2 claimants
- unassigned: tasks with zero claimants
- full valid: every task has exactly one claimant
- assignment agreement: offline modal local tentative executor share,
  per task, including missing; not a protocol consensus
- vote similarity: offline average per-task similarity of receiver
  normalized ticket distributions; purely descriptive
- cost gap versus full-information Global Greedy: ONLY on fully valid
  claims. Partial claimed cost is separate, possibly double counting
  duplicated tasks.
- Phase sender attempts, application Bytes, receiver drops, modeled
  stop time and per-robot local decisions are retained.
- JSONL per-robot vote view / local assignment audit is stored for
  the first --audit-seeds seeds per cohort, default 1, to avoid huge
  full-formal audit files; all seeds have summary rows and claims.

Formal grid: 100 robots, 100 tasks, capacity=1, votes 100/200/500/1000,
loss 0/30/50/70/90%, seeds 0..99, 2 policies = 4000 original new runs.
Historical P2J V3 remains only a labeled reliable-Score/Commit reference;
it is NOT a matched no-consensus network baseline.

## Owners

- optimizer.sample_p2k_task_balanced_votes: local visible-cost planning
  and task-balanced ticket generation.
- coordination.validate_p2k_local_scope: bounded input contract.
- coordination.encode_p2k_vote_packet / decode_p2k_vote_packet:
  separate one-frame P2KV data contract.
- coordination.collect_p2k_local_vote_views: physical per-recipient
  delivery, cutoff and local ticket counts.
- coordination.resolve_p2k_local_assignment: receiver-only matching,
  no unseen Vote edges.
- coordination.simulate_p2k_local_vote_epoch: one original Cost/Vote
  runtime, no Score/Commit calls or new state machine.
- experiments.run_p2k_consensus_free: experimental axes, offline
  metrics and append-only CSV/JSONL/manifest; never modifies claims.

Diagnostics categories: data/time/state/dependency/planning/safety/runtime/
contract. Important errors have owner/function/category/code and, where
relevant, expected/actual/details.

## Mac runbook

From the repository root, update the independent branch:

    git fetch origin
    git switch experiment/p2k-consensus-free-local-voting
    git pull --ff-only origin experiment/p2k-consensus-free-local-voting
    git rev-parse HEAD

Run focused and complete tests:

    python3 -m compileall -q democracy_mrta experiments tests
    python3 -m unittest discover -s tests -p 'test_p2k*.py' -v
    python3 -m unittest discover -s tests -p 'test_p2j*.py' -v
    python3 -m unittest discover -s tests -v

100-robot, 500-ticket, 0/30/90-loss two-seed smoke (12 cases):

    P2K_SMOKE="results/p2k_smoke_$(date +%Y%m%d_%H%M%S)"
    python3 -m experiments.run_p2k_consensus_free \
      --losses 0.00,0.30,0.90 --votes 500 --seeds 2 \
      --output-root "$P2K_SMOKE"

After tests and smoke pass, full formal 4000 cases:

    set -o pipefail
    P2K_FORMAL="results/p2k_formal_$(date +%Y%m%d_%H%M%S)"
    python3 -m experiments.run_p2k_consensus_free \
      --losses 0.00,0.30,0.50,0.70,0.90 \
      --votes 100,200,500,1000 --seeds 100 --audit-seeds 1 \
      --output-root "$P2K_FORMAL" 2>&1 | tee "$P2K_FORMAL.log"
    test -f "$P2K_FORMAL/manifest_p2k.json" && \
    zip -j "$HOME/Downloads/p2k_consensus_free_100seed.zip" \
      "$P2K_FORMAL/per_seed_p2k.csv" \
      "$P2K_FORMAL/summary_p2k.csv" \
      "$P2K_FORMAL/run_config_p2k.json" \
      "$P2K_FORMAL/manifest_p2k.json" "$P2K_FORMAL.log"

Status: GitHub source edits and tests are authored; remote connector
cannot execute Python in this repository. Compilation, focused regression,
smoke and formal run are pending the user's Mac. On first failure report
the first full traceback; do not silently correct the algorithm to hit 100%.


## P2Q opt-in extension (2026-11-03): optimized rank-square votes

This original P2K document defines historical cost_softmax and
optimized_kbest policies and remains their canonical contract. Neither
legacy policy is altered or re-run by the P2Q-only experiment.
P2Q registers ONE NEW opt-in
sample_p2k_task_balanced_votes(policy="optimized_rank_square")
in the existing owner module democracy_mrta.optimizer.
The existing locally visible Hungarian + seeded perturb-and-MAP
proposals are reused, sorted by original local assignment cost,
then weighted as w(rank)=1/rank^2 (rank1=1; rank2=0.25;
rank3=1/9), instead of optimized_kbest's exponential
cost-gap weighting. When a proposal covers a task, proposals'
weighted robot votes are aggregated with epsilon=0 exploration;
a task uncovered by all visible proposals falls back
ONLY to visible local cost softmax. The fixed 10 integer
tickets per 100 tasks are apportioned by deterministic
largest remainder, avoiding independent random ticket draws
while preserving the original 1016B P2KV wire and independent
per-receiver Cost/Vote packet loss. No hidden Cost rows are used.
P2Q's separate experiment does NOT add CLAIM/ACK/GRANT,
EXECUTING, reliable Score/Commit or any repair.

Raising rank separation might lower local vote-score ties,
but cannot imply common winner across different lossy
receiver-local matrices. All duplicate/missing task
self-executions are reported as real failed full allocations,
even if every receiver's own top-vote count has no tie.
Detailed P2Q canonical contract, diagnostics and Mac
runbook: docs/P2Q_OPTIMIZED_RANK_SQUARED_VOTING.md.

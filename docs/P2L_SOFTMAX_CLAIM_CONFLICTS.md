# P2L: Hsien-Te 1000-Vote Softmax + Conflict-Only CLAIM

**Experimental branch:** experiment/p2l-softmax-claim-conflicts
**Study:** P2L_1000_SOFTMAX_CONFLICT_ONLY_PAIRED
**Status:** GitHub source implemented, targeted test code authored; local Python
compilation, unit tests, smoke and 10-seed results MUST be verified on Mac.

## Research question and fair comparison

Does a 1000-ticket original per-task Cost Softmax, followed by a short
task-ownership CLAIM only where conflicts require resolution, improve
unique task completion and full valid allocation under Cost/Vote loss?

For each scene/loss/seed, the SAME physically generated Cost and P2KV Vote
events and the SAME receiver-local P2K tentative assignments are shared by
three *counterfactual* experimental arms:

1. local_only: original P2K receiver-local self-claim, no extra traffic.
2. bounded_ack: first CLAIM from all robots, then CLAIM only from
   unresolved/losing robots. Every CLAIM is a physical lossy broadcast;
   each successful remote receipt triggers a 16-byte physical ACK
   unicast, which may also drop. Sender retransmits original CLAIM
   (up to predeclared max attempts) until ALL peers ACK; every attempted
   broadcast and ACK counts toward sender Bytes, event timing and loss.
   If any expected CLAIm cannot be certified, no robot is authorized to
   execute and the arm returns 0 safe executions (fail closed). This
   makes high-loss confirmation failures visible instead of silently
   repairing them with model truth.
3. ideal_paid: *optimistic sensitivity control*, with one sender-paid
   CLAIM guaranteed to reach all others without ACK/retry. This has
   the same idealized-reliable-control limitation previously discussed
   for PSCR; it must NOT be represented as performance at the same
   physical CLAIM loss model or as a real radio guarantee.

The third arm isolates whether the ownership arbitration itself can fill
gaps, without hiding the very different realistic confirmation cost.
The first two arms are the primary physical-loss comparison. Every
result must visibly identify its channel and SEND breakdown.

## Cost, Vote and task-balance contract

- One physically sender-paid model-reliable TASK dissemination, matching
  historical P2K/P2J assumptions. It is not a no-reliable-communication claim.
- One physical lossy Cost broadcast per robot: each voter sees its own Cost
  row and only physically delivered/timely remote Cost rows.
- Each voter uses the original P2K cost_softmax policy, temperature=5.0:
  P_v(R_i|T_j) proportional to exp(-(Cost[i,j]-visible_min)/tau).
- Exactly 1000 task-balanced logical votes: when 100 tasks, 10
  samples per task per voter; ONE P2KV physical Vote broadcast per
  robot, 16-byte header plus 1000 one-byte candidate IDs = 1016 Bytes.
- Cost and Vote have identical per-recipient Bernoulli p_loss.
  All original sends are counted even if recipients drop.
- Every robot independently computes positive-supported maximum-cardinality
  one-to-one matching from only its receiver-local votes, then claims
  ONLY its own inferred task (or an idle sentinel).
- No PSCR, no full Score matrix, no reliable executor Commit, no hidden
  global cost repair. The full-cost reference exists OFFLINE only.
- CPU time for optimization and claim conflict processing is excluded
  from modeled communication time, same as older experiments.

## Conflict-only message and decision

P2LC CLAIM is one 28-byte struct:
    uint8[4] tag = P2LC
    uint32 claim_round
    uint32 sender_robot_id
    uint32 proposed_task_id (0xffffffff = idle)
    uint32 support_votes_for_sender_on_task
    uint32 received_vote_batch_count_at_sender
    uint32 tickets_per_task

P2AK ACK is 16 bytes:
    uint8[4] tag = P2AK
    uint32 claim_round
    uint32 ack_sender_id
    uint32 original_claimant_id

The claim's support numerator and valid ballot denominator are computed
exclusively from the sender robot's own receiver-local Vote view.
No candidate can publish or inspect another robot's private view.

For two candidates a and b claiming task t, use:

    S_a(t) = V^(a)[a,t] / (10 * N_a)
    S_b(t) = V^(b)[b,t] / (10 * N_b)

where N is the number of *actually received valid original Vote packets*
(including own timely original) as counted at that candidate. Comparisons
use exact rational arithmetic; ties use own raw votes, number of received
packets and smaller robot ID. Comparing raw received Vote totals across
unequal N is NOT permitted.

Initially every robot announces one CLAIM (including idle). After
successful per-round CLAIM confirmation and public conflict sorting,
each task with >=1 contender has exactly one publicly determined winner.
Only losing/idle robots participate in the next round; all already
confirmed tasks stay locked. A losing robot selects an unclaimed task
using its own local Vote support for itself, then its own known task
Cost and ascending task ID. Only the new CLAIM is sent; no Cost/Vote
is retransmitted, and no global rescoring of every pair occurs.

There is a bounded number of CLAIM rounds; if a broadcast/ACK attempt
budget exhausts or a round limit leaves tasks unresolved, the arm
fails closed with an explicit diagnostic and records zero safe actual
executions. All failed SENDs are charged. This choice avoids reporting
unsafe guessed ownership as successful execution. The protocol assumes
a synchronous CLAIM-round barrier and a pre-known robot roster; it is NOT
a proven fault-tolerant asynchronous consensus protocol. Conflicting
CLAIMs do constitute a restricted coordination/ownership agreement,
so P2L is **not** literally "consensus-free"; it eliminates full PSCR
Score synchronization, not all communication required for uniqueness.

## Audit, safety and source constraints

The algorithm may access only (a) its original P2K own receiver-view
vote row, (b) its own original task Cost row when reselecting, (c)
authenticated-in-model public CLAIM payloads, and (d) the public task/
robot roster. The global simulator may inspect all views only in the
OFFLINE experiment metrics. Uncertified CLAIMs never become assignments.

Per-seed metrics:
- preclaim unique/duplicate/unassigned;
- actual unique/duplicate/unassigned/coverage and full-valid after CLAIM;
- initial receiver-local matching agreement and CORRECTED vote-view
  total-variation similarity (P2K's older double-task-divided similarity
  number is NOT reused);
- claim conflict rounds and number of additional reassignment CLAIMs;
- individually counted original TASK, Cost, Vote and extra CLAIM, ACK
  sender application Bytes and SENDs, dropped remote receivers, modeled
  elapsed time;
- full-information Global Greedy cost gap ONLY if actual final execution
  is fully valid; partial/conflicted/confirmation-failed cost gap blank;
- success/failure diagnostic owner/function/category/code, source Git SHA,
  scene hash, raw per-seed CSV, summary, first-audit-seed JSONL and manifest.

Diagnostic examples:
- claim_resolution.validate_p2l_claim_scope / contract /
  P2L_INVALID_CLAIM_SCOPE
- claim_resolution.encode_p2l_claim_packet / data /
  P2L_INVALID_CLAIM_FIELDS
- claim_resolution.decode_p2l_claim_packet / contract /
  P2L_RECEIVED_CLAIM_INVALID
- claim_resolution.make_p2l_claim / contract /
  P2L_LOCAL_BALLOT_TOTAL_INVALID
- claim_resolution.transmit_p2l_claim_with_receipts / time /
  P2L_CLAIM_ACK_BUDGET_EXHAUSTED
- claim_resolution.resolve_p2l_claim_conflicts / safety /
  P2L_RECLAIMED_LOCKED_TASK
- claim_resolution.coordinate_p2l_claims / planning /
  P2L_UNRESOLVED_TASKS_AFTER_ROUNDS
- experiments.run_p2l_claim_conflicts.run_p2l_paired_seed /
  contract / P2L_SOURCE_NETWORK_LEDGER_MISMATCH

All errors retain owner/function/category/code and, when relevant,
expected/actual/details, using only data/time/state/dependency/planning/
safety/runtime/contract. Original P2K, P2J and published Figure1/2
remain untouched.

## Mac: update, verify, smoke and 10-seed experiment

From the repository root:

    git fetch origin
    git switch --track origin/experiment/p2l-softmax-claim-conflicts
    git pull --ff-only origin experiment/p2l-softmax-claim-conflicts
    git rev-parse HEAD

If that local branch already exists, replace "git switch --track" with:
    git switch experiment/p2l-softmax-claim-conflicts

Run tests before experiments:

    python3 -m compileall -q democracy_mrta experiments tests
    python3 -m unittest discover -s tests -p 'test_p2l*.py' -v
    python3 -m unittest discover -s tests -p 'test_p2k*.py' -v
    python3 -m unittest discover -s tests -v

SMOKE: 100 robots /100 tasks, 1000 tickets, 0%,30%,90% loss,
2 seeds x 3 arms x 3 loss groups = 18 records:

    P2L_SMOKE="results/p2l_smoke_$(date +%Y%m%d_%H%M%S)"
    python3 -m experiments.run_p2l_claim_conflicts \
      --losses 0.00,0.30,0.90 --votes 1000 --seeds 2 \
      --max-claim-attempts 24 \
      --output-root "$P2L_SMOKE"

After smoke passes, the requested 10-seed preliminary study:

    set -o pipefail
    P2L_ROOT="results/p2l_10seed_$(date +%Y%m%d_%H%M%S)"
    python3 -m experiments.run_p2l_claim_conflicts \
      --losses 0.00,0.30,0.50,0.90 --votes 1000 --seeds 10 \
      --channels bounded_ack,ideal_paid \
      --max-claim-attempts 24 --max-claim-rounds 101 \
      --audit-seeds 1 --output-root "$P2L_ROOT" \
      2>&1 | tee "$P2L_ROOT.log"

Expected source records: 4 losses x 10 seeds x 3 arms = 120 rows,
12 summary groups. Actual completion rates are UNVERIFIED and may
be low at high loss under honest bounded ACK.

When finished:

    test -f "$P2L_ROOT/manifest_p2l.json" && \
    zip -j "$HOME/Downloads/p2l_claim_conflicts_10seed.zip" \
      "$P2L_ROOT/per_seed_p2l.csv" \
      "$P2L_ROOT/summary_p2l.csv" \
      "$P2L_ROOT/run_config_p2l.json" \
      "$P2L_ROOT/manifest_p2l.json" \
      "$P2L_ROOT.log"

Keep audit_p2l.jsonl and the output directory locally; send the ZIP
and the first traceback on any failure. A successful GitHub source push
does not imply verified runtime tests or physics-realistic RF correctness.

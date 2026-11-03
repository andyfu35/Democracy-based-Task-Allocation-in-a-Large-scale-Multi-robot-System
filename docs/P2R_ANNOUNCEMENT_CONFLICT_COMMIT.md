# P2R — Announcement-Driven Conflict Resolution with Safe COMMIT

Branch: experiment/p2r-intent-conflict-commit
Study: P2R_RANK_SQUARED_VOTE_INTENT_CONFLICT_ONLY_COMMIT
Status: GitHub source/test prepared; native Python test + smoke/formal data
must be run on the local Mac before claiming successful implementation.

## Why this method

After P2Q optimize-first, rank-squared 1000-ticket vote results,
30% Cost/Vote PL gave only 79.5% of tasks with exactly one private
self-selected robot, 9.4 duplicate tasks and 11.1 empty tasks per
10-seed average. It also showed that per-receiver equal maximum
ticket counts were rare (~0.16% at PL30): local single-top-score
tie reduction alone does not make DISTINCT receiver-local Hungarian
matching matrices identical. This user-requested NEXT concern
therefore does NOT change Softmax, K=5 optimization or voting
weights. It adds ANNOUNCEMENT-DRIVEN conflict/repair communication
only, in the ORIGINAL task ownership owner module.

User request: each potential executor announces it intends to
perform a task, other potential executors who hear a conflict
raise an objection, conflicts are resolved like a small auction;
robots who lose select another task; protect one robot per task
and one task per robot WITHOUT a repeated costly CLAIM/ACK/GRANT/ACK
handshake for every candidate.

## Original P2Q source (fully preserved)

100 robots, 100 tasks, capacity=1, votes_per_voter=1000, each
task receives 10 uint8 tickets in one 1016B P2KV physical
broadcast per robot. One Cost row physical broadcast per
robot. A paid TASK bootstrap is still model-reliable as
in previous work. Each voter locally sees ONLY its own
physical Cost receipts; computes original visible-cost
Hungarian minimum and up to K=5 distinct seeded
perturb-and-MAP candidates, sorted by original local
cost, and assigns rank weights 1/k^2; epsilon=0;
apportion integer tickets by deterministic largest
remainder (fallback ONLY to visible Cost if no proposal
covers a task). All P2Q generation, original Cost/Vote
per-receiver independent loss, private matching and
P2KV bytes are unchanged. The original global simulator
can read full costs ONLY for OFFLINE diagnostics, never
for actual owner decisions.

P2R uses the ORIGINAL P2Q own (receiver-local) matching:
each robot initially nominates only the task assigned
to ITSELF, never its entire 100-task assignment matrix.
An unmatched robot chooses an available candidate
using only its own originally received self-support
and its original Cost row via the EXISTING
select_p2m_local_request_task planner.

## New on-wire packet contract

Everything below counts every actual physical SEND
even if dropped by one or all recipients. All messages
have physical sender/receiver Bernoulli loss, except
self-local knowledge requiring no radio.

- P2RI INTENT: 28B broadcast, tag P2RI, uint32 round,
  robot ID, task ID, locally received self-support
  ticket count, valid ballots received and per-task
  ticket count. It reuses the validated P2LClaim
  support fields as a *local payload container*, but
  it is **NOT a P2LC CLAIM** or another ballot send.
  Each pending robot broadcasts exactly three P2RI
  physical copies per owner round by default; each
  recipient observes only actually delivered copies,
  and deduplicates by (task,robot). No ACK phase.
- P2RH CHALLENGE: 16B unicast, tag P2RH, round,
  challenger, task. Emitted once per owner round
  ONLY by an ACTUAL contestant that personally
  received at least one other P2RI for the SAME
  task. Every other passive bystander is silent,
  greatly reducing conflict-alert broadcasts.
  A CHALLENGE is only an observation: it is NOT
  authorization, a signed ballot, or proof of
  a competitor which the fixed task owner did
  not directly receive. If the owner has only
  one direct candidate yet a delivered real
  CHALLENGE, it defers assignment ONE round to
  give another P2RI delivery an opportunity,
  then proceeds on subsequent rounds from its
  genuinely received candidates. It does NOT
  create a false claimant from someone else's
  unverified allegation.
- P2RC COMMIT: 20B task-owner-to-winner unicast,
  format 4sIIII: tag P2RC, owner round, recipient
  robot, task, flag=1. Task owner is
  fixed owner(t)=t % num_robots, from public TASK
  IDs; no election/global score. Only that
  owner's physically delivered P2RC (or its
  own self-local owner action) authorizes an
  executor. Default three physical copies,
  WITHOUT an extra ACK; if all copies drop,
  the owner keeps its IRREVOCABLE reservation
  and the intended robot MUST NOT execute.
  When a still-pending robot re-announces the
  SAME INTENT, the owner resends the SAME COMMIT
  without reallocating. If holder self=owner,
  local commit is free but the original P2RI
  broadcast still counted.
- P2RD DENY: 20B task-owner-to-loser unicast,
  format tag P2RD, original four uint32 fields
  and flag=0. Only sent to physically observed
  contestants who LOST a task's competition
  or applied to a task already reserved by
  its one owner. Default three physical copies,
  NO ACK. Actual receipt tells THIS robot to
  exclude that task and choose its next
  local candidate. NO global denied-state oracle.
- Existing P2NX EXECUTING: unchanged 20B format,
  three physical broadcasts by a robot ONLY
  after it actually received P2RC (or as its
  task's own authorized owner). Remote receivers
  update ONLY their own personally delivered
  known-executing task set. A missing P2NX is
  NOT proof a task is free.

## Single task-owner arbitration and conflict lifecycle

One bounded known-roster owner round (0..100 by default):

1. Every pending robot either holds its SAME
   unresolved P2RI target or, if it actually
   received a P2RD/P2NX for that task, retargets
   using ONLY private Vote self-support and
   own Cost. A robot may never independently
   switch away from an unresolved intent just
   because an answer has not arrived: the owner
   may already have secretly locked it, so a
   new target could create two reservations
   for one robot.
2. All selected robots release three P2RI
   announcements at the same round start.
   Original WifiCausalTimingSampler queues
   actual physical SENDs on ONE serialized
   hypothetical 144Mbps radio. Waiting time
   between other independent senders overlaps.
   All receiver observations are per-recipient
   physical Bernoulli loss; local self-receipt
   never invokes a free imaginary radio packet.
3. Actual contestants who PERSONALLY saw another
   candidate announce the same task unicast a
   16B P2RH CHALLENGE to that task's fixed owner.
   A task owner may also notice its own competing
   local intent directly. Bystanders do not send
   conflict challenges and cannot authorize tasks.
4. Only each task's ONE fixed safety owner
   considers directly received distinct P2RI
   contenders for that task. If a warning
   arrives and it saw only one contender,
   it may defer once. Otherwise if not
   previously reserved it chooses one winner
   using the ORIGINAL normalized
   ticket support and deterministic tie break:

       S(r,t) = V^(r)[r,t] / (10 * N_r).

   Ranks are compared using exact rational
   values; on tie compare raw votes, received
   ballot count and smaller robot ID. No full
   unseen Score or Cost matrix can affect winner.
   Once winner chosen, its task is IRREVOCABLY
   reserved before any COMMIT SEND; even all
   physically lost COMMIT copies may not
   transfer that task to another robot.
5. The owner replies P2RC to winner and P2RD
   ONLY to physically observed losing competitors.
   A task with one direct and no challenged
   candidate needs no expensive negotiation
   or DENY: just a minimal safe COMMIT.
   Each independently originated P2RI is
   considered in the correct own task-owner.
   No P2LC CLAIM, P2AK ACK, P2MD GRANT, P2MA ACK,
   PSCR score, full global reconciliation or
   secondary owner machine is used.
6. Physically committed robot retires from
   future INTENTs and issues its original
   three P2NX EXECUTING SENDs. Only physically
   delivered P2NX updates remote private task
   exclusion. Physically denied robots choose
   an alternative task next round; others
   repeat their SAME P2RI because unreceived
   response does not prove anything.
   A robot can hold at most one active intent
   at a time, avoiding double remote
   reservations for two tasks.
7. Stop at full actual authorization, no
   selectable INTENT left, or 101 owner rounds.
   No model-side hidden repair, automatic
   100% success, or guessed ACK receipt.
   Report reserved-but-unexecuted tasks
   separately from tasks with no actual
   owner-received candidate.

This is not a fully asynchronous crash-tolerant
consensus theorem. All contenders in a round
use an explicit shared request/response barrier,
under an assumed known stable robot/task roster.
The first owner may lock a task before a later
contender's INTENT survives losses. A later
P2RH challenge cannot override an already
irrevocably committed task. Hence no global
optimality or fair auction guarantee is
claimed. The scheme prioritizes safety over
unbounded eventual completion.

## Diagnostic boundaries and one true owner

The true owner stays democracy_mrta.claim_resolution:
- validate_p2r_announcement_scope:
  contract/P2R_INVALID_ANNOUNCEMENT_SCOPE;
  data/identity/phase capacity check.
- encode_p2r_intent / decode_p2r_intent:
  use original validated P2LClaim struct but
  distinct physical P2RI tag;
  data/P2R_INVALID_INTENT_PACKET,
  contract/P2R_WRONG_INTENT_TAG;
  original P2L claim field diagnostics retained.
- encode_p2r_challenge / decode_p2r_challenge:
  data/P2R_INVALID_CHALLENGE,
  contract/P2R_CHALLENGE_IDENTITY_MISMATCH.
- encode_p2r_owner_response /
  decode_p2r_owner_response:
  reuse original 20B P2MD field/schema and
  fixed owner validation, but different
  P2RC/P2RD tag and no ACK message;
  data/P2R_INVALID_RESPONSE_PACKET,
  contract/P2R_INVALID_RESPONSE_TAG,
  safety/P2R_NOT_FIXED_OWNER,
  contract/P2R_RESPONSE_FLAG_MISMATCH.
- transmit_p2r_intent_window:
  physical original broadcast and recipient
  receipts for per-task owner and local
  contestant, NO global dissemination.
- transmit_p2r_conflict_challenges:
  only physically triggered contestant
  P2RH, advisory owner warning.
- choose_p2r_owner_responses:
  owner-local vote/owner state, no duplicate
  sent intent, contract/P2R_DUPLICATE_OWNER_INTENT
  and P2R_INVALID_OWNER_WINNER; original
  resolve_p2l_claim_conflicts is reused
  for normalized vote ranking.
- transmit_p2r_owner_responses:
  owner physically sends P2RC/P2RD, checks
  real delivery, safety/
  P2R_CONFLICTING_OWNER_DECISIONS.
- transmit_p2r_execution_announcements:
  original P2NX physical sender/receiver
  local evidence only after true COMMIT.
- select_p2r_local_intent_task:
  existing own P2Q vote-support planner;
  one unresolved active task at a time.
- validate_p2r_unique_execution:
  safety/P2R_UNAUTHORISED_EXECUTION;
  executed/reserved must be injective
  and actual executions subset of
  irreversible owner reservations.
- coordinate_p2r_announced_intents:
  the ONE new announcement lifecycle
  in the existing task-ownership owner
  module (not copied P2M CLAIM handshake),
  state/P2R_STALE_DECISION_FOR_DIFFERENT_TASK,
  safety/P2R_COMMIT_NOT_RESERVED, and
  truthful first nonfatal
  time/P2R_COMMIT_NOT_DELIVERED or
  planning/P2R_INCOMPLETE_AFTER_ROUNDS
  with actual still-unexecuted task IDs.

Only the experiment source
experiments.run_p2r_intent_conflict_commit:
- validate_p2r_axes validates fixed
  B1000,K5,epsilon0, 1..5 repeat
  and 1..255 rounds;
  data/P2R_INVALID_STUDY_AXIS.
- run_one_p2r_case executes the original
  paid TASK + one original P2Q Cost/Vote
  epoch and then the true P2R owner
  ONCE per new (loss,seed); no older method
  or extra P2Q comparison arms.
- validate_p2r_execution_evidence is
  pure offline safety/receiver-local
  P2NX audit: safety/
  P2R_INVALID_EXECUTION_EVIDENCE;
  contract/P2R_PHANTOM_EXECUTION_NOTICE.
- make_p2r_evidence_row verifies original
  source and P2R actual sender ledger;
  contract/P2R_NATIVE_PHASE_MISMATCH and
  P2R_ACTUAL_SEND_LEDGER_MISMATCH.
- summarize_p2r_rows/save_p2r_evidence
  write new-only per-seed/summary/audit/
  run_config + SHA256 manifest.
  Costs and full-info Greedy gap are
  available ONLY on genuine full
  100/100 unique executable assignments.
- run_p2r fails state/
  P2R_OUTPUT_ALREADY_EXISTS, contract/
  P2R_OUTPUT_SCHEMA_MISMATCH on invalid
  data; it never fills missing tasks
  with an offline full-information solver.

All diagnostics retain owner/function/category/code,
with expected/actual/details where useful, and
categories are exclusively data/time/state/
dependency/planning/safety/runtime/contract.

## Experimental comparison and model caveats

Preliminary only P2R: 100R100T, 1000-ticket
rank-squared optimized Cost/Vote, one
true Cost and Vote epoch, PL0/30/50/90%
10 seeds each = 40 P2R rows. Defaults
3x P2RI, 1x conditional P2RH per observing
contestant and owner-round, 3x P2RC/P2RD,
3x P2NX after actual COMMIT, max 101
bounded owner rounds. Historical P2Q,
P2O, Proposed Multi-Round/CBAA/CBBA
data may be compared AS LABELED HISTORICAL
EVIDENCE; they are NOT re-executed
and different reliable-control/CPU
time assumptions remain explicit.

- P2Q 30% historical unique 79.5%,
  duplicate tasks 9.4 and missing 11.1;
  P2Q no safe COMMIT.
- P2O 30% historical native full
  allocation 10/10, send 215.35kB,
  modeled time 7.44s, based on the
  different Cost Softmax and P2M
  request+ACK transport. No claim
  that P2R is superior before running.
- Per phase attempted SENDs/Bytes,
  physical receiver drops, owner-visible
  conflicts vs peer challenges vs
  deferred warning, actual DENY,
  retargeting, executed/reserved,
  unique coverage, full-valid-only cost,
  first diagnostic and true native
  modeled stop must be retained.
- P2R shared PHY is the original
  Rady-trace proxy with hypothesized
  144Mbps one-medium serialization.
  It is not ns-3, OFDMA, real collisions,
  correlated fading, real-world deadline
  or measured application execution.
  CPU Hungarian optimizer time is NOT
  included. Lost COMMIT may leave task
  permanently reserved and unexecuted.
  Absence of a CHALLENGE does not certify
  absence of real conflict; it only
  means the local sender failed to
  observe one (or message was lost).

## Mac runbook — ONLY P2R, no old arms

At repository root, fresh branch:

    git fetch origin
    git switch --track origin/experiment/p2r-intent-conflict-commit
    git pull --ff-only
    git rev-parse --short HEAD

If the branch already exists locally:

    git switch experiment/p2r-intent-conflict-commit
    git pull --ff-only

Targeted compile/tests:

    python3 -m compileall -q democracy_mrta experiments tests
    python3 -m unittest discover -s tests -p 'test_p2r*.py' -v

Six P2R-only smoke cases, 0/30/90% x2 Seeds:

    P2R_SMOKE="results/p2r_smoke_$(date +%Y%m%d_%H%M%S)"
    python3 -m experiments.run_p2r_intent_conflict_commit \
      --losses 0.00,0.30,0.90 --votes 1000 \
      --seeds 2 --max-rounds 101 \
      --intent-repetitions 3 \
      --decision-repetitions 3 \
      --announcement-repetitions 3 \
      --output-root "$P2R_SMOKE"

ONLY after focused tests + smoke pass:
10 seeds × 4 losses = 40 new P2R cases:

    set -o pipefail
    P2R_RUN="results/p2r_10seed_$(date +%Y%m%d_%H%M%S)"
    python3 -m experiments.run_p2r_intent_conflict_commit \
      --losses 0.00,0.30,0.50,0.90 \
      --votes 1000 --seeds 10 \
      --max-rounds 101 \
      --intent-repetitions 3 \
      --decision-repetitions 3 \
      --announcement-repetitions 3 \
      --audit-seeds 1 \
      --output-root "$P2R_RUN" 2>&1 | tee "$P2R_RUN.log"

Package full physical evidence:

    test -f "$P2R_RUN/manifest_p2r.json" && \
    zip -j "$HOME/Downloads/p2r_intent_conflict_10seed.zip" \
      "$P2R_RUN/per_seed_p2r.csv" \
      "$P2R_RUN/summary_p2r.csv" \
      "$P2R_RUN/audit_p2r.jsonl" \
      "$P2R_RUN/run_config_p2r.json" \
      "$P2R_RUN/manifest_p2r.json" \
      "$P2R_RUN.log"

No GitHub commit proves the native source imports/tests
or the 40-run experiment pass. On the FIRST failure
send the full traceback including diagnostic owner/
function/category/code. Rework the true owner and
synchronize this canonical + CHANGE_CONTINUITY,
never disguise unsafe or incomplete assignments
as 100% success.

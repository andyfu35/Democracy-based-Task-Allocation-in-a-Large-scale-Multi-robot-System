# P2M: Fixed Task-ID Owner Arbitration (1000-Ticket Softmax Only)

Branch: experiment/p2m-task-owner-arbitration
Study: P2M_1000_SOFTMAX_FIXED_TASK_OWNER_ONLY

## Why duplicate tasks occurred in previous P2L source

In uploaded p2l_claim_conflicts_10seed.zip, the preclaim local-only mode
at 30% Cost/Vote loss, seed0 has 8 duplicate task IDs and 9 unassigned
tasks, although each receiver-local matching is individually one-to-one.
For example, task29 is claimed by R59 and R90; task37 by R27, R68,
and R87. Different robots received distinct lossy full P2KV broadcasts,
and therefore built different V^(robot) and distinct matchings. Each
robot then executed only its OWN row. The union of multiple valid but
nonidentical local matchings is not globally one-to-one.

This is not evidence of duplicated tickets inside a delivered P2KV
packet: one sender emits exactly B=1000 logical tickets in ONE native
1016B P2KV SEND, with task slot implicit (10 tickets per task).
Dropped broadcasts cause missing full blocks of votes, not accidental
double-counting inside one receiver's matrix. The uploaded P2L ZIP
lacks audit_p2l.jsonl, so exact candidate self-support ratios for each
collision cannot be reconstructed independently from that ZIP; the
P2M audit preserves them for the new experiment.

## New protocol: each task has one unique owner

For N robots, public deterministic mapping:

    owner(task_id) = task_id % N.

For 100 robots/100 tasks, owner(T29) is robot R29. This owner alone
can reserve task29; there is no arbitrary all-peer Score announcement.

Only ONE method is run per seed: P2M task_owner. No P2K local_only arm,
no P2L bounded_ack/ideal_paid arm and no P2J V3 arm is executed.
Historical code remains unmodified and reusable as a Cost/Vote source.

1. Paid model-reliable TASK startup source, one original lossy Cost
   row from each robot and one original lossy 1000-ticket P2KV Vote
   from each robot, exactly as in original P2K cost_softmax tau=5.
2. Every robot computes its OWN receiver-local one-to-one matching,
   and proposes the task assigned to itself; if locally unmatched,
   propose the task favored by its OWN self-support tickets and
   own Cost row. It sends ONE 28B P2LC CLAIM to the fixed owner of
   that task as a unicast, NOT as broadcast.
3. Owner acknowledgement of REQUEST: a physical 16B P2AK unicast to
   that same requester. Requester retries its *unchanged* original
   claim until receipt ACK arrives or max_attempts is exhausted.
   The owner considers ANY CLAIM its own receiver actually obtained,
   regardless of whether its outgoing ACK reached the claimant.
   A missing receipt ACK causes unchanged request retries; even
   after exhausting those ACK retries the owner may still evaluate
   its real received CLAIM and send a GRANT or DENY. The claimant
   cannot switch tasks or execute until that OWNER decision actually
   reaches it. If no REQUEST reached the owner at all, the
   claimant remains BLOCKED (no hidden acknowledgement).
4. One owner independently compares only its OWN physically confirmed
   pending CLAIMs, by exact rational score:

       S(r,t) = own_received_votes(r,t) / (10 * N_received(r))

   Tie order: higher raw support, more received ballots, smaller
   robot ID. The owner irrevocably reserves its task to ONE
   winner BEFORE attempting any GRANT. No other owner controls
   that task. Previously reserved tasks reject later proposals.
5. Owner sends 20B P2MD GRANT or DENY *only* to its actual bidders,
   using bounded lossy unicast and 16B P2MA decision ACK. On a
   physically received GRANT the robot may execute; DENY makes
   that robot eligible for a different task in the next claim
   round. The task owner never grants a reserved task twice,
   even if the final ACK is lost.
6. If a candidate receives no decision within retry budget, it
   is BLOCKED. An owner-granted task whose GRANT never reaches its
   recipient remains reserved but *unexecuted*; never silently
   reassigned to another robot. This can cause incomplete
   allocation but cannot create duplicate task execution.
7. On rejection, each robot chooses its next task using only
   its OWN original Vote support row, OWN Cost row and OWN
   previous rejection history. It is NOT given the global
   owner reservation map. Requests to already reserved tasks
   are rejected by their owners; a robot cannot hold two
   grants because it never sends a second request after
   physically receiving a GRANT.
8. Stop at complete execution, exhaustion, or max_rounds=101.
   No retroactive global Cost/Score correction or all-peer ACK
   quorum. Only one task owner and its bidder participate in
   each proposal/ACK/decision/ACK exchange.

Actual transmissions all count SEND application bytes whether delivered
or dropped. The packet types and sizes are:

| Phase | Direction | Application payload |
| --- | --- | --- |
| task_announcement | external -> all | original, paid/model-reliable |
| cost | each robot -> peers | original, independently lossy |
| vote | each robot -> peers | original, independently lossy 1016B |
| owner_request | claimant -> task owner | 28B P2LC |
| owner_request_ack | task owner -> claimant | 16B P2AK |
| owner_decision | task owner -> claimant | 20B P2MD |
| owner_decision_ack | claimant -> task owner | 16B P2MA |

When owner equals claimant, purely local handling incurs no network SEND.
All remote P2M phases use the same independent Bernoulli loss
probability as Cost/Vote. Serial timing is the existing hypothesis-driven
Rady Wi-Fi6 144 Mbps shared-medium approximation, *not* a real RF
or asynchronous Byzantine-tolerant guarantee. CPU optimizer work
and exact radio MAC conditions are not simulated.

## Diagnostic and safety contract

Owner module: democracy_mrta.claim_resolution. Exact new named functions
p2m_task_owner_id, validate_p2m_owner_scope, encode/decode_p2m_owner_decision,
transmit_p2m_owner_request, transmit_p2m_owner_decision,
select_p2m_local_request_task, coordinate_p2m_task_owners.

- P2M_INVALID_OWNER_MAP: data, invalid fixed task owner mapping
- P2M_INVALID_OWNER_SCOPE: contract, P2K source/sizes invalid
- P2M_REQUEST_ACK_LIMIT: time, request receipt ACK not received;
  if owner received the actual CLAIM, subsequent owner response may
  still resolve it (ACK receiver outcome is NOT exposed to owner)
  Successful subsequent GRANT/DENY clears this from terminal allocation
  failure; the event is counted separately as
  request_receipt_ack_timeouts (nonterminal network warning).
- P2M_DECISION_DELIVERY_LIMIT: time, owner decision not delivered
- P2M_UNAUTHORISED_OWNER_DECISION: contract, wrong owner/stale decision
- P2M_TASK_OWNER_NO_UNIQUE_WINNER: contract, invalid owner arbitration
- P2M_ROBOT_DOUBLE_GRANT: safety, robot granted two tasks
- P2M_INVALID_RESERVED_EXECUTION: safety, execution without owner
  reservation/valid phases
- P2M_TASK_OWNER_ALLOCATION_INCOMPLETE: planning, finite rounds exhausted
- P2M_TASK_OWNER_DUPLICATE_EXECUTION: experiment.safety offline
  integrity gate, never an online repair.

All important errors specify owner/function/category/code and expected/
actual/details. When a request/response is not received, diagnostic
identifies the first failed boundary and the robot/task/attempts.
Safe partial execution is retained and measured rather than replacing
the entire allocation with zero or fabricating a completion.
No private whole Vote matrix is published to the task owners.

## Single-method experiment and outputs

Default 100 robots, 100 tasks, capacity 1, Cost+Vote loss
0%, 30%, 50%, 90%, 1000 tickets/robot, 10 seeds, tau5, 24
max attempts per request/decision, max 101 claim rounds.
Only **40 P2M native study cases** (not legacy baselines).

Source and scene SHA, per-seed csv, four-group summary, sender
attempted Bytes/SEND breakdown per phase, receiver drops per phase,
blocked robot count, actual unique/duplicate/unassigned,
preclaim conflict counts as offline source diagnostics,
rounds, real delivered GRANTs, reserved-but-unexecuted pairs,
and first diagnostic are retained. Full execution cost only exists
on complete all-task valid allocation; partial cost is separate.
First --audit-seeds seeds for each loss level additionally retain
original per-robot OWN vote support, number of received Vote batches,
every task-owner's *confirmed* candidate scores/winner, actual
executions and irreversible reservations in audit_p2m.jsonl.

No old method is run in this experiment. It is still legitimate
to inspect initial P2K self-claims from the very SAME original
Vote run as a diagnostic, but there is no separate baseline
experiment or its communications in the results.

## Mac commands

From project root:

    git fetch origin
    git switch --track origin/experiment/p2m-task-owner-arbitration
    git pull --ff-only origin experiment/p2m-task-owner-arbitration
    git rev-parse HEAD

If branch exists, use git switch experiment/p2m-task-owner-arbitration
instead of switch --track.

Focused tests only (no legacy method benchmark runs):

    python3 -m compileall -q democracy_mrta experiments tests
    python3 -m unittest discover -s tests -p 'test_p2m*.py' -v

Smoke: TWO seeds at 0%,30% and 90% packet loss, SIX cases:

    P2M_SMOKE="results/p2m_smoke_$(date +%Y%m%d_%H%M%S)"
    python3 -m experiments.run_p2m_task_owner \
      --losses 0.00,0.30,0.90 --votes 1000 --seeds 2 \
      --output-root "$P2M_SMOKE"

Ten-seed single-method test: 40 cases:

    set -o pipefail
    P2M_RUN="results/p2m_10seed_$(date +%Y%m%d_%H%M%S)"
    python3 -m experiments.run_p2m_task_owner \
      --losses 0.00,0.30,0.50,0.90 \
      --votes 1000 --seeds 10 \
      --max-attempts 24 --max-rounds 101 \
      --audit-seeds 1 --output-root "$P2M_RUN" \
      2>&1 | tee "$P2M_RUN.log"

Pack ALL audit files and logs (including first-collision evidence):

    test -f "$P2M_RUN/manifest_p2m.json" && \
    zip -j "$HOME/Downloads/p2m_task_owner_10seed.zip" \
      "$P2M_RUN/per_seed_p2m.csv" \
      "$P2M_RUN/summary_p2m.csv" \
      "$P2M_RUN/audit_p2m.jsonl" \
      "$P2M_RUN/run_config_p2m.json" \
      "$P2M_RUN/manifest_p2m.json" \
      "$P2M_RUN.log"

IMPORTANT: GitHub source commits are NOT proof of test success.
Run focused test + smoke before 10 seeds; send first traceback
if any failure. Do not interpret model-reliable initial TASK as
a packet-loss-tested claim or claim full asynchronous safety.

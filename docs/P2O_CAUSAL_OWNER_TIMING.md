# P2O — Causal shared-radio owner timing (new method ONLY)

Branch: experiment/p2o-causal-owner-timing
Study: P2O_1000_SOFTMAX_TASK_OWNER_CAUSAL_TIMING_ONLY

## Problem and immutable assignment scope

P2N 100R100T, B=1000, three 20B EXECUTING copies measured
24.91/40.70/75.07/258.44 modeled seconds for PL0/30/50/90%.
The true claim_resolution.coordinate_p2m_task_owners used one
sequential common "clock", assigning the NEXT robot's REQUEST
release after the previous robot's entire end-to-end REQUEST/ACK
exchange, then doing the same for GRANT/DENY and every EXECUTING
copy. That double-serialized not just physical radio service but
also remote endpoint waiting. Long simulated stop times therefore
cannot be interpreted as measured 100-robot Wi-Fi times.

P2O changes ONLY temporal scheduling of P2M/P2N's EXISTING messages
and task-owner round windows. It deliberately retains:
- 100 robots and 100 tasks, capacity1.
- one sender-paid, model-reliable external TASK dissemination.
- each robot's original one independently lossy Cost row broadcast,
  original one 1016B P2KV (100 tasks x10 tickets) Cost-Softmax Vote
  broadcast, temperature5, only locally received matrices.
- same fixed owner(task) = task_id % robots, same OWN CLAIM fields
  and normalized score/tie order, same irrevocable task reservation.
- 28B P2LC CLAIM, 16B P2AK receipt ACK, 20B P2MD GRANT/DENY,
  16B P2MA decision ACK, independent original per-SEND/receiver
  Bernoulli loss, max 24 attempts for remote REQUEST and owner
  DECISION, including all failed physical attempts in Bytes.
- three original 20B P2NX EXECUTING broadcasts per actually
  GRANT-receiving robot; only genuinely received notices enter
  each OTHER robot's local known-executing task set. This remains
  advisory and can NEVER grant or release execution rights.
- failed control and reserved-but-not-granted cases remain incomplete;
  no hidden full-information repair. Old P2M/P2N source behavior
  is explicitly preserved when timing_mode="serial" (default).

## Actual change — event-driven round transport, not a second allocator

The ONLY task-owner allocator remains the original
democracy_mrta.claim_resolution.coordinate_p2m_task_owners. The
P2O caller chooses timing_mode="causal" and
retry_timeout_ms=100.0 by default; old callers omit both.

For one bounded task-owner round:
1. Owner coordinator selects each active robot's candidate task
   from its OWN native Cost/Vote and physically received P2NX
   notifications. It creates the unchanged P2LC CLAIMs.
2. schedule_p2o_exchange_window("request", plans) starts ALL
   independent candidate REQUEST timers at the SAME round start.
   Each SEND enters the ORIGINAL WifiCausalTimingSampler in
   nondecreasing physical release-time order, with ONE shared
   serialized 144Mbps modeled radio resource. Overlapping
   end-to-end waits do NOT serialize other robots' releases.
3. Every original P2LC physical receipt is individually checked;
   an owner considers ONLY CLAIMs its own receiver actually got,
   and responds with the unchanged 16B ACK at actual arrival time.
   The owner cannot know if its outgoing ACK arrived; the robot
   retries the same CLAIM only on its own configured timeout
   if it has not received an ACK. Attempts are capped at 24.
   ACK may arrive after an earlier retry has begun, as in a
   real asynchronous timeout/reply race; all sends count.
4. After this original known-roster round request window closes,
   the SAME coordinator picks task winners by its unchanged
   normalized vote support, locks tasks once and builds original
   P2MD owner DECISION messages. No global hidden Cost or
   receipt information is used for owner arbitration.
5. schedule_p2o_exchange_window("decision", plans) sends ALL
   task owner replies concurrently as distinct sender releases
   on that same serialized physical radio. A robot that
   physically receives GRANT immediately records its first
   executable-arrival time and initiates exactly three original
   20B P2NX broadcast SENDs. It does NOT wait for owner receipt
   of its own 16B P2MA ACK before announcing execution.
   The owner may still retry an unchanged P2MD if the final
   ACK did not return; it NEVER reallocates the reserved task.
   Physical decision ACKs are generated after each actual
   delivered P2MD; no magical knowledge of return delivery.
6. Only after the bounded decision exchange window ends do
   actually denied robots begin a next candidate round.
   P2NX observations from this round are applied to each
   remote receiver's own local task-occupancy set ONLY if
   its physical P2NX delivery succeeded. Unknown task
   occupancy does not mean free; the deterministic task
   owner must still GRANT.
7. Stop when all tasks have real GRANT executions, there are
   no eligible reattempts, or max_rounds=101 is reached.
   The known-roster round barrier is STILL present and
   explicitly charged; P2O is not arbitrary fully async
   consensus or a proof of real-world network performance.

P2O's timeout is an EXPLICIT new modeling assumption, not a
measurement: for the initial study, retry_timeout_ms=100.0,
all senders, both REQUEST/ACK and GRANT/decision-ACK.
A timeout is measured from the sender's last physical SEND
release. Its lost/late ACK triggers the next attempt at
sender_send_time+timeout; after the 24th attempt, the sender
waits one last timeout before terminal detection. This
can increase the wait for very slow packets even though
parallel scheduling reduces artificial global blocking.
For sensitivity tests vary ONLY this timer under a
separate P2O run (e.g. 50/100/200ms), never fold different
timers into an unlabelled estimate.

## Named owner functions and diagnostics

- validate_p2o_timing_scope owns numeric time/phase/duplicate
  participant validation; time/P2O_INVALID_TEMPORAL_SCOPE.
- encode_p2o_exchange_payloads uses existing original P2M
  P2LC/P2AK/P2MD/P2MA on-wire encoder owners;
  data/P2O_CANNOT_SEND_IDLE_CLAIM.
- validate_p2o_received_payload validates only physically
  delivered requests or decisions using original P2M decoders;
  contract/P2O_RECEIVED_CLAIM_CHANGED,
  contract/P2O_RECEIVED_GRANT_CHANGED.
- schedule_p2o_exchange_window owns the physical packet
  release/receipt/timeout/ack/announcement event priority
  queue (one temporal concern, no task winners or votes);
  time/P2O_NONCAUSAL_EVENT_TIME,
  time/P2O_EVENT_ORDER_REVERSED,
  contract/P2O_DECISION_ACK_INVALID,
  runtime/P2O_UNKNOWN_EVENT_KIND,
  safety/P2O_UNAUTHORIZED_ANNOUNCEMENT.
- validate_p2o_announcement_receipts only updates truly
  delivered own task/remote P2NX knowledge after authentic
  GRANT; safety/P2O_NOTICE_WITHOUT_DELIVERED_GRANT,
  contract/P2O_INVALID_NOTICE_RECEIVER.
- coordinate_p2m_task_owners is the ONE original claimant
  state owner; mode selection data/P2O_UNKNOWN_TIMING_MODE,
  first time/P2O_REQUEST_NOT_DELIVERED and
  time/P2O_OWNER_DECISION_NOT_DELIVERED; retains all
  original P2M uniqueness/lock safety errors.
- experiments.run_p2m_task_owner.run_one_p2m_case opt-in
  causal metrics and full event audit only when mode chosen;
  P2M/P2N source schema remains exactly unchanged by default.
- experiments.run_p2o_causal_owner_timing runs only P2O,
  a single new experiment per Seed/Loss with its own
  source SHA/scene identity/per-seed/summary/audit/config/hash
  manifest. No legacy arms or old-method benchmark are run.

All important errors preserve first owner/function/category/code
and where relevant expected/actual/details. Existing diagnostic
categories remain data/time/state/dependency/planning/safety/
runtime/contract.

## Time breakdown and reproducibility

Per Seed and loss, P2O records:
- actual attempted physical sender Bytes and SENDs for original
  TASK, Cost, Vote and original four P2M control phases,
  plus exactly 3x20B per physically received GRANT;
- per-class received/dropped observations, first-failed
  owner/function/category/code, actual incomplete/duplicate
  task counts, conditional complete-allocation cost;
- full owner window duration broken out as
  request_window_total_ms + decision_window_total_ms,
  owner_timeout_wait_total_ms (diagnostic, overlaps the
  corresponding windows, NOT add again to total);
- last_first_grant_arrival_ms: time when the last
  actually executable robot received its FIRST GRANT;
  owner_protocol_finish_ms: end of required last
  timeouts/ACK and P2NX in the modeled protocol;
  native_stop_ms adds the original startup TASK timing
  exactly as in the P2N experiment convention;
- audit_p2o.jsonl first seeds: per-robot original vote
  support, real owner winner decisions, per-receiver
  physical control and announcement delivery observations,
  every original physical SEND time/arrival and final
  irreversible reservations.

All times are MODEL TIMES from one shared causal radio
proxy + sampled Rady delay, NOT wall clock and not
an 802.11ax interference/collision simulator.
No CPU optimizer runtime, full MAC retransmission or
correlated loss modeled.

Only the NEW P2O method runs in formal grid:
100R100T, B1000, 3xP2NX, capacity1, PL0/30/50/90,
10 Seeds per Loss = 40 total. Historical P2N
results can be read as prior evidence but are NOT
re-run or silently mixed into P2O summary.
Never claim improvement until local tests/smoke and
native 40-row CSV were checked.

## Mac: pull, targeted test, smoke and 10 Seeds

From repository root:

    git fetch origin
    git switch --track origin/experiment/p2o-causal-owner-timing
    git pull --ff-only origin experiment/p2o-causal-owner-timing
    git rev-parse --short HEAD

If branch already exists locally use:
    git switch experiment/p2o-causal-owner-timing

Target only P2O (do not run old benchmark arms):

    python3 -m compileall -q democracy_mrta experiments tests
    python3 -m unittest discover -s tests -p 'test_p2o*.py' -v

First small 2-Seed smoke (6 NEW-method cases):

    P2O_SMOKE="results/p2o_smoke_$(date +%Y%m%d_%H%M%S)"
    python3 -m experiments.run_p2o_causal_owner_timing \
      --losses 0.00,0.30,0.90 --seeds 2 --votes 1000 \
      --retry-timeout-ms 100 --announcement-repetitions 3 \
      --max-attempts 24 --max-rounds 101 \
      --output-root "$P2O_SMOKE"

Formal NEW-method-only 40 cases, ONLY after smoke is green:

    set -o pipefail
    P2O_RUN="results/p2o_10seed_$(date +%Y%m%d_%H%M%S)"
    python3 -m experiments.run_p2o_causal_owner_timing \
      --losses 0.00,0.30,0.50,0.90 \
      --votes 1000 --seeds 10 \
      --retry-timeout-ms 100 \
      --announcement-repetitions 3 \
      --max-attempts 24 --max-rounds 101 \
      --audit-seeds 1 --output-root "$P2O_RUN" \
      2>&1 | tee "$P2O_RUN.log"

Pack complete raw + first-seed detailed physical chronology:

    test -f "$P2O_RUN/manifest_p2o.json" && \
    zip -j "$HOME/Downloads/p2o_causal_timing_10seed.zip" \
      "$P2O_RUN/per_seed_p2o.csv" \
      "$P2O_RUN/summary_p2o.csv" \
      "$P2O_RUN/audit_p2o.jsonl" \
      "$P2O_RUN/run_config_p2o.json" \
      "$P2O_RUN/manifest_p2o.json" \
      "$P2O_RUN.log"

GitHub source commits cannot prove Python tests pass.
On a failure capture the FIRST complete traceback including
owner/function/category/code. Fix the true owner and update
the canonical + continuity record, never bypass a contract.

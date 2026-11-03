# P2N: Task Owner + 3x EXECUTING Announcement

Branch: experiment/p2n-execution-announcement
Study ID: P2N_1000_SOFTMAX_TASK_OWNER_EXECUTING_3X_ONLY

Status: GitHub source and targeted tests written, local Python compilation
and actual smoke / 10-seed results pending the Mac operator.

## Goal and physical semantics

Keep the P2M original 1000-ticket Cost Softmax Vote, the ONE 1016B P2KV
physical Vote broadcast per robot, and fixed per-task grant authority:
owner(task_id) = task_id % robots. No historical method is rerun.
P2N adds only post-GRANT repeated EXECUTING announcement and per-robot
advisory local knowledge of already executing tasks.

Protocol steps:

1. Initial TASK dissemination stays model-reliable and sender-paid as
   in P2M. Each robot broadcasts ONE lossy Cost and ONE 1000-ticket
   original P2KV Vote; each recipient sees only truly delivered Cost
   rows and Vote packets. Each robot independently computes its OWN
   tentative one-to-one assignment.
2. Candidate sends a 28B P2LC CLAIM to the deterministic TASK OWNER,
   receives a 16B receipt ACK if delivered; owner compares only
   actually received candidate-local normalized support ratios
   (its vote numerator / [10 * received original P2KV packets]).
   Owner reserves its task irrevocably before attempting a 20B P2MD
   GRANT or DENY and 16B decision ACK.
3. A robot may execute only if it physically received the owner
   GRANT. ONLY THEN does it broadcast the SAME 20-byte P2NX
   EXECUTING announcement exactly THREE physical times.
   Physical SEND accounting includes all 3 attempts, even if
   every remote recipient drops them. Each unique actually
   GRANT-receiving executor issues one three-copy announcement;
   a task reserved but whose GRANT was lost never emits one.
4. P2NX wire is 20 bytes: <4sIIII> tag P2NX, claim_round,
   real executor_robot_id, task_id, fixed_task_owner_id.
   Each physically received packet is verified against its native
   sender, expected claim epoch/task and fixed task-owner mapping.
   Sender identity is authenticated only within the simulation,
   NOT cryptographically for adversarial real radio.
5. Every other robot stores task_id in its OWN known_executing_tasks
   only upon a genuinely delivered, validated P2NX packet.
   Repeated received P2NX copies are deduplicated locally.
   A missing P2NX does not imply a task is vacant.
6. In subsequent request rounds, a losing/idle robot chooses among
   tasks not in its OWN DENY history or OWN received
   known_executing_tasks, ranked using ONLY its OWN original
   Vote self-support and OWN Cost row. It has no global
   task-reservation map or merged Cost/Score view.
   Regardless of the local skip, the fixed task owner is still
   the sole issuer of GRANT. Every task-owner request/grant
   phase remains physically simulated and sender-paid.

No PSCR, full Score synchronization, global fallback, all-peer CLAIM
ACK, hidden voter observations or duplicate task-state machine.
A P2NX is advisory, not a GRANT, not proof of task completion and
not a task release. Owner retains irreversible reservation even
when an approved executor never received GRANT. This may leave
tasks unexecuted but does not allow duplicate authorized execution.

All 3 copies use Bernoulli per-recipient packet loss with keys
sender/recipient/task/round/copy. At p=0.3 the probability a given
receiver obtains >=1 of 3 independent copies is 1-0.3^3 = 97.3%;
at p=0.9 it is only 27.1%. This is NOT universal delivery
or a real radio correlation guarantee.

For 100 tasks all actually executing and 3 attempts each:
100 * 3 * 20 = 6,000 application-layer sender Bytes.
There are no per-receiver P2NX ACKs. Real physical MAC/PHY overhead
is beyond this application payload metric, although the existing
Rady Wi-Fi6 hypothetical 144 Mbps shared-medium proxy includes
modeled frame service. CPU time is still not modeled.

## Owners, named functions, diagnostic boundary

Existing real ownership module democracy_mrta.claim_resolution owns
this concern; NO second task assignment state machine:
- validate_p2n_announcement_repetitions: opt-in 0..5 (0 preserves
  historical P2M), data/P2N_INVALID_ANNOUNCEMENT_REPETITIONS.
- encode_p2n_execution_announcement: one 20B P2NX wire,
  data/P2N_INVALID_EXECUTING_FIELDS.
- decode_p2n_execution_announcement: strict received frame contract,
  data/P2N_BAD_EXECUTING_PACKET_SIZE or
  contract/P2N_EXECUTING_IDENTITY_MISMATCH.
- transmit_p2n_execution_announcement: exactly 3 physical
  broadcasts, true receiver receipts, local deduplication;
  contract/P2N_CANNOT_SEND_ZERO_REPETITIONS.
- select_p2m_local_request_task: opt-in local known_executing_tasks
  exclusion in task selection, preserving previous behavior by default.
- coordinate_p2m_task_owners: opt-in repetitions=3, only physically
  received owner GRANT triggers P2NX, then receiver-specific local
  known state is updated; preserves existing fixed-owner safety and
  diagnostics, particularly safety/P2M_INVALID_RESERVED_EXECUTION.
- experiments.run_p2m_task_owner.run_one_p2m_case: optional original
  native source accounting, raw evidence and audit; with repetition=0,
  historical P2M network behavior and original CSV schema are kept.
- experiments.run_p2n_execution_announcement: ONLY new-method
  experiment axes, raw/summary/audit, source SHA and manifest.

Error categories remain data/time/state/dependency/planning/safety/
runtime/contract; important failure has owner/function/category/code
and appropriate expected/actual/details. The first genuine missing
request/GRANT owner diagnostic remains visible and is never
hidden by a full-information correction.

## Evidence

Only P2N single method per (seed, loss), no other method arms.
Record original preclaim local collision as a diagnostic from the
SAME Cost/Vote run; not a second experiment or network SEND.
Record final executed unique/duplicate/missing tasks, full valid,
fully valid allocation cost or separately labeled partial cost,
per-phase attempted sender Bytes/SENDs including failed P2NX
broadcasts, receiver drops, repeated P2NX count, per-receiver
actual known executing tasks and avoided blocked-task requests,
reassignment rounds, first error and native modeled stop time.
The first audit seed for each loss includes all true delivered
P2NX receiver observations, claimant's own Vote support row,
and every owner's public task decision. All output SHA256 hashes
are recorded in manifest_p2n.json.

Formal grid: 100 robots, 100 tasks, capacity1, 1000 tickets/robot,
loss 0/30/50/90%, 10 seeds, 3 announcement copies, 40 cases.
Do not run or plot old P2J/P2K/P2L/P2M comparison arms.

## Mac runbook

From the project root:

    git fetch origin
    git switch --track origin/experiment/p2n-execution-announcement
    git pull --ff-only origin experiment/p2n-execution-announcement
    git rev-parse HEAD

If the branch already exists locally, use git switch
experiment/p2n-execution-announcement instead of switch --track.

Compile + P2N focused regression:

    python3 -m compileall -q democracy_mrta experiments tests
    python3 -m unittest discover -s tests -p 'test_p2n*.py' -v

Two-seed smoke, loss 0/30/90, SIX cases, only P2N:

    P2N_SMOKE="results/p2n_smoke_$(date +%Y%m%d_%H%M%S)"
    python3 -m experiments.run_p2n_execution_announcement \
      --losses 0.00,0.30,0.90 --votes 1000 --seeds 2 \
      --announcement-repetitions 3 \
      --output-root "$P2N_SMOKE"

Ten-seed formal exploratory NEW-method-only run, FOUR losses x10:

    set -o pipefail
    P2N_RUN="results/p2n_10seed_$(date +%Y%m%d_%H%M%S)"
    python3 -m experiments.run_p2n_execution_announcement \
      --losses 0.00,0.30,0.50,0.90 \
      --votes 1000 --seeds 10 \
      --announcement-repetitions 3 \
      --max-attempts 24 --max-rounds 101 \
      --audit-seeds 1 --output-root "$P2N_RUN" \
      2>&1 | tee "$P2N_RUN.log"

Pack all new evidence, especially the complete audit JSONL:

    test -f "$P2N_RUN/manifest_p2n.json" && \
    zip -j "$HOME/Downloads/p2n_execution_announce_10seed.zip" \
      "$P2N_RUN/per_seed_p2n.csv" \
      "$P2N_RUN/summary_p2n.csv" \
      "$P2N_RUN/audit_p2n.jsonl" \
      "$P2N_RUN/run_config_p2n.json" \
      "$P2N_RUN/manifest_p2n.json" \
      "$P2N_RUN.log"

Source-only GitHub commits are not evidence of passing Python tests.
If local test/smoke fails, report the FIRST complete owner traceback;
do not reinterpret partial allocations as successful. No performance
improvement is claimed until the 10-seed native CSV is validated.

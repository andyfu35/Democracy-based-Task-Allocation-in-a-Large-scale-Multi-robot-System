# P2J — One Cost, One Probabilistic Multi-Ticket Vote Batch, Dynamic Margin Matching

**Experimental branch:** \`experiment/p2j-probabilistic-100vote-once-20261022\`.
**Status:** implementation and test source committed to branch; independent Mac Python
compile/test/smoke/formal evidence is **PENDING**. No main README/paper figures
are replaced by unverified trial outcomes.

## Why this is a new test

The user specified **exactly 100 tickets per voting robot TOTAL**, not 100
tickets per task, and only **one physical Cost exchange + one Vote Batch**.
Each voter observes only Cost rows physically delivered to it; its own row
is always locally available. It samples 100 independent pair tickets, groups
duplicate \`(task, candidate)\` tickets, and emits ONE serialized \`PVOT\`
broadcast (up to 416B for 100 records); it does not physically send a frame
per ticket, task, or retry. Under Bernoulli loss each intended remote
recipient independently receives the batch or drops it. Receiver-local
Candidate Vote counts include sender's local tickets only if the candidate
is the sender and the sender ready time meets the deadline; remote ballots
only count after timely physical arrival of their original broadcast.

The algorithm is a **stochastic policy inspired by decision-making**,
NOT a learned Markov decision process (MDP) or trained Markov model. No
transition/reward training, policy gradient or hidden Markov inference is
claimed.

## Fixed probability and matching formulas

For voting robot \`v\`, let \`R_v\` contain only the physical Cost rows it
knows (including itself); \`T\` includes the 100 announced tasks.
Tickets choose task uniformly then candidate conditioned on task:

\`\`\`text
P_v(T=t,R=r)
  = (1/|T|) * exp(-(C[r,t]-min_{k in R_v} C[k,t])/tau)
             / sum_{j in R_v} exp(-(C[j,t]-min_{k in R_v} C[k,t])/tau)
tau = 5.0; tickets_per_voter = 100; seed SHA256 keyed by
scene seed, local voter ID, epoch, ticket count and temperature.
\`\`\`

For a proposed \`(t,r)\`, the candidate \`r\` counts its own tickets and the
tickets in received original Vote broadcasts addressed to it. One
candidate-local paid reliable \`PSCR\` Score packet then publishes positive
counts and **that candidate's own truthful self-known** \`C[r,t]\`
(float64). It does NOT read or publish other robot's unreceived Cost rows.
The physically transmitted Score size is 16B + 11B per positive task,
maximum 1116B at 100 tasks. TASK/Score/Commit retain their explicitly
modeled reliable control assumption; no simulated lossy ACK, collision,
Wi-Fi MAC retry, OFDMA or actual 100-device RF performance is implied.

For all remaining tasks \`T'\` and eligible robots \`R'\`, recompute each
task's top two **positive physically certified** candidate counts.
Let \`v_(1)(t)\` and \`v_(2)(t)\` be its top and runner-up counts (runner-up=0
if only one candidate). The default raw-margin priority is

\`\`\`text
Delta(t) = v_(1)(t) - v_(2)(t)
t* = argmax_{t in T' with positive votes} [
      Delta(t), v_(1)(t), -winner_reported_cost(t),
      -task_id(t), -winner_robot_id(t)
    ]
r* = argmax_{r in R' with certified (t*,r) positive vote} [
      votes(t*,r), -own_announced_cost(t*,r), -robot_id(r)
    ]
\`\`\`

The winner \`(r*,t*)\` is committed once; remove both \`r*\` and \`t*\`,
then **recompute ALL surviving task margins** before the next selection.
No fixed ascending task order. Equal ticket counts use physically paid
candidate-own Cost, then robot ID; task-priority ties use winner vote total,
self-reported Cost, task ID and robot ID. An alternative predeclared
\`--margin-rule normalized\` divides the difference by the sum of positive
votes for that task, but this is NOT the formal default.

Tasks without any positive eligible certified Vote **stay unassigned**.
A stochastic assignment may be incomplete **even at zero packet loss**;
no hidden Cost is filled in and no nonexistent completed assignment is
declared successful. The full-information Global minimum-pair Greedy is
used **only offline** as the cost denominator on *fully complete* runs.
The new output also includes partial committed Cost and mean Cost per
actually committed task so poor coverage is not concealed or imputed as
a fake 0% Greedy gap.

## One concern / original owner / one named function

- \`optimizer.validate_probabilistic_vote_policy\`: data policy boundary.
- \`optimizer.sample_probabilistic_pair_votes\`: pure seeded stochastic
  sampling; never reads costs outside the voter's received rows.
- \`coordination.validate_probabilistic_batch_scope\`: contract for exactly
  1 native decision epoch, 1 Cost, 1 Vote per voter, physically paid
  Score/Commit, no external retained full Cost, and deterministic seed.
- \`coordination.build_epoch_probabilistic_ballots\`: maps locally sampled
  task/robot indices to actual physical IDs.
- \`coordination.encode_probabilistic_vote_packet\` /
  \`decode_probabilistic_vote_packet\`: exact compact sender payload and
  first invalid-data/contract error; no silent frame fragmentation.
- \`coordination.collect_probabilistic_batch_votes\`: physical Vote owner,
  1 SEND per voter, per-recipient Bernoulli delivery, cutoff and candidate
  self-counting. Existing Cost, E9H shared-medium network and one-round
  E2/retirement owners are reused.
- \`coordination.encode_probabilistic_score_packet\` /
  \`decode_probabilistic_score_packet\`: validated positive candidate-local
  Score including the candidate's OWN original self-known Cost.
- \`coordination.publish_probabilistic_batch_scores\`: physically paid
  candidate Score announcements (only successful local receipts).
- \`coordination.resolve_dynamic_probability_margin_winners\`: recalculates
  all remaining vote gaps after each capacity-one assignment; no second
  epoch/state machine or task-ID-first ordering.
- Existing \`coordination.simulate_greedy_batch_vote_epoch\` retains the
  SAME Cost→Vote→Score→Commit timeline with the explicit opt-in path.
  \`simulate_democracy_hungarian_lossy\` and
  \`simulate_democracy_hungarian_retirement\` retain original runtime
  execution and membership owners. All defaults unchanged.
- \`experiments.run_e9h_adaptive_deadline.run_e9h_original_voting_case\`:
  opt-in flag forwarded, original TASK and physical packet accounting.
- \`experiments.run_p2j_probabilistic_batch\` only owns study axes,
  paired original native calls, evidence audit and aggregation. It never
  generates a substitute assignment.
- First failure names owner/function/category/code and optionally
  expected/actual/details; fixed categories data/time/state/dependency/
  planning/safety/runtime/contract. Most important new errors:
  \`optimizer.sample_probabilistic_pair_votes/state/P2J_INVALID_LOCAL_COST_VIEW\`,
  \`coordination.validate_probabilistic_batch_scope/contract/P2J_ONE_SHOT_SCOPE_VIOLATION\`,
  \`coordination.decode_probabilistic_vote_packet/contract/P2J_INVALID_RECEIVED_VOTE\`,
  \`coordination.resolve_dynamic_probability_margin_winners/contract/P2J_INVALID_CERTIFIED_SCORE\`,
  \`experiments.run_p2j_probabilistic_batch.audit_p2j_native_sender/contract/P2J_ONE_BATCH_SEND_CONTRACT\`.

## Frozen paired experiments

E0 100 robots, 100 tasks, capacity 1, seeds 0–99; per-receiver Cost
and Vote Bernoulli loss separately applied at **the same rate** 0%,10%,
20%,30%,40%,50%,60%,70%,80%,90%. Particular emphasis on **30% loss**.
Timing uses original Rady (Wi-Fi 6E ax_160mhz_6ghz medium-range LoS sample)
plus hypothetical shared 144Mbps serialized medium, **not RF
measurement**. TWO paired native methods:
- \`one_batch_greedy\`: original Global minimum-edge Greedy local
  planning from the received Cost rows; one original Greedy Vote Batch.
- \`probabilistic_margin\`: new 100-ticket task-balanced Softmax sampling
  + dynamic **raw top-two vote-count margin**, Cost only tie-break.

No Cost, Vote, or task is retransmitted; TASK/Score/Commit remain
model-reliable and are billed. Strictly compare successful full allocation
rate; average **task coverage** for incomplete runs; cost% vs full-info
Global Greedy only if fully complete; partial mean committed cost per
completed task; all-seed modeled stop time and application sender Bytes.
Use actual original packets for both; one Vote broadcast per robot (not
100 separate SENDs). Paid candidate Score frames may differ and must
not be omitted from totals.

Formal = 10 losses × 100 seeds × 2 native methods = **2,000 original
native runs**, 20 summary cells. Raw evidence append-only per new
output root, CSV includes per-seed input SHA, scene hash, source commit,
transport phases, native stop, full-complete cost and partial-cost
distinction; JSON manifest includes hashes. Do not merge into
main or replace README curves before the user supplies results and
we independently audit.

## Mac reproducibility commands

\`\`\`bash
cd "$(git rev-parse --show-toplevel)"
git fetch origin
git switch experiment/p2j-probabilistic-100vote-once-20261022
git pull --ff-only
git rev-parse HEAD
python3 -m compileall -q democracy_mrta experiments tests &&
python3 -m unittest discover -s tests -p 'test_p2j*.py' -v &&
python3 -m unittest discover -s tests -v
\`\`\`

**Only if every test passes**, run PL0/PL30/PL90 ×2 seeds ×2 modes = 12
native smoke cases (not a full formal claim):

\`\`\`bash
P2J_SMOKE="results/p2j_smoke_$(date +%Y%m%d_%H%M%S)"
python3 -m experiments.run_p2j_probabilistic_batch \
  --losses 0.00,0.30,0.90 --seeds 2 \
  --votes-per-voter 100 --temperature 5.0 --margin-rule absolute \
  --output-root "$P2J_SMOKE"
\`\`\`

Then 0% loss 100 seeds ×2 modes = 200 control examples:

\`\`\`bash
P2J_ZERO="results/p2j_zero_$(date +%Y%m%d_%H%M%S)"
python3 -m experiments.run_p2j_probabilistic_batch \
  --losses 0.00 --seeds 100 \
  --output-root "$P2J_ZERO"
\`\`\`

Only the \`one_batch_greedy\` 0% control MUST match complete
full-info Global Greedy (100/100, 0% cost gap). P2J probability may
remain incomplete or differ in cost; those are **observations**, not
automatic defects.

The frozen formal experiment:

\`\`\`bash
set -o pipefail
P2J_FORMAL="results/p2j_100seed_$(date +%Y%m%d_%H%M%S)"
python3 -m experiments.run_p2j_probabilistic_batch \
  --formal --seeds 100 --votes-per-voter 100 \
  --temperature 5.0 --margin-rule absolute \
  --output-root "$P2J_FORMAL" 2>&1 | tee "$P2J_FORMAL.log"
\`\`\`

If \`P2J_COMPLETE\` and \`manifest_p2j.json\` both exist:

\`\`\`bash
zip -j "$HOME/Downloads/p2j_probabilistic_onebatch_100seed.zip" \
  "$P2J_FORMAL/per_seed_p2j.csv" \
  "$P2J_FORMAL/summary_p2j.csv" \
  "$P2J_FORMAL/run_config_p2j.json" \
  "$P2J_FORMAL/manifest_p2j.json" \
  "$P2J_FORMAL.log"
shasum -a 256 "$HOME/Downloads/p2j_probabilistic_onebatch_100seed.zip"
\`\`\`

**Never claim tests/CI, native cases or physical packet replay passed
until actual outputs are received.** Preserve the FIRST traceback,
stop formal, and fix the true owner rather than hiding errors or
fabricating evidence.

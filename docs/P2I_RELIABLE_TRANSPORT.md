# P2I — original Global Greedy Voting, Cost/Vote ACK-and-retry A/B

**Branch:** \`experiment/p2i-cost-vote-ackretry-20261021\`.

## Native experiment contract

100 robots, 100 tasks, capacity 1, same \`generate_e0_scenario(seed,100,100)\`, seed 0..99, identical 10 packet loss rates 0..90% in steps of .10, 100 paired seeds. Two original native Proposed/Global minimum-pair Greedy arms:
- \`full_retry\`: each original Cost row broadcast and Batch Vote packet is ACK-confirmed by all intended peers, retransmitting the **same** payload only for missing recipients (one broadcast retransmission is one sender SEND, not per-receiver unicast). Physical ACK bitmap broadcast is paid, assumed reliable control like original Score/Commit. One batch Vote decision epoch after Cost completion; no fresh planning merely due to packet retry.
- \`cost_retry_vote_once\`: Cost ACK-confirmed exactly as above; each voter emits exactly one original Batch Vote. Original received self-vote/relative plurality + reliable Score/Commit remain unchanged. **Vote loss may prevent full task completion; the full-info Global Greedy optimum of the completed assignment is not guaranteed merely from full Cost.** No subsequent decision epoch: original \`max_rounds=1\`.

Keep unchanged old P2E/P2G Figure2 and source evidence. Neither mode uses implicit full Cost except actual received-and-ACK-confirmed original packets. ACK frames are actual \`_broadcast_event\` SENDs via the same causal Rady+144Mbps shared-medium sampler; ACKs are modeled reliable, not RF-tested ACK frames. ACKs contain sender-presence bitmaps (16B application header + ceil(N/8) Bytes) and are not silently free. Original Cost full row = 16+8T Bytes; Vote full batch = 16+8K Bytes (K remaining task/robot proposals). Both original Bernoulli delivery and deadlines stay in their true coordination/network owners. A **maximum 300 transmission waves** is a guard; at exhaustion raise \`coordination.transmit_acknowledged_broadcast_phase/time/P2I_ACK_RETRY_LIMIT_REACHED\` and stop, do not mark successful full-information result. Current study does not include lossy ACK, RF collision, EDCA or actual MAC ARQ. Do NOT generalize modeled ACK reliability to actual Wi-Fi reliability.

**Cross-method denominator:** \`solve_visible_batched_greedy_assignment(scene.cost_matrix, ALL robots)\` used OFFLINE only. For complete solutions \`cost_increase_percent=100(C_native/C_global_greedy-1)\`; incomplete cost is blank (not 0), with completion rate/coverage separately. All physical original TASK, Cost, Cost ACK, Vote, Vote ACK, Score and Commit application SENDs are charged irrespective of receiver loss. Incomplete guard-exhausted cases must retain error and physical trace for diagnosis; the present strict runner stops at first failed case rather than synthesizing a partial result.

## Native one-concern owners

- \`coordination.validate_ack_retry_scope\` checks opt-in Global Greedy flags and retry bound;
- \`coordination.encode_reliable_receipt_bitmap/decode_reliable_receipt_bitmap\` serializes and validates physically paid ACK source membership;
- \`coordination.transmit_acknowledged_broadcast_phase\` owns immutable Cost OR Vote DATA retransmission, actual receiver observation, and ACK-driven still-missing set;
- \`coordination.capture_retirement_cost_snapshot\` captures solely delivered Cost;
- \`coordination.collect_greedy_batch_votes\` uses deduplicated one-voter/one-task Vote ledger, whether transport is single-send or retry;
- \`coordination.simulate_democracy_hungarian_retirement\` retains the ORIGINAL owner for one native epoch, retirement, Commit and safety;
- \`experiments.run_e9h_adaptive_deadline.run_e9h_original_voting_case\` forwards new opt-in flags and keeps ACK phase SEND ledgers;
- \`experiments.run_p2i_reliable_transport.run_native\` owns only orchestration, source metrics and independent sender checks; \`summarize\` handles success-conditional cost;
- \`network.WifiCausalTimingSampler.sample_packet_ms\` remains the sole physical SEND timing/traffic owner, untouched.

First failing diagnostic fields owner/function/category/code, expected/actual/details; types data/time/state/dependency/planning/safety/runtime/contract. No wrapper or second decision state machine. This is a new research factor, not the old 300 fresh-decision-epoch Proposal or one-shot Cost in P2G.

## Mac test and formal run (stop at first failure)

\`\`\`bash
cd "$(git rev-parse --show-toplevel)"
git status --short
git fetch origin
git switch experiment/p2i-cost-vote-ackretry-20261021
git pull --ff-only
git rev-parse HEAD

python3 -m compileall -q democracy_mrta experiments tests &&
python3 -m unittest discover -s tests -p 'test_p2i*.py' -v &&
python3 -m unittest discover -s tests -v
\`\`\`

2 seeds × 2 loss points × 2 methods = 8 physically native smoke cases. Each output root must be fresh.

\`\`\`bash
P2I_SMOKE="results/p2i_retry_smoke_$(date +%Y%m%d_%H%M%S)"
python3 -m experiments.run_p2i_reliable_transport \
  --losses 0.00,0.90 --seeds 2 --retry-limit 300 \
  --output-root "$P2I_SMOKE"
\`\`\`

Only after smoke success, independently verify 100 seeds at 0% loss:

\`\`\`bash
P2I_ZERO="results/p2i_retry_zero_$(date +%Y%m%d_%H%M%S)"
python3 -m experiments.run_p2i_reliable_transport \
  --losses 0.00 --seeds 100 --retry-limit 300 \
  --output-root "$P2I_ZERO"
\`\`\`

Require 200/200 complete, every source mean/case quality at exactly 0 relative to Global Greedy, both modes with Cost ACK, only full_retry with Vote ACK. Cost-only Vote frame sender count = 100.

Run 100 seed ×10 loss ×2 modes = 2,000 *new* actual native experiments, 20 condition groups:

\`\`\`bash
set -o pipefail
P2I_FORMAL="results/p2i_retry_formal_$(date +%Y%m%d_%H%M%S)"
python3 -m experiments.run_p2i_reliable_transport \
  --formal --seeds 100 --retry-limit 300 \
  --output-root "$P2I_FORMAL" 2>&1 | tee "$P2I_FORMAL.log"
\`\`\`

Expected: \`per_seed_p2i.csv\`, \`summary_p2i.csv\`, \`run_config_p2i.json\`, \`manifest_p2i.json\`. **Do not fabricate a missing CSV or resume a failed case with a different SHA.** Send the first traceback if any test or execution fails.

\`\`\`bash
test -f "$P2I_FORMAL/manifest_p2i.json" &&
zip -j "$HOME/Downloads/p2i_reliable_transport_100seed.zip" \
  "$P2I_FORMAL/per_seed_p2i.csv" \
  "$P2I_FORMAL/summary_p2i.csv" \
  "$P2I_FORMAL/run_config_p2i.json" \
  "$P2I_FORMAL/manifest_p2i.json" \
  "$P2I_FORMAL.log" &&
shasum -a 256 "$HOME/Downloads/p2i_reliable_transport_100seed.zip"
\`\`\`

**Verification status:** Commit/code checks through GitHub only. The originating assistant cannot run Mac Python in this runtime and must not claim smoke or formal is verified until user's local outputs arrive. The user's Python run is the next mandatory gate before any paper-facing figure change.

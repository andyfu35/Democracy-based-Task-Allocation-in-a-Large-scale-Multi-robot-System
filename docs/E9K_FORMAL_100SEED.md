# E9K formal: original-source verified paid CBAA termination (2026-10-12)
**Classification: internal engineering validation only — excluded from the official allocation-algorithm Benchmark.** E9K is our team's optional CBAA READY/COMMIT termination protocol modification, **not a separate original/literature task allocation algorithm**. The numerical contrasts below quantify this termination-extension overhead as a technical ablation, **not a fourth competitor** in Voting vs original CBAA vs Price Auction. Its original run, source archives and technical findings are preserved.


**Evidence:** User-run E9K ZIP SHA256 `1495612c65a4fb40733af225b2121275e2b2309070695f2594c620079a6b8281`, executable commit `715dfa6c262b7081c241b54a7bddec16354990a3`. Original E9J frozen ZIP SHA256 `106fc14aa9088edf980a744bf9e129c516ce8cabf9c23322baa76be9b33c82bb`; original Voting E9I frozen source is nested as read-only E9J paired rows. Full E9K original CSV SHA256 `c6183a59177b37aaaf1ff2cd723ce4913f22646f137b4260813999df023be39b` and summary `74de2dca68da7d8aff4c2d3c35742dc1a306e1d7fdcd6cd7b12b74c4ae4a1b56`.

Exactly 20 sizes N=T=5..100 step5 × 100 seeds = **2,000 actual E9K simulations**, exactly matched by original E9J N/seed. Independently verified both ZIP SHA256, per-file manifest digests, 2,000 distinct keys and frozen scene/seed/task-broadcast/timeouts/Hungarian oracle, and all grouped means. All rows' native sender packet `16+12N` Bytes, READY+COMMIT 48B SENDs, N−1 receiver trials per SEND, drop bounds, full sender-accounting identity, stage-time identity, old E9J time/Bytes and original Voting time/Bytes match exactly. Original E9J CBAA assignment costs match E9K **in all 2,000 seeds**.

## Main results (100 Robots / 100 Tasks)

| Original method (separate completion contract) | Mean modeled time | Original sender Bytes | Mean Cost/Hungarian |
|---|---:|---:|---:|
| Frozen Voting Cost30/Vote30 guarded, **reliable Commit** | 20.131588 s | 255,498 B | 1.362148 |
| Frozen original CBAA Bid30, **optimistic unpaid stop** | 13.647431 s | 2,693,040 B | 1.235261 |
| **E9K original CBAA + paid READY/COMMIT**, all-N local receipts | **37.527083 s** | **4,074,431 B** | **1.235261** |

All 100/100 E9K N100 cases completed within the 160-iteration safety guard. The full dataset is **2,000/2,000 E9K paid locally certified**, not a proof of Byzantine security or guaranteed distributed common knowledge of terminal state.

100-seed paired mean CBAA paid−Voting time = **+17.395495 s**, bootstrap 95% CI **[+16.798490, +18.038409] s**; paid CBAA is **86.41% longer** by ratio of means, paired bootstrap CI **82.73–90.30%**. Paid CBAA versus original E9J optimistic stop adds **23.879652 s** (paired bootstrap 95% CI 23.486975–24.284600 s), or **174.98%** relative to original CBAA.

The +23.879652s consists of **17.523198s** separate READY/COMMIT phase windows and **6.356454s** additional native CBAA consensus-round timeout. Average native iterations rise from **22.12** (free) to **32.48** (paid). The extra **1,381,391 B** consists of only **121,615 B** of 48B control SENDs plus **1,259,776 B** of extra native Bid/Winner packets; E9K sends **15.95×** original Voting Bytes at N100. No numerical E9K improvement in final assignment Cost relative to original E9J was observed on any seed.

**Causal interpretation and limitations:** This is an engineering extension (not native paper CBAA) with physically modeled sender packets and receiver-specific Bernoulli 30% drop observations, but the conservative **full-vector E9J native per-round timeout is also applied to each nonempty 48B control phase**. The measured timing inversion is thus specific to this deadline assumption; it is NOT evidence that CBAA would be slower in measured Wi-Fi or ns-3. Network services use Rady industrial ROS latency samples plus an assumed 144Mbps shared-medium model without actual 802.11 collisions/retries/OFDMA, spatial correlation or field RF measurements. All-node READY/COMMIT receipt evidence is stronger than the previous unpaid global stop, but still not an authenticated distributed final ACK or infinite common-knowledge termination and is not the same finalization contract as Voting.

**Source-backed evidence:** [20-point derived CSV](docs/figures/e9k_paid/formal/verified_20point.csv) · [original-source manifest](docs/figures/e9k_paid/formal/source_manifest.json) · [three-method time/Bytes SVG](docs/figures/e9k_paid/formal/primary_three_way_time_and_sender_bytes.svg). Only derived rows/figure/attestations are published; original E9K and E9J ZIP raw bytes remain immutable external evidence. Next: **preregister a paid control-window sensitivity ablation** (same 100 paired seeds, keep original E9K frozen) before any real-time conclusion; then independently validate packet-level 802.11 MAC/ARQ/field RF. No E9K new simulation was run by this publication step.

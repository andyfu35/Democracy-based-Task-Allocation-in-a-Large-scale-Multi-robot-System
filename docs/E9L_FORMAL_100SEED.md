# E9L formal original-source audit — 20 sizes × 100 seeds (2026-10-12)

**Status:** User-executed original E9L experiment completed; this is **source-verified derived public evidence**, not a new algorithm run. Original executable Git SHA `0e1a091c547b7cc0d545e0707c51138dfa626d5c`; uploaded exact ZIP SHA256 `2b51cecbd84f105a2cee35bfcd8825de174cb3617f35596a81d94d4de6e5ff41`. Raw `per_seed_e9l.csv` SHA256 `4dd54863f7cb7392c29a0c91682a85c90750df8dc4af162ccb42ec2a9c426ad5`; original grouped CSV SHA256 `220f2fa9c6446ada8daca3cdf14e8b7acd75b1feb640de83343595a3e8f4d3ac`.

### Verification

2,000 unique (N, seed) original E9L runs: N=T=5,10,...100 and seed 0..99; no duplicate/missing records. Formal protocol fields are epsilon **10.0 cost-length units**, independently sampled BID/AWARD receiver loss **30%**, native 28B BID unicast/28B AWARD broadcast, TASK announced reliable, 160-round safety guard, assumed 144 Mbps shared Rady model. Validated each original native BID/AWARD sender Byte formula, N-1 AWARD broadcast receiver opportunities, task announcement 16+32·T record packets, source sender SEND/Bytes, receiver loss bounds, nonempty paid-stage model clock integrality and stop/certification consistency. Recalculated all 20 official summary rows independently, no discrepancies.

**Frozen E9I/E9J/E9K controls:** User E9L manifest pins the previously source-attested original ZIP SHA256s; every E9L per-case row includes the corresponding original baseline values and matched N/seed. All **20 baseline mean time and sender Byte values** match the previously Git-published E9K 20-point verification within rounding. The original E9I/E9J/E9K ZIP bytes were **not included in this new upload and therefore were not independently re-hashed anew in this turn**. This report does not claim otherwise, and no frozen algorithm was re-executed.

### Results — completion versus cost and communication

New E9L Price Auction: **1,867/2,000** independently locally certified and observer-full; **133/2,000** stopped at the 160-round guard. Global observer had a complete assignment in **1,880/2,000**: exactly 13 observer-complete cases lacked all needed physical local AWARD evidence. E9L starts to fail full local proof at N45 (98/100); at N100 **78/100 local certified** (Wilson 95% [68.93%,85.00%]), **79/100 observer-full**.

| 100 robots / 100 tasks | Voting E9I | Original CBAA E9J | Paid CBAA E9K | E9L distributed price auction |
|---|---:|---:|---:|---:|
| Complete by its **own** outcome contract | 100/100 | 100/100 | 100/100 | **78/100** |
| Mean modeled time, *all-seed stop* | 20.132 s | 13.647 s | 37.527 s | **135.828 s** (guard-censored) |
| Mean time *among successful only* | 20.132 s | 13.647 s | 37.527 s | **122.329 s** (78 only) |
| Mean attempted original sender bytes, all seeds | 255,498 B | 2,693,040 B | 4,074,431 B | **353,939 B** |
| Cost/Hungarian ratio | 1.362 (all 100) | 1.235 (all 100) | 1.235 (all 100) | **1.117** (only 78 successes) |

For a *proper common-success comparison*, on the **same 78 E9L-complete N100 Seeds** the reference mean Cost/Hungarian was Voting **1.366830**, original/paid CBAA **1.234752**, and E9L **1.117319**. Paired bootstrap (10,000 resamples seed20261012) gives E9L−Voting completed-time **+102.127625 s** CI95 [93.834787,110.483371] s and E9L−original CBAA **+108.688329 s** CI95 [100.544035,116.921291] s. E9L−Voting Cost ratio **−0.249511** CI95 [−0.266820,−0.232396], and E9L−CBAA Cost ratio **−0.117433** CI95 [−0.131696,−0.104087]. This source supports **better cost quality conditional on success but worse time and lower full local-proof completion**, not universal auction superiority.

### Research boundary

E9L is a distinct **Bertsekas-style epsilon task-home price auction network variant**, not original CBBA or a claim the cited original paper prescribed these packets. E9L still uses a simulator-level **unpaid global aggregation of local AWARD evidence**, not Voting reliable Commit or paid distributed final ACK. E9K paid two-stage local receipts also do not constitute common knowledge. The assumed shared 144Mbps model and Rady industrial ROS delay samples do not establish actual Wi-Fi 802.11 MAC/ARQ/collisions or RF implementation cost. E9L's small 28B packets have far less sender payload than original large CBAA vectors but at N100 have **38.53% more bytes than Voting** and a high sender SEND count (mean 12,527.68). E9L epsilon10.0 was selected at design-stage using limited synthetic seed0 exploration, not independently optimized; do not tune epsilon retrospectively on these formal Seeds while still calling it a frozen benchmark. The 22 failed N100 seeds are never assigned fictitious successful time/cost.

**Figures and data:** [20-point original-source-derived CSV](docs/figures/e9l_price/formal/plot_source_20point_rounded.csv) · [figure 1: four-method time/Bytes](docs/figures/e9l_price/formal/primary_four_method_time_and_sender_bytes.svg) · [figure 2: success/paired quality](docs/figures/e9l_price/formal/primary_e9l_completion_and_quality.svg) · [provenance/limitations manifest](docs/figures/e9l_price/formal/source_manifest.json). Original 2,000-row E9L user ZIP remains user-held as immutable raw; publication does not overwrite it.

**Next distinct benchmark:** true Choi/Brunet/How multi-task CBBA requires more tasks than robots, bundle capacity >1 and path-dependent marginal scoring, a **separate multi-task scenario/canonical change** rather than forcing the current N=T capacity1 results into CBBA. No CI or fresh simulation was started by this publication.

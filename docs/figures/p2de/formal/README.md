# Publication evidence — P2D + P2E, 100 paired seeds

These are **derived publication displays**, not additional robot simulations or replacements for original raw experiments. Figure 1 compares Proposed Single-Round with one-shot Centralized; Figure 2 compares Proposed Multi-Round, CBAA, CBBA, and includes Centralized as a one-shot reference. All 10 packet-loss points use seeds 0..99, 100 robots, 100 tasks, and capacity 1.

- P2D native Centralized original ZIP SHA256: `f88fd53335caf2076f4301168313ca2d25b88de604ed0a8cc0aee4082e8765df`; P2D source commit `7271c11f8d74858c6066e6fca00a97643a0317dc`.
- P2E original proposed single/multi ZIP SHA256: `0f85171a1aed84eb633a48ac8040b4312d10e9f6f5ef854948975bdd896edf74`; P2E source commit `7271c11f8d74858c6066e6fca00a97643a0317dc`.
- Historical CBAA/CBBA original P2 ZIP SHA256: `1d08a167308b9368ee2a764737066223ac041a5bd6508621c7b6cd0320036bb9`; executed source commit `f514cfa3613e7b0bad5c739d136b09fea8c3f92c`. The uploaded P2D ZIP reuses these original verified rows; this publication does not claim to rerun them.
- The P2D original P2-C Proposed (Multi-Round) result equals P2E Proposed Multi-Round for all 1,000 paired cases in the independently checked native-success, bytes, stop, assignment and distance fields. This avoids double counting: **five methods × 1,000 cases = 5,000 unique method-seed-loss cells**, though the two source CSVs have 6,000 rows including 1,000 matched duplicate Proposed cases.
- Independent P2D+P2E validation previously reported 73,463 assertions with 0 errors. Original raw archives, not this rounded 50-row source CSV, are the experiment evidence.

## Figure column contract

`verified_50point_summary.csv` contains each method/packet-loss group with 100 paired trials. Native success is success at the method's native terminal endpoint; these endpoints are **not identical guarantees**. Sender payload is all actual attempted application sender bytes divided by 1,000, **including dropped receiver deliveries**. Native stop is modeled seconds over **all 100 seeds**, including unsuccessful stops; not success-only latency or real deployed Wi-Fi. Cost increase (%) is the mean over successfully completed trials of `100 * (actual full assignment cost / offline complete-information global min-pair Greedy cost for the SAME seed - 1)`. The plot baseline is at **0%**, not at each method's independent PL0 cost. A negative cost increase is possible (Greedy is not globally optimal). When `cost_success_n=0`, cost is **blank**, not 0. For single-round PL10, quality uses n=1, not 100.

**Network limits:** Cost/Vote independent receiver loss, reliable TASK/Score/Commit by model; original CBAA/CBBA native stop/guard conditions differ from Proposed and Centralized. Centralized sends remote Cost only once and has no redecision. Proposed Multi-Round repeats **new decision epochs**, not the original Cost/Vote packet. Latencies combine source Rady app traces with a hypothetical shared 144 Mbps service, not measured MAC/PHY RF behavior.

The previous [P2-C four-method plot](../../p2c/formal/p2c_packet_loss_four_panel.svg) and [original audit](../../../P2C_FORMAL_100SEED.md) remain available for historical verification and Price Auction exploration, but are not the current README's primary plots.

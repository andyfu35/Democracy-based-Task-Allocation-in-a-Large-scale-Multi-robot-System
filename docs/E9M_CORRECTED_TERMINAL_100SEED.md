# E9M corrected 25R / 100T / capacity4 / loss30 — terminal-only audit (2026-10-13)

**Status:** USER TERMINAL LOG (200 result lines), **not** verified raw original ZIP. Preserve this status until the original `per_seed_e9m.csv`, `summary_e9m.csv`, and `manifest.json` ZIP are received and verified. Do not publish as independently verified formal source nor substitute the terminal-derived CSV for route/packet audit.

- Executed source: `7e857fd232c9459d0777cf130bc36766467e1ff0` (Vote target-unicast and free local ballots correction).
- Source pasted terminal log SHA256: `e634d00290df25296c69a2c474417b9b7e31ecfc68d87d2049b81126342ef3fa`.
- User reported root: `results/e9m_fixed_25r100t_loss30_100seed_20261013_084946`.
- Conditions: 25 robots, 100 tasks, capacity4, 100 independent scenario Seeds 0..99, pCost/Vote/CBBA consensus=.30, 160 CBBA guard, 100×100m, 1m/s, hypothetical 144 Mbps + Rady residual.
- Terminal records: exactly 100 unique rows per method/Seeds 0..99; 100/100 success and 100/100 coverage for both, zero printed failures. Original scores/routes/ledger data **not present** in pasted Terminal log.

| Terminal-derived all-seed metric | Voting Multi-task | CBBA |
|---|---:|---:|
| Success | 100/100 | 100/100 |
| Mean modeled allocation / observer-stop seconds | 63.022630 | 6.878180 |
| Min / max seconds | 53.602 / 72.394 | 3.898 / 12.740 |
| Mean sender application Bytes | 116,827.40 | 1,006,873.34 |
| Mean rounds | 100.00 | 16.81 |
| Max rounds | 100 | 28 |

Derived paired 100-seed mean Voting − CBBA time: +56.144450s; all 100 Seeds Voting's reported modeled allocation time was greater than CBBA. Ratio of means: Voting/CBBA time = 9.16269; CBBA/Voting sender Bytes = 8.61847. These are **modeled protocol-specific stop/Commit endpoints**, not equal final-agreement guarantees, PHY or real robot timing.

**Evidence:** [200 terminal-only derived rows](figures/e9m_multitask/terminal_corrected_v1_100seed.csv) · [summary with source SHA](figures/e9m_multitask/terminal_corrected_v1_summary.json). Derived rows retain only seed, method, success, coverage, rounds, elapsed seconds, sender Bytes and printed failure; these cannot prove path quality, physical per-message accounting, native manifest SHA or original CSV completeness. Old source `f347e26` is superseded and must remain separate.

**Next experiment:** E9N same-workload capacity1 native comparison. Do not reuse E9M capacity4 times as capacity1 competitive ranking. The original E9I/J/L N=T archived results may be displayed alongside new E9N native experiments only with exact scenario/protocol caveats and honest original-source provenance.

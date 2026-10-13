# Research Closure Plan — freeze the completed A–D experiments

**Status 2026-10-13: proposed limited follow-up scope; NOT new formal preregistration and NOT new completed evidence.** The accepted original-source studies shown in [README A–D](../README.md) remain valid **under their own model and endpoint contracts**. This plan identifies only the remaining gaps for a defensible cross-method statement. It does not silently revise earlier experiments, method packet formats or reward definitions.

## Accepted / frozen (do not rerun)

| Scientific question | Status | Frozen evidence |
|---|---|---|
| A. Controlled assignment correctness | Closed for zero-loss correctness and trace-bootstrap agreement overhead | 500 original correctness and 2,000 trace-bootstrap agreement records |
| B. Packet-loss native completion / Bytes | Closed **under synthetic timing/native endpoints** | 10,400 formal Voting/CBAA executions across 52 probabilities |
| C. Deadline reduction in Rady-based modeled setting | Closed for **modeled time only** | 100 Seeds at each N, original 30% Cost/30% Vote; separate zero-loss radio sensitivity |
| D. Algorithm-native C1/C4 behaviors | Original observations accepted, **comparative fairness claims remain limited** | 5-series common C1 chart, source verified 4,000 new E9N cases plus 6,000 historical; 25R/100T C4 source-verified 200 E9M cases |

## Priority 1 — one final matched five-method evaluation cell

**Failure mode to eliminate:** a five-method chart currently juxtaposes archived sources/commits, different allocation utility metrics and **different finalization conditions**. We can report their native numbers descriptively, but not call the ranking fully protocol-fair.

**Minimal proposed experiment, to preregister before code change:**

- N=T ∈ {25, 50, 100}; capacity C=1; 100 paired Seeds (0–99) each; Cost/real method packet receiver loss p=0.30; 100m geometry; same robot/task positions and common physical channel configuration.
- **Exactly five original native allocators**: Voting, original CBAA, Distributed Price Auction, Voting Multi-task C1, original CBBA C1. No Paid CBAA. Do not insert an artificial new finalization wrapper or alter a comparator's state machine.
- **One common read-only external evaluation event**: first globally feasible unique assignment observed **after each originally incurred native message phase**; this is an evaluation timestamp, **not** a distributed stopping protocol and it contributes **no hidden action or stop decision** to the robots. In the same row, independently report method-native local proof/paid Commit/observer stop and guard censorship; retain all attempted Bytes/SENDs whether or not the algorithm succeeds. If true first-feasible event cannot be observed without adding privileged information to the method itself, record its absence rather than inventing a timestamp.
- Common independently recomputed Euclidean **sum of robot-task distances** and Hungarian assignment optimum/gap for **successful common Seeds**; failed/incomplete cases remain in the primary full 100-Seed denominator and cannot be silently dropped. Compare discounted utility only *within* the implementations that genuinely use it.
- First verify one deterministic source/config SHA and small smoke, then 3 N ×100 Seeds ×5 native methods = **1,500 algorithm executions**, complete per-Seed original data and paired CIs. Do not commit to a full 20-size rerun unless this bounded experiment fails to answer the paper's principal fairness question.

**Acceptance gate:** (a) identical original scene IDs; (b) all five exact original methods preserved; (c) common externally observed event never drives runtime; (d) per-method local/payed terminal event described separately, with failures/censors; (e) per-Seed unified Euclidean/Hungarian quality and packet ledgers auditable; (f) one combined comparison figure on only common metrics. This closes the **fairness-of-measurement** question, not equal native distributed termination: claiming the latter would require an explicit separate protocol paper/experiment.

## Priority 2 — external validation of the radio-time model (claim-dependent)

**Issue:** Rady supplies recorded ROS application-level delay samples but shared 144Mbps scheduling/ACK/retries/airtime are hypothetical, particularly with native unicast versus broadcast and CBBA snapshot fragmentation.

**Proposed small validation:** use a packet-level 802.11 simulator (with identified parameters) **or** real two-/few-host controlled delivery traces, choosing 5/10/25 logical-agent packet schedules. Compare model time and counted application SEND/Bytes against packet-level service, retries, delivery and distribution of delays under observed/loss-injected 30%. Keep ACK and packet loss semantics explicit and do not retroactively rescale original published model outputs.

**Acceptance:** per-frame application payload identity, unicast/broadcast classification, latency distribution discrepancy and systematic difference reported, without claiming this emulates 100 physical robot RF nodes. **Needed before claiming real Wi-Fi communication time**, otherwise retain the exact current *modeled-time-only* language and STOP.

## Optional only if the manuscript claims multi-task scalability

The already accepted 25R/100T/C4 pair is one formal multi-task point. A defensible *multi-task scaling* claim would require **one second prespecified capacity-four scale** (example 50R/200T, 100 paired Seeds, 30% loss, same native two algorithms). This is **not mandatory** for a single-cell multi-task feasibility claim and should be deferred until the paper's contribution sentence is fixed.

## Explicit stop list — do NOT fill just because old IDs exist

Do not automatically rerun the provisional single-round Vote audit, the packet-size control, exploratory Cost-source repetitions, abandoned larger deadline factorial, old E3–E7 pilots or the team's Paid CBAA as an official literature comparator. Preserve their raw identities in [the internal study index](EXPERIMENT_LEGACY_INDEX.md). If the manuscript does not require a claim they would uniquely support, leave them archived.

**No CI, no automatic new experiment execution, and no production algorithm behavior changes are authorized by this plan.** Before Priority 1 changes code, the engineering protocol applies: AGENTS → AI_CHANGE_PROTOCOL → CHANGE_CONTINUITY → canonical spec → actual owner function, with one concern/owner/function/diagnostic and same-commit continuity.

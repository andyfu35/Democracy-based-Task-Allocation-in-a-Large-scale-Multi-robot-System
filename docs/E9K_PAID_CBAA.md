# E9K — Original CBAA with paid per-robot READY / COMMIT evidence

**Current status:** E9K user-run **2,000-case 100-seed paired formal evidence has been independently source-verified**. Original Git executable source `715dfa6c262b7081c241b54a7bddec16354990a3`. Formal numerical results and caveats in [E9K formal evidence](E9K_FORMAL_100SEED.md). Tests are provided for local use; an independent full automated unit-test run was not conducted in this evidence-publishing turn. This is a better *packet-accounted simulation*, not a real 802.11ax/ns-3 or radio-hardware experiment. No new CI runs are required. Use Mac locally.

## Question and protocol

Original E9J CBAA reports the time at which the simulator observes all local convergence flags. This optimistic shared stop is **not paid**. E9K leaves the original CBAA local Auction + Max-Consensus rule unchanged, adds an **opt-in** paid-termination mode in its true owner, and charges actual additional control SENDs.

At each original CBAA iteration, each agent first locally checks its own native proof based on **physically delivered** Bid/Winner messages. When locally ready, it broadcasts a 48-byte `cbaa_paid_ready` packet (16 B application header + 32 B SHA256 common Bid/Winner vector digest). Only physically delivered, on-time, matching-digest READY from each robot count in that receiver's local ledger. An agent may broadcast its own 48-byte `cbaa_paid_commit` only when its local READY inbox contains all N identities, including itself. Each robot's local finalization flag requires all N matching COMMIT identities *in addition to* its all-N READY proof. Neither the receiver's READY nor its COMMIT can be granted by the simulator's global observer. Real packet loss, lateness, full attempted sender bytes, retries at the **next native consensus iteration**, and distinct control windows are recorded.

This is a **separately labeled engineering extension**, not an original 2009 CBAA paper claim. Every node keeps participating in native CBAA and sending control packets until the simulated experiment observes every node's independent local complete ledger or the original 160-iteration safety guard. The simulator's final stop still does not establish *common knowledge* that everybody knows everybody has stopped; there is no authenticated message, complete RF/MAC/ARQ, or actual terminal ACK broadcast. Record this as an explicit remaining gap rather than declaring equivalence to Voting's reliable final Commit.

Fixed primary `N=T=5,10,...,100`, 100 original paired seeds each N. E9I Voting Cost30%, Vote30% and real Commit are **frozen**; E9J original CBAA Bid30% optimistic-stop ZIP is **frozen**. E9K runs only additional CBAA+paid:
`pBid=pReady=pCommit=0.30`; reliable paid TASK announcement; same original E9J pinned Rady delay profile and **assumed** 144 Mbps shared-medium proxy. Each native Bid phase and each nonempty READY/COMMIT wave is charged its declared conservative full-vector E9J phase timeout (independently). There is **no free control wave**. Control packet phase timeout equals native Bid phase timeout by frozen design, which may be conservative and is **not an independently measured deadline**.

Every *successful* N-agent two-phase certificate necessarily emits at least N READY and N COMMIT SENDs, i.e. at least `96N` B of paid control application traffic and at least `2N` SENDs even with zero packet loss; at N100, lower bound 9,600 B and 200 SENDs. **These are protocol accounting bounds, not new measured E9K results**. Additional consensus iterations and control retries can exceed this considerably.

## Local commands on Mac (no CI)

Run from the root of `Democracy-based-Task-Allocation-in-a-Large-scale-Multi-robot-System`:

```bash
git fetch origin experiment/e9k-paid-cbaa-finalization
git switch experiment/e9k-paid-cbaa-finalization
git pull --ff-only

python3 -m pip install -r requirements.txt
python3 -m unittest discover -s tests -p 'test_cbaa.py' -v
python3 -m unittest discover -s tests -p 'test_e9j_cbaa_vs_e9i.py' -v
python3 -m unittest discover -s tests -p 'test_e9k_*.py' -v
```

One unpaired local smoke first:

```bash
python3 -m experiments.run_e9k_paid_cbaa \
  --sizes 5,10,20 --seeds 3 --cbaa-safety-rounds 160 \
  --allow-unpaired-smoke \
  --output-root "results/e9k_unpaired_smoke_$(date +%Y%m%d_%H%M%S)"
```

For **formal** native CBAA + paid READY/COMMIT and frozen original-source E9J/E9I pair, ensure these *unmodified* original ZIP files are in Downloads:

```bash
export E9I_ZIP="$HOME/Downloads/e9i_cost30_formal_100seed.zip"
export E9J_ZIP="$HOME/Downloads/e9j_cbaa_paired_formal_100seed.zip"
shasum -a 256 "$E9I_ZIP" "$E9J_ZIP"

set -o pipefail
export E9K_ROOT="results/e9k_paid_formal_$(date +%Y%m%d_%H%M%S)"
python3 -m experiments.run_e9k_paid_cbaa \
  --sizes 5,10,15,20,25,30,35,40,45,50,55,60,65,70,75,80,85,90,95,100 \
  --seeds 100 --cbaa-safety-rounds 160 \
  --e9i-zip "$E9I_ZIP" --e9j-zip "$E9J_ZIP" \
  --output-root "$E9K_ROOT" \
  2>&1 | tee "$E9K_ROOT.log"
zip -r "$HOME/Downloads/e9k_paid_cbaa_formal_100seed.zip" \
  "$E9K_ROOT" "$E9K_ROOT.log"
```

The executable accepts a user original E9J ZIP **only** when SHA256 matches
`106fc14aa9088edf980a744bf9e129c516ce8cabf9c23322baa76be9b33c82bb`; E9I frozen ZIP SHA256 must match
`5d275bebd8d6f985e8eef1bbba9a0947991cd71660c1cc49817619e6bc276ee5`.
Any changed archive is rejected; no silent baseline regeneration. A formal missing-archive run is rejected. Unpaired smoke is permitted only `N<=20`, `seeds<=3` and explicitly marked as not paired.

Outputs: `per_seed_e9k.csv`, `summary_e9k.csv`, `manifest.json`, a growing `.partial.csv` during execution. New physical packet counters are kept separate for native Bid, READY and COMMIT; failed/guard-censored cases remain in the all-seed summary. Compare only **paired successful cases** for successful time, and separately report all-seed stop time and completion fractions. Baseline original source CSVs are **not rewritten**.

**Next validation gates:** local unit-test logs remain separate from this archived 100-seed result; next predeclared experiment varies **paid control timeout only**, with original frozen E9I/E9J/E9K intact. Then pursue independent ns-3/MAC/physical radio validation. Future separate E9L: paid global terminal ACK and calibrated ns-3/MAC/field radio effects.

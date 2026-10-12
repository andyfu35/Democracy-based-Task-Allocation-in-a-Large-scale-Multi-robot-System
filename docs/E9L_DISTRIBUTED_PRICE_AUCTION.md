# E9L: Bertsekas-style decentralized price auction vs immutable E9I/E9J/E9K

**Status: complete user-run 20×100 formal E9L original source is now independently verified;** see [full 100-seed report](E9L_FORMAL_100SEED.md). This guide preserves original reproducibility commands and predeclared epsilon10.0, not a new requirement to repeat old controls.
No CI or background execution is required. User Mac runs the actual source.

> **Official algorithm comparator rule (2026-10-12):** compare **Voting (E9I), original CBAA (E9J), and Distributed Price Auction (E9L)** only. The E9K paid-stop modification is our own engineering protocol study, **not another literature algorithm**. The historical user-executed E9L CLI and SHA-pinned raw manifest happen to require E9K as an old archival source-integrity input; the commands below are preserved **only for reproducibility**, and E9K's numbers must not appear in official benchmark tables, charts, or rankings. Future benchmark implementations should accept only the needed published algorithm baseline inputs, without altering or relabeling the frozen E9L original source SHA.

## Why this comparator first?

The 2009 Choi–Brunet–How work defines CBBA as a **multi-task
bundle** extension to CBAA; constraining original CBBA to one task would
remove the defining multi-task dimension. E9L first supplies a genuinely
different 1:1 method which reuses the exact N=T=5..100 E9I/E9J/E9K evidence.

- Research basis: Dimitri P. Bertsekas, *The Auction Algorithm: A
  Distributed Relaxation Method for the Assignment Problem* (1988),
  DOI https://doi.org/10.1007/BF02186476; standard positive epsilon
  best-versus-second-best **price increment**.
- E9L is our **per-task-home, packet-loss-aware task assignment
  implementation**, not the paper's prescribed radio/wire protocol or
  an original CBBA implementation.
- Each robot knows its **own** Euclidean cost row. Task home j is robot j
  because this benchmark has N=T and 1 task maximum per robot.
  Each home uses only delivered BID offers for its own task.
- Every remote BID is a real 28 B native unicast; every task-home AWARD
  is a real 28 B broadcast **each natural auction iteration**, including
  repeat announcements for packets previously dropped. A bidder sending
  to its own task home sends **zero** physical loopback packets.
  The packet format is precisely Python struct "<4sIIIdI" (magic,
  round, task, bidder/winner, float64 price, task version), not an
  assumed fixed-size global bid vector.
- Bid/award original receiver Bernoulli loss both 30%; Task
  announcements reliable and charged. Fixed epsilon = **10.0 m cost
  units** (a design-stage setting informed by exploratory synthetic
  smoke; NOT claimed optimal or hyperparameter-free).
- A bidder never bids on a second task while its previous price bid
  lacks a physical, version-increasing owner AWARD receipt. Local
  readiness requires observing a nonconflicting full 1:1 assignment,
  no pending bid and fresh announcements after its last own offer.
- Simulator stops after **all independently local AWARD certificates**
  or safety guard 160; this is an **optimistic unpaid global stop**, not
  a paid distributed acknowledgment or the reliable Voting Commit.
  Never compare endpoint labels as if those success guarantees were identical.

## Historical run inputs and official algorithm comparators (original source unchanged)

| Method | Actual source | Original loss / endpoint |
|---|---|---|
| Voting guarded received plurality | Frozen E9I original 100-seed ZIP | Cost30%, Vote30%, actual reliable Commit |
| Native original CBAA | Frozen E9J 100-seed ZIP | Bid/Winner30%, optimistic local certification and observer |
| E9K (internal, **not a comparator**) | Historical source ZIP for this frozen E9L CLI's provenance only | Our own modified paid-stop engineering validation, excluded from ranking |
| **E9L distributed price auction** | **New source run** | BID30%, AWARD30%, optimistic per-node local all-task proof |

The same independent Hungarian oracle is used **only for external final
evaluation**, never for an agent's bidding. The Rady-sampled ROS
application delay plus the **hypothetical** E9G 144 Mbps serialized
medium is identical in model family, with an independently **packet-size
aware 28B full-stage window** for each nonempty BID/AWARD wave.
This is not ns-3, measured real AP contention or collision/ARQ.

## Run on Mac Terminal (no CI)

In the repository root:

\`\`\`bash
git fetch origin experiment/e9l-distributed-price-auction
git switch experiment/e9l-distributed-price-auction
git pull --ff-only

python3 -m pip install -r requirements.txt
python3 -m compileall -q democracy_mrta experiments tests
python3 -m unittest discover -s tests -p 'test_e9l_*.py' -v
python3 -m unittest discover -s tests -p 'test_cbaa.py' -v
python3 -m unittest discover -s tests -p 'test_e9j_cbaa_vs_e9i.py' -v
python3 -m unittest discover -s tests -p 'test_e9k_*.py' -v
\`\`\`

Small local unpaired smoke, **not** the formal four-way result:

\`\`\`bash
python3 -m experiments.run_e9l_price_auction \
  --sizes 5,10,20 --seeds 3 --safety-rounds 160 \
  --allow-unpaired-smoke \
  --output-root "results/e9l_smoke_$(date +%Y%m%d_%H%M%S)"
\`\`\`

Full 20 sizes × 100 seed **only after local tests/smoke** (original
ZIP names are the ones previously produced in this project):

\`\`\`bash
export E9I_ZIP="$HOME/Downloads/e9i_cost30_formal_100seed.zip"
export E9J_ZIP="$HOME/Downloads/e9j_cbaa_paired_formal_100seed.zip"
export E9K_ZIP="$HOME/Downloads/e9k_paid_cbaa_formal_100seed.zip"

shasum -a 256 "$E9I_ZIP" "$E9J_ZIP" "$E9K_ZIP"

set -o pipefail
export E9L_ROOT="results/e9l_price_auction_formal_$(date +%Y%m%d_%H%M%S)"
python3 -m experiments.run_e9l_price_auction \
  --sizes 5,10,15,20,25,30,35,40,45,50,55,60,65,70,75,80,85,90,95,100 \
  --seeds 100 --safety-rounds 160 \
  --e9i-zip "$E9I_ZIP" \
  --e9j-zip "$E9J_ZIP" \
  --e9k-zip "$E9K_ZIP" \
  --output-root "$E9L_ROOT" \
  2>&1 | tee "$E9L_ROOT.log"

zip -r "$HOME/Downloads/e9l_price_auction_formal_100seed.zip" \
  "$E9L_ROOT" "$E9L_ROOT.log"
\`\`\`

**Pinned SHA256:**
E9I \`5d275bebd8d6f985e8eef1bbba9a0947991cd71660c1cc49817619e6bc276ee5\`,
E9J \`106fc14aa9088edf980a744bf9e129c516ce8cabf9c23322baa76be9b33c82bb\`,
E9K \`1495612c65a4fb40733af225b2121275e2b2309070695f2594c620079a6b8281\`.
Any different source ZIP fails explicitly; no source rerun/fallback.

Outputs: \`per_seed_e9l.csv\` (one row per N/seed), \`summary_e9l.csv\`,
\`manifest.json\` (Git SHA/config/timestamp/original source SHA and actual
E9L source SHA), plus a temporary partial CSV during execution.

**Evidence now accepted (2026-10-12):** The uploaded formal original ZIP passed SHA256, 2,000 unique keys and physical sender ledger plus per-size summary audits; 1,867/2,000 completed with 133 guard failures. The following remains the source audit contract for future replications: 2,000 unique keys, all physically
counted sends, no invented final Commit, per-seed task/price/cost
ledger, all-seed success denominators including guard failures, paired
time only for common-success seeds and separate censored stop times.
If E9L fails the guard often at N100, report its failure honestly;
do **not** tune epsilon or safety rounds after observing the formal
result and relabel it as a frozen benchmark.

## Later CBBA: separate multi-task benchmark

Original CBBA should be evaluated with tasks exceeding robots and
capacity>1, e.g. 25 robots/100 tasks, with path-dependent insertion and
true bundle consensus. The old N=T E9I/J/K source outcomes are not a
valid capacity>1 comparator. Do this as a separate protocol and
scenario-owner change; never label E9L as original CBBA.

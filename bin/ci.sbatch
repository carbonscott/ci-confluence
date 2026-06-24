#!/bin/bash
#
# ci.sbatch -- one-shot batch version of the Confluence-snippet CI on milano.
#
# Submit from the workspace root on the login node:
#     sbatch bin/ci.sbatch
# Output (table + summaries) lands in var/reports/ci-<jobid>.out.
#
# Runs tier 1 (syntax/lint) then tier 2 (psana2 import-smoke, sourcing psconda),
# and exits NONZERO iff any tier reported a FAILED snippet. Tier-2 failures do not
# short-circuit the summary; the final exit reflects both tiers.
#
# Whole node = 120 usable cores (--exclusive --mem=0); do NOT request 128.
#
#SBATCH --partition=milano
#SBATCH --account=lcls:prjdat21
#SBATCH --exclusive
#SBATCH --mem=0
#SBATCH --time=00:30:00
#SBATCH --job-name=ci-confluence
#SBATCH --output=var/reports/ci-%j.out

set -eo pipefail   # NOT -u: psconda's setup script is not set -u clean.

PSCONDA="/sdf/group/lcls/ds/ana/sw/conda2/manage/bin/psconda.sh"

# Resolve the workspace root. Prefer the submit directory (sbatch sets
# SLURM_SUBMIT_DIR); fall back to the script's parent.
if [ -n "${SLURM_SUBMIT_DIR:-}" ]; then
  WS="$SLURM_SUBMIT_DIR"
else
  WS="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
fi
cd "$WS"
mkdir -p var/reports

echo "=== ci.sbatch on $(hostname) (job ${SLURM_JOB_ID:-?}) workspace=$WS ==="

# ---- Tier 1: syntax/lint (no psana env needed) ----------------------------
echo
echo "=== TIER 1 (syntax/lint) ==="
set +e
python3 bin/run_checks.py --tier 1 --json var/reports/tier1-milano.json
TIER1_RC=$?
set -e
echo ">> tier 1 exit: $TIER1_RC"

# ---- Tier 2: psana2 import-smoke / execute --------------------------------
echo
echo "=== TIER 2 (psana2 import-smoke) ==="
set +e
( set -eo pipefail; source "$PSCONDA"; python bin/run_checks.py --tier 2 --json var/reports/tier2-milano.json )
TIER2_RC=$?
set -e
echo ">> tier 2 exit: $TIER2_RC"

# ---- Overall verdict ------------------------------------------------------
echo
echo "=== OVERALL ==="
OVERALL=0
for rc in "$TIER1_RC" "$TIER2_RC"; do
  [ "$rc" -ne 0 ] && OVERALL=1
done
if [ "$OVERALL" -eq 0 ]; then echo "OVERALL: PASS"; else echo "OVERALL: FAIL"; fi
exit "$OVERALL"

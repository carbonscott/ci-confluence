#!/bin/bash
#
# ci.sh -- re-runnable driver for the Confluence-snippet CI on a milano compute node.
#
# Runs bin/run_checks.py (the stable check runner) on a real milano node via Slurm:
#   - Tier 1: syntax/lint, no psana env (still run on the node for consistency).
#   - Tier 2: psana2 import-smoke / execute, sourcing psconda on the node.
#
# It creates a persistent --no-shell allocation, drives each tier with `srun
# --jobid=<id>`, prints a combined summary read back from reports/*.json, and
# releases the allocation (unless told to keep / reuse it). Exit is nonzero iff
# any tier had a FAILED snippet (CI semantics; warnings/skips never fail).
#
# Run from the workspace root on the login node (sdfiana025):
#   bash bin/ci.sh [--tier 1|2|all] [--time HH:MM:SS] [--jobid N] [--keep]
#
set -euo pipefail

# ---------------------------------------------------------------------------
# Config (verified Slurm facts for this site -- honor exactly)
# ---------------------------------------------------------------------------
PARTITION="milano"
ACCOUNT="lcls:prjdat21"
JOBNAME="ci-confluence"
PSCONDA="/sdf/group/lcls/ds/ana/sw/conda2/manage/bin/psconda.sh"
FULLNODE_CPUS=120          # whole node = 120 usable cores (NOT 128)

# ---------------------------------------------------------------------------
# Defaults / arg parsing
# ---------------------------------------------------------------------------
TIER="all"
WALLTIME="00:30:00"
REUSE_JID=""
KEEP=0

usage() {
  cat <<'EOF'
Usage: bash bin/ci.sh [options]

Run the Confluence-snippet CI on a milano compute node via Slurm.

Options:
  --tier 1|2|all   Which tier(s) to run (default: all).
                   1 = syntax/lint; 2 = psana2 import-smoke/execute.
  --time HH:MM:SS  Allocation wall time (default: 00:30:00).
  --jobid N        Reuse an existing allocation N instead of creating one.
                   (An allocation you pass in is never cancelled at the end.)
  --keep           Do not scancel the allocation this script created.
  --help           Show this help and exit.

Exit status: nonzero iff any tier reported a FAILED snippet.
EOF
}

while [ $# -gt 0 ]; do
  case "$1" in
    --tier)   TIER="${2:-}"; shift 2 ;;
    --time)   WALLTIME="${2:-}"; shift 2 ;;
    --jobid)  REUSE_JID="${2:-}"; shift 2 ;;
    --keep)   KEEP=1; shift ;;
    --help|-h) usage; exit 0 ;;
    *) echo "ci.sh: unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

case "$TIER" in
  1|2|all) ;;
  *) echo "ci.sh: --tier must be 1, 2, or all (got '$TIER')" >&2; exit 2 ;;
esac

# Resolve workspace root = directory containing this script's parent (bin/..).
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WS="$(cd "$SCRIPT_DIR/.." && pwd)"

if [ ! -f "$WS/bin/run_checks.py" ]; then
  echo "ci.sh: cannot find $WS/bin/run_checks.py -- run from the workspace root." >&2
  exit 2
fi
if [ ! -f "$WS/manifest.json" ]; then
  echo "ci.sh: cannot find $WS/manifest.json" >&2
  exit 2
fi
mkdir -p "$WS/reports"

# ---------------------------------------------------------------------------
# Allocation lifecycle
# ---------------------------------------------------------------------------
JID=""
CREATED_ALLOC=0   # 1 only if WE created the allocation (so we own teardown)

cleanup() {
  # Cancel only an allocation we created, and only if not asked to keep it.
  if [ "$CREATED_ALLOC" = "1" ] && [ "$KEEP" = "0" ] && [ -n "$JID" ]; then
    echo ">> Releasing allocation $JID (scancel)"
    scancel "$JID" 2>/dev/null || true
  fi
}
trap cleanup EXIT

if [ -n "$REUSE_JID" ]; then
  JID="$REUSE_JID"
  echo ">> Reusing existing allocation $JID (will not be cancelled by this run)."
else
  echo ">> Requesting milano allocation (partition=$PARTITION account=$ACCOUNT time=$WALLTIME, whole node)..."
  # salloc --no-shell persists with no shell; the granted job id appears on stderr
  # as 'salloc: Granted job allocation <N>'. Capture both streams to parse it.
  ALLOC_OUT="$(salloc --no-shell \
      --partition="$PARTITION" \
      --account="$ACCOUNT" \
      --exclusive --mem=0 \
      --time="$WALLTIME" \
      -J "$JOBNAME" 2>&1)" || {
    echo "ci.sh: salloc failed:" >&2
    echo "$ALLOC_OUT" >&2
    exit 1
  }
  echo "$ALLOC_OUT"
  JID="$(printf '%s\n' "$ALLOC_OUT" | grep -oE 'Granted job allocation [0-9]+' | grep -oE '[0-9]+' | head -1)"
  if [ -z "$JID" ]; then
    echo "ci.sh: could not parse a granted job id from salloc output -- aborting." >&2
    exit 1
  fi
  CREATED_ALLOC=1
  echo ">> Granted milano allocation: job $JID"
fi

# ---------------------------------------------------------------------------
# Confirm placement: a step must land on an sdfmilan* compute node.
# ---------------------------------------------------------------------------
echo ">> Confirming placement on a milano compute node..."
NODE="$(srun --jobid="$JID" --cpus-per-task="$FULLNODE_CPUS" --cpu-bind=none hostname 2>/dev/null | tail -1 | tr -d '[:space:]')"
if [ -z "$NODE" ]; then
  echo "ci.sh: srun returned no hostname for job $JID -- aborting." >&2
  exit 1
fi
case "$NODE" in
  sdfmilan*) echo ">> Running on milano compute node: $NODE (job $JID)" ;;
  *)
    echo "ci.sh: step did not land on a milano node (got '$NODE') -- aborting." >&2
    exit 1
    ;;
esac

# ---------------------------------------------------------------------------
# Run tiers
# ---------------------------------------------------------------------------
TIER1_RC="n/a"
TIER2_RC="n/a"
TIER1_JSON="var/reports/tier1-milano.json"
TIER2_JSON="var/reports/tier2-milano.json"

run_tier1=0
run_tier2=0
case "$TIER" in
  1)   run_tier1=1 ;;
  2)   run_tier2=1 ;;
  all) run_tier1=1; run_tier2=1 ;;
esac

if [ "$run_tier1" = "1" ]; then
  echo
  echo ">> ===== TIER 1 (syntax/lint) on $NODE ====="
  set +e
  srun --jobid="$JID" --cpus-per-task="$FULLNODE_CPUS" --cpu-bind=none \
    bash -lc "cd '$WS' && python3 bin/run_checks.py --tier 1 --json '$TIER1_JSON'"
  TIER1_RC=$?
  set -e
  echo ">> Tier 1 exit code: $TIER1_RC"
fi

if [ "$run_tier2" = "1" ]; then
  echo
  echo ">> ===== TIER 2 (psana2 import-smoke) on $NODE ====="
  # psconda is NOT set -u clean: wrapper uses `set -eo pipefail` WITHOUT -u.
  # Do not let a tier-2 FAIL abort the script before we print the summary.
  set +e
  srun --jobid="$JID" \
    bash -c "set -eo pipefail; source '$PSCONDA'; cd '$WS'; python bin/run_checks.py --tier 2 --json '$TIER2_JSON'"
  TIER2_RC=$?
  set -e
  echo ">> Tier 2 exit code: $TIER2_RC"
fi

# ---------------------------------------------------------------------------
# Combined summary (read back from the JSON reports)
# ---------------------------------------------------------------------------
echo
echo "============================================================"
echo " CI SUMMARY  (node=$NODE  job=$JID)"
echo "============================================================"

# Print one summary line per produced report via python3 (stdlib only).
print_summary() {
  # $1 = label, $2 = json path (relative to WS), $3 = run_checks exit code
  local label="$1" jpath="$2" rc="$3"
  python3 - "$label" "$WS/$jpath" "$rc" <<'PY'
import json, os, sys
label, path, rc = sys.argv[1], sys.argv[2], sys.argv[3]
if not os.path.exists(path):
    print("%-7s: (no report at %s; run_checks exit=%s)" % (label, path, rc))
    sys.exit(0)
try:
    with open(path) as fh:
        s = json.load(fh).get("summary", {})
except Exception as exc:
    print("%-7s: (unreadable report: %s)" % (label, exc))
    sys.exit(0)
verdict = "PASS" if s.get("failed", 0) == 0 else "FAIL"
print("%-7s: total=%d passed=%d failed=%d skipped=%d warnings=%d  exit=%s -> %s"
      % (label, s.get("total",0), s.get("passed",0), s.get("failed",0),
         s.get("skipped",0), s.get("warnings",0), rc, verdict))
PY
}

[ "$run_tier1" = "1" ] && print_summary "TIER 1" "$TIER1_JSON" "$TIER1_RC"
[ "$run_tier2" = "1" ] && print_summary "TIER 2" "$TIER2_JSON" "$TIER2_RC"

# ---------------------------------------------------------------------------
# Overall verdict + exit propagation.
# A tier "fails the build" if its run_checks exit code is 1 (a FAILED snippet).
# Exit code 2 (manifest/usage error) or any other nonzero also fails the build.
# ---------------------------------------------------------------------------
OVERALL_FAIL=0
for rc in "$TIER1_RC" "$TIER2_RC"; do
  case "$rc" in
    0|n/a) : ;;       # passed or not run -> fine
    *)     OVERALL_FAIL=1 ;;
  esac
done

if [ "$OVERALL_FAIL" = "0" ]; then
  echo "OVERALL: PASS"
else
  echo "OVERALL: FAIL"
fi
echo "============================================================"

# cleanup() runs on EXIT (scancel if we created the alloc and no --keep).
exit "$OVERALL_FAIL"

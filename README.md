# CI-Confluence — CI for psana Confluence code snippets

Continuous integration for the code examples documented on the LCLS-II **psana**
Confluence page (`pageId=267391733`) and its sub-pages. Confluence stays the
human-facing source of truth; this CI wraps around it to catch examples that
silently rot (typos, broken indentation, APIs that no longer import).

Workspace: `/sdf/data/lcls/ds/prj/prjcwang31/results/ci-confluence` (on S3DF, host `sdfiana025`).

---

## TL;DR — can we build CI on top of the confluence-doc database?

**Not on the DB's `content` column — it's a lossy markdown export.** The deployed
`lcls-docs.db` stores a pandoc-rendered markdown view: the psana page has **0
fenced code blocks**, Python indentation/newlines are gone, language hints are
glued to the first token (`pyfrom psana import ...`). Python is unrecoverable from it.

**But the confluence-doc _pipeline_ already has the faithful code and throws it away.**
`tools/confluence-doc/confluence_to_markdown.py` fetches Confluence **storage format**
(`body.storage`, which contains real `<ac:structured-macro ac:name="code">…<![CDATA[…]]>`
blocks with `language` tags) at line ~567, then destroys it at line ~576 by running it
through pandoc, whose HTML reader can't parse the `ac:` XML namespace.

So this CI extracts code from the **REST storage format** (faithful, byte-exact),
using the DB only as a **discovery index** (which pages exist, page IDs, hierarchy).
The storage-format parser (`parse_storage()` in `bin/extract.py`) is deliberately a
pure, side-effect-free function so the **same logic can later be dropped into the
confluence-doc pipeline** to persist a faithful `code_snippets` table — at which point
the DB *would* become a perfectly good offline CI substrate, fed by the existing
daily cron. That is the recommended Phase 2 (see below).

---

## What it does

```
bin/extract.py     DB discovery -> REST fetch (cached) -> parse <ac:code> macros
                   -> snippets/<page_id>/<NNN>.<ext>  +  manifest.json
bin/run_checks.py  read manifest -> tiered checks -> reports/*.json  (exit nonzero iff any FAIL)
bin/ci.sh          run the checks on a milano compute node via salloc/srun (re-runnable)
bin/ci.sbatch      one-shot sbatch equivalent
```

### Extraction (10 pages, 73 snippets)
Discovered the psana page + 9 descendants (2 grandchildren the original note missed),
fetched each via Bearer-auth REST (5 req/min limit, cached to `cache/storage/`), parsed
60+ code macros into **73 byte-faithful snippet files** (md5-verified identical to the
storage CDATA).

| Category | Count | Tier-1 check | Tier-2 check |
|----------|-------|--------------|--------------|
| `python-execute`      | 19 | `ast.parse` (+ruff warn) | import-smoke in psana2 |
| `shell-lint`          | 20 | `bash -n` (+shellcheck if present) | — |
| `python-import-smoke` |  6 | `ast.parse` (+ruff warn) | import-smoke in psana2 |
| `python-lint`         |  4 | `ast.parse` (+ruff warn) | — |
| `non-testable`        | 24 → 29 | skipped (prose / console transcripts / pseudocode) | — |

### Tiers
- **Tier 1** — syntax/lint. No psana env; runs anywhere. Python `ast.parse` (non-breaking
  spaces and uniform leading indentation are normalized in-memory and reported as
  *warnings*, not failures — only genuine syntax errors FAIL). Shell `bash -n`. `ruff`/
  `shellcheck` findings are warnings, never failures.
- **Tier 2** — import-smoke. Runs each python snippet's **import statements** under the
  psana2 conda env on a milano node, verifying the documented APIs still resolve. This is
  the real doc-rot signal.
- **Tier 3** — full execution under psana2 against fixture data (`/sdf/data/lcls/ds/prj/public01/xtc`).
  Wired but **opt-in** (noisy: needs data/MPI). `--tier 3`.

---

## Results

### Tier 1 (lint) — `total=73  passed=40  failed=4  skipped=29  warnings=15`
The **4 failures are genuine documentation bugs**, all verbatim in the source pages:

1. `for evt orun.events():` — missing `in` (Advanced psana Examples page).
2–4. `stextra_bits:(1<<64)-1` — `:` written where `=` belongs, in three copy-pasted
   `mask` calls on the **Area detector mask examples** page (`337080549`). Python reports
   these as "positional argument follows keyword argument"; the root cause is the `:` typo.

15 warnings flag snippets carrying non-breaking spaces or needing dedent (copy-paste
hazards, auto-fixable). 5 snippets were correctly reclassified to `non-testable`
(4 console-output transcripts mis-tagged as `bash`; 1 `<placeholder>` pseudocode).

### Tier 2 (import-smoke under psana2 on milano)
**22 / 24** python exec-category snippets (19 `python-execute` + 5 parseable
`python-import-smoke`) have **all their documented imports resolve cleanly** in the
current psana2 env (`lcls2_041726`, python 3.9) — **zero import failures**. Every
documented `psana` / `psmon` / `mpi4py` / `psana.detector.*` API still imports, including
`from psana.detector.mask import Mask, DTYPE_MASK`, `from psana.detector.UtilsMask import *`,
and `from psana.detector import Damage`. **No API drift detected.** The 2 not import-checked
are the genuine syntax-bug snippets above (skipped as "unparseable — see tier-1", not
double-counted). A full tier-2 run still surfaces those bugs via the tier-1 superset
behavior, so its line reads `passed=40 failed=2 skipped=31`.

Ran on milano node `sdfmilan242` (Slurm job `29760220`), exclusive whole node
(120 cores, 480 GB), allocation auto-released.

---

## How to re-run (maintainer)

From the workspace root on `sdfiana025`:

```bash
cd /sdf/data/lcls/ds/prj/prjcwang31/results/ci-confluence

# 1. (re)extract snippets from Confluence — uses cache unless --refresh
python3 bin/extract.py                 # add --refresh to re-hit REST (respects 5 req/min)

# 2. lint locally (no allocation needed)
python3 bin/run_checks.py --tier 1

# 3. full CI on a milano node (tier-1 + tier-2 import-smoke), auto-allocates + releases
bash bin/ci.sh                         # both tiers, exclusive milano node, account lcls:prjdat21
bash bin/ci.sh --tier 1 --time 00:20:00
bash bin/ci.sh --jobid <existing>      # reuse an allocation you already hold (won't cancel it)

# one-shot batch alternative
sbatch bin/ci.sbatch                   # output -> reports/ci-<jobid>.out
```

`ci.sh` exits nonzero whenever any snippet FAILs — correct CI semantics. Expect a
nonzero exit until the 4 documented bugs above are fixed in Confluence.

### Fast iterative-dev pattern (hold one allocation, reuse it)
```bash
JID=$(salloc --no-shell --partition=milano --account=lcls:prjdat21 \
      --exclusive --mem=0 --time=02:00:00 -J ci-dev 2>&1 | grep -oP 'allocation \K[0-9]+')
bash bin/ci.sh --jobid "$JID"          # run as many times as you like
scancel "$JID"                         # release when done
```

---

## Recommendation — Phase 2: make the DB a faithful CI substrate

The clean long-term shape (keeps Confluence as source of truth, gives offline CI):
patch `tools/confluence-doc/confluence_to_markdown.py` to call `parse_storage()` on the
`body.storage` it already fetches, and persist the faithful code into a new
`code_snippets` table (page_id, index, language, code, anchor) alongside the existing
markdown export. The daily cron then keeps code current automatically, and CI reads the
DB offline — no per-run REST calls, no token on the CI runner. This CI's extractor is
already structured so that one function moves into the pipeline unchanged.

## Limitations / notes
- REST is rate-limited to 5 req/min; `extract.py` caches storage XML so re-runs don't hit it.
- A Confluence token is read from the confluence-doc pipeline config (`CONFLUENCE_TOKEN_FILE`);
  any standalone CI runner needs that token provisioned (Phase 2 removes this need).
- `shellcheck` is not installed on the node, so shell lint is `bash -n` only.
- Tier-3 (execute against fixtures) is intentionally opt-in and not part of `--tier all`.
- Iter-1 research notes: `notes/iter1-db-extraction-findings.md`, `notes/iter1-slurm-recon.md`.
```

# CI-Confluence — CI for psana Confluence code snippets

Continuous integration for the code examples documented on the LCLS-II **psana**
Confluence page (`pageId=267391733`) and its sub-pages. Confluence stays the
human-facing source of truth; this CI wraps *around* it — extracting and mirroring
the documented code so it can catch examples that silently rot (typos, broken
indentation, APIs that no longer import). It does not replace Confluence.

Workspace: `/sdf/data/lcls/ds/prj/prjcwang31/results/ci-confluence` (on S3DF, host `sdfiana025`).

---

## How it works

```
bin/extract.py     DB discovery -> REST fetch (cached) -> parse <ac:code> macros
                   -> snippets/<page_id>/<NNN>.<ext>  +  manifest.json
bin/run_checks.py  read manifest -> tiered checks -> var/reports/*.json  (exit nonzero iff any FAIL)
bin/ci.sh          run the checks on a milano compute node via salloc/srun (re-runnable)
bin/ci.sbatch      one-shot sbatch equivalent
```

`extract.py` mirrors the Confluence code into `snippets/` + `manifest.json`;
`run_checks.py` reads that manifest and runs the tiered checks below.

## Prerequisites

- Access to an S3DF login node and the workspace above.
- **Normal runs need no token.** `extract.py` works fully OFFLINE from the warm
  REST cache in `var/cache/storage/`. A Confluence token
  (`CONFLUENCE_TOKEN_FILE`, from the confluence-doc pipeline config) is only
  needed if you ever pass `--refresh` to re-hit the REST API.
- Tier-2 / tier-3 checks need the **psana2 conda env** (psconda) on a **milano**
  Slurm node, account `lcls:prjdat21`. Tier 1 needs none of this.

## Quickstart

From the workspace root on `sdfiana025`:

```bash
cd /sdf/data/lcls/ds/prj/prjcwang31/results/ci-confluence

python3 bin/extract.py             # mirror snippets from Confluence (uses cache; add --refresh to re-hit REST)
python3 bin/run_checks.py --tier 1 # lint locally, no allocation needed
bash bin/ci.sh                     # full CI on a milano node (tier-1 + tier-2), auto-allocates + releases
```

`ci.sh` exits nonzero whenever any snippet FAILs — correct CI semantics
(see "Expected state" below for why it is currently red).

Gotchas:
- On a cold clone, `mkdir -p var/reports` before the first `sbatch bin/ci.sbatch`:
  Slurm opens its `--output` log before the script body runs. (`ci.sh`/`ci.sbatch`
  create the dir themselves otherwise.)
- `bash bin/ci.sh --jobid <existing>` reuses an allocation you already hold instead
  of allocating a fresh one (and won't cancel it).

## Tiers

- **Tier 1** — syntax/lint. No psana env; runs anywhere. Python via `ast.parse`
  (non-breaking spaces and uniform leading indentation are normalized in-memory
  and reported as *warnings*, not failures — only genuine syntax errors FAIL).
  Shell via `bash -n`. `ruff`/`shellcheck` findings are warnings, never failures.
- **Tier 2** — import-smoke. Runs each python snippet's **import statements** under
  the psana2 conda env on a milano node, verifying the documented APIs still
  resolve. **This is the real doc-rot signal.**
- **Tier 3** — full execution under psana2 against fixture data
  (`/sdf/data/lcls/ds/prj/public01/xtc`). Wired but **opt-in** (noisy: needs
  data/MPI). Run with `--tier 3`.

## Expected state — it's red on purpose

A red tier-1 run is **by design**. There are 4 genuine documentation bugs, all
verbatim in the source Confluence pages:

1. `for evt orun.events():` — missing `in` (Advanced psana Examples page).
2–4. Three `:`-for-`=` typos (`:` written where `=` belongs) in three copy-pasted
   `mask` calls on the Area detector mask examples page (`337080549`).

"Green" means no *new* rot has appeared. These known bugs are reported upstream to
the psana docs team; they live in Confluence, not here, so the build stays red
until they're fixed there. If you see exactly these failures, the build is healthy.

## Why REST, not the DB

The deployed confluence-doc DB stores a **lossy** pandoc-markdown export of each
page — 0 fenced code blocks, Python indentation and newlines destroyed — so
faithful code is unrecoverable from it. The faithful code lives in Confluence
**storage format** (`body.storage` CDATA), which `extract.py` fetches via REST;
the DB is used only as a **page-discovery index** (which pages exist, IDs,
hierarchy). Full argument: [`notes/iter1-db-extraction-findings.md`](notes/iter1-db-extraction-findings.md).

## Roadmap — Phase 2

Patch the confluence-doc pipeline's `confluence_to_markdown.py` to call
`extract.py`'s pure `parse_storage()` on the `body.storage` it already fetches and
persist a faithful `code_snippets` table. CI could then read code offline from the
DB with no token on the runner — the extractor is already structured so that one
function moves into the pipeline unchanged.

## Layout / extending & limitations

`SPEC.md` is the build contract — manifest schema, snippet categories, and the
`run_checks.py` contract. Read it before modifying internals or adding a check.

- REST is rate-limited to 5 req/min, so re-runs use the cache (`--refresh` only when needed).
- `shellcheck` is not installed on the node, so shell lint is `bash -n` only.
- Tier-3 (execute against fixtures) is intentionally opt-in, not part of `--tier all`.
- Iter-1 research notes: `notes/iter1-db-extraction-findings.md`, `notes/iter1-slurm-recon.md`.

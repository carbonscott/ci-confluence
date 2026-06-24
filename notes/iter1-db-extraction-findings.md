# Iter1 — DB Extraction Faithfulness Findings (psana page + 7 sub-pages)

**Date:** 2026-06-24
**Scope:** psana page `id=199` (`confluence_page_id=267391733`) + its 7 direct sub-pages
(`id=200..207`, parent `267391733`): XTCAV(200), Running at 1MHz(201), Advanced psana
Examples(202), cuNumeric(203), Area Detector Interface(204), Advanced(206), DASK(207).
**Source DB:** `/sdf/group/lcls/ds/dm/apps/dev/data/confluence-doc/lcls-docs.db`
**Method:** Dumped each page's `content` column to `/tmp/ci-confluence-dump/page_<id>.md` on
sdfiana025, then quantified code markup and compared against the live Confluence REST storage
format for the same pages.

---

## 1. Extraction-faithfulness verdict

**VERDICT: The DB markdown is irreparably LOSSY for code. Faithful Python CANNOT be
reconstructed from the DB. Shell is only partially recoverable. Do not build CI on the DB
content column.**

### Quantitative evidence (DB `content` column)

| page | id | fenced ``` blocks | `<span>` tags | `\#`-escaped lines | inline backticks |
|------|----|-------------------|---------------|--------------------|------------------|
| psana | 199 | **0** | 95 | 125 | 42 |
| XTCAV | 200 | 0 | 0 | 0 | 0 |
| 1MHz | 201 | 0 | 4 | 0 | 0 |
| Adv examples | 202 | 0 | 0 | 5 | 0 |
| cuNumeric | 203 | 0 | 0 | 0 | 0 |
| Area Det | 204 | 0 | 0 | 14 | 0 |
| Advanced | 206 | 0 | 0 | 0 | 0 |
| DASK | 207 | 0 | 2 | 0 | 0 |

**Zero fenced code blocks on every page.** `<code>`/`</code>` tags: 0 everywhere. Code is not
delimited at all — it is flattened inline into running prose, peppered with `<span style=...>`
HTML residue and backslash-escaped shell metacharacters (`\#`, `\$`, `\<`, `\>`, `\[`, `\]`,
`\*`). Each code block's language hint and title leak in as a glued prefix
(`pyfrom psana import...`, `bashsetup_hosts_openmpi.sh####...`, `bashenv.shtrue source ...` —
note the macro's collapsed-attribute `true` bleeding through).

### Python — UNRECOVERABLE (concrete before/after)

DB content (page 199, the psmon smalldata snippet), all newlines and indentation gone, the
language hint `py` glued to the first token, comments escaped as `\#`, and lines hard-wrapped
mid-token at ~62 chars (note `np` / `.array` split across the wrap):

```
import publish from psmon.plots import XYPlot,Image from collections
import deque from mpi4py import MPI numworkers =
MPI.COMM_WORLD.Get_size()-1 if numworkers==0: numworkers=1 \# the single
core case (no mpi) os.environ\['PS_SRV_NODES'\]='1' ...
... myxyplot = XYPlot(numevents, "Last 25 Sums", np.arange(len(mydeque)), np
.array(mydeque), formats='o') publish.send("OPALSUMS", myxyplot) ...
```

The SAME snippet from Confluence storage format (CDATA), perfectly faithful:

```python
from psana import DataSource
import numpy as np
import os

# OPTIONAL callback with "gathered" small data from all cores.
def my_smalldata(data_dict):
    print(data_dict)

os.environ['PS_SRV_NODES']='1'
ds = DataSource(exp='tmoc00118', run=222, dir='/sdf/data/lcls/ds/prj/public01/xtc', max_events=10)
```

Why Python is unrecoverable from the DB: Python is whitespace-significant. The DB has lost
**all** newlines and **all** indentation; multiple statements and whole `def`/`if`/`for`
bodies sit on one logical line with no separators. `if numendrun==numworkers: print(...)
numendrun=0 numevents=0 mydeque=...` — there is no signal for where the `if` body ends. No
heuristic can re-derive block structure, and hard-wraps even split identifiers. `ast.parse`
would reject this, and "fixing" it would mean rewriting the code, not recovering it.

### Shell — PARTIALLY recoverable

Single-line shell survives nearly intact (page 201: `export OMPI_MCA_btl_tcp_if_exclude=eno1`;
page 199's two `source .../psconda.sh` lines). But multi-line scripts are flattened the same
way as Python. Example (page 199 `setup_hosts_openmpi.sh`), one logical line:

```
for i in "\${!hosts\[@\]}"; do if \[\[ "\$i" == "0" \]\]; then echo \${hosts\[\$i\]} slots=1 \> \$host_file else if \[\[ -z "\${PS_N_TASKS_PER_NODE}" \]\]; then echo ... fi fi done
```

vs. faithful storage CDATA which keeps line breaks and indentation. Shell tolerates `;`/newline
interchange better than Python, but the `\$ \[ \] \> \>\>` escaping and lost newlines around
heredocs/`#SBATCH` directives (now indistinguishable from `\#` comments) make reconstruction
error-prone and non-trivial. **Not a reliable CI source.**

---

## 2. Could the pipeline make the DB faithful? — YES, EASILY (the crux)

**The faithful code is already being fetched and then thrown away.** Pipeline source:
`/sdf/group/lcls/ds/dm/apps/dev/tools/confluence-doc/confluence_to_markdown.py`.

- **Line 81:** default `--expand` = `body.storage,version,ancestors,...` — it requests
  Confluence **storage format**.
- **Line 567:** `content = page_data.get('body',{}).get('storage',{}).get('value','')` — it
  receives the storage XML (the faithful one, with
  `<ac:structured-macro ac:name="code"><ac:plain-text-body><![CDATA[...]]></ac:plain-text-body></ac:structured-macro>`
  and `<ac:parameter ac:name="language">py</ac:parameter>`).
- **Lines 576-579:** `pypandoc.convert_text(content, args.markdown_format, format='html')`
  with `--markdown-format gfm` (default). **This is the bug.** Pandoc's *HTML* reader does not
  understand Confluence's `ac:`/`ri:` XML namespace. It silently discards the
  `structured-macro` wrapper and renders the CDATA body as an ordinary paragraph, collapsing
  all whitespace. That single line destroys every code block.

**Feasibility of a faithful DB: HIGH / low-effort.** The storage XML is right there at line 567
before conversion. Two clean options:
1. **Pre-process before pandoc:** regex/lxml-extract each `code` macro's `language` param +
   CDATA body and emit a real fenced block (```` ```py ... ``` ````) into the markdown stream
   so pandoc passes it through verbatim; or
2. **Add a sidecar table** `code_snippets(page_id, ordinal, language, title, body)` populated
   directly from the parsed storage macros (independent of the lossy markdown).

Either is a contained change to one script. Storage format is confirmed available for these
pages (live probe below). This is exactly the "extend-the-pipeline" path and it is the
cheapest durable fix.

---

## 3. Confluence REST API reachability from sdfiana025 — REACHABLE

- **Base URL:** `https://confluence.slac.stanford.edu` (from `confluence-cron.sh`).
- **Token:** A token file exists and is readable — path is in
  `tools/confluence-doc/env.local` as `CONFLUENCE_TOKEN_FILE` (45 bytes, readable by the
  pipeline user). *(Value not printed.)*
- **Reachability probe (from sdfiana025):**
  - Unauthenticated `GET /rest/api/content/267391733` → **HTTP 429** instantly (WAF/rate-limit
    without a token).
  - Authenticated `GET /rest/api/content/267391733?expand=body.storage` (Bearer token) →
    **HTTP 200**, storage body **78,910 chars**, **38 code macros**, language params present
    (`py, py, py, py, py, bash, bash, python`). Same for sub-pages.
- **Rate limit (from `docs/rate-limiting.md`):** SLAC IT enforces **5 req/min** (7,200/day).
  A one-shot fetch of all 8 pages with a 12s delay is ~2 min — trivially within budget. Any CI
  REST step must respect this (no tight loops).

**Verdict: REACHABLE with the deployed token; storage format returns faithful code.**

---

## 4. Testable categorization scheme + counts

Counts are from the **storage-format CDATA** (the source CI should actually parse), not the
lossy DB. Across the 8 pages: **60 code macros total, 53 multi-line.** Language params:
`py`=16, `python`=4 (→ 20 Python), `bash`=17, `(none)`=23. Per page: 199→38, 200→0, 201→3,
202→3, 203→2, 204→10, 206→0, 207→4. The 23 `(none)` macros split (by inspection) into Python,
bash command lines, and console transcripts (prompt + output).

| Category | What | How tested | Rough count |
|----------|------|-----------|-------------|
| `python-lint` | Any Python block | `ast.parse` / `ruff` (syntax only) | ~20 explicit + several `(none)` that are Python (e.g. p202 `import psana`, p199 `from psana import DataSource`) → **~26** |
| `python-import-smoke` | Python that only imports/instantiates `DataSource` | run in psana2 conda env, no data | subset of above, **~8** |
| `python-execute` | Python that opens a `DataSource` against public xtc | run in env vs fixture `/sdf/data/lcls/ds/prj/public01/xtc` (confirmed present) | snippets hardcoding `exp='tmoc00118'/'rixx...'` `dir='.../public01/xtc'` → **~6-8** |
| `shell-lint` | `bash`-tagged scripts (sbatch, env.sh, host-setup) | `shellcheck` / `bash -n` | `bash`-tagged **17** + bash `(none)` lines → **~22** |
| `non-testable` | Console transcripts (prompt-prefixed cmd+output, e.g. `(ps-4.1.0) psanagpu101:lcls2$ detnames ...`), separator/output blocks, prose | none (or strip-prompt → shell-lint) | **~10-12** (mostly p199 `detnames` session dumps, p201 mpirun error dump) |

Notes that affect categorization:
- Many snippets are **not standalone** (e.g. sbatch script + the `setup_hosts_openmpi.sh` it
  sources are separate macros; psmon scripts reference `mysmallh5.h5` written by a prior
  snippet) — CI should group related macros per page, not test in isolation.
- Console transcripts mix shell commands with their output; CI should either skip them or
  parse only the `$`-prefixed command lines.

---

## 5. Bottom-line recommendation

**Do NOT build CI on the DB `content` column. It is lossy by construction for code: 0 fenced
blocks, all newlines/indentation destroyed by an HTML-mode pandoc pass over Confluence storage
XML. Python is unrecoverable; shell only partly.**

**Recommended extraction source: REST storage format (`body.storage` CDATA), with the DB used
only as a discovery index** (the `documents` table already gives page ids, titles, breadcrumb
hierarchy — perfect for enumerating which pages to fetch). Concretely:
1. CI enumerates the psana subtree from the DB (`id=199` + `parent_page_id=267391733`).
2. For each page, fetch `?expand=body.storage` via REST (token from
   `CONFLUENCE_TOKEN_FILE`), respecting the 5 req/min limit (~2 min for 8 pages).
3. Parse `ac:name="code"` macros → `(language, title, CDATA body)`, route to the category
   matrix above, and run the corresponding linter/smoke/execute step.

**Is "CI on top of the DB" easier? NO** — not the DB *as it exists today*. The DB content is
the wrong artifact for code CI. **However, "CI on top of the pipeline" is the best long-term
answer:** the pipeline already fetches faithful storage format and merely mis-converts it
(one `pypandoc.convert_text(..., format='html')` call). A small fix — extract code macros to
real fenced blocks or a `code_snippets` sidecar table before/around the pandoc step — would
make the DB a faithful, self-contained CI source and remove the need for live REST calls at CI
time. Recommended sequencing: **Phase 1** build CI on REST storage format now (unblocked,
token + reachability confirmed); **Phase 2** patch the pipeline to persist faithful code so CI
can read it offline from the DB.

**Blockers / caveats:**
- REST is rate-limited to 5 req/min — keep CI fetches batched and delayed; do not poll.
- Token lives in `env.local`; CI needs read access to `CONFLUENCE_TOKEN_FILE` (same host/user
  works; portability to a CI runner needs the token provisioned there).
- Snippets are interdependent and some are console transcripts — categorize per-page and
  filter transcripts; expect to skip a handful as non-testable.

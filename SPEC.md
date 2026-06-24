# CI-Confluence — Build Contract (v1)

Workspace root (on sdfiana025): `/sdf/data/lcls/ds/prj/prjcwang31/results/ci-confluence`
All paths below are relative to that root unless absolute.

## Goal
A re-runnable CI that extracts faithful code snippets documented on the LCLS-II
psana Confluence page + sub-pages, categorizes them, and runs tiered checks —
ultimately on a milano compute node. Confluence stays the human source of truth.

## Why REST, not the DB
The deployed DB (`/sdf/group/lcls/ds/dm/apps/dev/data/confluence-doc/lcls-docs.db`)
stores a LOSSY pandoc-markdown export: 0 fenced blocks, Python indentation gone.
The faithful code lives in Confluence **storage format** (`body.storage`), reachable
via REST from this node (verified HTTP 200). Use the DB ONLY to discover page IDs.

## Repo layout (target)
```
bin/
  extract.py        # discovery + REST fetch + parse -> snippets/ + manifest.json   (Subagent C)
  run_checks.py     # read manifest, run tiered checks, write var/reports/results.json   (Subagent D)
var/cache/storage/<page_id>.xml # cached raw storage XML (so dev re-runs don't hit REST)
snippets/<page_id>/<NNN>.<ext>  # one faithful code file per macro
manifest.json                    # index of all snippets (schema below)
var/reports/                     # check outputs
notes/                           # iter-1 findings (already present)
```

## Discovery (used by extract.py)
- psana root page: `confluence_page_id=267391733` (DB row id=199).
- Sub-pages: rows with `parent_page_id=267391733` (7 direct children). Walk recursively
  if any child has its own children. Query the DB read-only with `sqlite3`.
- For each page id, fetch `GET <base>/rest/api/content/<page_id>?expand=body.storage`.
  Confluence base URL + token file are configured in the confluence-doc tools dir:
  `/sdf/group/lcls/ds/dm/apps/dev/tools/confluence-doc/` (look for `env.local` /
  `CONFLUENCE_TOKEN_FILE` / base URL in the python config). NEVER print the token value.
- Rate limit: 5 req/min. Sleep ~13s between requests. Cache each page's XML to
  `var/cache/storage/<page_id>.xml`; if cache exists and `--refresh` not given, use it.

## Parsing (used by extract.py) — keep this a SEPARABLE function
`parse_storage(xml) -> list[ {language, code, index_on_page, anchor} ]`
- Code macros: `<ac:structured-macro ac:name="code"> ... <ac:plain-text-body><![CDATA[ CODE ]]></ac:plain-text-body> </ac:structured-macro>`.
  Language is `<ac:parameter ac:name="language">LANG</ac:parameter>` (may be absent).
- Unescape XML entities in the CDATA (`&lt; &gt; &amp;` etc. should already be raw in
  CDATA, but guard anyway). Preserve newlines/indentation EXACTLY.
- `anchor`: best-effort nearest preceding heading text, for human traceability.
- This function must be import-safe and side-effect-free so it can later be reused
  inside the confluence-doc pipeline to persist a `code_snippets` table.

## manifest.json schema (THE CONTRACT between C and D)
```json
{
  "generated_at": "<ISO8601 or 'unknown'>",
  "source": "confluence-rest-storage",
  "pages": [ {"page_id":"267391733","title":"psana","url":"<confluence_url>"} ],
  "snippets": [
    {
      "id": "267391733-003",            // "<page_id>-<zero-padded index_on_page>"
      "page_id": "267391733",
      "page_title": "psana",
      "index_on_page": 3,
      "language": "python",              // normalized: python|bash|shell|text|none|...
      "category": "python-lint",         // see categories below (assigned by extract.py)
      "path": "snippets/267391733/003.py",
      "n_lines": 12,
      "anchor": "Plotting with psmon",
      "notes": ""
    }
  ]
}
```

## Categories (assigned in extract.py; consumed by run_checks.py)
A single `category` per snippet, chosen by these rules (first match wins):
- `non-testable`  : language not python/shell, OR looks like a console transcript
                    (lines starting with `>>>`, `$`, `In [`, or pure output/prose).
- `python-execute`: python that constructs a `DataSource(exp=..., run=...)` with a
                    concrete experiment id (runnable against fixture data).
- `python-import-smoke`: python containing `import psana` (or `from psana`) but not a
                    concrete DataSource execution.
- `python-lint`   : any other python.
- `shell-lint`    : bash/shell/sh.
Heuristics are best-effort; when unsure, pick the cheaper/safer tier.

## run_checks.py contract (Subagent D)
`python run_checks.py [--manifest manifest.json] [--tier 1|2] [--category C] [--json var/reports/results.json]`
- Tier 1 (default, NO psana env, runs anywhere incl. login node):
  - python-*  -> syntax check via `ast.parse` (compile). Optionally ruff if available.
  - shell-lint -> `bash -n`; also `shellcheck` if on PATH (treat missing as skip, not fail).
  - non-testable -> skipped (counts as skipped, not pass/fail).
- Tier 2 (needs psana2 env; only meaningful on a milano node):
  - python-import-smoke / python-execute -> run the snippet under the psana2 conda env:
    `source /sdf/group/lcls/ds/ana/sw/conda2/manage/bin/psconda.sh && python <file>`.
    (psconda is NOT set -u clean: use `set -eo pipefail`, no -u.) For tier 2, import-smoke
    should ideally only execute the import lines, but a full run is acceptable v1.
- Output: write `var/reports/results.json` = `{summary:{total,passed,failed,skipped}, results:[{id,category,tier,status,detail}]}`
  and print a one-line-per-snippet table + a final summary. Exit nonzero iff any FAILED.
- Develop against a tiny self-made fixture manifest+snippets until C's real manifest lands;
  must then work unmodified on the real manifest.

## Environment / how to run things on the remote
- Reach the remote via cc-bridge from local Bash:
  `bridge --session ci-confluence bash "<cmd>"`  (runs on sdfiana025 as cwang31).
  `bridge --session ci-confluence write <relpath> --file <localtmp>`  (create workspace file).
  `bridge --session ci-confluence read <relpath> --raw > /tmp/x`       (download w/o context bloat).
- Develop the python files LOCALLY (tmp), push with `bridge ... write`, run with `bridge ... bash`.
- Tier-1 checks run fine directly on sdfiana025 (login node). Tier-2 / milano is a later iteration.
```

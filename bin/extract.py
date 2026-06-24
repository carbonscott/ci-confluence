#!/usr/bin/env python3
"""Snippet extractor for the CI-Confluence pipeline.

Discovers the LCLS-II psana Confluence page (id 267391733) plus every
descendant from the deployed confluence-doc SQLite DB, fetches each page's
faithful *storage format* (body.storage) over the Confluence REST API,
extracts every code macro verbatim, categorizes it, and writes one file per
snippet under snippets/<page_id>/ plus a manifest.json index.

Only the Python standard library is used (urllib, sqlite3, re, json, time,
html, argparse). Confluence "storage format" is XML with ac:/ri: namespaces;
it is parsed with defensive regular expressions rather than a strict XML
parser (the document is not always well-formed XML and CDATA must be
preserved byte-for-byte).

The token value is never printed.
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import sqlite3
import ssl
import sys
import time
import urllib.error
import urllib.request

# --------------------------------------------------------------------------
# Defaults (overridable via flags / environment)
# --------------------------------------------------------------------------
ROOT_PAGE_ID = "267391733"
DEFAULT_DB = "/sdf/group/lcls/ds/dm/apps/dev/data/confluence-doc/lcls-docs.db"
DEFAULT_BASE_URL = "https://confluence.slac.stanford.edu"
DEFAULT_TOKEN_FILE = "/sdf/group/lcls/ds/dm/apps/dev/env/confluence.dat"
RATE_LIMIT_SLEEP = 13.0  # seconds between REST requests (5 req/min budget)


# ==========================================================================
# parse_storage  --  SEPARABLE, side-effect-free, import-safe
# ==========================================================================
#
# It takes a Confluence storage-format XML string and returns a list of dicts:
#   {"language": <str|None>, "code": <str>, "index_on_page": <int>,
#    "anchor": <str|None>}
# It performs NO I/O and has NO global state, so it can be reused inside the
# confluence-doc pipeline to populate a code_snippets table.

# A code macro looks like:
#   <ac:structured-macro ac:name="code" ...>
#     <ac:parameter ac:name="language">py</ac:parameter>
#     <ac:parameter ac:name="title">foo.py</ac:parameter>
#     <ac:plain-text-body><![CDATA[ ...CODE... ]]></ac:plain-text-body>
#   </ac:structured-macro>
# We locate each code macro's open tag, then scan forward for its CDATA body.
# Using an explicit forward scan (rather than one mega-regex) is robust to
# attribute ordering, self-macro nesting, and macros with no body.

_CODE_MACRO_OPEN_RE = re.compile(
    r"<ac:structured-macro\b[^>]*\bac:name\s*=\s*[\"']code[\"'][^>]*>",
    re.IGNORECASE,
)
_MACRO_CLOSE_RE = re.compile(r"</ac:structured-macro>", re.IGNORECASE)
_LANG_PARAM_RE = re.compile(
    r"<ac:parameter\b[^>]*\bac:name\s*=\s*[\"']language[\"'][^>]*>(.*?)</ac:parameter>",
    re.IGNORECASE | re.DOTALL,
)
# CDATA body inside a plain-text-body (preferred) or any CDATA before the macro
# close as a fallback. Capture the CDATA contents verbatim.
_PLAIN_BODY_CDATA_RE = re.compile(
    r"<ac:plain-text-body\b[^>]*>\s*<!\[CDATA\[(.*?)\]\]>\s*</ac:plain-text-body>",
    re.IGNORECASE | re.DOTALL,
)
_ANY_CDATA_RE = re.compile(r"<!\[CDATA\[(.*?)\]\]>", re.DOTALL)

# Heading detection for the best-effort anchor: HTML headings (<h1>..<h6>) and
# the legacy Confluence heading macros are both handled.
_HEADING_RE = re.compile(r"<h[1-6]\b[^>]*>(.*?)</h[1-6]>", re.IGNORECASE | re.DOTALL)
_TAG_STRIP_RE = re.compile(r"<[^>]+>")


def _strip_tags(text: str) -> str:
    """Remove XML/HTML tags and unescape entities, collapsing whitespace."""
    no_tags = _TAG_STRIP_RE.sub("", text)
    unescaped = html.unescape(no_tags)
    return " ".join(unescaped.split()).strip()


def _nearest_anchor(xml: str, macro_start: int) -> str | None:
    """Return the text of the nearest heading that precedes macro_start."""
    last = None
    for m in _HEADING_RE.finditer(xml, 0, macro_start):
        text = _strip_tags(m.group(1))
        if text:
            last = text
    return last


def parse_storage(xml):
    """Extract every code macro from a Confluence storage-format string.

    Pure function: no I/O, no globals mutated. Returns a list of dicts with
    keys language (str|None), code (str), index_on_page (int, 1-based),
    anchor (str|None). Newlines and indentation in `code` are preserved
    exactly. Robust to absent language, missing body, and nested macros.
    """
    if not xml:
        return []

    snippets = []
    index = 0
    pos = 0
    n = len(xml)

    while True:
        open_m = _CODE_MACRO_OPEN_RE.search(xml, pos)
        if not open_m:
            break

        macro_start = open_m.start()
        body_search_start = open_m.end()

        # Find this macro's matching close tag. structured-macros can nest, so
        # balance opens/closes of any structured-macro between here and close.
        depth = 1
        scan = body_search_start
        macro_end = None
        open_generic_re = re.compile(r"<ac:structured-macro\b", re.IGNORECASE)
        while scan < n:
            next_open = open_generic_re.search(xml, scan)
            next_close = _MACRO_CLOSE_RE.search(xml, scan)
            if not next_close:
                break  # malformed: no close at all
            if next_open and next_open.start() < next_close.start():
                depth += 1
                scan = next_open.end()
            else:
                depth -= 1
                scan = next_close.end()
                if depth == 0:
                    macro_end = next_close.start()
                    break
        if macro_end is None:
            macro_end = n  # malformed: treat rest of doc as this macro

        macro_inner = xml[body_search_start:macro_end]

        # Language parameter (may be absent / empty).
        lang_m = _LANG_PARAM_RE.search(macro_inner)
        language = None
        if lang_m:
            language = _strip_tags(lang_m.group(1)) or None

        # CDATA body: prefer the plain-text-body wrapper, fall back to any CDATA.
        body_m = _PLAIN_BODY_CDATA_RE.search(macro_inner)
        if body_m:
            code = body_m.group(1)
        else:
            any_m = _ANY_CDATA_RE.search(macro_inner)
            code = any_m.group(1) if any_m else ""

        # CDATA is already raw, but guard against double-escaped content.
        # Only unescape if there are no literal '<' that would be code (i.e.
        # only when entity markers are present and angle brackets are absent),
        # otherwise leave the bytes untouched to stay faithful.
        if "&lt;" in code or "&gt;" in code or "&amp;" in code:
            if "<" not in code and ">" not in code:
                code = html.unescape(code)

        index += 1
        snippets.append(
            {
                "language": language,
                "code": code,
                "index_on_page": index,
                "anchor": _nearest_anchor(xml, macro_start),
            }
        )

        # Continue scanning AFTER this macro's close so we don't re-match
        # nested inner code macros twice. (Inner code macros, if any, are
        # contained within [macro_start, macro_end] and were already passed
        # over; treating the outer macro as the unit is the desired behavior.)
        pos = macro_end

    return snippets


# ==========================================================================
# Categorization  --  per SPEC "Categories" (first match wins)
# ==========================================================================

_PY_LANGS = {"py", "python", "python3", "py3"}
_SHELL_LANGS = {"bash", "sh", "shell", "zsh", "console"}

# concrete DataSource(exp=..., run=...) with a real experiment id
_DATASOURCE_RE = re.compile(
    r"DataSource\s*\(", re.IGNORECASE
)
_EXP_RE = re.compile(r"\bexp\s*=\s*['\"][^'\"]+['\"]")
_RUN_RE = re.compile(r"\brun\s*=\s*")
_IMPORT_PSANA_RE = re.compile(r"^\s*(import\s+psana|from\s+psana\b)", re.MULTILINE)


# A shell prompt: a Python REPL prompt, an IPython prompt, or a shell prompt
# that may carry a (host/venv/git) preamble with spaces before the final
# `$ `/`# ` separator (e.g. "(ps-4.5.5) monarin@psanagpu111 (master *) psana2 $ cmd").
_REPL_PROMPT_RE = re.compile(r"^\s*(>>>|\.\.\.\s|In \[|Out\[)")
_SHELL_PROMPT_RE = re.compile(r"^\s*[\w()@./~:*\- ]*[\w)][ ]*[$#] \S")
_BARE_SHELL_PROMPT_RE = re.compile(r"^\s*\$ \S")

# A Python traceback header — an unambiguous marker that a block is captured
# console output, never source. (Both the standard and the chained-exception
# forms start with this exact line.)
_TRACEBACK_RE = re.compile(r"^\s*Traceback \(most recent call last\):\s*$")

# Lines that are clearly *program output*, not a command or source line:
#   - a conda/venv prompt echo that leads a command, e.g.
#       "(ps-4.6.1) python parallel_h5_w_dask_dataframe.py"
#     (an "(<env>) <word> ..." line with no shell `$`/`#` separator — the env
#     prefix is echoed by the prompt and the command follows it directly).
#   - MPI/rank-tagged stdout, e.g. "RANK:0 reading took 0.01s.".
#   - the "... File "...", line N, in ..." frames of a traceback.
#   - a "SomeError: message" exception line, or distributed/logging output
#     ("2023-12-08 12:21:04,015 - distributed... - ERROR - ...").
#   - the chained-exception connector lines.
_ENV_PROMPT_CMD_RE = re.compile(r"^\s*\([\w.\-]+\)\s+\S")
_RANK_OUTPUT_RE = re.compile(r"^\s*RANK:\d")
_TB_FRAME_RE = re.compile(r"^\s*File\s+\".*\",\s+line\s+\d+,\s+in\s+")
_EXCEPTION_LINE_RE = re.compile(r"^\s*[\w.]+(Error|Exception|Warning)\b.*:")
_LOG_LINE_RE = re.compile(
    r"^\s*\d{4}-\d\d-\d\d[ T]\d\d:\d\d:\d\d.*\s-\s.*\s-\s(ERROR|WARNING|INFO|DEBUG)\b"
)
_CHAINED_EXC_RE = re.compile(
    r"^\s*During handling of the above exception|"
    r"^\s*The above exception was the direct cause"
)


def _is_output_line(ln: str) -> bool:
    """True if a single line reads as captured program/console output."""
    return bool(
        _ENV_PROMPT_CMD_RE.match(ln)
        or _RANK_OUTPUT_RE.match(ln)
        or _TB_FRAME_RE.match(ln)
        or _EXCEPTION_LINE_RE.match(ln)
        or _LOG_LINE_RE.match(ln)
        or _CHAINED_EXC_RE.match(ln)
    )


def _looks_like_transcript(code: str) -> bool:
    """True if the block reads as a console transcript / pure output/prose.

    A transcript mixes a prompt-prefixed command with its captured output, e.g.
        (ps-4.1.0) host:dir$ detnames exp=foo
        epix  raw  calib
    or a Python REPL session (>>> / In [ ] / Out[ ]). Detected by the presence
    of any prompt-prefixed line: even one such line, followed by output, means
    the block is not a clean source file and should be skipped.

    Additionally caught (these are program output mislabeled as a code macro,
    common when someone pastes a run's stdout/stderr into a code block):
      - any Python traceback header ("Traceback (most recent call last):");
      - a block where a *majority* of non-blank lines read as program output
        (conda/venv prompt echoes like "(ps-4.6.1) python foo.py", "RANK:N ..."
        stdout, traceback frames, exception lines, distributed/logging output).
    The majority test is conservative: a real script with one stray output-ish
    line stays code; only blocks dominated by output are demoted.
    """
    lines = [ln for ln in code.splitlines() if ln.strip()]
    if not lines:
        return True

    # A Python traceback is unambiguous captured output.
    for ln in lines:
        if _TRACEBACK_RE.match(ln):
            return True

    for ln in lines:
        if _REPL_PROMPT_RE.match(ln):
            return True
        if _BARE_SHELL_PROMPT_RE.match(ln):
            return True
        # A prompt with a host/venv preamble ending in "$ " or "# " — but guard
        # against false positives on shell scripts (comments start with "# ",
        # not "<text> # <cmd>"; require a non-space, non-# char before the $/#).
        m = _SHELL_PROMPT_RE.match(ln)
        if m and ("$ " in ln or re.search(r"[\w)] # \S", ln)):
            # Avoid matching ordinary "VAR=val # comment" or python "a # b".
            head = ln.split("$ ", 1)[0] if "$ " in ln else ln
            if "@" in head or ":" in head or "(" in head or ln.lstrip().startswith("$"):
                return True

    # Majority-output test: if most non-blank lines are clearly program output
    # (and there's more than one line, so we don't trip on a single command),
    # the block is a transcript, not a script.
    if len(lines) >= 2:
        n_output = sum(1 for ln in lines if _is_output_line(ln))
        if n_output * 2 > len(lines):
            return True

    return False


def _normalize_language(language):
    """Normalize a raw language token to a canonical value for the manifest."""
    if not language:
        return "none"
    lang = language.strip().lower()
    if lang in _PY_LANGS:
        return "python"
    if lang == "bash":
        return "bash"
    if lang in _SHELL_LANGS:
        return "shell"
    return lang  # keep whatever it is (e.g. "text", "yaml", ...)


def _guess_python(code: str) -> bool:
    """Heuristic: does an untagged block look like Python?"""
    if _IMPORT_PSANA_RE.search(code):
        return True
    py_signals = (
        re.search(r"^\s*(import|from)\s+\w", code, re.MULTILINE),
        re.search(r"^\s*def\s+\w+\s*\(", code, re.MULTILINE),
        re.search(r"^\s*class\s+\w+", code, re.MULTILINE),
        re.search(r"\bprint\s*\(", code),
        re.search(r"DataSource\s*\(", code),
        re.search(r"=\s*np\.", code),
    )
    return any(py_signals)


def _guess_shell(code: str) -> bool:
    """Heuristic: does an untagged block look like shell?"""
    shell_signals = (
        code.lstrip().startswith("#!") and "sh" in code.splitlines()[0],
        re.search(r"^\s*#SBATCH\b", code, re.MULTILINE),
        re.search(r"^\s*(export|source|module load|sbatch|srun|mpirun)\b", code, re.MULTILINE),
        re.search(r"^\s*\w+=\S+\s*$", code, re.MULTILINE) and "import" not in code,
    )
    return any(shell_signals)


# A line that is clearly a shell invocation, not python.
_SHELL_CMD_LINE_RE = re.compile(
    r"^\s*(mpirun|srun|sbatch|mpiexec|module\s+load|conda\s+activate|"
    r"source\s+\S|export\s+\w+=|cd\s+\S|sh\s+\S)\b"
)
# Jupyter/IPython cell or line magic (e.g. "%%bash", "%matplotlib").
_MAGIC_RE = re.compile(r"^\s*%%?\w")


def _python_is_implausible(code: str) -> bool:
    """True if a python-tagged block clearly is NOT python source.

    Catches mislabeled shell command lines (mpirun ...), Jupyter cell magics
    (%%bash), and pure-prose blurbs. Does NOT trip on genuine python that
    merely has a typo on the page (those keep python imports/keywords and so
    stay python-* to be reported by the linter).
    """
    lines = [ln for ln in code.splitlines() if ln.strip()]
    if not lines:
        return True
    first = lines[0]
    if _MAGIC_RE.match(first):
        return True  # %%bash etc.
    if _SHELL_CMD_LINE_RE.match(first):
        return True  # leads with mpirun/srun/...
    # No python-ish token anywhere AND no assignment/call structure -> prose.
    has_py_token = bool(
        re.search(r"\b(import|from|def|class|return|lambda|print|for|while|if|"
                  r"with|try|except|yield|assert)\b", code)
        or re.search(r"^\s*\w[\w.]*\s*=", code, re.MULTILINE)
        or re.search(r"\w\s*\(", code)
    )
    if not has_py_token:
        return True
    return False


# An angle-bracket placeholder used in illustrative pseudocode, e.g.
#   GeometryAccess(<geometry-file-name>)
# matches "<name>" / "<a-b>" / "<some thing>" but NOT a comparison ("a < b"),
# a type hint ("List[int]"), or an HTML-ish token — it requires the contents to
# be a bare identifier-like placeholder with no operators/quotes inside.
_PLACEHOLDER_RE = re.compile(r"<[A-Za-z][\w-]*(?:[ -][\w-]+)*>")


def _python_is_pseudocode(code: str) -> bool:
    """True if a python block is illustrative pseudocode that cannot parse.

    Specifically: it contains an angle-bracket placeholder (``<...>``) AND it
    does not parse as Python. The parse guard keeps real code (where ``<`` is a
    comparison and the block compiles) in the lint tier, while a fragment whose
    only ``<...>`` is a fill-in-the-blank placeholder (so it fails to compile)
    is correctly demoted to non-testable rather than reported as a doc bug.
    """
    if not _PLACEHOLDER_RE.search(code):
        return False
    try:
        compile(code, "<snippet>", "exec")
    except SyntaxError:
        return True
    except Exception:  # noqa: BLE001 - any non-syntax error means it parsed
        return False
    return False


def categorize(language, code):
    """Return (category, normalized_language) for a snippet.

    Rules (first match wins) per SPEC:
      non-testable         : not python/shell, OR a console transcript.
      python-execute       : python building DataSource(exp='...', run=...).
      python-import-smoke  : python importing psana but not executing DataSource.
      python-lint          : any other python.
      shell-lint           : bash/shell/sh.
    """
    norm = _normalize_language(language)

    # Decide the effective "kind": python, shell, or other.
    if norm == "python":
        kind = "python"
    elif norm in ("bash", "shell"):
        kind = "shell"
    elif norm == "none":
        # Untagged: try to infer.
        if _guess_python(code):
            kind = "python"
            norm = "python"
        elif _guess_shell(code):
            kind = "shell"
            norm = "shell"
        else:
            kind = "other"
    else:
        kind = "other"

    # Rule 1: non-testable if not python/shell, or a transcript.
    if kind == "other":
        return "non-testable", norm
    if _looks_like_transcript(code):
        return "non-testable", norm

    # A block tagged/guessed python that clearly is not python (shell command,
    # cell magic, or pure prose) is non-testable, not a lint candidate.
    if kind == "python" and _python_is_implausible(code):
        return "non-testable", norm

    # Illustrative pseudocode with an angle-bracket placeholder (<...>) that
    # cannot compile is non-testable, not a doc bug to be reported by the linter.
    if kind == "python" and _python_is_pseudocode(code):
        return "non-testable", norm

    if kind == "python":
        has_concrete_ds = bool(
            _DATASOURCE_RE.search(code)
            and _EXP_RE.search(code)
            and _RUN_RE.search(code)
        )
        if has_concrete_ds:
            return "python-execute", norm
        if _IMPORT_PSANA_RE.search(code):
            return "python-import-smoke", norm
        return "python-lint", norm

    # kind == "shell"
    return "shell-lint", norm


def _ext_for(norm_language, category):
    """Choose a file extension for an emitted snippet."""
    if norm_language == "python" or category.startswith("python"):
        return ".py"
    if norm_language in ("bash", "shell") or category == "shell-lint":
        return ".sh"
    return ".txt"


# ==========================================================================
# Discovery  --  read the deployed DB (read-only) for the page subtree
# ==========================================================================

def discover_pages(db_path, root_page_id):
    """Return [{page_id, title, url}] for root + all descendants (BFS)."""
    uri = "file:" + db_path + "?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT confluence_page_id, title, confluence_url, parent_page_id "
            "FROM documents WHERE confluence_page_id IS NOT NULL"
        )
        rows = cur.fetchall()
    finally:
        conn.close()

    by_id = {}
    children = {}
    for r in rows:
        pid = str(r["confluence_page_id"])
        by_id[pid] = {
            "page_id": pid,
            "title": r["title"] or "",
            "url": r["confluence_url"] or "",
        }
        parent = r["parent_page_id"]
        if parent is not None:
            children.setdefault(str(parent), []).append(pid)

    # BFS from the root, following parent_page_id chains downward.
    ordered = []
    seen = set()
    queue = [str(root_page_id)]
    while queue:
        pid = queue.pop(0)
        if pid in seen:
            continue
        seen.add(pid)
        if pid in by_id:
            ordered.append(by_id[pid])
        for child in sorted(children.get(pid, [])):
            if child not in seen:
                queue.append(child)
    return ordered


# ==========================================================================
# Fetch  --  REST storage format, cached, rate-limited
# ==========================================================================

def _read_token(token_file):
    with open(token_file, "r") as fh:
        return fh.read().strip()


# Candidate system CA bundles. urllib's openssl default (/etc/ssl/cert.pem) is
# missing on this host, so SLAC's internal CA chain fails to verify unless we
# point at the real system bundle (the one curl uses). Search common paths.
_CA_BUNDLE_CANDIDATES = (
    "/etc/pki/tls/certs/ca-bundle.crt",
    "/etc/pki/ca-trust/extracted/pem/tls-ca-bundle.pem",
    "/etc/ssl/certs/ca-certificates.crt",
)


def _build_ssl_context():
    """Build an SSL context that can verify the SLAC internal CA chain.

    Honors SSL_CERT_FILE if set, else probes known system bundles, else falls
    back to the OpenSSL default (which may include a capath that works).
    """
    cafile = os.environ.get("SSL_CERT_FILE")
    if cafile and os.path.exists(cafile):
        return ssl.create_default_context(cafile=cafile)
    for cand in _CA_BUNDLE_CANDIDATES:
        if os.path.exists(cand):
            return ssl.create_default_context(cafile=cand)
    return ssl.create_default_context()


_SSL_CONTEXT = _build_ssl_context()


def fetch_storage(base_url, page_id, token, timeout=60):
    """GET the storage-format body for one page. Returns the full JSON dict."""
    url = f"{base_url.rstrip('/')}/rest/api/content/{page_id}?expand=body.storage"
    req = urllib.request.Request(url)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Accept", "application/json")
    with urllib.request.urlopen(req, timeout=timeout, context=_SSL_CONTEXT) as resp:
        data = resp.read().decode("utf-8")
    return json.loads(data)


def get_page_xml(base_url, page_id, token, cache_dir, refresh, did_fetch_ref):
    """Return storage XML for page_id, using/refreshing the on-disk cache.

    did_fetch_ref is a one-element list flag set True when a live REST call was
    made (so the caller can apply the rate-limit sleep only between real
    fetches).
    """
    cache_path = os.path.join(cache_dir, f"{page_id}.xml")
    if os.path.exists(cache_path) and not refresh:
        with open(cache_path, "r", encoding="utf-8") as fh:
            return fh.read(), False

    payload = fetch_storage(base_url, page_id, token)
    xml = (
        payload.get("body", {})
        .get("storage", {})
        .get("value", "")
    )
    os.makedirs(cache_dir, exist_ok=True)
    with open(cache_path, "w", encoding="utf-8") as fh:
        fh.write(xml)
    did_fetch_ref[0] = True
    return xml, True


# ==========================================================================
# Emit  --  write snippet files + manifest.json
# ==========================================================================

def emit(snippets_meta, out_dir):
    """Write each snippet's code to snippets/<page_id>/<NNN>.<ext>."""
    for s in snippets_meta:
        full = os.path.join(out_dir, s["path"])
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w", encoding="utf-8", newline="") as fh:
            fh.write(s["_code"])


def build_manifest(pages, snippets_meta):
    manifest = {
        "source": "confluence-rest-storage",
        "pages": [
            {"page_id": p["page_id"], "title": p["title"], "url": p["url"]}
            for p in pages
        ],
        "snippets": [
            {
                "id": s["id"],
                "page_id": s["page_id"],
                "page_title": s["page_title"],
                "index_on_page": s["index_on_page"],
                "language": s["language"],
                "category": s["category"],
                "path": s["path"],
                "n_lines": s["n_lines"],
                "anchor": s["anchor"],
                "notes": s["notes"],
            }
            for s in snippets_meta
        ],
    }
    return manifest


# ==========================================================================
# main
# ==========================================================================

def main(argv=None):
    parser = argparse.ArgumentParser(
        description=(
            "Discover the psana Confluence subtree, fetch faithful code from "
            "the REST storage format, categorize each snippet, and emit "
            "snippets/ + manifest.json."
        ),
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Ignore cached storage XML and re-fetch every page from REST.",
    )
    parser.add_argument(
        "--db",
        default=DEFAULT_DB,
        help="Path to the deployed confluence-doc SQLite DB (read-only).",
    )
    parser.add_argument(
        "--out",
        default=".",
        help="Workspace root: snippets/, cache/, manifest.json are written here.",
    )
    parser.add_argument(
        "--base-url",
        default=os.environ.get("CONFLUENCE_BASE_URL", DEFAULT_BASE_URL),
        help="Confluence base URL.",
    )
    parser.add_argument(
        "--token-file",
        default=os.environ.get("CONFLUENCE_TOKEN_FILE", DEFAULT_TOKEN_FILE),
        help="File containing the Confluence bearer token (never printed).",
    )
    parser.add_argument(
        "--root-page-id",
        default=ROOT_PAGE_ID,
        help="Root Confluence page id to discover from.",
    )
    parser.add_argument(
        "--sleep",
        type=float,
        default=RATE_LIMIT_SLEEP,
        help="Seconds to sleep between live REST requests (5 req/min => ~13s).",
    )
    args = parser.parse_args(argv)

    out_dir = os.path.abspath(args.out)
    cache_dir = os.path.join(out_dir, "cache", "storage")

    # 1. Discovery.
    print(f"[discover] reading {args.db}", file=sys.stderr)
    pages = discover_pages(args.db, args.root_page_id)
    print(f"[discover] {len(pages)} pages in the psana subtree", file=sys.stderr)
    for p in pages:
        print(f"           {p['page_id']}  {p['title']}", file=sys.stderr)

    if not pages:
        print("[error] no pages discovered; aborting", file=sys.stderr)
        return 1

    # 2. Fetch token once (kept in a local; never printed).
    token = _read_token(args.token_file)

    # 3. Fetch + parse each page.
    snippets_meta = []
    n_pages = len(pages)
    for i, page in enumerate(pages):
        page_id = page["page_id"]
        did_fetch = [False]
        try:
            xml, fetched = get_page_xml(
                args.base_url, page_id, token, cache_dir, args.refresh, did_fetch
            )
        except urllib.error.HTTPError as e:
            print(f"[fetch] page {page_id}: HTTP {e.code} (skipping)", file=sys.stderr)
            continue
        except Exception as e:  # noqa: BLE001 - be defensive per page
            print(f"[fetch] page {page_id}: {type(e).__name__}: {e} (skipping)",
                  file=sys.stderr)
            continue

        src = "REST" if fetched else "cache"
        macros = parse_storage(xml)
        print(f"[parse] page {page_id} ({src}): {len(macros)} code macros",
              file=sys.stderr)

        for m in macros:
            idx = m["index_on_page"]
            category, norm_lang = categorize(m["language"], m["code"])
            ext = _ext_for(norm_lang, category)
            nnn = f"{idx:03d}"
            rel_path = os.path.join("snippets", page_id, f"{nnn}{ext}")
            snippet_id = f"{page_id}-{nnn}"
            code = m["code"]
            n_lines = code.count("\n") + (1 if code and not code.endswith("\n") else 0)
            if not code:
                n_lines = 0
            snippets_meta.append(
                {
                    "id": snippet_id,
                    "page_id": page_id,
                    "page_title": page["title"],
                    "index_on_page": idx,
                    "language": norm_lang,
                    "category": category,
                    "path": rel_path,
                    "n_lines": n_lines,
                    "anchor": m["anchor"],
                    "notes": "",
                    "_code": code,
                }
            )

        # Rate limit: sleep only after a real REST call, and not after the last.
        if did_fetch[0] and i < n_pages - 1:
            time.sleep(args.sleep)

    # 4. Emit snippet files.
    emit(snippets_meta, out_dir)

    # 5. Write manifest.json.
    manifest = build_manifest(pages, snippets_meta)
    manifest_path = os.path.join(out_dir, "manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2, ensure_ascii=False)
        fh.write("\n")

    # 6. Summary to stdout.
    by_cat = {}
    by_page = {}
    for s in snippets_meta:
        by_cat[s["category"]] = by_cat.get(s["category"], 0) + 1
        by_page[s["page_id"]] = by_page.get(s["page_id"], 0) + 1
    print(f"\n[done] {len(snippets_meta)} snippets across {len(pages)} pages")
    print(f"[done] manifest: {manifest_path}")
    print("[per-category]")
    for cat in sorted(by_cat):
        print(f"  {cat:22s} {by_cat[cat]}")
    print("[per-page]")
    for p in pages:
        print(f"  {p['page_id']:12s} {by_page.get(p['page_id'], 0):3d}  {p['title']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

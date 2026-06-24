#!/usr/bin/env python3
"""run_checks.py -- tiered CI checks for code snippets extracted from Confluence.

Reads a manifest.json (the contract between extract.py and this runner), iterates
the listed snippets, resolves each one's file via its `path`, and runs a tier of
checks. Writes reports/results.json and prints a compact per-snippet table plus a
final summary. Exits nonzero iff any snippet FAILED (CI semantics): warnings and
skips never fail the build.

Tier 1 (default; no psana env; runs anywhere, incl. the login node):
  - python-* categories : syntax check via ast.parse(open(path).read()). If `ruff`
                          is on PATH, additionally run `ruff check --quiet <file>`
                          and treat any ruff findings as WARNINGS (reported, but
                          NEVER a FAIL -- only hard syntax errors FAIL).
  - shell-lint          : `bash -n <file>`. If `shellcheck` is on PATH, run it too
                          as WARNINGS. Missing shellcheck = skipped sub-check, not a
                          failure.
  - non-testable        : status `skipped`.

Tier 2 (IMPORT-SMOKE; only meaningful on a milano compute node; psana2 env required):
  - python-import-smoke / python-execute : statically extract just the snippet's
    module-level import statements (via an `ast` walk, after the same U+00A0/dedent
    normalization tier-1 uses), regenerate clean import lines with `ast.unparse`,
    and run ONLY those imports under the psana2 conda env via a self-contained
    wrapper:
        bash -c 'set -eo pipefail; source <psconda>; python <tmp_imports.py>'
    (psconda is NOT `set -u`-clean, so we deliberately omit `-u`.) PASS if exit 0;
    an ImportError/ModuleNotFoundError/etc. => FAIL (last stderr line is the detail).
    This tests that the DOCUMENTED APIs still resolve in the current psana2 env --
    the real doc-rot mode -- WITHOUT executing the snippet body (which would read
    real data). A snippet that does not even parse (a genuine tier-1 syntax FAIL)
    is reported `skipped` ("unparseable (see tier-1)"), never a tier-2 FAIL.
  - other categories fall back to their Tier-1 behavior so a tier-2 run is a
    superset of tier 1, EXCEPT shell-lint which just re-runs its tier-1 `bash -n`.

Tier 3 (FULL EXECUTION; opt-in; psana2 env required; NOT part of `--tier all`):
  - python-execute : run the WHOLE snippet file under the psana2 conda env via
        bash -c 'set -eo pipefail; source <psconda>; python <file>'
    Nonzero exit => FAIL. This is the original tier-2 behavior, preserved but opt-in
    because python-execute snippets read real experiment data and are too noisy for
    routine CI. Non-exec categories fall back to their tier-1 behavior.

Status values: PASSED | FAILED | SKIPPED. A snippet may additionally carry warnings
(surfaced in `detail`) without changing a PASSED status.

Stdlib only.
"""

import argparse
import ast
import json
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap

# Copy-paste hazards that are auto-fixable whitespace, NOT logic/syntax rot:
# a non-breaking space (U+00A0) renders like a space but is not one, and a
# fragment copied out of a larger file may carry uniform leading indentation.
# These are normalized in an in-memory COPY before ast.parse so they don't
# hard-FAIL the build; the stored snippet file is left byte-faithful.
NBSP = chr(0xA0)

PSCONDA = "/sdf/group/lcls/ds/ana/sw/conda2/manage/bin/psconda.sh"

PASSED = "passed"
FAILED = "failed"
SKIPPED = "skipped"

PYTHON_CATEGORIES = {
    "python-lint",
    "python-import-smoke",
    "python-execute",
}
SHELL_CATEGORIES = {"shell-lint"}
NON_TESTABLE = {"non-testable"}

# Tier-2 (import-smoke) categories: extract & resolve just the import lines under
# psana2. Both python-import-smoke and python-execute snippets are checked this way
# so a tier-2 run validates the documented APIs without executing snippet bodies.
TIER2_IMPORT_SMOKE_CATEGORIES = {"python-import-smoke", "python-execute"}

# Tier-3 (full execution) categories: run the WHOLE snippet file under psana2. Only
# python-execute snippets are designed to be runnable end-to-end against fixture data.
TIER3_EXEC_CATEGORIES = {"python-execute"}

# Back-compat alias: the original tier-2 (now tier-3) "execute the whole snippet"
# category set. Retained so external references keep resolving.
TIER2_EXEC_CATEGORIES = TIER3_EXEC_CATEGORIES


def _read_file(path):
    """Read a file as UTF-8 text. Raises OSError/UnicodeDecodeError on problems."""
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


def _run(cmd, timeout=120):
    """Run a command list, capturing stdout+stderr. Returns (returncode, output).

    Never raises on a nonzero exit; only on a hard inability to spawn (which the
    caller turns into a FAIL/detail). Timeouts yield returncode 124.
    """
    try:
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
        )
        return proc.returncode, proc.stdout.decode("utf-8", "replace")
    except subprocess.TimeoutExpired as exc:
        out = exc.stdout.decode("utf-8", "replace") if exc.stdout else ""
        return 124, out + "\n[timed out]"


# ----------------------------------------------------------------------------
# Tier-1 checks
# ----------------------------------------------------------------------------

def _normalize_for_parse(source):
    """Return (normalized_source, warnings) for an in-memory parse copy.

    Auto-fixable copy-paste hazards are normalized so they do not hard-FAIL the
    build, while the stored snippet file is left byte-faithful (this operates on
    a COPY only):
      - non-breaking spaces (U+00A0) -> ASCII space. These render like spaces but
        ast.parse rejects them as "non-printable character U+00A0".
      - `textwrap.dedent` to strip uniform leading indentation, so a legitimate
        fragment lifted out of a deeper block (every line indented) still parses.

    Each fix that actually changed the source contributes a WARNING string.
    """
    warnings = []

    n_nbsp = source.count(NBSP)
    if n_nbsp:
        source = source.replace(NBSP, " ")
        warnings.append("contains %d non-breaking space(s)" % n_nbsp)

    dedented = textwrap.dedent(source)
    if dedented != source:
        # How many leading spaces were uniformly removed (the indent of the
        # first non-blank line in the original copy). textwrap.dedent also
        # strips whitespace-only common prefixes on otherwise-blank lines; only
        # warn when a real common indent (>0) was actually removed, so a
        # cosmetic blank-line cleanup does not surface a "dedented 0" warning.
        removed = 0
        for line in source.splitlines():
            if line.strip():
                removed = len(line) - len(line.lstrip(" "))
                break
        source = dedented
        if removed:
            warnings.append("dedented %d space(s)" % removed)

    return source, warnings


def check_python_syntax(abspath):
    """Tier-1 python check. Returns (status, detail).

    The snippet is parsed as-is first. If that fails, an in-memory COPY is
    normalized (U+00A0 -> space, then ``textwrap.dedent``) and re-parsed: copy-
    paste whitespace hazards are auto-fixable, not logic/syntax rot, so they
    PASS with a WARNING rather than hard-FAILing the build. Only source that
    STILL fails to parse after normalization is a real syntax FAIL. The stored
    snippet file is never modified. If `ruff` is on PATH we additionally lint and
    fold any findings in as WARNINGS that never flip a PASSED to FAILED.
    """
    try:
        source = _read_file(abspath)
    except (OSError, UnicodeDecodeError) as exc:
        return FAILED, "unreadable file: %s" % exc

    norm_warnings = []
    try:
        ast.parse(source, filename=abspath)
    except SyntaxError:
        # Retry on a normalized copy (the on-disk file stays byte-faithful).
        normalized, norm_warnings = _normalize_for_parse(source)
        try:
            ast.parse(normalized, filename=abspath)
        except SyntaxError as exc2:
            return FAILED, "SyntaxError: %s (line %s)" % (exc2.msg, exc2.lineno)

    detail = "ast.parse OK"
    for w in norm_warnings:
        detail += " | WARNING: %s" % w

    if shutil.which("ruff"):
        rc, out = _run(["ruff", "check", "--quiet", abspath])
        if rc != 0:
            first = out.strip().splitlines()
            preview = " | ".join(line.strip() for line in first[:3])
            detail += " | WARNING ruff: %s" % (preview or "findings reported")
        else:
            detail += " | ruff clean"
    else:
        detail += " | ruff not on PATH (lint skipped)"

    return PASSED, detail


def check_shell(abspath):
    """Tier-1 shell check. Returns (status, detail).

    `bash -n` syntax error -> FAILED. Clean -> PASSED. `shellcheck` (if present) is
    run as WARNINGS only; absence is a skipped sub-check, not a failure.
    """
    if not shutil.which("bash"):
        return FAILED, "bash not on PATH"

    rc, out = _run(["bash", "-n", abspath])
    if rc != 0:
        return FAILED, "bash -n error: %s" % (out.strip()[:300] or "syntax error")

    detail = "bash -n OK"

    if shutil.which("shellcheck"):
        sc_rc, sc_out = _run(["shellcheck", abspath])
        if sc_rc != 0:
            preview = " | ".join(
                line.strip() for line in sc_out.strip().splitlines()[:3]
            )
            detail += " | WARNING shellcheck: %s" % (preview or "findings reported")
        else:
            detail += " | shellcheck clean"
    else:
        detail += " | shellcheck not on PATH (lint skipped)"

    return PASSED, detail


# ----------------------------------------------------------------------------
# Tier-2 checks (import-smoke under psana env)
# ----------------------------------------------------------------------------

def extract_imports(source):
    """Return (import_lines, parsed_ok) for a python snippet's module-level imports.

    The snippet is parsed with `ast` after the SAME copy-paste normalization tier-1
    applies (U+00A0 -> space, then ``textwrap.dedent``), so a snippet that PASSES
    tier-1 (possibly only after normalization) also yields its imports here. We walk
    the whole tree and collect every ``ast.Import`` / ``ast.ImportFrom`` node --
    including ones nested inside functions / conditionals -- and regenerate a clean,
    canonical one-statement-per-line source with ``ast.unparse``. Regenerating from
    the AST (rather than slicing source lines) robustly handles parenthesized
    multi-line ``from X import (\\n a,\\n b)`` and trailing-backslash continuations,
    since the parser has already folded them into a single node.

    `parsed_ok` is False iff the snippet does not parse even after normalization
    (i.e. a genuine tier-1 syntax FAIL); the caller then SKIPs rather than failing.
    De-duplicates identical regenerated lines while preserving first-seen order.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        normalized, _ = _normalize_for_parse(source)
        try:
            tree = ast.parse(normalized)
        except SyntaxError:
            return [], False

    lines = []
    seen = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            line = ast.unparse(node)
            if line not in seen:
                seen.add(line)
                lines.append(line)
    return lines, True


def check_python_import_smoke(abspath, psconda=PSCONDA):
    """Tier-2 import-smoke under the psana2 conda env. Returns (status, detail).

    Statically extracts the snippet's import statements (see ``extract_imports``),
    writes them to a temp file, and runs ONLY those imports under psana2 via a
    self-contained wrapper (sources psconda itself, so this works whether or not the
    caller already sourced it):

        bash -c 'set -eo pipefail; source <psconda>; python <tmp_imports.py>'

    psconda is NOT `set -u`-clean, so the wrapper omits `-u`. PASS on exit 0; an
    ImportError / ModuleNotFoundError / etc. => FAIL, with the LAST line of output
    as the detail (the documented-API-no-longer-imports finding). A snippet with no
    imports passes trivially (nothing to resolve). A snippet that does not parse is
    reported SKIPPED ("unparseable (see tier-1)"), never a tier-2 FAIL.
    """
    if not os.path.exists(psconda):
        return FAILED, "psconda not found at %s (need a milano node)" % psconda

    try:
        source = _read_file(abspath)
    except (OSError, UnicodeDecodeError) as exc:
        return FAILED, "unreadable file: %s" % exc

    import_lines, parsed_ok = extract_imports(source)
    if not parsed_ok:
        return SKIPPED, "unparseable (see tier-1)"
    if not import_lines:
        return PASSED, "no imports to resolve"

    body = "\n".join(import_lines) + "\n"
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", prefix="imports_", delete=False, encoding="utf-8"
        ) as tf:
            tf.write(body)
            tmp_path = tf.name

        wrapper = (
            "set -eo pipefail; source %s; python %s"
            % (_shquote(psconda), _shquote(tmp_path))
        )
        rc, out = _run(["bash", "-c", wrapper], timeout=300)
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    n = len(import_lines)
    if rc != 0:
        last = ""
        for line in reversed(out.splitlines()):
            if line.strip():
                last = line.strip()
                break
        return FAILED, "exit=%d | %d import(s) | %s" % (
            rc, n, last or "(no output)"
        )
    return PASSED, "%d import(s) resolved" % n


def check_python_psana(abspath, psconda=PSCONDA):
    """Tier-3 full execution under the psana2 conda env. Returns (status, detail).

    Runs the WHOLE snippet file. Wrapper deliberately uses `set -eo pipefail` WITHOUT
    `-u` because psconda's setup script is not `set -u`-clean. Nonzero exit (env
    source failure or snippet error) -> FAILED. This is the original tier-2 behavior,
    preserved as opt-in tier 3 because python-execute snippets read real data.
    """
    if not os.path.exists(psconda):
        return FAILED, "psconda not found at %s (need a milano node)" % psconda

    wrapper = (
        "set -eo pipefail; source %s; python %s"
        % (_shquote(psconda), _shquote(abspath))
    )
    rc, out = _run(["bash", "-c", wrapper], timeout=300)
    tail = out.strip().splitlines()[-5:]
    detail = "exit=%d | %s" % (rc, " / ".join(t.strip() for t in tail) or "(no output)")
    if rc != 0:
        return FAILED, detail
    return PASSED, detail


def _shquote(s):
    """Minimal single-quote shell escaping for embedding paths in a bash -c string."""
    return "'" + s.replace("'", "'\"'\"'") + "'"


# ----------------------------------------------------------------------------
# Dispatch
# ----------------------------------------------------------------------------

def evaluate(snippet, tier, workspace_root):
    """Run the appropriate check for one snippet. Returns (status, detail).

    Snippet `path` values are relative to the workspace root, which is the directory
    the runner is invoked from (the documented invocation does
    `cd <workspace> && python3 bin/run_checks.py ...`). We therefore resolve them
    against `workspace_root` == cwd. This works identically for the fixture manifest
    (paths like `fixture/snippets/ok.py`) and the real root manifest.
    """
    category = snippet.get("category", "")
    rel = snippet.get("path", "")
    if not rel:
        return FAILED, "manifest snippet missing 'path'"

    abspath = rel if os.path.isabs(rel) else os.path.join(workspace_root, rel)

    if category in NON_TESTABLE:
        return SKIPPED, "non-testable"

    if not os.path.exists(abspath):
        return FAILED, "file not found: %s" % abspath

    # Tier 2 == import-smoke: resolve just the import lines under psana2 for the
    # exec categories. Everything else (shell-lint, python-lint, ...) falls through
    # to its tier-1 behavior, so a tier-2 run is a superset of tier 1.
    if tier == 2 and category in TIER2_IMPORT_SMOKE_CATEGORIES:
        return check_python_import_smoke(abspath)

    # Tier 3 == full execution: run the whole snippet under psana2 (opt-in).
    if tier == 3 and category in TIER3_EXEC_CATEGORIES:
        return check_python_psana(abspath)

    # Tier-1 behavior (also the fallback within a tier-2/3 run for non-exec
    # categories). shell-lint always uses its tier-1 `bash -n` regardless of tier.
    if category in PYTHON_CATEGORIES:
        return check_python_syntax(abspath)
    if category in SHELL_CATEGORIES:
        return check_shell(abspath)

    # Unknown category: be safe, don't fail the build on a categorization we don't
    # recognize -- skip and flag it in the detail.
    return SKIPPED, "unknown category '%s' (skipped)" % category


def _has_warning(detail):
    return "WARNING" in detail


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="run_checks.py",
        description="Tiered CI checks for Confluence-extracted code snippets. "
        "Exit nonzero iff any snippet FAILED.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--manifest",
        default="manifest.json",
        help="Path to manifest.json (relative to workspace root or absolute).",
    )
    parser.add_argument(
        "--tier",
        type=int,
        choices=(1, 2, 3),
        default=1,
        help="1 = syntax/lint, no psana env (runs anywhere). "
        "2 = import-smoke: resolve documented imports under psana2 (milano node). "
        "3 = full execution: run whole python-execute snippets under psana2 "
        "(opt-in; reads real data; NOT included in `ci.sh --tier all`).",
    )
    parser.add_argument(
        "--category",
        default=None,
        help="Only check snippets whose category matches this value.",
    )
    parser.add_argument(
        "--json",
        default=os.environ.get("CI_REPORTS_JSON", "var/reports/results.json"),
        help="Where to write the JSON results report "
             "(default: var/reports/results.json; override with $CI_REPORTS_JSON).",
    )
    args = parser.parse_args(argv)

    # Workspace root = cwd. Snippet `path` values are relative to the workspace root,
    # and the documented invocation runs the script from there
    # (`cd <workspace> && python3 bin/run_checks.py ...`). Resolving against cwd works
    # identically for the fixture manifest and the real root manifest.
    manifest_path = os.path.abspath(args.manifest)
    if not os.path.exists(manifest_path):
        print("error: manifest not found: %s" % manifest_path, file=sys.stderr)
        return 2
    workspace_root = os.getcwd()

    try:
        with open(manifest_path, "r", encoding="utf-8") as fh:
            manifest = json.load(fh)
    except (OSError, ValueError) as exc:
        print("error: cannot read/parse manifest: %s" % exc, file=sys.stderr)
        return 2

    snippets = manifest.get("snippets", [])
    if args.category:
        snippets = [s for s in snippets if s.get("category") == args.category]

    results = []
    counts = {"total": 0, "passed": 0, "failed": 0, "skipped": 0, "warnings": 0}

    for snip in snippets:
        status, detail = evaluate(snip, args.tier, workspace_root)
        warned = status != FAILED and _has_warning(detail)
        counts["total"] += 1
        counts[status] += 1
        if warned:
            counts["warnings"] += 1
        results.append(
            {
                "id": snip.get("id", "?"),
                "category": snip.get("category", "?"),
                "tier": args.tier,
                "status": status,
                "detail": detail,
            }
        )

    report = {"summary": counts, "results": results}

    # Write JSON report (relative paths resolve against cwd, per the CLI convention).
    out_path = os.path.abspath(args.json)
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)
        fh.write("\n")

    # Compact one-row-per-snippet table.
    _print_table(results)
    print(
        "SUMMARY: total=%d passed=%d failed=%d skipped=%d warnings=%d -> %s"
        % (
            counts["total"],
            counts["passed"],
            counts["failed"],
            counts["skipped"],
            counts["warnings"],
            "PASS" if counts["failed"] == 0 else "FAIL",
        )
    )
    print("report: %s" % out_path)

    return 1 if counts["failed"] else 0


def _print_table(results):
    if not results:
        print("(no snippets matched)")
        return
    id_w = max(len("ID"), max(len(str(r["id"])) for r in results))
    cat_w = max(len("CATEGORY"), max(len(str(r["category"])) for r in results))
    st_w = max(len("STATUS"), max(len(r["status"]) for r in results))
    header = "%-*s  %-*s  T  %-*s  %s" % (
        id_w, "ID", cat_w, "CATEGORY", st_w, "STATUS", "DETAIL",
    )
    print(header)
    print("-" * min(len(header), 100))
    for r in results:
        detail = r["detail"]
        if len(detail) > 80:
            detail = detail[:77] + "..."
        print(
            "%-*s  %-*s  %d  %-*s  %s"
            % (
                id_w, r["id"],
                cat_w, r["category"],
                r["tier"],
                st_w, r["status"].upper(),
                detail,
            )
        )


if __name__ == "__main__":
    sys.exit(main())

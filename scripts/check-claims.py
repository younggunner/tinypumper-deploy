#!/usr/bin/env python3
"""Page-copy claim gate (SE1, 2026-10-17). Stdlib only, Python 3.9+.

Hard-fails only on pages the push touches; other in-scope hits are backlog.
Tier 2/3 posts are never scanned. JSON-LD is copy; CSS/JS is not.
"""
from __future__ import annotations

import argparse
import glob
import hashlib
import json
import os
import re
import subprocess
import sys
from collections import Counter
from typing import Any, Dict, List, Optional, Tuple

SCOPE_PAGE_TYPES = frozenset({"pillar", "supporting", "comparison"})
ALLOW_BECAUSE = re.compile(
    r"<!--\s*claims-allow:\s*(?P<id>\S+)\s+because\s+\S",
    re.I,
)


def die(msg: str, code: int = 2) -> None:
    sys.stderr.write(msg.rstrip() + "\n")
    raise SystemExit(code)


def _blank_keep_newlines(s: str) -> str:
    return "".join("\n" if c == "\n" else " " for c in s)


def prepare_html(text: str) -> str:
    def repl_style(m: re.Match) -> str:
        return m.group(1) + _blank_keep_newlines(m.group(2)) + m.group(3)

    text = re.sub(
        r"(<style\b[^>]*>)(.*?)(</style>)",
        repl_style,
        text,
        flags=re.I | re.S,
    )

    def repl_script(m: re.Match) -> str:
        open_tag, body, close = m.group(1), m.group(2), m.group(3)
        tm = re.search(r"""type\s*=\s*["']([^"']+)["']""", open_tag, re.I)
        if tm and tm.group(1).strip().lower() == "application/ld+json":
            return m.group(0)
        return open_tag + _blank_keep_newlines(body) + close

    return re.sub(
        r"(<script\b[^>]*>)(.*?)(</script>)",
        repl_script,
        text,
        flags=re.I | re.S,
    )


def prepare_md(text: str) -> str:
    lines = text.splitlines(True)
    out: List[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.strip() == "---":
            nl = "\n" if line.endswith("\n") else ""
            out.append(_blank_keep_newlines(line.rstrip("\n")) + nl)
            i += 1
            continue
        if re.match(r"^architecture-record:\s*", line):
            nl = "\n" if line.endswith("\n") else ""
            out.append(_blank_keep_newlines(line.rstrip("\n")) + nl)
            i += 1
            while i < len(lines) and (
                lines[i].startswith(" ") or lines[i].startswith("\t")
            ):
                child = lines[i]
                nl = "\n" if child.endswith("\n") else ""
                out.append(_blank_keep_newlines(child.rstrip("\n")) + nl)
                i += 1
            continue
        out.append(line)
        i += 1
    return "".join(out)


def _front_matter(text: str) -> Dict[str, str]:
    if not text.startswith("---"):
        return {}
    rest = text[3:]
    if rest.startswith("\n"):
        rest = rest[1:]
    end = rest.find("\n---")
    if end < 0:
        block = rest
    else:
        block = rest[:end]
    fields: Dict[str, str] = {}
    for raw in block.splitlines():
        if ":" not in raw or raw.startswith(" ") or raw.startswith("\t"):
            continue
        key, val = raw.split(":", 1)
        fields[key.strip()] = val.strip().strip("\"'")
    return fields


def gb_brand(rel: str, text: str) -> str:
    if rel == "index.html":
        return "gb"
    fm = _front_matter(text)
    if fm.get("layout") == "post-tinypumper":
        return "tp"
    if fm.get("product_emphasis") == "tinypumper-led":
        return "tp"
    return "gb"


def gb_in_scope(rel: str, text: str) -> bool:
    if rel == "index.html":
        return True
    if not (rel.startswith("_posts/") and rel.endswith(".md")):
        return False
    page_type = _front_matter(text).get("page_type", "")
    return page_type in SCOPE_PAGE_TYPES


def list_scope_paths(repo: str, root: str) -> List[str]:
    found: List[str] = []
    idx = os.path.join(root, "index.html")
    if os.path.isfile(idx):
        found.append("index.html")
    if repo == "gb":
        for p in sorted(glob.glob(os.path.join(root, "_posts", "*.md"))):
            rel = os.path.relpath(p, root).replace(os.sep, "/")
            found.append(rel)
    else:
        for p in sorted(glob.glob(os.path.join(root, "ppc", "*", "index.html"))):
            rel = os.path.relpath(p, root).replace(os.sep, "/")
            found.append(rel)
    return found


def load_rules(path: str) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    if not os.path.isfile(path):
        die("missing rules file: %s" % path)
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        die("malformed rules file: %s (%s)" % (path, exc))
    if not isinstance(data, dict):
        die("malformed rules file: %s (not an object)" % path)
    rules = data.get("rules")
    if not isinstance(rules, list) or not rules:
        die("malformed rules file: empty or missing rules")
    compiled: List[Dict[str, Any]] = []
    for rule in rules:
        if not isinstance(rule, dict):
            die("malformed rules file: rule is not an object")
        for key in ("id", "brand", "kind", "pattern"):
            if key not in rule or not str(rule[key]).strip():
                die("malformed rules file: rule missing %s" % key)
        try:
            cre = re.compile(rule["pattern"], re.I)
        except re.error as exc:
            die("malformed rules file: bad pattern for %s (%s)" % (rule["id"], exc))
        row = dict(rule)
        row["_re"] = cre
        compiled.append(row)
    sha = data.get("source_sha256")
    if sha is not None:
        sha = str(sha)
    return compiled, sha


def _commit_in_clone(root: str, sha: str) -> bool:
    try:
        proc = subprocess.run(
            ["git", "-C", root, "cat-file", "-e", "%s^{commit}" % sha],
            capture_output=True,
            text=True,
        )
    except OSError:
        return False
    return proc.returncode == 0


def git_touched(root: str) -> List[str]:
    raw = os.environ.get("CLAIMS_DIFF_BASE", "HEAD~1")
    base = (raw or "").strip()
    reason = None
    if not base:
        reason = "CLAIMS_DIFF_BASE empty"
        base = "HEAD~1"
    elif set(base) <= {"0"}:
        reason = "CLAIMS_DIFF_BASE all zeros"
        base = "HEAD~1"
    elif not _commit_in_clone(root, base):
        reason = "CLAIMS_DIFF_BASE not a commit in the clone"
        base = "HEAD~1"
    if reason:
        sys.stdout.write("::warning::CLAIMS_DIFF_BASE fallback to HEAD~1 (%s)\n" % reason)
    try:
        proc = subprocess.run(
            ["git", "-C", root, "diff", "--name-only", "--no-renames", base, "HEAD"],
            capture_output=True,
            text=True,
        )
    except OSError as exc:
        die("git failed: %s" % exc)
    if proc.returncode != 0:
        die("git failed: %s" % (proc.stderr or proc.stdout or "exit %s" % proc.returncode))
    return [ln.strip().replace(os.sep, "/") for ln in proc.stdout.splitlines() if ln.strip()]


def without_grandfathered(line: str, rule: Dict[str, Any], rel: str) -> str:
    # Greg 2026-10-27: copy already published when a rule changed is never
    # flagged. Only the phrases listed under this page's path count, so a new
    # page cannot reuse them.
    for phrase in (rule.get("grandfathered") or {}).get(rel) or ():
        line = re.sub(re.escape(phrase), " ", line, flags=re.I)
    return line


def scan_page(
    rel: str,
    text: str,
    brand: str,
    rules: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    prepared = prepare_html(text) if rel.endswith(".html") else prepare_md(text)
    hits: List[Dict[str, Any]] = []
    for i, line in enumerate(prepared.splitlines(), start=1):
        allows = {m.group("id") for m in ALLOW_BECAUSE.finditer(line)}
        for rule in rules:
            if rule["kind"] != "refuse":
                continue
            rbrand = rule["brand"]
            if rbrand != "any" and rbrand != brand:
                continue
            if not rule["_re"].search(without_grandfathered(line, rule, rel)):
                continue
            if rule["id"] in allows:
                continue
            stripped = line.strip()[:200]
            hits.append({
                "path": rel,
                "line": i,
                "rule": rule["id"],
                "brand": brand,
                "text": stripped,
            })
    return hits


def write_summary(backlog: List[Dict[str, Any]]) -> None:
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not path:
        return
    counts = Counter(row["rule"] for row in backlog)
    lines = ["| rule | backlog |", "| --- | ---: |"]
    for rule, n in sorted(counts.items()):
        lines.append("| %s | %s |" % (rule, n))
    if not counts:
        lines.append("| _(none)_ | 0 |")
    with open(path, "a", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")


def why_for(rule_id: str, rules: List[Dict[str, Any]]) -> str:
    for rule in rules:
        if rule["id"] == rule_id:
            w = rule.get("why")
            if w:
                return str(w)
            return rule_id
    return rule_id


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description="SE1 page claim check")
    p.add_argument("--repo", required=True)
    p.add_argument("--root", default=".")
    p.add_argument("--rules", default=None)
    p.add_argument("--touched", nargs="*", default=None)
    p.add_argument("--report", default=None)
    args = p.parse_args(argv)

    if args.repo not in ("gb", "tp"):
        die("--repo must be gb or tp")

    root = os.path.abspath(args.root)
    rules_path = args.rules or os.path.join(root, ".github", "claim-rules.json")
    rules, source_sha = load_rules(rules_path)
    if source_sha is None:
        try:
            with open(rules_path, "rb") as fh:
                source_sha = hashlib.sha256(fh.read()).hexdigest()
        except OSError:
            source_sha = ""

    if args.touched is None:
        touched_list = git_touched(root)
    else:
        touched_list = list(args.touched)
    touched = {t.replace(os.sep, "/") for t in touched_list}

    scanned: List[str] = []
    failures: List[Dict[str, Any]] = []
    backlog: List[Dict[str, Any]] = []

    for rel in list_scope_paths(args.repo, root):
        abs_path = os.path.join(root, rel.replace("/", os.sep))
        if not os.path.isfile(abs_path):
            continue
        with open(abs_path, "rb") as fh:
            raw = fh.read()
        loose = raw.decode("utf-8", errors="replace")

        if args.repo == "gb" and not gb_in_scope(rel, loose):
            continue

        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            die("not valid UTF-8: %s" % rel)

        if args.repo == "gb":
            brand = gb_brand(rel, text)
        else:
            brand = "tp"

        scanned.append(rel)
        hits = scan_page(rel, text, brand, rules)
        if rel in touched:
            failures.extend(hits)
        else:
            backlog.extend(hits)

    report = {
        "repo": args.repo,
        "rules_source_sha256": source_sha or "",
        "scanned": scanned,
        "failures": failures,
        "backlog": backlog,
    }
    if args.report:
        parent = os.path.dirname(os.path.abspath(args.report))
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(args.report, "w", encoding="utf-8") as fh:
            json.dump(report, fh, indent=2)
            fh.write("\n")

    for row in failures:
        why = why_for(row["rule"], rules)
        sys.stdout.write(
            "::error file=%s,line=%s::%s: %s\n" % (row["path"], row["line"], row["rule"], why)
        )
    sys.stdout.write("::warning::%s backlog violation(s)\n" % len(backlog))
    write_summary(backlog)
    return 1 if failures else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception as exc:
        die("check-claims failed: %s" % exc)

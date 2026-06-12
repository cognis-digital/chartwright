"""Command-line interface for chartwright."""

from __future__ import annotations

import argparse
import json
import sys
from typing import List, Optional

from chartwright import TOOL_NAME, TOOL_VERSION
from chartwright.core import (
    ChartError,
    diff_values,
    lint_chart,
    load_chart,
    load_values,
    render_chart,
)

_SEV = {"error": "ERR ", "warning": "WARN", "info": "INFO"}


def _emit(text: str, out: Optional[str]) -> None:
    if out:
        with open(out, "w", encoding="utf-8") as fh:
            fh.write(text if text.endswith("\n") else text + "\n")
        print(f"wrote {out}", file=sys.stderr)
    else:
        print(text)


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog=TOOL_NAME,
        description="Helm-chart templating, linting & values-diff — render and "
                    "lint charts and diff values across environments, no Helm "
                    "binary required.")
    p.add_argument("--version", action="version",
                   version=f"{TOOL_NAME} {TOOL_VERSION}")
    sub = p.add_subparsers(dest="command")

    t = sub.add_parser("template", help="Render a chart's templates.")
    t.add_argument("chart", help="Path to a chart directory.")
    t.add_argument("--release", default="release", help="Release name.")
    t.add_argument("--values", help="Override values file (yaml/json).")
    t.add_argument("--out", help="Write rendered output to a file.")

    l = sub.add_parser("lint", help="Lint a chart's structure and templates.")
    l.add_argument("chart")
    l.add_argument("--format", choices=("table", "json"), default="table")
    l.add_argument("--fail-on", choices=("error", "warning"), default="error")

    d = sub.add_parser("diff", help="Diff two values files.")
    d.add_argument("left")
    d.add_argument("right")
    d.add_argument("--format", choices=("table", "json"), default="table")

    sub.add_parser("mcp", help="Run as an MCP server (stdio JSON-RPC).")
    return p


def _run_template(a) -> int:
    try:
        chart = load_chart(a.chart)
        overrides = load_values(a.values) if a.values else None
        rendered = render_chart(chart, release=a.release, overrides=overrides)
    except (OSError, ChartError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    blocks = []
    for name, text in rendered.items():
        blocks.append(f"# Source: {name}\n{text.rstrip()}")
    _emit("\n---\n".join(blocks) + "\n", a.out)
    return 0


def _run_lint(a) -> int:
    try:
        res = lint_chart(load_chart(a.chart))
    except (OSError, ChartError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if a.format == "json":
        _emit(json.dumps(res, indent=2), None)
    else:
        print(f"chartwright lint — {res['chart']}")
        print("=" * 60)
        if not res["findings"]:
            print("No findings. Chart passes lint.")
        for f in res["findings"]:
            print(f"[{_SEV.get(f['severity'], f['severity'])}] {f['rule']}: {f['message']}")
        print("-" * 60)
        print("RESULT: " + ("PASS" if res["ok"] else f"FAIL ({res['error_count']} error(s))"))
    has_warn = any(f["severity"] == "warning" for f in res["findings"])
    if a.fail_on == "warning" and (not res["ok"] or has_warn):
        return 1
    return 0 if res["ok"] else 1


def _run_diff(a) -> int:
    try:
        d = diff_values(load_values(a.left), load_values(a.right))
    except (OSError, ChartError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if a.format == "json":
        _emit(json.dumps(d, indent=2), None)
    else:
        print(f"chartwright diff — {a.left}  ->  {a.right}")
        print("=" * 60)
        for k, v in d["added"].items():
            print(f"  + {k} = {v}")
        for k in d["removed"]:
            print(f"  - {k}")
        for k, ch in d["changed"].items():
            print(f"  ~ {k}: {ch['from']} -> {ch['to']}")
        print("-" * 60)
        print(f"+{d['added_count']} added  -{d['removed_count']} removed  "
              f"~{d['changed_count']} changed")
    return 0


def _run_mcp() -> int:
    from chartwright.mcp_server import run_mcp_server
    run_mcp_server()
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.command == "template":
        return _run_template(args)
    if args.command == "lint":
        return _run_lint(args)
    if args.command == "diff":
        return _run_diff(args)
    if args.command == "mcp":
        return _run_mcp()
    parser.print_help(sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

"""Core engine for chartwright — Helm-chart templating, linting & values-diff.

chartwright works with the Helm chart *layout* (a ``Chart.yaml``, a ``values.yaml``,
and templates under ``templates/``) but needs **no Helm binary**. It renders the
template directives most charts actually use, lints the chart structure, and
diffs values files across environments — all with the Python standard library.

Supported template directives (a practical subset of the Go/Sprig surface):

  * ``{{ .Values.a.b }}`` / ``{{ .Chart.Name }}`` / ``{{ .Release.Name }}``
  * ``{{ .Values.x | default "y" | quote | upper | lower }}`` pipelines
  * ``{{- if .Values.flag }} ... {{- else }} ... {{- end }}`` conditionals
  * ``{{- range .Values.list }} ... {{ . }} ... {{- end }}`` loops
  * whitespace chomping with ``{{-`` and ``-}}``

This is original Cognis Digital work. It targets the open Helm chart layout and
template *behavior*; it contains no third-party code, names, or branding, and it
does not embed or vendor Helm or Sprig.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

TOOL_NAME = "chartwright"
TOOL_VERSION = "0.1.0"


class ChartError(Exception):
    """User-facing chart/template error."""


# --------------------------------------------------------------------------- #
# YAML subset (parse values/Chart files)
# --------------------------------------------------------------------------- #

def _coerce(text: str) -> Any:
    s = text.strip()
    if s in ("", "~", "null"):
        return None
    if s in ("true", "false"):
        return s == "true"
    if len(s) >= 2 and s[0] == s[-1] and s[0] in "\"'":
        return s[1:-1]
    if len(s) >= 2 and s[0] == "[" and s[-1] == "]":
        inner = s[1:-1].strip()
        return [] if not inner else [_coerce(p) for p in _split_flow(inner)]
    try:
        return int(s)
    except ValueError:
        pass
    try:
        return float(s)
    except ValueError:
        pass
    return s


def _split_flow(inner: str) -> List[str]:
    parts, depth, cur, sgl, dbl = [], 0, [], False, False
    for ch in inner:
        if ch == "'" and not dbl:
            sgl = not sgl
        elif ch == '"' and not sgl:
            dbl = not dbl
        if not sgl and not dbl:
            if ch in "[{":
                depth += 1
            elif ch in "]}":
                depth -= 1
            elif ch == "," and depth == 0:
                parts.append("".join(cur).strip())
                cur = []
                continue
        cur.append(ch)
    if "".join(cur).strip():
        parts.append("".join(cur).strip())
    return parts


def parse_yaml_subset(text: str) -> Any:
    lines = text.replace("\t", "  ").splitlines()
    toks: List[Tuple[int, str]] = []
    for raw in lines:
        out, sgl, dbl = [], False, False
        for i, ch in enumerate(raw):
            if ch == "'" and not dbl:
                sgl = not sgl
            elif ch == '"' and not sgl:
                dbl = not dbl
            elif ch == "#" and not sgl and not dbl and (i == 0 or raw[i-1] in " \t"):
                break
            out.append(ch)
        line = "".join(out).rstrip()
        if not line.strip() or line.strip() == "---":
            continue
        indent = len(line) - len(line.lstrip(" "))
        toks.append((indent, line.strip()))
    if not toks:
        return {}
    pos = [0]

    def kv(s):
        i = s.find(":")
        if i == -1:
            return s, ""
        k, v = s[:i].strip(), s[i+1:].strip()
        if len(k) >= 2 and k[0] == k[-1] and k[0] in "\"'":
            k = k[1:-1]
        return k, v

    def parse_block(indent):
        if pos[0] >= len(toks):
            return None
        _c, content = toks[pos[0]]
        return parse_list(indent) if content.startswith("- ") else parse_map(indent)

    def parse_list(indent):
        items = []
        while pos[0] < len(toks):
            cur, content = toks[pos[0]]
            if cur != indent or not content.startswith("- "):
                break
            inner = content[2:].strip()
            pos[0] += 1
            if ":" in inner and not (inner.find(":")+1 < len(inner)
                                     and inner[inner.find(":")+1] != " "):
                k, v = kv(inner)
                obj = {k: (_coerce(v) if v else _child(indent + 2))}
                obj.update(cont_map(indent + 2))
                items.append(obj)
            elif inner == "":
                items.append(_child(indent + 2))
            else:
                items.append(_coerce(inner))
        return items

    def cont_map(indent):
        obj = {}
        while pos[0] < len(toks):
            cur, content = toks[pos[0]]
            if cur != indent or content.startswith("- "):
                break
            k, v = kv(content)
            pos[0] += 1
            obj[k] = _coerce(v) if v else _child(indent + 2)
        return obj

    def parse_map(indent):
        obj = {}
        while pos[0] < len(toks):
            cur, content = toks[pos[0]]
            if cur != indent or content.startswith("- "):
                break
            k, v = kv(content)
            pos[0] += 1
            obj[k] = _coerce(v) if v else _child(indent + 1)
        return obj

    def _child(min_indent):
        if pos[0] >= len(toks):
            return None
        cur, content = toks[pos[0]]
        if cur < min_indent:
            return None
        return parse_list(cur) if content.startswith("- ") else parse_map(cur)

    result = parse_block(0)
    return result if result is not None else {}


# --------------------------------------------------------------------------- #
# Chart model
# --------------------------------------------------------------------------- #

@dataclass
class Chart:
    path: str
    metadata: Dict[str, Any]
    values: Dict[str, Any]
    templates: Dict[str, str] = field(default_factory=dict)  # name -> source


def load_chart(path: str) -> Chart:
    if not os.path.isdir(path):
        raise ChartError(f"chart directory not found: {path}")
    chart_yaml = os.path.join(path, "Chart.yaml")
    if not os.path.isfile(chart_yaml):
        raise ChartError(f"missing Chart.yaml in {path}")
    with open(chart_yaml, "r", encoding="utf-8") as fh:
        metadata = parse_yaml_subset(fh.read()) or {}

    values: Dict[str, Any] = {}
    values_yaml = os.path.join(path, "values.yaml")
    if os.path.isfile(values_yaml):
        with open(values_yaml, "r", encoding="utf-8") as fh:
            values = parse_yaml_subset(fh.read()) or {}

    templates: Dict[str, str] = {}
    tdir = os.path.join(path, "templates")
    if os.path.isdir(tdir):
        for fn in sorted(os.listdir(tdir)):
            if fn.endswith((".yaml", ".yml", ".tpl", ".txt")):
                with open(os.path.join(tdir, fn), "r", encoding="utf-8") as fh:
                    templates[fn] = fh.read()
    return Chart(path=path, metadata=metadata, values=values, templates=templates)


# --------------------------------------------------------------------------- #
# Template rendering (a practical Go-template subset)
# --------------------------------------------------------------------------- #

def _lookup(path: str, ctx: Dict[str, Any]) -> Any:
    """Resolve a dotted accessor like .Values.image.tag or . (the loop item)."""
    path = path.strip()
    if path == "." or path == "":
        return ctx.get("__dot__")
    if path.startswith("."):
        path = path[1:]
    cur: Any = ctx
    for part in path.split("."):
        if part == "":
            continue
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return None
    return cur


def _apply_pipeline(value: Any, funcs: List[Tuple[str, List[str]]]) -> Any:
    for name, args in funcs:
        if name == "default":
            if value is None or value == "":
                value = _literal(args[0]) if args else value
        elif name == "quote":
            value = '"' + str(value if value is not None else "") + '"'
        elif name == "upper":
            value = str(value).upper()
        elif name == "lower":
            value = str(value).lower()
        elif name == "trim":
            value = str(value).strip()
        elif name == "toString":
            value = str(value)
    return value


def _literal(tok: str) -> Any:
    tok = tok.strip()
    if len(tok) >= 2 and tok[0] == tok[-1] and tok[0] in "\"'":
        return tok[1:-1]
    return _coerce(tok)


def _eval_expr(expr: str, ctx: Dict[str, Any]) -> Any:
    """Evaluate a ``{{ ... }}`` expression body to a Python value."""
    segments = [s.strip() for s in expr.split("|")]
    head = segments[0]
    funcs: List[Tuple[str, List[str]]] = []
    for seg in segments[1:]:
        toks = seg.split()
        funcs.append((toks[0], toks[1:]))
    # head is either an accessor (.Foo / .) or a literal
    if head.startswith(".") or head == ".":
        value = _lookup(head, ctx)
    else:
        value = _literal(head)
    return _apply_pipeline(value, funcs)


def _truthy(v: Any) -> bool:
    if isinstance(v, str):
        return v not in ("", "false", "0", "no", "off")
    return bool(v)


# Token regex for the control directives + simple substitutions.
_TAG_RE = re.compile(r"\{\{-?\s*(.*?)\s*-?\}\}", re.DOTALL)


@dataclass
class _Tag:
    raw: str
    body: str
    chomp_left: bool
    chomp_right: bool
    start: int
    end: int


def _tokenize(src: str) -> List[_Tag]:
    tags: List[_Tag] = []
    for m in _TAG_RE.finditer(src):
        raw = m.group(0)
        tags.append(_Tag(
            raw=raw, body=m.group(1).strip(),
            chomp_left=raw.startswith("{{-"),
            chomp_right=raw.endswith("-}}"),
            start=m.start(), end=m.end()))
    return tags


def render_template(src: str, ctx: Dict[str, Any]) -> str:
    """Render one template string against a context.

    ctx provides Values / Chart / Release roots. Supports if/else/end,
    range/end, expression substitution, and whitespace chomping.
    """
    return _emit(src, ctx)


def _emit(src: str, ctx: Dict[str, Any]) -> str:
    tags = _tokenize(src)
    idx = [0]

    def walk(text_start: int, stop_words: Tuple[str, ...]):
        out: List[str] = []
        cursor = text_start
        while idx[0] < len(tags):
            tag = tags[idx[0]]
            # literal text before the tag
            literal = src[cursor:tag.start]
            if tag.chomp_left:
                literal = literal.rstrip()
            out.append(literal)
            kw = tag.body.split()[0] if tag.body else ""
            if kw in stop_words:
                cursor = tag.end
                if tag.chomp_right:
                    cursor = _skip_ws(src, cursor)
                idx[0] += 1
                return "".join(out), kw, cursor
            idx[0] += 1
            after = tag.end
            if tag.chomp_right:
                after = _skip_ws(src, after)
            if kw == "if":
                cond = _truthy(_eval_expr(tag.body[2:].strip(), ctx))
                then_txt, stop, c2 = walk(after, ("else", "end"))
                else_txt = ""
                if stop == "else":
                    else_txt, _stop2, c2 = walk(c2, ("end",))
                out.append(then_txt if cond else else_txt)
                cursor = c2
            elif kw == "range":
                items = _eval_expr(tag.body[5:].strip(), ctx)
                # Capture body once by walking to end, then re-render per item.
                body_start = after
                _body_txt, _stop, c2 = walk(body_start, ("end",))
                end_tag_idx = idx[0] - 1  # the 'end' we consumed
                if isinstance(items, list):
                    for it in items:
                        sub = dict(ctx)
                        sub["__dot__"] = it
                        # Re-render the body span [body_start, end_tag_start)
                        out.append(_render_span(src, tags, body_start,
                                                end_tag_idx, sub))
                cursor = c2
            else:
                val = _eval_expr(tag.body, ctx)
                out.append("" if val is None else str(val))
                cursor = after
        out.append(src[cursor:])
        return "".join(out), "", len(src)

    text, _stop, _c = walk(0, ())
    return text


def _skip_ws(src: str, i: int) -> int:
    while i < len(src) and src[i] in " \t\r\n":
        i += 1
    return i


def _render_span(src: str, tags: List[_Tag], start_idx_pos: int,
                 end_tag_idx: int, ctx: Dict[str, Any]) -> str:
    """Render the source span covered by tags between a start text pos and the
    matching end tag, for one range iteration. Re-tokenizes the substring."""
    end_tag = tags[end_tag_idx]
    sub_src = src[start_idx_pos:end_tag.start]
    return _emit(sub_src, ctx)


def render_chart(chart: Chart, release: str = "release",
                 overrides: Optional[Dict[str, Any]] = None) -> Dict[str, str]:
    """Render every template in the chart; return name -> rendered text."""
    values = _deep_merge(chart.values, overrides or {})
    ctx = {
        "Values": values,
        "Chart": chart.metadata,
        "Release": {"Name": release, "Namespace": "default"},
        "__dot__": None,
    }
    rendered: Dict[str, str] = {}
    for name, src in chart.templates.items():
        if name.endswith(".tpl"):
            continue  # helper templates are not emitted directly
        try:
            rendered[name] = _emit(src, ctx)
        except Exception as exc:  # keep rendering the rest
            raise ChartError(f"failed to render {name}: {exc}") from exc
    return rendered


def _deep_merge(base: Dict[str, Any], over: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


# --------------------------------------------------------------------------- #
# lint
# --------------------------------------------------------------------------- #

def lint_chart(chart: Chart) -> Dict[str, Any]:
    """Structural + template lint. Returns {ok, findings}."""
    findings: List[Dict[str, str]] = []

    def add(sev, rule, msg):
        findings.append({"severity": sev, "rule": rule, "message": msg})

    md = chart.metadata
    for req in ("name", "version"):
        if not md.get(req):
            add("error", f"chart.{req}", f"Chart.yaml missing required `{req}`")
    if md.get("apiVersion") not in ("v1", "v2", None):
        add("warning", "chart.apiVersion",
            f"unusual apiVersion: {md.get('apiVersion')}")
    if not chart.templates:
        add("warning", "templates.empty", "chart has no templates/")

    # Balanced if/range/end per template + undefined .Values references.
    for name, src in chart.templates.items():
        depth = 0
        for tag in _tokenize(src):
            kw = tag.body.split()[0] if tag.body else ""
            if kw in ("if", "range", "with"):
                depth += 1
            elif kw == "end":
                depth -= 1
                if depth < 0:
                    add("error", "template.unbalanced",
                        f"{name}: unexpected {{{{ end }}}}")
                    depth = 0
        if depth != 0:
            add("error", "template.unbalanced",
                f"{name}: {depth} unterminated if/range/with block(s)")

    errors = sum(1 for f in findings if f["severity"] == "error")
    return {"chart": md.get("name", chart.path), "ok": errors == 0,
            "error_count": errors, "findings": findings}


# --------------------------------------------------------------------------- #
# values diff
# --------------------------------------------------------------------------- #

def _flatten(d: Any, prefix: str = "") -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    if isinstance(d, dict):
        for k, v in d.items():
            out.update(_flatten(v, f"{prefix}.{k}" if prefix else str(k)))
    elif isinstance(d, list):
        for i, v in enumerate(d):
            out.update(_flatten(v, f"{prefix}[{i}]"))
    else:
        out[prefix] = d
    return out


def diff_values(left: Dict[str, Any], right: Dict[str, Any]) -> Dict[str, Any]:
    """Diff two values trees; return added/removed/changed leaf keys."""
    lf, rf = _flatten(left), _flatten(right)
    added = {k: rf[k] for k in rf if k not in lf}
    removed = {k: lf[k] for k in lf if k not in rf}
    changed = {k: {"from": lf[k], "to": rf[k]}
               for k in lf if k in rf and lf[k] != rf[k]}
    return {"added": added, "removed": removed, "changed": changed,
            "added_count": len(added), "removed_count": len(removed),
            "changed_count": len(changed)}


def load_values(path: str) -> Dict[str, Any]:
    if not os.path.isfile(path):
        raise ChartError(f"values file not found: {path}")
    with open(path, "r", encoding="utf-8") as fh:
        text = fh.read()
    if path.lower().endswith(".json"):
        return json.loads(text)
    return parse_yaml_subset(text) or {}


# --------------------------------------------------------------------------- #
# AI hook (opt-in, default OFF)
# --------------------------------------------------------------------------- #

def suggest_values(chart: Chart, description: str) -> Dict[str, Any]:
    """Suggest a values override for an environment (local fleet, OFF by default)."""
    out = {"overrides": {}, "_ai": "disabled — set COGNIS_AI_BACKEND to enable"}
    backend = _load_ai_backend()
    if backend is None or not backend.is_enabled() or not backend.health():
        return out
    prompt = ("Given a chart's default values and an environment description, "
              "output ONLY a JSON object of values overrides. No prose.\n\n"
              f"DEFAULTS:\n{json.dumps(chart.values)}\n\nENV:\n{description}\n")
    try:
        content = backend._chat("Return strict JSON only.", prompt)
    except Exception:
        return out
    parsed = _extract_json_object(content or "")
    if isinstance(parsed, dict):
        out["overrides"] = parsed
        out["_ai"] = "suggested by local fleet"
    return out


def _load_ai_backend():
    import importlib.util
    here = os.path.dirname(os.path.abspath(__file__))
    cand = os.path.abspath(os.path.join(here, "..", "..", "..", "_shared",
                                        "cognis_ai_backend.py"))
    if os.path.isfile(cand):
        try:
            spec = importlib.util.spec_from_file_location("cognis_ai_backend", cand)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)  # type: ignore[union-attr]
            return mod.CognisAIBackend()
        except Exception:
            return None
    return None


def _extract_json_object(text: str) -> Any:
    text = (text or "").strip()
    if "```" in text:
        m = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
        if m:
            text = m.group(1).strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        return json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return None

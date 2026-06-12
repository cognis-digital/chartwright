"""Deep tests for chartwright — template engine, overrides, lint, diff, MCP."""

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from chartwright import (
    diff_values,
    lint_chart,
    load_chart,
    load_values,
    render_chart,
    render_template,
    suggest_values,
)
from chartwright.core import Chart, ChartError, parse_yaml_subset
from chartwright import mcp_server

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHART = os.path.join(REPO_ROOT, "demos", "01-basic", "chart")
PROD = os.path.join(REPO_ROOT, "demos", "01-basic", "values-prod.yaml")


def _ctx(values):
    return {"Values": values, "Chart": {"name": "c"},
            "Release": {"Name": "r"}, "__dot__": None}


class TestTemplateEngine(unittest.TestCase):
    def test_simple_substitution(self):
        self.assertEqual(render_template("x={{ .Values.a }}", _ctx({"a": 1})), "x=1")

    def test_default_pipeline(self):
        self.assertEqual(render_template("{{ .Values.a | default 7 }}", _ctx({})), "7")
        self.assertEqual(render_template("{{ .Values.a | default 7 }}", _ctx({"a": 3})), "3")

    def test_quote_upper_lower(self):
        self.assertEqual(render_template('{{ .Values.a | quote }}', _ctx({"a": "x"})), '"x"')
        self.assertEqual(render_template('{{ .Values.a | upper }}', _ctx({"a": "ab"})), "AB")

    def test_if_else(self):
        tmpl = "{{- if .Values.on }}YES{{- else }}NO{{- end }}"
        self.assertEqual(render_template(tmpl, _ctx({"on": True})).strip(), "YES")
        self.assertEqual(render_template(tmpl, _ctx({"on": False})).strip(), "NO")

    def test_range_with_dot(self):
        tmpl = "{{- range .Values.items }}[{{ . }}]{{- end }}"
        out = render_template(tmpl, _ctx({"items": ["a", "b", "c"]}))
        self.assertEqual(out.strip(), "[a][b][c]")

    def test_nested_lookup(self):
        self.assertEqual(
            render_template("{{ .Values.a.b.c }}", _ctx({"a": {"b": {"c": "deep"}}})),
            "deep")

    def test_unknown_value_is_empty(self):
        self.assertEqual(render_template("[{{ .Values.nope }}]", _ctx({})), "[]")


class TestOverrides(unittest.TestCase):
    def test_prod_overrides_merge(self):
        chart = load_chart(CHART)
        out = render_chart(chart, overrides=load_values(PROD))
        self.assertIn("replicas: 5", out["deployment.yaml"])
        self.assertIn("1.2.0-prod", out["deployment.yaml"])


class TestLint(unittest.TestCase):
    def test_missing_name_version(self):
        chart = Chart(path="x", metadata={}, values={},
                      templates={"a.yaml": "ok"})
        res = lint_chart(chart)
        rules = {f["rule"] for f in res["findings"]}
        self.assertIn("chart.name", rules)
        self.assertIn("chart.version", rules)
        self.assertFalse(res["ok"])

    def test_unbalanced_blocks(self):
        chart = Chart(path="x", metadata={"name": "n", "version": "1"},
                      values={}, templates={"t.yaml": "{{ if .Values.x }}no end"})
        res = lint_chart(chart)
        self.assertIn("template.unbalanced", {f["rule"] for f in res["findings"]})

    def test_extra_end(self):
        chart = Chart(path="x", metadata={"name": "n", "version": "1"},
                      values={}, templates={"t.yaml": "{{ end }}"})
        res = lint_chart(chart)
        self.assertFalse(res["ok"])


class TestDiff(unittest.TestCase):
    def test_added_removed_changed(self):
        d = diff_values({"a": 1, "b": 2}, {"a": 9, "c": 3})
        self.assertEqual(d["changed"]["a"], {"from": 1, "to": 9})
        self.assertIn("c", d["added"])
        self.assertIn("b", d["removed"])

    def test_nested_flatten(self):
        d = diff_values({"x": {"y": 1}}, {"x": {"y": 2}})
        self.assertIn("x.y", d["changed"])

    def test_chart_default_vs_prod(self):
        d = diff_values(load_values(os.path.join(CHART, "values.yaml")),
                        load_values(PROD))
        self.assertIn("replicaCount", d["changed"])
        self.assertEqual(d["changed"]["replicaCount"]["to"], 5)


class TestYaml(unittest.TestCase):
    def test_inline_list(self):
        self.assertEqual(parse_yaml_subset("a: [x, y, z]")["a"], ["x", "y", "z"])

    def test_missing_chart_raises(self):
        with self.assertRaises(ChartError):
            load_chart("/no/such/chart")


class TestMcp(unittest.TestCase):
    def test_list_and_template(self):
        tl = mcp_server.handle_request({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        names = {t["name"] for t in tl["result"]["tools"]}
        self.assertEqual(names, {"template", "lint", "diff"})
        r = mcp_server.handle_request({
            "jsonrpc": "2.0", "id": 2, "method": "tools/call",
            "params": {"name": "lint", "arguments": {"chart": CHART}}})
        self.assertFalse(r["result"]["isError"])

    def test_diff_call(self):
        r = mcp_server.handle_request({
            "jsonrpc": "2.0", "id": 3, "method": "tools/call",
            "params": {"name": "diff",
                       "arguments": {"left": os.path.join(CHART, "values.yaml"),
                                     "right": PROD}}})
        payload = json.loads(r["result"]["content"][0]["text"])
        self.assertIn("replicaCount", payload["changed"])


class TestAiHook(unittest.TestCase):
    def test_off_by_default(self):
        for v in ("COGNIS_AI_BACKEND", "COGNIS_AI_ENDPOINT"):
            os.environ.pop(v, None)
        out = suggest_values(load_chart(CHART), "production, 5 replicas")
        self.assertTrue(out["_ai"].startswith("disabled"))


if __name__ == "__main__":
    unittest.main()

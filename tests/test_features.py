"""Feature tests for chartwright — --set overrides, values schema, CLI."""

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from chartwright import (
    Chart, load_chart, parse_set_overrides, render_chart, values_schema,
)
from chartwright.core import ChartError
from chartwright.cli import main

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHART = os.path.join(REPO_ROOT, "demos", "01-basic", "chart")


class TestSetOverrides(unittest.TestCase):
    def test_parse_nested(self):
        ov = parse_set_overrides(["image.repository=ghcr.io/x", "replicaCount=5"])
        self.assertEqual(ov["image"]["repository"], "ghcr.io/x")  # string kept
        self.assertEqual(ov["replicaCount"], 5)   # coerced to int

    def test_quoted_value_stays_string(self):
        ov = parse_set_overrides(['image.tag="2.0"'])
        self.assertEqual(ov["image"]["tag"], "2.0")  # quotes force string

    def test_bad_format(self):
        with self.assertRaises(ChartError):
            parse_set_overrides(["noequals"])

    def test_set_applied_to_render(self):
        chart = load_chart(CHART)
        ov = parse_set_overrides(["image.tag=9.9.9"])
        out = render_chart(chart, overrides=ov)
        self.assertIn("9.9.9", out["deployment.yaml"])


class TestValuesSchema(unittest.TestCase):
    def test_demo_paths_declared(self):
        sch = values_schema(load_chart(CHART))
        self.assertIn("replicaCount", sch["used"])
        self.assertIn("image.repository", sch["used"])
        self.assertIn("service.port", sch["used"])
        # all demo references have defaults in values.yaml
        self.assertEqual(sch["undeclared"], [])

    def test_undeclared_detected(self):
        chart = Chart(path="x", metadata={"name": "c", "version": "1"},
                      values={"a": 1},
                      templates={"t.yaml": "x: {{ .Values.missing.deep }}"})
        sch = values_schema(chart)
        self.assertIn("missing.deep", sch["undeclared"])


class TestCliFeatures(unittest.TestCase):
    def test_template_with_set(self):
        self.assertEqual(main(["template", CHART, "--set", "image.tag=3.3.3"]), 0)

    def test_schema_cli(self):
        self.assertEqual(main(["schema", CHART]), 0)

    def test_schema_json(self):
        self.assertEqual(main(["schema", CHART, "--format", "json"]), 0)

    def test_schema_fail_on_undeclared_passes_for_clean_chart(self):
        self.assertEqual(main(["schema", CHART, "--fail-on-undeclared"]), 0)

    def test_schema_fail_on_undeclared_trips(self):
        with tempfile.TemporaryDirectory() as tmp:
            cdir = os.path.join(tmp, "c")
            os.makedirs(os.path.join(cdir, "templates"))
            with open(os.path.join(cdir, "Chart.yaml"), "w") as fh:
                fh.write("apiVersion: v2\nname: c\nversion: 1.0.0\n")
            with open(os.path.join(cdir, "values.yaml"), "w") as fh:
                fh.write("a: 1\n")
            with open(os.path.join(cdir, "templates", "t.yaml"), "w") as fh:
                fh.write("x: {{ .Values.nope.here }}\n")
            self.assertEqual(main(["schema", cdir, "--fail-on-undeclared"]), 1)


if __name__ == "__main__":
    unittest.main()

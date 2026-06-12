"""Smoke tests for chartwright. Standard library only."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from chartwright import TOOL_NAME, TOOL_VERSION, load_chart, render_chart, lint_chart
from chartwright.cli import main

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHART = os.path.join(REPO_ROOT, "demos", "01-basic", "chart")
PROD = os.path.join(REPO_ROOT, "demos", "01-basic", "values-prod.yaml")


class TestMetadata(unittest.TestCase):
    def test_metadata(self):
        self.assertEqual(TOOL_NAME, "chartwright")
        self.assertTrue(TOOL_VERSION)


class TestRender(unittest.TestCase):
    def test_render_substitutes(self):
        chart = load_chart(CHART)
        out = render_chart(chart, release="prod")
        dep = out["deployment.yaml"]
        self.assertIn("prod-hello-edge", dep)
        self.assertIn("localhost:5000/hello-edge:1.2.0", dep)
        self.assertIn("replicas: 2", dep)
        # range over env list
        self.assertIn("name: LOG_LEVEL", dep)
        self.assertIn("name: CACHE_HOST", dep)

    def test_if_branch(self):
        chart = load_chart(CHART)
        out = render_chart(chart)
        self.assertIn("kind: Service", out["service.yaml"])

    def test_lint_passes(self):
        self.assertTrue(lint_chart(load_chart(CHART))["ok"])


class TestCli(unittest.TestCase):
    def test_template(self):
        self.assertEqual(main(["template", CHART]), 0)

    def test_lint(self):
        self.assertEqual(main(["lint", CHART]), 0)

    def test_diff(self):
        values = os.path.join(CHART, "values.yaml")
        self.assertEqual(main(["diff", values, PROD]), 0)

    def test_no_command_exits_2(self):
        self.assertEqual(main([]), 2)

    def test_missing_chart_exits_2(self):
        self.assertEqual(main(["lint", "/no/such/chart"]), 2)


if __name__ == "__main__":
    unittest.main()

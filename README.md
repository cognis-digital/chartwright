# chartwright

**Helm-chart templating, linting & values-diff — without a Helm binary.** Render
the template directives charts actually use, lint chart structure, and diff
values files across environments, all in pure Python.

Part of the **Cognis Neural Suite**.

---

## Why

You don't always have (or want) a Helm install in CI, in an air-gap, or in a
quick pre-commit hook. chartwright reads the standard Helm chart layout
(`Chart.yaml`, `values.yaml`, `templates/`) and renders the practical subset of
Go/Sprig template behavior most charts rely on — no binary, no pip installs.

## Commands

```bash
# Render a chart's templates against its values.
python -m chartwright template ./mychart --release prod

# Merge an environment-specific values override.
python -m chartwright template ./mychart --values values-prod.yaml

# Lint structure + balanced if/range/with blocks.
python -m chartwright lint ./mychart
python -m chartwright lint ./mychart --fail-on warning

# Diff two values files (added / removed / changed leaf keys).
python -m chartwright diff values.yaml values-prod.yaml

# Run as a local MCP server (stdio JSON-RPC).
python -m chartwright mcp
```

## Template directives supported

- `{{ .Values.a.b }}`, `{{ .Chart.name }}`, `{{ .Release.Name }}`
- pipelines: `{{ .Values.x | default "y" | quote | upper | lower | trim }}`
- conditionals: `{{- if .Values.flag }} … {{- else }} … {{- end }}`
- loops: `{{- range .Values.list }} … {{ . }} … {{- end }}`
- whitespace chomping with `{{-` and `-}}`

## What sets chartwright apart

- **No Helm dependency.** Render and lint in environments where installing Helm
  is impractical.
- **Values diffing built in.** Catch drift between `values.yaml` and a prod
  override before it ships — flattened, leaf-level, easy to read.
- **MCP-native** (`template` / `lint` / `diff`) and an opt-in local-fleet AI hook
  (default OFF) that suggests a values override for an environment.
- **Pairs with the air-gap suite:** lint and render with chartwright, mirror the
  images with [oradeck](https://github.com/cognis-digital/oradeck), and bundle
  the app with [airlock](https://github.com/cognis-digital/airlock).

## Tests

```bash
python -m pytest -q     # or: python -m unittest discover -s tests
```

## Interoperability

`{}` composes with the 300+ tool Cognis suite — JSON in/out and a shared
OpenAI-compatible `/v1` backbone. See **[INTEROP.md](INTEROP.md)** for the
suite map, composition patterns, and reference stacks.

## License

Cognis Open Collaboration License (COCL) 1.0 — see [`LICENSE`](LICENSE).
© 2026 Cognis Digital LLC. Original Cognis work targeting the open Helm chart
layout and template behavior; it does not embed or vendor Helm or Sprig, and
contains no third-party code, names, or branding.

<!-- cognis:domains:start -->
## Domains

**Primary domain:** Cyber & Security  ·  **JTF MERIDIAN division:** NULLBYTE · SPECTER

**Topics:** `cognis` `security` `infosec` `cybersecurity` `blue-team`

Part of the **Cognis Neural Suite** — 300+ source-available tools organized across 12 domains under the JTF MERIDIAN command structure. See the [suite on GitHub](https://github.com/cognis-digital) and [jtf-meridian](https://github.com/cognis-digital/jtf-meridian) for how the pieces fit together.
<!-- cognis:domains:end -->

## Usage — step by step

`chartwright` renders, lints, and diffs Helm charts and their values — no Helm binary required.

1. **Install** (pure stdlib, Python 3.10+):
   ```bash
   pip install "git+https://github.com/cognis-digital/chartwright.git"
   ```
2. **Render** a chart's templates against its values, layering an env override file and inline `--set`:
   ```bash
   chartwright template ./mychart --release prod --values values-prod.yaml --set image.tag=2.0
   ```
3. **Lint** chart structure and balanced if/range/with blocks; `--fail-on warning` tightens the gate:
   ```bash
   chartwright lint ./mychart --fail-on warning
   ```
4. **Use the output** — list the `.Values` paths a chart references (catch typos with `--fail-on-undeclared`), or diff values across environments:
   ```bash
   chartwright schema ./mychart --fail-on-undeclared
   chartwright diff values.yaml values-prod.yaml --format json
   ```
5. **Automate in CI** — lint + schema-check as a pre-merge gate:
   ```bash
   chartwright lint ./mychart && chartwright schema ./mychart --fail-on-undeclared
   ```
   Or run it as a local MCP server (stdio JSON-RPC): `chartwright mcp`.

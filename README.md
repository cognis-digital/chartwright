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

## License

Cognis Open Collaboration License (COCL) 1.0 — see [`LICENSE`](LICENSE).
© 2026 Cognis Digital LLC. Original Cognis work targeting the open Helm chart
layout and template behavior; it does not embed or vendor Helm or Sprig, and
contains no third-party code, names, or branding.

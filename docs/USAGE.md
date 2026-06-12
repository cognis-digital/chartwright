# chartwright — Usage Guide

chartwright renders, lints, and diffs Helm charts without a Helm binary, using
the standard chart layout (`Chart.yaml`, `values.yaml`, `templates/`).

## Commands

### template
```bash
python -m chartwright template ./mychart --release prod
python -m chartwright template ./mychart --values values-prod.yaml
python -m chartwright template ./mychart --set image.tag=2.0 --set replicaCount=5
```
`--set key.path=value` applies Helm-style nested overrides on top of
`values.yaml` (and `--values`), with type coercion (`5` → int, `true` → bool).
To keep a version-like value as a string, quote it: `--set 'image.tag="2.0"'`
(otherwise `2.0` coerces to a float, matching Helm's `--set` footgun).

### lint
```bash
python -m chartwright lint ./mychart
python -m chartwright lint ./mychart --fail-on warning
```
Checks required `Chart.yaml` fields and balanced `if`/`range`/`with`/`end`
blocks per template.

### diff
```bash
python -m chartwright diff values.yaml values-prod.yaml
```
Flattened, leaf-level added/removed/changed report — catch drift between a base
and an environment override before it ships.

### schema — value-reference audit
```bash
python -m chartwright schema ./mychart
python -m chartwright schema ./mychart --fail-on-undeclared
```
Lists every `.Values.*` path the templates reference and flags any with **no
default** in `values.yaml` (a common cause of empty renders in production). With
`--fail-on-undeclared` it gates CI.

## Template directives supported

- `{{ .Values.a.b }}`, `{{ .Chart.name }}`, `{{ .Release.Name }}`
- pipelines: `{{ .Values.x | default "y" | quote | upper | lower | trim }}`
- conditionals: `{{- if .Values.flag }} … {{- else }} … {{- end }}`
- loops: `{{- range .Values.list }} … {{ . }} … {{- end }}`
- whitespace chomping with `{{-` and `-}}`

## MCP server

```bash
python -m chartwright mcp   # template / lint / diff over stdio JSON-RPC
```

## CI recipe

```bash
python -m chartwright lint ./chart --fail-on warning || exit 1
python -m chartwright schema ./chart --fail-on-undeclared || exit 1
python -m chartwright template ./chart --set image.tag=$CI_TAG > rendered.yaml
```

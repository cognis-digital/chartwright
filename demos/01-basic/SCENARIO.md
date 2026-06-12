# Demo 01 — Render and lint a chart, diff values across environments

This scenario uses a small Helm-layout chart under `chart/` (a `Chart.yaml`,
`values.yaml`, and two templates) plus a `values-prod.yaml` override.

## Run it

```bash
# Render the chart's templates (no Helm binary needed).
python -m chartwright template demos/01-basic/chart --release prod

# Render with a production values override merged in.
python -m chartwright template demos/01-basic/chart \
    --values demos/01-basic/values-prod.yaml

# Lint the chart structure + template blocks.
python -m chartwright lint demos/01-basic/chart

# Diff the default values against production.
python -m chartwright diff demos/01-basic/chart/values.yaml \
    demos/01-basic/values-prod.yaml
```

## What you should see

`template` substitutes `.Values`, `.Chart`, and `.Release`, evaluates the
`{{ if .Values.service.enabled }}` branch, and expands the
`{{ range .Values.env }}` loop into one entry per environment variable.

`diff` reports that production changes `replicaCount` (2 → 5), the image tag
(`1.2.0` → `1.2.0-prod`), and the service port (80 → 443).

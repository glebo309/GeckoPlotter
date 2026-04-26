# GeckoPlotter V2 Current README

`GeckoPlotter_V2` is the active codebase for ongoing development.

## Run

From this folder:

```bash
python app.py
```

The main entrypoint is `app.py`.

## Current Structure

- `src/` contains active app code
- `src/callbacks/` contains active Dash callbacks
- `src/components/` contains UI components
- `src/services/` contains data, plotting, and reader services
- `archive/` contains backup and playground files kept for reference only

## Active Direction

Current development is following `CONTINUATION_PLAN.md`.

Immediate priorities:

1. Keep `GeckoPlotter_V2` as the only active app
2. Continue Phase 0 cleanup and stabilization
3. Introduce unified per-file UI state
4. Integrate the table editor from archived playground logic into real services

## Archive Policy

Files under `archive/` are not part of the active runtime path.

Use them as reference material only when porting logic into the modular `src/` codebase.

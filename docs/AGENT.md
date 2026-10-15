# GeckoPlotter for agents (MCP)

**Under construction.** This is an early local integration. Tool coverage and the agent-to-GUI review workflow are still being developed.

`gecko_mcp.py` lets Claude (Claude Code, Claude Desktop) or another MCP client work with GeckoPlotter: open runs,
integrate, extract ion chromatograms, read mass spectra, draw figures and save a project. The project opens in the app
with every peak in place, so the user checks and corrects the agent's integration by hand.

It runs on the user's computer over stdio; no data leaves the machine.

## Register it (once)

Easiest: in GeckoPlotter click the logo (About) and **Connect to Claude**. It adds GeckoPlotter to Claude Desktop and
Claude Code on this computer (only its own entry; Claude Desktop's settings are backed up first). Restart Claude to use
it. By hand:

With the launcher install (macOS):

```
claude mcp add geckoplotter -- "$HOME/Library/Application Support/GeckoPlotter/venv/bin/python" \
  "$HOME/Library/Application Support/GeckoPlotter/app/gecko_mcp.py"
```

Windows: the same with `%LOCALAPPDATA%\GeckoPlotter\venv\Scripts\python.exe` and `%LOCALAPPDATA%\GeckoPlotter\app\gecko_mcp.py`.
From a git checkout: any Python with `requirements.txt` installed, and `<checkout>/gecko_mcp.py`.

## Tools

| Tool | Does |
|---|---|
| `open_data(path)` | a file, a run folder, a folder of run folders (one sample per run, named after the folder: `…-4` -> `4`), or a `.gecko` / FAIR `.zip` project |
| `list_samples()` | samples, their channels (UV wavelength, +/- MS, whether full spectra are there), peak counts |
| `detect_peaks(samples, channel, sensitivity)` | the Detect button (services/detection.py) |
| `integrate(rt_start, rt_end, samples, channel, name)` | straight baseline from the signal at both times, like a baseline drawn in the plot |
| `peak_table(samples)` | every peak: RT, start, end, area, height, area %, concentration, source |
| `rename_peak(sample, peak, new_name)` | the name spreads to the same peak in every sample |
| `extract_ion_chromatogram(mz, tolerance, samples, polarity, rt_start, rt_end)` | apex RT, height, area per sample; also listed in the app's EIC view |
| `mass_spectrum(sample, rt / rt_start+rt_end / peak, polarity, top)` | the most intense ions (apices, 0.6 m/z apart), relative %; over a peak it is the app's Peak mass average |
| `figure(...)` | PNG of the samples overlaid with their peaks, returned to the agent |
| `save_project(path)` | `.gecko` project |

The Python layer is `src/gecko_api.py` (`Workspace`), usable from scripts and notebooks as well. Files are loaded by
`services/workspace_loader.py`, the same code the app's drop runs, so samples, channels, methods and remembered UV
wavelengths come out identical.

## Limits (first version)

- The agent works in its own workspace, not in the app window that is open; the hand-over is the saved project.
- EIC areas use the agent's own boundaries (5 % of the apex height, or the window given); the app has no EIC
  integration to compare with yet.
- Agilent `.ms` files are skipped (no reader); the `.cdf` / `.CSV` exports of the same run are used.
- Tests: `tests/test_gecko_api.py`.

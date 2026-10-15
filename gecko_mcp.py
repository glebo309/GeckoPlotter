#!/usr/bin/env python3
"""GeckoPlotter as an MCP server: an agent (Claude Code, Claude Desktop) opens runs, integrates, extracts ion
chromatograms, reads mass spectra, draws figures and saves a project that opens in the app.

Register once (Claude Code), with the Python that has GeckoPlotter's packages:

    claude mcp add geckoplotter -- "<GeckoPlotter folder>/venv/bin/python" "<GeckoPlotter folder>/app/gecko_mcp.py"

It runs on this computer only (stdio); nothing is sent anywhere. One workspace lives as long as the agent's session.
"""
import contextlib
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'src'))

from mcp.server.mcpserver import Image, MCPServer  # noqa: E402

from gecko_api import GeckoError, Workspace  # noqa: E402

server = MCPServer(
    name='geckoplotter',
    title='GeckoPlotter',
    instructions=(
        'GeckoPlotter analyses chromatography and LC-MS data (UV/PDA channels, TIC, mass spectra). Open a run, a '
        'folder of run folders or a .gecko project first, then list the samples to learn their names and channels. '
        'Peaks you integrate are kept in the workspace; save a project so the user can open it in GeckoPlotter and '
        'check or correct every peak by hand. Show a figure when a result depends on where a peak was cut. '
        'Single-quadrupole m/z values are read about 0.4-0.5 below the exact mass.'),
)
workspace = Workspace()


@contextlib.contextmanager
def _quiet():
    """The protocol runs over stdout: anything a module prints goes to stderr instead."""
    with contextlib.redirect_stdout(sys.stderr):
        yield


def _run(call, *args, **kwargs):
    with _quiet():
        try:
            return call(*args, **kwargs)
        except GeckoError as exc:
            return {'error': str(exc)}


@server.tool()
def open_data(path: str) -> dict:
    """Open a data file, a run folder, a folder of run folders (one sample per run, named after its folder) or a
    GeckoPlotter project (.gecko, or a FAIR package .zip; this replaces the workspace)."""
    return _run(workspace.open, path)


@server.tool()
def list_samples() -> list:
    """The loaded samples: name, type, channels (name, kind uv/ms+/ms-, wavelength, points, time range, whether it
    holds full mass spectra) and peak count."""
    return _run(workspace.samples)


@server.tool()
def detect_peaks(samples: list[str] | None = None, channel: str | None = None, sensitivity: float = 50) -> list:
    """Detect peaks as the app's Detect button does. samples: names (default: every run); channel: e.g. 'UV 220',
    'Ch B', '+TIC' (default: the one the app shows); sensitivity 0-100 (minimum height = 100 - sensitivity % of the
    tallest peak). Earlier detected peaks of that channel are replaced, manual ones kept."""
    return _run(workspace.detect_peaks, samples, channel, sensitivity)


@server.tool()
def integrate(rt_start: float, rt_end: float, samples: list[str] | None = None, channel: str | None = None,
              name: str | None = None) -> list:
    """Integrate between two retention times (min) with a straight baseline from the signal at rt_start to the
    signal at rt_end, in each given sample. name: compound name for the peak (spreads to the same peak in all
    samples)."""
    return _run(workspace.integrate, rt_start, rt_end, samples, channel, name)


@server.tool()
def peak_table(samples: list[str] | None = None) -> list:
    """All integrated peaks: sample, channel, name, RT, start, end, area, height, area %, concentration, source."""
    return _run(workspace.peaks, samples)


@server.tool()
def rename_peak(sample: str, peak: str, new_name: str) -> list:
    """Rename a peak (by its name or id); the same peak in every sample gets the name. Returns the peak table."""
    return _run(workspace.rename_peak, sample, peak, new_name)


@server.tool()
def extract_ion_chromatogram(mz: float, tolerance: float = 0.5, samples: list[str] | None = None,
                             polarity: str = '+', rt_start: float | None = None,
                             rt_end: float | None = None) -> list:
    """EIC of m/z ± tolerance in each sample with full mass spectra; per sample the apex RT, height and area (the
    tallest peak, inside rt_start-rt_end when given; integrated to 5 % of its height or over the given window)."""
    return _run(workspace.eic, mz, tolerance, samples, polarity, rt_start, rt_end)


@server.tool()
def mass_spectrum(sample: str, rt: float | None = None, rt_start: float | None = None, rt_end: float | None = None,
                  peak: str | None = None, polarity: str = '+', top: int = 10) -> dict:
    """Mass spectrum at one time, averaged over rt_start-rt_end, or averaged over a peak's integration window (as
    the app's Peak mass view). Returns the most intense ions with relative intensity (%)."""
    return _run(workspace.mass_spectrum, sample, rt, rt_start, rt_end, peak, polarity, top)


@server.tool()
def figure(samples: list[str] | None = None, channel: str | None = None, rt_start: float | None = None,
           rt_end: float | None = None, eic_mz: float | None = None, tolerance: float = 0.5,
           polarity: str = '+'):
    """Draw the samples overlaid (a channel, or the EIC of eic_mz) with their integrated peaks shaded and named, and
    return the image."""
    with _quiet():
        try:
            target = os.path.join(tempfile.mkdtemp(prefix='gecko-'), 'figure.png')
            path = workspace.figure(target, samples, channel, rt_start, rt_end, eic_mz, tolerance, polarity)
        except GeckoError as exc:
            return {'error': str(exc)}
    return Image(path=path)


@server.tool()
def save_project(path: str, project_name: str | None = None) -> dict:
    """Save the workspace as a GeckoPlotter project (.gecko): it opens in the app with every sample, peak, name and
    calibration, so the user can check and correct the integration by hand."""
    return _run(lambda: {'saved': workspace.save(path, project_name)})


if __name__ == '__main__':
    server.run()

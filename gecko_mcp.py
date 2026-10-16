#!/usr/bin/env python3
"""GeckoPlotter as an MCP server: an agent (Claude Code, Claude Desktop) opens runs, integrates, extracts ion
chromatograms, reads mass spectra, draws figures and saves a project that opens in the app.

Register once (Claude Code), with the Python that has GeckoPlotter's packages:

    claude mcp add geckoplotter -- "<GeckoPlotter folder>/venv/bin/python" "<GeckoPlotter folder>/app/gecko_mcp.py"

It runs on this computer only (stdio); nothing is sent anywhere. When GeckoPlotter is open, every tool works in the
window used last and the screen redraws (live mode, services/live_agent); otherwise in a workspace of its own that
lives as long as the agent's session.
"""
import contextlib
import json
import os
import sys
import tempfile
import threading
import time
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'src'))

from mcp.server.mcpserver import Context, Image, MCPServer  # noqa: E402

from gecko_api import GeckoError, Workspace  # noqa: E402
from services import live_client  # noqa: E402
from services.live_agent import HELLO  # noqa: E402

server = MCPServer(
    name='geckoplotter',
    title='GeckoPlotter',
    instructions=(
        'GeckoPlotter analyses chromatography and LC-MS data (UV/PDA channels, TIC, mass spectra). Open a run, a '
        'folder of run folders or a .gecko project first, then list the samples to learn their names and channels. '
        'Peaks you integrate are kept in the workspace; save a project so the user can open it in GeckoPlotter and '
        'check or correct every peak by hand. Show a figure when a result depends on where a peak was cut. '
        'Single-quadrupole m/z values are read about 0.4-0.5 below the exact mass. Samples with PDA data hold the '
        'whole UV range: list_samples shows pda=true; add_uv_channel reads any wavelength, uv_spectrum a spectrum. '
        'When GeckoPlotter is open, the tools work in it and the user sees every step; otherwise in a workspace of '
        'its own. Do the analysis with these tools, not with scripts or by reading the data files yourself: what '
        'a tool does is what the user sees and can check in the app. If a tool is missing, say so instead of working '
        'around it. To choose a wavelength call compare_wavelengths (it screens every PDA wavelength); do not add '
        'channels and integrate them one by one to compare. Save projects where the user says; without a place pass just a file name: it goes to '
        'GeckoPlotter\'s Projects folder (never a temporary folder), and tell the user the path. Before a judgement call read analysis_guide(topic): wavelength (choosing the detection wavelength), '
        'integration, deconvolution, calibration (acceptance and outliers), identification (LC-MS ions), conversion. '
        'First call identify_agent with your model name: changes are recorded as made by an MCP agent. To quantify, '
        'integrate a peak in the standards and call calibrate with {sample: concentration}; read its warnings.'),
)
workspace = Workspace()


@contextlib.contextmanager
def _quiet():
    """The protocol runs over stdout: anything a module prints goes to stderr instead."""
    with contextlib.redirect_stdout(sys.stderr):
        yield


def _identify(ctx) -> None:
    """Who is at work: the MCP client from the protocol handshake (name, version) and the model the agent named
    (identify_agent). Every change it makes is noted in the analysis history with this (research_package)."""
    client = None
    try:
        client = ctx.session.client_params.client_info
    except Exception:                                   # noqa: BLE001  an older client: name unknown
        pass
    agent = {'via': 'MCP agent', 'client': getattr(client, 'name', None) or 'unknown client',
             'version': getattr(client, 'version', None)}
    if MODEL.get('model'):
        agent['model'] = MODEL['model']
    workspace.agent = agent


MODEL = {}


def _label(client: str) -> str:
    """The app's own name for the status bar: 'claude-code' -> 'Claude Code'."""
    name = (client or '').lower()
    for part, label in (('claude-code', 'Claude Code'), ('claude-ai', 'Claude Desktop'), ('claude', 'Claude'),
                        ('codex', 'Codex'), ('gemini', 'Gemini CLI')):
        if part in name:
            return label
    return client or 'Agent'


def _heartbeat_once() -> None:
    """Announce this MCP process even before it has made a tool call; follow the app used last."""
    info = live_client.find()
    if not info:
        return
    client = (workspace.agent or {}).get('client')
    label = _label(client) if client and client != 'unknown client' else 'Agent'
    body = json.dumps({'id': os.getpid(), 'parent': os.getppid(), 'agent': label}).encode()
    request = urllib.request.Request(f"http://127.0.0.1:{info['port']}{HELLO}", data=body, method='POST',
                                     headers={'Content-Type': 'application/json', 'X-Gecko-Key': info['key']})
    with urllib.request.urlopen(request, timeout=3):
        pass


def _heartbeat() -> None:
    while True:
        try:
            _heartbeat_once()
        except Exception:                                  # noqa: BLE001  no app, stale file, etc.: try next time
            pass                                           # stdout belongs to the MCP protocol
        time.sleep(10)


def _run(method, *args, ctx=None, **kwargs):
    """Run a Workspace method: in the GeckoPlotter that is open (live mode, the screen redraws), or here when none is."""
    if ctx is not None:
        _identify(ctx)
    with _quiet():
        agent = dict(workspace.agent or {}, client_label=_label((workspace.agent or {}).get('client')), pid=os.getpid())
        try:
            return live_client.call(method, args, kwargs, agent)
        except live_client.Refused as exc:
            return {'error': str(exc)}
        except live_client.NotRunning:
            pass
        try:
            return getattr(workspace, method)(*args, **kwargs)
        except GeckoError as exc:
            return {'error': str(exc)}


@server.tool()
def identify_agent(model: str, ctx: Context = None) -> dict:
    """Name the model you are (e.g. 'Claude Opus 5.5') once at the start: the project and its FAIR package record
    that the analysis was made with an MCP agent, which client and which model."""
    MODEL['model'] = model.strip()[:80]
    _identify(ctx)
    return {'recorded': workspace.agent}


@server.tool()
def analysis_guide(topic: str) -> dict:
    """How an analytical chemist decides, with the numbers that decide: read it before the judgement call.
    Topics: wavelength, integration, deconvolution, calibration, identification, conversion."""
    from services.agent_guide import guide
    return guide(topic)


@server.tool()
def open_data(path: str, everything: bool = False, ctx: Context = None) -> dict:
    """Open a data file, a run folder, a folder of run folders (one sample per run, named after its folder) or a
    GeckoPlotter project (.gecko, or a FAIR package .zip; this replaces the workspace). From Agilent export folders
    only the full-scan spectra (*_spectra.cdf) and UV channels (*.dx_VWD*.CSV) are read; everything=True reads the
    small duplicate .cdf/.CSV exports too. Project files (.gecko / .zip) found inside a data folder are not read
    as data: their paths are returned under projects, separately from not_readable. Use open_data(<project path>)
    to open one instead."""
    return _run('open', path, everything, ctx=ctx)


@server.tool()
def list_samples(ctx: Context = None) -> list:
    """The loaded samples: name, type, channels (name, kind uv/ms+/ms-, wavelength, points, time range, whether it
    holds full mass spectra) and peak count."""
    return _run('samples', ctx=ctx)


@server.tool()
def detect_peaks(samples: list[str] | None = None, channel: str | None = None, sensitivity: float = 50, ctx: Context = None) -> list:
    """Detect peaks as the app's Detect button does. samples: names (default: every run); channel: e.g. 'UV 220',
    'Ch B', '+TIC' (default: the one the app shows); sensitivity 0-100 (minimum height = 100 - sensitivity % of the
    tallest peak). Earlier detected peaks of that channel are replaced, manual ones kept."""
    return _run('detect_peaks', samples, channel, sensitivity, ctx=ctx)


@server.tool()
def integrate(rt_start: float, rt_end: float, samples: list[str] | None = None, channel: str | None = None,
              name: str | None = None, snap_to_valleys: bool = True, ctx: Context = None) -> list:
    """Integrate a peak in each given sample with a straight baseline on the curve. Each end walks down the slope to
    the nearest valley (at most 0.5 min), so a rough window around the peak takes the whole peak; snap_to_valleys=
    False uses the exact times. name: compound name (spreads to the same peak in all samples). Peaks with height
    below three times that channel's robust baseline noise are skipped with a per-sample error. Check the result
    with figure() when neighbouring peaks are close."""
    return _run('integrate', rt_start, rt_end, samples, channel, name, snap_to_valleys, ctx=ctx)


@server.tool()
def deconvolve(rt_start: float, rt_end: float, samples: list[str] | None = None, channel: str | None = None,
               n_peaks: int | None = None, names: list[str] | None = None, centers: list[float] | None = None,
               prominence: float = .05, center_tolerance: float | None = None, ctx: Context = None) -> list:
    """Use for a shoulder or overlapping peaks that integrate() cannot separate; check the result with figure().
    Fits the GUI's EMG model in the exact RT window, saving editable deconvolved peaks with undo. samples defaults
    to every run, channel to the shown channel. n_peaks=None auto-detects shoulders; an integer forces the count
    with curvature seeds for weak shoulders. Fits a linear baseline jointly with the peaks, and limits each
    component's tailing to the main peak's. Include baseline on both sides (and the full main-peak tail).
    names labels components in RT order. centers supplies seed RTs; center_tolerance optionally bounds actual
    apex RTs around those seeds (minutes), useful when a weak shoulder drifts into the main peak. Returns per sample
    components (name, apex_rt, area, height, area % of this fit, FWHM), R², residual RMSE, redchi and shape/fit warnings,
    including components narrower than 1/3 of the widest component's FWHM.
    Existing peaks with stored RT in the window are replaced. A high R² alone does not identify the shoulder."""
    return _run('deconvolve', rt_start, rt_end, samples, channel, n_peaks, names, centers, prominence,
                center_tolerance, ctx=ctx)


@server.tool()
def peak_table(samples: list[str] | None = None, ctx: Context = None) -> list:
    """All integrated peaks: sample, channel, name, RT, start, end, area, height, area %, concentration, source."""
    return _run('peaks', samples, ctx=ctx)


@server.tool()
def rename_peak(sample: str, peak: str, new_name: str, ctx: Context = None) -> list:
    """Rename a peak (by its name or id); the same peak in every sample gets the name. Returns the peak table."""
    return _run('rename_peak', sample, peak, new_name, ctx=ctx)


@server.tool()
def remove_peak(sample: str | None, peak: str, ctx: Context = None) -> list:
    """Delete a peak (by its name or id); sample=None removes it from every sample that has it.
    Returns the remaining peak table."""
    return _run('remove_peak', sample, peak, ctx=ctx)


@server.tool()
def calibrate(peak: str, standards: dict[str, float], units: str = 'mM', fit: str = 'linear',
              through_zero: bool = False, channel: str | None = None, rt_tolerance: float = 0.2,
              name: str | None = None, ctx: Context = None) -> dict:
    """Calibrate a peak from standards: standards maps sample name -> concentration (e.g. {"Ala 1 mM": 1.0, ...}).
    The peak (by its name) must be integrated in the standards first. Every other sample with that peak (same channel,
    retention time ± rt_tolerance min) gets a concentration. Matching prefers the calibrated peak's name; only if
    absent does it use the nearest RT in the window, with ambiguity only for equal distances. Other peaks in
    standard samples are not unknowns. fit: linear, quadratic or power. Standard rows with unavailable
    back_calculated values include a note (e.g. area below the intercept). Read 'warnings':
    missing standards, low R², standards that back-calculate badly, samples outside the calibrated range or the
    retention-time window. Recalibrating with the same name replaces the curve."""
    return _run('calibrate', peak, standards, units, fit, through_zero, channel, rt_tolerance, name, ctx=ctx)


@server.tool()
def list_calibrations(ctx: Context = None) -> list:
    """The calibrations of the workspace: name, fit, units, R², number of standards, range, retention-time window."""
    return _run('list_calibrations', ctx=ctx)


@server.tool()
def remove_calibration(name: str, ctx: Context = None) -> list:
    """Delete a calibration (its concentrations are cleared); returns the remaining calibrations."""
    return _run('remove_calibration', name, ctx=ctx)


@server.tool()
def compare_wavelengths(peak: str, standards: dict[str, float], wavelengths: list[float] | None = None,
                        samples: list[str] | None = None, rt_tolerance: float = 0.2, detail: bool = False,
                        ctx: Context = None) -> dict:
    """Choose the detection wavelength for a calibration from PDA data: use it before calibrating PDA data, when asked
    for the best wavelength, or when a calibration is poor. Integrate and name the analyte in the standards first
    ({sample: concentration}). Every recorded wavelength is screened with one fixed window and a straight baseline;
    the best candidates are ranked: saturated or S/N < 10 are rejected, linearity within 3 points is a tie that S/N
    decides. Returns the recommendation, the top candidates (height of the top standard, S/N and LOQ of the lowest,
    R2, max back-calculated error), the screen's saturated/noisy/non-linear ranges, peak purity and warnings.
    Then integrate rt_start-rt_end on the recommended channel with snap_to_valleys=False and calibrate there.
    detail=True returns everything (long). The user's PDA view sweeps the range and ends on the choice."""
    return _run('compare_wavelengths', peak, standards, wavelengths, samples, rt_tolerance, detail, ctx=ctx)


@server.tool()
def add_uv_channel(wavelength_nm: float, samples: list[str] | None = None, ctx: Context = None) -> list:
    """Extract one wavelength from each sample's PDA (3D UV) data as a new channel, like the app's "Add N nm
    channel". To find the best wavelength use compare_wavelengths instead of adding channels to compare. Use it when the recorded channels miss the compound (no chromophore: try 200-210 nm); then
    detect_peaks or integrate on that channel (e.g. channel='205 nm')."""
    return _run('add_uv_channel', wavelength_nm, samples, ctx=ctx)


@server.tool()
def uv_spectrum(sample: str, rt: float, top: int = 5, ctx: Context = None) -> dict:
    """UV spectrum at a retention time from the sample's PDA data: absorbance maxima and the absorbance every
    10 nm. Use it to find the wavelength a peak absorbs at."""
    return _run('uv_spectrum', sample, rt, top, ctx=ctx)


@server.tool()
def add_eic_channel(mz: float, tolerance: float = 0.5, polarity: str = '+', samples: list[str] | None = None,
                    ctx: Context = None) -> list:
    """Add the extracted-ion chromatogram of m/z ± tolerance as a channel in each run with full-scan spectra
    (polarity '+', '-' or 'both'). The channel ('EIC 633.8 ±0.5 (+)') then works like any other: detect_peaks,
    integrate, calibrate, figure and export with channel='EIC 633.8'."""
    return _run('add_eic_channel', mz, tolerance, polarity, samples, ctx=ctx)


@server.tool()
def extract_ion_chromatogram(mz: float, tolerance: float = 0.5, samples: list[str] | None = None,
                             polarity: str = '+', rt_start: float | None = None,
                             rt_end: float | None = None, ctx: Context = None) -> list:
    """EIC of m/z ± tolerance in each run, added as a channel and integrated on it: per sample the apex RT, height
    and area of the tallest peak (inside rt_start-rt_end when given; to 5 % of its height or over the window). The
    peaks are in the app, where the user can correct them; running it again replaces the earlier EIC peak."""
    return _run('eic', mz, tolerance, samples, polarity, rt_start, rt_end, ctx=ctx)


@server.tool()
def mass_spectrum(sample: str, rt: float | None = None, rt_start: float | None = None, rt_end: float | None = None,
                  peak: str | None = None, polarity: str | None = None, top: int = 10, ctx: Context = None) -> dict:
    """Mass spectrum at one time, averaged over rt_start-rt_end, or averaged over a peak's integration window (as
    the app's Peak mass view). polarity '+' or '-' (default: a peak's own, else '+'). Returns the most intense ions
    with relative intensity (%). The user's screen shows the spectrum too."""
    return _run('mass_spectrum', sample, rt, rt_start, rt_end, peak, polarity, top, ctx=ctx)


@server.tool()
def figure(samples: list[str] | None = None, channel: str | None = None, rt_start: float | None = None,
           rt_end: float | None = None, eic_mz: float | None = None, tolerance: float = 0.5,
           polarity: str = '+', ctx: Context = None):
    """Draw the samples overlaid (a channel, or the EIC of eic_mz) with their integrated peaks shaded and named, and
    return the image."""
    target = os.path.join(tempfile.mkdtemp(prefix='gecko-'), 'figure.png')
    path = _run('figure', target, samples, channel, rt_start, rt_end, eic_mz, tolerance, polarity, ctx=ctx)
    if isinstance(path, dict):
        return path
    return Image(path=path)


@server.tool()
def export_results(path: str, ctx: Context = None) -> dict:
    """Write the whole project to one Excel workbook for the user to keep working with: an overview, one sheet per plot
    tab (peak areas per compound and sample, every peak) with its traces, calibrations, samples and history."""
    saved = _run('export_results', path, ctx=ctx)
    return saved if isinstance(saved, dict) else {'saved': saved}


@server.tool()
def save_project(path: str, project_name: str | None = None, ctx: Context = None) -> dict:
    """Save the workspace as a GeckoPlotter project (.gecko): it opens in the app with every sample, peak, name and
    calibration, so the user can check and correct the integration by hand. path: where the user asked, or only a
    file name ('PEA calibration.gecko'), which goes to GeckoPlotter's Projects folder (~/Documents/GeckoPlotter)."""
    saved = _run('save', path, project_name, ctx=ctx)
    return saved if isinstance(saved, dict) else {'saved': saved}


if __name__ == '__main__':
    threading.Thread(target=_heartbeat, name='gecko-heartbeat', daemon=True).start()
    server.run()

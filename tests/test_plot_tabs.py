"""Test multi-tab plot workspace — tabs auto-create per data type."""
import os
import sys
import base64
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

FIXTURES = os.path.join(os.path.dirname(__file__), 'ingestion', 'fixtures')


def _make_record(path, file_id=None):
    """Build a file record dict from a fixture file path."""
    name = os.path.basename(path)
    with open(path, 'rb') as f:
        raw = f.read()
    from services.storage_manager import guess_file_type
    ext = name.rsplit('.', 1)[-1].lower()
    mime = 'text/csv' if ext == 'csv' else 'text/plain'
    return {
        'id': file_id or f'test-{name}',
        'name': name,
        'type': guess_file_type(name),
        'size': len(raw),
        'size_display': f'{len(raw)} B',
        'last_modified': 0,
        'last_modified_display': '',
        'preview': '',
        'encoded': f'data:{mime};base64,{base64.b64encode(raw).decode()}',
    }


def _load_file(dm, record):
    """Load a file record into DataManager and return its data."""
    return dm.load_file_data(record)


@pytest.fixture
def dm():
    from services.storage_manager import DataManager
    return DataManager()


@pytest.fixture
def chromeleon_record():
    return _make_record(os.path.join(FIXTURES, 'chromeleon_export.txt'), 'chrom-001')


@pytest.fixture
def csv_record():
    return _make_record(os.path.join(FIXTURES, 'simple_xy.csv'), 'csv-001')


@pytest.fixture
def cary_record():
    return _make_record(os.path.join(FIXTURES, 'cary_kinetics.csv'), 'cary-001')


class TestTabHelpers:
    def test_tab_id_deterministic(self):
        from callbacks.viz_callbacks import _tab_id_from_group
        group = ('chromatogram', 'Time (min)')
        tid = _tab_id_from_group(group)
        assert tid == 'tab-chromatogram_time_min'
        assert _tab_id_from_group(group) == tid

    def test_tab_label_known_category(self):
        from callbacks.viz_callbacks import _tab_label_from_group
        assert _tab_label_from_group(('chromatogram', 'Time (min)')) == 'Chromatograms'
        assert _tab_label_from_group(('uvvis', 'Wavelength (nm)')) == 'UV-Vis Spectra'
        assert _tab_label_from_group(('generic', 'x')) == 'Data'

    def test_tab_label_unknown_category(self):
        from callbacks.viz_callbacks import _tab_label_from_group
        label = _tab_label_from_group(('some_new_type', 'col'))
        assert label == 'Some New Type'

    def test_different_groups_different_ids(self):
        from callbacks.viz_callbacks import _tab_id_from_group
        g1 = ('chromatogram', 'Time (min)')
        g2 = ('generic', 'x')
        assert _tab_id_from_group(g1) != _tab_id_from_group(g2)


class TestOverlayGroups:
    def test_chromeleon_gets_chromatogram_group(self, dm, chromeleon_record):
        _load_file(dm, chromeleon_record)
        from callbacks.viz_callbacks import _get_overlay_group
        fdata = dm.loaded_data['chrom-001']
        metadata = fdata.get('metadata', {})
        group = _get_overlay_group(metadata, fdata)
        assert group[0] == 'chromatogram'
        assert 'Time' in group[1] or 'time' in group[1].lower()

    def test_csv_gets_generic_group(self, dm, csv_record):
        _load_file(dm, csv_record)
        from callbacks.viz_callbacks import _get_overlay_group
        fdata = dm.loaded_data['csv-001']
        metadata = fdata.get('metadata', {})
        group = _get_overlay_group(metadata, fdata)
        assert group[0] == 'generic'

    def test_different_types_different_groups(self, dm, chromeleon_record, csv_record):
        _load_file(dm, chromeleon_record)
        _load_file(dm, csv_record)
        from callbacks.viz_callbacks import _get_overlay_group
        chrom_data = dm.loaded_data['chrom-001']
        csv_data = dm.loaded_data['csv-001']
        g1 = _get_overlay_group(chrom_data.get('metadata', {}), chrom_data)
        g2 = _get_overlay_group(csv_data.get('metadata', {}), csv_data)
        assert g1 != g2, "Chromatogram and generic CSV must get different overlay groups"


class TestSyncPlotTabs:
    """Test the sync_plot_tabs logic (extracted, not via Dash callbacks)."""

    def _build_tabs(self, dm, loaded_files, existing_tabs=None, current_active=None, active_file=None):
        """Replicate sync_plot_tabs logic without Dash."""
        from callbacks.viz_callbacks import (
            _get_overlay_group, _tab_id_from_group, _tab_label_from_group,
            _get_active_file_group,
        )
        existing_tabs = existing_tabs or []
        bundled_component_ids = set()
        for b in dm.bundle_manager.bundles.values():
            if b.main_file:
                bundled_component_ids.add(b.main_file.get('id'))
            for af in b.auxiliary_files:
                bundled_component_ids.add(af.get('id'))
        seen_groups = set()
        for fid, fdata in dm.loaded_data.items():
            if fid in bundled_component_ids:
                continue
            sr = fdata.get('standardized')
            if sr is None:
                continue
            metadata = fdata.get('metadata', {})
            group = _get_overlay_group(metadata, fdata)
            seen_groups.add(group)

        new_tabs = []
        for group in sorted(seen_groups):
            tid = _tab_id_from_group(group)
            existing = next((t for t in existing_tabs if t['id'] == tid), None)
            if existing:
                new_tabs.append(existing)
            else:
                new_tabs.append({
                    'id': tid,
                    'label': _tab_label_from_group(group),
                    'type': 'raw',
                    'group_key': list(group),
                })

        new_tab_ids = {t['id'] for t in new_tabs}
        if active_file:
            file_group = _get_active_file_group(dm, active_file)
            if file_group and _tab_id_from_group(file_group) in new_tab_ids:
                next_active = _tab_id_from_group(file_group)
            elif current_active and current_active in new_tab_ids:
                next_active = current_active
            else:
                next_active = new_tabs[0]['id'] if new_tabs else None
        elif current_active and current_active in new_tab_ids:
            next_active = current_active
        else:
            next_active = new_tabs[0]['id'] if new_tabs else None

        return new_tabs, next_active

    def test_single_chromatogram_creates_one_tab(self, dm, chromeleon_record):
        _load_file(dm, chromeleon_record)
        tabs, active = self._build_tabs(dm, [chromeleon_record])
        assert len(tabs) == 1
        assert tabs[0]['label'] == 'Chromatograms'
        assert tabs[0]['type'] == 'raw'
        assert active == tabs[0]['id']

    def test_generic_csv_creates_tab(self, dm, csv_record):
        _load_file(dm, csv_record)
        tabs, active = self._build_tabs(dm, [csv_record])
        assert len(tabs) == 1, "Generic CSV should auto-create a tab"
        assert tabs[0]['label'] == 'Data'
        assert active == tabs[0]['id']

    def test_chromatogram_plus_csv_creates_two_tabs(self, dm, chromeleon_record, csv_record):
        _load_file(dm, chromeleon_record)
        _load_file(dm, csv_record)
        tabs, active = self._build_tabs(dm, [chromeleon_record, csv_record])
        assert len(tabs) == 2, "Chromatogram and CSV should each get a tab"
        labels = {t['label'] for t in tabs}
        assert 'Chromatograms' in labels
        assert 'Data' in labels

    def test_same_type_stays_one_tab(self, dm, chromeleon_record):
        rec2 = _make_record(os.path.join(FIXTURES, 'chromeleon_export.txt'), 'chrom-002')
        _load_file(dm, chromeleon_record)
        _load_file(dm, rec2)
        tabs, _ = self._build_tabs(dm, [chromeleon_record, rec2])
        assert len(tabs) == 1, "Two chromatograms should share one tab"

    def test_no_files_no_tabs(self, dm):
        tabs, active = self._build_tabs(dm, [])
        assert tabs == []
        assert active is None

    def test_new_upload_switches_to_new_file_tab(self, dm, chromeleon_record, csv_record):
        _load_file(dm, chromeleon_record)
        tabs1, active1 = self._build_tabs(dm, [chromeleon_record])
        _load_file(dm, csv_record)
        tabs2, active2 = self._build_tabs(
            dm, [chromeleon_record, csv_record],
            existing_tabs=tabs1, current_active=active1,
            active_file='csv-001')
        assert len(tabs2) == 2
        assert active2 != active1, "Should switch to the newly uploaded file's tab"

    def test_kinetics_creates_tab(self, dm, cary_record):
        _load_file(dm, cary_record)
        tabs, active = self._build_tabs(dm, [cary_record])
        assert len(tabs) == 1
        assert tabs[0]['label'] == 'Kinetics'


class TestCollectVisibleFiles:
    def test_only_matching_group_returned(self, dm, chromeleon_record, csv_record):
        _load_file(dm, chromeleon_record)
        _load_file(dm, csv_record)
        from callbacks.viz_callbacks import _collect_visible_files, _get_overlay_group
        chrom_data = dm.loaded_data['chrom-001']
        chrom_group = _get_overlay_group(chrom_data.get('metadata', {}), chrom_data)
        loaded = [chromeleon_record, csv_record]
        groups = _collect_visible_files(dm, 'chrom-001', loaded, target_group_override=chrom_group)
        assert len(groups) == 1
        assert chrom_group in groups
        names = [name for name, _ in groups[chrom_group]]
        assert any('chromeleon' in n.lower() for n in names)

    def test_csv_group_excludes_chromatogram(self, dm, chromeleon_record, csv_record):
        _load_file(dm, chromeleon_record)
        _load_file(dm, csv_record)
        from callbacks.viz_callbacks import _collect_visible_files, _get_overlay_group
        csv_data = dm.loaded_data['csv-001']
        csv_group = _get_overlay_group(csv_data.get('metadata', {}), csv_data)
        loaded = [chromeleon_record, csv_record]
        groups = _collect_visible_files(dm, 'csv-001', loaded, target_group_override=csv_group)
        assert len(groups) == 1
        all_names = [name for name, _ in groups[csv_group]]
        assert not any('chromeleon' in n.lower() for n in all_names)


def test_zoom_restore_keeps_each_pane_and_ignores_removed_axes():
    from callbacks.viz_callbacks import _apply_zoom_state
    from plotly.subplots import make_subplots
    fig = make_subplots(rows=2, cols=1)
    _apply_zoom_state(fig, {'xaxis.range':[5,9], 'xaxis2.range':[6,8],
                           'yaxis2.range[0]':0, 'yaxis2.range[1]':600,
                           'yaxis3.range':[0,99]})
    assert tuple(fig.layout.xaxis2.range) == (6,8)
    assert tuple(fig.layout.yaxis2.range) == (0,600)
    assert 'yaxis3' not in fig.layout

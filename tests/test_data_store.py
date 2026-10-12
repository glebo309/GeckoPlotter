import pandas as pd

from src.ingestion.types import ColumnRole, FileIdentity, PlotHint, SourceCategory, StandardizedResult
from src.services.data_store import Bundle, BundleType, Component, ComponentRole, DataStore


def make_result(filename="sample.csv", source_category=SourceCategory.GENERIC):
    df = pd.DataFrame({"time": [0.0, 1.0, 2.0], "signal": [10.0, 20.0, 30.0]})
    return StandardizedResult(
        data=df,
        column_roles={"time": ColumnRole.X, "signal": ColumnRole.Y},
        identity=FileIdentity(filename, "csv", "heuristic", 3),
        plot_hint=PlotHint.LINE,
        source_category=source_category,
        sample_name="Sample A",
        metadata={"instrument": "demo"},
    )


def make_component(component_id="component-1", filename="sample.csv", role=ComponentRole.PRIMARY):
    result = make_result(filename)
    return Component(
        component_id=component_id,
        role=role,
        original_filename=filename,
        raw_bytes=b"time,signal\n0,10\n1,20\n2,30\n",
        dataframe=result.data,
        column_roles=result.column_roles,
        metadata=result.metadata,
        source_category=result.source_category,
        plot_hint=result.plot_hint,
        standardized=result,
    )


def test_bundle_properties_expose_primary_data_and_roles():
    primary = make_component()
    integration = Component(
        component_id="integration-1",
        role=ComponentRole.INTEGRATION,
        original_filename="sample_Integration.txt",
        raw_bytes=b"Peak\tArea\nA\t123\n",
        metadata={"injection": "Sample A"},
    )
    bundle = Bundle(
        bundle_id="bundle-1",
        name="Sample A",
        bundle_type=BundleType.CHROMELEON,
        component_list=[primary, integration],
    )

    assert bundle.primary == primary
    assert bundle.dataframe.equals(primary.dataframe)
    assert bundle.column_roles == {"time": ColumnRole.X, "signal": ColumnRole.Y}
    assert bundle.source_category == SourceCategory.GENERIC
    assert bundle.plot_hint == PlotHint.LINE
    assert bundle.metadata == {"instrument": "demo", "injection": "Sample A"}
    assert bundle.x_columns == ["time"]
    assert bundle.y_columns == ["signal"]
    assert bundle.has_integration_data()
    assert bundle.get_integration_text() == "Peak\tArea\nA\t123\n"


def test_data_store_crud_and_indexes():
    bundle = Bundle(
        bundle_id="bundle-1",
        name="Sample A",
        bundle_type=BundleType.GENERIC,
        component_list=[make_component()],
    )
    store = DataStore()

    store.add_bundle(bundle)

    assert store.get_bundle("bundle-1") == bundle
    assert store.get_bundle_for_component("component-1") == bundle
    assert store.get_bundle_for_file("sample.csv") == bundle
    assert list(store.iter_bundles()) == [bundle]
    assert store.all_bundles() == {"bundle-1": bundle}

    removed = store.remove_bundle("bundle-1")

    assert removed == bundle
    assert store.get_bundle("bundle-1") is None
    assert store.get_bundle_for_component("component-1") is None
    assert store.get_bundle_for_file("sample.csv") is None


def test_data_store_clear_removes_bundles_and_indexes():
    store = DataStore()
    store.add_bundle(
        Bundle(
            bundle_id="bundle-1",
            name="Sample A",
            bundle_type=BundleType.GENERIC,
            component_list=[make_component()],
        )
    )

    store.clear()

    assert list(store.iter_bundles()) == []
    assert store.get_bundle_for_component("component-1") is None
    assert store.get_bundle_for_file("sample.csv") is None


def test_data_store_get_dataframe_and_xy_arrays():
    bundle = Bundle(
        bundle_id="bundle-1",
        name="Sample A",
        bundle_type=BundleType.GENERIC,
        component_list=[make_component()],
    )
    store = DataStore()
    store.add_bundle(bundle)

    x, y = store.get_xy_arrays("bundle-1")

    assert store.get_dataframe("bundle-1").equals(bundle.dataframe)
    assert x.tolist() == [0.0, 1.0, 2.0]
    assert y.tolist() == [10.0, 20.0, 30.0]


def test_data_store_get_xy_arrays_returns_none_for_unknown_bundle():
    assert DataStore().get_xy_arrays("missing") == (None, None)


def test_lcms_components_are_addressable_by_component_id():
    ms = make_component(
        component_id="ms-pos-1",
        filename="Sample_01_MS1 +TIC.cdf",
        role=ComponentRole.MS_POSITIVE,
    )
    uv = make_component(
        component_id="uv-a-1",
        filename="Sample_01_VWD1A.cdf",
        role=ComponentRole.VWD_A,
    )
    ms.source_category = SourceCategory.LCMS_MS
    ms.standardized.source_category = SourceCategory.LCMS_MS
    uv.source_category = SourceCategory.LCMS_UV
    uv.standardized.source_category = SourceCategory.LCMS_UV
    bundle = Bundle(
        bundle_id="lcms-bundle-1",
        name="Sample_01",
        bundle_type=BundleType.LCMS,
        component_list=[ms, uv],
    )
    store = DataStore()
    store.add_bundle(bundle)

    ms_entry = store.get_data_by_id("ms-pos-1")
    uv_entry = store.get_data_by_id("uv-a-1")

    assert ms_entry["record"]["id"] == "ms-pos-1"
    assert ms_entry["metadata"]["parent_bundle_id"] == "lcms-bundle-1"
    assert ms_entry["metadata"]["component_role"] == ComponentRole.MS_POSITIVE.value
    assert uv_entry["record"]["id"] == "uv-a-1"
    assert uv_entry["metadata"]["component_role"] == ComponentRole.VWD_A.value


def test_lcms_loaded_data_exposes_components_without_parent_duplicate():
    ms = make_component(
        component_id="ms-pos-1",
        filename="Sample_01_MS1 +TIC.cdf",
        role=ComponentRole.MS_POSITIVE,
    )
    uv = make_component(
        component_id="uv-a-1",
        filename="Sample_01_VWD1A.cdf",
        role=ComponentRole.VWD_A,
    )
    ms.source_category = SourceCategory.LCMS_MS
    ms.standardized.source_category = SourceCategory.LCMS_MS
    uv.source_category = SourceCategory.LCMS_UV
    uv.standardized.source_category = SourceCategory.LCMS_UV
    store = DataStore()
    store.add_bundle(
        Bundle(
            bundle_id="lcms-bundle-1",
            name="Sample_01",
            bundle_type=BundleType.LCMS,
            component_list=[ms, uv],
        )
    )

    assert set(store.loaded_data) == {"ms-pos-1", "uv-a-1"}


def test_lcms_eic_overlays_are_persistent_for_component_entries():
    ms = make_component(
        component_id="ms-pos-1",
        filename="Sample_01_MS1 +TIC.cdf",
        role=ComponentRole.MS_POSITIVE,
    )
    ms.source_category = SourceCategory.LCMS_MS
    ms.standardized.source_category = SourceCategory.LCMS_MS
    store = DataStore()
    store.add_bundle(
        Bundle(
            bundle_id="lcms-bundle-1",
            name="Sample_01",
            bundle_type=BundleType.LCMS,
            component_list=[ms],
        )
    )

    overlay = {"mz": 123.4, "tolerance": 0.2, "time": [0.0], "intensity": [10.0]}
    store.add_lcms_eic_overlay("ms-pos-1", overlay)

    assert store.get_data_by_id("ms-pos-1")["eic_overlays"] == [overlay]
    assert store.loaded_data["ms-pos-1"]["eic_overlays"] == [overlay]
    assert store.get_data_by_id("lcms-bundle-1")["eic_overlays"] == [overlay]

    store.clear_lcms_eic_overlays("ms-pos-1")

    assert store.get_data_by_id("ms-pos-1")["eic_overlays"] == []


def test_peak_colors_match_across_lcms_runs_and_component_owners():
    store = DataStore()
    for suffix in ('a', 'b'):
        primary = make_component('primary-' + suffix)
        uv = make_component('uv-' + suffix, role=ComponentRole.VWD_A)
        store.add_bundle(Bundle(bundle_id='run-' + suffix, name=suffix,
                                bundle_type=BundleType.LCMS,
                                component_list=[primary, uv]))
    def add(fid, rt):
        return store.peak_service.add_baseline_peak(
            file_id=fid, area=1, height=1, apex_x=rt,
            poly_x=[rt-.05, rt, rt+.05], poly_y=[0, 1, 0],
            p_line=[(rt-.05, 0), (rt+.05, 0)],
            q1=(rt-.05, 0), q2=(rt+.05, 0))
    add('run-a', 2.0)
    first = add('run-a', 7.3)
    store.peak_service.group_peaks_across_samples(file_overlay_map=store.build_file_overlay_map())
    second = add('uv-b', 7.31)
    store.peak_service.group_peaks_across_samples(file_overlay_map=store.build_file_overlay_map())
    assert first.color == second.color
    assert first.group_id == second.group_id


def test_bundle_iterator_keeps_reference_snapshot_during_removal_and_undo():
    store = DataStore()
    bundles = [Bundle(name, name, BundleType.GENERIC,
                      component_list=[make_component(name+'-signal')]) for name in ('a','b','c')]
    for bundle in bundles:
        store.add_bundle(bundle)
    cursor = store.iter_bundles()
    assert next(cursor) is bundles[0]
    store.file_removal_service.remove('b')
    store.file_removal_service.undo()
    store.file_removal_service.remove('c')
    remaining = list(cursor)
    assert remaining[0] is bundles[1]
    assert remaining[1] is bundles[2]
    assert remaining[0].dataframe is bundles[1].dataframe
    assert [bundle.bundle_id for bundle in store.iter_bundles()] == ['a','b']

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

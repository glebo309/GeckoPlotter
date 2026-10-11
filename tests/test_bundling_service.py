import pandas as pd

from src.ingestion.types import ColumnRole, FileIdentity, SourceCategory, StandardizedResult
from src.services.bundling_service import assign_bundles
from src.services.data_store import BundleType, ComponentRole


def make_result(filename, detected_format="heuristic", extension=None, source_category=SourceCategory.GENERIC, metadata=None):
    extension = extension or filename.rsplit(".", 1)[-1]
    return StandardizedResult(
        data=pd.DataFrame({"x": [0, 1], "y": [2, 3]}),
        column_roles={"x": ColumnRole.X, "y": ColumnRole.Y},
        identity=FileIdentity(filename, extension, detected_format, 2),
        source_category=source_category,
        metadata=metadata or {},
    )


def test_chromeleon_files_are_grouped_into_one_bundle_by_injection_metadata():
    parsed_files = [
        (
            filename,
            filename.encode(),
            make_result(
                filename,
                detected_format="chromeleon_txt",
                extension="txt",
                source_category=SourceCategory.CHROMATOGRAM,
                metadata={"injection": "Injection 42"},
            ),
        )
        for filename in [
            "Export_UV_VIS_1.txt",
            "Export_SST.txt",
            "Export_Integration.txt",
            "Export_Peak Analysis.txt",
            "Export_Summary.txt",
        ]
    ]

    bundles = assign_bundles(parsed_files)

    assert len(bundles) == 1
    bundle = bundles[0]
    assert bundle.name == "Injection 42"
    assert bundle.bundle_type == BundleType.CHROMELEON
    assert len(bundle.component_list) == 5
    assert bundle.get_component(ComponentRole.PRIMARY).original_filename == "Export_UV_VIS_1.txt"
    assert bundle.get_component(ComponentRole.SST).original_filename == "Export_SST.txt"
    assert bundle.get_component(ComponentRole.INTEGRATION).original_filename == "Export_Integration.txt"
    assert bundle.get_component(ComponentRole.PEAK_ANALYSIS).original_filename == "Export_Peak Analysis.txt"
    assert bundle.get_component(ComponentRole.SUMMARY).original_filename == "Export_Summary.txt"


def test_lcms_cdf_files_are_grouped_by_base_name():
    parsed_files = [
        (
            filename,
            b"cdf",
            make_result(
                filename,
                detected_format="lcms_cdf",
                extension="cdf",
                source_category=source_category,
            ),
        )
        for filename, source_category in [
            ("Sample_01_MS1 +TIC.cdf", SourceCategory.LCMS_MS),
            ("Sample_01_MS1 -TIC.cdf", SourceCategory.LCMS_MS),
            ("Sample_01_VWD1A.cdf", SourceCategory.LCMS_UV),
            ("Sample_01_VWD1B.cdf", SourceCategory.LCMS_UV),
        ]
    ]

    bundles = assign_bundles(parsed_files)

    assert len(bundles) == 1
    bundle = bundles[0]
    assert bundle.name == "Sample_01"
    assert bundle.bundle_type == BundleType.LCMS
    assert len(bundle.component_list) == 4
    assert bundle.get_component(ComponentRole.MS_POSITIVE).original_filename == "Sample_01_MS1 +TIC.cdf"
    assert bundle.get_component(ComponentRole.MS_NEGATIVE).original_filename == "Sample_01_MS1 -TIC.cdf"
    assert bundle.get_component(ComponentRole.VWD_A).original_filename == "Sample_01_VWD1A.cdf"
    assert bundle.get_component(ComponentRole.VWD_B).original_filename == "Sample_01_VWD1B.cdf"


def test_single_csv_becomes_one_component_bundle():
    bundles = assign_bundles(
        [
            (
                "single.csv",
                b"x,y\n0,1\n",
                make_result("single.csv", detected_format="heuristic", extension="csv"),
            )
        ]
    )

    assert len(bundles) == 1
    assert bundles[0].name == "single"
    assert bundles[0].bundle_type == BundleType.GENERIC
    assert bundles[0].primary.role == ComponentRole.GENERIC
    assert bundles[0].primary.original_filename == "single.csv"


def test_mixed_upload_creates_chromeleon_bundle_and_csv_bundle():
    parsed_files = [
        (
            "Run_A_UV_VIS_1.txt",
            b"chrom",
            make_result(
                "Run_A_UV_VIS_1.txt",
                detected_format="chromeleon_txt",
                extension="txt",
                source_category=SourceCategory.CHROMATOGRAM,
            ),
        ),
        (
            "Run_A_Integration.txt",
            b"integration",
            make_result(
                "Run_A_Integration.txt",
                detected_format="chromeleon_txt",
                extension="txt",
                source_category=SourceCategory.CHROMATOGRAM,
            ),
        ),
        (
            "single.csv",
            b"x,y\n0,1\n",
            make_result("single.csv", detected_format="heuristic", extension="csv"),
        ),
    ]

    bundles = assign_bundles(parsed_files)

    assert len(bundles) == 2
    by_type = {bundle.bundle_type: bundle for bundle in bundles}
    assert by_type[BundleType.CHROMELEON].name == "Run_A"
    assert len(by_type[BundleType.CHROMELEON].component_list) == 2
    assert by_type[BundleType.GENERIC].name == "single"


def test_lcms_uses_polarity_metadata_when_export_filename_has_no_detector_hint():
    result = make_result('sample_signal.cdf', source_category=SourceCategory.LCMS_MS,
                         metadata={'ionization_mode': 'negative'})
    bundle = assign_bundles([('sample_signal.cdf', b'', result)])[0]
    assert bundle.primary.role == ComponentRole.MS_NEGATIVE
    assert bundle.component_display_name(bundle.primary) == '-TIC'


def test_explicit_ms_polarity_metadata_overrides_misleading_export_name():
    result = make_result('Run_MS1 +TIC.cdf', source_category=SourceCategory.LCMS_MS,
                         metadata={'ionization_mode': 'negative'})
    bundle = assign_bundles([('Run_MS1 +TIC.cdf', b'', result)])[0]
    assert bundle.primary.role == ComponentRole.MS_NEGATIVE
    uv = make_result('Run_VWD1B.cdf', source_category=SourceCategory.LCMS_UV,
                     metadata={'ionization_mode': 'negative'})
    assert assign_bundles([('Run_VWD1B.cdf', b'', uv)])[0].primary.role == ComponentRole.VWD_B

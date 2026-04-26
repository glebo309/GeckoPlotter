# =============================================================================
# GeckoPlotter V2 - Services Package
# =============================================================================

from .storage_manager import (
    create_file_records,
    merge_records,
    summarize_records,
    DataManager
)
from .integration_service import IntegrationService, IntegrationSettings, ProcessedSignal
from .persistence import ProjectPersistence
from .peak_service import Peak, PeakService
from .calibration_service import CalibrationModel, CalibrationPoint, CalibrationService
from .plot_settings_service import PlotSettings, PlotSettingsService
from .export_service import ExportService
from .lcms_service import LCMSService

__all__ = [
    # Data ingestion
    'create_file_records',
    'merge_records',
    'summarize_records',
    'DataManager',
    # Domain services
    'Peak', 'PeakService',
    'CalibrationModel', 'CalibrationPoint', 'CalibrationService',
    'PlotSettings', 'PlotSettingsService',
    'IntegrationService', 'IntegrationSettings', 'ProcessedSignal',
    'ExportService',
    'LCMSService',
    # Persistence
    'ProjectPersistence',
]

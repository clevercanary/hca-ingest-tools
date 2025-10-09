"""HCA Smart Sync - Intelligent S3 synchronization for HCA Atlas data."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("hca-smart-sync")
except PackageNotFoundError:
    # Package metadata not available (e.g., during local source runs)
    __version__ = "0.3.0"

__author__ = "HCA Team"
__email__ = "hca-team@example.com"

from hca_smart_sync.sync_engine import SmartSync
from hca_smart_sync.config import Config

__all__ = ["SmartSync", "Config", "__version__"]

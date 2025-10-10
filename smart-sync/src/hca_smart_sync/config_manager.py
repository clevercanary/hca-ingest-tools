"""User configuration management for HCA Smart-Sync."""

import logging
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

logger = logging.getLogger(__name__)


def get_config_path() -> Path:
    """Get the path to the user config file.

    Returns:
        Path to ~/.hca-smart-sync/config.yaml
    """
    return Path.home() / ".hca-smart-sync" / "config.yaml"


def load_config(config_path: Path) -> Optional[Dict[str, Any]]:
    """Load configuration from YAML file.

    Args:
        config_path: Path to the config file

    Returns:
        Dictionary with config data, or None if file doesn't exist or is empty

    Raises:
        yaml.YAMLError: If the YAML file is malformed
    """
    if not config_path.exists():
        return None

    try:
        with open(config_path, "r") as f:
            config_data = yaml.safe_load(f)
    except yaml.YAMLError as e:
        logger.error(f"Failed to parse config file at {config_path}: {e}")
        raise yaml.YAMLError(
            f"Config file at {config_path} is malformed. "
            f"Please check the YAML syntax or delete the file to start fresh."
        ) from e

    # Handle empty file (yaml.safe_load returns None for empty files)
    if config_data is None:
        return None

    return config_data


def save_config(config_path: Path, config_data: Dict[str, Any]) -> None:
    """Save configuration to YAML file.

    Args:
        config_path: Path to the config file
        config_data: Dictionary with config data to save
    """
    # Create directory if it doesn't exist
    config_path.parent.mkdir(parents=True, exist_ok=True)

    with open(config_path, "w") as f:
        yaml.dump(config_data, f, default_flow_style=False, sort_keys=False)

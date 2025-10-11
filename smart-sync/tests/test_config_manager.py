"""Tests for user configuration management."""

import pytest
import yaml

from hca_smart_sync.config_manager import get_config_path, load_config, save_config


class TestConfigPath:
    """Tests for config file path resolution."""

    def test_get_config_path_default(self):
        """Test that config path is in user home directory."""
        config_path = get_config_path()
        assert config_path.name == "config.yaml"
        assert ".hca-smart-sync" in str(config_path)
        assert config_path.parent.name == ".hca-smart-sync"


class TestLoadConfig:
    """Tests for loading configuration."""

    def test_load_config_file_exists(self, tmp_path):
        """Test loading a valid config file."""
        config_file = tmp_path / "config.yaml"
        config_data = {"profile": "test-profile", "atlas": "gut-v1"}

        # Write test config
        with open(config_file, "w") as f:
            yaml.dump(config_data, f)

        # Load and verify
        loaded_config = load_config(config_file)
        assert loaded_config is not None
        assert loaded_config["profile"] == "test-profile"
        assert loaded_config["atlas"] == "gut-v1"

    def test_load_config_file_missing(self, tmp_path):
        """Test loading when config file doesn't exist."""
        config_file = tmp_path / "nonexistent.yaml"
        loaded_config = load_config(config_file)
        assert loaded_config is None

    def test_load_config_empty_file(self, tmp_path):
        """Test loading an empty config file."""
        config_file = tmp_path / "config.yaml"
        config_file.touch()

        loaded_config = load_config(config_file)
        # Empty file returns None or empty dict
        assert loaded_config is None or len(loaded_config) == 0

    def test_load_config_invalid_yaml(self, tmp_path):
        """Test loading a corrupted YAML file."""
        config_file = tmp_path / "config.yaml"
        with open(config_file, "w") as f:
            f.write("invalid: yaml: content: [")

        with pytest.raises(yaml.YAMLError):
            load_config(config_file)

    def test_load_config_partial_data(self, tmp_path):
        """Test loading config with only profile (no atlas)."""
        config_file = tmp_path / "config.yaml"
        config_data = {"profile": "test-profile"}

        with open(config_file, "w") as f:
            yaml.dump(config_data, f)

        loaded_config = load_config(config_file)
        assert loaded_config is not None
        assert loaded_config["profile"] == "test-profile"
        assert "atlas" not in loaded_config

    def test_load_config_with_only_atlas(self, tmp_path):
        """Test loading config with only atlas (no profile)."""
        config_file = tmp_path / "config.yaml"
        config_data = {"atlas": "immune-v1"}

        with open(config_file, "w") as f:
            yaml.dump(config_data, f)

        loaded_config = load_config(config_file)
        assert loaded_config is not None
        assert loaded_config["atlas"] == "immune-v1"
        assert "profile" not in loaded_config


class TestSaveConfig:
    """Tests for saving configuration."""

    def test_save_config_new_file(self, tmp_path):
        """Test saving config to a new file."""
        config_file = tmp_path / "config.yaml"
        config_data = {"profile": "my-profile", "atlas": "gut-v1"}

        save_config(config_file, config_data)

        # Verify file was created
        assert config_file.exists()

        # Verify content can be loaded back
        loaded_config = load_config(config_file)
        assert loaded_config == config_data

    def test_save_config_creates_parent_directory(self, tmp_path):
        """Test that save_config creates parent directory if it doesn't exist."""
        config_file = tmp_path / ".hca-smart-sync" / "config.yaml"
        config_data = {"profile": "test-profile", "atlas": "immune-v1"}

        # Directory doesn't exist yet
        assert not config_file.parent.exists()

        save_config(config_file, config_data)

        # Directory and file should now exist
        assert config_file.parent.exists()
        assert config_file.exists()

        # Verify content
        loaded_config = load_config(config_file)
        assert loaded_config == config_data

    def test_save_config_overwrites_existing(self, tmp_path):
        """Test that save_config overwrites existing config file."""
        config_file = tmp_path / "config.yaml"

        # Save initial config
        initial_data = {"profile": "old-profile", "atlas": "gut-v1"}
        save_config(config_file, initial_data)

        # Overwrite with new data
        new_data = {"profile": "new-profile", "atlas": "immune-v1"}
        save_config(config_file, new_data)

        # Verify new data is saved
        loaded_config = load_config(config_file)
        assert loaded_config == new_data
        assert loaded_config["profile"] == "new-profile"

    def test_save_config_partial_data(self, tmp_path):
        """Test saving config with only one field."""
        config_file = tmp_path / "config.yaml"
        config_data = {"profile": "my-profile"}

        save_config(config_file, config_data)

        loaded_config = load_config(config_file)
        assert loaded_config == config_data
        assert "atlas" not in loaded_config

    def test_save_config_yaml_format(self, tmp_path):
        """Test that saved YAML is human-readable (not flow style)."""
        config_file = tmp_path / "config.yaml"
        config_data = {"profile": "my-profile", "atlas": "gut-v1"}

        save_config(config_file, config_data)

        # Read raw file content
        with open(config_file, "r") as f:
            content = f.read()

        # Verify it's block style (has newlines), not flow style (all on one line)
        assert "\n" in content
        assert "profile:" in content
        assert "atlas:" in content
        # Should not be flow style like: {profile: my-profile, atlas: gut-v1}
        assert "{" not in content

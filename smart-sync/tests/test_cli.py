"""Tests for HCA Smart Sync CLI."""

import os
import pytest
from pathlib import Path
from unittest.mock import Mock, patch
from typer.testing import CliRunner
import click
import io

from hca_smart_sync.cli import (
    app, 
    _load_and_configure, 
    _validate_configuration, 
    _build_s3_path, 
    _resolve_local_path, 
    _initialize_sync_engine,
    error_msg,
    success_msg,
    format_file_count,
    format_status,
    main
)
from hca_smart_sync.config import Config


class TestCLI:
    """Test CLI interface."""
    
    def setup_method(self):
        """Set up test runner."""
        self.runner = CliRunner()
    
    def test_cli_help(self):
        """Test CLI help command."""
        result = self.runner.invoke(app, ["--help"])
        
        assert result.exit_code == 0
        assert "hca-smart-sync" in result.stdout or "Usage:" in result.stdout
    
    def test_sync_command_help(self):
        """Test sync command help (sync is the default command)."""
        result = self.runner.invoke(app, ["--help"])
        
        assert result.exit_code == 0
        assert "--dry-run" in result.stdout
        assert "--verbose" in result.stdout
    
    def test_sync_command_missing_args(self):
        """Test sync command with missing atlas argument."""
        result = self.runner.invoke(app, [])
        
        # Should fail due to missing required atlas argument
        assert result.exit_code != 0
    
    def test_sync_command_with_invalid_atlas(self):
        """Test sync command with invalid atlas name."""
        # Test with an atlas that would likely fail validation
        result = self.runner.invoke(app, ["invalid-atlas-name", "--dry-run"])
        
        # Should either fail or show some error (depending on validation)
        # This test mainly ensures the command structure works
        assert result.exit_code in [0, 1]  # Either succeeds (dry run) or fails (validation)
    
    def test_sync_command_with_invalid_environment(self):
        """Test sync command with invalid environment value."""
        # Test with invalid environment value - should be rejected by Typer enum validation
        result = self.runner.invoke(app, ["gut-v1", "--environment", "devv", "--dry-run"])
        
        # Should fail due to invalid environment enum value
        assert result.exit_code != 0
        # Check that error message mentions valid choices (Typer errors go to stderr)
        error_output = result.stderr if result.stderr else result.stdout
        assert "is not one of" in error_output or "Invalid value" in error_output
    
    def test_sync_command_with_valid_environments(self):
        """Test sync command with valid environment values."""
        # Test with valid environment values - should pass Typer enum validation
        # Note: These may still fail later due to AWS access, but enum validation should pass
        
        # Test prod environment
        result_prod = self.runner.invoke(app, ["gut-v1", "--environment", "prod", "--dry-run"])
        # Should not fail due to enum validation (may fail later for other reasons)
        # If it fails, it shouldn't be due to invalid enum value
        if result_prod.exit_code != 0:
            error_output = result_prod.stderr if result_prod.stderr else result_prod.stdout
            assert "is not one of" not in error_output
            assert "Invalid value for '--environment'" not in error_output
        
        # Test dev environment  
        result_dev = self.runner.invoke(app, ["gut-v1", "--environment", "dev", "--dry-run"])
        # Should not fail due to enum validation (may fail later for other reasons)
        if result_dev.exit_code != 0:
            error_output = result_dev.stderr if result_dev.stderr else result_dev.stdout
            assert "is not one of" not in error_output
            assert "Invalid value for '--environment'" not in error_output


class TestHelperFunctions:
    """Test CLI helper functions extracted during refactoring."""
    
    def test_load_and_configure_basic(self):
        """Test basic configuration loading."""
        with patch('hca_smart_sync.cli.Config') as mock_config_class:
            mock_config = Mock()
            mock_config.aws.profile = None
            mock_config.s3.bucket_name = None
            mock_config_class.return_value = mock_config
            
            result = _load_and_configure(None, None)
            
            assert result == mock_config
            mock_config_class.assert_called_once()
    
    def test_load_and_configure_with_overrides(self):
        """Test configuration loading with profile and bucket overrides."""
        with patch('hca_smart_sync.cli.Config') as mock_config_class:
            mock_config = Mock()
            mock_config.aws.profile = None
            mock_config.s3.bucket_name = None
            mock_config_class.return_value = mock_config
            
            result = _load_and_configure("test-profile", "test-bucket")
            
            assert result == mock_config
            assert mock_config.aws.profile == "test-profile"
            assert mock_config.s3.bucket_name == "test-bucket"
    
    def test_load_and_configure_exception(self):
        """Test configuration loading with exception."""
        with patch('hca_smart_sync.cli.Config') as mock_config_class:
            mock_config_class.side_effect = Exception("Config error")
            
            with pytest.raises(click.exceptions.Exit):
                _load_and_configure(None, None)
    
    def test_validate_configuration_valid(self):
        """Test configuration validation with valid config."""
        mock_config = Mock()
        mock_config.s3.bucket_name = "test-bucket"
        
        # Should not raise any exception
        _validate_configuration(mock_config)
    
    def test_validate_configuration_missing_bucket(self):
        """Test configuration validation with missing bucket."""
        mock_config = Mock()
        mock_config.s3.bucket_name = None
        
        with pytest.raises(click.exceptions.Exit):
            _validate_configuration(mock_config)
    
    def test_build_s3_path(self):
        """Test S3 path building."""
        result = _build_s3_path("test-bucket", "gut-v1", "source-datasets")
        expected = "s3://test-bucket/gut/gut-v1/source-datasets/"
        
        assert result == expected
    
    def test_build_s3_path_different_atlas(self):
        """Test S3 path building with different atlas."""
        result = _build_s3_path("my-bucket", "immune-v2", "integrated-objects")
        expected = "s3://my-bucket/immune/immune-v2/integrated-objects/"
        
        assert result == expected
    
    def test_resolve_local_path_with_path(self):
        """Test local path resolution with provided path."""
        test_path = "/tmp/test-data"
        result = _resolve_local_path(test_path)
        
        assert result == Path(test_path).resolve()
    
    def test_resolve_local_path_without_path(self):
        """Test local path resolution without provided path."""
        result = _resolve_local_path(None)
        
        assert result == Path.cwd()
    
    def test_initialize_sync_engine_basic(self):
        """Test basic sync engine initialization."""
        with patch('hca_smart_sync.cli.SmartSync') as mock_sync_class:
            mock_config = Mock()
            mock_console = Mock()
            mock_sync_engine = Mock()
            mock_sync_class.return_value = mock_sync_engine
            
            result = _initialize_sync_engine(mock_config, None, mock_console)
            
            assert result == mock_sync_engine
            mock_sync_class.assert_called_once_with(mock_config, console=mock_console)
    
    def test_initialize_sync_engine_with_profile(self):
        """Test sync engine initialization with profile override."""
        with patch('hca_smart_sync.cli.SmartSync') as mock_sync_class, \
             patch.dict('os.environ', {}, clear=True):
            mock_config = Mock()
            mock_console = Mock()
            mock_sync_engine = Mock()
            mock_sync_class.return_value = mock_sync_engine
            
            result = _initialize_sync_engine(mock_config, "test-profile", mock_console)
            
            assert result == mock_sync_engine
            mock_sync_class.assert_called_once_with(mock_config, console=mock_console)
            assert os.environ.get('AWS_PROFILE') == "test-profile"


class TestMessageFormatters:
    """Test message formatting helper functions."""
    
    def test_error_msg(self):
        """Test error message formatting."""
        result = error_msg("Test error")
        assert result == "[red]Test error[/red]"
    
    def test_success_msg(self):
        """Test success message formatting."""
        result = success_msg("Test success")
        assert result == "[green]Test success[/green]"
    
    def test_format_file_count(self):
        """Test file count formatting."""
        result = format_file_count(5, "Uploaded")
        assert result == "\nUploaded 5 file(s)"
        
        result = format_file_count(1, "Would upload")
        assert result == "\nWould upload 1 file(s)"
    
    def test_format_status(self):
        """Test status formatting."""
        result = format_status("Sync completed successfully")
        assert result == "[green]Sync completed successfully[/green]"


class TestCLIArgumentValidation:
    """Test CLI argument validation and error handling."""
    
    # These tests are obsolete since we removed custom error handling in Typer 0.16.0 upgrade
    # The main() function now just calls app() directly and Typer handles all errors natively
    pass

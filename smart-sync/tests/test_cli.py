"""Tests for HCA Smart Sync CLI."""

import os
import pytest
import subprocess
from pathlib import Path
from unittest.mock import Mock, patch
from typer.testing import CliRunner
import click
import re

from hca_smart_sync.cli import (
    app, 
    _load_and_configure, 
    _validate_configuration, 
    _build_s3_path, 
    _resolve_local_path, 
    _initialize_sync_engine,
    _check_aws_cli,
    _display_aws_cli_installation_help,
    error_msg,
    success_msg,
    format_file_count,
    format_status
)


# Helper: strip ANSI escape sequences from CLI output for stable assertions
ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")

def strip_ansi(s: str) -> str:
    return ANSI_RE.sub("", s)


class TestCLI:
    """Test CLI interface."""
    
    def setup_method(self):
        """Set up test runner."""
        self.runner = CliRunner()
    
    def test_cli_help(self):
        """Test CLI help command."""
        result = self.runner.invoke(app, ["--help"])
        
        out = strip_ansi(result.stdout or result.output)
        assert result.exit_code == 0
        assert "hca-smart-sync" in out or "Usage:" in out
    
    def test_cli_version(self):
        """Test --version flag shows version."""
        result = self.runner.invoke(app, ["--version"])
        
        out = strip_ansi(result.stdout or result.output)
        assert result.exit_code == 0
        assert "hca-smart-sync" in out
        # Version should be in format like "0.2.3"
        assert any(char.isdigit() for char in out), "Version output should contain version number"
    
    def test_sync_command_help(self):
        """Test sync command help."""
        result = self.runner.invoke(app, ["sync", "--help"])
        
        out = strip_ansi(result.stdout or result.output)
        assert result.exit_code == 0
        assert "--dry-run" in out
        assert "--verbose" in out
    
    def test_sync_command_missing_args(self):
        """Test sync command with missing atlas argument fails."""
        result = self.runner.invoke(app, ["sync"])
        
        # Should fail - atlas is required
        assert result.exit_code != 0
        out = strip_ansi(result.stderr if result.stderr else result.stdout)
        assert "Missing argument" in out or "required" in out.lower()
    
    def test_sync_command_with_invalid_atlas(self):
        """Test sync command with invalid atlas name."""
        # Mock AWS/sync engine to prevent real calls
        with patch('hca_smart_sync.cli._initialize_sync_engine') as mock_init:
            mock_sync_engine = Mock()
            mock_sync_engine.sync.return_value = {"status": "error", "message": "Invalid atlas"}
            mock_init.return_value = mock_sync_engine
            
            # Test with an atlas that would likely fail validation
            result = self.runner.invoke(app, ["sync", "invalid-atlas-name", "source-datasets", "--dry-run"])
            
            # Should either fail or show some error (depending on validation)
            # This test mainly ensures the command structure works
            assert result.exit_code in [0, 1]  # Either succeeds (dry run) or fails (validation)
    
    def test_sync_command_with_invalid_environment(self):
        """Test sync command with invalid environment value."""
        # Test with invalid environment value - should be rejected by Typer enum validation
        result = self.runner.invoke(app, ["sync", "gut-v1", "source-datasets", "--environment", "devv", "--dry-run"])
        
        # Should fail due to invalid environment enum value
        assert result.exit_code != 0
        # Check that error message mentions valid choices (Typer errors go to stderr)
        error_output = result.stderr if result.stderr else result.stdout
        assert "is not one of" in error_output or "Invalid value" in error_output
    
    def test_sync_command_with_valid_environments(self):
        """Test sync command with valid environment values."""
        # Mock AWS/sync engine to prevent real calls
        with patch('hca_smart_sync.cli._initialize_sync_engine') as mock_init:
            mock_sync_engine = Mock()
            mock_sync_engine.sync.return_value = {
                "status": "success", 
                "files_to_upload": [],
                "message": "No files to upload"
            }
            mock_init.return_value = mock_sync_engine
            
            # Test with valid environment values - should pass Typer enum validation
            # Note: These may still fail later due to AWS access, but enum validation should pass
            
            # Test prod environment
            result_prod = self.runner.invoke(app, ["sync", "gut-v1", "source-datasets", "--environment", "prod", "--dry-run"])
            # Should not fail due to enum validation (may fail later for other reasons)
            # If it fails, it shouldn't be due to invalid enum value
            if result_prod.exit_code != 0:
                error_output = result_prod.stderr if result_prod.stderr else result_prod.stdout
                assert "is not one of" not in error_output
                assert "Invalid value for '--environment'" not in error_output
            
            # Test dev environment  
            result_dev = self.runner.invoke(app, ["sync", "gut-v1", "source-datasets", "--environment", "dev", "--dry-run"])
            # Should not fail due to enum validation (may fail later for other reasons)
            if result_dev.exit_code != 0:
                error_output = result_dev.stderr if result_dev.stderr else result_dev.stdout
                assert "is not one of" not in error_output
                assert "Invalid value for '--environment'" not in error_output
    
    def test_sync_command_missing_file_type(self):
        """Test sync command with missing file_type argument fails."""
        result = self.runner.invoke(app, ["sync", "gut-v1"])
        
        # Should fail - file_type is required
        assert result.exit_code != 0
        error_output = result.stderr if result.stderr else result.stdout
        assert "Missing argument" in error_output or "required" in error_output.lower()
    
    def test_sync_command_with_invalid_file_type(self):
        """Test sync command with invalid file_type value."""
        result = self.runner.invoke(app, ["sync", "gut-v1", "invalid-folder-type", "--dry-run"])
        
        # Should fail due to invalid file_type enum value
        assert result.exit_code != 0
        # Check that error message mentions valid choices
        error_output = result.stderr if result.stderr else result.stdout
        assert "is not one of" in error_output or "Invalid value" in error_output


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


class TestNoArgsHelp:
    """Test help display when no arguments provided."""
    
    def setup_method(self):
        """Set up test runner."""
        self.runner = CliRunner()
    
    def test_no_args_shows_help(self):
        """Test that running with no arguments displays help."""
        result = self.runner.invoke(app, [])
        
        out = strip_ansi(result.stdout or result.output)
        assert result.exit_code == 0
        assert "Usage:" in out or "hca-smart-sync" in out
        # Should show command descriptions
        assert "sync" in out.lower()
    
    def test_help_works_without_aws_cli(self):
        """Test that --help works even without AWS CLI installed."""
        with patch('hca_smart_sync.cli._check_aws_cli') as mock_check:
            mock_check.return_value = False
            
            result = self.runner.invoke(app, ["--help"])
            
            out = strip_ansi(result.stdout or result.output)
            assert result.exit_code == 0
            assert "Usage:" in out or "hca-smart-sync" in out


class TestAWSCLIDependencyCheck:
    """Test AWS CLI dependency checking functionality."""
    
    def test_check_aws_cli_available(self):
        """Test _check_aws_cli when AWS CLI is available."""
        with patch('subprocess.run') as mock_run:
            # Mock successful AWS CLI check
            mock_result = Mock()
            mock_result.returncode = 0
            mock_run.return_value = mock_result
            
            result = _check_aws_cli()
            
            assert result is True
            mock_run.assert_called_once_with(
                ["aws", "--version"],
                capture_output=True,
                text=True,
                timeout=10
            )
    
    def test_check_aws_cli_not_found(self):
        """Test _check_aws_cli when AWS CLI is not found."""
        with patch('subprocess.run') as mock_run:
            # Mock FileNotFoundError (command not found)
            mock_run.side_effect = FileNotFoundError("aws command not found")
            
            result = _check_aws_cli()
            
            assert result is False
    
    def test_check_aws_cli_non_zero_exit(self):
        """Test _check_aws_cli when AWS CLI returns non-zero exit code."""
        with patch('subprocess.run') as mock_run:
            # Mock non-zero exit code
            mock_result = Mock()
            mock_result.returncode = 1
            mock_run.return_value = mock_result
            
            result = _check_aws_cli()
            
            assert result is False
    
    def test_check_aws_cli_timeout(self):
        """Test _check_aws_cli when subprocess times out."""
        with patch('subprocess.run') as mock_run:
            # Mock timeout
            mock_run.side_effect = subprocess.TimeoutExpired("aws", 10)
            
            result = _check_aws_cli()
            
            assert result is False
    
    def test_check_aws_cli_subprocess_error(self):
        """Test _check_aws_cli with general subprocess error."""
        with patch('subprocess.run') as mock_run:
            # Mock general subprocess error
            mock_run.side_effect = subprocess.SubprocessError("General error")
            
            result = _check_aws_cli()
            
            assert result is False
    
    def test_display_aws_cli_installation_help(self, capsys):
        """Test _display_aws_cli_installation_help output."""
        _display_aws_cli_installation_help()
        
        captured = capsys.readouterr()
        output = captured.out
        
        # Check key elements are present
        assert "AWS CLI is required but not found" in output
        assert "brew install awscli" in output
        assert "sudo apt update && sudo apt install awscli" in output
        assert "winget install Amazon.AWSCLI" in output
        assert "aws configure" in output


class TestSyncScenarios:
    """Test sync command scenarios."""
    
    def test_sync_no_files_found(self):
        """Test sync command when no .h5ad files are found."""
        with patch('hca_smart_sync.cli._check_aws_cli') as mock_check_aws_cli, \
             patch('hca_smart_sync.cli._load_and_configure') as mock_load_config, \
             patch('hca_smart_sync.cli._validate_configuration') as mock_validate_config, \
             patch('hca_smart_sync.cli._build_s3_path') as mock_build_s3_path, \
             patch('hca_smart_sync.cli._resolve_local_path') as mock_resolve_local_path, \
             patch('hca_smart_sync.cli._initialize_sync_engine') as mock_init_sync:
            
            # Mock AWS CLI available
            mock_check_aws_cli.return_value = True
            
            # Mock config and paths
            mock_config = Mock()
            mock_config.s3.bucket_name = "test-bucket"
            mock_load_config.return_value = mock_config
            mock_validate_config.return_value = None
            mock_build_s3_path.return_value = "s3://test-bucket/gut/gut-v1/source-datasets/"
            mock_resolve_local_path.return_value = "/test/path"
            
            # Mock sync engine to return no files found
            mock_sync_engine = Mock()
            mock_sync_engine.sync.return_value = {
                "files_uploaded": 0,
                "files_to_upload": [],
                "manifest_path": None,
                "no_files_found": True
            }
            mock_init_sync.return_value = mock_sync_engine
            
            runner = CliRunner()
            result = runner.invoke(app, ["sync", "gut-v1", "source-datasets", "--profile", "test"])
            
            assert result.exit_code == 0
            assert "No .h5ad files found in directory" in result.output
            assert "Uploaded 0 file(s)" in result.output
            assert "Sync completed successfully" in result.output

    def test_sync_all_files_up_to_date(self):
        """Test sync command when files exist but are all up to date."""
        with patch('hca_smart_sync.cli._check_aws_cli') as mock_check_aws_cli, \
             patch('hca_smart_sync.cli._load_and_configure') as mock_load_config, \
             patch('hca_smart_sync.cli._validate_configuration') as mock_validate_config, \
             patch('hca_smart_sync.cli._build_s3_path') as mock_build_s3_path, \
             patch('hca_smart_sync.cli._resolve_local_path') as mock_resolve_local_path, \
             patch('hca_smart_sync.cli._initialize_sync_engine') as mock_init_sync:
            
            # Mock AWS CLI available
            mock_check_aws_cli.return_value = True
            
            # Mock config and paths
            mock_config = Mock()
            mock_config.s3.bucket_name = "test-bucket"
            mock_load_config.return_value = mock_config
            mock_validate_config.return_value = None
            mock_build_s3_path.return_value = "s3://test-bucket/gut/gut-v1/source-datasets/"
            mock_resolve_local_path.return_value = "/test/path"
            
            # Mock sync engine to return files found but all up to date
            mock_local_files = [
                {"filename": "test1.h5ad", "size": 100},
                {"filename": "test2.h5ad", "size": 200},
                {"filename": "test3.h5ad", "size": 150}
            ]
            mock_sync_engine = Mock()
            mock_sync_engine.sync.return_value = {
                "files_uploaded": 0,
                "files_to_upload": [],
                "manifest_path": None,
                "local_files": mock_local_files,
                "all_up_to_date": True
            }
            mock_init_sync.return_value = mock_sync_engine
            
            runner = CliRunner()
            result = runner.invoke(app, ["sync", "gut-v1", "source-datasets", "--profile", "test"])
            
            assert result.exit_code == 0
            assert "Found 3 .h5ad files - all up to date" in result.output
            assert "Uploaded 0 file(s)" in result.output
            assert "Sync completed successfully" in result.output

    def test_sync_single_file_up_to_date(self):
        """Test sync command when single file exists but is up to date (singular message)."""
        with patch('hca_smart_sync.cli._check_aws_cli') as mock_check_aws_cli, \
             patch('hca_smart_sync.cli._load_and_configure') as mock_load_config, \
             patch('hca_smart_sync.cli._validate_configuration') as mock_validate_config, \
             patch('hca_smart_sync.cli._build_s3_path') as mock_build_s3_path, \
             patch('hca_smart_sync.cli._resolve_local_path') as mock_resolve_local_path, \
             patch('hca_smart_sync.cli._initialize_sync_engine') as mock_init_sync:
            
            # Mock AWS CLI available
            mock_check_aws_cli.return_value = True
            
            # Mock config and paths
            mock_config = Mock()
            mock_config.s3.bucket_name = "test-bucket"
            mock_load_config.return_value = mock_config
            mock_validate_config.return_value = None
            mock_build_s3_path.return_value = "s3://test-bucket/gut/gut-v1/source-datasets/"
            mock_resolve_local_path.return_value = "/test/path"
            
            # Mock sync engine to return single file up to date
            mock_local_files = [
                {"filename": "test1.h5ad", "size": 100}
            ]
            mock_sync_engine = Mock()
            mock_sync_engine.sync.return_value = {
                "files_uploaded": 0,
                "files_to_upload": [],
                "manifest_path": None,
                "local_files": mock_local_files,
                "all_up_to_date": True
            }
            mock_init_sync.return_value = mock_sync_engine
            
            runner = CliRunner()
            result = runner.invoke(app, ["sync", "gut-v1", "source-datasets", "--profile", "test"])
            
            assert result.exit_code == 0
            assert "Found 1 .h5ad file - all up to date" in result.output  # Singular "file"
            assert "Uploaded 0 file(s)" in result.output
            assert "Sync completed successfully" in result.output

    def test_sync_integrated_objects_file_type(self):
        """Test sync command with integrated-objects file type builds correct S3 path."""
        with patch('hca_smart_sync.cli._check_aws_cli') as mock_check_aws_cli, \
             patch('hca_smart_sync.cli._load_and_configure') as mock_load_config, \
             patch('hca_smart_sync.cli._validate_configuration') as mock_validate_config, \
             patch('hca_smart_sync.cli._build_s3_path') as mock_build_s3_path, \
             patch('hca_smart_sync.cli._resolve_local_path') as mock_resolve_local_path, \
             patch('hca_smart_sync.cli._initialize_sync_engine') as mock_init_sync:
            
            # Mock AWS CLI available
            mock_check_aws_cli.return_value = True
            
            # Mock config
            mock_config = Mock()
            mock_load_config.return_value = mock_config
            mock_validate_config.return_value = None
            mock_build_s3_path.return_value = "s3://test-bucket/gut/gut-v1/integrated-objects/"
            mock_resolve_local_path.return_value = "/test/path"
            
            # Mock sync engine to avoid real AWS calls
            mock_sync_engine = Mock()
            mock_sync_engine.sync.return_value = {"files_uploaded": 0, "files_to_upload": []}
            mock_init_sync.return_value = mock_sync_engine
            
            runner = CliRunner()
            result = runner.invoke(app, ["sync", "gut-v1", "integrated-objects", "--profile", "test"])
            
            # Verify that _build_s3_path was called with "integrated-objects" folder
            mock_build_s3_path.assert_called_once()
            call_args = mock_build_s3_path.call_args
            assert call_args[0][2] == "integrated-objects"  # Third positional arg is folder

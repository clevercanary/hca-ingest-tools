"""Command-line interface for HCA Smart Sync."""

import os
import subprocess
from enum import Enum
from pathlib import Path
from typing import Optional
from typing_extensions import Annotated
from typing import List, Dict

import typer
from rich.console import Console
from rich.table import Table
from rich.prompt import Confirm

from hca_smart_sync.config import Config
from hca_smart_sync.sync_engine import SmartSync

# Create the Typer app instance with proper configuration
app = typer.Typer(
    name="hca-smart-sync",
    help="Intelligent S3 synchronization for HCA Atlas data",
    add_completion=False,  # Disable shell completion for simplicity
)
console = Console()

# Message templates for consistent formatting
class Messages:
    # Error messages
    CONFIG_LOAD_ERROR = "Error loading configuration: {error}"
    CONFIG_INIT_ERROR = "Failed to initialize configuration: {error}"
    CONFIG_SHOW_ERROR = "Failed to load configuration: {error}"
    SYNC_ERROR = "Sync failed: {error}"
    BUCKET_NOT_CONFIGURED = "Error: S3 bucket not configured. Provide bucket argument or set in config"
    
    # Success messages
    CONFIG_INITIALIZING = "Initializing HCA Smart Sync Configuration"
    CONFIG_INITIALIZED = "Configuration initialized successfully"
    
    # Result states
    DRY_RUN_COMPLETED = "Dry run completed"
    SYNC_CANCELLED = "Sync canceled by user"
    SYNC_COMPLETED = "Sync completed successfully"

# Result message lookup table
RESULT_MESSAGES = {
    "dry_run": {
        "action": "Would upload",
        "status": Messages.DRY_RUN_COMPLETED,
        "show_file_count": False
    },
    "cancelled": {
        "action": "Uploaded",
        "status": Messages.SYNC_CANCELLED,
        "show_file_count": True
    },
    "completed": {
        "action": "Uploaded",
        "status": Messages.SYNC_COMPLETED, 
        "show_file_count": True
    }
}

# Common message helpers
def error_msg(message: str) -> str:
    """Format error message with consistent styling."""
    return f"[red]{message}[/red]"

def success_msg(message: str) -> str:
    """Format success message with consistent styling."""
    return f"[green]{message}[/green]"

# Common formatting helpers
def format_file_count(file_count: int, action: str) -> str:
    """Format file count message with consistent styling."""
    return f"\n{action} {file_count} file(s)"

def format_status(status: str) -> str:
    """Format status message with consistent styling."""
    return f"[green]{status}[/green]"

def format_tool(tool: str) -> str:
    """Format tool message with performance context and recommendations."""
    if tool == "s5cmd":
        return "[white]Using s5cmd for best performance[/white]"
    else:  # aws
        return "[white]Using AWS CLI for uploads. Install s5cmd for better performance.[/white]"

# Banner display function
def _display_banner(local_path: Path, s3_path: str, dry_run: bool = False) -> None:
    """Display the HCA Smart-Sync banner and configuration."""
    console.print("\n[#4A90E2]" + "="*60 + "[/#4A90E2]")
    console.print("[#4A90E2]║" + "HCA Smart-Sync Tool".center(58) + "║[/#4A90E2]")
    console.print("[#4A90E2]" + "="*60 + "[/#4A90E2]")
    console.print()
    console.print(f"[bright_black]Local Path: {local_path}[/bright_black]")
    console.print(f"[bright_black]S3 Target: {s3_path}[/bright_black]")
    if dry_run:
        console.print()
        console.print("[bold]DRY RUN MODE - No files will be uploaded[/bold]")
    console.print()

def _display_step(step_number: int, description: str) -> None:
    """Display a numbered step in the sync process."""
    console.print(f"[#4A90E2]Step {step_number}: {description}...[/#4A90E2]")

def _display_upload_plan(files_to_upload: List[Dict], s3_path: str, dry_run: bool) -> None:
    """Display the upload plan to the user."""
    action = "Would upload" if dry_run else "Will upload"
    
    console.print("\n[bold green]Upload Plan[/bold green]")
    
    table = Table(border_style="bright_black")
    table.add_column("File", style="bright_black")
    table.add_column("Size", style="bright_black")
    table.add_column("Reason", style="bright_black")
    table.add_column("SHA256", style="bright_black")
    
    total_size = 0
    for file_info in files_to_upload:
        size_mb = file_info['size'] / (1024 * 1024)
        total_size += file_info['size']
        
        table.add_row(
            file_info['filename'],
            f"{size_mb:.1f} MB",
            file_info['reason'],
            file_info['checksum'][:16] + "..."
        )
    
    console.print(table)
    
    total_mb = total_size / (1024 * 1024)
    console.print(f"\n[bold]{action} {len(files_to_upload)} files ({total_mb:.1f} MB total)[/bold]")


# Configuration helpers
def _load_and_configure(profile: Optional[str], bucket: Optional[str]) -> Config:
    """Load configuration and apply overrides."""
    try:
        config = Config()
        if profile:
            config.aws.profile = profile
        if bucket:
            config.s3.bucket_name = bucket
        return config
    except Exception as e:
        console.print(error_msg(Messages.CONFIG_LOAD_ERROR.format(error=e)))
        raise typer.Exit(1)

def _validate_configuration(config: Config) -> None:
    """Validate required configuration settings."""
    if not config.s3.bucket_name:
        console.print(error_msg(Messages.BUCKET_NOT_CONFIGURED))
        raise typer.Exit(1)

def _build_s3_path(bucket_name: str, atlas: str, folder: str) -> str:
    """Build S3 path from components."""
    bionetwork = atlas.split('-')[0]
    return f"s3://{bucket_name}/{bionetwork}/{atlas}/{folder}/"

def _resolve_local_path(local_path: Optional[str]) -> Path:
    """Resolve local directory to scan."""
    if local_path:
        return Path(local_path).resolve()
    else:
        return Path.cwd()

def _initialize_sync_engine(config: Config, profile: Optional[str], console: Console) -> SmartSync:
    """Initialize the sync engine with AWS profile."""
    # Set AWS profile in environment if provided
    if profile:
        os.environ['AWS_PROFILE'] = profile
    
    return SmartSync(config, console=console)

def _check_aws_cli() -> bool:
    """Check if AWS CLI is installed and accessible."""
    try:
        result = subprocess.run(
            ["aws", "--version"],
            capture_output=True,
            text=True,
            timeout=10
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError, subprocess.SubprocessError):
        return False

def _display_aws_cli_installation_help() -> None:
    """Display helpful AWS CLI installation instructions."""
    typer.secho("AWS CLI is required but not found on your system.", fg=typer.colors.RED)
    
    help_text = """
Please install AWS CLI v2:

macOS:     brew install awscli
Linux:     sudo apt update && sudo apt install awscli  
Windows:   winget install Amazon.AWSCLI

Alternative: https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html

After installation, configure your credentials:
  aws configure
  # OR: aws configure --profile your-profile-name
"""
    typer.echo(help_text)


class Environment(str, Enum):
    prod = "prod"
    dev = "dev"

@app.command()
def sync(
    atlas: Annotated[str, typer.Argument(help="Atlas name (e.g., gut-v1, immune-v1)")],
    dry_run: Annotated[bool, typer.Option(help="Dry run mode")] = False,
    verbose: Annotated[bool, typer.Option(help="Verbose output")] = False,
    profile: Annotated[Optional[str], typer.Option(help="AWS profile")] = None,
    environment: Annotated[Environment, typer.Option(help="Environment: prod or dev (default: prod)")] = Environment.prod,
    folder: Annotated[str, typer.Option(help="Target folder (default: source-datasets)")] = "source-datasets",
    force: Annotated[bool, typer.Option(help="Force upload")] = False,
    local_path: Annotated[Optional[str], typer.Option(help="Local directory to scan (defaults to current directory)")] = None,
) -> None:
    """Sync .h5ad files from local directory to S3."""
    
    # Determine bucket based on environment
    if environment == Environment.prod:
        bucket = "hca-atlas-tracker-data"
    elif environment == Environment.dev:
        bucket = "hca-atlas-tracker-data-dev"
    
    # Load and validate configuration
    config = _load_and_configure(profile, bucket)
    _validate_configuration(config)
    
    # Build paths
    s3_path = _build_s3_path(config.s3.bucket_name, atlas, folder)
    current_dir = _resolve_local_path(local_path)
    
    # Display banner
    _display_banner(current_dir, s3_path, dry_run)
    
    # Step 1: Check AWS CLI dependency
    _display_step(1, "Checking AWS CLI dependency")
    if not _check_aws_cli():
        _display_aws_cli_installation_help()
        raise typer.Exit(1)
    
    # Step 2: Validate S3 access
    _display_step(2, "Validating S3 access")
    
    # Initialize sync engine and perform sync
    try:
        sync_engine = _initialize_sync_engine(config, profile, console)
        
        # Step 3: Determine upload tool
        _display_step(3, "Determining upload tool")
        upload_tool = sync_engine._detect_upload_tool()
        console.print(format_tool(upload_tool))
        
        # Step 4: Scan local files
        _display_step(4, "Scanning local file system for .h5ad files")
        
        # Perform sync to get upload plan (always get plan first except for dry_run)
        if dry_run:
            # Dry run handles its own display and stops
            result = sync_engine.sync(
                local_path=current_dir,
                s3_path=s3_path,
                dry_run=True,
                verbose=verbose,
                force=force,
                plan_only=False
            )
        else:
            # For normal and force mode, get plan first
            result = sync_engine.sync(
                local_path=current_dir,
                s3_path=s3_path,
                dry_run=False,
                verbose=verbose,
                force=force,
                plan_only=True  # Just get the plan
            )
        
        # Handle S3 access errors
        if result.get('error') == 'access_denied':
            console.print("\n[red]S3 access validation failed. Cannot proceed with sync.[/red]")
            console.print("[yellow]Try using the correct AWS profile with --profile option[/yellow]")
            raise typer.Exit(1)
        
        # Handle no files found
        if result.get('no_files_found'):
            console.print("\n[yellow]No .h5ad files found in directory[/yellow]")
            console.print("\n[green]Uploaded 0 file(s)[/green]")
            console.print("[green]Sync completed successfully[/green]")
            return
        
        # Handle files found but all up-to-date
        if result.get('all_up_to_date'):
            local_files = result.get('local_files', [])
            file_count = len(local_files)
            console.print(f"\n[green]Found {file_count} .h5ad file{'s' if file_count != 1 else ''} - all up to date[/green]")
            console.print("\n[green]Uploaded 0 file(s)[/green]")
            console.print("[green]Sync completed successfully[/green]")
            return
        
        # Step 5: Compare with S3
        _display_step(5, "Comparing with S3 (using SHA256 checksums and file size)")
        
        # Display upload plan for all modes
        if 'files_to_upload' in result and result['files_to_upload']:
            _display_upload_plan(result['files_to_upload'], s3_path, dry_run)
            
            # Handle confirmation and execution based on mode
            if dry_run:
                # Dry run: plan shown, no upload, no confirmation needed
                pass
            else:
                # Both normal and force mode: plan shown, ask for confirmation, then upload
                if not Confirm.ask("\nProceed with upload?"):
                    console.print("\n[green]Sync canceled by user[/green]")
                    return
                console.print()  # Add blank line after confirmation
                
                # Step 6: Generate manifest
                _display_step(6, "Generating and saving manifest locally")
                
                # Step 7: Upload files
                _display_step(7, "Uploading files")
                
                # Upload with the original force setting (preserves normal vs force behavior)
                result = sync_engine.sync(
                    local_path=current_dir,
                    s3_path=s3_path,
                    dry_run=False,
                    verbose=verbose,
                    force=force,  # Use original force setting (True for force mode, False for normal)
                    plan_only=False  # Actually execute the upload
                )
                
                # Step 8: Upload manifest (if files were uploaded)
                if result.get('files_uploaded', 0) > 0:
                    _display_step(8, "Uploading manifest to S3")
        else:
            # No files to upload - but only show "all up to date" if there are actually files
            local_files = result.get('local_files', [])
            if local_files:
                console.print(f"\nFound {len(local_files)} .h5ad files - all up to date")
            # If no local files, the no_files_found check above already handled it
        
        # Display results
        _display_results(result, dry_run)
        
    except Exception as e:
        console.print(error_msg(Messages.SYNC_ERROR.format(error=e)))
        if verbose:
            console.print_exception()
        raise typer.Exit(1)


def _display_results(result: dict, dry_run: bool) -> None:
    """Display sync results."""
    file_count = result.get('files_uploaded', 0)
    cancelled = result.get('cancelled', False)
    
    # Determine result state and get appropriate messages
    if dry_run:
        state = "dry_run"
    elif cancelled:
        state = "cancelled"
    else:
        state = "completed"
    
    msg = RESULT_MESSAGES[state]
    
    # Display file count if needed (consistent f-string formatting)
    if msg["show_file_count"]:
        console.print(format_file_count(file_count, msg["action"]))
    
    # Display status message (always green for success states)
    console.print(format_status(msg["status"]))
    console.print()  # Add spacing after results


def main() -> None:
    """Main entry point for the CLI."""
    if not _check_aws_cli():
        _display_aws_cli_installation_help()
        raise typer.Exit(1)
    app()


if __name__ == "__main__":
    main()

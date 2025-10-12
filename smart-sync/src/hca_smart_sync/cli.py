"""Command-line interface for HCA Smart Sync."""

import os
import subprocess
from enum import Enum
from pathlib import Path
from typing import Optional, Any, Tuple
from typing_extensions import Annotated
from typing import List, Dict

import typer
from rich.console import Console
from rich.table import Table
from rich.prompt import Confirm

from hca_smart_sync.config import Config
from hca_smart_sync.sync_engine import SmartSync
from hca_smart_sync.config_manager import get_config_path, load_config, save_config
from hca_smart_sync import __version__
import yaml

# Create the Typer app instance with proper configuration
app = typer.Typer(
    name="hca-smart-sync",
    help="Intelligent S3 synchronization for HCA Atlas data",
    epilog="💡 Tip: Run 'hca-smart-sync sync --help' for detailed sync command options",
    add_completion=False,  # Disable shell completion for simplicity
)
console = Console()


@app.callback(invoke_without_command=True)
def main_callback(
    ctx: typer.Context,
    version: Annotated[bool, typer.Option("--version", help="Show version and exit")] = False,
) -> None:
    """HCA Smart-Sync - Intelligent S3 synchronization for HCA Atlas data."""
    # Handle version flag
    if version:
        typer.echo(f"hca-smart-sync {__version__}")
        raise typer.Exit(0)
    
    # If no subcommand was invoked, show help
    if ctx.invoked_subcommand is None:
        typer.echo(ctx.get_help())
        raise typer.Exit(0)

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

def _parse_sync_arguments(
    arg1: Optional[str], 
    arg2: Optional[str], 
    user_config: Dict[str, Any]
) -> Tuple[Optional[str], Optional[str], bool]:
    """Parse sync command arguments to determine atlas and file type.
    
    Supports two usage patterns:
    1. "sync <file_type>" - uses atlas from config
    2. "sync <atlas> <file_type>" - explicit atlas and file type
    
    Args:
        arg1: First positional argument (atlas or file type)
        arg2: Second positional argument (file type if arg1 is atlas)
        user_config: User configuration dictionary
        
    Returns:
        Tuple of (atlas, file_type_str, atlas_from_config)
        
    Raises:
        typer.Exit: If arguments are invalid
    """
    if arg1 in KNOWN_FILE_TYPES:
        # Case 1: "sync source-datasets" - file_type provided, get atlas from config
        if arg2:
            # User provided two args when file type came first - they're confused about syntax
            console.print("[red]✗ Error: When file type is specified first, no second argument is allowed[/red]")
            console.print(f"[dim]You provided: file_type='{arg1}', unexpected='{arg2}'[/dim]")
            console.print("\nCorrect usage:")
            console.print(f"  hca-smart-sync sync {arg1}              # Uses atlas from config")
            console.print(f"  hca-smart-sync sync <atlas> {arg1}      # Specify both atlas and file type")
            raise typer.Exit(1)
        return user_config.get('atlas'), arg1, True
        
    elif arg2 in KNOWN_FILE_TYPES:
        # Case 2: "sync gut-v1 source-datasets" - atlas first, file type second
        return arg1, arg2, False
        
    elif arg1 and not arg2:
        # Case 3: Only one arg provided and it's not a known file type
        console.print(f"[red]✗ Error: File type required when providing atlas '{arg1}'[/red]")
        console.print(f"[dim]Valid file types: {', '.join(KNOWN_FILE_TYPES)}[/dim]")
        console.print("\nUsage examples:")
        console.print(f"  hca-smart-sync sync {arg1} source-datasets")
        console.print(f"  hca-smart-sync sync {arg1} integrated-objects")
        raise typer.Exit(1)
        
    elif arg1 and arg2:
        # Case 4: "sync something something" - neither is a known file type
        console.print(f"[red]✗ Error: Unrecognized file type. Must be one of: {', '.join(KNOWN_FILE_TYPES)}[/red]")
        console.print(f"[dim]Got: arg1='{arg1}', arg2='{arg2}'[/dim]")
        raise typer.Exit(1)
        
    else:
        # Case 5: No arguments at all - require file type
        console.print("[red]✗ Error: File type required[/red]")
        console.print(f"[dim]Valid file types: {', '.join(KNOWN_FILE_TYPES)}[/dim]")
        console.print("\nUsage examples:")
        console.print("  hca-smart-sync sync source-datasets")
        console.print("  hca-smart-sync sync integrated-objects")
        if user_config.get('atlas'):
            console.print(f"  hca-smart-sync sync {user_config.get('atlas')} source-datasets")
        raise typer.Exit(1)

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

class FileType(str, Enum):
    source_datasets = "source-datasets"
    integrated_objects = "integrated-objects"

# Derive valid file types from enum to maintain single source of truth
KNOWN_FILE_TYPES = {ft.value for ft in FileType}

@app.command()
def sync(
    arg1: Annotated[Optional[str], typer.Argument(help="Atlas name or file type")] = None,
    arg2: Annotated[Optional[str], typer.Argument(help="File type (if atlas provided first)")] = None,
    dry_run: Annotated[bool, typer.Option(help="Dry run mode")] = False,
    verbose: Annotated[bool, typer.Option(help="Verbose output")] = False,
    profile: Annotated[Optional[str], typer.Option(help="AWS profile - uses config default if not specified")] = None,
    environment: Annotated[Environment, typer.Option(help="Environment: prod or dev (default: prod)")] = Environment.prod,
    force: Annotated[bool, typer.Option(help="Force upload")] = False,
    local_path: Annotated[Optional[str], typer.Option(help="Local directory to scan (defaults to current directory)")] = None,
) -> None:
    """Sync .h5ad files from local directory to S3.
    
    Usage examples:
      hca-smart-sync sync gut-v1 source-datasets        # Atlas first, then file type
      hca-smart-sync sync source-datasets               # File type only (uses config atlas)
    """
    
    # Load user config file for defaults
    config_path = get_config_path()
    try:
        user_config = load_config(config_path)
    except yaml.YAMLError:
        console.print("[yellow]Warning: Config file is malformed. Ignoring config file.[/yellow]")
        user_config = None
    
    if user_config is None:
        user_config = {}
    
    # Parse arguments to determine atlas and file type
    atlas, file_type_str, atlas_from_config = _parse_sync_arguments(arg1, arg2, user_config)
    
    # Convert file_type string to enum
    try:
        file_type = FileType(file_type_str)
    except ValueError:
        console.print(f"[red]✗ Error: Invalid file type '{file_type_str}'[/red]")
        raise typer.Exit(1)
    
    # Use config defaults if not already set
    if profile is None and "profile" in user_config:
        profile = user_config["profile"]
        console.print(f"[dim]Using profile from config: {profile}[/dim]")
    
    # Show message if atlas actually came from config
    if atlas_from_config and atlas:
        console.print(f"[dim]Using atlas from config: {atlas}[/dim]")
    
    # Validate atlas is provided
    if atlas is None:
        console.print("[red]✗ Error: Atlas is required.[/red]")
        console.print("Either provide atlas as an argument or set a default in config:")
        console.print("  hca-smart-sync config init")
        raise typer.Exit(1)
    
    # Determine bucket based on environment
    if environment == Environment.prod:
        bucket = "hca-atlas-tracker-data"
    elif environment == Environment.dev:
        bucket = "hca-atlas-tracker-data-dev"
    
    # Load and validate configuration
    config = _load_and_configure(profile, bucket)
    _validate_configuration(config)
    
    # Build paths
    s3_path = _build_s3_path(config.s3.bucket_name, atlas, file_type.value)
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


# Create config command group
config_app = typer.Typer(help="Manage configuration settings")
app.add_typer(config_app, name="config")


@config_app.command("show")
def config_show() -> None:
    """Display current configuration settings."""
    config_path = get_config_path()
    
    try:
        config_data = load_config(config_path)
    except yaml.YAMLError:
        console.print(f"[red]✗ Error:[/red] Config file at {config_path} is malformed.")
        console.print("[yellow]Please check the YAML syntax or delete the file to start fresh.[/yellow]")
        raise typer.Exit(1)
    
    if config_data is None:
        console.print(f"[yellow]No configuration file found at {config_path}[/yellow]")
        console.print("Run 'hca-smart-sync config init' to create one.")
        return
    
    # Display config
    console.print(f"\n[bold]Configuration:[/bold] {config_path}")
    console.print("─" * 50)
    
    if "profile" in config_data:
        console.print(f"profile: {config_data['profile']}")
    else:
        console.print("profile: [dim](not set)[/dim]")
    
    if "atlas" in config_data:
        console.print(f"atlas: {config_data['atlas']}")
    else:
        console.print("atlas: [dim](not set)[/dim]")
    
    console.print()


@config_app.command("init")
def config_init() -> None:
    """Initialize or update configuration settings interactively."""
    config_path = get_config_path()
    
    # Load existing config if it exists
    try:
        existing_config = load_config(config_path)
    except yaml.YAMLError:
        console.print("[yellow]Warning: Existing config file is malformed. Creating new configuration.[/yellow]")
        existing_config = None
    
    if existing_config is None:
        existing_config = {}
    
    console.print("\n[bold]HCA Smart-Sync Configuration[/bold]")
    console.print("─" * 50)
    
    # Prompt for AWS Profile
    current_profile = existing_config.get("profile", "")
    if current_profile:
        profile_prompt = f"AWS Profile [current: {current_profile}]"
    else:
        profile_prompt = "AWS Profile"
    
    profile = typer.prompt(profile_prompt, default=current_profile, show_default=False)
    
    # Prompt for Default Atlas
    current_atlas = existing_config.get("atlas", "")
    if current_atlas:
        atlas_prompt = f"Default Atlas [current: {current_atlas}]"
    else:
        atlas_prompt = "Default Atlas"
    
    atlas = typer.prompt(atlas_prompt, default=current_atlas, show_default=False)
    
    # Build config data (only include non-empty values)
    config_data = {}
    if profile:
        config_data["profile"] = profile
    if atlas:
        config_data["atlas"] = atlas
    
    # Save configuration
    save_config(config_path, config_data)
    
    console.print()
    console.print(f"[green]✓ Configuration saved to {config_path}[/green]")
    console.print()


def main() -> None:
    """Main entry point for the CLI."""
    app()


if __name__ == "__main__":
    main()

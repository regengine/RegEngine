#!/usr/bin/env python3
"""
RegEngine CLI
=============
Command-line interface for RegEngine operations.

Commands:
- compile vertical <name>: Compile a vertical from YAML schemas
- validate vertical <name>: Validate vertical schemas without compiling
- list verticals: List all available verticals
"""

import click
import sys
from pathlib import Path
import os

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# NOTE: despite the "6 services → monolith" direction, the compiler stack
# lives at ``kernel/control/`` today. The prior import path
# ``services.vertical_compiler.compiler`` has never existed on disk, so
# every invocation of ``regengine compile vertical`` died with a
# ModuleNotFoundError before executing any user code (#1309).
from kernel.control.compiler import VerticalCompiler


@click.group()
def cli():
    """RegEngine - Regulatory Compliance Engine CLI"""
    pass


@cli.group()
def compile():
    """Compile commands"""
    pass


@compile.command('vertical')
@click.argument('vertical_name')
@click.option('--verticals-dir', default='./verticals', help='Path to verticals directory')
@click.option('--services-dir', default='./services', help='Path to services directory')
@click.option('--output-dir', default='./generated', help='Path to output directory')
def compile_vertical(vertical_name: str, verticals_dir: str, services_dir: str, output_dir: str):
    """
    Compile a vertical from YAML schemas.
    
    Generates:
    - FastAPI routes
    - Pydantic models
    - Graph node definitions
    - Snapshot adapter
    - Test scaffolds
    
    Example:
        regengine compile vertical finance
    """
    click.echo(f"🔨 Compiling vertical: {vertical_name}")
    click.echo("")
    
    try:
        verticals_path = Path(verticals_dir)
        services_path = Path(services_dir)
        output_path = Path(output_dir)
        
        # Initialize compiler
        compiler = VerticalCompiler(
            verticals_dir=verticals_path,
            services_dir=services_path,
            output_dir=output_path
        )
        
        # Compile vertical
        result = compiler.compile_vertical(vertical_name)
        
        # Display results
        if result.compilation_status == "success":
            click.echo("✅ Compilation successful!")
            click.echo("")
            click.echo(f"Generated {len(result.generated_files)} files:")
            for file_path in result.generated_files:
                click.echo(f"  📄 {file_path}")
            
            if result.warnings:
                click.echo("")
                click.echo(f"⚠️  {len(result.warnings)} warnings:")
                for warning in result.warnings:
                    click.echo(f"  {warning}")
            
            sys.exit(0)
        else:
            click.echo("❌ Compilation failed!")
            click.echo("")
            for error in result.errors:
                click.echo(f"  ERROR: {error}")
            
            sys.exit(1)
            
    except FileNotFoundError as e:
        click.echo(f"❌ Error: {str(e)}")
        sys.exit(1)
    except Exception as e:
        click.echo(f"❌ Unexpected error: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


@cli.group()
def validate():
    """Validation commands"""
    pass


@validate.command('vertical')
@click.argument('vertical_name')
@click.option('--verticals-dir', default='./verticals', help='Path to verticals directory')
def validate_vertical(vertical_name: str, verticals_dir: str):
    """
    Validate a vertical's YAML schemas without compiling.
    
    Checks:
    - vertical.yaml structure
    - obligations.yaml completeness
    - Cross-validation (evidence_contract, scoring_weights)
    
    Example:
        regengine validate vertical finance
    """
    click.echo(f"🔍 Validating vertical: {vertical_name}")
    click.echo("")
    
    try:
        # Same relocation as the compile command above — schema_validator
        # lives at kernel/control/, not services/vertical_compiler/ (#1309).
        from kernel.control.schema_validator import (
            validate_vertical_schema,
            validate_obligations_schema
        )
        import yaml
        
        verticals_path = Path(verticals_dir)
        vertical_dir = verticals_path / vertical_name
        
        # Load vertical.yaml
        vertical_file = vertical_dir / "vertical.yaml"
        if not vertical_file.exists():
            click.echo(f"❌ vertical.yaml not found at {vertical_file}")
            sys.exit(1)
        
        with open(vertical_file) as f:
            vertical_data = yaml.safe_load(f)
        
        # Validate vertical schema
        vertical_errors = validate_vertical_schema(vertical_data)
        if vertical_errors:
            click.echo("❌ vertical.yaml validation failed:")
            for error in vertical_errors:
                click.echo(f"  {error}")
            sys.exit(1)
        
        click.echo("✅ vertical.yaml is valid")
        
        # Load obligations.yaml
        obligations_file = vertical_dir / "obligations.yaml"
        if not obligations_file.exists():
            click.echo(f"❌ obligations.yaml not found at {obligations_file}")
            sys.exit(1)
        
        with open(obligations_file) as f:
            obligations_data = yaml.safe_load(f)
        
        # Validate obligations schema
        obligations_errors = validate_obligations_schema(
            obligations_data.get("obligations", [])
        )
        if obligations_errors:
            click.echo("❌ obligations.yaml validation failed:")
            for error in obligations_errors:
                click.echo(f"  {error}")
            sys.exit(1)
        
        click.echo("✅ obligations.yaml is valid")
        click.echo("")
        click.echo(f"📊 Summary:")
        click.echo(f"  {len(obligations_data.get('obligations', []))} obligations defined")
        click.echo(f"  {len(vertical_data.get('regulators', []))} regulators")
        click.echo(f"  {len(vertical_data.get('decision_types', []))} decision types")
        
        sys.exit(0)
        
    except Exception as e:
        click.echo(f"❌ Validation error: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


@cli.command('list-verticals')
@click.option('--verticals-dir', default='./verticals', help='Path to verticals directory')
def list_verticals(verticals_dir: str):
    """List all available verticals."""
    click.echo("📋 Available verticals:")
    click.echo("")
    
    verticals_path = Path(verticals_dir)
    
    if not verticals_path.exists():
        click.echo(f"❌ Verticals directory not found: {verticals_path}")
        sys.exit(1)
    
    verticals = []
    for item in verticals_path.iterdir():
        if item.is_dir() and (item / "vertical.yaml").exists():
            verticals.append(item.name)
    
    if not verticals:
        click.echo("  No verticals found")
    else:
        for vertical in sorted(verticals):
            click.echo(f"  • {vertical}")
    
    click.echo("")
    click.echo(f"Total: {len(verticals)} vertical(s)")


if __name__ == '__main__':
    cli()

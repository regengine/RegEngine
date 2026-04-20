#!/usr/bin/env python3
"""
RegEngine CLI
=============
Command-line interface for RegEngine operations.

Commands:
- list-verticals: List all available verticals

NOTE: The ``compile vertical`` and ``validate vertical`` commands relied on
``kernel/control/`` (the compiler/codegen stack), which was retired in #1366.
That stack was never wired into any production service and carried known
crash/RCE defects (#1275, #1285, #1295).  Code generation is scheduled for
re-implementation inside the monolith consolidation sprint.
"""

import click
import sys
from pathlib import Path
import os

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))


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
    [RETIRED] Compile a vertical from YAML schemas.

    The kernel/control compiler stack was retired in #1366.
    Code generation will be re-implemented in the monolith consolidation sprint.
    """
    click.echo("ERROR: 'compile vertical' is retired (kernel/control removed in #1366).", err=True)
    click.echo("Code generation will be re-implemented in the monolith consolidation sprint.", err=True)
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
    [RETIRED] Validate a vertical's YAML schemas without compiling.

    The kernel/control compiler stack was retired in #1366.
    Schema validation will be re-implemented in the monolith consolidation sprint.
    """
    click.echo("ERROR: 'validate vertical' is retired (kernel/control removed in #1366).", err=True)
    click.echo("Schema validation will be re-implemented in the monolith consolidation sprint.", err=True)
    sys.exit(1)


@cli.command('list-verticals')
@click.option('--verticals-dir', default='./verticals', help='Path to verticals directory')
def list_verticals(verticals_dir: str):
    """List all available verticals."""
    click.echo("Available verticals:")
    click.echo("")

    verticals_path = Path(verticals_dir)

    if not verticals_path.exists():
        click.echo(f"ERROR: Verticals directory not found: {verticals_path}", err=True)
        sys.exit(1)

    verticals = []
    for item in verticals_path.iterdir():
        if item.is_dir() and (item / "vertical.yaml").exists():
            verticals.append(item.name)

    if not verticals:
        click.echo("  No verticals found")
    else:
        for vertical in sorted(verticals):
            click.echo(f"  - {vertical}")

    click.echo("")
    click.echo(f"Total: {len(verticals)} vertical(s)")


if __name__ == '__main__':
    cli()

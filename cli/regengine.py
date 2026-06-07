#!/usr/bin/env python3
"""
RegEngine CLI
=============
Command-line interface for RegEngine operations.

NOTE: The historical commands (``compile vertical``, ``list-verticals``,
``validate vertical``) were removed alongside ``kernel/control/`` (codegen
+ RCE surface) per the ``epic-g-retire-kernel`` epic. They had no
consumers and were the only known importers of ``kernel.control``. See
``project_kernel_audit_2026_04_17`` and PR #2205 for the broader kernel
retirement plan; this file is intentionally left as a stub so the
entry point keeps working if anything still invokes ``python -m
cli.regengine``.
"""

import click


@click.group()
def cli():
    """RegEngine - Regulatory Compliance Engine CLI

    No commands are currently registered. The previous vertical-compiler
    commands were retired with ``kernel/control/``.
    """
    pass


if __name__ == "__main__":
    cli()

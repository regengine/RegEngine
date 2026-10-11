"""RegEngine command line package.

Marking this directory as a package keeps cli/regengine.py as the module
cli.regengine. Without that, type checkers treat the file as a second
top-level module named regengine and stop checking the SDK.
"""

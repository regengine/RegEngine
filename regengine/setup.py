"""
RegEngine Python SDK
Official client library for RegEngine FSMA 204 Compliance Platform.
"""

import re
from pathlib import Path

from setuptools import setup

with open("README.md", "r", encoding="utf-8") as f:
    long_description = f.read()

# Single source of truth for the version: regengine/__init__.py.
_version_match = re.search(
    r'^__version__ = "([^"]+)"',
    Path(__file__).with_name("__init__.py").read_text(encoding="utf-8"),
    re.MULTILINE,
)
if not _version_match:
    raise RuntimeError("__version__ not found in __init__.py")
_VERSION = _version_match.group(1)

setup(
    name="regengine",
    version=_VERSION,
    author="RegEngine",
    author_email="sdk@regengine.co",
    description="Official Python SDK for RegEngine FSMA 204 Compliance Platform",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/regengine/python-sdk",
    project_urls={
        "Documentation": "https://docs.regengine.co/sdks/python",
        "Bug Tracker": "https://github.com/regengine/python-sdk/issues",
        "Changelog": "https://github.com/regengine/python-sdk/blob/main/CHANGELOG.md",
    },
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "License :: Other/Proprietary License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        # #2954: 3.8 removed. verify_records.py — the module behind the sole
        # console script — is not exercised on 3.8 by any CI job, and the
        # declared floor must not advertise a version nothing verifies.
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "Topic :: Scientific/Engineering :: Information Analysis",
    ],
    # setup.py lives INSIDE the package directory, so find_packages() used
    # to discover the SUBdirectories (swarm/, tests/) as top-level packages
    # and never installed the client itself — `import regengine` failed in a
    # clean environment (the sdk-ci import check passed only because it ran
    # from the repo root, where the source tree shadows site-packages). Map
    # the package explicitly instead, and keep the legacy swarm framework and
    # in-repo tests out of the customer artifact.
    packages=["regengine"],
    package_dir={"regengine": "."},
    # #2954: the floor is what is actually exercised, not an aspiration.
    python_requires=">=3.9",
    install_requires=[
        "httpx>=0.27,<1.0",
        "requests>=2.28.0",
    ],
    extras_require={
        # #2957: regengine/labels.py is swept into the distribution by
        # package_dir={"regengine": "."}. Its third-party imports (qrcode,
        # Pillow, fpdf2) are declared here and imported lazily inside the
        # label functions, so importing the module never raises
        # ModuleNotFoundError for an undeclared package.
        "labels": [
            "qrcode>=7.4",
            "Pillow>=10.0.0",
            "fpdf2>=2.8.0",
        ],
        "dev": [
            "pytest>=7.0",
            "pytest-cov",
            "responses",
            "mypy",
            "ruff",
        ],
    },
    entry_points={
        "console_scripts": [
            "regengine-verify=regengine.verify_records:main",
        ],
    },
    keywords="regengine fsma fda traceability compliance food-safety supply-chain",
)

"""
RegEngine Python SDK
Official client library for RegEngine FSMA 204 Compliance Platform.
"""

from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as f:
    long_description = f.read()

setup(
    name="regengine",
    version="1.0.0",
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
        "Development Status :: 5 - Production/Stable",
        "Intended Audience :: Developers",
        "License :: Other/Proprietary License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "Topic :: Scientific/Engineering :: Information Analysis",
    ],
    packages=find_packages(),
    python_requires=">=3.8",
    install_requires=[
        "requests>=2.28.0",
    ],
    extras_require={
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
            "regengine-verify=regengine.verify_chain:main",
        ],
    },
    keywords="regengine fsma fda traceability compliance food-safety supply-chain",
)

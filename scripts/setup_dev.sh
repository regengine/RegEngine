#!/usr/bin/env bash

# RegEngine Local Development Setup Script
# This script automates the creation of a virtual environment and dependency installation.

set -e

# Configuration
VENV_NAME="venv"
PYTHON_BIN="python3"
PROJECT_ROOT=$(pwd)

echo "🚀 Starting RegEngine Local Setup..."

# 1. Check for Python
if ! command -v $PYTHON_BIN &> /dev/null; then
    echo "❌ Error: $PYTHON_BIN not found. Please install Python 3.11+ (e.g., 'brew install python@3.11')"
    exit 1
fi

PYTHON_VERSION=$($PYTHON_BIN --version)
echo "✅ Found $PYTHON_VERSION"

# 2. Setup Virtual Environment
if [ ! -d "$VENV_NAME" ]; then
    echo "📦 Creating virtual environment in ./$VENV_NAME..."
    $PYTHON_BIN -m venv $VENV_NAME
else
    echo "ℹ️  Virtual environment already exists."
fi

# 3. Activate and Install
echo "🔌 Activating virtual environment..."
# shellcheck source=/dev/null
source "$VENV_NAME/bin/activate"

echo "⬆️  Upgrading pip..."
pip install --quiet --upgrade pip

echo "📥 Installing dependencies from requirements.lock..."
# Root requirements.lock is the pinned, hash-verified output of pip-compile
# (source: requirements.in). Reproducible builds — see #1139.
pip install --quiet --require-hashes -r requirements.lock

# 4. Environment File Setup
if [ ! -f ".env" ]; then
    if [ -f ".env.example" ]; then
        echo "📝 Creating .env from .env.example..."
        cp .env.example .env
        echo "⚠️  Action Required: Edit .env and set your secrets!"
    else
        echo "⚠️  Warning: .env.example not found. Skipping .env creation."
    fi
else
    echo "ℹ️  .env file already exists."
fi

echo ""
echo "===================================================="
echo "🎉 Setup Complete!"
echo "===================================================="
echo ""
echo "To start development, follow these steps:"
echo ""
echo "1. Activate the environment in your terminal:"
echo "   source $VENV_NAME/bin/activate"
echo ""
echo "2. Configure your IDE (Cursor / VS Code):"
echo "   - Press Cmd + Shift + P"
echo "   - Type 'Python: Select Interpreter'"
echo "   - Choose the one at $PROJECT_ROOT/$VENV_NAME/bin/python"
echo ""
echo "3. Important: If you run scripts directly, ensure PYTHONPATH is set:"
echo "   export PYTHONPATH=\$PYTHONPATH:$PROJECT_ROOT"
echo ""
echo "4. Start local Postgres (only infra dep still used locally):"
echo "   docker compose -f docker-compose.dev.yml up -d"
echo ""
echo "5. Start the consolidated backend monolith:"
echo "   uvicorn server.main:app --reload --port 8000"
echo "   (Prod runs this same server on Railway as one process — see"
echo "    docs/architecture/CONSOLIDATION.md.)"
echo ""

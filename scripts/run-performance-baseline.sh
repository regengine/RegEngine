#!/bin/bash
# Performance Baseline Test Script
# Runs k6 load tests and captures baseline metrics

set -e

echo "🚀 RegEngine Performance Baseline Test"
echo "========================================"
echo ""

# Check if k6 is installed
if ! command -v k6 &> /dev/null; then
    echo "❌ k6 is not installed"
    echo "Installing k6..."
    
    if [[ "$OSTYPE" == "darwin"* ]]; then
        brew install k6
    elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
        wget https://github.com/grafana/k6/releases/download/v0.47.0/k6-v0.47.0-linux-amd64.tar.gz
        tar -xzf k6-v0.47.0-linux-amd64.tar.gz
        sudo cp k6-v0.47.0-linux-amd64/k6 /usr/local/bin/
        rm -rf k6-v0.47.0-linux-amd64*
    fi
fi

# Check if services are running
echo "Checking service health..."
if ! curl -f http://localhost:8000/health &> /dev/null; then
    echo "⚠️  Admin service not running at port 8000"
    echo "Please start services with: docker-compose up -d"
    exit 1
fi

echo "✅ Services are running"
echo ""

# Create output directory
mkdir -p test-results/load

# Run load test
echo "Running k6 load test..."
echo "Target: 100 concurrent users"
echo "Duration: ~7 minutes"
echo ""

k6 run \
  --out json=test-results/load/results-$(date +%Y%m%d-%H%M%S).json \
  --summary-export=test-results/load/summary-$(date +%Y%m%d-%H%M%S).json \
  tests/load/user-journey.js

echo ""
echo "✅ Load test complete!"
echo "Results saved to test-results/load/"
echo ""
echo "Key metrics to review:"
echo "  - http_req_duration p(95)"
echo "  - http_req_failed rate"
echo "  - errors rate"

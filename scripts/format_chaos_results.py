#!/usr/bin/env python3
"""
Format chaos engineering test results for GitHub Step Summary.

Stub implementation — outputs a markdown summary placeholder.
TODO: Parse chaos_results.json and produce detailed pass/fail table.
"""

import json
import os
import sys


def main():
    results_file = os.path.join(os.getcwd(), "chaos_results.json")

    if os.path.exists(results_file):
        with open(results_file) as f:
            data = json.load(f)
        total = len(data) if isinstance(data, list) else 0
        print(f"| Metric | Value |")
        print(f"|--------|-------|")
        print(f"| Tests Run | {total} |")
        print(f"| Status | See artifacts |")
    else:
        print("| Metric | Value |")
        print("|--------|-------|")
        print("| Tests Run | 0 (no results file) |")
        print("| Status | STUB |")

    return 0


if __name__ == "__main__":
    sys.exit(main())

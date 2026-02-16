#!/usr/bin/env python3
"""
🧬 RegEngine Swarm Sweep
The 10000x Productivity tool for solo founders.
Identifies horizontal technical debt patterns across the 23+ microservices
and dispatches the swarm to fix them all in one operation.
"""

import os
import sys
import json
import structlog
from typing import List, Dict, Any
from regengine.swarm.coordinator import AgentSwarm
from regengine.swarm.github_integration import GitHubClient

log = structlog.get_logger("swarm-sweep")

class SwarmSweeper:
    def __init__(self):
        self.github = GitHubClient()
        self.swarm = AgentSwarm()
        
    def identify_patterns(self, issues: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
        """Group issues by common architectural patterns."""
        patterns = {
            "middleware": [],
            "health_checks": [],
            "logging": [],
            "styling": [],
            "other": []
        }
        
        for issue in issues:
            title = issue['title'].lower()
            if "middleware" in title or "request id" in title:
                patterns["middleware"].append(issue)
            elif "ready endpoint" in title or "health" in title:
                patterns["health_checks"].append(issue)
            elif "logging" in title or "startup" in title:
                patterns["logging"].append(issue)
            elif "tailwind" in title or "inline style" in title:
                patterns["styling"].append(issue)
            else:
                patterns["other"].append(issue)
        
        return patterns

    async def sweep(self, limit: int = 5):
        """Execute the sweep across identified patterns."""
        log.info("sweep_started", limit=limit)
        
        # 1. Fetch open issues with technical debt
        issues = self.github.list_issues(state="open", limit=50)
        patterns = self.identify_patterns(issues)
        
        log.info("patterns_identified", 
                 middleware=len(patterns["middleware"]),
                 health_checks=len(patterns["health_checks"]),
                 logging=len(patterns["logging"]),
                 styling=len(patterns["styling"]))

        all_candidate_tasks = []
        for pattern_issues in patterns.values():
            for issue in pattern_issues:
                task = f"Solve GitHub Issue #{issue['number']}: {issue['title']}\n\n{issue['body']}"
                all_candidate_tasks.append(task)
        
        tasks_to_run = all_candidate_tasks[:limit]
        if not tasks_to_run:
            log.info("no_tasks_to_run")
            return

        log.info("launching_fleet_sweep", task_count=len(tasks_to_run))
        
        # Ensure environment variables are set for auto-fix
        os.environ["REGENGINE_CI_AUTO_FIX"] = "true"
        
        results = await self.swarm.sweep(tasks_to_run, concurrency=5)
        
        for i, result in enumerate(results):
            log.info("task_completed", index=i, status=result.status, task=result.task[:50])

if __name__ == "__main__":
    import asyncio
    # Ensure environment variables are set
    if not os.getenv("GITHUB_TOKEN"):
        print("❌ GITHUB_TOKEN not found.")
        sys.exit(1)
        
    sweeper = SwarmSweeper()
    # Sweep the first 10 horizontal tasks to clear the backlog
    asyncio.run(sweeper.sweep(limit=10))

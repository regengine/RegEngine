"""GitHub integration for the autonomous agent swarm.

Provides:
  - GitHubClient: wrapper around PyGitHub for repo interaction
  - Issue labeling via LLM classification
  - PR creation from agent work
  - Issue commenting for agent status updates
"""

import json
import os
from typing import Any, Dict, List, Optional

import structlog

logger = structlog.get_logger("swarm.github")


class GitHubClient:
    """GitHub API wrapper for autonomous agent operations.

    Requires GITHUB_TOKEN environment variable.

    Usage:
        client = GitHubClient("owner/repo")
        issues = client.list_issues(state="open", limit=10)
        client.label_issue(42, ["agent:fsma", "bug"])
        client.comment_on_issue(42, "Bot-Security: Review complete ✅")
    """

    def __init__(self, repo_name: Optional[str] = None, token: Optional[str] = None):
        self.repo_name = repo_name or os.getenv("GITHUB_REPO", "")
        self.token = token or os.getenv("GITHUB_TOKEN", "")
        self._github = None
        self._repo = None

    @property
    def github(self):
        """Lazy-init PyGitHub client."""
        if self._github is None:
            try:
                from github import Github
                self._github = Github(self.token)
            except ImportError:
                raise ImportError(
                    "PyGithub is required for GitHub integration. "
                    "Install it with: pip install PyGithub>=2.1.0"
                )
        return self._github

    @property
    def repo(self):
        """Lazy-init repo reference."""
        if self._repo is None:
            if not self.repo_name:
                raise ValueError(
                    "Repository name required. Set GITHUB_REPO env var "
                    "or pass repo_name to GitHubClient()"
                )
            self._repo = self.github.get_repo(self.repo_name)
        return self._repo

    def list_issues(
        self,
        state: str = "open",
        labels: Optional[List[str]] = None,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """List issues with optional label filtering."""
        kwargs = {"state": state}
        if labels:
            kwargs["labels"] = [self.repo.get_label(l) for l in labels]

        issues = []
        for issue in self.repo.get_issues(**kwargs)[:limit]:
            issues.append({
                "number": issue.number,
                "title": issue.title,
                "body": issue.body or "",
                "labels": [l.name for l in issue.labels],
                "state": issue.state,
                "created_at": issue.created_at.isoformat(),
                "url": issue.html_url,
            })

        logger.info("issues_listed", count=len(issues), state=state)
        return issues

    def get_issue(self, issue_number: int) -> Dict[str, Any]:
        """Get a specific issue by number."""
        issue = self.repo.get_issue(issue_number)
        return {
            "number": issue.number,
            "title": issue.title,
            "body": issue.body or "",
            "labels": [l.name for l in issue.labels],
            "state": issue.state,
            "created_at": issue.created_at.isoformat(),
            "comments": [
                {"author": c.user.login, "body": c.body, "created_at": c.created_at.isoformat()}
                for c in issue.get_comments()
            ],
            "url": issue.html_url,
        }

    def label_issue(self, issue_number: int, labels: List[str]) -> None:
        """Add labels to an issue."""
        issue = self.repo.get_issue(issue_number)
        for label_name in labels:
            try:
                self.repo.get_label(label_name)
            except Exception:
                # Create label if it doesn't exist
                self.repo.create_label(name=label_name, color="0e8a16")
                logger.info("label_created", label=label_name)

            issue.add_to_labels(label_name)
        logger.info("issue_labeled", issue=issue_number, labels=labels)

    def comment_on_issue(self, issue_number: int, body: str) -> None:
        """Post a comment on an issue."""
        issue = self.repo.get_issue(issue_number)
        issue.create_comment(body)
        logger.info("issue_commented", issue=issue_number, body_len=len(body))

    def create_branch(self, branch_name: str, base: str = "main") -> str:
        """Create a new branch from base."""
        base_ref = self.repo.get_git_ref(f"heads/{base}")
        sha = base_ref.object.sha
        self.repo.create_git_ref(f"refs/heads/{branch_name}", sha)
        logger.info("branch_created", branch=branch_name, base=base)
        return sha

    def create_pr(
        self,
        title: str,
        body: str,
        head: str,
        base: str = "main",
        labels: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Create a Pull Request."""
        pr = self.repo.create_pull(
            title=title,
            body=body,
            head=head,
            base=base,
        )
        if labels:
            pr.add_to_labels(*labels)

        logger.info("pr_created", number=pr.number, title=title)
        return {
            "number": pr.number,
            "title": pr.title,
            "url": pr.html_url,
            "state": pr.state,
        }

    def merge_pr(self, pr_number: int, commit_message: str = "") -> bool:
        """Merge a pull request."""
        pr = self.repo.get_pull(pr_number)
        if pr.mergeable:
            status = pr.merge(commit_message=commit_message or f"🤖 Swarm Auto-Merge PR #{pr_number}")
            logger.info("pr_merged", number=pr_number, success=status.merged)
            return status.merged
        else:
            logger.warning("pr_not_mergeable", number=pr_number)
            return False

    def get_pr_checks_status(self, pr_number: int) -> str:
        """Get the combined status of CI checks for a PR."""
        pr = self.repo.get_pull(pr_number)
        ref = pr.head.sha
        status = self.repo.get_combined_status(ref)
        return status.state # 'success', 'failure', 'pending', etc.


class IssueLabelClassifier:
    """Uses LLM to classify and auto-label GitHub issues.

    This is the starter use case for the autonomous swarm —
    agents that automatically categorize issues based on content.
    """

    # Maps LLM-suggested categories to GitHub labels
    LABEL_MAP = {
        "food_safety": "agent:fsma",
        "fsma": "agent:fsma",
        "payroll": "agent:pcos",
        "security": "agent:security",
        "infrastructure": "agent:infra",
        "ui": "agent:ui",
        "energy": "agent:energy",
        "healthcare": "agent:healthcare",
        "aerospace": "agent:aerospace",
        "testing": "agent:qa",
        "bug": "bug",
        "feature": "enhancement",
        "documentation": "docs",
        "performance": "performance",
    }

    SYSTEM_PROMPT = (
        "You are a GitHub issue classifier for RegEngine, a multi-tenant regulatory compliance platform. "
        "Analyze the issue title and body, then classify it into one or more categories.\n\n"
        "Available categories: food_safety, payroll, security, infrastructure, ui, energy, "
        "healthcare, aerospace, testing, bug, feature, documentation, performance\n\n"
        'Respond in JSON: {"categories": ["category1", "category2"], "confidence": 0.0-1.0, '
        '"reasoning": "..."}'
    )

    def __init__(self, llm_client=None):
        from regengine.swarm.llm import LLMClientFactory
        self.llm = llm_client or LLMClientFactory.create()

    def classify(self, title: str, body: str) -> Dict[str, Any]:
        """Classify an issue and return suggested labels."""
        prompt = f"ISSUE TITLE: {title}\n\nISSUE BODY:\n{body[:3000]}"
        response = self.llm.generate_json(prompt, self.SYSTEM_PROMPT)

        categories = response.get("categories", [])
        labels = []
        for cat in categories:
            cat_lower = cat.lower().strip()
            if cat_lower in self.LABEL_MAP:
                labels.append(self.LABEL_MAP[cat_lower])

        return {
            "categories": categories,
            "labels": labels,
            "confidence": response.get("confidence", 0.0),
            "reasoning": response.get("reasoning", ""),
        }

    def label_issues(
        self,
        github_client: GitHubClient,
        limit: int = 10,
        dry_run: bool = True,
        min_confidence: float = 0.7,
    ) -> List[Dict[str, Any]]:
        """Classify and label open issues.

        Args:
            github_client: GitHub client instance
            limit: Max issues to process
            dry_run: If True, don't actually apply labels
            min_confidence: Minimum confidence threshold to apply labels

        Returns:
            List of classification results
        """
        issues = github_client.list_issues(state="open", limit=limit)
        results = []

        for issue in issues:
            classification = self.classify(issue["title"], issue["body"])

            result = {
                "issue_number": issue["number"],
                "title": issue["title"],
                **classification,
                "applied": False,
            }

            if classification["labels"] and classification["confidence"] >= min_confidence:
                if not dry_run:
                    github_client.label_issue(issue["number"], classification["labels"])
                    result["applied"] = True
                    logger.info(
                        "issue_auto_labeled",
                        issue=issue["number"],
                        labels=classification["labels"],
                    )
                else:
                    logger.info(
                        "issue_would_label",
                        issue=issue["number"],
                        labels=classification["labels"],
                        dry_run=True,
                    )

            results.append(result)

        return results

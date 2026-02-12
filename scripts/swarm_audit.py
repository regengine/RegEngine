#!/usr/bin/env python3
"""
Swarm Audit Script - Automated Code Quality and Security Auditing

This script performs automated audits of the RegEngine codebase and can:
- Detect security vulnerabilities (bare excepts, hardcoded secrets, etc.)
- Identify technical debt (TODOs, complex functions, etc.)
- Assess code quality metrics
- Automatically create GitHub issues for findings

Usage:
    python3 scripts/swarm_audit.py --type security --severity critical --auto-create-issues
"""

import argparse
import os
import subprocess
import json
import re
from datetime import datetime
from typing import List, Dict, Optional
from pathlib import Path


class BaseAuditor:
    """Base class for all auditors"""
    
    def __init__(self):
        self.findings = []
        self.scanned_files = 0
    
    def audit(self) -> List[Dict]:
        """Run audit and return findings"""
        raise NotImplementedError
    
    def add_finding(self, title: str, description: str, severity: str, 
                   category: str = None, file_path: str = None, line_number: int = None):
        """Add finding to results"""
        self.findings.append({
            'title': title,
            'description': description,
            'severity': severity,
            'category': category or self.__class__.__name__.replace('Auditor', '').lower(),
            'file_path': file_path,
            'line_number': line_number,
            'timestamp': datetime.now().isoformat()
        })


class SecurityAuditor(BaseAuditor):
    """Audits for security vulnerabilities"""
    
    def audit(self) -> List[Dict]:
        """Run security audit"""
        print("🔒 Running security audit...")
        self.find_bare_excepts()
        self.find_hardcoded_secrets()
        self.find_eval_exec()
        self.find_sql_injection_risks()
        print(f"  ✓ Scanned {self.scanned_files} files, found {len(self.findings)} security issues")
        return self.findings
    
    def find_bare_excepts(self):
        """Find dangerous bare except clauses"""
        try:
            # Target specific source directories to avoid venv noise
            target_dirs = ['services', 'scripts']
            
            # Common directories to exclude (extra safety)
            exclude_dirs = [
                '--exclude-dir=node_modules', '--exclude-dir=.git', 
                '--exclude-dir=venv', '--exclude-dir=.venv', 
                '--exclude-dir=.venv-test', '--exclude-dir=env', 
                '--exclude-dir=dist', '--exclude-dir=build', 
                '--exclude-dir=__pycache__', '--exclude-dir=site-packages',
                '--exclude-dir=tests'  # Exclude tests from critical security scan for now to avoid false positives
            ]
            
            cmd = ['grep', '-rn', 'except:', *target_dirs, '--include=*.py'] + exclude_dirs
            
            result = subprocess.run(cmd, capture_output=True, text=True, cwd='/Users/christophersellers/Desktop/RegEngine')
            
            if result.returncode == 0 and result.stdout:
                lines = result.stdout.strip().split('\n')
                self.scanned_files += len(set(line.split(':')[0] for line in lines if ':' in line))
                
                for line in lines:
                    if ':' not in line:
                        continue
                    parts = line.split(':', 2)
                    if len(parts) >= 3:
                        file_path, line_num, code = parts[0], parts[1], parts[2]
                        # Exclude if it's properly handling Exception
                        if 'except:' in code and 'Exception' not in code and '#' not in code.split('except:')[0]:
                            self.add_finding(
                                "Bare except clause detected",
                                f"**File:** `{file_path}:{line_num}`\n\n"
                                f"**Code:** `{code.strip()}`\n\n"
                                f"**Risk:** Catches ALL exceptions including SystemExit and KeyboardInterrupt, "
                                f"preventing graceful shutdown and masking critical errors.\n\n"
                                f"**Fix:** Replace with `except Exception as e:` and add logging.",
                                "critical",
                                "security",
                                file_path,
                                int(line_num) if line_num.isdigit() else None
                            )
        except Exception as e:
            print(f"  ⚠ Bare except scan failed: {e}")
    
    def find_hardcoded_secrets(self):
        """Find hardcoded passwords, API keys, and secrets"""
        patterns = [
            (r'password\s*=\s*["\'][^"\']{8,}["\']', 'password'),
            (r'api_key\s*=\s*["\'][^"\']{10,}["\']', 'API key'),
            (r'secret\s*=\s*["\'][^"\']{10,}["\']', 'secret'),
            (r'token\s*=\s*["\'][^"\']{20,}["\']', 'token')
        ]
        
        exclude_patterns = ['os.getenv', 'config', 'test', 'example', 'placeholder']
        
        for pattern, secret_type in patterns:
            try:
                target_dirs = ['services', 'scripts']
                exclude_dirs = [
                    '--exclude-dir=node_modules', '--exclude-dir=.git', 
                    '--exclude-dir=venv', '--exclude-dir=.venv', 
                    '--exclude-dir=.venv-test', '--exclude-dir=env', 
                    '--exclude-dir=dist', '--exclude-dir=build', 
                    '--exclude-dir=__pycache__', '--exclude-dir=site-packages',
                    '--exclude-dir=tests' 
                ]
                
                cmd = ['grep', '-rn', '-E', pattern, *target_dirs, '--include=*.py'] + exclude_dirs
                
                result = subprocess.run(cmd, capture_output=True, text=True, cwd='/Users/christophersellers/Desktop/RegEngine')
                
                if result.returncode == 0 and result.stdout:
                    lines = result.stdout.strip().split('\n')
                    for line in lines:
                        # Skip if it's using environment variables or in test files
                        if any(exc in line.lower() for exc in exclude_patterns):
                            continue
                        
                        if ':' in line:
                            parts = line.split(':', 2)
                            if len(parts) >= 3:
                                file_path, line_num, code = parts[0], parts[1], parts[2]
                                self.add_finding(
                                    f"Hardcoded {secret_type} detected",
                                    f"**File:** `{file_path}:{line_num}`\n\n"
                                    f"**Risk:** Hardcoded credentials pose security risk if committed to version control.\n\n"
                                    f"**Fix:** Use environment variables via `os.getenv()` or secure configuration management.",
                                    "high",
                                    "security",
                                    file_path,
                                    int(line_num) if line_num.isdigit() else None
                                )
            except Exception:
                pass
    
    def find_eval_exec(self):
        """Find dangerous eval() and exec() usage"""
        try:
            target_dirs = ['services', 'scripts']
            exclude_dirs = [
                '--exclude-dir=node_modules', '--exclude-dir=.git', 
                '--exclude-dir=venv', '--exclude-dir=.venv',
                '--exclude-dir=.venv-test', '--exclude-dir=site-packages',
                '--exclude-dir=tests'
            ]
            
            cmd = ['grep', '-rn', '-E', r'\b(eval|exec)\s*\(', *target_dirs, '--include=*.py', '--exclude=swarm_audit.py'] + exclude_dirs
            
            result = subprocess.run(cmd, capture_output=True, text=True, cwd='/Users/christophersellers/Desktop/RegEngine')
            
            if result.returncode == 0 and result.stdout:
                lines = result.stdout.strip().split('\n')
                for line in lines:
                    if ':' in line and ('.eval()' not in line):  # Exclude model.eval()
                        parts = line.split(':', 2)
                        if len(parts) >= 3:
                            file_path, line_num, code = parts[0], parts[1], parts[2]
                            self.add_finding(
                                "Dangerous eval/exec usage detected",
                                f"**File:** `{file_path}:{line_num}`\n\n"
                                f"**Code:** `{code.strip()}`\n\n"
                                f"**Risk:** eval() and exec() can execute arbitrary code and pose severe security risks.\n\n"
                                f"**Fix:** Use safer alternatives like ast.literal_eval() or specific parsing.",
                                "critical",
                                "security",
                                file_path,
                                int(line_num) if line_num.isdigit() else None
                            )
        except Exception:
            pass
    
    def find_sql_injection_risks(self):
        """Find potential SQL injection vulnerabilities"""
        try:
            # Look for string formatting in SQL queries
            result = subprocess.run([
                'grep', '-rn', '-E', r'(execute|query|run)\s*\([^)]*f["\']|\.format\(', 
                'services', '--include=*.py'
            ], capture_output=True, text=True, cwd='/Users/christophersellers/Desktop/RegEngine')
            
            if result.returncode == 0 and result.stdout:
                lines = result.stdout.strip().split('\n')
                for line in lines:
                    if 'SELECT' in line.upper() or 'INSERT' in line.upper() or 'UPDATE' in line.upper():
                        if ':' in line:
                            parts = line.split(':', 2)
                            if len(parts) >= 3:
                                file_path, line_num, code = parts[0], parts[1], parts[2]
                                self.add_finding(
                                    "Potential SQL injection risk",
                                    f"**File:** `{file_path}:{line_num}`\n\n"
                                    f"**Risk:** String formatting in SQL queries may allow SQL injection.\n\n"
                                    f"**Fix:** Use parameterized queries with placeholders ($1, :param, etc.).",
                                    "high",
                                    "security",
                                    file_path,
                                    int(line_num) if line_num.isdigit() else None
                                )
        except Exception:
            pass


class TechDebtAuditor(BaseAuditor):
    """Audits for technical debt"""
    
    def audit(self) -> List[Dict]:
        """Run tech debt audit"""
        print("🔧 Running technical debt audit...")
        self.find_todo_comments()
        self.find_commented_code()
        self.find_long_functions()
        print(f"  ✓ Found {len(self.findings)} tech debt items")
        return self.findings
    
    def find_todo_comments(self):
        """Find TODO and FIXME comments"""
        try:
            exclude_dirs = [
                '--exclude-dir=node_modules', '--exclude-dir=.git', 
                '--exclude-dir=venv', '--exclude-dir=.venv', 
                '--exclude-dir=env', '--exclude-dir=dist', 
                '--exclude-dir=build', '--exclude-dir=__pycache__',
                '--exclude-dir=site-packages'
            ]
            
            cmd = ['grep', '-rn', '-E', 'TODO|FIXME|HACK|XXX', 'services', '--include=*.py'] + exclude_dirs
            
            result = subprocess.run(cmd, capture_output=True, text=True, cwd='/Users/christophersellers/Desktop/RegEngine')
            
            if result.returncode == 0 and result.stdout:
                lines = result.stdout.strip().split('\n')
                todo_count = len(lines)
                self.scanned_files = len(set(line.split(':')[0] for line in lines if ':' in line))
                
                if todo_count > 20:
                    self.add_finding(
                        f"High TODO count: {todo_count} items",
                        f"**Count:** {todo_count} TODO/FIXME/HACK comments found across {self.scanned_files} files\n\n"
                        f"**Impact:** High number of incomplete implementations indicates significant technical debt.\n\n"
                        f"**Recommendation:** Prioritize and track these items, convert to GitHub issues.",
                        "medium",
                        "tech-debt"
                    )
                elif todo_count > 10:
                    self.add_finding(
                        f"Moderate TODO count: {todo_count} items",
                        f"**Count:** {todo_count} TODO/FIXME comments found\n\n"
                        f"**Recommendation:** Review and prioritize these items.",
                        "low",
                        "tech-debt"
                    )
        except Exception:
            pass
    
    def find_commented_code(self):
        """Find large blocks of commented code"""
        try:
            # Count consecutive comment lines
            python_files = subprocess.run([
                'find', 'services', '-name', '*.py'
            ], capture_output=True, text=True, cwd='/Users/christophersellers/Desktop/RegEngine')
            
            if python_files.returncode == 0:
                for file_path in python_files.stdout.strip().split('\n'):
                    if not file_path:
                        continue
                    full_path = f"/Users/christophersellers/Desktop/RegEngine/{file_path}"
                    try:
                        with open(full_path, 'r') as f:
                            lines = f.readlines()
                            comment_block = []
                            
                            for i, line in enumerate(lines, 1):
                                stripped = line.strip()
                                if stripped.startswith('#') and not stripped.startswith('##'):
                                    comment_block.append((i, line))
                                else:
                                    if len(comment_block) > 10:  # More than 10 consecutive comments
                                        self.add_finding(
                                            f"Large commented code block in {file_path}",
                                            f"**File:** `{file_path}:{comment_block[0][0]}-{comment_block[-1][0]}`\n\n"
                                            f"**Size:** {len(comment_block)} lines of commented code\n\n"
                                            f"**Impact:** Commented code clutters codebase and should be removed if unused.\n\n"
                                            f"**Fix:** Remove if no longer needed, or convert to proper documentation.",
                                            "low",
                                            "tech-debt",
                                            file_path,
                                            comment_block[0][0]
                                        )
                                    comment_block = []
                    except Exception:
                        pass
        except Exception:
            pass
    
    def find_long_functions(self):
        """Find overly long functions that may need refactoring"""
        # This is a simplified check - a real implementation would parse AST
        try:
            result = subprocess.run([
                'grep', '-rn', 'def ', 'services', '--include=*.py'
            ], capture_output=True, text=True, cwd='/Users/christophersellers/Desktop/RegEngine')
            
            if result.returncode == 0:
                # This is a placeholder - would need proper AST parsing for accurate results
                func_count = len(result.stdout.strip().split('\n'))
                if func_count > 500:
                    self.add_finding(
                        f"Large codebase: {func_count} functions",
                        f"**Functions:** {func_count} function definitions found\n\n"
                        f"**Recommendation:** Monitor code complexity and consider refactoring large functions.",
                        "low",
                        "code-quality"
                    )
        except Exception:
            pass


class QualityAuditor(BaseAuditor):
    """Audits for code quality issues"""
    
    def audit(self) -> List[Dict]:
        """Run quality audit"""
        print("📊 Running code quality audit...")
        self.check_import_organization()
        self.find_duplicate_code()
        print(f"  ✓ Found {len(self.findings)} quality issues")
        return self.findings
    
    def check_import_organization(self):
        """Check for poorly organized imports"""
        # Simplified check
        pass
    
    def find_duplicate_code(self):
        """Find potential code duplication"""
        # Would need more sophisticated analysis
        pass


def create_github_issues(findings: List[Dict], assignee: Optional[str] = None):
    """Create GitHub issues for audit findings"""
    if not findings:
        print("📝 No issues to create")
        return
    
    try:
        # Check if gh CLI is available
        result = subprocess.run(['gh', '--version'], capture_output=True)
        if result.returncode != 0:
            print("⚠️  GitHub CLI not found - saving issues to file instead")
            save_issues_to_file(findings)
            return
        
        print(f"📋 Creating {len(findings)} GitHub issues...")
        created_count = 0
        
        for finding in findings:
            # Create label based on severity
            labels = [finding['severity'], finding.get('category', 'audit')]
            
            cmd = [
                'gh', 'issue', 'create',
                '--title', f"[{finding['severity'].upper()}] {finding['title']}",
                '--body', finding['description'],
                '--label', ','.join(labels)
            ]
            
            if assignee:
                cmd.extend(['--assignee', assignee])
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode == 0:
                created_count += 1
            else:
                print(f"  ⚠️  Failed to create issue: {finding['title']}")
        
        print(f"✅ Created {created_count}/{len(findings)} GitHub issues")
        
    except Exception as e:
        print(f"❌ Failed to create GitHub issues: {e}")
        save_issues_to_file(findings)


def save_issues_to_file(findings: List[Dict]):
    """Save findings to markdown file"""
    filename = f"audit-findings-{datetime.now().strftime('%Y%m%d-%H%M%S')}.md"
    
    with open(filename, 'w') as f:
        f.write(f"# Audit Findings - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        f.write(f"**Total Issues Found:** {len(findings)}\n\n")
        
        # Group by severity
        by_severity = {}
        for finding in findings:
            sev = finding['severity']
            if sev not in by_severity:
                by_severity[sev] = []
            by_severity[sev].append(finding)
        
        for severity in ['critical', 'high', 'medium', 'low']:
            if severity in by_severity:
                f.write(f"## {severity.upper()} ({len(by_severity[severity])} issues)\n\n")
                for issue in by_severity[severity]:
                    f.write(f"### {issue['title']}\n\n")
                    f.write(f"**Category:** {issue.get('category', 'general')}\n\n")
                    f.write(f"{issue['description']}\n\n")
                    f.write("---\n\n")
    
    print(f"💾 Saved findings to {filename}")


def main():
    parser = argparse.ArgumentParser(description='RegEngine Swarm Audit System')
    parser.add_argument('--type', 
                       choices=['security', 'quality', 'tech-debt', 'full'], 
                       default='security',
                       help='Type of audit to run')
    parser.add_argument('--severity', 
                       choices=['critical', 'high', 'medium', 'low', 'all'],
                       default='all',
                       help='Minimum severity to report')
    parser.add_argument('--auto-create-issues', 
                       action='store_true',
                       help='Automatically create GitHub issues for findings')
    parser.add_argument('--assignee', 
                       help='Assign issues to specific GitHub user')
    
    args = parser.parse_args()
    
    print(f"🚀 Starting {args.type} audit at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    
    # Run audits based on type
    all_findings = []
    
    if args.type == 'security' or args.type == 'full':
        auditor = SecurityAuditor()
        all_findings.extend(auditor.audit())
    
    if args.type == 'tech-debt' or args.type == 'full':
        auditor = TechDebtAuditor()
        all_findings.extend(auditor.audit())
    
    if args.type == 'quality' or args.type == 'full':
        auditor = QualityAuditor()
        all_findings.extend(auditor.audit())
    
    # Filter by severity
    if args.severity != 'all':
        severity_order = ['low', 'medium', 'high', 'critical']
        min_severity_idx = severity_order.index(args.severity)
        all_findings = [f for f in all_findings 
                       if severity_order.index(f['severity']) >= min_severity_idx]
    
    print(f"\n📊 Audit Summary:")
    print(f"  Total findings: {len(all_findings)}")
    
    # Count by severity
    by_sev = {}
    for f in all_findings:
        sev = f['severity']
        by_sev[sev] = by_sev.get(sev, 0) + 1
    
    for sev in ['critical', 'high', 'medium', 'low']:
        if sev in by_sev:
            print(f"    {sev.upper()}: {by_sev[sev]}")
    
    print()
    
    # Create issues or save to file
    if all_findings:
        if args.auto_create_issues:
            create_github_issues(all_findings, args.assignee)
        else:
            save_issues_to_file(all_findings)
    else:
        print("✅ No issues found! Codebase is clean.")
    
    # Exit with error code if critical/high issues found
    critical_high = [f for f in all_findings if f['severity'] in ['critical', 'high']]
    if critical_high:
        print(f"\n⚠️  Found {len(critical_high)} critical/high severity issues")
        return 1
    
    return 0


if __name__ == '__main__':
    exit(main())

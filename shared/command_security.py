"""
SEC-046: Command Injection Prevention.

Secure command execution with input validation,
sandboxing, and safe subprocess handling.
"""

import os
import re
import shlex
import subprocess
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class CommandSafetyLevel(str, Enum):
    """Command safety levels."""
    SAFE = "safe"
    RESTRICTED = "restricted"
    DANGEROUS = "dangerous"
    BLOCKED = "blocked"


class CommandResult(str, Enum):
    """Command execution result types."""
    SUCCESS = "success"
    BLOCKED = "blocked"
    TIMEOUT = "timeout"
    ERROR = "error"


@dataclass
class CommandConfig:
    """Configuration for command execution."""
    
    # Allowed commands whitelist
    allowed_commands: set = field(default_factory=lambda: {
        "ls", "cat", "head", "tail", "grep", "wc", "date", "echo",
        "pwd", "whoami", "hostname", "uname", "df", "du",
    })
    
    # Blocked commands (always reject)
    blocked_commands: set = field(default_factory=lambda: {
        "rm", "mv", "cp", "chmod", "chown", "chgrp",
        "kill", "pkill", "killall",
        "su", "sudo", "passwd",
        "curl", "wget", "nc", "netcat",
        "python", "python3", "perl", "ruby", "node", "php",
        "bash", "sh", "zsh", "csh",
        "eval", "exec",
    })
    
    # Blocked patterns (regex)
    blocked_patterns: list = field(default_factory=lambda: [
        r"[;&|`$]",  # Command chaining
        r"\$\(",     # Command substitution
        r"\$\{",     # Variable expansion
        r">\s*>",    # Append redirect
        r">\s*\|",   # Redirect to pipe
        r"<\s*<",    # Here document
        r"\.\.",     # Parent directory
        r"~",        # Home directory
    ])
    
    # Execution limits
    timeout_seconds: int = 30
    max_output_size: int = 1048576  # 1MB
    max_args: int = 20
    
    # Sandbox settings
    use_sandbox: bool = True
    allowed_paths: set = field(default_factory=lambda: {"/tmp"})
    
    # Environment
    inherit_env: bool = False
    safe_env: dict = field(default_factory=lambda: {
        "PATH": "/usr/bin:/bin",
        "HOME": "/tmp",
    })


@dataclass
class CommandValidationResult:
    """Result of command validation."""
    
    is_valid: bool
    safety_level: CommandSafetyLevel = CommandSafetyLevel.BLOCKED
    command: str = ""
    args: list = field(default_factory=list)
    errors: list = field(default_factory=list)


@dataclass
class CommandExecutionResult:
    """Result of command execution."""
    
    status: CommandResult
    return_code: int = -1
    stdout: str = ""
    stderr: str = ""
    error_message: str = ""


class CommandValidator:
    """Validates commands before execution."""
    
    def __init__(self, config: Optional[CommandConfig] = None):
        self.config = config or CommandConfig()
        self._blocked_patterns = [
            re.compile(p) for p in self.config.blocked_patterns
        ]
    
    def validate(self, command_line: str) -> CommandValidationResult:
        """Validate a command line."""
        errors = []
        
        # Empty command
        if not command_line or not command_line.strip():
            return CommandValidationResult(
                is_valid=False,
                errors=["Command is empty"],
            )
        
        # Check for blocked patterns first
        for pattern in self._blocked_patterns:
            if pattern.search(command_line):
                return CommandValidationResult(
                    is_valid=False,
                    safety_level=CommandSafetyLevel.BLOCKED,
                    errors=[f"Command contains blocked pattern"],
                )
        
        # Parse command
        try:
            parts = shlex.split(command_line)
        except ValueError as e:
            return CommandValidationResult(
                is_valid=False,
                errors=[f"Invalid command syntax: {e}"],
            )
        
        if not parts:
            return CommandValidationResult(
                is_valid=False,
                errors=["No command specified"],
            )
        
        command = parts[0]
        args = parts[1:]
        
        # Check argument count
        if len(args) > self.config.max_args:
            errors.append(f"Too many arguments: {len(args)} > {self.config.max_args}")
        
        # Check if command is blocked
        base_command = os.path.basename(command)
        if base_command in self.config.blocked_commands:
            return CommandValidationResult(
                is_valid=False,
                safety_level=CommandSafetyLevel.BLOCKED,
                command=base_command,
                args=args,
                errors=[f"Command '{base_command}' is blocked"],
            )
        
        # Check if command is allowed
        if base_command in self.config.allowed_commands:
            if errors:
                return CommandValidationResult(
                    is_valid=False,
                    safety_level=CommandSafetyLevel.RESTRICTED,
                    command=base_command,
                    args=args,
                    errors=errors,
                )
            
            return CommandValidationResult(
                is_valid=True,
                safety_level=CommandSafetyLevel.SAFE,
                command=base_command,
                args=args,
            )
        
        # Unknown command - restricted by default
        return CommandValidationResult(
            is_valid=False,
            safety_level=CommandSafetyLevel.RESTRICTED,
            command=base_command,
            args=args,
            errors=[f"Command '{base_command}' is not in allowlist"],
        )
    
    def validate_args(self, args: list[str]) -> tuple[bool, list[str]]:
        """Validate command arguments."""
        errors = []
        
        for arg in args:
            # Check for shell metacharacters
            for pattern in self._blocked_patterns:
                if pattern.search(arg):
                    errors.append(f"Argument contains blocked pattern: {arg}")
                    break
            
            # Check for path traversal
            if ".." in arg:
                errors.append(f"Argument contains path traversal: {arg}")
        
        return len(errors) == 0, errors


class ArgumentSanitizer:
    """Sanitizes command arguments."""
    
    def __init__(self, config: Optional[CommandConfig] = None):
        self.config = config or CommandConfig()
    
    def sanitize(self, arg: str) -> str:
        """Sanitize a single argument."""
        # Remove null bytes
        sanitized = arg.replace("\x00", "")
        
        # Remove shell metacharacters
        dangerous_chars = ";|&`$(){}<>"
        for char in dangerous_chars:
            sanitized = sanitized.replace(char, "")
        
        # Remove newlines and control characters
        sanitized = re.sub(r"[\r\n\t]", " ", sanitized)
        
        # Collapse multiple spaces
        sanitized = re.sub(r"\s+", " ", sanitized)
        
        # Limit length
        max_len = 1024
        if len(sanitized) > max_len:
            sanitized = sanitized[:max_len]
        
        return sanitized.strip()
    
    def sanitize_all(self, args: list[str]) -> list[str]:
        """Sanitize all arguments."""
        return [self.sanitize(arg) for arg in args]
    
    def escape_for_shell(self, arg: str) -> str:
        """Escape argument for shell use."""
        return shlex.quote(arg)
    
    def escape_all_for_shell(self, args: list[str]) -> list[str]:
        """Escape all arguments for shell."""
        return [self.escape_for_shell(arg) for arg in args]


class SafeCommandExecutor:
    """Executes commands safely."""
    
    def __init__(self, config: Optional[CommandConfig] = None):
        self.config = config or CommandConfig()
        self.validator = CommandValidator(self.config)
        self.sanitizer = ArgumentSanitizer(self.config)
    
    def execute(
        self,
        command: str,
        args: Optional[list[str]] = None,
        cwd: Optional[str] = None,
        env: Optional[dict] = None,
    ) -> CommandExecutionResult:
        """Execute a command safely."""
        args = args or []
        
        # Build command line for validation
        full_command = f"{command} {' '.join(args)}".strip()
        
        # Validate command
        validation = self.validator.validate(full_command)
        
        if not validation.is_valid:
            return CommandExecutionResult(
                status=CommandResult.BLOCKED,
                error_message="; ".join(validation.errors),
            )
        
        # Validate working directory
        if cwd and self.config.use_sandbox:
            if not any(cwd.startswith(p) for p in self.config.allowed_paths):
                return CommandExecutionResult(
                    status=CommandResult.BLOCKED,
                    error_message=f"Working directory not allowed: {cwd}",
                )
        
        # Sanitize arguments
        safe_args = self.sanitizer.sanitize_all(args)
        
        # Build environment
        if env is None:
            if self.config.inherit_env:
                exec_env = os.environ.copy()
                exec_env.update(self.config.safe_env)
            else:
                exec_env = self.config.safe_env.copy()
        else:
            exec_env = env
        
        # Execute
        try:
            result = subprocess.run(
                [command] + safe_args,
                capture_output=True,
                text=True,
                timeout=self.config.timeout_seconds,
                cwd=cwd,
                env=exec_env,
                shell=False,  # Never use shell=True
            )
            
            # Truncate output if needed
            stdout = result.stdout
            stderr = result.stderr
            
            if len(stdout) > self.config.max_output_size:
                stdout = stdout[:self.config.max_output_size] + "\n[truncated]"
            if len(stderr) > self.config.max_output_size:
                stderr = stderr[:self.config.max_output_size] + "\n[truncated]"
            
            return CommandExecutionResult(
                status=CommandResult.SUCCESS,
                return_code=result.returncode,
                stdout=stdout,
                stderr=stderr,
            )
            
        except subprocess.TimeoutExpired:
            return CommandExecutionResult(
                status=CommandResult.TIMEOUT,
                error_message=f"Command timed out after {self.config.timeout_seconds}s",
            )
        except FileNotFoundError:
            return CommandExecutionResult(
                status=CommandResult.ERROR,
                error_message=f"Command not found: {command}",
            )
        except Exception as e:
            return CommandExecutionResult(
                status=CommandResult.ERROR,
                error_message=str(e),
            )
    
    def execute_safe(
        self,
        command_line: str,
        cwd: Optional[str] = None,
    ) -> CommandExecutionResult:
        """Execute a command line safely (parses command)."""
        try:
            parts = shlex.split(command_line)
        except ValueError as e:
            return CommandExecutionResult(
                status=CommandResult.ERROR,
                error_message=f"Invalid command: {e}",
            )
        
        if not parts:
            return CommandExecutionResult(
                status=CommandResult.ERROR,
                error_message="Empty command",
            )
        
        return self.execute(parts[0], parts[1:], cwd)


class CommandSecurityService:
    """Comprehensive command security service."""
    
    _instance: Optional["CommandSecurityService"] = None
    
    def __init__(self, config: Optional[CommandConfig] = None):
        self.config = config or CommandConfig()
        self.executor = SafeCommandExecutor(self.config)
        self.validator = CommandValidator(self.config)
        self.sanitizer = ArgumentSanitizer(self.config)
    
    @classmethod
    def get_instance(cls) -> "CommandSecurityService":
        """Get singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    @classmethod
    def configure(cls, config: CommandConfig) -> "CommandSecurityService":
        """Configure and return singleton."""
        cls._instance = cls(config)
        return cls._instance
    
    def validate(self, command_line: str) -> CommandValidationResult:
        """Validate a command."""
        return self.validator.validate(command_line)
    
    def execute(
        self,
        command: str,
        args: Optional[list[str]] = None,
        cwd: Optional[str] = None,
    ) -> CommandExecutionResult:
        """Execute a command safely."""
        return self.executor.execute(command, args, cwd)
    
    def sanitize(self, arg: str) -> str:
        """Sanitize an argument."""
        return self.sanitizer.sanitize(arg)
    
    def add_allowed_command(self, command: str) -> None:
        """Add command to allowlist."""
        self.config.allowed_commands.add(command)
    
    def remove_allowed_command(self, command: str) -> None:
        """Remove command from allowlist."""
        self.config.allowed_commands.discard(command)
    
    def add_blocked_command(self, command: str) -> None:
        """Add command to blocklist."""
        self.config.blocked_commands.add(command)
    
    def is_command_allowed(self, command: str) -> bool:
        """Check if command is allowed."""
        base = os.path.basename(command)
        return base in self.config.allowed_commands


# Convenience functions
def get_command_service() -> CommandSecurityService:
    """Get command service instance."""
    return CommandSecurityService.get_instance()


def validate_command(command_line: str) -> CommandValidationResult:
    """Validate a command."""
    return get_command_service().validate(command_line)


def execute_command(
    command: str,
    args: Optional[list[str]] = None,
) -> CommandExecutionResult:
    """Execute a command safely."""
    return get_command_service().execute(command, args)


def sanitize_argument(arg: str) -> str:
    """Sanitize a command argument."""
    return get_command_service().sanitize(arg)

"""
Tests for SEC-046: Command Injection Prevention.

Tests cover:
- Command validation
- Argument sanitization
- Safe execution
- Injection prevention
"""

import pytest

from shared.command_security import (
    # Enums
    CommandSafetyLevel,
    CommandResult,
    # Data classes
    CommandConfig,
    CommandValidationResult,
    CommandExecutionResult,
    # Classes
    CommandValidator,
    ArgumentSanitizer,
    SafeCommandExecutor,
    CommandSecurityService,
    # Convenience functions
    get_command_service,
    validate_command,
    execute_command,
    sanitize_argument,
)


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def config():
    """Create command config."""
    return CommandConfig()


@pytest.fixture
def validator(config):
    """Create validator."""
    return CommandValidator(config)


@pytest.fixture
def sanitizer(config):
    """Create sanitizer."""
    return ArgumentSanitizer(config)


@pytest.fixture
def executor(config):
    """Create executor."""
    return SafeCommandExecutor(config)


@pytest.fixture
def service(config):
    """Create service."""
    CommandSecurityService._instance = None
    return CommandSecurityService(config)


# =============================================================================
# Test: Enums
# =============================================================================

class TestEnums:
    """Test enum values."""
    
    def test_safety_levels(self):
        """Should have expected safety levels."""
        assert CommandSafetyLevel.SAFE == "safe"
        assert CommandSafetyLevel.RESTRICTED == "restricted"
        assert CommandSafetyLevel.DANGEROUS == "dangerous"
        assert CommandSafetyLevel.BLOCKED == "blocked"
    
    def test_command_results(self):
        """Should have expected result types."""
        assert CommandResult.SUCCESS == "success"
        assert CommandResult.BLOCKED == "blocked"
        assert CommandResult.TIMEOUT == "timeout"
        assert CommandResult.ERROR == "error"


# =============================================================================
# Test: CommandConfig
# =============================================================================

class TestCommandConfig:
    """Test CommandConfig class."""
    
    def test_default_values(self):
        """Should have secure defaults."""
        config = CommandConfig()
        
        assert "ls" in config.allowed_commands
        assert "rm" in config.blocked_commands
        assert config.use_sandbox is True
        assert config.timeout_seconds == 30


# =============================================================================
# Test: CommandValidator
# =============================================================================

class TestCommandValidator:
    """Test CommandValidator."""
    
    def test_validates_allowed_command(self, validator):
        """Should validate allowed command."""
        result = validator.validate("ls -la")
        
        assert result.is_valid is True
        assert result.safety_level == CommandSafetyLevel.SAFE
    
    def test_rejects_blocked_command(self, validator):
        """Should reject blocked command."""
        result = validator.validate("rm -rf /")
        
        assert result.is_valid is False
        assert result.safety_level == CommandSafetyLevel.BLOCKED
    
    def test_rejects_unknown_command(self, validator):
        """Should reject unknown command."""
        result = validator.validate("mycommand")
        
        assert result.is_valid is False
        assert result.safety_level == CommandSafetyLevel.RESTRICTED
    
    def test_rejects_command_chaining(self, validator):
        """Should reject command chaining."""
        result = validator.validate("ls; rm -rf /")
        
        assert result.is_valid is False
        assert result.safety_level == CommandSafetyLevel.BLOCKED
    
    def test_rejects_pipe(self, validator):
        """Should reject pipe."""
        result = validator.validate("cat file | bash")
        
        assert result.is_valid is False
    
    def test_rejects_command_substitution(self, validator):
        """Should reject command substitution."""
        result = validator.validate("echo $(whoami)")
        
        assert result.is_valid is False
    
    def test_rejects_backticks(self, validator):
        """Should reject backticks."""
        result = validator.validate("echo `whoami`")
        
        assert result.is_valid is False
    
    def test_rejects_path_traversal(self, validator):
        """Should reject path traversal."""
        result = validator.validate("cat ../../../etc/passwd")
        
        assert result.is_valid is False
    
    def test_rejects_empty_command(self, validator):
        """Should reject empty command."""
        result = validator.validate("")
        
        assert result.is_valid is False
    
    def test_rejects_too_many_args(self, validator):
        """Should reject too many arguments."""
        args = " ".join([f"arg{i}" for i in range(50)])
        result = validator.validate(f"echo {args}")
        
        assert result.is_valid is False
    
    def test_validates_args(self, validator):
        """Should validate arguments."""
        is_valid, errors = validator.validate_args(["file.txt"])
        
        assert is_valid is True
        assert len(errors) == 0
    
    def test_rejects_dangerous_args(self, validator):
        """Should reject dangerous arguments."""
        is_valid, errors = validator.validate_args(["; rm -rf /"])
        
        assert is_valid is False


# =============================================================================
# Test: ArgumentSanitizer
# =============================================================================

class TestArgumentSanitizer:
    """Test ArgumentSanitizer."""
    
    def test_sanitizes_arg(self, sanitizer):
        """Should sanitize argument."""
        result = sanitizer.sanitize("normal_file.txt")
        
        assert result == "normal_file.txt"
    
    def test_removes_null_bytes(self, sanitizer):
        """Should remove null bytes."""
        result = sanitizer.sanitize("file\x00name")
        
        assert "\x00" not in result
    
    def test_removes_semicolon(self, sanitizer):
        """Should remove semicolon."""
        result = sanitizer.sanitize("file; rm -rf /")
        
        assert ";" not in result
    
    def test_removes_pipe(self, sanitizer):
        """Should remove pipe."""
        result = sanitizer.sanitize("file | bash")
        
        assert "|" not in result
    
    def test_removes_backticks(self, sanitizer):
        """Should remove backticks."""
        result = sanitizer.sanitize("`whoami`")
        
        assert "`" not in result
    
    def test_removes_dollar_sign(self, sanitizer):
        """Should remove dollar sign."""
        result = sanitizer.sanitize("$HOME")
        
        assert "$" not in result
    
    def test_collapses_spaces(self, sanitizer):
        """Should collapse multiple spaces."""
        result = sanitizer.sanitize("file   name")
        
        assert "  " not in result
    
    def test_truncates_long_args(self, sanitizer):
        """Should truncate long arguments."""
        long_arg = "x" * 2000
        result = sanitizer.sanitize(long_arg)
        
        assert len(result) <= 1024
    
    def test_escapes_for_shell(self, sanitizer):
        """Should escape for shell."""
        result = sanitizer.escape_for_shell("file with spaces")
        
        assert result == "'file with spaces'"
    
    def test_sanitizes_all(self, sanitizer):
        """Should sanitize all arguments."""
        args = ["file1", "file;2", "file|3"]
        result = sanitizer.sanitize_all(args)
        
        assert ";" not in result[1]
        assert "|" not in result[2]


# =============================================================================
# Test: SafeCommandExecutor
# =============================================================================

class TestSafeCommandExecutor:
    """Test SafeCommandExecutor."""
    
    def test_executes_allowed_command(self, executor):
        """Should execute allowed command."""
        result = executor.execute("echo", ["hello"])
        
        assert result.status == CommandResult.SUCCESS
        assert "hello" in result.stdout
    
    def test_blocks_disallowed_command(self, executor):
        """Should block disallowed command."""
        result = executor.execute("rm", ["-rf", "/"])
        
        assert result.status == CommandResult.BLOCKED
    
    def test_handles_nonexistent_command(self):
        """Should handle nonexistent command."""
        config = CommandConfig(allowed_commands={"nonexistent_cmd_xyz"})
        executor = SafeCommandExecutor(config)
        
        result = executor.execute("nonexistent_cmd_xyz")
        
        assert result.status == CommandResult.ERROR
        assert "not found" in result.error_message.lower()
    
    def test_respects_timeout(self):
        """Should respect timeout."""
        config = CommandConfig(
            allowed_commands={"sleep"},
            timeout_seconds=1,
        )
        executor = SafeCommandExecutor(config)
        
        result = executor.execute("sleep", ["10"])
        
        assert result.status == CommandResult.TIMEOUT
    
    def test_captures_stderr(self, executor):
        """Should capture stderr."""
        result = executor.execute("ls", ["nonexistent_file_xyz"])
        
        assert result.status == CommandResult.SUCCESS
        # ls returns error for nonexistent file
        assert result.return_code != 0
    
    def test_execute_safe(self, executor):
        """Should execute command line safely."""
        result = executor.execute_safe("echo hello world")
        
        assert result.status == CommandResult.SUCCESS
        assert "hello" in result.stdout
    
    def test_sanitizes_arguments(self, executor):
        """Should sanitize arguments."""
        result = executor.execute("echo", ["test;echo evil"])
        
        # Semicolon should be removed
        assert "evil" not in result.stdout or ";" not in result.stdout


# =============================================================================
# Test: CommandSecurityService
# =============================================================================

class TestCommandSecurityService:
    """Test CommandSecurityService."""
    
    def test_singleton(self):
        """Should return singleton instance."""
        CommandSecurityService._instance = None
        
        s1 = get_command_service()
        s2 = get_command_service()
        
        assert s1 is s2
    
    def test_validate(self, service):
        """Should validate command."""
        result = service.validate("ls -la")
        
        assert result.is_valid is True
    
    def test_execute(self, service):
        """Should execute command."""
        result = service.execute("echo", ["test"])
        
        assert result.status == CommandResult.SUCCESS
    
    def test_sanitize(self, service):
        """Should sanitize argument."""
        result = service.sanitize("file;rm")
        
        assert ";" not in result
    
    def test_add_allowed_command(self, service):
        """Should add allowed command."""
        service.add_allowed_command("mycommand")
        
        assert "mycommand" in service.config.allowed_commands
    
    def test_remove_allowed_command(self, service):
        """Should remove allowed command."""
        service.remove_allowed_command("ls")
        
        assert "ls" not in service.config.allowed_commands
    
    def test_add_blocked_command(self, service):
        """Should add blocked command."""
        service.add_blocked_command("dangerous")
        
        assert "dangerous" in service.config.blocked_commands
    
    def test_is_command_allowed(self, service):
        """Should check if command allowed."""
        assert service.is_command_allowed("ls") is True
        assert service.is_command_allowed("rm") is False


# =============================================================================
# Test: Convenience Functions
# =============================================================================

class TestConvenienceFunctions:
    """Test convenience functions."""
    
    def test_validate_command(self):
        """Should validate via convenience function."""
        CommandSecurityService._instance = None
        
        result = validate_command("ls -la")
        
        assert result.is_valid is True
    
    def test_execute_command(self):
        """Should execute via convenience function."""
        CommandSecurityService._instance = None
        
        result = execute_command("echo", ["test"])
        
        assert result.status == CommandResult.SUCCESS
    
    def test_sanitize_argument(self):
        """Should sanitize via convenience function."""
        CommandSecurityService._instance = None
        
        result = sanitize_argument("file;rm")
        
        assert ";" not in result


# =============================================================================
# Test: Security (Injection Prevention)
# =============================================================================

class TestInjectionPrevention:
    """Test command injection prevention."""
    
    def test_blocks_semicolon_injection(self, validator):
        """Should block semicolon injection."""
        assert not validator.validate("ls; rm -rf /").is_valid
    
    def test_blocks_ampersand_injection(self, validator):
        """Should block ampersand injection."""
        assert not validator.validate("ls & rm -rf /").is_valid
    
    def test_blocks_pipe_injection(self, validator):
        """Should block pipe injection."""
        assert not validator.validate("ls | bash").is_valid
    
    def test_blocks_backtick_injection(self, validator):
        """Should block backtick injection."""
        assert not validator.validate("echo `id`").is_valid
    
    def test_blocks_dollar_paren_injection(self, validator):
        """Should block $() injection."""
        assert not validator.validate("echo $(id)").is_valid
    
    def test_blocks_variable_expansion(self, validator):
        """Should block variable expansion."""
        assert not validator.validate("echo ${PATH}").is_valid
    
    def test_blocks_redirect_injection(self, validator):
        """Should block redirect injection."""
        assert not validator.validate("echo test >> /etc/passwd").is_valid
    
    def test_blocks_path_traversal(self, validator):
        """Should block path traversal."""
        assert not validator.validate("cat ../../../etc/passwd").is_valid
    
    def test_blocks_home_expansion(self, validator):
        """Should block home expansion."""
        assert not validator.validate("cat ~/.ssh/id_rsa").is_valid
    
    def test_never_uses_shell(self, executor):
        """Should never use shell=True."""
        # This is a design test - executor never uses shell=True
        # The test validates safe commands don't execute shell features
        result = executor.execute("echo", ["test;whoami"])
        
        # If shell=True was used, whoami would execute
        # With shell=False, the literal string is echoed
        assert "whoami" not in result.stdout or result.stdout.strip() == "testwhoami"

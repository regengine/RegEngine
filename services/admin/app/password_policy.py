"""Password Policy Enforcement Module.

SEC-009: Implements configurable password strength requirements.

Usage:
    from app.password_policy import validate_password, PasswordPolicyError
    import structlog
    
    logger = structlog.get_logger(__name__)
    
    try:
        validate_password("MyP@ssw0rd!")
    except PasswordPolicyError as e:
        logger.error("password_validation_failed", violations=e.message)
"""

import re
import os
from dataclasses import dataclass, field
from typing import List, Optional


# Password Policy Configuration (all values configurable via env)
MIN_LENGTH = int(os.getenv("PASSWORD_MIN_LENGTH", "12"))
REQUIRE_UPPERCASE = os.getenv("PASSWORD_REQUIRE_UPPERCASE", "true").lower() == "true"
REQUIRE_LOWERCASE = os.getenv("PASSWORD_REQUIRE_LOWERCASE", "true").lower() == "true"
REQUIRE_DIGIT = os.getenv("PASSWORD_REQUIRE_DIGIT", "true").lower() == "true"
REQUIRE_SPECIAL = os.getenv("PASSWORD_REQUIRE_SPECIAL", "true").lower() == "true"
MAX_LENGTH = int(os.getenv("PASSWORD_MAX_LENGTH", "128"))

# Common password blocklist — NIST SP 800-63B requires checking against
# breach corpuses.  Load from file when available; fall back to inline set (#970).
import pathlib as _pathlib

_BLOCKLIST_PATH = _pathlib.Path(__file__).resolve().parent.parent.parent.parent / "data" / "common_passwords.txt"


def _load_blocklist() -> frozenset:
    try:
        with open(_BLOCKLIST_PATH) as f:
            return frozenset(line.strip().lower() for line in f if line.strip())
    except FileNotFoundError:
        pass
    # Inline fallback — minimum viable blocklist
    return frozenset({
        "password", "password123", "123456", "qwerty", "admin", "letmein",
        "welcome", "monkey", "dragon", "master", "123456789", "12345678",
        "abc123", "111111", "iloveyou", "trustno1", "sunshine", "princess",
        "football", "baseball", "shadow", "michael", "batman", "access",
        "hello", "charlie", "donald", "login", "passw0rd", "1234567890",
        "regengine", "compliance", "traceability", "fsma204",
    })


COMMON_PASSWORDS = _load_blocklist()


class PasswordPolicyError(Exception):
    """Raised when password fails policy validation."""

    def __init__(self, violations: List[str]):
        self.violations = violations
        self.message = "; ".join(violations)
        super().__init__(self.message)


@dataclass
class PasswordPolicy:
    """Password policy configuration."""

    min_length: int = MIN_LENGTH
    max_length: int = MAX_LENGTH
    require_uppercase: bool = REQUIRE_UPPERCASE
    require_lowercase: bool = REQUIRE_LOWERCASE
    require_digit: bool = REQUIRE_DIGIT
    require_special: bool = REQUIRE_SPECIAL
    blocked_passwords: set = field(default_factory=lambda: COMMON_PASSWORDS)

    def validate(self, password: str, user_context: Optional[dict] = None) -> List[str]:
        """Validate password against policy.

        Args:
            password: The password to validate
            user_context: Optional dict with keys 'email', 'username', 'first_name', 'last_name'

        Returns:
            List of policy violation messages (empty if valid)
        """
        violations = []

        # Length checks
        if len(password) < self.min_length:
            violations.append(f"Password must be at least {self.min_length} characters")

        if len(password) > self.max_length:
            violations.append(f"Password must not exceed {self.max_length} characters")

        # Character class checks
        if self.require_uppercase and not re.search(r"[A-Z]", password):
            violations.append("Password must contain at least one uppercase letter")

        if self.require_lowercase and not re.search(r"[a-z]", password):
            violations.append("Password must contain at least one lowercase letter")

        if self.require_digit and not re.search(r"\d", password):
            violations.append("Password must contain at least one digit")

        if self.require_special and not re.search(r"[!@#$%^&*(),.?\":{}|<>_\-+=\[\]\\;'/`~]", password):
            violations.append("Password must contain at least one special character")

        # Repetition check (max 3 consecutive identical characters)
        if re.search(r"(.)\1\1", password):
            violations.append("Password must not contain more than 2 consecutive identical characters")

        # Personal Information Check
        if user_context:
            for field_name in ['email', 'username', 'first_name', 'last_name']:
                value = user_context.get(field_name)
                if value and len(value) > 3:
                    # For email, check the part before @
                    if field_name == 'email':
                        parts = value.split('@')
                        check_values = [p for p in parts if len(p) > 3]
                    else:
                        check_values = [value]

                    for val in check_values:
                        if val.lower() in password.lower():
                            violations.append(f"Password must not contain your {field_name}")

        # Blocklist check
        if password.lower() in self.blocked_passwords:
            violations.append("Password is too common and easily guessed")

        return violations


# Default policy instance
_default_policy = PasswordPolicy()


def validate_password(password: str, policy: Optional[PasswordPolicy] = None, user_context: Optional[dict] = None) -> None:
    """Validate password against policy, raising on failure.

    Args:
        password: The password to validate
        policy: Optional custom policy (uses default if not provided)
        user_context: Optional dict for contextual validation

    Raises:
        PasswordPolicyError: If password violates policy
    """
    p = policy or _default_policy
    violations = p.validate(password, user_context)

    if violations:
        raise PasswordPolicyError(violations)


def check_password_strength(password: str, user_context: Optional[dict] = None) -> dict:
    """Check password strength without raising.

    Args:
        password: The password to check
        user_context: Optional context

    Returns:
        Dict with 'valid' bool and any 'violations' list
    """
    violations = _default_policy.validate(password, user_context)
    return {
        "valid": len(violations) == 0,
        "violations": violations,
        "strength": "strong" if len(violations) == 0 else "weak",
    }


def get_policy_requirements() -> dict:
    """Get current policy requirements for UI display."""
    return {
        "min_length": MIN_LENGTH,
        "max_length": MAX_LENGTH,
        "require_uppercase": REQUIRE_UPPERCASE,
        "require_lowercase": REQUIRE_LOWERCASE,
        "require_digit": REQUIRE_DIGIT,
        "require_special": REQUIRE_SPECIAL,
        "no_repetition": True,
        "no_personal_info": True,
    }

"""Docstring coverage for shared.database public surface."""

from shared import database as shared_database


def test_module_has_docstring():
    assert isinstance(shared_database.__doc__, str) and shared_database.__doc__.strip()


def test_circuit_breaker_has_docstrings():
    assert isinstance(shared_database.CircuitBreaker.__doc__, str) and shared_database.CircuitBreaker.__doc__.strip()
    assert (
        isinstance(shared_database.CircuitBreaker.__init__.__doc__, str)
        and shared_database.CircuitBreaker.__init__.__doc__.strip()
    )
    assert (
        isinstance(shared_database.CircuitBreaker.call.__doc__, str)
        and shared_database.CircuitBreaker.call.__doc__.strip()
    )

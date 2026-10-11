"""``SupplierGraphSync._get_driver`` stays graceful when credentials vanish.

``shared.secrets_manager`` is now fail-closed in production: the Neo4j getter
raises instead of returning localhost fallbacks. Startup validation guarantees
credentials exist at boot, so a raise at runtime means they disappeared
mid-flight (rotation gap, revoked secret). The mirror must no-op in that case,
exactly as it already did for empty credentials, rather than crash the caller.
"""

from app import supplier_graph_sync as module
from app.supplier_graph_sync import SupplierGraphSync


class _RaisingSecrets:
    def get_neo4j_credentials(self, environment=None):
        raise RuntimeError("Missing required Neo4j credentials in production: NEO4J_PASSWORD")


def test_get_driver_returns_none_when_credentials_raise(monkeypatch):
    """A fail-closed getter raise degrades to a no-op, not a crash."""
    monkeypatch.setattr(module, "get_secrets_manager", lambda: _RaisingSecrets())
    monkeypatch.setattr(module, "GraphDatabase", object())
    sync = SupplierGraphSync(enabled=True)
    assert sync._get_driver() is None


def test_get_driver_returns_none_when_disabled_without_touching_secrets(monkeypatch):
    """A disabled sync never consults the secrets manager at all."""
    monkeypatch.setattr(
        module,
        "get_secrets_manager",
        lambda: (_ for _ in ()).throw(AssertionError("must not be called")),
    )
    sync = SupplierGraphSync(enabled=False)
    assert sync._get_driver() is None

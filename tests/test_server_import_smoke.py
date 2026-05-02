import importlib


def test_consolidated_backend_imports():
    module = importlib.import_module("server.main")

    assert hasattr(module, "app")

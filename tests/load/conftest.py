"""Load-test directory conftest.

``tests/load/*.py`` contains Locust scenarios, not pytest tests. Importing
them triggers gevent monkey-patching of ``ssl`` after ``ssl`` was already
imported, which hits a RecursionError during pytest collection (see
https://github.com/gevent/gevent/issues/1016).

The Locust scenarios are executed via ``locust -f <file>`` in CI/infra,
not via pytest. Skip them during collection so the main suite can run.
"""
collect_ignore_glob = ["test_*.py"]

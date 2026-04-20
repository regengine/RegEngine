"""Coverage-sweep tests for ``app.models`` SSRF protection (#549, #1342).

``app/models.py`` is imported transitively via ``test_normalization_1342.py``
but the SSRF guard at ``_reject_private_host`` (lines 35-68) and the two
field validators that call it (lines 78-82, 127-131) are never exercised.
That leaves a 90% coverage ceiling on this module and, more importantly,
leaves the #549 SSRF mitigation silently unverified. This file pins:

* line 38-39 — host-missing branch
* line 42-43 — metadata hostname blocklist (all three entries)
* line 46-50 — DNS resolution failure (``socket.gaierror``)
* line 58-62 — ``is_private`` / ``is_loopback`` / ``is_link_local`` /
  ``is_reserved`` rejection branch (covers the common AWS/GCP IMDS case)
* line 63-68 — the defense-in-depth ``_SSRF_BLOCKED_NETWORKS`` fallback
  (reachable only via a forged ``ipaddress.ip_address`` that passes the
  public-address check but still lives inside a blocked network — exists
  to catch future Python stdlib regressions)
* line 81-82 — ``IngestRequest.url_must_not_be_private`` validator hook
* line 130-131 — ``NormalizedDocument.source_url_must_not_be_private``
  validator hook

The validators are driven through the real pydantic model factories so
the tests fail if the ``@field_validator`` decoration is accidentally
dropped in a refactor (the most common silent-regression mode for SSRF
guards).
"""

from __future__ import annotations

import ipaddress
import socket
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

service_dir = Path(__file__).parent.parent
sys.path.insert(0, str(service_dir))

from app.models import (  # noqa: E402
    IngestRequest,
    NormalizedDocument,
    _reject_private_host,
)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _addrinfo(ip: str, family: int = socket.AF_INET):
    """Build a minimal addrinfo tuple like ``socket.getaddrinfo`` returns."""
    port = 0
    if family == socket.AF_INET6:
        sockaddr = (ip, port, 0, 0)
    else:
        sockaddr = (ip, port)
    return (family, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", sockaddr)


def _patch_resolver(monkeypatch: pytest.MonkeyPatch, ips: list[str]) -> None:
    """Force ``socket.getaddrinfo`` to return ``ips`` regardless of host."""

    def _fake(host, port, *args, **kwargs):
        return [
            _addrinfo(ip, socket.AF_INET6 if ":" in ip else socket.AF_INET)
            for ip in ips
        ]

    monkeypatch.setattr("app.models.socket.getaddrinfo", _fake)


# --------------------------------------------------------------------------- #
# _reject_private_host — direct tests
# --------------------------------------------------------------------------- #


class TestRejectPrivateHost:

    def test_public_host_passes(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # 8.8.8.8 is not private/loopback/link_local/reserved/in-blocked-net.
        _patch_resolver(monkeypatch, ["8.8.8.8"])
        url = IngestRequest.model_validate(
            {"url": "https://example.com/x", "source_system": "src"}
        ).url
        # Validator path already covered by this call. For the direct
        # helper assertion, re-invoke against the public IP.
        _reject_private_host(url)  # must not raise

    @pytest.mark.parametrize(
        "blocked,url",
        [
            ("metadata.google.internal", "https://metadata.google.internal/x"),
            ("169.254.169.254", "https://169.254.169.254/x"),
            # IPv6 literals must be bracketed in URLs per RFC 3986 §3.2.2.
            # The guard now strips brackets from ``url.host`` before the
            # blocklist lookup so the AWS IPv6 IMDS entry actually fires
            # through the pydantic validator path.
            ("fd00:ec2::254", "https://[fd00:ec2::254]/x"),
        ],
    )
    def test_blocked_hostname_rejected_before_dns(
        self,
        monkeypatch: pytest.MonkeyPatch,
        blocked: str,
        url: str,
    ) -> None:
        # Line 42-43. Resolver should not even be consulted — if we got
        # past the hostname blocklist something is wrong.
        def _boom(*_a, **_kw):
            pytest.fail("DNS resolver must not be called for blocked hostnames")

        monkeypatch.setattr("app.models.socket.getaddrinfo", _boom)
        with pytest.raises(ValidationError) as exc:
            IngestRequest(url=url, source_system="src")
        assert "metadata endpoint" in str(exc.value)

    def test_blocked_ipv6_literal_exercises_helper_directly(self) -> None:
        # Backstop: calling the helper with a duck-typed URL whose host
        # matches the IPv6 IMDS entry exactly. Pins the blocklist set
        # independently of the pydantic bracketed-host normalization.
        class _Ipv6Url:
            host = "fd00:ec2::254"

        with pytest.raises(ValueError, match="metadata endpoint"):
            _reject_private_host(_Ipv6Url())  # type: ignore[arg-type]

    def test_ipv6_literal_private_rejected_without_dns(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Literal-IP URLs should be short-circuited before DNS. Use a
        # ULA address that is *not* on the hostname blocklist so the
        # rejection path is the literal-IP range check.
        def _boom(*_a, **_kw):
            pytest.fail("DNS resolver must not be called for literal IP URLs")

        monkeypatch.setattr("app.models.socket.getaddrinfo", _boom)
        with pytest.raises(ValidationError) as exc:
            IngestRequest(
                url="https://[fd12:3456::1]/x", source_system="src"
            )
        assert "private or reserved" in str(exc.value)

    def test_ipv4_literal_private_rejected_without_dns(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # 10.1.2.3 is not on the hostname blocklist but is in the
        # private range. Literal IPv4 URLs must also skip DNS.
        def _boom(*_a, **_kw):
            pytest.fail("DNS resolver must not be called for literal IP URLs")

        monkeypatch.setattr("app.models.socket.getaddrinfo", _boom)
        with pytest.raises(ValidationError) as exc:
            IngestRequest(url="https://10.1.2.3/x", source_system="src")
        assert "private or reserved" in str(exc.value)

    def test_ipv4_literal_public_passes_without_dns(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # A public IPv4 literal must pass the literal short-circuit
        # without ever hitting DNS.
        def _boom(*_a, **_kw):
            pytest.fail("DNS resolver must not be called for literal IP URLs")

        monkeypatch.setattr("app.models.socket.getaddrinfo", _boom)
        req = IngestRequest(url="https://8.8.8.8/x", source_system="src")
        assert str(req.url).startswith("https://8.8.8.8")

    def test_missing_host_rejects(self) -> None:
        # Line 38-39. Pydantic's HttpUrl always has a host, so we exercise
        # the helper directly with a duck-typed object.
        class _HostlessUrl:
            host: str | None = ""

        with pytest.raises(ValueError, match="must include a hostname"):
            _reject_private_host(_HostlessUrl())  # type: ignore[arg-type]

        class _NoneHostUrl:
            host: str | None = None

        with pytest.raises(ValueError, match="must include a hostname"):
            _reject_private_host(_NoneHostUrl())  # type: ignore[arg-type]

    def test_blocked_hostname_case_insensitive(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Uppercase metadata host must still hit the blocklist branch.
        monkeypatch.setattr(
            "app.models.socket.getaddrinfo",
            lambda *_a, **_kw: pytest.fail("resolver should not be called"),
        )
        with pytest.raises(ValidationError):
            IngestRequest(
                url="https://Metadata.Google.Internal/x",
                source_system="src",
            )

    def test_dns_failure_rejects(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Line 46-50. If DNS fails we cannot verify — reject.
        def _fail(*_a, **_kw):
            raise socket.gaierror("nxdomain")

        monkeypatch.setattr("app.models.socket.getaddrinfo", _fail)
        with pytest.raises(ValidationError) as exc:
            IngestRequest(
                url="https://nx.example.invalid/x", source_system="src"
            )
        assert "Unable to resolve" in str(exc.value)

    @pytest.mark.parametrize(
        "ip",
        [
            "10.1.2.3",        # is_private
            "192.168.1.5",     # is_private
            "172.16.0.1",      # is_private
            "127.0.0.1",       # is_loopback
            "169.254.169.254",  # is_link_local (different from hostname case)
            "::1",             # is_loopback (IPv6)
            "fe80::1",         # is_link_local (IPv6)
            "fd00::1",         # is_private (IPv6 ULA per stdlib)
        ],
    )
    def test_private_ip_resolution_rejected(
        self, monkeypatch: pytest.MonkeyPatch, ip: str
    ) -> None:
        # Line 58-62. Hostname is public-looking; DNS yields a private IP.
        _patch_resolver(monkeypatch, [ip])
        with pytest.raises(ValidationError) as exc:
            IngestRequest(
                url="https://attacker.example.com/x", source_system="src"
            )
        assert "private or reserved" in str(exc.value)

    def test_any_private_in_multi_ip_response_rejects(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Resolver returns a public IP plus a private IP — the latter
        # must still trigger rejection (defense against DNS-rebinding
        # where multiple A records are returned).
        _patch_resolver(monkeypatch, ["8.8.8.8", "10.0.0.1"])
        with pytest.raises(ValidationError):
            IngestRequest(
                url="https://multi.example.com/x", source_system="src"
            )

    def test_unparseable_ip_is_skipped(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Line 56-57 (``except ValueError: continue``). Forge a resolver
        # that yields an unparseable address, then a public one. The
        # unparseable entry should be silently skipped rather than
        # crashing the validator.
        def _fake(host, port, *args, **kwargs):
            return [
                _addrinfo("not-an-ip", family=socket.AF_INET),
                _addrinfo("8.8.8.8"),
            ]

        monkeypatch.setattr("app.models.socket.getaddrinfo", _fake)
        # Should not raise — the public IP is still valid.
        IngestRequest(
            url="https://weird.example.com/x", source_system="src"
        )

    def test_blocked_network_defense_in_depth(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Line 63-68. In real stdlib, every IP in _SSRF_BLOCKED_NETWORKS
        # already matches ``is_private``/``is_loopback``/``is_link_local``/
        # ``is_reserved``, so this branch is defense-in-depth. To hit it
        # we forge ``ipaddress.ip_address`` to return an object whose
        # public-address predicates are all False but which still
        # containment-matches the 10/8 network. This simulates a future
        # stdlib regression where the predicate flags drift out of sync
        # with the containment-based blocklist.
        real_addr = ipaddress.ip_address("10.99.99.99")

        class _SneakyAddr:
            is_private = False
            is_loopback = False
            is_link_local = False
            is_reserved = False

            def __contains__(self, other):  # pragma: no cover — not called
                return False

            # Delegate network containment checks to the real addr.
            def __eq__(self, other):
                return real_addr == other

            def __hash__(self):
                return hash(real_addr)

        sneaky = _SneakyAddr()

        # Patch the ip_address factory used by models.py so our sneaky
        # object is returned. Also patch in ipaddress's network `__contains__`
        # indirectly: the code does ``if addr in network``, which calls
        # network.__contains__(addr). Force that to return True for our
        # sneaky instance when the network is 10.0.0.0/8.
        real_ten_net = ipaddress.ip_network("10.0.0.0/8")
        original_contains = type(real_ten_net).__contains__

        def _patched_contains(self, item):
            if item is sneaky and self == real_ten_net:
                return True
            return original_contains(self, item)

        monkeypatch.setattr(
            "app.models.ipaddress.ip_address", lambda _s: sneaky
        )
        monkeypatch.setattr(
            ipaddress.IPv4Network, "__contains__", _patched_contains
        )
        _patch_resolver(monkeypatch, ["10.99.99.99"])

        with pytest.raises(ValidationError) as exc:
            IngestRequest(
                url="https://sneaky.example.com/x", source_system="src"
            )
        assert "private or reserved" in str(exc.value)


# --------------------------------------------------------------------------- #
# IngestRequest.url_must_not_be_private  (line 81-82)
# --------------------------------------------------------------------------- #


class TestIngestRequestValidator:

    def test_public_url_accepted(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_resolver(monkeypatch, ["93.184.216.34"])  # example.com
        req = IngestRequest(
            url="https://example.com/api", source_system="fda"
        )
        assert str(req.url).startswith("https://example.com")
        assert req.source_system == "fda"

    def test_private_url_rejected_via_validator(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Confirms the decorator is still wired up — if the @field_validator
        # line goes away, this test fails loudly.
        _patch_resolver(monkeypatch, ["10.0.0.1"])
        with pytest.raises(ValidationError):
            IngestRequest(
                url="https://internal.example.com/", source_system="fda"
            )


# --------------------------------------------------------------------------- #
# NormalizedDocument.source_url_must_not_be_private  (line 130-131)
# --------------------------------------------------------------------------- #


class TestNormalizedDocumentValidator:

    def test_public_source_url_accepted(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from datetime import datetime, timezone

        _patch_resolver(monkeypatch, ["93.184.216.34"])
        doc = NormalizedDocument(
            document_id="doc-1",
            source_url="https://example.com/reg/1",
            source_system="federal_register",
            retrieved_at=datetime(2026, 4, 19, tzinfo=timezone.utc),
            text="regulation text",
            content_sha256="a" * 64,
        )
        assert doc.document_id == "doc-1"

    def test_private_source_url_rejected(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from datetime import datetime, timezone

        _patch_resolver(monkeypatch, ["127.0.0.1"])
        with pytest.raises(ValidationError) as exc:
            NormalizedDocument(
                document_id="doc-2",
                source_url="https://loopback-attack.example.com/",
                source_system="federal_register",
                retrieved_at=datetime(2026, 4, 19, tzinfo=timezone.utc),
                text="",
                content_sha256="a" * 64,
            )
        assert "private or reserved" in str(exc.value)

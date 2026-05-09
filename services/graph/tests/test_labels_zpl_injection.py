"""RE-SEC-004 integration tests: ZPL injection in label generation.

Covers two layers of defense:

1. ``ProductInfo`` Pydantic validators reject ``description`` / ``plu``
   inputs containing ``^``, ``~``, or control bytes — caller sees a
   ``ValidationError`` (HTTP 400 in the API), not a silently mangled label.

2. ``generate_zpl_code`` runs every interpolated string through
   ``zpl_safe`` so even if a value reaches the formatter (e.g. via a code
   path that bypasses the request schema), no ``^XZ`` / ``^XA`` / ``~JA``
   can break out of the format block or reprogram the printer.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from services.graph.app.routers.labels import (  # noqa: E402
    ProductInfo,
    generate_zpl_code,
)


@pytest.mark.security
class TestProductInfoRejectsZplInjection:
    def test_caret_in_description_raises(self):
        with pytest.raises(ValidationError):
            ProductInfo(
                gtin="00000012345678",
                description="Romaine^XZ^XA",
                plu=None,
                expected_units=10,
            )

    def test_tilde_in_description_raises(self):
        with pytest.raises(ValidationError):
            ProductInfo(
                gtin="00000012345678",
                description="Romaine~JA",
                plu=None,
                expected_units=10,
            )

    def test_control_byte_in_description_raises(self):
        with pytest.raises(ValidationError):
            ProductInfo(
                gtin="00000012345678",
                description="Romaine\x00",
                plu=None,
                expected_units=10,
            )

    def test_caret_in_plu_raises(self):
        with pytest.raises(ValidationError):
            ProductInfo(
                gtin="00000012345678",
                description="Romaine",
                plu="4080^XZ",
                expected_units=10,
            )

    def test_clean_input_passes(self):
        info = ProductInfo(
            gtin="00000012345678",
            description="Romaine 8oz Bag",
            plu="4080",
            expected_units=10,
        )
        assert info.description == "Romaine 8oz Bag"
        assert info.plu == "4080"


@pytest.mark.security
class TestGenerateZplCodeNeutralizesInjection:
    def test_caret_attack_in_desc_is_stripped(self):
        # Bypass the Pydantic validator and ensure the formatter still
        # produces a single well-formed label (one ^XA / ^XZ pair).
        zpl = generate_zpl_code(
            desc="^XZ^XAEvil",
            plu=None,
            qr="https://trace.example.com/01/x/10/y/21/z",
            serial="00012345601234567",
            gtin="00000012345678",
        )
        # Caret-prefix attack must not introduce extra ^XA/^XZ tokens.
        assert zpl.count("^XA") == 1
        assert zpl.count("^XZ") == 1
        # The injected literal substrings must not appear adjacent (we
        # stripped every ^ from desc, so "XZ"/"XA" letters survive but
        # not as commands).
        assert "^XZ^XA" not in zpl.replace("^XA\n", "").replace("\n^XZ", "")

    def test_tilde_attack_in_plu_is_stripped(self):
        zpl = generate_zpl_code(
            desc="Romaine",
            plu="~JA",
            qr="https://trace.example.com/01/x/10/y/21/z",
            serial="00012345601234567",
            gtin="00000012345678",
        )
        # Tilde commands must be stripped from the PLU field.
        assert "~JA" not in zpl
        assert "~" not in zpl  # No tilde anywhere in the output.

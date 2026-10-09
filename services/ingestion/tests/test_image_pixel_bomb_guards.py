"""Pixel-bomb guards for image uploads (audit medium finding).

The compressed-byte cap (10 MB) does not bound decompressed pixels: a tiny
PNG can expand to gigapixels and OOM a worker inside Pillow, pyzbar, or the
base64 vision payload. These tests lock in the fix:

* images over MAX_IMAGE_PIXELS are rejected with 413,
* images wider than MAX_IMAGE_DECODE_SIDE_PIXELS are downscaled before
  QR decode and before the vision model call,
* small images pass through unchanged.

Huge dimensions are simulated by stubbing PIL.Image.open so the tests never
allocate a real gigapixel raster.
"""

from __future__ import annotations

import asyncio
import base64
import io
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

service_dir = Path(__file__).parent.parent
sys.path.insert(0, str(service_dir))

from app.shared import upload_limits
from app.shared.upload_limits import (
    MAX_IMAGE_DECODE_SIDE_PIXELS,
    MAX_IMAGE_PIXELS,
    downscale_image_bytes,
)
from fastapi import HTTPException


def _tiny_png_bytes() -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (4, 4), color=(255, 255, 255)).save(buf, format="PNG")
    return buf.getvalue()


def _wide_png_bytes(width: int = 3000, height: int = 1500) -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (width, height), color=(200, 30, 30)).save(buf, format="PNG")
    return buf.getvalue()


class _HugeImage:
    """Stub claiming 400 MP without allocating any raster."""

    format = "PNG"
    size = (20000, 20000)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def verify(self):
        return None

    def load(self):
        return None

    def copy(self):
        return self

    def thumbnail(self, *args, **kwargs):
        return None


def _patch_huge_image(monkeypatch):
    from PIL import Image

    monkeypatch.setattr(Image, "open", lambda *args, **kwargs: _HugeImage())
    # downscale path also touches MAX_IMAGE_PIXELS; keep the real budget.
    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", MAX_IMAGE_PIXELS)


class TestPixelBudgetConstants:
    def test_budget_is_defined_and_positive(self):
        assert isinstance(MAX_IMAGE_PIXELS, int) and MAX_IMAGE_PIXELS > 0
        assert isinstance(MAX_IMAGE_DECODE_SIDE_PIXELS, int)
        assert MAX_IMAGE_DECODE_SIDE_PIXELS > 0

    def test_pillow_threshold_clamped(self):
        from PIL import Image

        assert upload_limits._pillow_max_pixels() is not None


class TestDownscaleHelper:
    def test_small_image_passes_through_unchanged(self):
        raw = _tiny_png_bytes()
        out, mime = downscale_image_bytes(raw)
        assert out == raw
        assert mime == "image/png"

    def test_wide_image_downscaled_to_decode_side(self):
        raw = _wide_png_bytes()
        out, mime = downscale_image_bytes(raw)
        assert mime == "image/png"
        from PIL import Image

        with Image.open(io.BytesIO(out)) as img:
            img.load()
            assert max(img.size) <= MAX_IMAGE_DECODE_SIDE_PIXELS
        assert len(out) < len(raw) or out != raw

    def test_huge_dimensions_rejected_with_413(self, monkeypatch):
        _patch_huge_image(monkeypatch)
        with pytest.raises(HTTPException) as exc_info:
            downscale_image_bytes(_tiny_png_bytes())
        assert exc_info.value.status_code == 413
        assert "pixel" in exc_info.value.detail.lower()

    def test_validated_content_type_rejects_pixel_bomb(self, monkeypatch):
        _patch_huge_image(monkeypatch)
        with pytest.raises(HTTPException) as exc_info:
            upload_limits.validated_image_content_type(_tiny_png_bytes(), "image/png")
        assert exc_info.value.status_code == 413


class TestQrDecodePixelBomb:
    def test_decode_rejects_pixel_bomb(self, monkeypatch):
        import app.qr_decoder as qr_decoder

        fake_sub = ModuleType("pyzbar.pyzbar")
        fake_sub.decode = lambda image: [SimpleNamespace(data=b"https://id.example.com/01/09506000134352")]
        fake_pkg = ModuleType("pyzbar")
        fake_pkg.pyzbar = fake_sub
        monkeypatch.setitem(sys.modules, "pyzbar", fake_pkg)
        monkeypatch.setitem(sys.modules, "pyzbar.pyzbar", fake_sub)
        _patch_huge_image(monkeypatch)
        with pytest.raises(HTTPException) as exc_info:
            qr_decoder._decode_image_bytes(_tiny_png_bytes())
        assert exc_info.value.status_code == 413

    def test_decode_downscales_wide_image_before_pyzbar(self, monkeypatch):
        import app.qr_decoder as qr_decoder
        from PIL import Image

        raw = _wide_png_bytes()
        seen_sizes: list = []
        real_open = Image.open

        def _spy_open(*args, **kwargs):
            img = real_open(*args, **kwargs)
            seen_sizes.append(img.size)
            return img

        fake_sub = ModuleType("pyzbar.pyzbar")

        def _fake_decode(image):
            seen_sizes.append(tuple(image.size))
            return [SimpleNamespace(data=b"0109506000134352")]

        fake_sub.decode = _fake_decode
        fake_pkg = ModuleType("pyzbar")
        fake_pkg.pyzbar = fake_sub
        monkeypatch.setitem(sys.modules, "pyzbar", fake_pkg)
        monkeypatch.setitem(sys.modules, "pyzbar.pyzbar", fake_sub)
        monkeypatch.setattr(Image, "open", _spy_open)
        value = qr_decoder._decode_image_bytes(raw)
        assert value == "0109506000134352"
        assert seen_sizes, "pyzbar should have received an image"
        assert max(seen_sizes[-1]) <= MAX_IMAGE_DECODE_SIDE_PIXELS


class TestLabelVisionPixelBomb:
    def _install_openai(self, monkeypatch, **kwargs):
        import json

        captured: dict = {}

        class _Completions:
            def __init__(self):
                self.last_kwargs: dict | None = None

            async def create(self, **kw):
                self.last_kwargs = kw
                return SimpleNamespace(
                    choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps({"fsma_compatible": False})))]
                )

        class _Client:
            def __init__(self, *, api_key: str):
                captured["api_key"] = api_key
                self.chat = SimpleNamespace(completions=_Completions())

        def _factory(*, api_key: str):
            client = _Client(api_key=api_key)
            captured["client"] = client
            return client

        fake_mod = ModuleType("openai")
        fake_mod.AsyncOpenAI = _factory
        monkeypatch.setitem(sys.modules, "openai", fake_mod)
        return captured

    def test_rejects_pixel_bomb_with_413(self, monkeypatch):
        from app import label_vision as lv

        class _Up:
            content_type = "image/png"

            def __init__(self, content: bytes):
                self._buf = io.BytesIO(content)

            async def read(self, size: int = -1) -> bytes:
                return self._buf.read(size)

        _patch_huge_image(monkeypatch)
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(lv.analyze_label(file=_Up(_tiny_png_bytes()), api_key="k"))
        assert exc_info.value.status_code == 413

    def test_downscales_before_model_call(self, monkeypatch):
        from app import label_vision as lv
        from PIL import Image

        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        captured = self._install_openai(monkeypatch)
        raw = _wide_png_bytes()

        class _Up:
            content_type = "image/png"

            def __init__(self, content: bytes):
                self._buf = io.BytesIO(content)

            async def read(self, size: int = -1) -> bytes:
                return self._buf.read(size)

        asyncio.run(lv.analyze_label(file=_Up(raw), api_key="k"))
        kwargs = captured["client"].chat.completions.last_kwargs
        parts = kwargs["messages"][0]["content"]
        url = parts[1]["image_url"]["url"]
        assert url.startswith("data:image/png;base64,")
        sent = base64.b64decode(url.split(",", 1)[1])
        with Image.open(io.BytesIO(sent)) as img:
            img.load()
            assert max(img.size) <= MAX_IMAGE_DECODE_SIDE_PIXELS

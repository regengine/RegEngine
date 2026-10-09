"""ZPL printer-command injection guard for regengine.labels.

Product fields are attacker-influenced text interpolated into ZPL printer
commands. A crafted value containing ``^`` or ``~`` command prefixes (for
example ``Romaine^FS^FO999,999^FDHACKED``) would break out of its
``^FD...^FS`` block and reprogram label output. ``generate_label_zpl`` must
strip those command characters before printing.
"""

from __future__ import annotations

from regengine.labels import LabelData, generate_label_zpl


def _label(**overrides) -> LabelData:
    fields = {
        "traceability_lot_code": "LOT-001",
        "product_description": "Romaine Hearts",
        "quantity": 100,
        "unit_of_measure": "cases",
        "location_gln": "0614141000001",
        "location_name": "Salinas, CA",
        "lot_date": "2026-02-06",
    }
    fields.update(overrides)
    return LabelData(**fields)


def _field_bodies(zpl: str) -> list:
    """Text inside each ^FD...^FS block."""
    bodies = []
    for chunk in zpl.split("^FD")[1:]:
        bodies.append(chunk.split("^FS")[0])
    return bodies


def test_product_name_cannot_inject_extra_commands():
    """A crafted product name must not add printer commands to the output."""
    evil = "Romaine^FS^FO999,999^A0N,28,28^FDHACKED"
    zpl = generate_label_zpl(_label(product_description=evil))

    assert "^FO999,999" not in zpl
    # The template emits exactly nine ^FS field terminators; an unsanitized
    # value would add a tenth from the injected ^FS.
    assert zpl.count("^FS") == 9


def test_caret_and_tilde_stripped_from_every_field():
    """No field body may retain ZPL command prefixes after sanitizing."""
    zpl = generate_label_zpl(
        _label(
            traceability_lot_code="LO^T~001",
            product_description="Green^Leaf~Lettuce",
            location_name="Salinas^CA",
            location_gln="0614~141000001",
            unit_of_measure="ca^ses",
            lot_date="2026-02-^06",
        )
    )

    for body in _field_bodies(zpl):
        assert "^" not in body
        assert "~" not in body


def test_control_characters_stripped():
    """Newlines and other control characters must not survive into ZPL."""
    zpl = generate_label_zpl(_label(product_description="Romaine\nHACKED\x00\x1b"))

    for body in _field_bodies(zpl):
        assert "\n" not in body
        assert "\x00" not in body
        assert "\x1b" not in body
    assert "RomaineHACKED" in zpl


def test_benign_fields_pass_through_unchanged():
    """Sanitizing must not mangle ordinary label text."""
    zpl = generate_label_zpl(_label())

    assert "^FDRomaine Hearts^FS" in zpl
    assert "^FDTLC: LOT-001^FS" in zpl
    assert "^FDOrigin: Salinas, CA^FS" in zpl

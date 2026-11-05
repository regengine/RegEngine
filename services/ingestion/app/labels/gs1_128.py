"""GS1-128 label symbols as Code 128 codewords, ZPL, and a hand-built PDF.

Fixed-length identifiers are checked with ``app.gs1_identifiers``. This module
does not invent identifier values and its errors do not repeat the caller's
value. No third-party barcode or PDF library.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from typing import Any

from ..gs1_identifiers import validate_gln, validate_gtin, validate_sscc

# Code 128 symbol values (ISO/IEC 15417). Not identifier data.
_START_C = 105
_FNC1 = 102
_CODE_C = 99
_CODE_B = 100
_CODE_A = 101
_STOP = 106

_PAGE_W = 4 * 72
_PAGE_H = 6 * 72
_DEFAULT_WIDTH_DOTS = 812  # 4 inches at 203 dpi
_DEFAULT_HEIGHT_DOTS = 1218  # 6 inches at 203 dpi

# GS1 AI encodable character set 82: digits, both letter cases, twenty
# specials, and no space. Figure 7.11-1 of the GS1 General Specifications.
_CSET82_TEXT = "!\"%&'()*+,-./0123456789:;<=>?ABCDEFGHIJKLMNOPQRSTUVWXYZ_abcdefghijklmnopqrstuvwxyz"
if len(_CSET82_TEXT) != 82 or len(set(_CSET82_TEXT)) != 82:
    raise RuntimeError("GS1 character set 82 is corrupt.")
_CSET82 = frozenset(_CSET82_TEXT)
_DIGITS = frozenset("0123456789")
_SEP = object()

# Six bar/space widths for symbol values 0..106. The stop symbol (106) is
# followed by one extra 2-module bar when it is drawn.
_PATTERN_BLOB = """
212222 222122 222221 121223 121322 131222 122213 122312 132212 221213
221312 231212 112232 122132 122231 113222 123122 123221 223211 221132
221231 213212 223112 312131 311222 321122 321221 312212 322112 322211
212123 212321 232121 111323 131123 131321 112313 132113 132311 211313
231113 231311 112133 112331 132131 113123 113321 133121 313121 211331
231131 213113 213311 213131 311123 311321 331121 312113 312311 332111
314111 221411 431111 111224 111422 121124 121421 141122 141221 112214
112412 122114 122411 142112 142211 241211 221114 413111 241112 134111
111242 121142 121241 114212 124112 124211 411212 421112 421211 212141
214121 412121 111143 111341 131141 114113 114311 411113 411311 113141
114131 311141 411131 211412 211214 211232 233111
"""


class Gs1LabelError(ValueError):
    """Label input that cannot be encoded.

    The message names the application identifier and the problem. It does not
    include the submitted value.
    """


@dataclass(frozen=True)
class _Spec:
    variable: bool
    kind: str
    size: int


# size is the exact length for fixed fields and the maximum for variable ones.
_SPECS: dict[str, _Spec] = {
    "00": _Spec(False, "sscc", 18),
    "01": _Spec(False, "gtin", 14),
    "02": _Spec(False, "gtin", 14),
    "11": _Spec(False, "date", 6),
    "13": _Spec(False, "date", 6),
    "15": _Spec(False, "date", 6),
    "17": _Spec(False, "date", 6),
    "410": _Spec(False, "gln", 13),
    "414": _Spec(False, "gln", 13),
    "10": _Spec(True, "text", 20),
    "21": _Spec(True, "text", 20),
    "37": _Spec(True, "count", 8),
}

_VALIDATORS = {
    "gtin": validate_gtin,
    "gln": validate_gln,
    "sscc": validate_sscc,
}


@dataclass(frozen=True)
class _Element:
    ai: str
    value: str
    variable: bool


def _patterns() -> tuple[tuple[int, ...], ...]:
    rows: list[tuple[int, ...]] = []
    for token in _PATTERN_BLOB.split():
        if len(token) != 6 or any(ch not in "1234" for ch in token):
            raise RuntimeError("Code 128 pattern table is corrupt.")
        widths = tuple(int(ch) for ch in token)
        bars = widths[0] + widths[2] + widths[4]
        spaces = widths[1] + widths[3] + widths[5]
        if sum(widths) != 11 or bars not in (4, 6, 8) or spaces not in (3, 5, 7):
            raise RuntimeError("Code 128 pattern table is corrupt.")
        rows.append(widths)
    if len(rows) != 107 or len(set(rows)) != 107:
        raise RuntimeError("Code 128 pattern table is corrupt.")
    anchors = {
        0: (2, 1, 2, 2, 2, 2),
        99: (1, 1, 3, 1, 4, 1),
        100: (1, 1, 4, 1, 3, 1),
        102: (4, 1, 1, 1, 3, 1),
        103: (2, 1, 1, 4, 1, 2),
        104: (2, 1, 1, 2, 1, 4),
        105: (2, 1, 1, 2, 3, 2),
        106: (2, 3, 3, 1, 1, 1),
    }
    for value, widths in anchors.items():
        if rows[value] != widths:
            raise RuntimeError("Code 128 pattern table is corrupt.")
    return tuple(rows)


_PATTERNS = _patterns()


def _pair(item: Any) -> tuple[Any, Any]:
    if isinstance(item, dict):
        if "ai" not in item or "value" not in item:
            raise Gs1LabelError("Each label element needs an application identifier and a value.")
        return item["ai"], item["value"]
    if isinstance(item, (list, tuple)):
        if len(item) != 2:
            raise Gs1LabelError("Each label element needs an application identifier and a value.")
        return item[0], item[1]
    ai = getattr(item, "ai", None)
    value = getattr(item, "value", None)
    if ai is None and value is None:
        raise Gs1LabelError("Each label element needs an application identifier and a value.")
    return ai, value


def _canonical_ai(raw: Any) -> str:
    if not isinstance(raw, str):
        raise Gs1LabelError("Application identifier must be text.")
    ai = raw.strip()
    if not ai:
        raise Gs1LabelError("Application identifier is empty.")
    if ai in _SPECS:
        return ai
    if ai.isdigit() and 2 <= len(ai) <= 4:
        raise Gs1LabelError(f"Application identifier {ai} is not supported.")
    raise Gs1LabelError("Unknown application identifier.")


def _valid_date(value: str) -> bool:
    if len(value) != 6 or not value.isdigit():
        return False
    month = int(value[2:4])
    day = int(value[4:6])
    if month < 1 or month > 12:
        return False
    if day == 0:
        return True
    year = 2000 + int(value[0:2])
    return 1 <= day <= calendar.monthrange(year, month)[1]


def _clean_value(ai: str, raw: Any, spec: _Spec) -> str:
    if spec.kind in _VALIDATORS:
        result = _VALIDATORS[spec.kind](raw)
        if not result.is_valid or result.value is None or len(result.value) != spec.size:
            if result.is_valid and result.value is not None and len(result.value) != spec.size:
                detail = f"This label needs {spec.size} digits."
            else:
                detail = result.error or "The value is not valid."
            raise Gs1LabelError(f"Application identifier {ai} rejected. {detail}")
        return result.value

    if not isinstance(raw, str):
        raise Gs1LabelError(f"Application identifier {ai} value must be text.")
    value = raw.strip()
    if not value:
        raise Gs1LabelError(f"Application identifier {ai} value is empty.")
    if spec.kind == "date":
        if not _valid_date(value):
            raise Gs1LabelError(f"Application identifier {ai} needs a 6 digit date. Day 00 means the whole month.")
        return value
    if spec.kind == "count":
        if not value.isdigit() or not 1 <= len(value) <= spec.size:
            raise Gs1LabelError(f"Application identifier {ai} needs 1 to {spec.size} digits.")
        return value
    if not 1 <= len(value) <= spec.size or any(ch not in _CSET82 for ch in value):
        raise Gs1LabelError(f"Application identifier {ai} has a character outside the GS1 set or the wrong length.")
    return value


def _prepare(elements: Any) -> list[_Element]:
    if elements is None or isinstance(elements, (str, bytes)):
        raise Gs1LabelError("Label elements are empty.")
    try:
        items = list(elements)
    except TypeError as exc:
        raise Gs1LabelError("Label elements must be a list of application identifier and value pairs.") from exc
    if not items:
        raise Gs1LabelError("Label elements are empty.")

    fixed: list[_Element] = []
    variable: list[_Element] = []
    seen: set[str] = set()
    for item in items:
        ai_raw, value_raw = _pair(item)
        ai = _canonical_ai(ai_raw)
        if ai in seen:
            raise Gs1LabelError(f"Application identifier {ai} is repeated.")
        seen.add(ai)
        spec = _SPECS[ai]
        element = _Element(ai, _clean_value(ai, value_raw, spec), spec.variable)
        if spec.variable:
            variable.append(element)
        else:
            fixed.append(element)
    return fixed + variable


def _atoms(elements: list[_Element]) -> list[Any]:
    variable_count = sum(1 for element in elements if element.variable)
    seen = 0
    atoms: list[Any] = []
    for element in elements:
        atoms.extend(element.ai + element.value)
        if element.variable:
            seen += 1
            if seen < variable_count:
                atoms.append(_SEP)
    return atoms


def _join_atoms(atoms: list[Any]) -> str:
    return "".join("\x1d" if atom is _SEP else atom for atom in atoms)


def _digit_run(atoms: list[Any], index: int) -> tuple[int, bool]:
    cursor = index
    while cursor < len(atoms) and isinstance(atoms[cursor], str) and atoms[cursor] in _DIGITS:
        cursor += 1
    at_boundary = cursor >= len(atoms) or atoms[cursor] is _SEP
    return cursor - index, at_boundary


def _switch_to_c(atoms: list[Any], index: int) -> bool:
    """Code C pays for itself at 4 digits on a boundary, or 6 digits in the middle.

    An odd count waits one Code B digit so the switch lands on a pair.
    """
    count, at_boundary = _digit_run(atoms, index)
    needed = 4 if at_boundary else 6
    return count >= needed and count % 2 == 0


def _encode_atoms(atoms: list[Any]) -> list[int]:
    codewords = [_START_C, _FNC1]
    mode = "C"
    index = 0
    limit = len(atoms)
    # Switches add symbols but must stay proportional to the data. A higher
    # count means the subset machine stopped advancing.
    ceiling = limit * 2 + 4
    while index < limit:
        if len(codewords) > ceiling:
            raise Gs1LabelError("Barcode could not be encoded.")
        if mode == "C":
            token = atoms[index]
            if token is _SEP:
                codewords.append(_FNC1)
                index += 1
                continue
            nxt = atoms[index + 1] if index + 1 < limit else None
            if isinstance(token, str) and token in _DIGITS and isinstance(nxt, str) and nxt in _DIGITS:
                codewords.append(int(token) * 10 + int(nxt))
                index += 2
                continue
            codewords.append(_CODE_B)
            mode = "B"
            continue
        if _switch_to_c(atoms, index):
            codewords.append(_CODE_C)
            mode = "C"
            continue
        token = atoms[index]
        if token is _SEP:
            codewords.append(_FNC1)
        else:
            codewords.append(ord(token) - 32)
        index += 1

    total = codewords[0]
    for position, value in enumerate(codewords[1:], start=1):
        total += position * value
    codewords.append(total % 103)
    codewords.append(_STOP)
    return codewords


def _runs(codewords: list[int]) -> list[int]:
    if not codewords or codewords[-1] != _STOP:
        raise Gs1LabelError("Barcode is missing the stop symbol.")
    runs: list[int] = []
    for codeword in codewords[:-1]:
        runs.extend(_PATTERNS[codeword])
    runs.extend(_PATTERNS[_STOP])
    runs.append(2)
    return runs


def _zpl_barcode(codewords: list[int]) -> str:
    if codewords[0] != _START_C or codewords[1] != _FNC1 or codewords[-1] != _STOP:
        raise Gs1LabelError("Barcode symbol is incomplete.")
    pieces = [">;", ">8"]
    mode = "C"
    for codeword in codewords[2:-2]:
        # Symbol 99 is the digit pair 99 while already in Code C. The same
        # number latches to Code C only from another subset. Symbol 100
        # latches to Code B only from Code C.
        if mode == "C" and codeword == _CODE_B:
            pieces.append(">6")
            mode = "B"
            continue
        if mode != "C" and codeword == _CODE_C:
            pieces.append(">5")
            mode = "C"
            continue
        if codeword == _CODE_A:
            pieces.append(">7")
            mode = "A"
            continue
        if codeword == _FNC1:
            pieces.append(">8")
            continue
        if mode == "C":
            if not 0 <= codeword <= 99:
                raise Gs1LabelError("Barcode subset is not encodable in ZPL.")
            pieces.append(f"{codeword:02d}")
            continue
        if mode == "B":
            if not 0 <= codeword <= 95:
                raise Gs1LabelError("Barcode subset is not encodable in ZPL.")
            character = chr(codeword + 32)
            # `>` is the ZPL invocation marker. `>0` is that character in subset B.
            pieces.append(">0" if character == ">" else character)
            continue
        raise Gs1LabelError("Barcode subset is not encodable in ZPL.")
    return "".join(pieces)


def _positive_dots(name: str, value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise Gs1LabelError(f"Label {name} must be a positive whole number.")
    return value


def _pdf_number(value: float) -> str:
    text = f"{value:.2f}"
    return "0.00" if text == "-0.00" else text


def _pdf_stream(codewords: list[int], lines: list[str]) -> bytes:
    runs = _runs(codewords)
    quiet = 10
    margin = 14.0
    total = sum(runs) + 2 * quiet
    module = min(1.8, (_PAGE_W - 2 * margin) / total)
    barcode_width = total * module
    x = (_PAGE_W - barcode_width) / 2 + quiet * module
    bar_height = 110.0
    bar_y = _PAGE_H - 36.0 - bar_height
    ops = ["q", "0 0 0 rg"]
    bar = True
    for width in runs:
        drawn = width * module
        if bar:
            ops.append(f"{_pdf_number(x)} {_pdf_number(bar_y)} {_pdf_number(drawn)} {_pdf_number(bar_height)} re f")
        x += drawn
        bar = not bar
    ops.append("Q")
    ops.append("BT")
    ops.append("/F1 10 Tf")
    ops.append("0 0 0 rg")
    text_y = bar_y - 18.0
    for index, line in enumerate(lines):
        hex_text = line.encode("ascii").hex().upper()
        if index == 0:
            ops.append(f"1 0 0 1 {_pdf_number(margin)} {_pdf_number(text_y)} Tm")
        else:
            ops.append("0 -13 Td")
        ops.append(f"<{hex_text}> Tj")
    ops.append("ET")
    return "\n".join(ops).encode("ascii")


def _pdf_document(stream: bytes) -> bytes:
    objects = [
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n",
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n",
        (
            f"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {_PAGE_W} {_PAGE_H}] "
            f"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>\nendobj\n"
        ).encode("ascii"),
        (
            b"4 0 obj\n<< /Length "
            + str(len(stream)).encode("ascii")
            + b" >>\nstream\n"
            + stream
            + b"\nendstream\nendobj\n"
        ),
        b"5 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n",
    ]
    header = b"%PDF-1.4\n"
    chunks = [header]
    offsets = [0]
    cursor = len(header)
    for obj in objects:
        offsets.append(cursor)
        chunks.append(obj)
        cursor += len(obj)
    xref_at = cursor
    lines = [f"xref\n0 {len(offsets)}\n", "0000000000 65535 f \n"]
    lines.extend(f"{offset:010d} 00000 n \n" for offset in offsets[1:])
    trailer = (f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref_at}\n%%EOF").encode("ascii")
    return b"".join(chunks) + "".join(lines).encode("ascii") + trailer


def _lines(elements: list[_Element]) -> list[str]:
    return [f"({element.ai}){element.value}" for element in elements]


def encode_gs1_128(elements: Any) -> list[int]:
    """Code 128 codewords: Start C, FNC1, data, mod-103 check, stop (106)."""
    return _encode_atoms(_atoms(_prepare(elements)))


def human_readable(elements: Any) -> str:
    """Parenthesised HRI text, fixed-length application identifiers first."""
    return "".join(_lines(_prepare(elements)))


def element_string(elements: Any) -> str:
    """Element string with a GS separator after every variable field but the last."""
    return _join_atoms(_atoms(_prepare(elements)))


def to_zpl(elements: Any, *, width_dots: int = _DEFAULT_WIDTH_DOTS, height_dots: int = _DEFAULT_HEIGHT_DOTS) -> str:
    """ZPL for a 203 dpi label. The barcode starts ``>;>8`` and uses ``>8`` between variable fields."""
    prepared = _prepare(elements)
    width = _positive_dots("width", width_dots)
    height = _positive_dots("height", height_dots)
    codewords = _encode_atoms(_atoms(prepared))
    modules = sum(_runs(codewords)) + 20
    usable = max(1, width - 80)
    module = max(1, min(3, usable // modules))
    bar_height = max(60, min(height // 5, 320))
    commands = [
        "^XA",
        f"^PW{width}",
        f"^LL{height}",
        f"^FO40,40^BY{module},2,{bar_height}^BCN,{bar_height},N,N,N,N^FD{_zpl_barcode(codewords)}^FS",
    ]
    text_y = 40 + bar_height + 28
    for line in _lines(prepared):
        commands.append(f"^FO40,{text_y}^A0N,28,28^FD{line}^FS")
        text_y += 36
    commands.append("^XZ")
    return "\n".join(commands)


def to_pdf(elements: Any) -> bytes:
    """A 4 by 6 inch PDF 1.4 page with filled bars and Helvetica HRI text."""
    prepared = _prepare(elements)
    codewords = _encode_atoms(_atoms(prepared))
    return _pdf_document(_pdf_stream(codewords, _lines(prepared)))

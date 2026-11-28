"""Synthetic X12 documents shared by the EDI line identity tests."""

from __future__ import annotations

TENANT = "00000000-0000-0000-0000-000000000123"
GTIN = "00012345678905"
_ISA = "ISA*00*          *00*          *ZZ*SENDERID       *ZZ*RECEIVERID     *260310*1200*U*00401*{isa13}*0*P*>~"


def _advice_set(lines: list[tuple[str, str]], st02: str, header: str, references: str = "") -> str:
    """One 945 transaction set, ST to SE."""
    body = [
        f"ST*945*{st02}~",
        header,
        references,
        "N1*WH*Cold Storage West*UL*6141410000014~",
        "N1*ST*Metro Distribution Center*UL*6141410000069~",
        "N1*DE*Valley Fresh Farms*92*VFF01~",
    ]
    for number, (quantity, lot) in enumerate(lines, start=1):
        body += [
            f"LX*{number}~",
            f"W12*CC*100*{quantity}**CA**UK*{GTIN}*{lot}~",
            "G69*Romaine Hearts 12ct~",
        ]
    body = [segment for segment in body if segment]
    body.append(f"SE*{len(body) + 1}*{st02}~")
    return "".join(body)


def _advice_interchange(sets: list[str], isa13: str, gs06: str) -> bytes:
    raw = (
        _ISA.format(isa13=isa13)
        + f"GS*SW*SENDERID*RECEIVERID*20260310*1200*{gs06}*X*004010~"
        + "".join(sets)
        + f"GE*{len(sets)}*{gs06}~IEA*1*{isa13}~"
    )
    return raw.encode("utf-8")


def shipping_advice(
    lines: list[tuple[str, str]],
    *,
    isa13: str = "000000201",
    gs06: str = "1",
    st02: str = "0001",
    header: str = "W06*N*ORD-5001*20260310*SHIP-9001~",
    references: str = "",
) -> bytes:
    """A 945 with one W12 per ``(units shipped, lot)``.

    The default header carries order ORD-5001 and shipment SHIP-9001. The
    event TLC of a line is the GTIN, a hyphen and its lot. Quantity ordered
    (W1202) is always 100, so a corrected shipped quantity changes no other KDE.
    """
    return _advice_interchange([_advice_set(lines, st02, header, references)], isa13, gs06)


def two_shipping_advices(
    first: list[tuple[str, str]], second: list[tuple[str, str]], *, isa13: str = "000000201", gs06: str = "1"
) -> bytes:
    """One interchange with two 945 sets: shipment SHIP-9001 (ST 0001), then SHIP-9002 (ST 0002)."""
    return _advice_interchange(
        [
            _advice_set(first, "0001", "W06*N*ORD-5001*20260310*SHIP-9001~"),
            _advice_set(second, "0002", "W06*N*ORD-5002*20260310*SHIP-9002~"),
        ],
        isa13,
        gs06,
    )


def ship_notice(lines: list[tuple[str, str, str]], *, isa13: str = "000000101") -> bytes:
    """An 856 (ASN-777) with one SN1 per ``(item id, quantity, lot)``."""
    body = [
        "ST*856*0001~",
        "BSN*00*ASN-777*20260310*1200~",
        "HL*1**S~",
        "N1*SF*Valley Fresh Farms*92*6141410000014~",
        "N1*ST*Metro Distribution Center*92*6141410000069~",
    ]
    for number, (item, quantity, lot) in enumerate(lines, start=2):
        body += [f"HL*{number}*1*I~", f"LIN**SK*{item}~", f"SN1**{quantity}*CA~", f"REF*LT*{lot}~"]
    body.append(f"SE*{len(body) + 1}*0001~")
    raw = (
        _ISA.format(isa13=isa13)
        + "GS*SH*SENDERID*RECEIVERID*20260310*1200*1*X*004010~"
        + "".join(body)
        + f"GE*1*1~IEA*1*{isa13}~"
    )
    return raw.encode("utf-8")

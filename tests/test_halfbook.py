from decimal import Decimal

import pytest

from src.backend.halfbook import Halfbook


def test_halfbook_bid():
    hb = Halfbook(is_bid=True)
    hb.set([["100", "10"], ["99", "5"], ["101", "15"]])
    assert hb.get() == [(Decimal("101"), "15"), (Decimal("100"), "10"), (Decimal("99"), "5")]
    assert hb.get_qty("100") == "10"
    assert hb.get_qty("102") == ""
    assert hb.top_n(2) == [(Decimal("101"), "15"), (Decimal("100"), "10")]
    hb.update("100", "20")
    assert hb.get_qty("100") == "20"
    hb.update("102", "25")
    hb.update("99.5", "25")
    hb.update("98", "20")
    assert hb.get() == [
        (Decimal("102"), "25"),
        (Decimal("101"), "15"),
        (Decimal("100"), "20"),
        (Decimal("99.5"), "25"),
        (Decimal("99"), "5"),
        (Decimal("98"), "20"),
    ]
    assert hb[0] == (Decimal("102"), "25")
    assert hb[1:3] == [(Decimal("101"), "15"), (Decimal("100"), "20")]
    hb.update("100", "0")
    assert hb.get() == [(Decimal("102"), "25"), (Decimal("101"), "15"), (Decimal("99.5"), "25"), (Decimal("99"), "5"), (Decimal("98"), "20")]


def test_halfbook_ask():
    hb = Halfbook(is_bid=False)
    hb.set([["100", "10"], ["99", "5"], ["101", "15"]])
    assert hb.get() == [(Decimal("99"), "5"), (Decimal("100"), "10"), (Decimal("101"), "15")]
    assert hb.get_qty("100") == "10"
    assert hb.get_qty("98") == ""
    assert hb.top_n(2) == [(Decimal("99"), "5"), (Decimal("100"), "10")]
    hb.update("100", "20")
    assert hb.get_qty("100") == "20"
    hb.update("99.5", "25")
    assert hb.get() == [(Decimal("99"), "5"), (Decimal("99.5"), "25"), (Decimal("100"), "20"), (Decimal("101"), "15")]
    assert hb[0] == (Decimal("99"), "5")
    assert hb[1:3] == [(Decimal("99.5"), "25"), (Decimal("100"), "20")]
    hb.update("100", "0")
    assert hb.get() == [(Decimal("99"), "5"), (Decimal("99.5"), "25"), (Decimal("101"), "15")]

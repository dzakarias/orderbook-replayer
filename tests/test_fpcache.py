import pytest
from src.backend.orderbook_traverser import FPCache


def test_get_no_values():
    cache = FPCache()
    assert cache.get(1) is None


def test_get():
    cache = FPCache()
    cache.add(1, 'value1')
    assert cache.get(1) == 'value1'
    assert cache.get(0) is None
    assert cache.get(2) == 'value1'


def test_get_largest_key_smaller_than():
    cache = FPCache()
    cache.add(1, 'value1')
    cache.add(3, 'value3')
    assert cache.get(2) == 'value1'
    assert cache.get(4) == 'value3'


def test_update():
    cache = FPCache()
    cache.add(1, 'value1')
    cache.add(1, 'value2')
    assert cache.get(1) == 'value1'


def test_copy():
    o = ['a', 11, 'b']
    cache = FPCache()
    cache.add(1, o)
    o[0] = 'c'
    cache.add(2, o)
    assert cache.get(1) == ['a', 11, 'b']
    assert cache.get(2) == ['c', 11, 'b']


def test_nested_object_copy():
    o = [[[['a', 11, 'b']]]]
    cache = FPCache()
    cache.add(1, o)
    o[0][0][0][0] = 'c'
    o.append('d')
    cache.add(2, o)
    o.append('e')
    assert cache.get(1) == [[[['a', 11, 'b']]]]
    assert cache.get(2) == [[[['c', 11, 'b']]], 'd']

import bisect
from decimal import Decimal


class Halfbook:
    def __init__(self, is_bid: bool):
        self.is_bid = is_bid
        self.halfbook = []
        if is_bid:
            self._sort_key = lambda x: -x[0]
        else:
            self._sort_key = lambda x: x[0]

    @classmethod
    def create(cls, halfbook: list[tuple[Decimal, str]], is_bid: bool, need_sort: bool = False) -> 'Halfbook':
        """
        Creates a new Halfbook using a copy of the given halfbook list.
        """
        hb = Halfbook(is_bid)
        if need_sort:
            hb.set_decimal(halfbook)
        else:
            hb.halfbook = halfbook[:]
        return hb

    def copy(self) -> 'Halfbook':
        return Halfbook.create(self.halfbook, self.is_bid, need_sort=False)

    def set(self, halfbook: list[list[str]]):
        """
        Sets up self.halfbook using given halfbook, that has prices in str format.
        Assumes given halfbook is not sorted.
        """
        self.halfbook = sorted([(Decimal(price), size) for price, size in halfbook], key=self._sort_key)

    def set_decimal(self, halfbook: list[tuple[Decimal, str]]):
        """
        Sets up self.halfbook using given halfbook, that has prices in Decimal format.
        Assumes given halfbook is not sorted.
        """
        self.halfbook = sorted([(price, size) for price, size in halfbook], key=self._sort_key)

    def get(self) -> list[tuple[Decimal, str]]:
        return self.halfbook

    def _get_idx(self, price: str) -> int:
        search_key = Decimal(price) if not self.is_bid else -Decimal(price)
        return bisect.bisect_left(self.halfbook, search_key, key=self._sort_key)

    def get_qty(self, price: str) -> str:
        """
        Returns the qty as str for price. Empty string if not found
        """
        index = self._get_idx(price)

        if index < len(self.halfbook) and self.halfbook[index][0] == Decimal(price):
            return self.halfbook[index][1]
        return ''

    def get_qty_decimal(self, price: Decimal):
        """
        Returns the qty as str for price. Empty string if not found.
        Price should be Decimal.
        """
        search_key = price if not self.is_bid else -price
        index = bisect.bisect_left(self.halfbook, search_key, key=self._sort_key)

        if index < len(self.halfbook) and self.halfbook[index][0] == price:
            return self.halfbook[index][1]
        return ''

    def top_n(self, n: int) -> list[tuple[Decimal, str]]:
        """
        Returns the top n bids/asks.
        """
        return self.halfbook[:n]

    def update(self, price: str, qty: str):
        price_decimal = Decimal(price)
        index = self._get_idx(price)
        if index < len(self.halfbook) and self.halfbook[index][0] == price_decimal:
            # Update existing entry
            if Decimal(qty):
                self.halfbook[index] = (price_decimal, qty)
            else:
                del self.halfbook[index]

        else:
            # Insert new entry
            bisect.insort(self.halfbook, (price_decimal, qty), key=self._sort_key)

    def __getitem__(self, i):
        return self.halfbook[i]

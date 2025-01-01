from copy import copy
from dataclasses import dataclass
from datetime import timezone

import pandas as pd


def _max_significant_decimal_places(float_list: list[float]):
    max_decimals = 0
    for number in float_list:
        str_number = str(number)

        # Split the string at the decimal point
        if '.' in str_number:
            decimal_part = str_number.split('.')[1]
            # Count the number of digits in the decimal part
            num_decimals = len(decimal_part)
            max_decimals = max(max_decimals, num_decimals)
    return max_decimals


@dataclass
class OrderBook:
    symbol: str
    asks: list[tuple[float, float]]  # price, volume
    bids: list[tuple[float, float]]  # price, volume
    timestamp: int  # unix timestamp in milliseconds

    @property
    def best_bid(self) -> float | None:
        return self.bids[0][0] if self.bids else None

    @property
    def best_ask(self) -> float | None:
        return self.asks[-1][0] if self.asks else None

    @property
    def bid_volume(self) -> float | None:
        return self.bids[0][1] if self.bids else None

    @property
    def ask_volume(self) -> float | None:
        return self.asks[-1][1] if self.asks else None

    @property
    def midprice(self) -> float | None:
        try:
            return (self.best_ask + self.best_bid) / 2
        except:
            return None

    @property
    def spread(self) -> float:
        """best_ask - best_bid"""
        return self.best_ask - self.best_bid

    @property
    def spread_bp(self) -> float:
        """Bid-ask spread ratio in basis points"""
        return self.spread / self.midprice * 10_000.0

    @classmethod
    def copy(cls, other: 'OrderBook') -> 'OrderBook':
        # A shallow copy works as even though asks and bids hold objects, but those objects are tuples that cannot be modified (just replaced,
        # which does not break the shallow copy).
        # The reason why this isn't a member function, but a class method, is because ob.copy() would require the caller to do a None-check.
        return copy(other)

    def _avg_price(self, qty: float, halfbook: list[tuple[float, float]]) -> float:
        if not halfbook[0][0] or qty <= 0.0:
            return 0.0

        avg_price = filled_qty = 0.0
        filled = False

        for price, qty_available in halfbook:
            if not qty_available:
                continue
            if filled_qty + qty_available >= qty:
                qty_available = qty - filled_qty
                filled = True

            avg_price = (price * qty_available + avg_price * filled_qty) / (filled_qty + qty_available)
            filled_qty += qty_available

            if filled:
                return avg_price
        return avg_price

    def avg_buy_price(self, qty: float) -> float:
        """
        Returns the qty-weighted average price for buying the specified quantity based on the orderbook.
        """
        return self._avg_price(qty, self.asks[::-1])

    def avg_sell_price(self, qty: float) -> float:
        """
        Returns the qty-weighted average price for a selling the specified qty based on the orderbook.
        """
        return self._avg_price(qty, self.bids)

    @staticmethod
    def calculate_maximum_trade_qty(
        orderbook_buy: "OrderBook",
        orderbook_sell: "OrderBook",
        minimum_profit_bps: float,
        buy_fee_rate: float,
        sell_fee_rate: float,
        buy_exchange_rate: float = 1.0,
        sell_exchange_rate: float = 1.0,
    ) -> float:
        assert buy_exchange_rate and sell_exchange_rate, 'Exchange rates cannot be zero!'
        total_qty = 0
        total_buy_value = 0
        total_sell_value = 0

        # Start from the end of asks (lowest price) in buy orderbook
        buy_index = len(orderbook_buy.asks) - 1

        # Start from the beginning of bids (highest price) in sell orderbook
        sell_index = 0

        buy_price, buy_qty_remaining = orderbook_buy.asks[buy_index]
        sell_price, sell_qty_remaining = orderbook_sell.bids[sell_index]
        buy_price *= buy_exchange_rate  # buy price in "main" settle coin
        sell_price *= sell_exchange_rate  # sell price in "main" settle coin

        while True:
            trade_qty = min(buy_qty_remaining, sell_qty_remaining)

            new_total_qty = total_qty + trade_qty
            new_total_buy_value = total_buy_value + (trade_qty * buy_price * (1 + buy_fee_rate))
            new_total_sell_value = total_sell_value + (trade_qty * sell_price * (1 - sell_fee_rate))

            if new_total_qty > 0:
                avg_buy_price_with_fees = new_total_buy_value / new_total_qty
                avg_sell_price_with_fees = new_total_sell_value / new_total_qty
                net_unit_profit = avg_sell_price_with_fees - avg_buy_price_with_fees
                current_profit_bps = 100 * 100 * net_unit_profit / (avg_buy_price_with_fees + avg_sell_price_with_fees)

                if current_profit_bps < minimum_profit_bps:
                    break

                total_qty = new_total_qty
                total_buy_value = new_total_buy_value
                total_sell_value = new_total_sell_value

            buy_qty_remaining -= trade_qty
            sell_qty_remaining -= trade_qty

            if buy_qty_remaining == 0:
                buy_index -= 1  # Move to the next higher ask price in buy orderbook
                if buy_index < 0:
                    break
                buy_price, buy_qty_remaining = orderbook_buy.asks[buy_index]
                buy_price *= buy_exchange_rate

            if sell_qty_remaining == 0:
                sell_index += 1  # Move to the next lower bid price in sell orderbook
                if sell_index >= len(orderbook_sell.bids):
                    break
                sell_price, sell_qty_remaining = orderbook_sell.bids[sell_index]
                sell_price *= sell_exchange_rate

        return total_qty

    def str(self, depth: int = 0, low_qty_filter: float = 0.0) -> str:
        """Returns an ASCII visualization of the orderbook."""
        if not self.best_bid or not self.best_ask:
            return f'{self.symbol}: No orderbook'

        # Constants for graph appearance
        ROW_LEN = 60
        MAX_BAR_WIDTH = 30
        BID_CHAR = "◼"
        ASK_CHAR = "◻"

        if not depth:
            depth = max(len(self.asks), len(self.bids))

        # Combine bids and asks, and find the maximum quantity
        all_orders = self.bids[:depth] + self.asks[-depth:]
        qtys = [qty for _, qty in all_orders]
        max_qty = max(qtys)
        qty_sum = sum(qtys)

        # Calculate the scale factor for quantity representation
        scale = MAX_BAR_WIDTH / max_qty if max_qty > 0 else 1

        price_decimals = _max_significant_decimal_places([o[0] for o in all_orders])
        qty_decimals = min(5, _max_significant_decimal_places([o[1] for o in all_orders]))
        price_fmt = f'<12.{price_decimals}f'
        qty_fmt = f'>12.{qty_decimals}f'

        # Generate the graph
        ts_str = pd.Timestamp(self.timestamp, unit='ms').tz_localize(timezone.utc).strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
        graph = [f"Orderbook for {self.symbol} at {ts_str}"]
        graph.append("=" * ROW_LEN)
        graph.append(f"{'Price':^12} {'Qty':^12} {'Qty Bar':^{MAX_BAR_WIDTH}}")
        graph.append("=" * ROW_LEN)

        bids_cnt = 0
        ask_graph = []  # we cannot directly append to graph list, because we want the last depth elements not the first depth elements
        for price, qty in self.asks:
            if not low_qty_filter or qty > low_qty_filter * qty_sum:
                bar = ASK_CHAR * int(qty * scale)
                ask_graph.append(f"{price:{price_fmt}} {qty:{qty_fmt}} {bar:<{MAX_BAR_WIDTH}}")
        graph.extend(ask_graph[-depth:])

        graph.append(f'{"=" * 5}{self.midprice:{f"^12.{price_decimals}f"}}{"=" * (ROW_LEN-12-5)}')

        for price, qty in self.bids:
            if not low_qty_filter or qty > low_qty_filter * qty_sum:
                bar = BID_CHAR * int(qty * scale)
                # can directly append: for bids the first depth elements is what we want
                graph.append(f"{price:{price_fmt}} {qty:{qty_fmt}} {bar:<{MAX_BAR_WIDTH}}")
                bids_cnt += 1
            if bids_cnt == depth:
                break

        graph.append("=" * ROW_LEN)
        return "\n".join(graph)

    def __str__(self) -> str:
        return self.str()

    def slippage_ratio_and_best_price(self, value_to_skip: float, asks: bool) -> tuple[float, float]:
        half_book = self.asks[::-1] if asks else self.bids
        midprice = self.midprice
        last_price = half_book[0][0]

        for price, volume in half_book:
            if value_to_skip <= 0:
                break
            value_to_skip -= price * volume
            last_price = price
        return abs(midprice - last_price) / midprice, last_price

    def weighted_bid_ask(self, value_to_fill_per_side: float) -> list[float]:
        """
        Returns the weighted average price for filling value_to_fill_per_side on each side of the orderbook,
        avg. bid is returned first.
        """
        res = []
        for half_book in [self.bids, self.asks[::-1]]:
            remaining_value = value_to_fill_per_side
            filled_qty = 0.0
            for price, volume in half_book:
                if remaining_value <= 0:
                    break
                filled_qty += min(remaining_value / price, volume)
                remaining_value -= price * volume
            filled_value = min(value_to_fill_per_side, value_to_fill_per_side - remaining_value)
            if filled_qty:
                res.append(filled_value / filled_qty)
            else:
                res.append(0.0)
        return res

    def exclude_oo(self, oo: pd.DataFrame) -> 'OrderBook':
        """
        Returns this orderbook minus the open orders in oo
        """
        res = OrderBook(self.symbol, [], [], self.timestamp)
        longs = oo.query('side == "Buy"')
        for i in range(len(self.bids)):
            bid_price = self.bids[i][0]
            if bid_price in longs['price'].values:
                oo_qty = longs.query('price == @bid_price')['remaining_qty'].values[0]
                res.bids.append((bid_price, max(0.0, self.bids[i][1] - oo_qty)))
            else:
                res.bids.append(self.bids[i])

        shorts = oo.query('side == "Sell"')
        for i in range(len(self.asks)):
            ask_price = self.asks[i][0]
            if ask_price in shorts['price'].values:
                oo_qty = shorts.query('price == @ask_price')['remaining_qty'].values[0]
                res.asks.append((ask_price, max(0.0, self.asks[i][1] - oo_qty)))
            else:
                res.asks.append(self.asks[i])

        return res

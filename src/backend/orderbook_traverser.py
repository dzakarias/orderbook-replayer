import os.path
from copy import deepcopy
from typing import Optional, Callable
from decimal import Decimal
import json
from dataclasses import dataclass
from sortedcontainers import SortedDict

from .orderbook import OrderBook


@dataclass
class OrderbookState:
    bids: list[list[str]]  # [[price, size], ...]
    asks: list[list[str]]  # [[price, size], ...]
    timestamp: int
    sequence: int


@dataclass
class PriceRange:
    lowest_ask: Decimal
    highest_bid: Decimal
    start_time: int
    end_time: int


class FPCache:
    """
    A simple integer key -> any value mapping with sorted keys.
    """

    def __init__(self):
        self.cache = SortedDict()

    def add(self, key: int, value) -> None:
        """
        Adds a new key-value pair if key is not already present
        """
        if key in self.cache:
            return
        self.cache[key] = value

    def get(self, key: int):
        """
        Returns the value associated with the given key, if key is present.
        Otherwise the value associated with the smallest key larger than input key, or None if we do not have any values.
        If smallest_larger_mode is False, the largest key smaller than input will be returned
        """
        idx = self.cache.bisect_left(key)
        if idx < len(self.cache):
            return self.cache.peekitem(index=idx)[1]
        if len(self.cache):
            return self.cache.peekitem(index=idx - 1)[1]
        return None


class OrderbookTraverser:
    def __init__(self, symbol: str, filename: str, cache_frequency_seconds: int = 10):
        """
        Initialize the traverser with a file containing compressed orderbook data.
        cache_frequency_seconds: while processing, cache orderbooks this many seconds apart
        """
        assert os.path.exists(filename), f'Orderbook not found at {filename}'

        self.symbol = symbol
        self.filename = filename
        self.cache_frequency_seconds = cache_frequency_seconds
        self.current_position = 0  # File position
        self.current_state: Optional[OrderbookState] = None
        self.current_timestamp = 0  # Logical timestamp, greater or equal to the current orderbook. Smaller than the next delta's timestamp.

        # Create cache and load initial snapshot
        self.obs_cache = FPCache()
        self._load_initial_snapshot()

    def _load_initial_snapshot(self):
        """
        Load the initial snapshot and store its position
        """
        with open(self.filename, 'r') as f:
            first_line = f.readline()
            data = json.loads(first_line)

            self.current_state = OrderbookState(bids=data['b'], asks=data['a'], timestamp=data['t'], sequence=data['s'])
            self.current_timestamp = self.current_state.timestamp

            self.current_position = f.tell()
            self._add_to_cache()

    def _process_update(self, data: dict):
        """
        Processes a single update and updates current state
        """
        # Update bids if present in delta
        if 'b' in data:
            current_bids = {price: size for price, size in self.current_state.bids}
            for price, size in data['b']:
                if Decimal(size) == 0:
                    current_bids.pop(price, None)
                else:
                    current_bids[price] = size

            # Sort descending
            sorted_bids = sorted(((Decimal(price), price, size) for price, size in current_bids.items()), reverse=True)
            new_bids = [[str(price), size] for _, price, size in sorted_bids]
        else:
            new_bids = self.current_state.bids

        # Update asks if present in delta
        if 'a' in data:
            current_asks = {price: size for price, size in self.current_state.asks}
            for price, size in data['a']:
                if Decimal(size) == 0:
                    current_asks.pop(price, None)
                else:
                    current_asks[price] = size

            # Sort ascending
            sorted_asks = sorted(((Decimal(price), price, size) for price, size in current_asks.items()))
            new_asks = [[str(price), size] for _, price, size in sorted_asks]
        else:
            new_asks = self.current_state.asks

        self.current_state = OrderbookState(bids=new_bids, asks=new_asks, timestamp=data['t'], sequence=data['s'])
        # print(self.current_state)

    def get(self) -> OrderbookState:
        """
        Returns current orderbook state
        """
        return self.current_state

    def get_orderbook(self) -> OrderBook:
        """
        Converts current state to OrderBook object with float values
        """
        return OrderBook(
            symbol=self.symbol,
            asks=[(float(price), float(size)) for price, size in self.current_state.asks[::-1]],
            bids=[(float(price), float(size)) for price, size in self.current_state.bids],
            timestamp=self.current_timestamp,
        )

    def get_best_bid(self) -> Decimal | None:
        """
        Gets the current best bid price
        """
        if self.current_state.bids:
            return Decimal(self.current_state.bids[0][0])
        return None

    def get_best_ask(self) -> Decimal | None:
        """
        Gets the current best ask price
        """
        if self.current_state.asks:
            return Decimal(self.current_state.asks[0][0])
        return None

    def _add_to_cache(self) -> None:
        """
        Adds the current book to the cache
        """
        self.obs_cache.add(self.current_state.timestamp, (deepcopy(self.current_state), self.current_position))
        self.last_cached_ts = self.current_state.timestamp

    def _add_to_cache_if_needed(self) -> None:
        """
        Adds the current book to the cache if the last cached book was more than self.cache_frequency_seconds ago
        """
        if self.current_state.timestamp - self.last_cached_ts > self.cache_frequency_seconds * 1000:
            self._add_to_cache()

    def _read_from_current(self, post_iteration_hook: Callable[[dict, dict], bool], hook_ctx: dict) -> None:
        """
        Reads deltas from the current position. Terminates when post_iteration_hook returns True
        Updates state, saves current position, updates cache on every complete (not terminated) iteration.
        post_iteration_hook's parameters:
          - hook_ctx (a dict, initialized to empty dict),
          - current delta loaded from disk
        """
        with open(self.filename, 'r') as f:
            f.seek(self.current_position)
            while True:
                line = f.readline()
                if not line:  # EOF
                    break
                data = json.loads(line)
                terminate = post_iteration_hook(hook_ctx, data)
                if terminate:
                    break

                self._process_update(data)
                self.current_position = f.tell()

                # Update cache
                self._add_to_cache_if_needed()

    def skip(self, seconds: float) -> None:
        """
        Skips forward by specified number of seconds (or backward if seconds < 0).
        Moves relative to self.current_timestamp, then updates self.current_timestamp.
        """
        target_time = int(self.current_timestamp + (seconds * 1000))  # Convert to milliseconds

        res = self.obs_cache.get(target_time)
        if res:
            self.current_state, self.current_position = res
            if self.current_state.timestamp == target_time:
                # we're exactly where we want to be
                return

        self._read_from_current(post_iteration_hook=lambda hook_ctx, data: data['t'] > target_time, hook_ctx={})
        self.current_timestamp = target_time

    def move(self, seconds: float) -> PriceRange:
        """
        Moves forward by specified number of seconds and tracks price ranges.
        Moves relative to self.current_timestamp, then updates self.current_timestamp.
        seconds has to be positive.

        Returns the price range observed.
        """
        assert seconds > 0, 'Move only accepts positive intervals!'
        start_time = self.current_timestamp
        # we cannot use the cache here as we need to collect maximum and minimum values

        def record_extremes_until_target(_hook_ctx: dict, _data: dict) -> bool:
            _hook_ctx['lowest_ask'] = min(_hook_ctx['lowest_ask'], self.get_best_ask())
            _hook_ctx['highest_bid'] = max(_hook_ctx['highest_bid'], self.get_best_bid())

            return _data['t'] > _hook_ctx['target_time']

        hook_ctx = {
            'lowest_ask': self.get_best_ask(),
            'highest_bid': self.get_best_bid(),
            'target_time': self.current_state.timestamp + (seconds * 1000),
        }
        self._read_from_current(post_iteration_hook=record_extremes_until_target, hook_ctx=hook_ctx)
        self.current_timestamp = int(hook_ctx['target_time'])

        return PriceRange(
            lowest_ask=hook_ctx['lowest_ask'], highest_bid=hook_ctx['highest_bid'], start_time=start_time, end_time=self.current_timestamp
        )

    def at(self, timestamp: int) -> None:
        """
        Skips to the earliest orderbook at or after input timestamp.
        """
        self.skip((timestamp - self.current_state.timestamp) // 1000)

    def step(self) -> None:
        """
        Moves one set of deltas ahead (deltas with the same timestamp are in one set)
        """

        def terminate_on_different_ts(hook_ctx: dict, data: dict) -> bool:
            if 'current_ts' not in hook_ctx:
                hook_ctx['current_ts'] = data['t']
            elif data['t'] > hook_ctx['current_ts']:
                return True
            return False

        self._read_from_current(post_iteration_hook=terminate_on_different_ts, hook_ctx={})
        self.current_timestamp = self.current_state.timestamp

    def reset(self):
        """
        Resets to initial state (the first available orderbook)
        """
        self._load_initial_snapshot()

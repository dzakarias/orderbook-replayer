import json
from decimal import Decimal

import argparse
from line_profiler import LineProfiler

from halfbook import Halfbook


ENABLE_PROFILING = False

lp = LineProfiler()


def conditional_profile(enable_profiling):
    def decorator(func):
        if enable_profiling:
            return lp(func)
        return func

    return decorator


@conditional_profile(ENABLE_PROFILING)
def _calculate_deltas(new_halfbook: list[tuple[Decimal, str]], old_halfbook: list[tuple[Decimal, str]], is_bid: bool) -> list[list[str]]:
    """
    Calculate the minimal set of deltas needed to update from previous top levels to new top levels
    """
    changes = []
    new_levels = set(price for price, _ in new_halfbook)
    old_levels = set(price for price, _ in old_halfbook)

    added_price_levels = new_levels - old_levels
    removed_price_levels = old_levels - new_levels

    # create a Halfbook for convenient and fast qty lookups
    old_hb_object = Halfbook.create(old_halfbook, is_bid, need_sort=False)

    # Add all new/modified levels
    for price, qty in new_halfbook:
        if price in removed_price_levels:
            continue
        if price in added_price_levels:
            changes.append([str(price), qty])
        else:
            old_qty = old_hb_object.get_qty_decimal(price)
            if not old_qty or old_qty != qty:
                changes.append([str(price), qty])

    # Add removals for old top levels that are no longer present
    changes.extend([[str(removed_price), "0"] for removed_price in removed_price_levels])

    return changes


def _update_halfbook(halfbook: Halfbook, updates: list[tuple[str, str]]):
    """
    Update the asks/bids state
    """
    for update in updates:
        price, qty = update
        halfbook.update(price=price, qty=qty)


class OrderbookProcessor:
    def __init__(self, max_output_depth: int = 20):
        """ """
        # Store all levels internally
        self.bids = Halfbook(is_bid=True)
        self.asks = Halfbook(is_bid=False)
        self.max_output_depth = max_output_depth
        self.first_message = True

    @conditional_profile(ENABLE_PROFILING)
    def process_message(self, message: dict) -> dict:
        """
        Process a single message (snapshot or delta) and return compressed version, i.e. either the snapshot, or the minimal set of
        deltas required to accurately reconstruct any future state.
        """
        msg_type = message['type']
        data = message['data']
        timestamp = message['ts']

        compressed_deltas = {}
        if not self.first_message:
            # Update full book
            if data['b']:
                new_bids = self.bids.copy()
                _update_halfbook(new_bids, data['b'])
                bid_deltas = _calculate_deltas(new_bids[: self.max_output_depth], self.bids[: self.max_output_depth], is_bid=True)
                self.bids = new_bids
            else:
                bid_deltas = None
            if data['a']:
                new_asks = self.asks.copy()
                _update_halfbook(new_asks, data['a'])
                ask_deltas = _calculate_deltas(new_asks[: self.max_output_depth], self.asks[: self.max_output_depth], is_bid=False)
                self.asks = new_asks
            else:
                ask_deltas = None

            if bid_deltas or ask_deltas:
                compressed_deltas = {'t': timestamp, 's': data['seq']}

                if bid_deltas:
                    compressed_deltas['b'] = bid_deltas
                if ask_deltas:
                    compressed_deltas['a'] = ask_deltas
        else:
            if msg_type != 'snapshot':
                raise ValueError("First message must be a snapshot")

            # Store full book
            self.bids.set(data['b'])
            self.asks.set(data['a'])

            # Get initial top levels
            top_bids = self.bids[: self.max_output_depth]
            top_asks = self.asks[: self.max_output_depth]

            compressed_deltas = {
                't': timestamp,
                'b': [[str(price), size] for price, size in top_bids],  # output all levels, they may be needed to reconstruct future states
                'a': [[str(price), size] for price, size in top_asks],  # output all levels, they may be needed to reconstruct future states
                's': data['seq'],
            }

            self.first_message = False
        return compressed_deltas


def process_orderbook_file(input_file: str, max_levels: int = 20):
    """
    Process an entire orderbook file and write compressed output
    """
    processor = OrderbookProcessor(max_output_depth=max_levels)
    output_file = input_file.replace('ob500', f'ob{max_levels}')

    with open(input_file, 'r') as f_in, open(output_file, 'w') as f_out:
        out_strings = []
        for line_nr, line in enumerate(f_in):
            message = json.loads(line.strip())
            compressed = processor.process_message(message)
            if compressed:
                out_strings.append(json.dumps(compressed))
            if not line_nr % 10000:
                f_out.write('\n'.join(out_strings))
                f_out.write('\n')
                out_strings.clear()
                print('.', end='')
        if out_strings:
            f_out.write('\n'.join(out_strings))
            f_out.write('\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Bybit orderbook history compressor')
    parser.add_argument('-f', '--file', help='Path of the input file (as downloaded from Bybit)', required=True)
    parser.add_argument('-d', '--depth', help='Maximum depth of output orderbook history, default: 20', type=int, default=20)
    args = parser.parse_args()

    process_orderbook_file(args.file, max_levels=args.depth)
    if ENABLE_PROFILING:
        lp.print_stats()

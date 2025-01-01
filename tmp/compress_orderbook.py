import asyncio
import json
from typing import Callable, TextIO

import aiofiles
import argparse

from orderbook_processor import OrderbookProcessor

CHUNK_LINE_CNT = 10000


async def producer(queue: asyncio.Queue, file_path: str):
    """Asynchronously read a file line by line and put lines into the queue."""
    async with aiofiles.open(file_path, 'r') as f:
        lines = []
        i = 0
        async for line in f:
            i += 1
            lines.append(line)
            if i % CHUNK_LINE_CNT == 0:
                await queue.put(lines)
                lines = []  # create a new list every time, lines.clear() would mess up the consumer!
    await queue.put(None)  # Signal that the producer is done


async def consumer(queue: asyncio.Queue, infile_path: str, process_fn: Callable[[OrderbookProcessor, str], str], max_levels: int):
    """Asynchronously process lines from the queue."""
    processor = OrderbookProcessor(max_output_depth=max_levels)
    output_filepath = infile_path.replace('ob500', f'ob{max_levels}')
    async with aiofiles.open(output_filepath, 'w') as f_out:
        while True:
            lines = await queue.get()
            if lines is None:  # Check for the end signal
                queue.task_done()
                break
            # Process the lines
            results = []
            for line in lines:
                res = process_fn(processor, line)
                if res:
                    results.append(res)
            if results:
                await f_out.write('\n'.join(results))
                await f_out.write('\n')
            print('.', end='')
            queue.task_done()


def process_line(processor: OrderbookProcessor, line: str) -> str:
    message = json.loads(line.strip())
    try:
        compressed = processor.process_message(message)
        if compressed:
            return f'{json.dumps(compressed)}'
    except Exception as e:
        print(f'Failed to process line {line}: {repr(e)}')
    return ''


async def main(file_path: str, max_levels: int):
    queue = asyncio.Queue()
    prod = asyncio.create_task(producer(queue, file_path))
    cons = asyncio.create_task(consumer(queue, file_path, process_fn=process_line, max_levels=max_levels))

    print('Started producer and consumer.')
    await prod
    print('Waiting for all queue items to be processed...')
    await queue.join()  # Wait for all items in the queue to be processed
    print('Cancelling consumer...')
    cons.cancel()  # Cancel the consumer task
    print('Done')


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Bybit orderbook history compressor')
    parser.add_argument('-f', '--file', help='Path of the input file (as downloaded from Bybit)', required=True)
    parser.add_argument('-d', '--depth', help='Maximum depth of output orderbook history, default: 20', type=int, default=20)
    args = parser.parse_args()

    asyncio.run(main(args.file, args.depth))

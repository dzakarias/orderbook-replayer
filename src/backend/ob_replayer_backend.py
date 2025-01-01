import datetime
import os
from typing import List, Tuple

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

from .orderbook import OrderBook
from .orderbook_traverser import OrderbookTraverser
from .helpers.logger import log, set_logfile

app = FastAPI(title="Order Book History Viewer")
# Mount the frontend directory
app.mount("/src/frontend", StaticFiles(directory="src/frontend"), name="frontend")

set_logfile('ob_replay_backend')

# Add CORS middleware to allow frontend communication
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


class Market(BaseModel):
    symbol: str
    date_: datetime.date


class OrderBookResponse(BaseModel):
    symbol: str
    asks: List[Tuple[float, float]]
    bids: List[Tuple[float, float]]
    timestamp: int


class OrderBookService:
    def __init__(self):
        self.current_history: OrderbookTraverser | None = None
        self.current_symbol: str | None = None
        self.current_date: datetime.date | None = None

    def _assert_history(self):
        if not self.current_history:
            raise HTTPException(status_code=400, detail="No market selected")

    def available_markets(self, date_: datetime.date) -> List[str]:
        data_dir = './orderbooks'
        os.makedirs(data_dir, exist_ok=True)
        return [f.split('_')[1] for f in os.listdir(data_dir) if date_.strftime('%Y-%m-%d') in f and f.endswith('.data')]

    def select_market(self, symbol: str, date_: datetime.date):
        filename = f'./orderbooks/{date_.strftime("%Y-%m-%d")}_{symbol}_ob20.data'
        if not os.path.exists(filename):
            raise HTTPException(status_code=404, detail="Market data not found")

        self.current_history = OrderbookTraverser(symbol=symbol, filename=filename)
        self.current_symbol = symbol
        self.current_date = date_

    def step(self) -> OrderBook:
        self._assert_history()

        self.current_history.step()
        return self.current_history.get_orderbook()

    def skip(self, delta: float) -> OrderBook:
        self._assert_history()

        self.current_history.skip(delta)
        return self.current_history.get_orderbook()

    def reset(self) -> OrderBook:
        self._assert_history()

        self.current_history.reset()
        return self.current_history.get_orderbook()

    def goto(self, dt: datetime.datetime) -> OrderBook:
        self._assert_history()

        timestamp = int(dt.timestamp() * 1000)
        self.current_history.at(timestamp)
        return self.current_history.get_orderbook()


order_book_service = OrderBookService()


# Custom middleware to log requests
@app.middleware("http")
async def log_requests(request: Request, call_next):
    try:
        request_body = await request.json()
        log(f"Request: {request.method} {request.url} {request_body}")
    except Exception as e:
        log(f"Request: {request.method} {request.url}")
    response = await call_next(request)
    log(f"Response status: {response.status_code}")
    return response


@app.get("/markets", response_model=List[str])
def get_available_markets(date_: datetime.date = datetime.date.today()):
    return order_book_service.available_markets(date_)


@app.post("/select_market")
def select_market(market: Market):
    log(f'Selected symbol: {market.symbol}, date: {market.date_}')
    order_book_service.select_market(market.symbol, market.date_)
    return {"message": f"Selected market {market.symbol} for {market.date_}"}


@app.get("/step", response_model=OrderBookResponse)
def get_next_orderbook():
    orderbook = order_book_service.step()
    return OrderBookResponse(**orderbook.__dict__)


@app.post("/skip")
def skip_orderbook(req: dict):
    try:
        interval = float(req["seconds"])
        orderbook = order_book_service.skip(interval)
        return OrderBookResponse(**orderbook.__dict__)
    except Exception as e:
        log(f"Error in /skip endpoint: {e}")
        raise HTTPException(status_code=422, detail=str(e))


@app.get("/reset")
def reset():
    orderbook = order_book_service.reset()
    return OrderBookResponse(**orderbook.__dict__)


@app.post("/goto")
def goto_timestamp(req: dict):
    timestamp = float(req['timestamp'])
    dt = datetime.datetime.fromtimestamp(timestamp / 1000.0)
    orderbook = order_book_service.goto(dt)
    return OrderBookResponse(**orderbook.__dict__)


# Serve index.html as the default page
@app.get("/")
async def serve_index():
    return FileResponse("src/frontend/index.html")

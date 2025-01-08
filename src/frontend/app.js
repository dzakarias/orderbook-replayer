const { createApp, ref, computed, onMounted, reactive } = Vue;

// API Service abstraction
const createApiService = () => {
    const baseUrl = '';
    
    const get = async (endpoint, params = {}) => {
        try {
            const response = await axios.get(`${baseUrl}${endpoint}`, {params});
            return response.data;
        } catch (error) {
            console.error(endpoint, 'API Error:', error);
            throw error;
        }
    };

    const post = async (endpoint, data = {}) => {
        try {
            const response = await axios.post(`${baseUrl}${endpoint}`, data);
            return response.data;
        } catch (error) {
            console.error(endpoint, 'API Error:', error);
            throw error;
        }
    };

    return {
        getMarkets: (date) => get('/markets', { date_: date }),
        selectMarket: (symbol, date) => post('/select_market', { symbol: symbol, date_: date }),
        stepForward: () => get('/step'),
        skip: (seconds) => post('/skip', { seconds }),
        goto: (timestamp) => post('/goto', { timestamp }),
        reset: () => get('/reset')
    };
};

const app = Vue.createApp({
    setup() {
        const api = createApiService();
        
        // Reactive state
        const state = reactive({
            selectedDate: new Date().toISOString().split('T')[0],
            selectedTime: new Date().toLocaleTimeString([], {hour: '2-digit', minute:'2-digit', second:'2-digit', hour12: false}),
            selectedMarket: '',
            markets: [],
            orderBook: { bids: [], asks: [] },
            replaySpeed: 2,
            replayStepSize: 2,
            replayInterval: null,
            previousOrderBook: { bids: [], asks: [] },
            skipping: false
        });

        const dates = computed(() => {
            return Array.from({ length: 7 }, (_, i) => {
                const d = new Date();
                d.setDate(d.getDate() - i);
                return d.toISOString().split('T')[0];
            });
        });

        const orderbookLabel = computed(() => {
            if (state.skipping) {
                return `Moving to ${state.selectedTime} ...`;
            } else if (state.selectedMarket == null) {
                return "Select a market/date first";
            } else {
                date_ = state.orderBook?.timestamp ? new Date(state.orderBook?.timestamp) : null;
                return `${state.selectedMarket} Orderbook at ${date_ ? getFormattedTime(date_) : '-'}`;
            }
        });

        // Order Book Utilities
        const formatDecimal = (value, maxDecimals) => Number(value).toFixed(maxDecimals);
        
        const calculateMaxDecimals = (tuples, index) => {
            return Math.max(...tuples.map(tuple => {
                const str = tuple[index].toString();
                const decimalIndex = str.indexOf('.');
                return decimalIndex === -1 ? 0 : str.length - decimalIndex - 1;
            }));
        };

        const formatTuples = (tuples) => {
            if (!tuples.length) return tuples;
            
            const maxPriceDecimals = calculateMaxDecimals(tuples, 0);
            const maxQtyDecimals = calculateMaxDecimals(tuples, 1);
            
            return tuples.map(tuple => [
                formatDecimal(tuple[0], maxPriceDecimals),
                formatDecimal(tuple[1], maxQtyDecimals)
            ]);
        };

        const updateOrderBook = (responseData, updatePrevious = true) => {
            if (updatePrevious) {
                state.previousOrderBook = { ...state.orderBook };
            }
            state.orderBook = {
                ...responseData,
                bids: formatTuples(responseData.bids),
                asks: formatTuples(responseData.asks)
            };
        };

        // Market Operations
        const fetchMarkets = async () => {
            try {
                // Ensure we have a valid date string
                const date = state.selectedDate;
                const markets = await api.getMarkets(date);
                // Ensure we have an array of market symbols
                state.markets = Array.isArray(markets) ? markets : [];
                
                if (state.markets.length > 0) {
                    // Select first market by default
                    state.selectedMarket = state.markets[0];
                    await selectMarket();
                } else {
                    state.selectedMarket = '';
                    state.orderBook = { bids: [], asks: [] };
                }
            } catch (error) {
                console.error('Failed to fetch markets:', error);
                state.markets = [];
                state.selectedMarket = '';
                state.orderBook = { bids: [], asks: [] };
            }
        };

        const selectMarket = async () => {
            try {
                await api.selectMarket(state.selectedMarket, state.selectedDate);
                await stepForward();
            } catch (error) {
                console.error(`No such market: ${state.selectedMarket} ${state.selectedDate}`);
            }
        };

        // Order Book Operations
        const stepForward = async () => {
            stopReplay();
            const data = await api.stepForward();
            updateOrderBook(data);
        };

        const skip = async (seconds) => {
            const data = await api.skip(seconds);
            updateOrderBook(data);
        };

        const skipForward = async() => {
            stopReplay();
            skip(state.replayStepSize);

        };

        const skipBackward = async() => {
            stopReplay();
            skip(-state.replayStepSize);
        };

        const skipTo = async () => {
            state.skipping = true;
            try {
                stopReplay();
                
                const targetDateTime = new Date(`${state.selectedDate}T${state.selectedTime}Z`);
                const data = await api.goto(targetDateTime.getTime());
                updateOrderBook(data);
            } catch (error) {
                console.error('Skip to failed:', error);
            } finally {
                state.skipping = false;
            }
        };

        const reset = async () => {
            stopReplay();
            const data = await api.reset();
            updateOrderBook(data, false);
        };

        // Replay Controls
        const startReplay = () => {
            state.replayInterval = setInterval(() => skip(state.replayStepSize), state.replaySpeed * 1000);
        };

        const stopReplay = () => {
            if (state.replayInterval) {
                clearInterval(state.replayInterval);
                state.replayInterval = null;
            }
        };

        // UI Helpers
        const getPriceLevelClass = (current, previous, index) => {
            if (!previous?.[index]) return '';
            return current[1] > previous[index][1] ? 'bg-green-100' :
                   current[1] < previous[index][1] ? 'bg-red-100' : '';
        };

        const getBidClass = (bid, index) => 
            getPriceLevelClass(bid, state.previousOrderBook.bids, index);

        const getAskClass = (ask, index) => 
            getPriceLevelClass(ask, state.previousOrderBook.asks, index);

        const getFormattedTime = (date) => {
            const d = date || new Date();
            const pad = (n, length) => n.toString().padStart(length, '0');
            return `${pad(d.getUTCHours(), 2)}:${pad(d.getMinutes(), 2)}:${pad(d.getSeconds(), 2)}.${pad(d.getMilliseconds(), 3)}`;
        };

        onMounted(() => {
            fetchMarkets();
        });

        return {
            state,
            fetchMarkets,
            selectMarket,
            stepForward,
            skipForward,
            skipBackward,
            skipTo,
            reset,
            startReplay,
            stopReplay,
            getBidClass,
            getAskClass,
            formatTuples,
            orderbookLabel,
            getFormattedTime
        };
    }
});

app.mount('#app');

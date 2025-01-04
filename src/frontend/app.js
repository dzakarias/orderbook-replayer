const { createApp, ref, computed, onMounted } = Vue;

const app = Vue.createApp({
    setup() {
        const selectedDate = ref(new Date().toISOString().split('T')[0]);
        const selectedTime = ref(new Date().toLocaleTimeString([], {hour: '2-digit', minute:'2-digit', second:'2-digit'}));
        const selectedMarket = ref(null);
        const markets = ref([]);
        const orderBook = ref({ bids: [], asks: [] });
        const replaySpeed = ref(2);
        const replayStepSize = ref(2);
        const replayInterval = ref(null);
        const previousOrderBook = ref({ bids: [], asks: [] });
        // track the status of the skipTo operation
        const skipping = ref(false);

        const dates = computed(() => {
            return Array.from({ length: 7 }, (_, i) => {
                const d = new Date();
                d.setDate(d.getDate() - i);
                return d.toISOString().split('T')[0];
            });
        });

        const orderbookLabel = computed(() => {
            if (skipping.value) {
                return `Moving to ${selectedTime.value} ...`;
            } else if (selectedMarket?.value == null) {
                return "Select a market/date first";
            } else {
                date_ = orderBook.value?.timestamp ? new Date(orderBook.value?.timestamp) : null;
                return `${selectedMarket.value} Orderbook at ${date_ ? date_.toLocaleTimeString('en-US',{timeZone: 'UTC'}) : '-'}`;
            }
        });

        const fetchMarkets = () => {
            axios.get(`/markets?date_=${selectedDate.value}`)
                .then(response => {
                    markets.value = response.data;
                    selectedMarket.value = markets.value[0];
                    selectMarket();
                });
        };

        const selectMarket = () => {
            axios.post('/select_market', { symbol: selectedMarket.value, date_: selectedDate.value })
                .then(stepForward)
                .catch(error => {
                    console.log(`No such market: ${selectedMarket.value} ${selectedDate.value}`);
                });
        };

        const updateOrderBook = (responseData, updatePrevious = true) => {
            if (updatePrevious) {
                previousOrderBook.value = { ...orderBook.value };
            }
            orderBook.value = responseData;
            orderBook.value.bids = formatTuples(orderBook.value.bids);
            orderBook.value.asks = formatTuples(orderBook.value.asks);
        };

        const stepForward = () => {
            axios.get('/step')
                .then(response => updateOrderBook(response.data));
        };

        const skipForward = () => {
            axios.post('/skip', {seconds: replayStepSize.value})
                .then(response => updateOrderBook(response.data));
        };

        const skipTo = () => {
            skipping.value = true;
            const targetDateTime = new Date(`${selectedDate.value}T${selectedTime.value}Z`);
            const targetTimestamp = targetDateTime.getTime();
            
            axios.post('/goto', {timestamp: targetTimestamp})
                .then(response => {
                    updateOrderBook(response.data);
                    skipping.value = false;
                })
                .catch(error => {
                    skipping.value = false;
                    console.error(error);
                })
                .finally(() => {
                    skipping.value = false;
                });
                if (replayInterval.value) {
                    stopReplay();
                }
        };

        const skipBackward = () => {
           axios.post('/skip', {seconds: -replayStepSize.value})
                .then(response => updateOrderBook(response.data));
        };

        const reset = () => {
            axios.get('/reset')
                .then(response => updateOrderBook(response.data, false));
        };

        const startReplay = () => {
            replayInterval.value = setInterval(skipForward, replaySpeed.value * 1000);
        };

        const stopReplay = () => {
            clearInterval(replayInterval.value);
        };

        const getBidClass = (bid, index) => {
            const prev = previousOrderBook.value.bids[index];
            if (!prev) return '';
            return bid[1] > prev[1] ? 'bg-green-100' :
                   bid[1] < prev[1] ? 'bg-red-100' : '';
        };

        const getAskClass = (ask, index) => {
            const prev = previousOrderBook.value.asks[index];
            if (!prev) return '';
            return ask[1] > prev[1] ? 'bg-green-100' :
                   ask[1] < prev[1] ? 'bg-red-100' : '';
        };

        const formatTuples = (tuples) => {
            const maxDecimalsFirst = Math.max(...tuples.map(tuple => {
                const str = tuple[0].toString();
                const decimalIndex = str.indexOf('.');
                return decimalIndex === -1 ? 0 : str.length - decimalIndex - 1;
            }));

            const maxDecimalsSecond = Math.max(...tuples.map(tuple => {
                const str = tuple[1].toString();
                const decimalIndex = str.indexOf('.');
                return decimalIndex === -1 ? 0 : str.length - decimalIndex - 1;
            }));

            return tuples.map(tuple => {
                const firstValue = Number(tuple[0]).toFixed(maxDecimalsFirst);
                const secondValue = Number(tuple[1]).toFixed(maxDecimalsSecond);
                return [firstValue, secondValue];
            });
        };

        onMounted(() => {
            fetchMarkets();
        });

        return {
            selectedDate,
            selectedTime,
            selectedMarket,
            markets,
            orderBook,
            replaySpeed,
            replayStepSize,
            replayInterval,
            previousOrderBook,
            skipping,
            dates,
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
            orderbookLabel
        };
    }
});

app.mount('#app');

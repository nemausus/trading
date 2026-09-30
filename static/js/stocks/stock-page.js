/**
 * stock-page.js
 * ~~~~~~~~~~~~~
 * Coordinates UI controls, user events, API fetching, and chart rendering for the Stocks tab.
 */

import { fetchStockHistory } from './stock-api.js';
import { StockChart } from './stock-chart.js';
import { formatVolume, computePriceChange } from '../utils.js';

let chartInstance = null;
let currentSymbol = 'AAPL';
let currentPeriod = '1Y';
let currentInterval = '1D';
let isInitialLoaded = false;
let isLoading = false;

// Cached DOM elements (populated once in initStockPage)
let _els = null;

function _getElements() {
    if (_els) return _els;
    _els = {
        tickerInput: document.getElementById('stock-ticker-input'),
        loadBtn: document.getElementById('btn-stock-load'),
        periodSelect: document.getElementById('stock-period-select'),
        intervalSelect: document.getElementById('stock-interval-select'),
        statusMsg: document.getElementById('stock-status-msg'),
        chartWrapper: document.getElementById('stock-chart-wrapper'),
        legendContainer: document.getElementById('stock-chart-legend'),
        banner: document.getElementById('stock-overview-banner'),
    };
    return _els;
}

/**
 * Initialize DOM listeners and state for the Stocks page.
 */
export function initStockPage() {
    const els = _getElements();

    if (!els.chartWrapper) return;

    if (!chartInstance) {
        chartInstance = new StockChart(els.chartWrapper, els.legendContainer);
    }

    // Preset buttons
    document.querySelectorAll('.stock-preset-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
            const sym = e.target.getAttribute('data-symbol');
            if (sym) {
                if (els.tickerInput) els.tickerInput.value = sym;
                loadStockData(sym);
            }
        });
    });

    // Load button
    if (els.loadBtn) {
        els.loadBtn.addEventListener('click', () => {
            const sym = els.tickerInput ? els.tickerInput.value.trim().toUpperCase() : 'AAPL';
            loadStockData(sym);
        });
    }

    // Enter key on ticker input
    if (els.tickerInput) {
        els.tickerInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                const sym = els.tickerInput.value.trim().toUpperCase();
                loadStockData(sym);
            }
        });
    }

    // Period change
    if (els.periodSelect) {
        els.periodSelect.addEventListener('change', (e) => {
            currentPeriod = e.target.value;
            _adjustIntervalOptionsForPeriod(currentPeriod);
            loadStockData(currentSymbol);
        });
    }

    // Interval change
    if (els.intervalSelect) {
        els.intervalSelect.addEventListener('change', (e) => {
            currentInterval = e.target.value;
            loadStockData(currentSymbol);
        });
    }

    // Indicator checkboxes
    const indicatorToggles = [
        { id: 'toggle-sma50', name: 'sma50' },
        { id: 'toggle-sma200', name: 'sma200' },
        { id: 'toggle-volume', name: 'volume' },
        { id: 'toggle-rsi', name: 'rsi' },
    ];

    indicatorToggles.forEach(({ id, name }) => {
        const checkbox = document.getElementById(id);
        if (checkbox) {
            checkbox.addEventListener('change', (e) => {
                if (chartInstance) {
                    chartInstance.toggleIndicator(name, e.target.checked);
                }
            });
        }
    });
}

/**
 * Intelligently adjust interval dropdown choices based on selected period.
 */
function _adjustIntervalOptionsForPeriod(period) {
    const els = _getElements();
    if (!els.intervalSelect) return;

    const currentVal = els.intervalSelect.value;
    const isShortPeriod = period === '5D';
    const intradayIntervals = ['1M', '5M', '15M', '30M'];

    // If 5D selected and interval is 1W or 1MO, default to 1D
    if (isShortPeriod && (currentVal === '1W' || currentVal === '1MO')) {
        els.intervalSelect.value = '1D';
        currentInterval = '1D';
    } else if (!isShortPeriod && intradayIntervals.includes(currentVal)) {
        // Intraday intervals only supported for 5D
        els.intervalSelect.value = '1D';
        currentInterval = '1D';
    }
}

/**
 * Fetch and display stock history for a ticker.
 *
 * @param {string} symbol - Ticker symbol (default 'AAPL').
 * @param {string} [period] - Period (default from select or '1Y').
 * @param {string} [interval] - Interval (default from select or '1D').
 */
export async function loadStockData(symbol = currentSymbol, period = null, interval = null) {
    const els = _getElements();

    const cleanSymbol = (symbol || (els.tickerInput ? els.tickerInput.value : 'AAPL')).trim().toUpperCase();
    if (!cleanSymbol) return;

    currentSymbol = cleanSymbol;
    if (els.tickerInput) els.tickerInput.value = cleanSymbol;

    if (period) currentPeriod = period;
    else if (els.periodSelect) currentPeriod = els.periodSelect.value;

    if (interval) currentInterval = interval;
    else if (els.intervalSelect) currentInterval = els.intervalSelect.value;

    if (isLoading) return;
    isLoading = true;

    if (els.loadBtn) {
        els.loadBtn.disabled = true;
        els.loadBtn.innerText = 'Loading...';
    }

    if (els.statusMsg) {
        els.statusMsg.className = 'stock-status-loading';
        els.statusMsg.innerHTML = `<span class="spinner-small"></span> Loading ${cleanSymbol} (${currentPeriod}, ${currentInterval})...`;
        els.statusMsg.style.display = 'flex';
    }

    try {
        const data = await fetchStockHistory(cleanSymbol, currentPeriod, currentInterval);

        if (!data || !data.candles || !data.candles.length) {
            if (els.statusMsg) {
                els.statusMsg.className = 'stock-status-error';
                els.statusMsg.innerText = `No price history candles returned for ${cleanSymbol}.`;
                els.statusMsg.style.display = 'block';
            }
            return;
        }

        if (els.statusMsg) {
            els.statusMsg.style.display = 'none';
        }

        if (!chartInstance && els.chartWrapper) {
            chartInstance = new StockChart(els.chartWrapper, els.legendContainer);
        }

        if (chartInstance) {
            chartInstance.setData(cleanSymbol, data.candles);
            _updateStockHeaderInfo(cleanSymbol, data.candles);
        }

        isInitialLoaded = true;
    } catch (err) {
        console.error("Failed to load stock data:", err);
        if (els.statusMsg) {
            els.statusMsg.className = 'stock-status-error';
            els.statusMsg.innerText = `Error loading ${cleanSymbol}: ${err.message}`;
            els.statusMsg.style.display = 'block';
        }
    } finally {
        isLoading = false;
        if (els.loadBtn) {
            els.loadBtn.disabled = false;
            els.loadBtn.innerText = 'Load';
        }
    }
}

function _updateStockHeaderInfo(symbol, candles) {
    const els = _getElements();
    if (!els.banner || !candles.length) return;

    const latest = candles[candles.length - 1];
    const prev = candles.length > 1 ? candles[candles.length - 2] : null;
    const prevClose = prev ? prev.close : latest.open;
    const { change, pctChange, isPositive, sign } = computePriceChange(latest.close, prevClose);
    const badgeClass = isPositive ? 'badge-green' : 'badge-red';

    els.banner.innerHTML = `
        <div class="stock-banner-item">
            <span class="stock-banner-symbol">${symbol}</span>
            <span class="stock-banner-price">$${latest.close.toFixed(2)}</span>
            <span class="stock-banner-badge ${badgeClass}">${sign}$${Math.abs(change).toFixed(2)} (${sign}${pctChange.toFixed(2)}%)</span>
        </div>
        <div class="stock-banner-stats">
            <span>Range: <strong>$${latest.low.toFixed(2)} - $${latest.high.toFixed(2)}</strong></span>
            <span>Vol: <strong>${formatVolume(latest.volume)}</strong></span>
            <span>Bars: <strong>${candles.length}</strong></span>
        </div>
    `;
    els.banner.style.display = 'flex';
}

/**
 * Triggered on tab activation to ensure chart canvas renders with proper dimensions.
 */
export function onStocksTabActivated() {
    if (!isInitialLoaded) {
        initStockPage();
        loadStockData('AAPL', '1Y', '1D');
    } else if (chartInstance) {
        setTimeout(() => {
            chartInstance.resize();
        }, 50);
    }
}

/**
 * Resize chart on window resize.
 */
export function resizeStockChart() {
    if (chartInstance) {
        chartInstance.resize();
    }
}

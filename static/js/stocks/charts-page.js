/**
 * charts-page.js
 * ~~~~~~~~~~~~~~
 * Charts tab: renders a responsive grid of StockChart instances (one per ticker)
 * with a user-editable ticker list, shared period/interval selects and indicator toggles.
 */

import { fetchStockHistory } from './stock-api.js';
import { StockChart } from './stock-chart.js';
import { computePriceChange, escapeHtml } from '../utils.js';

const DEFAULT_TICKERS = ['SNOW', 'NVDA', 'GOOG', 'AAPL', 'AMZN', 'META', 'MSFT', 'HOOD', 'UNH'];
// The history endpoint is rate-limited to 30 requests/minute; keep one load well below that.
const MAX_TICKERS = 15;
const TICKER_PATTERN = /^[A-Z0-9.$\/-]{1,10}$/;
const TICKERS_STORAGE_KEY = 'chartsTickers';
const INDICATOR_NAMES = ['sma50', 'sma200', 'volume', 'rsi'];
const INTRADAY_INTERVALS = ['1M', '5M', '15M', '30M'];

// symbol -> { chart: StockChart, quote, status }
const _cards = new Map();
let _tickers = [];
let _initialized = false;
let _loadGeneration = 0;

let _els = null;

function _getElements() {
    if (_els) return _els;
    _els = {
        grid: document.getElementById('charts-grid'),
        tickersInput: document.getElementById('charts-tickers-input'),
        applyBtn: document.getElementById('btn-charts-apply'),
        statusMsg: document.getElementById('charts-status-msg'),
        periodSelect: document.getElementById('charts-period-select'),
        intervalSelect: document.getElementById('charts-interval-select'),
    };
    return _els;
}

/**
 * Return a valid interval for the given period.
 * Intraday intervals are only supported for 5D; 1W/1MO are not allowed for 5D.
 */
function _resolveIntervalForPeriod(period, interval) {
    const isShortPeriod = period === '5D';
    if (isShortPeriod && (interval === '1W' || interval === '1MO')) return '1D';
    if (!isShortPeriod && INTRADAY_INTERVALS.includes(interval)) return '1D';
    return interval;
}

/**
 * Parse a comma/space separated ticker string.
 *
 * @param {string} raw - User input, e.g. "aapl, msft nvda".
 * @returns {{ tickers: string[], invalid: string[] }} Upper-cased, de-duplicated tickers
 *          (input order preserved) and any tokens that are not valid symbols.
 */
function _parseTickers(raw) {
    const tokens = (raw || '').split(/[\s,]+/).map(t => t.trim().toUpperCase()).filter(Boolean);
    const invalid = tokens.filter(t => !TICKER_PATTERN.test(t));
    const tickers = [...new Set(tokens.filter(t => TICKER_PATTERN.test(t)))];
    return { tickers, invalid };
}

function _loadSavedTickers() {
    try {
        const { tickers, invalid } = _parseTickers(localStorage.getItem(TICKERS_STORAGE_KEY));
        if (tickers.length && !invalid.length && tickers.length <= MAX_TICKERS) return tickers;
    } catch (e) {
        console.warn('Could not read saved chart tickers, using defaults:', e);
    }
    return [...DEFAULT_TICKERS];
}

function _showPageStatus(message) {
    const { statusMsg } = _getElements();
    if (!statusMsg) return;
    if (!message) {
        statusMsg.style.display = 'none';
        return;
    }
    statusMsg.className = 'stock-status-error';
    statusMsg.textContent = message;
    statusMsg.style.display = 'block';
}

/**
 * Read current indicator checkbox state into a { name: bool } map.
 */
function _getIndicatorState() {
    const state = {};
    INDICATOR_NAMES.forEach(name => {
        const cb = document.getElementById(`charts-toggle-${name}`);
        state[name] = cb ? cb.checked : true;
    });
    return state;
}

/**
 * Build one chart card (header + status + legend + chart wrapper) and its StockChart.
 */
function _createCard(symbol, indicatorState) {
    const safeSymbol = escapeHtml(symbol);
    const card = document.createElement('div');
    card.className = 'stock-chart-card charts-grid-card';
    card.innerHTML = `
        <div class="charts-card-header">
            <span class="stock-banner-symbol">${safeSymbol}</span>
            <span class="charts-card-quote"></span>
        </div>
        <div class="charts-card-status" style="display: none;"></div>
        <div class="stock-chart-legend"></div>
        <div class="stock-chart-wrapper"></div>
    `;
    _getElements().grid.appendChild(card);

    const chart = new StockChart(
        card.querySelector('.stock-chart-wrapper'),
        card.querySelector('.stock-chart-legend')
    );
    INDICATOR_NAMES.forEach(name => chart.toggleIndicator(name, indicatorState[name]));

    _cards.set(symbol, {
        chart,
        quote: card.querySelector('.charts-card-quote'),
        status: card.querySelector('.charts-card-status'),
    });
}

/**
 * Tear down existing charts and build one card per ticker in `_tickers`.
 */
function _rebuildGrid() {
    const els = _getElements();
    _cards.forEach(({ chart }) => chart.destroy());
    _cards.clear();
    els.grid.innerHTML = '';

    const indicatorState = _getIndicatorState();
    _tickers.forEach(sym => _createCard(sym, indicatorState));
}

function _setCardStatus(entry, kind, message) {
    if (!kind) {
        entry.status.style.display = 'none';
        return;
    }
    const safeMessage = escapeHtml(message);
    entry.status.className = `charts-card-status ${kind === 'error' ? 'stock-status-error' : 'stock-status-loading'}`;
    entry.status.innerHTML = kind === 'loading'
        ? `<span class="spinner-small"></span> ${safeMessage}`
        : safeMessage;
    entry.status.style.display = 'flex';
}

function _renderQuote(entry, candles) {
    const latest = candles[candles.length - 1];
    const prev = candles.length > 1 ? candles[candles.length - 2] : null;
    const prevClose = prev ? prev.close : latest.open;
    const { change, pctChange, isPositive, sign } = computePriceChange(latest.close, prevClose);
    const badgeClass = isPositive ? 'badge-green' : 'badge-red';

    entry.quote.innerHTML = `
        <span class="charts-card-price">$${latest.close.toFixed(2)}</span>
        <span class="stock-banner-badge ${badgeClass}">${sign}$${Math.abs(change).toFixed(2)} (${sign}${pctChange.toFixed(2)}%)</span>
    `;
}

async function _loadOne(symbol, period, interval, generation, isRefresh = false) {
    const entry = _cards.get(symbol);
    if (!entry) return;

    _setCardStatus(entry, 'loading', `Loading ${symbol} (${period}, ${interval})...`);

    try {
        const data = await fetchStockHistory(symbol, period, interval, isRefresh);
        if (generation !== _loadGeneration) return; // a newer load superseded this one

        if (!data || !data.candles || !data.candles.length) {
            _setCardStatus(entry, 'error', `No price history returned for ${symbol}.`);
            return;
        }

        _setCardStatus(entry, null);
        entry.chart.setData(data.candles);
        _renderQuote(entry, data.candles);
    } catch (err) {
        if (generation !== _loadGeneration) return;
        console.error(`Failed to load chart for ${symbol}:`, err);
        _setCardStatus(entry, 'error', `Error loading ${symbol}: ${err.message}`);
    }
}

/**
 * Fetch history for every ticker in parallel and render each chart.
 */
export async function loadAllCharts(isRefresh = false) {
    const els = _getElements();
    if (!els.grid) return;
    if (!_initialized) initChartsPage();

    const period = els.periodSelect ? els.periodSelect.value : '1Y';
    const interval = els.intervalSelect ? els.intervalSelect.value : '1D';
    const generation = ++_loadGeneration;

    await Promise.allSettled(
        _tickers.map(sym => _loadOne(sym, period, interval, generation, isRefresh))
    );
}

/**
 * Validate the tickers input; on success rebuild the grid, persist and reload.
 * Invalid input leaves the current charts untouched and shows an error.
 */
function _applyTickersFromInput() {
    const els = _getElements();
    const { tickers, invalid } = _parseTickers(els.tickersInput.value);

    if (invalid.length) {
        _showPageStatus(`Invalid ticker(s): ${invalid.join(', ')}`);
        return;
    }
    if (!tickers.length) {
        _showPageStatus('Enter at least one ticker.');
        return;
    }
    if (tickers.length > MAX_TICKERS) {
        _showPageStatus(`Too many tickers (${tickers.length}). Maximum is ${MAX_TICKERS}.`);
        return;
    }

    _showPageStatus(null);
    _tickers = tickers;
    els.tickersInput.value = tickers.join(', ');
    try {
        localStorage.setItem(TICKERS_STORAGE_KEY, tickers.join(','));
    } catch (e) {
        console.warn('Could not save chart tickers:', e);
    }
    _rebuildGrid();
    loadAllCharts();
}

/**
 * Build the chart grid and wire up shared controls (runs once).
 */
export function initChartsPage() {
    if (_initialized) return;
    const els = _getElements();
    if (!els.grid) return;
    _initialized = true;

    _tickers = _loadSavedTickers();
    if (els.tickersInput) els.tickersInput.value = _tickers.join(', ');
    _rebuildGrid();

    els.applyBtn?.addEventListener('click', _applyTickersFromInput);
    els.tickersInput?.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            e.preventDefault();
            _applyTickersFromInput();
        }
    });

    els.periodSelect?.addEventListener('change', () => {
        if (els.intervalSelect) {
            els.intervalSelect.value = _resolveIntervalForPeriod(
                els.periodSelect.value, els.intervalSelect.value
            );
        }
        loadAllCharts();
    });

    els.intervalSelect?.addEventListener('change', () => loadAllCharts());

    INDICATOR_NAMES.forEach(name => {
        const cb = document.getElementById(`charts-toggle-${name}`);
        cb?.addEventListener('change', (e) => {
            _cards.forEach(({ chart }) => chart.toggleIndicator(name, e.target.checked));
        });
    });
}

/**
 * Triggered on tab activation: first visit loads data, later visits just resize.
 */
export function onChartsTabActivated() {
    if (!_initialized) {
        initChartsPage();
        loadAllCharts();
    } else {
        setTimeout(() => _cards.forEach(({ chart }) => chart.resize()), 50);
    }
}

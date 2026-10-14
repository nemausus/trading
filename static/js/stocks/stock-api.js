/**
 * stock-api.js
 * ~~~~~~~~~~~~
 * Network request helper for stock price history using Firebase authentication.
 */

import { auth } from '../auth.js';

/**
 * Fetch historical OHLCV candlestick data for a ticker symbol.
 *
 * @param {string} ticker - Stock symbol (e.g. 'AAPL').
 * @param {string} period - Lookback period (e.g. '1Y', '5D', '6M').
 * @param {string} interval - Candle interval (e.g. '1D', '5m', '1W').
 * @returns {Promise<{ symbol: string, candles: Array<Object> }>}
 */
export async function fetchStockHistory(ticker, period = '1Y', interval = '1D', refresh = false) {
    const user = auth.currentUser;
    if (!user) {
        throw new Error("You must be logged in to fetch stock history.");
    }

    const token = await user.getIdToken();
    const cleanTicker = encodeURIComponent((ticker || '').trim().toUpperCase());
    const query = new URLSearchParams({
        period: (period || '1Y').trim(),
        interval: (interval || '1D').trim()
    });
    if (refresh) {
        query.set('refresh', 'true');
    }

    const url = `/api/schwab/stocks/${cleanTicker}/history?${query.toString()}`;
    const response = await fetch(url, {
        method: 'GET',
        headers: {
            'Authorization': `Bearer ${token}`,
            'Accept': 'application/json'
        }
    });

    const data = await response.json().catch(() => ({}));

    if (!response.ok) {
        const errorMsg = data.error || `HTTP error ${response.status}: ${response.statusText}`;
        throw new Error(errorMsg);
    }

    return data;
}

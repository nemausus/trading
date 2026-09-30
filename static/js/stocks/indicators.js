/**
 * indicators.js
 * ~~~~~~~~~~~~~
 * Pure mathematical indicator calculations decoupled from chart rendering.
 * All functions accept an array of normalized candles:
 *   [{ time: number, open: number, high: number, low: number, close: number, volume: number }, ...]
 * and return an array of time/value data points:
 *   [{ time: number, value: number }, ...]
 */

/**
 * Calculate Simple Moving Average (SMA).
 *
 * @param {Array<Object>} candles - Array of OHLCV candles with time and close properties.
 * @param {number} period - Number of bars to average (e.g. 50, 200).
 * @returns {Array<{ time: number, value: number }>}
 */
export function calculateSMA(candles, period) {
    if (!Array.isArray(candles) || candles.length < period || period <= 0) {
        return [];
    }

    const result = [];
    let windowSum = 0;

    // Accumulate the initial window
    for (let i = 0; i < period; i++) {
        windowSum += Number(candles[i].close) || 0;
    }

    // First SMA point at index (period - 1)
    result.push({
        time: candles[period - 1].time,
        value: Number((windowSum / period).toFixed(2))
    });

    // Slide window across remaining candles
    for (let i = period; i < candles.length; i++) {
        const added = Number(candles[i].close) || 0;
        const dropped = Number(candles[i - period].close) || 0;
        windowSum += added - dropped;

        result.push({
            time: candles[i].time,
            value: Number((windowSum / period).toFixed(2))
        });
    }

    return result;
}

/**
 * Calculate Relative Strength Index (RSI) using Wilder's smoothing method.
 *
 * Wilder's Smoothing:
 * - First average gain/loss: simple average over the first `period` price changes.
 * - Subsequent average gain/loss:
 *     avgGain = (prevAvgGain * (period - 1) + currentGain) / period
 *     avgLoss = (prevAvgLoss * (period - 1) + currentLoss) / period
 *
 * @param {Array<Object>} candles - Array of OHLCV candles with time and close properties.
 * @param {number} [period=14] - Lookback period (standard is 14).
 * @returns {Array<{ time: number, value: number }>}
 */
export function calculateRSI(candles, period = 14) {
    if (!Array.isArray(candles) || candles.length <= period || period <= 0) {
        return [];
    }

    const result = [];
    let gainSum = 0;
    let lossSum = 0;

    // First (period) price changes (index 1 to period)
    for (let i = 1; i <= period; i++) {
        const change = Number(candles[i].close) - Number(candles[i - 1].close);
        if (change > 0) {
            gainSum += change;
        } else {
            lossSum += Math.abs(change);
        }
    }

    let avgGain = gainSum / period;
    let avgLoss = lossSum / period;

    // First RSI data point at index `period`
    let rsi;
    if (avgLoss === 0) {
        rsi = avgGain === 0 ? 50 : 100;
    } else {
        const rs = avgGain / avgLoss;
        rsi = 100 - (100 / (1 + rs));
    }

    result.push({
        time: candles[period].time,
        value: Number(rsi.toFixed(2))
    });

    // Wilder's smoothing for subsequent candles
    for (let i = period + 1; i < candles.length; i++) {
        const change = Number(candles[i].close) - Number(candles[i - 1].close);
        const gain = change > 0 ? change : 0;
        const loss = change < 0 ? Math.abs(change) : 0;

        avgGain = (avgGain * (period - 1) + gain) / period;
        avgLoss = (avgLoss * (period - 1) + loss) / period;

        if (avgLoss === 0) {
            rsi = avgGain === 0 ? 50 : 100;
        } else {
            const rs = avgGain / avgLoss;
            rsi = 100 - (100 / (1 + rs));
        }

        result.push({
            time: candles[i].time,
            value: Number(rsi.toFixed(2))
        });
    }

    return result;
}

/**
 * test_indicators.mjs
 * Unit tests for SMA and Wilder's RSI calculations in indicators.js.
 * Run with: node tests/test_indicators.mjs
 */

import assert from 'assert';
import { calculateSMA, calculateRSI } from '../static/js/stocks/indicators.js';

console.log("Testing indicators.js...");

// 1. Test SMA with known values
{
    const candles = [
        { time: 1, close: 10 },
        { time: 2, close: 20 },
        { time: 3, close: 30 },
        { time: 4, close: 40 },
        { time: 5, close: 50 },
    ];

    // SMA with period 3:
    // Index 2 (candle 3): (10 + 20 + 30) / 3 = 20.0
    // Index 3 (candle 4): (20 + 30 + 40) / 3 = 30.0
    // Index 4 (candle 5): (30 + 40 + 50) / 3 = 40.0
    const sma3 = calculateSMA(candles, 3);
    assert.strictEqual(sma3.length, 3, "SMA(3) should return 3 points for 5 candles");
    assert.strictEqual(sma3[0].time, 3);
    assert.strictEqual(sma3[0].value, 20);
    assert.strictEqual(sma3[1].time, 4);
    assert.strictEqual(sma3[1].value, 30);
    assert.strictEqual(sma3[2].time, 5);
    assert.strictEqual(sma3[2].value, 40);

    // SMA with period greater than candle count should return []
    const sma10 = calculateSMA(candles, 10);
    assert.deepStrictEqual(sma10, [], "SMA should return empty array if period > candles.length");

    // SMA with period 0 or negative
    assert.deepStrictEqual(calculateSMA(candles, 0), []);
    assert.deepStrictEqual(calculateSMA([], 3), []);

    console.log("✓ SMA tests passed!");
}

// 2. Test RSI with known behavior
{
    // Case A: 15 candles strictly increasing
    // All gains, 0 losses -> RSI should be 100
    const risingCandles = Array.from({ length: 16 }, (_, i) => ({
        time: i + 1,
        close: 100 + i * 2,
    }));

    const rsiRising = calculateRSI(risingCandles, 14);
    assert.strictEqual(rsiRising.length, 2, "RSI(14) on 16 candles should produce 2 data points");
    assert.strictEqual(rsiRising[0].value, 100, "RSI with all gains should be 100");
    assert.strictEqual(rsiRising[1].value, 100, "RSI with all gains should remain 100");

    // Case B: 15 candles strictly falling
    // All losses, 0 gains -> RSI should be 0
    const fallingCandles = Array.from({ length: 16 }, (_, i) => ({
        time: i + 1,
        close: 100 - i * 2,
    }));

    const rsiFalling = calculateRSI(fallingCandles, 14);
    assert.strictEqual(rsiFalling[0].value, 0, "RSI with all losses should be 0");
    assert.strictEqual(rsiFalling[1].value, 0, "RSI with all losses should remain 0");

    // Case C: Standard RSI reference series (period = 14)
    // 15 prices with alternating gains and losses:
    // Day 0: 44.34, 1: 44.09, 2: 44.15, 3: 43.61, 4: 44.33, 5: 44.83, 6: 45.10, 7: 45.42,
    // 8: 45.84, 9: 46.08, 10: 45.89, 11: 46.03, 12: 45.61, 13: 46.28, 14: 46.28
    const testPrices = [
        44.34, 44.09, 44.15, 43.61, 44.33, 44.83, 45.10, 45.42,
        45.84, 46.08, 45.89, 46.03, 45.61, 46.28, 46.28, 46.00
    ];
    const testCandles = testPrices.map((p, i) => ({ time: i + 1, close: p }));

    const rsiCalculated = calculateRSI(testCandles, 14);
    assert.strictEqual(rsiCalculated.length, 2);
    // At index 14 (first RSI):
    // Gain sum: 0.06 + 0.72 + 0.50 + 0.27 + 0.32 + 0.42 + 0.24 + 0.14 + 0.67 = 3.34
    // Avg gain = 3.34 / 14 = 0.23857
    // Loss sum: 0.25 + 0.54 + 0.19 + 0.42 = 1.40
    // Avg loss = 1.40 / 14 = 0.10000
    // RS = 0.23857 / 0.10 = 2.3857
    // RSI = 100 - (100 / (1 + 2.3857)) = 70.46
    assert.strictEqual(rsiCalculated[0].value, 70.46);

    // Not enough candles
    assert.deepStrictEqual(calculateRSI(testCandles.slice(0, 10), 14), []);
    assert.deepStrictEqual(calculateRSI([], 14), []);

    console.log("✓ RSI tests passed!");
}

console.log("All indicator unit tests successfully passed!");

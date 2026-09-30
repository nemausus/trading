import assert from 'assert';
import { isOption, baseUnderlying, parseOptionStrike, isMarkWithinPercent } from '../static/js/utils.js';

console.log("Running transaction & realized filter tests...");

// 1. Test isOption
assert.strictEqual(isOption('AAPL'), false, 'Equity AAPL should not be option');
assert.strictEqual(isOption('SPX'), false, 'Index SPX should not be option');
assert.strictEqual(isOption('MARGIN INTEREST'), false, 'MARGIN INTEREST should not be option');
assert.strictEqual(isOption('INTEREST'), false, 'INTEREST should not be option');
assert.strictEqual(isOption('CURRENCY_USD'), false, 'CURRENCY_USD should not be option');
assert.strictEqual(isOption('AAPL  261219C00295000'), true, 'OCC option AAPL call should be option');
assert.strictEqual(isOption('SPX   261219P05000000'), true, 'OCC option SPX put should be option');
assert.strictEqual(isOption('NVDA261219C00200000'), true, 'Unspaced OCC option should be option');

// 2. Test baseUnderlying
assert.strictEqual(baseUnderlying('AAPL'), 'AAPL');
assert.strictEqual(baseUnderlying('SPX'), 'SPX');
assert.strictEqual(baseUnderlying('AAPL  261219C00295000'), 'AAPL');
assert.strictEqual(baseUnderlying('SPX   261219P05000000'), 'SPX');
assert.strictEqual(baseUnderlying('GOOGL 261219C00200000'), 'GOOGL');
assert.strictEqual(baseUnderlying('BRK/B 261219C00200000'), 'BRK/B');
assert.strictEqual(baseUnderlying('NVDA261219C00200000'), 'NVDA');

// 2b. Test parseOptionStrike
assert.strictEqual(parseOptionStrike('AAPL  261219C00295000'), 295.0);
assert.strictEqual(parseOptionStrike('SPX   261219P05000000'), 5000.0);
assert.strictEqual(parseOptionStrike('NVDA261219C00122500'), 122.5);
assert.strictEqual(parseOptionStrike('META 1/23/26 655 C'), 655.0);
assert.strictEqual(parseOptionStrike('AAPL'), null);

// 2c. Test isMarkWithinPercent (default 10% tolerance)
// Current mark = 5.0 -> 10% range is [4.50, 5.50]
assert.strictEqual(isMarkWithinPercent(5.0, 5.0), true, 'Exact match should be within 10%');
assert.strictEqual(isMarkWithinPercent(4.5, 5.0), true, 'Lower boundary 4.5 should be within 10%');
assert.strictEqual(isMarkWithinPercent(5.5, 5.0), true, 'Upper boundary 5.5 should be within 10%');
assert.strictEqual(isMarkWithinPercent(5.1, 5.0), true, '5.1 should be within 10% of 5.0');
assert.strictEqual(isMarkWithinPercent(4.9, 5.0), true, '4.9 should be within 10% of 5.0');
assert.strictEqual(isMarkWithinPercent(4.49, 5.0), false, '4.49 is below 10% range');
assert.strictEqual(isMarkWithinPercent(5.51, 5.0), false, '5.51 is above 10% range');
assert.strictEqual(isMarkWithinPercent(2.0, 5.0), false, '2.0 is well outside 10% range');
assert.strictEqual(isMarkWithinPercent(10.0, 5.0), false, '10.0 is well outside 10% range');
// Edge cases: null, undefined, NaN, non-positive
assert.strictEqual(isMarkWithinPercent(null, 5.0), false, 'null candMark should return false');
assert.strictEqual(isMarkWithinPercent(5.0, null), false, 'null currentMark should return false');
assert.strictEqual(isMarkWithinPercent(undefined, 5.0), false, 'undefined candMark should return false');
assert.strictEqual(isMarkWithinPercent(5.0, undefined), false, 'undefined currentMark should return false');
assert.strictEqual(isMarkWithinPercent(NaN, 5.0), false, 'NaN candMark should return false');
assert.strictEqual(isMarkWithinPercent(5.0, 0), false, '0 currentMark should return false');
assert.strictEqual(isMarkWithinPercent(5.0, -1.0), false, 'negative currentMark should return false');
// Custom pct parameter
assert.strictEqual(isMarkWithinPercent(6.0, 5.0, 0.25), true, '6.0 is within 25% of 5.0');
assert.strictEqual(isMarkWithinPercent(6.5, 5.0, 0.25), false, '6.5 is outside 25% of 5.0');

// 3. Mock transactions for date/type/account filter verification
const optionTxn = {
    activityId: 1,
    type: 'TRADE',
    time: '2026-06-15T10:00:00-07:00',
    accountNumber: 'ACC123',
    transferItems: [
        {
            positionEffect: 'OPENING',
            instrument: {
                assetType: 'OPTION',
                symbol: 'AAPL  261219C00295000',
                underlyingSymbol: 'AAPL',
            }
        },
        {
            instrument: {
                assetType: 'CURRENCY',
                symbol: 'CURRENCY_USD',
            }
        }
    ]
};

const equityTxn = {
    activityId: 2,
    type: 'TRADE',
    time: '2026-07-20T14:30:00-07:00',
    accountNumber: 'ACC123',
    transferItems: [
        {
            positionEffect: 'OPENING',
            instrument: {
                assetType: 'EQUITY',
                symbol: 'AAPL',
            }
        }
    ]
};

const spxOptionTxnWithoutExplicitUnderlying = {
    activityId: 3,
    type: 'TRADE',
    time: '2026-08-01T09:15:00-07:00',
    accountNumber: 'ACC456',
    transferItems: [
        {
            positionEffect: 'CLOSING',
            instrument: {
                assetType: 'OPTION',
                symbol: 'SPX   261219C05000000',
            }
        }
    ]
};

const dividendTxn = {
    activityId: 4,
    type: 'DIVIDEND_OR_INTEREST',
    time: '2026-05-01T08:00:00-07:00',
    accountNumber: 'ACC123',
    transferItems: [
        {
            instrument: {
                assetType: 'CURRENCY',
                symbol: 'CURRENCY_USD',
            }
        }
    ]
};

// 4. Test filtering by dates
const txns = [optionTxn, equityTxn, spxOptionTxnWithoutExplicitUnderlying, dividendTxn];

// Date range: 2026-06-01 to 2026-07-31
const dateFiltered = txns.filter(t => {
    const d = (t.time || '').slice(0, 10);
    const fromDate = '2026-06-01';
    const toDate = '2026-07-31';
    return (!fromDate || d >= fromDate) && (!toDate || d <= toDate);
});
assert.strictEqual(dateFiltered.length, 2, 'Should match 2 txns in June/July 2026');
assert.strictEqual(dateFiltered[0].activityId, 1);
assert.strictEqual(dateFiltered[1].activityId, 2);

// Type filter: TRADE
const tradeOnly = txns.filter(t => t.type === 'TRADE');
assert.strictEqual(tradeOnly.length, 3, 'Should have 3 TRADE txns');

// Type filter: DIVIDEND_OR_INTEREST
const divOnly = txns.filter(t => t.type === 'DIVIDEND_OR_INTEREST');
assert.strictEqual(divOnly.length, 1, 'Should have 1 DIVIDEND_OR_INTEREST txn');

// Account filter: ACC123
const acc123Only = txns.filter(t => t.accountNumber === 'ACC123');
assert.strictEqual(acc123Only.length, 3, 'Should have 3 txns for ACC123');

// 5. Test Realized sell date filtering (From Date and To Date)
const realizedList = [
    { symbol: 'AAPL', sell_date: '2026-01-15', 'P/L': 100 },
    { symbol: 'NVDA', sell_date: '2026-05-20', 'P/L': 250 },
    { symbol: 'SPX', sell_date: '2026-08-10', 'P/L': 500 },
    { symbol: 'TSLA', sell_date: '2026-09-01', 'P/L': -50 },
];

function filterRealized(list, fromDate, toDate) {
    return list.filter(r => {
        if (fromDate && (!r.sell_date || r.sell_date < fromDate)) return false;
        if (toDate && (!r.sell_date || r.sell_date > toDate)) return false;
        return true;
    });
}

assert.strictEqual(filterRealized(realizedList, '2026-05-01', '2026-08-31').length, 2);
assert.strictEqual(filterRealized(realizedList, '2026-01-01', '').length, 4);
assert.strictEqual(filterRealized(realizedList, '', '2026-05-20').length, 2);

console.log("All transaction & realized filter tests passed successfully!");

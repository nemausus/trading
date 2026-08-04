export function formatCurrency(val) {
    if (val === null || val === undefined || isNaN(val)) return '-';
    return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(val);
}

export function formatPercent(val) {
    if (val === null || val === undefined || isNaN(val)) return '-';
    return val.toFixed(2) + '%';
}

export function formatNumber(val, decimals = 2) {
    if (val === null || val === undefined || isNaN(val)) return '-';
    return val.toFixed(decimals);
}

export function baseUnderlying(symbol) {
    if (symbol.length <= 4) return symbol;
    return symbol.slice(0, 6).trimEnd();
}

export function sortPositionsGrouped(positions) {
    return [...positions].sort((a, b) => {
        if (a.accountNumber < b.accountNumber) return -1;
        if (a.accountNumber > b.accountNumber) return 1;
        const ua = baseUnderlying(a.symbol);
        const ub = baseUnderlying(b.symbol);
        if (ua < ub) return -1;
        if (ua > ub) return 1;
        const aIsOpt = a.symbol.length > 4;
        const bIsOpt = b.symbol.length > 4;
        if (aIsOpt !== bIsOpt) return aIsOpt ? 1 : -1;
        return a.symbol < b.symbol ? -1 : a.symbol > b.symbol ? 1 : 0;
    });
}

export function getPLFormatting(plVal) {
    if (plVal === null || plVal === undefined) {
        return { valDisplay: '-', cssClass: '', sign: '' };
    }
    return {
        valDisplay: formatCurrency(plVal),
        cssClass: plVal >= 0 ? 'val-positive' : 'val-negative',
        sign: plVal >= 0 ? '+' : ''
    };
}

export function getPLPercentFormatting(plPercent) {
    if (plPercent === null || plPercent === undefined) {
        return { valDisplay: '-', cssClass: '', sign: '' };
    }
    return {
        valDisplay: formatNumber(plPercent, 2) + '%',
        cssClass: plPercent >= 0 ? 'val-positive' : 'val-negative',
        sign: plPercent >= 0 ? '+' : ''
    };
}

export function getSymbolBadgeClass(symbol) {
    return 'symbol-text';
}

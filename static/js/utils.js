export function formatCurrency(val, decimals = 2) {
    if (val === null || val === undefined || isNaN(val)) return '-';
    return new Intl.NumberFormat('en-US', {
        style: 'currency',
        currency: 'USD',
        minimumFractionDigits: decimals,
        maximumFractionDigits: decimals
    }).format(val);
}

export function formatPercent(val) {
    if (val === null || val === undefined || isNaN(val)) return '-';
    return val.toFixed(2) + '%';
}

export function formatNumber(val, decimals = 2) {
    if (val === null || val === undefined || isNaN(val)) return '-';
    return val.toFixed(decimals);
}

export function isOption(symbol) {
    if (!symbol) return false;
    const s = symbol.trim();
    return s.length > 6 || (s.includes(' ') && s.length > 4) || /\d{6}[CP]\d+/.test(s);
}

export function baseUnderlying(symbol) {
    if (!symbol) return '';
    const s = symbol.trim();
    if (!isOption(s)) return s;
    return s.slice(0, 6).trimEnd();
}

export function sortPositionsGrouped(positions) {
    return [...positions].sort((a, b) => {
        if (a.accountNumber < b.accountNumber) return -1;
        if (a.accountNumber > b.accountNumber) return 1;
        const ua = baseUnderlying(a.symbol);
        const ub = baseUnderlying(b.symbol);
        if (ua < ub) return -1;
        if (ua > ub) return 1;
        const aIsOpt = isOption(a.symbol);
        const bIsOpt = isOption(b.symbol);
        if (aIsOpt !== bIsOpt) return aIsOpt ? 1 : -1;
        return a.symbol < b.symbol ? -1 : a.symbol > b.symbol ? 1 : 0;
    });
}

export function getPLFormatting(plVal, decimals = 2) {
    if (plVal === null || plVal === undefined || isNaN(plVal)) {
        return { valDisplay: '-', cssClass: '', sign: '' };
    }
    return {
        valDisplay: formatCurrency(plVal, decimals),
        cssClass: plVal >= 0 ? 'val-positive' : 'val-negative',
        sign: plVal >= 0 ? '+' : ''
    };
}

export function getPLPercentFormatting(plPercent, decimals = 2) {
    if (plPercent === null || plPercent === undefined || isNaN(plPercent)) {
        return { valDisplay: '-', cssClass: '', sign: '' };
    }
    return {
        valDisplay: formatNumber(plPercent, decimals) + '%',
        cssClass: plPercent >= 0 ? 'val-positive' : 'val-negative',
        sign: plPercent >= 0 ? '+' : ''
    };
}

export function getSymbolBadgeClass(symbol) {
    return 'symbol-text';
}

export function formatOptionSymbol(symbol) {
    if (!symbol) return '';
    const s = symbol.trim();
    if (s.length >= 18 && (s.includes('C') || s.includes('P'))) {
        const ticker = s.slice(0, 6).trim();
        const rest = s.slice(6);
        let cpIdx = rest.indexOf('C');
        if (cpIdx === -1) cpIdx = rest.indexOf('P');
        if (cpIdx >= 6) {
            const yymmdd = rest.slice(0, cpIdx);
            const cp = rest[cpIdx];
            const strikeStr = rest.slice(cpIdx + 1);
            if (yymmdd.length === 6 && /^\d+$/.test(strikeStr)) {
                const yy = yymmdd.slice(0, 2);
                const mm = parseInt(yymmdd.slice(2, 4), 10);
                const dd = parseInt(yymmdd.slice(4, 6), 10);
                const strikeVal = parseInt(strikeStr, 10) / 1000.0;
                const strikeFmt = (strikeVal % 1 === 0) ? strikeVal.toFixed(0) : strikeVal.toString();
                return `${ticker} ${mm}/${dd}/${yy} ${strikeFmt}${cp}`;
            }
        }
    }

    const parts = s.split(/\s+/);
    if (parts.length === 4 && (parts[3] === 'C' || parts[3] === 'P') && parts[1].includes('/')) {
        const [ticker, dateStr, strikeStr, cp] = parts;
        try {
            const dateParts = dateStr.split('/');
            const mm = parseInt(dateParts[0], 10);
            const dd = parseInt(dateParts[1], 10);
            const yy = dateParts[2].length === 4 ? dateParts[2].slice(2) : dateParts[2];
            const strikeVal = parseFloat(strikeStr);
            const strikeFmt = isNaN(strikeVal) ? strikeStr : ((strikeVal % 1 === 0) ? strikeVal.toFixed(0) : strikeVal.toString());
            return `${ticker} ${mm}/${dd}/${yy} ${strikeFmt}${cp}`;
        } catch (e) {
            // Fall through
        }
    }

    return s;
}


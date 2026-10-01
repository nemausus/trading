import {
    formatCurrency, formatPercent, formatNumber,
    baseUnderlying, sortPositionsGrouped, isOption,
    getPLFormatting, getPLPercentFormatting, getSymbolBadgeClass,
    formatOptionSymbol, getTradeTypeBadgeClass, getDeltaCssClass,
    escapeHtml
} from './utils.js';

export let lastPositions = [];
let lastOrders = [];

// ── Shared UI helpers ──────────────────────────────────────────────────────

/** Render a standard empty-state placeholder. */
function _noDataHtml(msg) {
    return `<div class="no-data-msg"><p>${msg}</p></div>`;
}

/**
 * Render a full responsive table scaffold.
 * @param {Array<{label: string, cls?: string}>} headers - Column header descriptors.
 * @param {string} bodyHtml - Pre-rendered <tr> rows HTML string.
 */
function _buildTable(headers, bodyHtml) {
    const headCols = headers
        .map(h => `<th${h.cls ? ` class="${h.cls}"` : ''}>${h.label}</th>`)
        .join('');
    return `
        <div class="table-responsive">
            <table>
                <thead><tr>${headCols}</tr></thead>
                <tbody>${bodyHtml}</tbody>
            </table>
        </div>
    `;
}

export function showView(viewId) {
    document.querySelectorAll('.view').forEach(view => {
        view.classList.remove('active-view');
    });
    document.getElementById(viewId).classList.add('active-view');
}

export function clearDashboard() {
    const posContainer = document.getElementById('positions-container');
    if (posContainer) {
        posContainer.innerHTML = _noDataHtml('Connect your Schwab account to retrieve positions.');
    }

    const chainContainer = document.getElementById('chain-container');
    if (chainContainer) {
        chainContainer.innerHTML = _noDataHtml('Enter a symbol and click "Fetch Chain" to retrieve option contracts.');
    }

    const boxContainer = document.getElementById('box-container');
    if (boxContainer) {
        boxContainer.innerHTML = _noDataHtml('Select a date range and click "Find Boxes" to scan for SPX box spread opportunities.');
    }

    const txnContainer = document.getElementById('transactions-container');
    if (txnContainer) {
        txnContainer.innerHTML = _noDataHtml('No transactions stored yet. Click <strong>Sync</strong> to fetch from Schwab.');
    }

    const realizedContainer = document.getElementById('realized-container');
    if (realizedContainer) {
        realizedContainer.innerHTML = _noDataHtml('Loading realized transactions...');
    }

    const realizedPivot = document.getElementById('realized-pivot-container');
    if (realizedPivot) {
        realizedPivot.innerHTML = '';
    }
}

export function renderDashboard(data) {
    lastPositions = data.positions || [];
    lastOrders = data.orders || [];
    renderUnifiedAccounts(data.summaries || [], lastPositions, lastOrders);
}

function parseActionItem(accNum, actionStr) {
    const match = actionStr.match(/^(STO|BTC|ROLL|EXIT)\s+(\d+x)\s+(.+?)\s+\((.+?)\)$/);
    if (match) {
        return {
            account: accNum,
            type: match[1],
            qty: match[2],
            symbol: match[3],
            details: match[4]
        };
    }
    return {
        account: accNum,
        type: 'ACTION',
        qty: '-',
        symbol: actionStr,
        details: '-'
    };
}

function renderAccountActionsHtml(sum) {
    if (!sum || !sum.Todo) return '';

    const itemStrs = sum.Todo.split(/;\s*|,\s*(?=(?:STO|BTC|ROLL|EXIT)\b)/).map(s => s.trim()).filter(Boolean);
    if (itemStrs.length === 0) return '';

    const actions = itemStrs.map(s => parseActionItem(sum.accountNumber, s)).filter(Boolean);
    actions.sort((a, b) => (a.type || '').localeCompare(b.type || ''));

    let rowsHtml = '';
    let mobileListHtml = '';

    actions.forEach(act => {
        let typeClass = 'action-type-sto';
        if (act.type === 'BTC') typeClass = 'action-type-btc';
        else if (act.type === 'ROLL') typeClass = 'action-type-roll';
        else if (act.type === 'EXIT') typeClass = 'action-type-roll';

        rowsHtml += `
            <tr>
                <td><span class="action-type-badge ${typeClass}">${act.type}</span></td>
                <td style="text-align: right; font-weight: 500;">${act.qty}</td>
                <td><span class="symbol-text">${formatOptionSymbol(act.symbol)}</span></td>
                <td style="color: var(--text-secondary); font-size: 0.78rem;">${act.details}</td>
            </tr>
        `;

        mobileListHtml += `
            <div class="mobile-action-row">
                <div class="mobile-action-left">
                    <span class="action-type-badge ${typeClass}">${act.type}</span>
                    <span style="font-weight: 500;">${act.qty}</span>
                    <span class="symbol-text" style="font-weight: 500;">${formatOptionSymbol(act.symbol)}</span>
                </div>
                <div class="mobile-action-right">${act.details}</div>
            </div>
        `;
    });

    const summaryListStr = actions.slice(0, 3).map(a => `${a.type} ${a.qty} ${formatOptionSymbol(a.symbol)}`).join(', ') + (actions.length > 3 ? '...' : '');

    return `
        <details class="account-actions-section">
            <summary class="actions-collapsible-bar" role="button" aria-label="Toggle action items">
                <div style="display: flex; align-items: center; gap: 8px;">
                    <span class="actions-toggle-icon">▸</span>
                    <strong style="color: var(--text-primary); font-size: 0.80rem;">⚡ Action Items</strong>
                    <span class="account-actions-count">${actions.length} Pending</span>
                    <span class="desktop-only-col" style="font-size: 0.76rem; color: var(--text-secondary); margin-left: 4px;">${summaryListStr}</span>
                </div>
                <span class="actions-toggle-label" style="font-size: 0.74rem; color: var(--schwab-link); font-weight: 600;"></span>
            </summary>

            <div class="actions-collapsible-content" style="padding: 6px 12px; background: #ffffff;">
                <!-- Desktop Table View -->
                <div class="desktop-only-action-table table-responsive" style="border: 1px solid var(--border-color); border-radius: 4px; margin-bottom: 4px;">
                    <table style="font-size: 0.78rem;">
                        <thead>
                            <tr style="background-color: var(--bg-tertiary);">
                                <th>Action</th>
                                <th style="text-align: right;">Qty</th>
                                <th>Symbol</th>
                                <th>Metrics / Details</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${rowsHtml}
                        </tbody>
                    </table>
                </div>

                <!-- Mobile Compact List View -->
                <div class="mobile-only-action-list">
                    ${mobileListHtml}
                </div>
            </div>
        </details>
    `;
}

export function renderUnifiedAccounts(summaries = [], positions = [], orders = []) {
    const container = document.getElementById('positions-container');
    if (!container) return;

    // Attach active orders to positions (creating virtual pending-only positions if non-held symbol)
    const mergedPositions = (positions || []).map(p => ({
        ...p,
        pending_orders: []
    }));

    const posIndex = {};
    mergedPositions.forEach(p => {
        posIndex[`${p.accountNumber}_${p.symbol}`] = p;
    });

    (orders || []).forEach(ord => {
        const acc = ord.accountNumber;
        const sym = ord.symbol;
        if (!acc || !sym) return;
        const key = `${acc}_${sym}`;
        if (posIndex[key]) {
            posIndex[key].pending_orders.push(ord);
        } else {
            const virtualPos = {
                accountNumber: acc,
                symbol: sym,
                quantity: 0,
                'cost/share': 0,
                'value/share': 0,
                marketValue: 0,
                'P/L': 0,
                'P/L%': 0,
                cost: 0,
                dte: -1,
                delta: 0,
                mpr: 0,
                markPercentChange: 0,
                pending_orders: [ord],
                isPendingOnly: true
            };
            mergedPositions.push(virtualPos);
            posIndex[key] = virtualPos;
        }
    });

    if ((!summaries || summaries.length === 0) && mergedPositions.length === 0) {
        container.innerHTML = _noDataHtml('No open positions or account data found in Schwab accounts.');
        return;
    }

    const summaryMap = {};
    (summaries || []).forEach(s => {
        if (s && s.accountNumber) {
            summaryMap[String(s.accountNumber)] = s;
        }
    });

    const accountPositionsMap = {};
    mergedPositions.forEach(p => {
        if (p && p.accountNumber) {
            const acc = String(p.accountNumber);
            if (!accountPositionsMap[acc]) accountPositionsMap[acc] = [];
            accountPositionsMap[acc].push(p);
        }
    });

    const allAccNums = Array.from(new Set([
        ...Object.keys(summaryMap),
        ...Object.keys(accountPositionsMap)
    ])).sort();

    if (allAccNums.length === 0) {
        container.innerHTML = _noDataHtml('No open positions found in Schwab accounts.');
        return;
    }

    let html = '';

    allAccNums.forEach(accNum => {
        const sum = summaryMap[accNum];
        const rawAccPositions = accountPositionsMap[accNum] || [];
        const accPositions = sortPositionsGrouped(rawAccPositions);

        // Render Summary Header Bar for this account card
        let summaryBarHtml = '';
        if (sum) {
            let riskClass = "risk-low";
            if (sum.Risk < 90) riskClass = "risk-high";
            else if (sum.Risk < 95) riskClass = "risk-med";

            const shortPLFormat = getPLFormatting(sum['Short P/L'] || 0);
            summaryBarHtml = `
                <div class="account-summary-bar">
                    <div class="account-summary-container">
                        <div class="account-summary-header">
                            <span class="account-summary-title">Account ${sum.accountNumber}</span>
                            <span class="account-summary-net">Net: <strong>${formatCurrency(sum.Net)}</strong></span>
                        </div>
                        <div class="account-summary-metrics">
                            <div class="summary-metric-item"><span>Short P/L:</span><strong class="${shortPLFormat.cssClass}">${shortPLFormat.sign}${shortPLFormat.valDisplay}</strong></div>
                            <div class="summary-metric-item"><span>Short Val:</span><strong>${formatCurrency(sum['Short Value'])}</strong></div>
                            <div class="summary-metric-item"><span>Cash:</span><strong>${formatCurrency(sum.Cash)}</strong></div>
                            <div class="summary-metric-item summary-metric-loan"><span>Box:</span><strong>${formatCurrency(sum['BOX'])}</strong></div>
                            <div class="summary-metric-item"><span>Risk:</span><strong class="${riskClass}">${formatPercent(sum.Risk)}</strong></div>
                        </div>
                    </div>
                </div>
            `;
        } else {
            summaryBarHtml = `
                <div class="account-summary-bar" style="padding: 6px 12px; background-color: #f8fafc; border-bottom: 1px solid var(--border-color);">
                    <strong style="font-size: 0.86rem; color: var(--accent-blue);">Account ${accNum}</strong>
                </div>
            `;
        }

        const actionsHtml = sum ? renderAccountActionsHtml(sum) : '';

        // Render Positions Table / Cards for this account
        let tableHtml = '';
        if (accPositions.length === 0) {
            tableHtml = _noDataHtml('No open positions in this account.');
        } else {
            tableHtml = `
                <div class="table-responsive">
                    <table class="schwab-positions-table">
                        <thead>
                            <tr>
                                <th style="min-width: 170px;">Symbol</th>
                                <th class="text-right">Qty</th>
                                <th class="text-right">Cost/Share</th>
                                <th class="text-right">Mark</th>
                                <th class="text-right">Cost Basis</th>
                                <th class="text-right">Market Value</th>
                                <th class="text-right">P/L</th>
                                <th class="desktop-only-pl-pct text-right">P/L%</th>
                                <th class="text-right">Day %</th>
                                <th class="text-center">DTE</th>
                                <th class="text-center">Delta</th>
                                <th class="text-center">MPR</th>
                            </tr>
                        </thead>
                        <tbody>
            `;

            accPositions.forEach((pos, index) => {
                const isOpt = isOption(pos.symbol);
                const underlying = baseUnderlying(pos.symbol);

                const isGroupStart = (index === 0 || baseUnderlying(accPositions[index - 1].symbol) !== underlying);
                const groupStartClass = isGroupStart ? 'group-start-row' : '';
                const isGroupEnd = (index === accPositions.length - 1 || baseUnderlying(accPositions[index + 1].symbol) !== underlying);
                const groupEndClass = isGroupEnd ? 'group-end-row' : '';

                const pl = getPLFormatting(pos['P/L'], 0);
                const plPercent = getPLPercentFormatting(pos['P/L%'], 0);

                const markPctDisplay = (pos.markPercentChange !== undefined && pos.markPercentChange !== null)
                    ? getPLPercentFormatting(pos.markPercentChange)
                    : { valDisplay: '-', cssClass: '', sign: '' };

                const dteDisplay = pos.dte >= 0 ? pos.dte : '-';
                const deltaDisplay = pos.delta !== 0 ? formatNumber(pos.delta, 2) : '-';
                const mprDisplay = pos.mpr !== 0 ? formatPercent(pos.mpr) : '-';
                const hasOptionsMetrics = (pos.dte >= 0) || (pos.delta !== 0) || (pos.mpr !== 0);

                const dteCssClass = (pos.dte >= 0 && pos.dte < 14) ? 'val-negative' : '';
                const deltaCssClass = getDeltaCssClass(pos.delta);

                let pendingOrdersDesktopHtml = '';
                let pendingOrdersMobileHtml = '';

                if (pos.pending_orders && pos.pending_orders.length > 0) {
                    pos.pending_orders.forEach((ord, ordIdx) => {
                        const isLastOrder = (ordIdx === pos.pending_orders.length - 1);
                        const orderRowGroupEndClass = (isGroupEnd && isLastOrder) ? 'group-end-row' : '';

                        const ordType = ord.type || 'ORDER';
                        const ordPrice = ord.price ? formatCurrency(ord.price) : 'MKT';
                        const ordStatus = ord.status || 'WORKING';

                        pendingOrdersDesktopHtml += `
                            <tr class="pending-order-row ${orderRowGroupEndClass}">
                                <td class="desktop-only-col" style="padding-left: 28px;">
                                    <span class="badge-pending-order" style="font-size: 0.72rem; padding: 1px 5px; background: rgba(148, 163, 184, 0.15); color: var(--text-secondary); border-radius: 3px; font-weight: 600;">⚡ Order</span>
                                </td>
                                <td class="desktop-only-col" style="text-align: right; color: var(--text-secondary);">${ord.quantity}</td>
                                <td class="desktop-only-col" colspan="6" style="text-align: left; color: var(--text-secondary);">
                                    <span>${ordType}</span> @ ${ordPrice} <span style="font-size:0.75rem; opacity:0.85;">(${ord.orderType || ''} ${ord.duration || ''})</span>
                                </td>
                                <td class="desktop-only-col" style="text-align: right;"><span style="font-size: 0.72rem; padding: 1px 5px; background: rgba(217, 119, 6, 0.12); color: #d97706; border-radius: 3px; font-weight: 600;">${ordStatus}</span></td>
                                <td class="desktop-only-col" colspan="3"></td>
                            </tr>
                        `;

                        pendingOrdersMobileHtml += `
                            <div class="mobile-split-row pending-order-row" style="border-top: 1px dashed rgba(148, 163, 184, 0.25); margin-top: 4px; padding-top: 3px; padding-bottom: 2px; color: var(--text-secondary); font-size: 0.80rem;">
                                <div class="split-col"><span>⚡ Order: ${ordType} ${ord.quantity} @ ${ordPrice}</span></div>
                                <div class="split-col" style="text-align: right;"><span style="font-size: 0.72rem; padding: 1px 4px; background: rgba(217, 119, 6, 0.12); color: #d97706; border-radius: 3px; font-weight: 600;">${ordStatus}</span></div>
                            </div>
                        `;
                    });
                }

                let symbolCellDesktopHtml = '';
                let rowTypeClass = isOpt ? 'row-option' : 'row-equity';
                let cellIndentClass = isOpt ? 'cell-option-symbol' : '';

                if (!isOpt) {
                    // Parent Equity Row
                    symbolCellDesktopHtml = `
                        <div class="symbol-equity-wrap">
                            <span class="symbol-equity-ticker">${pos.symbol}</span>
                            <button class="btn-row-action" title="Stock Options">···</button>
                        </div>
                    `;
                } else {
                    // Indented Child Option Row
                    symbolCellDesktopHtml = `
                        <div class="symbol-option-wrap">
                            <span class="symbol-option-ticker">${formatOptionSymbol(pos.symbol)}</span>
                            <button class="btn-row-action btn-option-menu-trigger" data-symbol="${pos.symbol}" data-account="${pos.accountNumber || pos.account || ''}" data-qty="${pos.quantity}" data-cost="${pos['cost/share'] || 0}" data-val="${pos['value/share'] || 0}" data-strike="${pos.strikePrice || ''}" title="Option Actions">···</button>
                        </div>
                    `;
                }

                const symbolCellMobileHtml = !isOpt
                    ? `<span class="symbol-equity-ticker">${pos.symbol}</span>`
                    : `<span class="symbol-option-ticker">${formatOptionSymbol(pos.symbol)}</span>`;

                let stripeClass = '';
                if (pos.action) {
                    const actUpper = String(pos.action).toUpperCase().trim();
                    if (actUpper.startsWith('ROLL')) {
                        stripeClass = 'row-stripe-roll';
                    } else if (actUpper.startsWith('BTC')) {
                        stripeClass = 'row-stripe-btc';
                    } else if (actUpper.startsWith('STO')) {
                        stripeClass = 'row-stripe-sto';
                    } else if (actUpper.startsWith('EXIT')) {
                        stripeClass = 'row-stripe-exit';
                    }
                }

                tableHtml += `
                    <tr class="${rowTypeClass} ${groupStartClass} ${groupEndClass} ${stripeClass}" ${pos.action ? `title="Recommended Action: ${pos.action}"` : ''}>
                        <!-- Desktop Columns -->
                        <td class="desktop-only-col ${cellIndentClass}" data-label="Symbol">${symbolCellDesktopHtml}</td>
                        <td class="desktop-only-col" style="text-align: right; font-weight: 500;">${pos.quantity}</td>
                        <td class="desktop-only-col" style="text-align: right;">${formatCurrency(pos['cost/share'])}</td>
                        <td class="desktop-only-col" style="text-align: right;">${formatCurrency(pos['value/share'])}</td>
                        <td class="desktop-only-col" style="text-align: right; font-weight: 500;">${formatCurrency(pos.cost)}</td>
                        <td class="desktop-only-col" style="text-align: right; font-weight: 500;">${formatCurrency(pos.marketValue)}</td>
                        <td class="desktop-only-col ${pl.cssClass}" style="text-align: right; font-weight: 500;">${pl.sign}${pl.valDisplay}</td>
                        <td class="desktop-only-col ${plPercent.cssClass}" style="text-align: right; font-weight: 500;">${plPercent.sign}${plPercent.valDisplay}</td>
                        <td class="desktop-only-col ${markPctDisplay.cssClass}" style="text-align: right; font-weight: 500;">${markPctDisplay.valDisplay !== '-' ? `${markPctDisplay.sign}${markPctDisplay.valDisplay}` : '-'}</td>
                        <td class="desktop-only-col ${dteCssClass}" style="text-align: center;">${dteDisplay}</td>
                        <td class="desktop-only-col ${deltaCssClass}" style="text-align: center;">${deltaDisplay}</td>
                        <td class="desktop-only-col" style="text-align: center;">${mprDisplay}</td>

                        <!-- Mobile Only Combined Row Layout -->
                        <td class="mobile-only-card-col" colspan="12">
                            <div class="mobile-split-row header-row">
                                <div class="split-col col-symbol"><span>${symbolCellMobileHtml} ${pos.quantity}</span> ${isOpt ? `<button class="btn-row-action btn-option-menu-trigger" data-symbol="${pos.symbol}" data-account="${pos.accountNumber || pos.account || ''}" data-qty="${pos.quantity}" data-cost="${pos['cost/share'] || 0}" data-val="${pos['value/share'] || 0}" data-strike="${pos.strikePrice || ''}" title="Option Actions">···</button>` : ''}</div>
                                <div class="split-col col-pl ${pl.cssClass}" style="text-align: right;">${pl.sign}${pl.valDisplay} <span class="mobile-pl-pct">(${plPercent.sign}${plPercent.valDisplay})</span></div>
                            </div>
                            <div class="mobile-split-row details-row">
                                <div class="split-col col-cost">${formatCurrency(pos.marketValue)} / ${formatCurrency(pos.cost)}</div>
                                <div class="split-col col-prices" style="text-align: right;">${formatCurrency(pos['value/share'])}${markPctDisplay.valDisplay !== '-' ? ` <span class="${markPctDisplay.cssClass}">(${markPctDisplay.sign}${markPctDisplay.valDisplay})</span>` : ''} / ${formatCurrency(pos['cost/share'])}</div>
                            </div>
                            ${hasOptionsMetrics ? `
                            <div class="mobile-split-row options-row">
                                <div class="split-col col-dte">DTE: <span class="${dteCssClass}">${dteDisplay}</span> | &Delta;: <span class="${deltaCssClass}">${deltaDisplay}</span></div>
                                <div class="split-col col-mpr" style="text-align: right;">MPR: ${mprDisplay}</div>
                            </div>
                            ` : ''}
                            ${pendingOrdersMobileHtml}
                        </td>
                    </tr>
                    ${pendingOrdersDesktopHtml}
                `;
            });

            tableHtml += `</tbody></table></div>`;
        }

        html += `
            <div class="section-card account-card" style="margin-bottom: 12px; padding: 0; overflow: hidden; border-radius: 6px;">
                ${summaryBarHtml}
                ${actionsHtml}
                ${tableHtml}
            </div>
        `;
    });

    container.innerHTML = html;

    // Attach row selection click listener (mimicking selected row in Schwab screenshot)
    container.querySelectorAll('.schwab-positions-table tbody tr').forEach(tr => {
        tr.addEventListener('click', (e) => {
            if (e.target.closest('button')) return;
            const table = tr.closest('table');
            if (!table) return;
            const wasSelected = tr.classList.contains('row-selected');
            table.querySelectorAll('tr.row-selected').forEach(r => r.classList.remove('row-selected'));
            if (!wasSelected) {
                tr.classList.add('row-selected');
            }
        });
    });
}



export function renderUnderlyingBanner(underlying) {
    const container = document.getElementById('chain-underlying-container');
    if (!underlying || !underlying.symbol) {
        container.innerHTML = '';
        return;
    }

    const changeVal = underlying.change || 0.0;
    const changeClass = changeVal >= 0 ? 'val-positive' : 'val-negative';
    const changeSign = changeVal >= 0 ? '+' : '';
    const pctVal = underlying.percentChange || 0.0;

    container.innerHTML = `
        <div class="underlying-banner">
            <div style="display: flex; align-items: center; gap: 10px;">
                <span class="underlying-title">${underlying.symbol}</span>
                <span style="font-size: 1.05rem; font-weight: 700;">${formatCurrency(underlying.price)}</span>
                <span class="${changeClass}" style="font-size: 0.82rem; font-weight: 600;">
                    ${changeSign}${formatNumber(changeVal)} (${changeSign}${formatNumber(pctVal, 2)}%)
                </span>
            </div>
        </div>
    `;
}

export function renderOptionChainTable(contracts) {
    const container = document.getElementById('chain-container');
    if (!contracts || contracts.length === 0) {
        container.innerHTML = _noDataHtml('No option contracts match the selected filters.');
        return;
    }

    let displayContracts = contracts;
    let rollBannerHtml = '';

    if (window.activeRollFilter && window.activeRollFilter.targetMark > 0) {
        const targetMark = window.activeRollFilter.targetMark;
        const targetSymbol = window.activeRollFilter.targetSymbol;
        const tolerance = Math.max(0.75, targetMark * 0.35);

        const filtered = contracts.filter(opt => {
            const m = (opt.mark !== undefined && opt.mark !== null) ? Number(opt.mark) : 0;
            return Math.abs(m - targetMark) <= tolerance;
        });

        if (filtered.length > 0) {
            displayContracts = filtered;
        } else {
            // Sort by price proximity and take closest 15
            const sorted = [...contracts].sort((a, b) => Math.abs((Number(a.mark) || 0) - targetMark) - Math.abs((Number(b.mark) || 0) - targetMark));
            displayContracts = sorted.slice(0, 15);
        }

        rollBannerHtml = `
            <div class="roll-filter-banner">
                <span>🔄 <strong>Roll View for ${formatOptionSymbol(targetSymbol)}</strong>: Showing ${displayContracts.length} contracts near current mark <strong>$${targetMark.toFixed(2)}</strong> (minimal credit/debit).</span>
                <button id="btn-clear-roll-filter" class="btn-clear-roll">Show All Contracts</button>
            </div>
        `;
    }

    let prevDte = null;
    let dteGroupIndex = 0;

    let rowsHtml = displayContracts.map((opt, index) => {
        const deltaDisplay = opt.delta !== 0 ? formatNumber(opt.delta, 2) : '-';
        const ivDisplay = opt.volatility ? formatNumber(opt.volatility, 1) + '%' : '-';
        const mprDisplay = opt.mpr ? formatPercent(opt.mpr) : '-';

        const changeVal = opt.change || 0.0;
        const changeClass = changeVal >= 0 ? 'val-positive' : 'val-negative';
        const changeSign = changeVal >= 0 ? '+' : '';

        const beChangeVal = opt.beChange || 0.0;
        const beChangeClass = beChangeVal >= 0 ? 'val-positive' : 'val-negative';
        const beChangeSign = beChangeVal >= 0 ? '+' : '';

        // Calculate prefilled Buy/Sell limit prices
        // Buy order: (mark + bid) / 2
        // Sell order: (mark + ask) / 2
        const markVal = (opt.mark !== undefined && opt.mark !== null) ? Number(opt.mark) : 0;
        const bidVal = (opt.bid !== undefined && opt.bid !== null) ? Number(opt.bid) : 0;
        const askVal = (opt.ask !== undefined && opt.ask !== null) ? Number(opt.ask) : 0;

        const buyLimit = (bidVal > 0) ? (markVal + bidVal) / 2 : markVal;
        const sellLimit = (askVal > 0) ? (markVal + askVal) / 2 : markVal;

        const buyPriceFormatted = buyLimit >= 1.0 ? buyLimit.toFixed(2) : buyLimit.toFixed(4);
        const sellPriceFormatted = sellLimit >= 1.0 ? sellLimit.toFixed(2) : sellLimit.toFixed(4);

        const isNewGroup = opt.dte !== prevDte;
        let dteGroupHeaderHtml = '';
        if (isNewGroup) {
            if (prevDte !== null) {
                dteGroupIndex++;
            }
            prevDte = opt.dte;
            dteGroupHeaderHtml = `
                <tr class="dte-group-row">
                    <td colspan="8">
                        <div class="dte-header-content">
                            <span class="dte-group-pill">${opt.dte} DTE</span>
                            <span class="dte-group-date">Expiration: <strong>${opt.expirationDate}</strong></span>
                        </div>
                    </td>
                </tr>
            `;
        }

        const isGroupStart = isNewGroup;
        const isGroupEnd = (index === displayContracts.length - 1 || displayContracts[index + 1].dte !== opt.dte);
        const groupStartClass = isGroupStart ? 'group-start-row' : '';
        const groupEndClass = isGroupEnd ? 'group-end-row' : '';

        const rowBgClass = (dteGroupIndex % 2 === 0) ? 'dte-bg-group-0' : 'dte-bg-group-1';
        const contractTypeClass = opt.contractType === 'CALL' ? 'row-call' : 'row-put';

        return dteGroupHeaderHtml + `
            <tr class="${rowBgClass} ${contractTypeClass}">
                <td style="text-align: right; font-weight: 700;">$${formatNumber(opt.strikePrice, 2)}</td>
                <td style="text-align: right; font-weight: 600;">${formatCurrency(opt.mark)}</td>
                <td style="text-align: center; font-weight: 600; color: var(--accent-blue);">${deltaDisplay}</td>
                <td style="text-align: center;" class="val-positive">${mprDisplay}</td>
                <td style="text-align: center;" class="${changeClass}">${changeSign}${formatNumber(changeVal, 2)}%</td>
                <td style="text-align: right;" class="${beChangeClass}">${beChangeSign}${formatNumber(beChangeVal, 2)}%</td>
                <td style="text-align: right;">${ivDisplay}</td>
                <td class="chain-actions-cell">
                    <button class="btn-trade-buy" data-symbol="${opt.symbol}" data-action="BTO" data-price="${buyPriceFormatted}" data-mark="${markVal}" data-bid="${bidVal}" data-ask="${askVal}">Buy</button>
                    <button class="btn-trade-sell" data-symbol="${opt.symbol}" data-action="STO" data-price="${sellPriceFormatted}" data-mark="${markVal}" data-bid="${bidVal}" data-ask="${askVal}">Sell</button>
                </td>
            </tr>
        `;
    }).join('');

    container.innerHTML = rollBannerHtml + _buildTable([
        { label: 'Strike', cls: 'text-right' },
        { label: 'Mark', cls: 'text-right' },
        { label: 'Delta', cls: 'text-center' },
        { label: 'MPR', cls: 'text-center' },
        { label: 'Strike %', cls: 'text-center' },
        { label: 'BE %', cls: 'text-right' },
        { label: 'IV', cls: 'text-right' },
        { label: 'Action', cls: 'text-center' },
    ], rowsHtml);
}

export function renderBoxes(boxes) {
    const container = document.getElementById('box-container');
    if (!boxes || boxes.length === 0) {
        container.innerHTML = _noDataHtml('No SPX box spreads found for the selected criteria. Try adjusting the date range or box size.');
        return;
    }

    let prevExpDate = null;

    let rowsHtml = boxes.map((box, index) => {
        const rateClass = box.rate >= 5.5 ? 'val-positive' : (box.rate >= 4.5 ? '' : 'val-negative');

        const isNewGroup = box.expirationDate !== prevExpDate;
        let expHeaderHtml = '';
        if (isNewGroup) {
            prevExpDate = box.expirationDate;
            expHeaderHtml = `<tr class="group-header-row"><td colspan="8">Expiration: <strong>${box.expirationDate}</strong> &mdash; <strong>${box.dte} DTE</strong></td></tr>`;
        }

        const isGroupStart = isNewGroup;
        const isGroupEnd = (index === boxes.length - 1 || boxes[index + 1].expirationDate !== box.expirationDate);
        const groupStartClass = isGroupStart ? 'group-start-row' : '';
        const groupEndClass = isGroupEnd ? 'group-end-row' : '';

        return expHeaderHtml + `
            <tr class="${groupStartClass} ${groupEndClass}">
                <!-- Desktop Columns -->
                <td class="desktop-only-col" style="text-align: center; font-weight: 600; color: var(--text-secondary);">${box.size}</td>
                <td class="desktop-only-col" style="text-align: right; font-weight: 700;">$${formatNumber(box.btoPut, 0)}</td>
                <td class="desktop-only-col" style="text-align: right; font-weight: 700;">$${formatNumber(box.stoPut, 0)}</td>
                <td class="desktop-only-col" style="text-align: right; font-weight: 700;">$${formatNumber(box.stoCall, 0)}</td>
                <td class="desktop-only-col" style="text-align: right; font-weight: 700;">$${formatNumber(box.btoCall, 0)}</td>
                <td class="desktop-only-col" style="text-align: right; font-weight: 600;">$${formatNumber(box.netCredit, 2)}</td>
                <td class="desktop-only-col" style="text-align: right;" class="${rateClass}">${formatNumber(box.rate, 2)}%</td>
                <td class="desktop-only-col" style="text-align: right; color: var(--text-secondary);">${box.liquidity.toLocaleString()}</td>

                <!-- Mobile Only Combined Row Layout -->
                <td class="mobile-only-card-col" colspan="8">
                    <div class="mobile-split-row header-row">
                        <div class="split-col col-symbol"><span>Box Size ${box.size}</span></div>
                        <div class="split-col" style="text-align: right; font-weight: 700;">Net Cr: $${formatNumber(box.netCredit, 2)} <span class="${rateClass}" style="margin-left: 4px;">(${formatNumber(box.rate, 2)}%)</span></div>
                    </div>
                    <div class="mobile-split-row details-row">
                        <div class="split-col" style="color: var(--text-secondary);">Put: $${formatNumber(box.btoPut, 0)} / $${formatNumber(box.stoPut, 0)}</div>
                        <div class="split-col" style="text-align: right; color: var(--text-secondary);">Call: $${formatNumber(box.stoCall, 0)} / $${formatNumber(box.btoCall, 0)}</div>
                    </div>
                    <div class="mobile-split-row options-row">
                        <div class="split-col" style="color: var(--text-secondary); font-size: 0.72rem;">Liq: ${box.liquidity.toLocaleString()}</div>
                    </div>
                </td>
            </tr>
        `;
    }).join('');

    container.innerHTML = _buildTable([
        { label: 'Size', cls: 'text-center' },
        { label: 'BTO PUT', cls: 'text-right' },
        { label: 'STO PUT', cls: 'text-right' },
        { label: 'STO CALL', cls: 'text-right' },
        { label: 'BTO CALL', cls: 'text-right' },
        { label: 'Net Credit', cls: 'text-right' },
        { label: 'Ann. Rate', cls: 'text-right' },
        { label: 'Liquidity', cls: 'text-right' },
    ], rowsHtml);
}

// =====================================================================================
// --- TRANSACTIONS ---
// =====================================================================================

/** Extract the primary non-currency transfer item from a transaction. */
function _primaryTransferItem(txn) {
    const items = txn.transferItems || [];
    return items.find(it => it.instrument && it.instrument.assetType !== 'CURRENCY') || items[0] || null;
}

/** Format an ISO date string to a short readable date. */
function _shortDate(isoStr) {
    if (!isoStr) return '—';
    try {
        return isoStr.slice(0, 10); // YYYY-MM-DD
    } catch (_) {
        return isoStr;
    }
}

/** Return badge HTML and CSS class for a transaction type. */
function _typeBadge(type) {
    switch (type) {
        case 'TRADE':
            return '<span class="txn-badge txn-badge-trade">TRADE</span>';
        case 'DIVIDEND_OR_INTEREST':
            return '<span class="txn-badge txn-badge-dividend">DIVIDEND</span>';
        case 'RECEIVE_AND_DELIVER':
            return '<span class="txn-badge txn-badge-assignment">ASSIGN</span>';
        default:
            return `<span class="txn-badge">${type}</span>`;
    }
}

/** Return CSS class for positionEffect (OPENING/CLOSING). */
function _effectClass(effect) {
    if (effect === 'OPENING') return 'txn-effect-open';
    if (effect === 'CLOSING') return 'txn-effect-close';
    return '';
}

export function renderTransactions(transactions) {
    const container = document.getElementById('transactions-container');
    const statsBar = document.getElementById('txn-stats-bar');

    if (!transactions || transactions.length === 0) {
        container.innerHTML = _noDataHtml('No transactions match the selected criteria.');
        if (statsBar) {
            const earliestEl = document.getElementById('txn-stat-earliest');
            const latestEl = document.getElementById('txn-stat-latest');
            const countEl = document.getElementById('txn-stat-count');
            if (earliestEl) earliestEl.textContent = '—';
            if (latestEl) latestEl.textContent = '—';
            if (countEl) countEl.textContent = '0';
            statsBar.style.display = 'flex';
        }
        return;
    }

    // --- Populate stats bar ---
    if (statsBar) {
        const times = transactions.map(t => t.time).filter(Boolean).sort();
        const earliestEl = document.getElementById('txn-stat-earliest');
        const latestEl = document.getElementById('txn-stat-latest');
        const countEl = document.getElementById('txn-stat-count');
        if (earliestEl) earliestEl.textContent = times.length ? _shortDate(times[0]) : '—';
        if (latestEl) latestEl.textContent = times.length ? _shortDate(times[times.length - 1]) : '—';
        if (countEl) countEl.textContent = transactions.length;
        statsBar.style.display = 'flex';
    }

    // --- Build rows ---
    let rowsHtml = transactions.map(txn => {
        const primary = _primaryTransferItem(txn);
        const instrument = primary?.instrument || {};
        const symbol = instrument.symbol || '—';
        const assetType = instrument.assetType || '';
        const posEffect = primary?.positionEffect || '';
        const price = primary?.price;
        const amount = primary?.amount;

        const priceDisplay = price != null && price !== 0
            ? formatCurrency(price)
            : '—';
        const amountDisplay = amount != null ? formatNumber(amount, 0) : '—';

        const netPL = getPLFormatting(txn.netAmount || 0);

        const symbolBadgeClass = getSymbolBadgeClass(symbol);
        const displaySym = symbol !== 'CURRENCY_USD' ? symbol : '—';
        const effectCls = _effectClass(posEffect);
        const effectBadge = posEffect ? `<span style="font-size:0.7rem; padding:1px 5px; border-radius:4px; font-weight:600;" class="${effectCls}">${posEffect}</span>` : '';

        return `
            <tr>
                <!-- Desktop Columns -->
                <td class="desktop-only-col" style="color:var(--text-secondary); font-size:0.82rem;">${txn.accountNumber || '—'}</td>
                <td class="desktop-only-col" style="color:var(--text-secondary); font-size:0.82rem;">${_shortDate(txn.time)}</td>
                <td class="desktop-only-col">${_typeBadge(txn.type)}</td>
                <td class="desktop-only-col"><span class="${symbolBadgeClass}">${displaySym}</span></td>
                <td class="desktop-only-col" style="font-size:0.75rem; color:var(--text-secondary); max-width:120px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">${assetType}</td>
                <td class="desktop-only-col ${effectCls}" style="text-align:center; font-size:0.8rem; font-weight:600;">${posEffect || '—'}</td>
                <td class="desktop-only-col" style="text-align:right;">${amountDisplay}</td>
                <td class="desktop-only-col" style="text-align:right;">${priceDisplay}</td>
                <td class="desktop-only-col" style="text-align:right; font-weight:600;" class="${netPL.cssClass}">${netPL.sign}${netPL.valDisplay}</td>

                <!-- Mobile Only Combined Row Layout -->
                <td class="mobile-only-card-col" colspan="9">
                    <div class="mobile-split-row header-row">
                        <div class="split-col col-symbol" style="display:flex; align-items:center; gap:6px; flex-wrap:wrap;">
                            <span class="${symbolBadgeClass}">${displaySym}</span>
                            ${_typeBadge(txn.type)}
                            ${effectBadge}
                        </div>
                        <div class="split-col ${netPL.cssClass}" style="text-align: right; font-weight: 700;">${netPL.sign}${netPL.valDisplay}</div>
                    </div>
                    <div class="mobile-split-row details-row">
                        <div class="split-col" style="color: var(--text-secondary);">${_shortDate(txn.time)} &bull; ${assetType}</div>
                        <div class="split-col" style="text-align: right; color: var(--text-secondary);">${amountDisplay !== '—' ? `${amountDisplay} @ ${priceDisplay}` : priceDisplay}</div>
                    </div>
                </td>
            </tr>
        `;
    }).join('');

    container.innerHTML = _buildTable([
        { label: 'Account' },
        { label: 'Date' },
        { label: 'Type' },
        { label: 'Symbol' },
        { label: 'Asset' },
        { label: 'Effect', cls: 'text-center' },
        { label: 'Qty', cls: 'text-right' },
        { label: 'Price', cls: 'text-right' },
        { label: 'Net Amount', cls: 'text-right' },
    ], rowsHtml);
}

const ACCOUNT_COLORS = [
    '#2563eb', // Blue
    '#10b981', // Emerald Green
    '#f59e0b', // Amber
    '#8b5cf6', // Purple
    '#06b6d4', // Cyan
    '#ec4899', // Pink
    '#6366f1', // Indigo
    '#84cc16'  // Lime
];

function getAccountColorMap(items) {
    const accMap = {};
    let colorIdx = 0;
    (items || []).forEach(item => {
        const acc = item.accountNumber || 'Default';
        if (!accMap[acc]) {
            accMap[acc] = ACCOUNT_COLORS[colorIdx % ACCOUNT_COLORS.length];
            colorIdx++;
        }
    });
    return accMap;
}

export function renderRealized(realizedList) {
    const container = document.getElementById('realized-container');
    const pivotContainer = document.getElementById('realized-pivot-container');

    if (!realizedList || realizedList.length === 0) {
        container.innerHTML = _noDataHtml('No realized transactions match the criteria.');
        if (pivotContainer) pivotContainer.innerHTML = '';
        return;
    }


    // Render 2D monthly P/L by Symbol pivot grid
    if (pivotContainer) {
        const monthsSet = new Set();
        const symbolsSet = new Set();

        realizedList.forEach(r => {
            if (r.sell_date) {
                const m = r.sell_date.slice(0, 7); // "YYYY-MM"
                monthsSet.add(m);
            } else {
                monthsSet.add('Unknown');
            }
            if (r.symbol) {
                const baseSym = r.symbol === 'MARGIN INTEREST' ? 'MARGIN INTEREST' : baseUnderlying(r.symbol);
                symbolsSet.add(baseSym);
            }
        });

        const months = Array.from(monthsSet).sort();
        const symbols = Array.from(symbolsSet).sort();

        // Map of symbol -> month -> P/L sum
        const pivotData = {};
        symbols.forEach(sym => {
            pivotData[sym] = {};
            months.forEach(m => {
                pivotData[sym][m] = 0;
            });
        });

        // Row totals and column totals
        const symbolTotals = {};
        symbols.forEach(sym => { symbolTotals[sym] = 0; });
        const monthTotals = {};
        months.forEach(m => { monthTotals[m] = 0; });
        let grandTotal = 0;

        realizedList.forEach(r => {
            const sym = r.symbol === 'MARGIN INTEREST' ? 'MARGIN INTEREST' : baseUnderlying(r.symbol || '');
            const m = r.sell_date ? r.sell_date.slice(0, 7) : 'Unknown';
            const pl = r['P/L'] || 0;

            if (pivotData[sym] && pivotData[sym][m] !== undefined) {
                pivotData[sym][m] += pl;
                symbolTotals[sym] += pl;
                monthTotals[m] += pl;
                grandTotal += pl;
            }
        });

        const rows = months.map(m => {
            const cells = symbols.map(sym => {
                const val = pivotData[sym][m];
                const plFmt = getPLFormatting(val);
                const displayVal = val !== 0 ? plFmt.valDisplay : '—';
                return `<td class="text-right ${plFmt.cssClass}">${displayVal}</td>`;
            }).join('');

            const mTotalFmt = getPLFormatting(monthTotals[m]);
            const mTotalDisplay = monthTotals[m] !== 0 ? mTotalFmt.valDisplay : '—';

            return `
                <tr>
                    <td style="font-weight:600;">${m}</td>
                    ${cells}
                    <td class="text-right font-semibold ${mTotalFmt.cssClass}">${mTotalDisplay}</td>
                </tr>
            `;
        }).join('');

        const totalCells = symbols.map(sym => {
            const val = symbolTotals[sym];
            const plFmt = getPLFormatting(val);
            const displayVal = val !== 0 ? plFmt.valDisplay : '—';
            return `<td class="text-right font-semibold ${plFmt.cssClass}">${displayVal}</td>`;
        }).join('');

        const grandTotalFmt = getPLFormatting(grandTotal);
        const grandTotalDisplay = grandTotal !== 0 ? grandTotalFmt.valDisplay : '—';

        pivotContainer.innerHTML = `
            <div class="section-card" style="margin-bottom: 10px; padding: 10px 14px;">
                <h3 style="margin-bottom: 8px; font-size: 1.05rem;">Monthly P/L by Symbol</h3>
                ${_buildTable(
            [{ label: 'Month' }, ...symbols.map(sym => ({ label: sym, cls: 'text-right' })), { label: 'Total', cls: 'text-right' }],
            rows + `<tr style="border-top: 2px solid var(--border-color); font-weight:600;"><td>Total</td>${totalCells}<td class="text-right font-bold ${grandTotalFmt.cssClass}">${grandTotalDisplay}</td></tr>`
        )}
            </div>
        `;

    }

    const accColorMap = getAccountColorMap(realizedList);
    const accounts = Object.keys(accColorMap);

    let legendHtml = '';
    if (accounts.length > 0) {
        legendHtml = `
            <div class="account-legend-bar" style="display: flex; flex-wrap: wrap; gap: 10px; align-items: center; margin-bottom: 8px; padding: 4px 10px; background: var(--bg-tertiary); border: 1px solid var(--border-color); border-radius: 4px; font-size: 0.76rem;">
                <span style="font-weight: 600; color: var(--text-secondary);">Accounts:</span>
                ${accounts.map(acc => `
                    <span style="display: inline-flex; align-items: center; gap: 5px; font-weight: 500; color: var(--text-primary);">
                        <span style="display: inline-block; width: 8px; height: 8px; border-radius: 50%; background-color: ${accColorMap[acc]};"></span>
                        Account ${acc}
                    </span>
                `).join('')}
            </div>
        `;
    }

    let rowsHtml = realizedList.map(r => {
        const symbol = r.symbol || '—';
        const symbolBadgeClass = getSymbolBadgeClass(symbol);
        const tradeType = r.trade_type || '—';
        const typeBadgeClass = getTradeTypeBadgeClass(tradeType);
        const plFormat = getPLFormatting(r['P/L'] || 0);
        const accNumber = r.accountNumber || '—';
        const accColor = accColorMap[accNumber] || 'var(--accent-blue)';

        return `
            <tr style="border-left: 3.5px solid ${accColor} !important;">
                <!-- Desktop Columns -->
                <td class="desktop-only-col" style="color:var(--text-secondary); font-size:0.82rem;">
                    <span style="display: inline-block; width: 8px; height: 8px; border-radius: 50%; background-color: ${accColor}; margin-right: 6px;"></span>${accNumber}
                </td>
                <td class="desktop-only-col"><span class="${typeBadgeClass}">${tradeType}</span></td>
                <td class="desktop-only-col" style="color:var(--text-secondary); font-size:0.82rem;">${_shortDate(r.buy_date)}</td>
                <td class="desktop-only-col" style="text-align:right;">${formatCurrency(r.buy_price)}</td>
                <td class="desktop-only-col" style="color:var(--text-secondary); font-size:0.82rem;">${_shortDate(r.sell_date)}</td>
                <td class="desktop-only-col" style="text-align:right;">${formatCurrency(r.sell_price)}</td>
                <td class="desktop-only-col"><span class="${symbolBadgeClass}">${formatOptionSymbol(symbol)}</span></td>
                <td class="desktop-only-col" style="text-align:right;">${formatNumber(r.amount, 0)}</td>
                <td class="desktop-only-col ${plFormat.cssClass}" style="text-align:right; font-weight:600;">${plFormat.sign}${plFormat.valDisplay}</td>

                <!-- Mobile Only Combined Row Layout -->
                <td class="mobile-only-card-col" colspan="9">
                    <div class="mobile-split-row header-row" style="display: flex; justify-content: space-between; align-items: center; width: 100%; margin-bottom: 4px;">
                        <div class="split-col col-symbol" style="flex: 1 1 auto; overflow: hidden; min-width: 0;">
                            <span><span class="${typeBadgeClass}" style="margin-right: 6px;">${tradeType}</span> ${formatNumber(r.amount, 0)} &times; <span class="${symbolBadgeClass}">${formatOptionSymbol(symbol)}</span></span>
                        </div>
                        <div class="split-col ${plFormat.cssClass}" style="flex: 0 0 auto; text-align: right; font-weight: 700; min-width: max-content; margin-left: 8px;">${plFormat.sign}${plFormat.valDisplay}</div>
                    </div>
                    <div class="mobile-split-row details-row" style="display: flex; justify-content: space-between; align-items: center; width: 100%; font-size: 0.78rem;">
                        <div class="split-col" style="color: var(--text-secondary); flex: 1;">Open: ${formatCurrency(r.buy_price)} <span style="font-size:0.72rem;">(${_shortDate(r.buy_date)})</span></div>
                        <div class="split-col" style="text-align: right; color: var(--text-secondary); flex: 1;">Close: ${formatCurrency(r.sell_price)} <span style="font-size:0.72rem;">(${_shortDate(r.sell_date)})</span></div>
                    </div>
                </td>
            </tr>
        `;
    }).join('');

    container.innerHTML = legendHtml + _buildTable([
        { label: 'Account' },
        { label: 'Type' },
        { label: 'Open Date' },
        { label: 'Open Price', cls: 'text-right' },
        { label: 'Close Date' },
        { label: 'Close Price', cls: 'text-right' },
        { label: 'Symbol' },
        { label: 'Qty', cls: 'text-right' },
        { label: 'Realized P/L', cls: 'text-right' },
    ], rowsHtml);
}


export function renderRollChainModal(data) {
    const modal = document.getElementById('roll-chain-modal');
    const badgeEl = document.getElementById('modal-roll-badge');
    const bodyEl = document.getElementById('modal-roll-body');

    if (!modal || !bodyEl) return;

    modal.classList.remove('hidden');

    if (!data || data.error) {
        bodyEl.innerHTML = `<div class="no-data-msg" style="color:var(--accent-red)"><p>${escapeHtml(data ? data.error : 'Failed to load roll chain.')}</p></div>`;
        return;
    }

    const rollChain = data.roll_chain || {};
    const chain = rollChain.chain || [];
    const summary = rollChain.summary || {};
    const targetSymbol = rollChain.target_symbol || '';
    const underlying = rollChain.underlying || '';

    if (badgeEl) badgeEl.textContent = underlying || targetSymbol;

    if (chain.length === 0) {
        bodyEl.innerHTML = `<div class="no-data-msg"><p>No transaction history found for ${escapeHtml(targetSymbol)}.</p></div>`;
        return;
    }

    const netAmountFmt = getPLFormatting(summary.total_net_amount || 0);

    let summaryHtml = `
        <div class="roll-summary-pill">
            <div>
                <div style="font-size: 0.8rem; color: var(--text-secondary);">Roll History</div>
                <div style="font-size: 1rem; font-weight: 600;">${summary.is_rolled ? `${summary.total_legs} Legs Sequence` : 'Direct Open Position'}</div>
            </div>
            <div style="text-align: right;">
                <div style="font-size: 0.8rem; color: var(--text-secondary);">Total Net Credit / Debit</div>
                <div style="font-size: 1.1rem; font-weight: 700;" class="${netAmountFmt.cssClass}">${netAmountFmt.sign}${netAmountFmt.valDisplay}</div>
            </div>
        </div>
    `;

    let timelineHtml = '<div class="roll-timeline">';
    const displayChain = [...chain].reverse();

    displayChain.forEach((leg, idx) => {
        const isCurrent = (leg.symbol === targetSymbol || idx === 0);
        const actionTagClass = leg.action === 'STO' ? 'action-type-sto' : (leg.action === 'BTO' ? 'action-type-btc' : 'action-type-roll');
        const stepNetVal = leg.roll_net_amount !== undefined ? leg.roll_net_amount : (leg.netAmount || 0);
        const netFmt = getPLFormatting(stepNetVal);
        const stepLabel = leg.roll_net_amount !== undefined ? 'Roll Net Credit' : 'Leg Net';

        let detailsStr = '';
        if (leg.close_leg) {
            const closeNetFmt = getPLFormatting(leg.close_leg.netAmount || 0);
            detailsStr = `<div style="font-size:0.8rem; color:var(--text-secondary); margin-top:4px;">Rolled from <strong>${formatOptionSymbol(leg.close_leg.symbol)}</strong> (BTC ${leg.close_leg.amount}x @ ${formatCurrency(leg.close_leg.price)} &bull; ${closeNetFmt.valDisplay})</div>`;
        }

        const dateStr = leg.time ? leg.time.slice(0, 10) : 'Initial';

        timelineHtml += `
            <div class="roll-timeline-item">
                <div class="roll-timeline-node" style="${isCurrent ? 'background: var(--accent-green, #10b981);' : ''}"></div>
                <div class="roll-timeline-card">
                    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom: 4px;">
                        <div>
                            <span class="action-type-badge ${actionTagClass}" style="margin-right:6px;">${leg.action}</span>
                            <strong style="font-size:0.95rem;">${formatOptionSymbol(leg.symbol)}</strong>
                            ${isCurrent ? ' <span style="font-size:0.75rem; background:rgba(16,185,129,0.15); color:var(--accent-green); padding:1px 6px; border-radius:4px;">Current Open</span>' : ''}
                        </div>
                        <span style="font-size:0.8rem; color:var(--text-secondary);">${dateStr}</span>
                    </div>
                    <div style="display:flex; justify-content:space-between; font-size:0.85rem; color:var(--text-secondary); margin-top:4px;">
                        <span>Qty: ${leg.amount} @ ${formatCurrency(leg.price)}</span>
                        <span class="${netFmt.cssClass}" style="font-weight:600;">${stepLabel}: ${netFmt.sign}${netFmt.valDisplay}</span>
                    </div>
                    ${detailsStr}
                </div>
            </div>
        `;
    });

    timelineHtml += '</div>';

    bodyEl.innerHTML = summaryHtml + timelineHtml;
}


export function closeRollChainModal() {
    const modal = document.getElementById('roll-chain-modal');
    if (modal) modal.classList.add('hidden');
}


export function renderRollCandidatesTable(candidates, rollContext, selectedSymbol = '') {
    const container = document.getElementById('roll-chain-candidates-container');
    if (!container) return;

    if (!candidates || candidates.length === 0) {
        container.innerHTML = `<div class="no-data-msg" style="padding: 16px;"><p>No matching option contracts found for roll.</p></div>`;
        return;
    }

    const rowsHtml = candidates.map(c => {
        const isSelected = (selectedSymbol && c.symbol === selectedSymbol);
        const candMark = (c.mark !== undefined && c.mark !== null && !isNaN(c.mark))
            ? Number(c.mark)
            : ((Number(c.bid || 0) + Number(c.ask || 0)) / 2);

        const currentMark = Number(rollContext.mark || 0);
        const netDiff = candMark - currentMark; // Positive = Credit, Negative = Debit

        let diffBadgeHtml = '';
        if (netDiff >= 0) {
            diffBadgeHtml = `<span class="roll-diff-badge roll-diff-credit">+$${netDiff.toFixed(2)} Credit</span>`;
        } else {
            diffBadgeHtml = `<span class="roll-diff-badge roll-diff-debit">-$${Math.abs(netDiff).toFixed(2)} Debit</span>`;
        }

        const expDisplay = `${c.expirationDate || ''} (${c.dte !== undefined ? c.dte : '-'}d)`;
        const strikeDisplay = `$${Number(c.strikePrice || 0).toFixed(2)}`;
        const markDisplay = `$${candMark.toFixed(2)}`;
        const bidAskDisplay = `${c.bid !== undefined ? `$${Number(c.bid).toFixed(2)}` : '-'} / ${c.ask !== undefined ? `$${Number(c.ask).toFixed(2)}` : '-'}`;
        const deltaDisplay = (c.delta !== undefined && c.delta !== 0) ? Number(c.delta).toFixed(2) : '-';
        const candDeltaCssClass = getDeltaCssClass(c.delta);

        return `
            <tr class="roll-candidate-row ${isSelected ? 'selected-roll-candidate' : ''}"
                data-symbol="${c.symbol}"
                data-mark="${candMark}"
                data-diff="${netDiff}"
                data-exp="${c.expirationDate || ''}"
                data-strike="${c.strikePrice || 0}">
                <td style="font-weight: 500;">${expDisplay}</td>
                <td style="text-align: right; font-weight: 600;">${strikeDisplay}</td>
                <td style="text-align: right; font-weight: 600; color: var(--text-primary);">${markDisplay}</td>
                <td style="text-align: right; color: var(--text-secondary); font-size: 0.74rem;">${bidAskDisplay}</td>
                <td style="text-align: center;" class="${candDeltaCssClass}">${deltaDisplay}</td>
                <td style="text-align: right;">${diffBadgeHtml}</td>
                <td style="text-align: center;">
                    <button type="button" class="btn-select-target" data-symbol="${c.symbol}">
                        ${isSelected ? '✓ Selected' : 'Select'}
                    </button>
                </td>
            </tr>
        `;
    }).join('');

    container.innerHTML = `
        <table class="roll-candidates-table">
            <thead>
                <tr>
                    <th>Exp (DTE)</th>
                    <th style="text-align: right;">Strike</th>
                    <th style="text-align: right;">Mark</th>
                    <th style="text-align: right;">Bid / Ask</th>
                    <th style="text-align: center;">&Delta;</th>
                    <th style="text-align: right;">Net Diff</th>
                    <th style="text-align: center;">Action</th>
                </tr>
            </thead>
            <tbody>
                ${rowsHtml}
            </tbody>
        </table>
    `;
}


function _populateModalAccounts(selectEl, selectedAccount) {
    if (!selectEl) return;
    const accNums = new Set();
    (lastPositions || []).forEach(p => {
        if (p.accountNumber) accNums.add(String(p.accountNumber));
    });
    if (accNums.size === 0) {
        accNums.add('primary');
        accNums.add('secondary');
    }
    selectEl.innerHTML = '';
    accNums.forEach(acc => {
        const opt = document.createElement('option');
        opt.value = acc;
        opt.textContent = `Account ${acc}`;
        if (String(acc) === String(selectedAccount)) opt.selected = true;
        selectEl.appendChild(opt);
    });
}

export function openOrderModal(params = {}) {
    const modal = document.getElementById('order-modal');
    if (!modal) return;

    const isRollMode = (params.mode === 'roll');
    const modalCard = modal.querySelector('.order-modal-card');
    if (modalCard) {
        modalCard.classList.toggle('roll-mode', isRollMode);
    }

    const singleSection = document.getElementById('order-single-section');
    const rollSection = document.getElementById('order-roll-section');

    const symbol = params.symbol || '';
    const badgeEl = document.getElementById('modal-order-badge');
    if (badgeEl) badgeEl.textContent = symbol ? formatOptionSymbol(symbol) : '';

    const symbolInput = document.getElementById('order-symbol');
    if (symbolInput) symbolInput.value = symbol;

    const statusEl = document.getElementById('order-status-msg');
    if (statusEl) {
        statusEl.className = 'order-status-msg hidden';
        statusEl.innerHTML = '';
    }

    if (isRollMode) {
        if (singleSection) singleSection.classList.add('hidden');
        if (rollSection) rollSection.classList.remove('hidden');

        const titleEl = document.getElementById('modal-order-title');
        if (titleEl) titleEl.textContent = 'Roll Option';

        const submitBtn = document.getElementById('btn-order-submit');
        if (submitBtn) submitBtn.textContent = 'Submit Roll Order';

        // Setup Leg 1
        const closeActionEl = document.getElementById('roll-close-action');
        if (closeActionEl) closeActionEl.textContent = 'BTC';
        const closeSymbolDisplayEl = document.getElementById('roll-close-symbol-display');
        if (closeSymbolDisplayEl) closeSymbolDisplayEl.textContent = formatOptionSymbol(symbol);
        const closeSymbolInput = document.getElementById('roll-close-symbol');
        if (closeSymbolInput) closeSymbolInput.value = symbol;
        const closeMarkEl = document.getElementById('roll-close-mark');
        const markVal = Number(params.mark || 0);
        if (closeMarkEl) closeMarkEl.textContent = markVal > 0 ? `Mark: ~$${markVal.toFixed(2)}` : 'Mark: -';

        // Reset Leg 2
        const openSymbolDisplayEl = document.getElementById('roll-open-symbol-display');
        if (openSymbolDisplayEl) openSymbolDisplayEl.textContent = 'Select target from table below';
        const openMarkEl = document.getElementById('roll-open-mark');
        if (openMarkEl) openMarkEl.textContent = 'Mark: -';
        const openSymbolInput = document.getElementById('roll-open-symbol');
        if (openSymbolInput) openSymbolInput.value = '';

        // Reset price and hint
        const rollPriceEl = document.getElementById('roll-price');
        if (rollPriceEl) rollPriceEl.value = '';
        const rollPriceHint = document.getElementById('roll-price-hint');
        if (rollPriceHint) rollPriceHint.textContent = 'Select a target contract below to auto-calculate Net Credit/Debit';

        // Reset filter selects to default recommendations
        const markFilterSelect = document.getElementById('roll-chain-mark-filter');
        if (markFilterSelect) markFilterSelect.value = '10pct';
        const expiryFilterSelect = document.getElementById('roll-chain-expiry-filter');
        if (expiryFilterSelect) expiryFilterSelect.value = 'later';

        // Update picker subtitle with current strike & mark filter info
        const rollSubtitleEl = document.getElementById('roll-chain-picker-subtitle');
        if (rollSubtitleEl) {
            const subtitleParts = [];
            if (params.currentStrike !== null && params.currentStrike !== undefined && !isNaN(params.currentStrike) && params.currentStrike > 0) {
                subtitleParts.push(`strikes \u2265 $${Number(params.currentStrike).toFixed(2)}`);
            }
            if (params.mark !== null && params.mark !== undefined && !isNaN(params.mark) && Number(params.mark) > 0) {
                const curM = Number(params.mark);
                subtitleParts.push(`mark within 10% ($${(curM * 0.9).toFixed(2)} - $${(curM * 1.1).toFixed(2)})`);
            }
            if (subtitleParts.length > 0) {
                rollSubtitleEl.textContent = `Filtered for ${subtitleParts.join(' & ')}`;
            } else {
                rollSubtitleEl.textContent = 'Filtered for minimal credit/debit roll near current mark';
            }
        }

        // Accounts dropdown
        _populateModalAccounts(document.getElementById('roll-account'), params.account);

        // Quantity
        const rollQtyEl = document.getElementById('roll-quantity');
        if (rollQtyEl) rollQtyEl.value = params.quantity || 1;

        // Duration
        const rollDurEl = document.getElementById('roll-duration');
        if (rollDurEl) rollDurEl.value = params.duration || 'GOOD_TILL_CANCEL';

        // Order Type
        const rollOrderType = document.getElementById('roll-order-type');
        if (rollOrderType) rollOrderType.value = 'NET_CREDIT';

    } else {
        if (singleSection) singleSection.classList.remove('hidden');
        if (rollSection) rollSection.classList.add('hidden');

        const instruction = params.instruction || 'BTO';
        const quantity = params.quantity || 1;
        const price = (params.price !== undefined && params.price !== null) ? params.price : '';
        const duration = params.duration || 'GOOD_TILL_CANCEL';
        const account = params.account || '';

        const titleEl = document.getElementById('modal-order-title');
        if (titleEl) {
            const actionLabels = {
                'BTO': 'Buy to Open (BTO)',
                'STO': 'Sell to Open (STO)',
                'BTC': 'Buy to Close (BTC)',
                'STC': 'Sell to Close (STC)',
                'BUY': 'Buy Stock',
                'SELL': 'Sell Stock'
            };
            titleEl.textContent = actionLabels[instruction] || 'Place Order';
        }

        const submitBtn = document.getElementById('btn-order-submit');
        if (submitBtn) submitBtn.textContent = 'Submit Order';

        const instructionEl = document.getElementById('order-instruction');
        if (instructionEl) instructionEl.value = instruction;

        const qtyEl = document.getElementById('order-quantity');
        if (qtyEl) qtyEl.value = quantity;

        const priceEl = document.getElementById('order-price');
        if (priceEl) priceEl.value = price;

        const durationEl = document.getElementById('order-duration');
        if (durationEl) durationEl.value = duration;

        // Populate accounts dropdown
        _populateModalAccounts(document.getElementById('order-account'), account);

        // Price hint text
        const hintEl = document.getElementById('order-price-hint');
        if (hintEl) {
            if (params.mark !== undefined) {
                const fmt = v => (v && Number(v) > 0) ? `$${Number(v).toFixed(2)}` : '-';
                hintEl.textContent = `Bid: ${fmt(params.bid)} | Mark: ${fmt(params.mark)} | Ask: ${fmt(params.ask)}`;
            } else if (params.buyPrice !== undefined && Number(params.buyPrice) > 0) {
                hintEl.textContent = `Open Cost: $${Number(params.buyPrice).toFixed(2)} (Target 30%: $${Number(price).toFixed(2)})`;
            } else {
                hintEl.textContent = '';
            }
        }
    }

    modal.classList.remove('hidden');
}


export function closeOrderModal() {
    const modal = document.getElementById('order-modal');
    if (modal) modal.classList.add('hidden');
}


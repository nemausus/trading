import {
    formatCurrency, formatPercent, formatNumber,
    baseUnderlying, sortPositionsGrouped,
    getPLFormatting, getPLPercentFormatting, getSymbolBadgeClass
} from './utils.js';

export let lastPositions = [];

export function showView(viewId) {
    document.querySelectorAll('.view').forEach(view => {
        view.classList.remove('active-view');
    });
    document.getElementById(viewId).classList.add('active-view');
}

export function clearDashboard() {
    document.getElementById('summaries-container').innerHTML = "";
    document.getElementById('positions-container').innerHTML = `
        <div class="no-data-msg">
            <p>Connect your Schwab account to retrieve positions.</p>
        </div>
    `;
    document.getElementById('orders-container').innerHTML = `
        <div class="no-data-msg">
            <p>Connect your Schwab account to retrieve working orders.</p>
        </div>
    `;

    const boxContainer = document.getElementById('box-container');
    if (boxContainer) {
        boxContainer.innerHTML = `<div class="no-data-msg"><p>Select a date range and click "Find Boxes" to scan for SPX box spread opportunities.</p></div>`;
    }
}

export function renderDashboard(data) {
    lastPositions = data.positions || [];
    renderSummaries(data.summaries || []);
    renderPositions(lastPositions);
    renderOrders(data.orders || []);

}

export function renderSummaries(summaries) {
    const container = document.getElementById('summaries-container');
    if (!summaries || summaries.length === 0) {
        container.innerHTML = `
            <div class="summary-card" style="grid-column: 1 / -1; text-align: center;">
                <h4>Accounts Summary</h4>
                <div class="summary-value" style="font-size: 1.2rem; color: var(--text-secondary);">No accounts found.</div>
            </div>
        `;
        return;
    }

    container.innerHTML = summaries.map(sum => {
        const todoItems = sum.Todo ? sum.Todo.split(',').map(s => s.trim()) : [];
        const todoPillsHtml = todoItems.length > 0
            ? `<div class="todo-list-pills">${todoItems.map(item => `<span class="todo-pill">${item}</span>`).join('')}</div>`
            : `<div class="summary-subtext" style="color: var(--accent-green); font-weight:600; margin-top: 8px;">Covered / Complete</div>`;

        let riskClass = "risk-low";
        if (sum.Risk < 90) riskClass = "risk-high";
        else if (sum.Risk < 95) riskClass = "risk-med";

        return `
            <div class="summary-card">
                <h4>Account ${sum.accountNumber}</h4>
                <div class="summary-value">${formatCurrency(sum.Net)}</div>
                <div class="summary-subtext">Cash: <strong>${formatCurrency(sum.Cash)}</strong></div>
                <div class="summary-subtext" style="margin-top: 4px;">
                    Total Loan: <strong>${formatCurrency(sum['Total Loan'])}</strong>
                    <span style="font-size:0.75rem; color:var(--text-secondary); display:block;">
                        (Margin: ${formatCurrency(sum.Margin)} | Box: ${formatCurrency(sum.BOX)} | CSP: ${formatCurrency(sum.CSP)})
                    </span>
                </div>
                <div class="summary-subtext" style="margin-top: 4px;">
                    Risk Factor: <strong class="${riskClass}">${formatPercent(sum.Risk)}</strong>
                </div>
                <div class="summary-subtext" style="margin-top: 8px; border-top: 1px solid var(--border-color); padding-top: 8px;">
                    <strong>Action Items (Uncovered Longs):</strong>
                    ${todoPillsHtml}
                </div>
            </div>
        `;
    }).join('');
}

export function renderPositions(positions) {
    const container = document.getElementById('positions-container');
    if (!positions || positions.length === 0) {
        container.innerHTML = `<div class="no-data-msg"><p>No open positions found in Schwab accounts.</p></div>`;
        return;
    }

    const grouped = document.getElementById('btn-group-underlying')?.dataset.grouped === 'true';
    const displayPositions = grouped ? sortPositionsGrouped(positions) : positions;

    let prevUnderlying = null;
    let prevAccount = null;

    let rowsHtml = displayPositions.map(pos => {
        const symbolBadgeClass = getSymbolBadgeClass(pos.symbol);
        const pl = getPLFormatting(pos['P/L']);
        const plPercent = getPLPercentFormatting(pos['P/L%']);

        const dteDisplay = pos.dte >= 0 ? pos.dte : '-';
        const deltaDisplay = pos.delta !== 0 ? formatNumber(pos.delta, 2) : '-';
        const mprDisplay = pos.mpr !== 0 ? formatPercent(pos.mpr) : '-';

        const hasOptionsMetrics = (pos.dte >= 0) || (pos.delta !== 0) || (pos.mpr !== 0);
        const optMetricsClass = hasOptionsMetrics ? '' : 'hide-if-empty';

        let groupHeaderHtml = '';
        if (grouped) {
            const underlying = baseUnderlying(pos.symbol);
            if (underlying !== prevUnderlying || pos.accountNumber !== prevAccount) {
                const colCount = 11;
                groupHeaderHtml = `<tr class="group-header-row"><td colspan="${colCount}">${pos.accountNumber} &mdash; ${underlying}</td></tr>`;
                prevUnderlying = underlying;
                prevAccount = pos.accountNumber;
            }
        } else {
            if (pos.accountNumber !== prevAccount) {
                const colCount = 11;
                groupHeaderHtml = `<tr class="group-header-row"><td colspan="${colCount}">Account: ${pos.accountNumber}</td></tr>`;
                prevAccount = pos.accountNumber;
                prevUnderlying = null;
            }
        }

        return groupHeaderHtml + `
            <tr>
                <!-- Desktop Columns (hidden on mobile) -->
                <td class="desktop-only-col" data-label="Symbol"><span class="${symbolBadgeClass}">${pos.symbol}</span></td>
                <td class="desktop-only-col" style="text-align: right;">${pos.quantity}</td>
                <td class="desktop-only-col" style="text-align: right;">${formatCurrency(pos['cost/share'])}</td>
                <td class="desktop-only-col" style="text-align: right;">${formatCurrency(pos['value/share'])}</td>
                <td class="desktop-only-col" style="text-align: right;">${formatCurrency(pos.cost)}</td>
                <td class="desktop-only-col" style="text-align: right;">${formatCurrency(pos.marketValue)}</td>
                <td class="desktop-only-col" style="text-align: right;" class="${pl.cssClass}">${pl.sign}${pl.valDisplay}</td>
                <td class="desktop-only-col" style="text-align: right;" class="${plPercent.cssClass}">${plPercent.sign}${plPercent.valDisplay}</td>
                <td class="desktop-only-col" style="text-align: center;">${dteDisplay}</td>
                <td class="desktop-only-col" style="text-align: center;">${deltaDisplay}</td>
                <td class="desktop-only-col" style="text-align: center;">${mprDisplay}</td>

                <!-- Mobile Only Combined Row Layout (hidden on desktop) -->
                <td class="mobile-only-card-col" colspan="11">
                    <div class="mobile-split-row header-row">
                        <div class="split-col col-symbol"><span>${pos.quantity} x ${pos.symbol}</span></div>
                        <div class="split-col col-pl ${pl.cssClass}" style="text-align: right; font-weight: 700;">${pl.sign}${pl.valDisplay} <span class="mobile-pl-pct">(${plPercent.sign}${plPercent.valDisplay})</span></div>
                    </div>
                    <div class="mobile-split-row details-row">
                        <div class="split-col col-cost"">${formatCurrency(pos.marketValue)} / ${formatCurrency(pos.cost)}</div>
                        <div class="split-col col-prices" style="text-align: right;">${formatCurrency(pos['value/share'])} / ${formatCurrency(pos['cost/share'])}</div>
                    </div>
                    ${hasOptionsMetrics ? `
                    <div class="mobile-split-row options-row">
                        <div class="split-col col-dte">DTE: ${dteDisplay} | &Delta;: ${deltaDisplay}</div>
                        <div class="split-col col-mpr" style="text-align: right;">MPR: ${mprDisplay}</div>
                    </div>
                    ` : ''}
                </td>
            </tr>
        `;
    }).join('');

    container.innerHTML = `
        <div class="table-responsive">
            <table>
                <thead>
                    <tr>
                        <th>Symbol</th>
                        <th style="text-align: right;">Qty</th>
                        <th style="text-align: right;">Cost/Share</th>
                        <th style="text-align: right;">Mark</th>
                        <th style="text-align: right;">Cost Basis</th>
                        <th style="text-align: right;">Market Value</th>
                        <th style="text-align: right;">P/L</th>
                        <th class="desktop-only-pl-pct" style="text-align: right;">P/L%</th>
                        <th style="text-align: center;">DTE</th>
                        <th style="text-align: center;">Delta</th>
                        <th style="text-align: center;">MPR</th>
                    </tr>
                </thead>
                <tbody>
                    ${rowsHtml}
                </tbody>
            </table>
        </div>
    `;
}



export function renderOrders(orders) {
    const container = document.getElementById('orders-container');
    if (!orders || orders.length === 0) {
        container.innerHTML = `<div class="no-data-msg"><p>No active working orders found.</p></div>`;
        return;
    }

    let rowsHtml = orders.map(ord => {
        const symbolBadgeClass = getSymbolBadgeClass(ord.symbol);

        const pl = getPLFormatting(ord['P/L']);
        const plPercent = getPLPercentFormatting(ord['P/L%']);

        const qtyDisplay = ord.quantity !== null && ord.quantity !== undefined ? ord.quantity : '-';
        const costShareDisplay = ord['cost/share'] ? formatCurrency(ord['cost/share']) : '-';
        const valShareDisplay = ord['value/share'] ? formatCurrency(ord['value/share']) : '-';
        const dteDisplay = ord.dte >= 0 ? ord.dte : '-';
        const deltaDisplay = ord.delta ? formatNumber(ord.delta, 2) : '-';
        const mprDisplay = ord.mpr ? formatPercent(ord.mpr) : '-';

        const hasOptionsMetrics = (ord.dte >= 0) || (!!ord.delta) || (!!ord.mpr);
        const optMetricsClass = hasOptionsMetrics ? '' : 'hide-if-empty';

        return `
            <tr>
                <!-- Desktop Columns (hidden on mobile) -->
                <td class="desktop-only-col" data-label="Symbol"><span class="${symbolBadgeClass}">${ord.symbol}</span></td>
                <td class="desktop-only-col"><strong style="color:var(--accent-blue)">${ord.order}</strong></td>
                <td class="desktop-only-col" style="text-align: right;">${qtyDisplay}</td>
                <td class="desktop-only-col" style="text-align: right;">${costShareDisplay}</td>
                <td class="desktop-only-col" style="text-align: right;">${valShareDisplay}</td>
                <td class="desktop-only-col" style="text-align: right;" class="${pl.cssClass}">${pl.sign}${pl.valDisplay}</td>
                <td class="desktop-only-col" style="text-align: right;" class="${plPercent.cssClass}">${plPercent.sign}${plPercent.valDisplay}</td>
                <td class="desktop-only-col" style="text-align: center;">${dteDisplay}</td>
                <td class="desktop-only-col" style="text-align: center;">${deltaDisplay}</td>
                <td class="desktop-only-col" style="text-align: center;">${mprDisplay}</td>

                <!-- Mobile Only Combined Row Layout (hidden on desktop) -->
                <td class="mobile-only-card-col" colspan="10">
                    <div class="mobile-split-row header-row">
                        <div class="split-col col-symbol"><span class="${symbolBadgeClass}">${ord.symbol}</span></div>
                        <div class="split-col col-order" style="text-align: right; font-weight: 700;"><strong style="color:var(--accent-blue)">${ord.order}</strong></div>
                        <div class="split-col col-pl ${pl.cssClass}" style="text-align: right; font-weight: 700;">${pl.sign}${pl.valDisplay} <span class="mobile-pl-pct">(${plPercent.sign}${plPercent.valDisplay})</span></div>
                    </div>
                    <div class="mobile-split-row details-row">
                        <div class="split-col col-qty">Qty: ${qtyDisplay}</div>
                        <div class="split-col col-cost" style="text-align: right;">Mark: ${valShareDisplay}</div>
                        <div class="split-col col-prices" style="text-align: right;">Cost: ${costShareDisplay}</div>
                    </div>
                    ${hasOptionsMetrics ? `
                    <div class="mobile-split-row options-row">
                        <div class="split-col col-dte">DTE: ${dteDisplay}</div>
                        <div class="split-col col-delta" style="text-align: right;">&Delta;: ${deltaDisplay}</div>
                        <div class="split-col col-mpr" style="text-align: right;">MPR: ${mprDisplay}</div>
                    </div>
                    ` : ''}
                </td>
            </tr>
        `;
    }).join('');

    container.innerHTML = `
        <div class="table-responsive">
            <table>
                <thead>
                    <tr>
                        <th>Symbol</th>
                        <th>Order</th>
                        <th style="text-align: right;">Pos Qty</th>
                        <th style="text-align: right;">Pos Cost/Shr</th>
                        <th style="text-align: right;">Pos Mark</th>
                        <th style="text-align: right;">Pos P/L</th>
                        <th class="desktop-only-pl-pct" style="text-align: right;">Pos P/L%</th>
                        <th style="text-align: center;">DTE</th>
                        <th style="text-align: center;">Delta</th>
                        <th style="text-align: center;">MPR</th>
                    </tr>
                </thead>
                <tbody>
                    ${rowsHtml}
                </tbody>
            </table>
        </div>
    `;
}

export function renderUnderlyingBanner(underlying, totalContracts, matchingCount) {
    const container = document.getElementById('chain-underlying-container');
    if (!underlying || !underlying.symbol) {
        container.innerHTML = '';
        return;
    }

    const changeVal = underlying.change || 0.0;
    const changeClass = changeVal >= 0 ? 'val-positive' : 'val-negative';
    const changeSign = changeVal >= 0 ? '+' : '';
    const pctVal = underlying.percentChange || 0.0;

    const totalStr = totalContracts ? `${matchingCount} / ${totalContracts}` : `${matchingCount}`;

    container.innerHTML = `
        <div class="underlying-banner">
            <div>
                <span class="underlying-title">${underlying.symbol}</span>
                <span style="margin-left: 12px; font-size: 1.4rem; font-weight: 700;">${formatCurrency(underlying.price)}</span>
                <span class="${changeClass}" style="margin-left: 8px; font-size: 1rem;">
                    ${changeSign}${formatNumber(changeVal)} (${changeSign}${formatNumber(pctVal, 2)}%)
                </span>
            </div>
            <div class="underlying-stats">
                <div class="underlying-stat">
                    <span class="underlying-stat-label">Matching Contracts</span>
                    <span class="underlying-stat-value" id="chain-contracts-count">${totalStr}</span>
                </div>
            </div>
        </div>
    `;
}

export function renderOptionChainTable(contracts) {
    const container = document.getElementById('chain-container');
    if (!contracts || contracts.length === 0) {
        container.innerHTML = `<div class="no-data-msg"><p>No option contracts match the selected filters.</p></div>`;
        return;
    }

    let prevDte = null;
    let dteGroupIndex = 0;

    let rowsHtml = contracts.map(opt => {
        const deltaDisplay = opt.delta !== 0 ? formatNumber(opt.delta, 2) : '-';
        const ivDisplay = opt.volatility ? formatNumber(opt.volatility, 1) + '%' : '-';
        const mprDisplay = opt.mpr ? formatPercent(opt.mpr) : '-';

        const changeVal = opt.change || 0.0;
        const changeClass = changeVal >= 0 ? 'val-positive' : 'val-negative';
        const changeSign = changeVal >= 0 ? '+' : '';

        const beChangeVal = opt.beChange || 0.0;
        const beChangeClass = beChangeVal >= 0 ? 'val-positive' : 'val-negative';
        const beChangeSign = beChangeVal >= 0 ? '+' : '';

        let dteGroupHeaderHtml = '';
        if (opt.dte !== prevDte) {
            if (prevDte !== null) {
                dteGroupIndex++;
            }
            prevDte = opt.dte;
            dteGroupHeaderHtml = `
                <tr class="dte-group-row">
                    <td colspan="7">
                        <div class="dte-header-content">
                            <span class="dte-group-pill">${opt.dte} DTE</span>
                            <span class="dte-group-date">Expiration: <strong>${opt.expirationDate}</strong></span>
                        </div>
                    </td>
                </tr>
            `;
        }

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
            </tr>
        `;
    }).join('');

    container.innerHTML = `
        <div class="table-responsive">
            <table>
                <thead>
                    <tr>
                        <th style="text-align: right;">Strike</th>
                        <th style="text-align: right;">Mark</th>
                        <th style="text-align: center;">Delta</th>
                        <th style="text-align: center;">MPR</th>
                        <th style="text-align: center;">Strike %</th>
                        <th style="text-align: right;">BE %</th>
                        <th style="text-align: right;">IV</th>
                    </tr>
                </thead>
                <tbody>
                    ${rowsHtml}
                </tbody>
            </table>
        </div>
    `;
}

export function renderBoxes(boxes) {
    const container = document.getElementById('box-container');
    if (!boxes || boxes.length === 0) {
        container.innerHTML = `<div class="no-data-msg"><p>No SPX box spreads found for the selected criteria. Try adjusting the date range or box size.</p></div>`;
        return;
    }

    let prevExpDate = null;

    let rowsHtml = boxes.map(box => {
        const rateClass = box.rate >= 5.5 ? 'val-positive' : (box.rate >= 4.5 ? '' : 'val-negative');

        let expHeaderHtml = '';
        if (box.expirationDate !== prevExpDate) {
            prevExpDate = box.expirationDate;
            expHeaderHtml = `<tr class="group-header-row"><td colspan="9">Expiration: ${box.expirationDate} &mdash; ${box.dte} DTE</td></tr>`;
        }

        return expHeaderHtml + `
            <tr>
                <td style="text-align: center; font-weight: 600; color: var(--text-secondary);">${box.size}</td>
                <td style="text-align: right; font-weight: 700;">$${formatNumber(box.btoPut, 0)}</td>
                <td style="text-align: right; font-weight: 700;">$${formatNumber(box.stoPut, 0)}</td>
                <td style="text-align: right; font-weight: 700;">$${formatNumber(box.stoCall, 0)}</td>
                <td style="text-align: right; font-weight: 700;">$${formatNumber(box.btoCall, 0)}</td>
                <td style="text-align: right; font-weight: 600;">$${formatNumber(box.netCredit, 2)}</td>
                <td style="text-align: right;" class="${rateClass} font-weight: 700;">${formatNumber(box.rate, 2)}%</td>
                <td style="text-align: right; color: var(--text-secondary);">${box.liquidity.toLocaleString()}</td>
            </tr>
        `;
    }).join('');

    container.innerHTML = `
        <div class="table-responsive">
            <table>
                <thead>
                    <tr>
                        <th style="text-align: center;">Size</th>
                        <th style="text-align: right;">BTO PUT</th>
                        <th style="text-align: right;">STO PUT</th>
                        <th style="text-align: right;">STO CALL</th>
                        <th style="text-align: right;">BTO CALL</th>
                        <th style="text-align: right;">Net Credit</th>
                        <th style="text-align: right;">Ann. Rate</th>
                        <th style="text-align: right;">Liquidity</th>
                    </tr>
                </thead>
                <tbody>
                    ${rowsHtml}
                </tbody>
            </table>
        </div>
    `;
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
        container.innerHTML = `<div class="no-data-msg"><p>No transactions stored yet. Click <strong>Sync</strong> to fetch from Schwab.</p></div>`;
        if (statsBar) statsBar.style.display = 'none';
        return;
    }

    // --- Populate stats bar ---
    if (statsBar) {
        const times = transactions.map(t => t.time).filter(Boolean).sort();
        document.getElementById('txn-stat-count').textContent = transactions.length;
        document.getElementById('txn-stat-earliest').textContent = _shortDate(times[0]);
        document.getElementById('txn-stat-latest').textContent = _shortDate(times[times.length - 1]);
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

        const netClass = (txn.netAmount || 0) >= 0 ? 'val-positive' : 'val-negative';
        const netSign = (txn.netAmount || 0) >= 0 ? '+' : '';

        const symbolBadgeClass = symbol.length > 4 ? 'badge-option' : 'badge-equity';

        return `
            <tr>
                <td style="color:var(--text-secondary); font-size:0.82rem;">${_shortDate(txn.time)}</td>
                <td>${_typeBadge(txn.type)}</td>
                <td><span class="${symbolBadgeClass}">${symbol !== 'CURRENCY_USD' ? symbol : '—'}</span></td>
                <td style="font-size:0.75rem; color:var(--text-secondary); max-width:120px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">${assetType}</td>
                <td class="${_effectClass(posEffect)}" style="text-align:center; font-size:0.8rem; font-weight:600;">${posEffect || '—'}</td>
                <td style="text-align:right;">${amountDisplay}</td>
                <td style="text-align:right;">${priceDisplay}</td>
                <td style="text-align:right; font-weight:600;" class="${netClass}">${netSign}${formatCurrency(txn.netAmount)}</td>
            </tr>
        `;
    }).join('');

    container.innerHTML = `
        <div class="table-responsive">
            <table>
                <thead>
                    <tr>
                        <th>Date</th>
                        <th>Type</th>
                        <th>Symbol</th>
                        <th>Asset</th>
                        <th style="text-align:center;">Effect</th>
                        <th style="text-align:right;">Qty</th>
                        <th style="text-align:right;">Price</th>
                        <th style="text-align:right;">Net Amount</th>
                    </tr>
                </thead>
                <tbody>
                    ${rowsHtml}
                </tbody>
            </table>
        </div>
    `;
}

export function renderRealized(realizedList) {
    const container = document.getElementById('realized-container');
    const pivotContainer = document.getElementById('realized-pivot-container');

    if (!realizedList || realizedList.length === 0) {
        container.innerHTML = `<div class="no-data-msg"><p>No realized transactions match the criteria.</p></div>`;
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


        const headerCols = symbols.map(sym => `<th style="text-align:right;">${sym}</th>`).join('');

        const rows = months.map(m => {
            const cells = symbols.map(sym => {
                const val = pivotData[sym][m];
                const cls = val > 0 ? 'val-positive' : (val < 0 ? 'val-negative' : '');
                const displayVal = val !== 0 ? formatCurrency(val) : '—';
                return `<td style="text-align:right;" class="${cls}">${displayVal}</td>`;
            }).join('');

            const mTotal = monthTotals[m];
            const mTotalCls = mTotal > 0 ? 'val-positive' : (mTotal < 0 ? 'val-negative' : '');
            const mTotalDisplay = mTotal !== 0 ? formatCurrency(mTotal) : '—';

            return `
                <tr>
                    <td style="font-weight:600;">${m}</td>
                    ${cells}
                    <td style="text-align:right; font-weight:600;" class="${mTotalCls}">${mTotalDisplay}</td>
                </tr>
            `;
        }).join('');

        const totalCells = symbols.map(sym => {
            const val = symbolTotals[sym];
            const cls = val > 0 ? 'val-positive' : (val < 0 ? 'val-negative' : '');
            const displayVal = val !== 0 ? formatCurrency(val) : '—';
            return `<td style="text-align:right; font-weight:600;" class="${cls}">${displayVal}</td>`;
        }).join('');

        const grandTotalCls = grandTotal > 0 ? 'val-positive' : (grandTotal < 0 ? 'val-negative' : '');
        const grandTotalDisplay = grandTotal !== 0 ? formatCurrency(grandTotal) : '—';

        pivotContainer.innerHTML = `
            <div class="section-card" style="margin-bottom: 20px;">
                <h3 style="margin-bottom: 12px;">Monthly P/L by Symbol</h3>
                <div class="table-responsive">
                    <table>
                        <thead>
                            <tr>
                                <th>Month</th>
                                ${headerCols}
                                <th style="text-align:right;">Total</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${rows}
                        </tbody>
                        <tfoot>
                            <tr style="border-top: 2px solid var(--border-color); font-weight:600;">
                                <td>Total</td>
                                ${totalCells}
                                <td style="text-align:right; font-weight:800;" class="${grandTotalCls}">${grandTotalDisplay}</td>
                            </tr>
                        </tfoot>
                    </table>
                </div>
            </div>
        `;

    }

    let rowsHtml = realizedList.map(r => {
        const symbol = r.symbol || '—';
        const symbolBadgeClass = symbol.length > 4 ? 'badge-option' : 'badge-equity';
        const pl = r['P/L'] || 0;
        const plClass = pl >= 0 ? 'val-positive' : 'val-negative';
        const plSign = pl >= 0 ? '+' : '';

        return `
            <tr>
                <td style="color:var(--text-secondary); font-size:0.82rem;">${_shortDate(r.buy_date)}</td>
                <td style="text-align:right;">${formatCurrency(r.buy_price)}</td>
                <td style="color:var(--text-secondary); font-size:0.82rem;">${_shortDate(r.sell_date)}</td>
                <td style="text-align:right;">${formatCurrency(r.sell_price)}</td>
                <td><span class="${symbolBadgeClass}">${symbol}</span></td>
                <td style="text-align:right;">${formatNumber(r.amount, 0)}</td>
                <td style="text-align:right; font-weight:600;" class="${plClass}">${plSign}${formatCurrency(pl)}</td>
            </tr>
        `;
    }).join('');

    container.innerHTML = `
        <div class="table-responsive">
            <table>
                <thead>
                    <tr>
                        <th>Open Date</th>
                        <th style="text-align:right;">Open Price</th>
                        <th>Close Date</th>
                        <th style="text-align:right;">Close Price</th>
                        <th>Symbol</th>
                        <th style="text-align:right;">Qty</th>
                        <th style="text-align:right;">Realized P/L</th>
                    </tr>
                </thead>
                <tbody>
                    ${rowsHtml}
                </tbody>
            </table>
        </div>
    `;
}




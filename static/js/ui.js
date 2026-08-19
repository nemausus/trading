import {
    formatCurrency, formatPercent, formatNumber,
    baseUnderlying, sortPositionsGrouped,
    getPLFormatting, getPLPercentFormatting, getSymbolBadgeClass
} from './utils.js';

export let lastPositions = [];
export let lastOrders = [];

export function showView(viewId) {
    document.querySelectorAll('.view').forEach(view => {
        view.classList.remove('active-view');
    });
    document.getElementById(viewId).classList.add('active-view');
}

export function clearDashboard() {
    const posContainer = document.getElementById('positions-container');
    if (posContainer) {
        posContainer.innerHTML = `
            <div class="no-data-msg">
                <p>Connect your Schwab account to retrieve positions.</p>
            </div>
        `;
    }

    const chainContainer = document.getElementById('chain-container');
    if (chainContainer) {
        chainContainer.innerHTML = `<div class="no-data-msg"><p>Enter a symbol and click "Fetch Chain" to retrieve option contracts.</p></div>`;
    }

    const boxContainer = document.getElementById('box-container');
    if (boxContainer) {
        boxContainer.innerHTML = `<div class="no-data-msg"><p>Select a date range and click "Find Boxes" to scan for SPX box spread opportunities.</p></div>`;
    }

    const txnContainer = document.getElementById('transactions-container');
    if (txnContainer) {
        txnContainer.innerHTML = `<div class="no-data-msg"><p>No transactions stored yet. Click <strong>Sync</strong> to fetch from Schwab.</p></div>`;
    }

    const realizedContainer = document.getElementById('realized-container');
    if (realizedContainer) {
        realizedContainer.innerHTML = `<div class="no-data-msg"><p>Loading realized transactions...</p></div>`;
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

export function renderSummaries(summaries) {
    renderUnifiedAccounts(summaries, lastPositions, lastOrders);
}

export function renderPositions(positions) {
    lastPositions = positions || [];
    renderUnifiedAccounts([], lastPositions, lastOrders);
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
        container.innerHTML = `<div class="no-data-msg"><p>No open positions or account data found in Schwab accounts.</p></div>`;
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
        container.innerHTML = `<div class="no-data-msg"><p>No open positions found in Schwab accounts.</p></div>`;
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
            const todoItems = sum.Todo ? sum.Todo.split(',').map(s => s.trim()) : [];
            const todoPillsHtml = todoItems.length > 0
                ? `<div class="todo-list-pills" style="margin-top: 0; display: inline-flex;">${todoItems.map(item => `<span class="todo-pill">${item}</span>`).join('')}</div>`
                : `<span style="color: var(--accent-green); font-weight:600; font-size:0.78rem;">Covered / Complete</span>`;

            let riskClass = "risk-low";
            if (sum.Risk < 90) riskClass = "risk-high";
            else if (sum.Risk < 95) riskClass = "risk-med";

            summaryBarHtml = `
                <div class="account-summary-bar" style="padding: 10px 16px; background-color: var(--bg-tertiary); border-bottom: 1px solid var(--border-color);">
                    <div style="display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 12px; font-size: 0.84rem;">
                        <div style="display: flex; align-items: center; gap: 12px;">
                            <strong style="font-size: 0.98rem; color: var(--accent-blue);">Account ${sum.accountNumber}</strong>
                            <span style="font-size: 0.98rem; font-weight: 700; color: var(--text-primary);">Net: ${formatCurrency(sum.Net)}</span>
                        </div>
                        <div style="display: flex; flex-wrap: wrap; align-items: center; gap: 14px;">
                            <span>Cash: <strong>${formatCurrency(sum.Cash)}</strong></span>
                            <span>Loan: <strong>${formatCurrency(sum['Total Loan'])}</strong> <span style="font-size:0.75rem; color:var(--text-secondary);">(Margin: ${formatCurrency(sum.Margin)} | Box: ${formatCurrency(sum.BOX)} | CSP: ${formatCurrency(sum.CSP)})</span></span>
                            <span>Risk: <strong class="${riskClass}">${formatPercent(sum.Risk)}</strong></span>
                            <div style="display: inline-flex; align-items: center; gap: 6px;">
                                <span style="color: var(--text-secondary); font-weight: 600; font-size: 0.78rem;">Action:</span>
                                ${todoPillsHtml}
                            </div>
                        </div>
                    </div>
                </div>
            `;
        } else {
            summaryBarHtml = `
                <div class="account-summary-bar" style="padding: 10px 16px; background-color: var(--bg-tertiary); border-bottom: 1px solid var(--border-color);">
                    <strong style="font-size: 0.98rem; color: var(--accent-blue);">Account ${accNum}</strong>
                </div>
            `;
        }

        // Render Positions Table / Cards for this account
        let tableHtml = '';
        if (accPositions.length === 0) {
            tableHtml = `<div class="no-data-msg" style="padding: 16px;"><p>No open positions in this account.</p></div>`;
        } else {
            tableHtml = `
                <div class="table-responsive">
                    <table>
                        <thead>
                            <tr>
                                <th>Symbol</th>
                                <th class="text-right">Qty</th>
                                <th class="text-right">Cost/Share</th>
                                <th class="text-right">Mark</th>
                                <th class="text-right">Mark %</th>
                                <th class="text-right">Cost Basis</th>
                                <th class="text-right">Market Value</th>
                                <th class="text-right">P/L</th>
                                <th class="desktop-only-pl-pct text-right">P/L%</th>
                                <th class="text-center">DTE</th>
                                <th class="text-center">Delta</th>
                                <th class="text-center">MPR</th>
                            </tr>
                        </thead>
                        <tbody>
            `;

            let prevUnderlying = null;
            let currentGroupIndex = 0;

            accPositions.forEach((pos, index) => {
                const underlying = baseUnderlying(pos.symbol);

                if (underlying !== prevUnderlying) {
                    currentGroupIndex++;
                    prevUnderlying = underlying;
                }

                const groupBgClass = (currentGroupIndex % 2 === 0) ? 'group-bg-even' : 'group-bg-odd';
                const isGroupStart = (index === 0 || baseUnderlying(accPositions[index - 1].symbol) !== underlying);
                const groupStartClass = isGroupStart ? 'group-start-row' : '';
                const isGroupEnd = (index === accPositions.length - 1 || baseUnderlying(accPositions[index + 1].symbol) !== underlying);

                const symbolBadgeClass = getSymbolBadgeClass(pos.symbol);
                const pl = getPLFormatting(pos['P/L']);
                const plPercent = getPLPercentFormatting(pos['P/L%']);

                const markPctDisplay = (pos.markPercentChange !== undefined && pos.markPercentChange !== null)
                    ? getPLPercentFormatting(pos.markPercentChange)
                    : { valDisplay: '-', cssClass: '', sign: '' };

                const dteDisplay = pos.dte >= 0 ? pos.dte : '-';
                const deltaDisplay = pos.delta !== 0 ? formatNumber(pos.delta, 2) : '-';
                const mprDisplay = pos.mpr !== 0 ? formatPercent(pos.mpr) : '-';
                const hasOptionsMetrics = (pos.dte >= 0) || (pos.delta !== 0) || (pos.mpr !== 0);

                const dteCssClass = (pos.dte >= 0 && pos.dte < 14) ? 'val-negative' : '';
                let deltaCssClass = '';
                if (pos.delta !== undefined && pos.delta !== 0) {
                    deltaCssClass = Math.abs(pos.delta) < 0.50 ? 'val-positive' : 'val-negative';
                }

                const groupEndClass = isGroupEnd ? 'group-end-row' : '';

                let spacerHtml = '';
                if (index > 0 && isGroupStart) {
                    spacerHtml = `<tr class="group-spacer-row"><td colspan="12"></td></tr>`;
                }

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
                            <tr class="${groupBgClass} pending-order-row ${orderRowGroupEndClass}" style="font-size: 0.78rem;">
                                <td class="desktop-only-col" style="padding-left: 16px;"><span class="badge-pending-order" style="font-size: 0.7rem; padding: 1px 6px; background: rgba(148, 163, 184, 0.12); color: var(--text-secondary); border-radius: 4px; font-weight: 500;">⚡ Order</span></td>
                                <td class="desktop-only-col" style="text-align: right; color: var(--text-secondary); font-weight: 400;">${ord.quantity}</td>
                                <td class="desktop-only-col" colspan="6" style="text-align: left; color: var(--text-secondary); font-weight: 400;">
                                    <span>${ordType}</span> @ ${ordPrice} <span style="font-size:0.73rem; opacity:0.75;">(${ord.orderType || ''} ${ord.duration || ''})</span>
                                </td>
                                <td class="desktop-only-col" style="text-align: right;"><span style="font-size: 0.7rem; padding: 1px 6px; background: rgba(245, 158, 11, 0.12); color: #d97706; border-radius: 4px; font-weight: 500;">${ordStatus}</span></td>
                                <td class="desktop-only-col" colspan="3"></td>
                            </tr>
                        `;

                        pendingOrdersMobileHtml += `
                            <div class="mobile-split-row pending-order-row" style="border-top: 1px dashed rgba(148, 163, 184, 0.25); margin-top: 5px; padding-top: 4px; padding-bottom: 2px; color: var(--text-secondary); font-size: 0.76rem;">
                                <div class="split-col"><span>⚡ Order: ${ordType} ${ord.quantity} @ ${ordPrice}</span></div>
                                <div class="split-col" style="text-align: right;"><span style="font-size: 0.68rem; padding: 1px 5px; background: rgba(245, 158, 11, 0.12); color: #d97706; border-radius: 4px; font-weight: 500;">${ordStatus}</span></div>
                            </div>
                        `;
                    });
                }

                tableHtml += spacerHtml + `
                    <tr class="${groupBgClass} ${groupStartClass} ${groupEndClass}">
                        <!-- Desktop Columns -->
                        <td class="desktop-only-col" data-label="Symbol"><span class="${symbolBadgeClass}">${pos.symbol}</span></td>
                        <td class="desktop-only-col" style="text-align: right;">${pos.quantity}</td>
                        <td class="desktop-only-col" style="text-align: right;">${formatCurrency(pos['cost/share'])}</td>
                        <td class="desktop-only-col" style="text-align: right;">${formatCurrency(pos['value/share'])}</td>
                        <td class="desktop-only-col ${markPctDisplay.cssClass}" style="text-align: right;">${markPctDisplay.valDisplay !== '-' ? `${markPctDisplay.sign}${markPctDisplay.valDisplay}` : '-'}</td>
                        <td class="desktop-only-col" style="text-align: right;">${formatCurrency(pos.cost)}</td>
                        <td class="desktop-only-col" style="text-align: right;">${formatCurrency(pos.marketValue)}</td>
                        <td class="desktop-only-col ${pl.cssClass}" style="text-align: right;">${pl.sign}${pl.valDisplay}</td>
                        <td class="desktop-only-col ${plPercent.cssClass}" style="text-align: right;">${plPercent.sign}${plPercent.valDisplay}</td>
                        <td class="desktop-only-col ${dteCssClass}" style="text-align: center;">${dteDisplay}</td>
                        <td class="desktop-only-col ${deltaCssClass}" style="text-align: center;">${deltaDisplay}</td>
                        <td class="desktop-only-col" style="text-align: center;">${mprDisplay}</td>

                        <!-- Mobile Only Combined Row Layout -->
                        <td class="mobile-only-card-col" colspan="12">
                            <div class="mobile-split-row header-row">
                                <div class="split-col col-symbol"><span>${pos.quantity} x ${pos.symbol}</span></div>
                                <div class="split-col col-pl ${pl.cssClass}" style="text-align: right; font-weight: 700;">${pl.sign}${pl.valDisplay} <span class="mobile-pl-pct">(${plPercent.sign}${plPercent.valDisplay})</span></div>
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
            <div class="section-card account-card" style="margin-bottom: 20px; padding: 0; overflow: hidden; border-radius: 8px;">
                ${summaryBarHtml}
                ${tableHtml}
            </div>
        `;
    });

    container.innerHTML = html;
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
            <div>
                <span class="underlying-title">${underlying.symbol}</span>
                <span style="margin-left: 12px; font-size: 1.4rem; font-weight: 700;">${formatCurrency(underlying.price)}</span>
                <span class="${changeClass}" style="margin-left: 8px; font-size: 1rem;">
                    ${changeSign}${formatNumber(changeVal)} (${changeSign}${formatNumber(pctVal, 2)}%)
                </span>
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

    let rowsHtml = contracts.map((opt, index) => {
        const deltaDisplay = opt.delta !== 0 ? formatNumber(opt.delta, 2) : '-';
        const ivDisplay = opt.volatility ? formatNumber(opt.volatility, 1) + '%' : '-';
        const mprDisplay = opt.mpr ? formatPercent(opt.mpr) : '-';

        const changeVal = opt.change || 0.0;
        const changeClass = changeVal >= 0 ? 'val-positive' : 'val-negative';
        const changeSign = changeVal >= 0 ? '+' : '';

        const beChangeVal = opt.beChange || 0.0;
        const beChangeClass = beChangeVal >= 0 ? 'val-positive' : 'val-negative';
        const beChangeSign = beChangeVal >= 0 ? '+' : '';

        const isNewGroup = opt.dte !== prevDte;
        let dteGroupHeaderHtml = '';
        if (isNewGroup) {
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

        const isGroupStart = isNewGroup;
        const isGroupEnd = (index === contracts.length - 1 || contracts[index + 1].dte !== opt.dte);
        const groupStartClass = isGroupStart ? 'group-start-row' : '';
        const groupEndClass = isGroupEnd ? 'group-end-row' : '';

        const rowBgClass = (dteGroupIndex % 2 === 0) ? 'dte-bg-group-0' : 'dte-bg-group-1';
        const contractTypeClass = opt.contractType === 'CALL' ? 'row-call' : 'row-put';
        const contractTypeBadge = opt.contractType === 'CALL' ? '<span class="badge-call">CALL</span>' : '<span class="badge-put">PUT</span>';

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
                        <th class="text-right">Strike</th>
                        <th class="text-right">Mark</th>
                        <th class="text-center">Delta</th>
                        <th class="text-center">MPR</th>
                        <th class="text-center">Strike %</th>
                        <th class="text-right">BE %</th>
                        <th class="text-right">IV</th>
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

    container.innerHTML = `
        <div class="table-responsive">
            <table>
                <thead>
                    <tr>
                        <th class="text-center">Size</th>
                        <th class="text-right">BTO PUT</th>
                        <th class="text-right">STO PUT</th>
                        <th class="text-right">STO CALL</th>
                        <th class="text-right">BTO CALL</th>
                        <th class="text-right">Net Credit</th>
                        <th class="text-right">Ann. Rate</th>
                        <th class="text-right">Liquidity</th>
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
        const earliestEl = document.getElementById('txn-stat-earliest');
        const latestEl = document.getElementById('txn-stat-latest');
        if (earliestEl) earliestEl.textContent = _shortDate(times[0]);
        if (latestEl) latestEl.textContent = _shortDate(times[times.length - 1]);
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
                <td class="desktop-only-col" style="color:var(--text-secondary); font-size:0.82rem;">${_shortDate(txn.time)}</td>
                <td class="desktop-only-col">${_typeBadge(txn.type)}</td>
                <td class="desktop-only-col"><span class="${symbolBadgeClass}">${displaySym}</span></td>
                <td class="desktop-only-col" style="font-size:0.75rem; color:var(--text-secondary); max-width:120px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">${assetType}</td>
                <td class="desktop-only-col ${effectCls}" style="text-align:center; font-size:0.8rem; font-weight:600;">${posEffect || '—'}</td>
                <td class="desktop-only-col" style="text-align:right;">${amountDisplay}</td>
                <td class="desktop-only-col" style="text-align:right;">${priceDisplay}</td>
                <td class="desktop-only-col" style="text-align:right; font-weight:600;" class="${netPL.cssClass}">${netPL.sign}${netPL.valDisplay}</td>

                <!-- Mobile Only Combined Row Layout -->
                <td class="mobile-only-card-col" colspan="8">
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

    container.innerHTML = `
        <div class="table-responsive">
            <table>
                <thead>
                    <tr>
                        <th>Date</th>
                        <th>Type</th>
                        <th>Symbol</th>
                        <th>Asset</th>
                        <th class="text-center">Effect</th>
                        <th class="text-right">Qty</th>
                        <th class="text-right">Price</th>
                        <th class="text-right">Net Amount</th>
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
        const symbolBadgeClass = getSymbolBadgeClass(symbol);
        const plFormat = getPLFormatting(r['P/L'] || 0);

        return `
            <tr>
                <!-- Desktop Columns -->
                <td class="desktop-only-col" style="color:var(--text-secondary); font-size:0.82rem;">${_shortDate(r.buy_date)}</td>
                <td class="desktop-only-col" style="text-align:right;">${formatCurrency(r.buy_price)}</td>
                <td class="desktop-only-col" style="color:var(--text-secondary); font-size:0.82rem;">${_shortDate(r.sell_date)}</td>
                <td class="desktop-only-col" style="text-align:right;">${formatCurrency(r.sell_price)}</td>
                <td class="desktop-only-col"><span class="${symbolBadgeClass}">${symbol}</span></td>
                <td class="desktop-only-col" style="text-align:right;">${formatNumber(r.amount, 0)}</td>
                <td class="desktop-only-col" style="text-align:right; font-weight:600;" class="${plFormat.cssClass}">${plFormat.sign}${plFormat.valDisplay}</td>

                <!-- Mobile Only Combined Row Layout -->
                <td class="mobile-only-card-col" colspan="7">
                    <div class="mobile-split-row header-row">
                        <div class="split-col col-symbol">
                            <span class="${symbolBadgeClass}">${symbol}</span>
                            <span style="color: var(--text-secondary); font-size:0.75rem; margin-left:6px;">Qty: ${formatNumber(r.amount, 0)}</span>
                        </div>
                        <div class="split-col ${plFormat.cssClass}" style="text-align: right; font-weight: 700;">${plFormat.sign}${plFormat.valDisplay}</div>
                    </div>
                    <div class="mobile-split-row details-row">
                        <div class="split-col" style="color: var(--text-secondary);">Open: ${formatCurrency(r.buy_price)} <span style="font-size:0.72rem;">(${_shortDate(r.buy_date)})</span></div>
                        <div class="split-col" style="text-align: right; color: var(--text-secondary);">Close: ${formatCurrency(r.sell_price)} <span style="font-size:0.72rem;">(${_shortDate(r.sell_date)})</span></div>
                    </div>
                </td>
            </tr>
        `;
    }).join('');

    container.innerHTML = `
        <div class="table-responsive">
            <table>
                <thead>
                    <tr>
                        <th>Open Date</th>
                        <th class="text-right">Open Price</th>
                        <th>Close Date</th>
                        <th class="text-right">Close Price</th>
                        <th>Symbol</th>
                        <th class="text-right">Qty</th>
                        <th class="text-right">Realized P/L</th>
                    </tr>
                </thead>
                <tbody>
                    ${rowsHtml}
                </tbody>
            </table>
        </div>
    `;
}




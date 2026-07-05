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

        let groupHeaderHtml = '';
        if (grouped) {
            const underlying = baseUnderlying(pos.symbol);
            if (underlying !== prevUnderlying || pos.accountNumber !== prevAccount) {
                const colCount = 11;
                groupHeaderHtml = `<tr class="group-header-row"><td colspan="${colCount}">${pos.accountNumber} &mdash; ${underlying}</td></tr>`;
                prevUnderlying = underlying;
                prevAccount = pos.accountNumber;
            }
        }

        return groupHeaderHtml + `
            <tr>
                <td><span class="${symbolBadgeClass}">${pos.symbol}</span></td>
                <td style="text-align: right;">${pos.quantity}</td>
                <td style="text-align: right;">${formatCurrency(pos['cost/share'])}</td>
                <td style="text-align: right;">${formatCurrency(pos['value/share'])}</td>
                <td style="text-align: right;">${formatCurrency(pos.cost)}</td>
                <td style="text-align: right;">${formatCurrency(pos.marketValue)}</td>
                <td style="text-align: right;" class="${pl.cssClass}">${pl.sign}${pl.valDisplay}</td>
                <td style="text-align: right;" class="${plPercent.cssClass}">${plPercent.sign}${plPercent.valDisplay}</td>
                <td style="text-align: center;">${dteDisplay}</td>
                <td style="text-align: center;">${deltaDisplay}</td>
                <td style="text-align: center;">${mprDisplay}</td>
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
                        <th style="text-align: right;">P/L%</th>
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

        return `
            <tr>
                <td><span class="${symbolBadgeClass}">${ord.symbol}</span></td>
                <td><strong style="color:var(--accent-blue)">${ord.order}</strong></td>
                <td style="text-align: right;">${qtyDisplay}</td>
                <td style="text-align: right;">${costShareDisplay}</td>
                <td style="text-align: right;">${valShareDisplay}</td>
                <td style="text-align: right;" class="${pl.cssClass}">${pl.sign}${pl.valDisplay}</td>
                <td style="text-align: right;" class="${plPercent.cssClass}">${plPercent.sign}${plPercent.valDisplay}</td>
                <td style="text-align: center;">${dteDisplay}</td>
                <td style="text-align: center;">${deltaDisplay}</td>
                <td style="text-align: center;">${mprDisplay}</td>
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
                        <th style="text-align: right;">Pos P/L%</th>
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
                    <td colspan="10">
                        <div class="dte-header-content">
                            <span class="dte-group-pill">${opt.dte} DTE</span>
                            <span class="dte-group-date">Expiration: <strong>${opt.expirationDate}</strong></span>
                        </div>
                    </td>
                </tr>
            `;
        }

        const rowBgClass = (dteGroupIndex % 2 === 0) ? 'dte-bg-group-0' : 'dte-bg-group-1';

        return dteGroupHeaderHtml + `
            <tr class="${rowBgClass}">
                <td><span class="badge-option">${opt.symbol}</span></td>
                <td style="text-align: right; font-weight: 700;">$${formatNumber(opt.strikePrice, 2)}</td>
                <td style="text-align: right;">${formatCurrency(opt.bid)}</td>
                <td style="text-align: right;">${formatCurrency(opt.ask)}</td>
                <td style="text-align: right; font-weight: 600;">${formatCurrency(opt.mark)}</td>
                <td style="text-align: center; font-weight: 600; color: var(--accent-blue);">${deltaDisplay}</td>
                <td style="text-align: center;">${ivDisplay}</td>
                <td style="text-align: center;" class="val-positive">${mprDisplay}</td>
                <td style="text-align: right;" class="${changeClass}">${changeSign}${formatNumber(changeVal, 2)}%</td>
                <td style="text-align: right;" class="${beChangeClass}">${beChangeSign}${formatNumber(beChangeVal, 2)}%</td>
            </tr>
        `;
    }).join('');

    container.innerHTML = `
        <div class="table-responsive">
            <table>
                <thead>
                    <tr>
                        <th>Symbol</th>
                        <th style="text-align: right;">Strike</th>
                        <th style="text-align: right;">Bid</th>
                        <th style="text-align: right;">Ask</th>
                        <th style="text-align: right;">Mark</th>
                        <th style="text-align: center;">Delta</th>
                        <th style="text-align: center;">IV</th>
                        <th style="text-align: center;">MPR</th>
                        <th style="text-align: right;">Strike Δ%</th>
                        <th style="text-align: right;">Break-Even Δ%</th>
                    </tr>
                </thead>
                <tbody>
                    ${rowsHtml}
                </tbody>
            </table>
        </div>
    `;
}

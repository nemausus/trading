import { initializeApp } from "https://www.gstatic.com/firebasejs/10.8.0/firebase-app.js";
import { getAuth, signInWithEmailAndPassword, signOut, onAuthStateChanged } from "https://www.gstatic.com/firebasejs/10.8.0/firebase-auth.js";

const firebaseConfig = {
    apiKey: "AIzaSyA80IB4rvoqoTo0FCaJhg48bWjSm1n2I4g",
    authDomain: "covered-calls-ab5d1.firebaseapp.com",
    projectId: "covered-calls-ab5d1",
    storageBucket: "covered-calls-ab5d1.firebasestorage.app",
    messagingSenderId: "395032013974",
    appId: "1:395032013974:web:ee980f78db6ce8502fe6b7",
    measurementId: "G-YFWTHS1GY3"
};

const app = initializeApp(firebaseConfig);
const auth = getAuth(app);

// Router
function showView(viewId) {
    document.querySelectorAll('.view').forEach(view => {
        view.classList.remove('active-view');
    });
    document.getElementById(viewId).classList.add('active-view');
}

// Parse URL params on load
const urlParams = new URLSearchParams(window.location.search);
const schwabResult = urlParams.get('schwab');
const errorMessage = urlParams.get('message');
if (schwabResult === 'success') {
    alert('Successfully connected to Charles Schwab!');
    window.history.replaceState({}, document.title, window.location.pathname);
} else if (schwabResult === 'error') {
    alert('Schwab Connection Failed: ' + (errorMessage || 'Unknown error'));
    window.history.replaceState({}, document.title, window.location.pathname);
}

// Formatting helpers
function formatCurrency(val) {
    if (val === null || val === undefined || isNaN(val)) return '-';
    return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(val);
}

function formatPercent(val) {
    if (val === null || val === undefined || isNaN(val)) return '-';
    return val.toFixed(2) + '%';
}

function formatNumber(val, decimals = 2) {
    if (val === null || val === undefined || isNaN(val)) return '-';
    return val.toFixed(decimals);
}

// Auth Observer
onAuthStateChanged(auth, (user) => {
    if (user) {
        document.getElementById('user-display-email').innerText = user.email;
        showView('view-main');
        checkSchwabStatus();
    } else {
        showView('view-login');
        clearDashboard();
    }
});

// Event Listeners
document.getElementById('btn-login').addEventListener('click', async () => {
    const email = document.getElementById('email').value;
    const password = document.getElementById('password').value;
    document.getElementById('login-error').innerText = "";

    try {
        await signInWithEmailAndPassword(auth, email, password);
    } catch (error) {
        document.getElementById('login-error').innerText = "Authentication failed: " + error.message;
    }
});

document.getElementById('btn-logout').addEventListener('click', async () => {
    try {
        await signOut(auth);
    } catch (error) {
        console.error("Logout failed", error);
    }
});

document.getElementById('btn-refresh-portfolio').addEventListener('click', fetchSchwabPortfolio);

document.getElementById('btn-group-underlying').addEventListener('click', () => {
    const btn = document.getElementById('btn-group-underlying');
    const isGrouped = btn.dataset.grouped === 'true';
    btn.dataset.grouped = String(!isGrouped);
    btn.classList.toggle('active', !isGrouped);
    if (_lastPositions.length > 0) renderPositions(_lastPositions);
});


async function checkSchwabStatus() {
    const user = auth.currentUser;
    if (!user) return;

    const statusPill = document.getElementById('schwab-status-pill');
    const statusText = document.getElementById('schwab-status-text');
    const actionsDiv = document.getElementById('schwab-actions');
    const refreshBtn = document.getElementById('btn-refresh-portfolio');

    statusText.innerText = "Checking...";
    statusPill.className = "status-pill disconnected";

    try {
        const token = await user.getIdToken();
        const response = await fetch('/api/schwab/status', {
            headers: { 'Authorization': `Bearer ${token}` }
        });
        const data = await response.json();

        if (data.connected) {
            statusText.innerText = "Connected";
            statusPill.className = "status-pill connected";
            refreshBtn.style.display = "inline-block";

            actionsDiv.innerHTML = `
                <button id="btn-disconnect" class="btn-header btn-disconnect">Disconnect</button>
            `;
            document.getElementById('btn-disconnect').addEventListener('click', disconnectSchwab);

            // Auto fetch portfolio details
            fetchSchwabPortfolio();
        } else {
            statusText.innerText = "Disconnected";
            statusPill.className = "status-pill disconnected";
            refreshBtn.style.display = "none";

            actionsDiv.innerHTML = `
                <button id="btn-connect" class="btn-header btn-connect">Connect Schwab</button>
            `;
            document.getElementById('btn-connect').addEventListener('click', connectSchwab);
            clearDashboard();
        }
    } catch (error) {
        console.error("Error checking Schwab status:", error);
        statusText.innerText = "Error";
        statusPill.className = "status-pill disconnected";
        refreshBtn.style.display = "none";
    }
}

async function connectSchwab() {
    const user = auth.currentUser;
    if (!user) return;
    try {
        const token = await user.getIdToken();
        const response = await fetch('/api/auth/schwab', {
            method: 'POST',
            headers: { 'Authorization': `Bearer ${token}` }
        });
        const data = await response.json();
        if (response.ok && data.url) {
            window.location.href = data.url;
        } else {
            alert('Failed to initiate Schwab connection: ' + (data.error || 'Unknown error'));
        }
    } catch (error) {
        console.error("Failed to connect Schwab:", error);
    }
}

async function disconnectSchwab() {
    if (!confirm("Are you sure you want to disconnect your Schwab account? This will revoke access token storage.")) return;
    const user = auth.currentUser;
    if (!user) return;
    try {
        const token = await user.getIdToken();
        const response = await fetch('/api/schwab/disconnect', {
            method: 'POST',
            headers: { 'Authorization': `Bearer ${token}` }
        });
        if (response.ok) {
            checkSchwabStatus();
        } else {
            alert("Failed to disconnect");
        }
    } catch (error) {
        console.error("Disconnect failed", error);
    }
}

async function fetchSchwabPortfolio() {
    const user = auth.currentUser;
    if (!user) return;

    const refreshBtn = document.getElementById('btn-refresh-portfolio');
    const positionsContainer = document.getElementById('positions-container');
    const ordersContainer = document.getElementById('orders-container');

    refreshBtn.disabled = true;
    refreshBtn.innerText = "Refreshing...";

    positionsContainer.innerHTML = `<div class="no-data-msg"><p>Retrieving latest portfolio positions and market quotes...</p></div>`;
    ordersContainer.innerHTML = `<div class="no-data-msg"><p>Retrieving working orders...</p></div>`;

    try {
        const token = await user.getIdToken();
        const response = await fetch('/api/schwab/accounts', {
            headers: { 'Authorization': `Bearer ${token}` }
        });
        const data = await response.json();

        if (response.ok) {
            renderDashboard(data);
        } else {
            const errMsg = data.error || 'Failed to fetch account portfolio';
            positionsContainer.innerHTML = `<div class="no-data-msg" style="color:var(--accent-red)"><p>Error: ${errMsg}</p></div>`;
            ordersContainer.innerHTML = `<div class="no-data-msg" style="color:var(--accent-red)"><p>Error: ${errMsg}</p></div>`;
        }
    } catch (error) {
        console.error("Failed to fetch Schwab portfolio:", error);
        positionsContainer.innerHTML = `<div class="no-data-msg" style="color:var(--accent-red)"><p>Network Error: ${error.message}</p></div>`;
        ordersContainer.innerHTML = `<div class="no-data-msg" style="color:var(--accent-red)"><p>Network Error: ${error.message}</p></div>`;
    } finally {
        refreshBtn.disabled = false;
        refreshBtn.innerText = "Refresh Data";
    }
}

// Cache last-fetched positions so the group toggle can re-render without a new fetch
let _lastPositions = [];

// Extract the base underlying ticker from a symbol (AAPL from 'AAPL  260821C00295000')
function baseUnderlying(symbol) {
    if (symbol.length <= 4) return symbol;
    return symbol.slice(0, 6).trimEnd();
}

// Sort positions grouped: stock/ETF first, then its options, all under the same underlying
function sortPositionsGrouped(positions) {
    return [...positions].sort((a, b) => {
        if (a.accountNumber < b.accountNumber) return -1;
        if (a.accountNumber > b.accountNumber) return 1;
        const ua = baseUnderlying(a.symbol);
        const ub = baseUnderlying(b.symbol);
        if (ua < ub) return -1;
        if (ua > ub) return 1;
        // Within same underlying: equity (short symbol) before options
        const aIsOpt = a.symbol.length > 4;
        const bIsOpt = b.symbol.length > 4;
        if (aIsOpt !== bIsOpt) return aIsOpt ? 1 : -1;
        return a.symbol < b.symbol ? -1 : a.symbol > b.symbol ? 1 : 0;
    });
}

function renderDashboard(data) {
    _lastPositions = data.positions || [];
    renderSummaries(data.summaries || []);
    renderPositions(_lastPositions);
    renderOrders(data.orders || []);
}

function renderSummaries(summaries) {
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

        // Risk factor color classes
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

function renderPositions(positions) {
    const container = document.getElementById('positions-container');
    if (!positions || positions.length === 0) {
        container.innerHTML = `<div class="no-data-msg"><p>No open positions found in Schwab accounts.</p></div>`;
        return;
    }

    const grouped = document.getElementById('btn-group-underlying')?.dataset.grouped === 'true';
    const displayPositions = grouped ? sortPositionsGrouped(positions) : positions;

    // In grouped mode inject a separator row whenever the underlying changes
    let prevUnderlying = null;
    let prevAccount = null;

    let rowsHtml = displayPositions.map(pos => {
        const isOption = pos.symbol.length > 4;
        const symbolBadgeClass = isOption ? 'badge-option' : 'badge-underlying';

        const plVal = pos['P/L'] || 0.0;
        const plClass = plVal >= 0 ? 'val-positive' : 'val-negative';
        const plSign = plVal >= 0 ? '+' : '';

        const plPercent = pos['P/L%'] || 0.0;
        const plPercentClass = plPercent >= 0 ? 'val-positive' : 'val-negative';
        const plPercentSign = plPercent >= 0 ? '+' : '';

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
                <td style="text-align: right;" class="${plClass}">${plSign}${formatCurrency(plVal)}</td>
                <td style="text-align: right;" class="${plPercentClass}">${plPercentSign}${formatNumber(plPercent, 2)}%</td>
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

function renderOrders(orders) {
    const container = document.getElementById('orders-container');
    if (!orders || orders.length === 0) {
        container.innerHTML = `<div class="no-data-msg"><p>No active working orders found.</p></div>`;
        return;
    }

    let rowsHtml = orders.map(ord => {
        const isOption = ord.symbol.length > 4;
        const symbolBadgeClass = isOption ? 'badge-option' : 'badge-underlying';

        const plVal = ord['P/L'] !== null && ord['P/L'] !== undefined ? ord['P/L'] : null;
        const plClass = plVal !== null ? (plVal >= 0 ? 'val-positive' : 'val-negative') : '';
        const plSign = plVal !== null ? (plVal >= 0 ? '+' : '') : '';

        const plPercent = ord['P/L%'] !== null && ord['P/L%'] !== undefined ? ord['P/L%'] : null;
        const plPercentClass = plPercent !== null ? (plPercent >= 0 ? 'val-positive' : 'val-negative') : '';
        const plPercentSign = plPercent !== null ? (plPercent >= 0 ? '+' : '') : '';

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
                <td style="text-align: right;" class="${plClass}">${plVal !== null ? plSign + formatCurrency(plVal) : '-'}</td>
                <td style="text-align: right;" class="${plPercentClass}">${plPercent !== null ? plPercentSign + formatNumber(plPercent, 2) + '%' : '-'}</td>
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

function clearDashboard() {
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

// =====================================================================================
// --- HEADER TAB NAVIGATION ---
// =====================================================================================
const tabBtnPortfolio = document.getElementById('tab-btn-portfolio');
const tabBtnChain = document.getElementById('tab-btn-chain');
const tabContentPortfolio = document.getElementById('tab-content-portfolio');
const tabContentChain = document.getElementById('tab-content-chain');

if (tabBtnPortfolio && tabBtnChain) {
    tabBtnPortfolio.addEventListener('click', () => {
        tabBtnPortfolio.classList.add('active');
        tabBtnChain.classList.remove('active');
        tabContentPortfolio.classList.add('active-tab-content');
        tabContentChain.classList.remove('active-tab-content');
    });

    tabBtnChain.addEventListener('click', () => {
        tabBtnChain.classList.add('active');
        tabBtnPortfolio.classList.remove('active');
        tabContentChain.classList.add('active-tab-content');
        tabContentPortfolio.classList.remove('active-tab-content');
        // Auto-fetch default chain if not loaded yet
        if (!_rawChainData.chain || _rawChainData.chain.length === 0) {
            fetchOptionChain();
        }
    });
}

// =====================================================================================
// --- OPTION CHAIN EXPLORER ---
// =====================================================================================
let _rawChainData = { underlying: {}, chain: [] };

document.getElementById('btn-fetch-chain')?.addEventListener('click', fetchOptionChain);

document.getElementById('chain-symbol')?.addEventListener('keyup', (e) => {
    if (e.key === 'Enter') fetchOptionChain();
});

document.querySelectorAll('.preset-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        const symbol = btn.dataset.symbol;
        const input = document.getElementById('chain-symbol');
        if (input) {
            input.value = symbol;
            fetchOptionChain();
        }
    });
});

document.getElementById('btn-reset-filters')?.addEventListener('click', () => {
    document.getElementById('chain-type').value = 'CALL';
    document.getElementById('chain-min-dte').value = '21';
    document.getElementById('chain-max-dte').value = '60';
    document.getElementById('chain-min-delta').value = '0.15';
    document.getElementById('chain-max-delta').value = '0.30';
    fetchOptionChain();
});

// Real-time server-side fetching on input change
['chain-type', 'chain-min-dte', 'chain-max-dte', 'chain-min-delta', 'chain-max-delta'].forEach(id => {
    document.getElementById(id)?.addEventListener('change', fetchOptionChain);
});

async function fetchOptionChain() {
    const user = auth.currentUser;
    if (!user) {
        alert("Please sign in first.");
        return;
    }

    const symbolInput = document.getElementById('chain-symbol');
    const symbol = (symbolInput?.value || 'AAPL').trim().toUpperCase();
    const typeSelect = document.getElementById('chain-type')?.value || 'CALL';
    const minDte = document.getElementById('chain-min-dte')?.value;
    const maxDte = document.getElementById('chain-max-dte')?.value;
    const minDelta = document.getElementById('chain-min-delta')?.value;
    const maxDelta = document.getElementById('chain-max-delta')?.value;

    const fetchBtn = document.getElementById('btn-fetch-chain');
    const chainContainer = document.getElementById('chain-container');

    if (!symbol) return;

    if (fetchBtn) {
        fetchBtn.disabled = true;
        fetchBtn.innerText = "Fetching...";
    }

    chainContainer.innerHTML = `<div class="no-data-msg"><p>Fetching options chain for ${symbol}...</p></div>`;

    try {
        const token = await user.getIdToken();
        const query = new URLSearchParams({
            symbol: symbol,
            contractType: typeSelect
        });
        if (minDte !== '' && minDte !== null && !isNaN(minDte)) query.append('minDte', minDte);
        if (maxDte !== '' && maxDte !== null && !isNaN(maxDte)) query.append('maxDte', maxDte);
        if (minDelta !== '' && minDelta !== null && !isNaN(minDelta)) query.append('minDelta', minDelta);
        if (maxDelta !== '' && maxDelta !== null && !isNaN(maxDelta)) query.append('maxDelta', maxDelta);

        const url = `/api/schwab/chain?${query.toString()}`;
        const response = await fetch(url, {
            headers: { 'Authorization': `Bearer ${token}` }
        });
        const data = await response.json();

        if (response.ok) {
            _rawChainData = data;
            renderUnderlyingBanner(data.underlying, data.totalContracts, data.chain ? data.chain.length : 0);
            renderOptionChainTable(data.chain || []);
        } else {
            const errMsg = data.error || `Failed to fetch option chain for ${symbol}`;
            chainContainer.innerHTML = `<div class="no-data-msg" style="color:var(--accent-red)"><p>Error: ${errMsg}</p></div>`;
            document.getElementById('chain-underlying-container').innerHTML = '';
        }
    } catch (error) {
        console.error("Failed to fetch option chain:", error);
        chainContainer.innerHTML = `<div class="no-data-msg" style="color:var(--accent-red)"><p>Network Error: ${error.message}</p></div>`;
    } finally {
        if (fetchBtn) {
            fetchBtn.disabled = false;
            fetchBtn.innerText = "Fetch Chain";
        }
    }
}

function renderUnderlyingBanner(underlying, totalContracts, matchingCount) {
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

function renderOptionChainTable(contracts) {
    const container = document.getElementById('chain-container');
    if (!contracts || contracts.length === 0) {
        container.innerHTML = `<div class="no-data-msg"><p>No option contracts match the selected filters.</p></div>`;
        return;
    }

    let prevDte = null;
    let dteGroupIndex = 0;

    let rowsHtml = contracts.map(opt => {
        const badgeClass = opt.contractType === 'CALL' ? 'badge-call' : 'badge-put';
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
                    <td colspan="13">
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
                <td style="text-align: center;"><span class="${badgeClass}">${opt.contractType}</span></td>
                <td style="text-align: right; font-weight: 700;">$${formatNumber(opt.strikePrice, 2)}</td>
                <td style="text-align: center;">${opt.expirationDate}</td>
                <td style="text-align: center;"><span class="dte-pill">${opt.dte}</span></td>
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
                        <th style="text-align: center;">Type</th>
                        <th style="text-align: right;">Strike</th>
                        <th style="text-align: center;">Exp Date</th>
                        <th style="text-align: center;">DTE</th>
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


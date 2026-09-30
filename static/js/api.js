import { auth } from './auth.js';
import { clearDashboard, renderDashboard, renderUnderlyingBanner, renderOptionChainTable, renderTransactions, renderRealized, renderRollChainModal, renderBoxes, lastPositions } from './ui.js';

export let rawChainData = { underlying: {}, chain: [] };

async function _getAuthToken() {
    const user = auth.currentUser;
    if (!user) return null;
    return await user.getIdToken();
}

function _populateAccountDropdown(accountSelect, accounts, defaultVal = 'ALL') {
    if (!accountSelect || !accounts) return;
    const currentSelection = accountSelect.value || defaultVal;
    const sortedAccounts = Array.from(new Set(accounts)).sort();
    accountSelect.innerHTML = '<option value="ALL">ALL</option>' +
        sortedAccounts.map(acc => `<option value="${acc}">${acc}</option>`).join('');
    accountSelect.value = sortedAccounts.includes(currentSelection) ? currentSelection : defaultVal;
}

function _renderConnectBtn(actionsDiv) {
    if (!actionsDiv) return;
    actionsDiv.innerHTML = `<button id="btn-connect" class="btn-header btn-connect">Connect</button>`;
    document.getElementById('btn-connect')?.addEventListener('click', connectSchwab);
}

export function setRefreshBtnLoading(loading) {
    const btn = document.getElementById('btn-refresh-data');
    if (!btn) return;
    if (loading) {
        btn.disabled = true;
        btn.innerText = "Refreshing...";
    } else {
        btn.disabled = false;
        btn.innerText = "↻ Refresh";
    }
}

export async function checkSchwabStatus() {
    const token = await _getAuthToken();
    if (!token) return;

    const actionsDiv = document.getElementById('schwab-actions');
    const refreshBtn = document.getElementById('btn-refresh-data');

    try {
        const response = await fetch('/api/schwab/status', {
            headers: { 'Authorization': `Bearer ${token}` }
        });
        const data = await response.json();

        if (data.connected) {
            if (refreshBtn) refreshBtn.style.display = "inline-block";
            actionsDiv.innerHTML = `<button id="btn-disconnect" class="btn-header btn-disconnect">Disconnect</button>`;
            document.getElementById('btn-disconnect')?.addEventListener('click', disconnectSchwab);
            fetchSchwabPortfolio();
        } else {
            if (refreshBtn) refreshBtn.style.display = "none";
            _renderConnectBtn(actionsDiv);
            clearDashboard();
        }
    } catch (error) {
        console.error("Error checking Schwab status:", error);
        if (refreshBtn) refreshBtn.style.display = "none";
        _renderConnectBtn(actionsDiv);
    }
}

export async function connectSchwab() {
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

export async function disconnectSchwab() {
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

export async function fetchSchwabPortfolio() {
    const token = await _getAuthToken();
    if (!token) return;

    const positionsContainer = document.getElementById('positions-container');
    setRefreshBtnLoading(true);

    if (positionsContainer) {
        positionsContainer.innerHTML = `<div class="no-data-msg"><p>Retrieving latest portfolio positions and market quotes...</p></div>`;
    }

    try {
        const response = await fetch('/api/schwab/accounts', {
            headers: { 'Authorization': `Bearer ${token}` }
        });
        const data = await response.json();

        if (response.ok) {
            renderDashboard(data);
        } else {
            const errMsg = data.error || 'Failed to fetch account portfolio';
            if (positionsContainer) {
                positionsContainer.innerHTML = `<div class="no-data-msg" style="color:var(--accent-red)"><p>Error: ${errMsg}</p></div>`;
            }
        }
    } catch (error) {
        console.error("Failed to fetch Schwab portfolio:", error);
        if (positionsContainer) {
            positionsContainer.innerHTML = `<div class="no-data-msg" style="color:var(--accent-red)"><p>Network Error: ${error.message}</p></div>`;
        }
    } finally {
        setRefreshBtnLoading(false);
    }
}

export async function fetchOptionChain() {
    const token = await _getAuthToken();
    if (!token) {
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
    setRefreshBtnLoading(true);

    chainContainer.innerHTML = `<div class="no-data-msg"><p>Fetching options chain for ${symbol}...</p></div>`;

    try {
        const query = new URLSearchParams({
            symbol: symbol,
            contractType: typeSelect
        });
        if (minDte !== '' && minDte !== null && !isNaN(minDte)) query.append('minDte', minDte);
        if (maxDte !== '' && maxDte !== null && !isNaN(maxDte)) query.append('maxDte', maxDte);
        if (minDelta !== '' && minDelta !== null && !isNaN(minDelta)) query.append('minDelta', minDelta);
        if (maxDelta !== '' && maxDelta !== null && !isNaN(maxDelta)) query.append('maxDelta', maxDelta);
        const minStrike = document.getElementById('chain-min-strike')?.value;
        const maxStrike = document.getElementById('chain-max-strike')?.value;
        if (minStrike !== '' && minStrike !== null && minStrike !== undefined && !isNaN(minStrike)) query.append('minStrike', minStrike);
        if (maxStrike !== '' && maxStrike !== null && maxStrike !== undefined && !isNaN(maxStrike)) query.append('maxStrike', maxStrike);

        const url = `/api/schwab/chain?${query.toString()}`;
        const response = await fetch(url, {
            headers: { 'Authorization': `Bearer ${token}` }
        });
        const data = await response.json();

        if (response.ok) {
            rawChainData = data;
            renderUnderlyingBanner(data.underlying);
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
        setRefreshBtnLoading(false);
    }
}

export async function fetchSPXBoxes() {
    const token = await _getAuthToken();
    if (!token) {
        alert("Please sign in first.");
        return;
    }

    const fromDate = document.getElementById('box-from-date')?.value || '';
    const toDate = document.getElementById('box-to-date')?.value || '';
    const sizes = document.getElementById('box-sizes')?.value || '';

    const fetchBtn = document.getElementById('btn-fetch-boxes');
    const boxContainer = document.getElementById('box-container');

    if (fetchBtn) {
        fetchBtn.disabled = true;
        fetchBtn.innerText = "Scanning...";
    }
    setRefreshBtnLoading(true);

    boxContainer.innerHTML = `<div class="no-data-msg"><p>Scanning SPX options chain for box spread opportunities...</p></div>`;

    try {
        const query = new URLSearchParams();
        if (fromDate) query.append('fromDate', fromDate);
        if (toDate) query.append('toDate', toDate);
        if (sizes) query.append('sizes', sizes);

        const url = `/api/schwab/boxes?${query.toString()}`;
        const response = await fetch(url, {
            headers: { 'Authorization': `Bearer ${token}` }
        });
        const data = await response.json();

        if (response.ok) {
            renderBoxes(data.boxes || []);
        } else {
            const errMsg = data.error || 'Failed to fetch SPX box spreads';
            boxContainer.innerHTML = `<div class="no-data-msg" style="color:var(--accent-red)"><p>Error: ${errMsg}</p></div>`;
        }
    } catch (error) {
        console.error("Failed to fetch SPX boxes:", error);
        boxContainer.innerHTML = `<div class="no-data-msg" style="color:var(--accent-red)"><p>Network Error: ${error.message}</p></div>`;
    } finally {
        if (fetchBtn) {
            fetchBtn.disabled = false;
            fetchBtn.innerText = "Find Boxes";
        }
        setRefreshBtnLoading(false);
    }
}

// =====================================================================================
// --- TRANSACTIONS ---
// =====================================================================================

let allTransactions = [];

export async function fetchTransactions() {
    const token = await _getAuthToken();
    if (!token) return;

    const container = document.getElementById('transactions-container');
    container.innerHTML = `<div class="no-data-msg"><p>Loading stored transactions...</p></div>`;
    setRefreshBtnLoading(true);

    const symbolInput = document.getElementById('txn-symbol');
    const accountSelect = document.getElementById('txn-account');
    const typeSelect = document.getElementById('txn-type');
    const fromDateInput = document.getElementById('txn-from-date');
    const toDateInput = document.getElementById('txn-to-date');

    const symbolVal = symbolInput ? symbolInput.value.trim().toUpperCase() : 'ALL';
    const accountVal = accountSelect ? accountSelect.value : 'ALL';
    const typeVal = typeSelect ? typeSelect.value : 'TRADE';
    const fromDateVal = fromDateInput ? fromDateInput.value : '';
    const toDateVal = toDateInput ? toDateInput.value : '';

    const queryParams = new URLSearchParams();
    if (symbolVal && symbolVal !== 'ALL') queryParams.set('symbol', symbolVal);
    if (accountVal && accountVal !== 'ALL') queryParams.set('account', accountVal);
    if (typeVal && typeVal !== 'ALL') queryParams.set('type', typeVal);
    if (fromDateVal) queryParams.set('from_date', fromDateVal);
    if (toDateVal) queryParams.set('to_date', toDateVal);

    try {
        const url = `/api/schwab/transactions?${queryParams.toString()}`;
        const response = await fetch(url, {
            headers: { 'Authorization': `Bearer ${token}` }
        });
        const data = await response.json();

        if (response.ok) {
            allTransactions = data.transactions || [];
            _populateAccountDropdown(accountSelect, data.accounts);

            // Populate any extra transaction types dynamically
            if (typeSelect && allTransactions.length > 0) {
                const currentTypeSelection = typeSelect.value || 'TRADE';
                const baseTypes = ['ALL', 'TRADE', 'DIVIDEND_OR_INTEREST', 'RECEIVE_AND_DELIVER'];
                const typesSet = new Set(allTransactions.map(t => t.type).filter(Boolean));
                const extraTypes = Array.from(typesSet).filter(t => !baseTypes.includes(t)).sort();

                typeSelect.innerHTML = '<option value="ALL">ALL</option>' +
                    '<option value="TRADE">TRADE</option>' +
                    '<option value="DIVIDEND_OR_INTEREST">DIVIDEND_OR_INTEREST</option>' +
                    '<option value="RECEIVE_AND_DELIVER">RECEIVE_AND_DELIVER</option>' +
                    extraTypes.map(t => `<option value="${t}">${t}</option>`).join('');

                typeSelect.value = currentTypeSelection;
            }

            renderTransactions(allTransactions);
        } else {
            const errMsg = data.error || 'Failed to load transactions';
            container.innerHTML = `<div class="no-data-msg" style="color:var(--accent-red)"><p>Error: ${errMsg}</p></div>`;
        }
    } catch (error) {
        console.error('Failed to fetch transactions:', error);
        container.innerHTML = `<div class="no-data-msg" style="color:var(--accent-red)"><p>Network Error: ${error.message}</p></div>`;
    } finally {
        setRefreshBtnLoading(false);
    }
}

export const applyTransactionFilters = fetchTransactions;

export async function syncTransactions() {
    const token = await _getAuthToken();
    if (!token) return;

    const syncBtn = document.getElementById('btn-sync-transactions');
    const statusSpan = document.getElementById('txn-sync-status');

    if (syncBtn) {
        syncBtn.disabled = true;
        syncBtn.innerText = 'Syncing...';
    }
    if (statusSpan) {
        statusSpan.textContent = '';
        statusSpan.className = 'txn-sync-status';
    }
    setRefreshBtnLoading(true);

    try {
        const response = await fetch('/api/schwab/sync_transactions', {
            method: 'POST',
            headers: { 'Authorization': `Bearer ${token}` }
        });
        const data = await response.json();

        if (response.ok) {
            let totalNewCount = 0;
            if (Array.isArray(data.results)) {
                totalNewCount = data.results.reduce((sum, res) => sum + (res.new_count || 0), 0);
            } else if (typeof data.new_count === 'number') {
                totalNewCount = data.new_count;
            }

            const msg = totalNewCount > 0
                ? `✓ ${totalNewCount} new transaction${totalNewCount !== 1 ? 's' : ''} synced`
                : '✓ Already up to date';
            if (statusSpan) {
                statusSpan.textContent = msg;
                statusSpan.className = 'txn-sync-status txn-sync-ok';
            }
            await fetchTransactions();
        } else {
            const errMsg = data.error || 'Sync failed';
            if (statusSpan) {
                statusSpan.textContent = `✗ ${errMsg}`;
                statusSpan.className = 'txn-sync-status txn-sync-err';
            }
        }
    } catch (error) {
        console.error('Sync transactions failed:', error);
        if (statusSpan) {
            statusSpan.textContent = `✗ Network error`;
            statusSpan.className = 'txn-sync-status txn-sync-err';
        }
    } finally {
        if (syncBtn) {
            syncBtn.disabled = false;
            syncBtn.innerText = '↻ Sync';
        }
        setRefreshBtnLoading(false);
    }
}

let allRealized = [];

export async function fetchRealized() {
    const token = await _getAuthToken();
    if (!token) return;

    const container = document.getElementById('realized-container');
    container.innerHTML = `<div class="no-data-msg"><p>Loading realized transactions...</p></div>`;
    setRefreshBtnLoading(true);

    const symbolInput = document.getElementById('realized-symbol');
    const fromDateInput = document.getElementById('realized-from-date');
    const toDateInput = document.getElementById('realized-to-date');
    const accountSelect = document.getElementById('realized-account');
    const typeSelect = document.getElementById('realized-type');

    // Default fromDate is 1st January of current year
    const defaultFromDate = `${new Date().getFullYear()}-01-01`;
    if (fromDateInput && !fromDateInput.value) {
        fromDateInput.value = defaultFromDate;
    }

    const symbolVal = symbolInput ? symbolInput.value.trim().toUpperCase() : 'ALL';
    const fromDateVal = fromDateInput ? fromDateInput.value : defaultFromDate;
    const toDateVal = toDateInput ? toDateInput.value : '';
    const accountVal = accountSelect ? accountSelect.value : 'ALL';
    const typeVal = typeSelect ? typeSelect.value : 'ALL';

    const queryParams = new URLSearchParams();
    if (symbolVal && symbolVal !== 'ALL') queryParams.set('symbol', symbolVal);
    if (accountVal && accountVal !== 'ALL') queryParams.set('account', accountVal);
    if (typeVal && typeVal !== 'ALL') queryParams.set('type', typeVal);
    if (fromDateVal) queryParams.set('from_date', fromDateVal);
    if (toDateVal) queryParams.set('to_date', toDateVal);

    try {
        const url = `/api/schwab/realized?${queryParams.toString()}`;
        const response = await fetch(url, {
            headers: { 'Authorization': `Bearer ${token}` }
        });
        const data = await response.json();

        if (response.ok) {
            allRealized = data.realized_transactions || [];
            _populateAccountDropdown(accountSelect, data.accounts);
            renderRealized(allRealized);
        } else {
            const errMsg = data.error || 'Failed to load realized transactions';
            container.innerHTML = `<div class="no-data-msg" style="color:var(--accent-red)"><p>Error: ${errMsg}</p></div>`;
        }
    } catch (error) {
        console.error('Failed to fetch realized transactions:', error);
        container.innerHTML = `<div class="no-data-msg" style="color:var(--accent-red)"><p>Network Error: ${error.message}</p></div>`;
    } finally {
        setRefreshBtnLoading(false);
    }
}

export const applyRealizedFilters = fetchRealized;

export async function fetchAndShowRollChain(symbol, accountNumber = '') {
    const token = await _getAuthToken();
    if (!token) return;

    if (!accountNumber && lastPositions && lastPositions.length > 0) {
        const matchingPos = lastPositions.find(p => p.symbol === symbol && (p.accountNumber || p.account));
        if (matchingPos) {
            accountNumber = matchingPos.accountNumber || matchingPos.account || '';
        }
    }

    if (!accountNumber) {
        renderRollChainModal({ error: 'Account number is required to fetch roll chain.' });
        return;
    }

    renderRollChainModal({ roll_chain: { target_symbol: symbol, chain: [] } });

    try {
        const queryParams = new URLSearchParams({
            symbol,
            account: accountNumber
        });
        const response = await fetch(`/api/schwab/roll-chain?${queryParams.toString()}`, {
            headers: { 'Authorization': `Bearer ${token}` }
        });
        const data = await response.json();
        if (response.ok) {
            renderRollChainModal(data);
        } else {
            renderRollChainModal({ error: data.error || 'Failed to fetch roll chain' });
        }
    } catch (err) {
        console.error('Error fetching roll chain:', err);
        renderRollChainModal({ error: err.message });
    }
}

export async function submitOrder(orderData) {
    const token = await _getAuthToken();
    if (!token) throw new Error("Please sign in first.");

    const response = await fetch('/api/schwab/order', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify(orderData)
    });

    const result = await response.json();
    if (!response.ok) {
        throw new Error(result.error || `Failed to ${orderData.preview ? 'preview' : 'place'} order`);
    }
    return result;
}

export async function fetchOptionChainRaw(symbol, contractType = 'CALL', options = {}) {
    const token = await _getAuthToken();
    if (!token) throw new Error("Please sign in first.");

    const query = new URLSearchParams({
        symbol: symbol.trim().toUpperCase(),
        contractType: contractType.toUpperCase()
    });

    const minStrike = options.minStrike ?? options.min_strike;
    if (minStrike !== undefined && minStrike !== null && minStrike !== '' && !isNaN(minStrike)) {
        query.append('minStrike', minStrike);
    }
    const maxStrike = options.maxStrike ?? options.max_strike;
    if (maxStrike !== undefined && maxStrike !== null && maxStrike !== '' && !isNaN(maxStrike)) {
        query.append('maxStrike', maxStrike);
    }
    const minDte = options.minDte ?? options.min_dte;
    if (minDte !== undefined && minDte !== null && minDte !== '' && !isNaN(minDte)) {
        query.append('minDte', minDte);
    }
    const maxDte = options.maxDte ?? options.max_dte;
    if (maxDte !== undefined && maxDte !== null && maxDte !== '' && !isNaN(maxDte)) {
        query.append('maxDte', maxDte);
    }

    const response = await fetch(`/api/schwab/chain?${query.toString()}`, {
        headers: { 'Authorization': `Bearer ${token}` }
    });
    const data = await response.json();
    if (!response.ok) {
        throw new Error(data.error || `Failed to fetch chain for ${symbol}`);
    }
    return data;
}



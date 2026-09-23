import { auth } from './auth.js';
import { clearDashboard, renderDashboard, renderUnderlyingBanner, renderOptionChainTable, renderTransactions, renderRealized, renderRollChainModal } from './ui.js';

export let rawChainData = { underlying: {}, chain: [] };

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
    const user = auth.currentUser;
    if (!user) return;

    const actionsDiv = document.getElementById('schwab-actions');
    const refreshBtn = document.getElementById('btn-refresh-data');

    try {
        const token = await user.getIdToken();
        const response = await fetch('/api/schwab/status', {
            headers: { 'Authorization': `Bearer ${token}` }
        });
        const data = await response.json();

        if (data.connected) {
            if (refreshBtn) refreshBtn.style.display = "inline-block";

            actionsDiv.innerHTML = `
                <button id="btn-disconnect" class="btn-header btn-disconnect">Disconnect</button>
            `;
            document.getElementById('btn-disconnect').addEventListener('click', disconnectSchwab);

            fetchSchwabPortfolio();
        } else {
            if (refreshBtn) refreshBtn.style.display = "none";

            actionsDiv.innerHTML = `
                <button id="btn-connect" class="btn-header btn-connect">Connect</button>
            `;
            document.getElementById('btn-connect').addEventListener('click', connectSchwab);
            clearDashboard();
        }
    } catch (error) {
        console.error("Error checking Schwab status:", error);
        if (refreshBtn) refreshBtn.style.display = "none";
        actionsDiv.innerHTML = `
            <button id="btn-connect" class="btn-header btn-connect">Connect</button>
        `;
        document.getElementById('btn-connect')?.addEventListener('click', connectSchwab);
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
    const user = auth.currentUser;
    if (!user) return;

    const positionsContainer = document.getElementById('positions-container');

    setRefreshBtnLoading(true);

    if (positionsContainer) {
        positionsContainer.innerHTML = `<div class="no-data-msg"><p>Retrieving latest portfolio positions and market quotes...</p></div>`;
    }

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
    setRefreshBtnLoading(true);

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
    const user = auth.currentUser;
    if (!user) {
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
        const token = await user.getIdToken();
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
            const { renderBoxes } = await import('./ui.js');
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

export async function fetchTransactions() {
    const user = auth.currentUser;
    if (!user) return;

    const container = document.getElementById('transactions-container');
    container.innerHTML = `<div class="no-data-msg"><p>Loading stored transactions...</p></div>`;
    setRefreshBtnLoading(true);

    try {
        const token = await user.getIdToken();
        const response = await fetch('/api/schwab/transactions', {
            headers: { 'Authorization': `Bearer ${token}` }
        });
        const data = await response.json();

        if (response.ok) {
            renderTransactions(data.transactions || []);
        } else {
            const errMsg = data.error || 'Failed to load transactions';
            if (data.error === 'No primary account hash found') {
                container.innerHTML = `<div class="no-data-msg"><p>No transaction history found. Connect your Schwab account and click <strong>↻ Sync</strong> to import transactions.</p></div>`;
            } else {
                container.innerHTML = `<div class="no-data-msg" style="color:var(--accent-red)"><p>Error: ${errMsg}</p></div>`;
            }
        }
    } catch (error) {
        console.error('Failed to fetch transactions:', error);
        container.innerHTML = `<div class="no-data-msg" style="color:var(--accent-red)"><p>Network Error: ${error.message}</p></div>`;
    } finally {
        setRefreshBtnLoading(false);
    }
}

export async function syncTransactions() {
    const user = auth.currentUser;
    if (!user) return;

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
        const token = await user.getIdToken();
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
            // Refresh the table after a successful sync
            await fetchTransactions();
        } else {
            const errMsg = data.error === 'No primary account hash found'
                ? 'No connected Schwab account found'
                : (data.error || 'Sync failed');
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

export let allRealized = [];

export async function fetchRealized() {
    const user = auth.currentUser;
    if (!user) return;

    const container = document.getElementById('realized-container');
    container.innerHTML = `<div class="no-data-msg"><p>Loading realized transactions...</p></div>`;
    setRefreshBtnLoading(true);

    try {
        const token = await user.getIdToken();
        const response = await fetch('/api/schwab/realized', {
            headers: { 'Authorization': `Bearer ${token}` }
        });
        const data = await response.json();

        if (response.ok) {
            allRealized = data.realized_transactions || [];
            // Populate account dropdown options dynamically
            const accountSelect = document.getElementById('realized-account');
            if (accountSelect) {
                const currentSelection = accountSelect.value || 'ALL';
                const accountsSet = new Set(allRealized.map(r => r.accountNumber).filter(Boolean));
                const sortedAccounts = Array.from(accountsSet).sort();

                accountSelect.innerHTML = '<option value="ALL">ALL</option>' +
                    sortedAccounts.map(acc => `<option value="${acc}">${acc}</option>`).join('');

                if (sortedAccounts.includes(currentSelection)) {
                    accountSelect.value = currentSelection;
                } else {
                    accountSelect.value = 'ALL';
                }
            }

            // Apply default filters
            const symbolInput = document.getElementById('realized-symbol');
            const minDateInput = document.getElementById('realized-min-date');
            const typeSelect = document.getElementById('realized-type');

            // Default minDate is 1st January of current year
            const currentYear = new Date().getFullYear();
            const defaultMinDate = `${currentYear}-01-01`;
            if (minDateInput && !minDateInput.value) {
                minDateInput.value = defaultMinDate;
            }

            const symbolVal = symbolInput ? symbolInput.value.trim().toUpperCase() : 'ALL';
            const minDateVal = minDateInput ? minDateInput.value : defaultMinDate;
            const accountVal = accountSelect ? accountSelect.value : 'ALL';
            const typeVal = typeSelect ? typeSelect.value : 'ALL';

            applyRealizedFilters(symbolVal, minDateVal, accountVal, typeVal);
        } else {
            const errMsg = data.error || 'Failed to load realized transactions';
            if (data.error === 'No primary account hash found') {
                container.innerHTML = `<div class="no-data-msg"><p>No realized transactions found. Connect your Schwab account and click <strong>↻ Sync</strong> in the Transactions tab to calculate realized gains.</p></div>`;
            } else {
                container.innerHTML = `<div class="no-data-msg" style="color:var(--accent-red)"><p>Error: ${errMsg}</p></div>`;
            }
        }
    } catch (error) {
        console.error('Failed to fetch realized transactions:', error);
        container.innerHTML = `<div class="no-data-msg" style="color:var(--accent-red)"><p>Network Error: ${error.message}</p></div>`;
    } finally {
        setRefreshBtnLoading(false);
    }
}

export function applyRealizedFilters(symbol, minDate, accountNum, tradeType) {
    let filtered = allRealized;

    // Filter by symbol if not "ALL" and not empty
    if (symbol && symbol !== 'ALL') {
        filtered = filtered.filter(r => r.symbol && r.symbol.toUpperCase().includes(symbol));
    }

    // Filter by min sell/close date
    if (minDate) {
        filtered = filtered.filter(r => r.sell_date && r.sell_date >= minDate);
    }

    // Filter by accountNumber if not "ALL" and not empty
    if (accountNum && accountNum !== 'ALL') {
        filtered = filtered.filter(r => String(r.accountNumber) === String(accountNum));
    }

    // Filter by tradeType if not "ALL" and not empty
    if (tradeType && tradeType !== 'ALL') {
        filtered = filtered.filter(r => r.trade_type === tradeType);
    }

    renderRealized(filtered);
}


export async function fetchAndShowRollChain(symbol) {
    const user = auth.currentUser;
    if (!user) return;

    renderRollChainModal({ roll_chain: { target_symbol: symbol, chain: [] } });

    try {
        const token = await user.getIdToken();
        const response = await fetch(`/api/schwab/roll-chain?symbol=${encodeURIComponent(symbol)}`, {
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


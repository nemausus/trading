import { auth } from './auth.js';
import { clearDashboard, renderDashboard, renderUnderlyingBanner, renderOptionChainTable } from './ui.js';

export let rawChainData = { underlying: {}, chain: [] };

export async function checkSchwabStatus() {
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
    }
}

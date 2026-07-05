import { auth, signInWithEmailAndPassword, signOut, onAuthStateChanged } from './auth.js';
import { checkSchwabStatus, fetchSchwabPortfolio, fetchOptionChain, rawChainData } from './api.js';
import { showView, clearDashboard, renderPositions, renderOptions, lastPositions } from './ui.js';

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
    if (lastPositions.length > 0) renderPositions(lastPositions);
});

document.getElementById('btn-group-options').addEventListener('click', () => {
    const btn = document.getElementById('btn-group-options');
    const isGrouped = btn.dataset.grouped === 'true';
    btn.dataset.grouped = String(!isGrouped);
    btn.classList.toggle('active', !isGrouped);
    if (lastPositions.length > 0) renderOptions(lastPositions);
});


// =====================================================================================
// --- HEADER TAB NAVIGATION ---
// =====================================================================================
const tabBtnPortfolio = document.getElementById('tab-btn-portfolio');
const tabBtnOptions = document.getElementById('tab-btn-options');
const tabBtnChain = document.getElementById('tab-btn-chain');
const tabContentPortfolio = document.getElementById('tab-content-portfolio');
const tabContentOptions = document.getElementById('tab-content-options');
const tabContentChain = document.getElementById('tab-content-chain');

if (tabBtnPortfolio && tabBtnOptions && tabBtnChain) {
    tabBtnPortfolio.addEventListener('click', () => {
        tabBtnPortfolio.classList.add('active');
        tabBtnOptions.classList.remove('active');
        tabBtnChain.classList.remove('active');
        tabContentPortfolio.classList.add('active-tab-content');
        tabContentOptions.classList.remove('active-tab-content');
        tabContentChain.classList.remove('active-tab-content');
    });

    tabBtnOptions.addEventListener('click', () => {
        tabBtnOptions.classList.add('active');
        tabBtnPortfolio.classList.remove('active');
        tabBtnChain.classList.remove('active');
        tabContentOptions.classList.add('active-tab-content');
        tabContentPortfolio.classList.remove('active-tab-content');
        tabContentChain.classList.remove('active-tab-content');
    });

    tabBtnChain.addEventListener('click', () => {
        tabBtnChain.classList.add('active');
        tabBtnPortfolio.classList.remove('active');
        tabBtnOptions.classList.remove('active');
        tabContentChain.classList.add('active-tab-content');
        tabContentPortfolio.classList.remove('active-tab-content');
        tabContentOptions.classList.remove('active-tab-content');
        // Auto-fetch default chain if not loaded yet
        if (!rawChainData.chain || rawChainData.chain.length === 0) {
            fetchOptionChain();
        }
    });
}

// =====================================================================================
// --- OPTION CHAIN EXPLORER ---
// =====================================================================================

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

import { auth, signInWithEmailAndPassword, signOut, onAuthStateChanged } from './auth.js';
import { checkSchwabStatus, fetchSchwabPortfolio, fetchOptionChain, fetchSPXBoxes, fetchTransactions, syncTransactions, rawChainData } from './api.js';
import { showView, clearDashboard, renderPositions, lastPositions } from './ui.js';

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
        // Navigate to the tab indicated by the URL hash (or default)
        applyHashNavigation();
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




// =====================================================================================
// --- HEADER TAB NAVIGATION ---
// =====================================================================================
const tabBtnPortfolio = document.getElementById('tab-btn-portfolio');
const tabBtnChain = document.getElementById('tab-btn-chain');
const tabBtnBox = document.getElementById('tab-btn-box');
const tabBtnTransactions = document.getElementById('tab-btn-transactions');
const tabContentPortfolio = document.getElementById('tab-content-portfolio');
const tabContentChain = document.getElementById('tab-content-chain');
const tabContentBox = document.getElementById('tab-content-box');
const tabContentTransactions = document.getElementById('tab-content-transactions');

const allTabBtns = [tabBtnPortfolio, tabBtnChain, tabBtnBox, tabBtnTransactions];
const allTabContents = [tabContentPortfolio, tabContentChain, tabContentBox, tabContentTransactions];

// Map of hash fragment -> { btn, content } for each tab
const TAB_MAP = {
    portfolio:    { btn: tabBtnPortfolio,    content: tabContentPortfolio },
    chain:        { btn: tabBtnChain,        content: tabContentChain },
    box:          { btn: tabBtnBox,          content: tabContentBox },
    transactions: { btn: tabBtnTransactions, content: tabContentTransactions },
};

let txnsLoaded = false;

function switchTab(activeBtn, activeContent, tabKey) {
    allTabBtns.forEach(b => b && b.classList.remove('active'));
    allTabContents.forEach(c => c && c.classList.remove('active-tab-content'));
    activeBtn.classList.add('active');
    activeContent.classList.add('active-tab-content');
    // Keep URL in sync (pushState so back/forward works)
    if (tabKey && window.location.hash !== '#' + tabKey) {
        history.pushState({ tab: tabKey }, '', '#' + tabKey);
    }
}

/**
 * Navigate to a tab identified by its hash key (e.g. 'chain').
 * Triggers any side-effects (auto-fetch chain, load transactions).
 * Falls back to 'portfolio' if the key is unknown.
 */
function navigateToTab(tabKey) {
    const entry = TAB_MAP[tabKey] || TAB_MAP['portfolio'];
    switchTab(entry.btn, entry.content, tabKey in TAB_MAP ? tabKey : 'portfolio');

    if (tabKey === 'transactions') {
        if (!txnsLoaded) {
            txnsLoaded = true;
            fetchTransactions();
        }
    }
}

// Read initial hash (e.g. when the user pastes a URL with /#chain)
function applyHashNavigation() {
    const hash = window.location.hash.replace('#', '');
    navigateToTab(hash || 'portfolio');
}

// Update tab when the user navigates with the browser back/forward buttons
window.addEventListener('hashchange', () => {
    const hash = window.location.hash.replace('#', '');
    navigateToTab(hash || 'portfolio');
});

if (tabBtnPortfolio && tabBtnChain && tabBtnBox && tabBtnTransactions) {
    tabBtnPortfolio.addEventListener('click',    () => navigateToTab('portfolio'));
    tabBtnChain.addEventListener('click',        () => navigateToTab('chain'));
    tabBtnBox.addEventListener('click',          () => navigateToTab('box'));
    tabBtnTransactions.addEventListener('click', () => navigateToTab('transactions'));
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
        }
    });
});

document.getElementById('btn-reset-filters')?.addEventListener('click', () => {
    document.getElementById('chain-type').value = 'CALL';
    document.getElementById('chain-min-dte').value = '21';
    document.getElementById('chain-max-dte').value = '60';
    document.getElementById('chain-min-delta').value = '0.15';
    document.getElementById('chain-max-delta').value = '0.30';
});

// =====================================================================================
// --- BOX SPREAD SCANNER ---
// =====================================================================================
document.getElementById('btn-fetch-boxes')?.addEventListener('click', fetchSPXBoxes);

// =====================================================================================
// --- TRANSACTIONS ---
// =====================================================================================
document.getElementById('btn-sync-transactions')?.addEventListener('click', syncTransactions);

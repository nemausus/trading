import { auth, signInWithEmailAndPassword, signOut, onAuthStateChanged } from './auth.js';
import { checkSchwabStatus, fetchSchwabPortfolio, fetchOptionChain, fetchSPXBoxes, fetchTransactions, syncTransactions, rawChainData, fetchRealized, applyRealizedFilters, fetchAndShowRollChain } from './api.js';
import { showView, clearDashboard, renderPositions, lastPositions, closeRollChainModal } from './ui.js';

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

let currentTabKey = 'portfolio';

document.getElementById('btn-refresh-data')?.addEventListener('click', () => {
    switch (currentTabKey) {
        case 'portfolio':
            fetchSchwabPortfolio();
            break;
        case 'chain':
            fetchOptionChain();
            break;
        case 'box':
            fetchSPXBoxes();
            break;
        case 'transactions':
            syncTransactions();
            break;
        case 'realized':
            fetchRealized();
            break;
        default:
            fetchSchwabPortfolio();
            break;
    }
});




// =====================================================================================
// --- HEADER TAB NAVIGATION ---
// =====================================================================================
const tabBtnPortfolio = document.getElementById('tab-btn-portfolio');
const tabBtnChain = document.getElementById('tab-btn-chain');
const tabBtnBox = document.getElementById('tab-btn-box');
const tabBtnRealized = document.getElementById('tab-btn-realized');
const tabBtnTransactions = document.getElementById('tab-btn-transactions');
const tabContentPortfolio = document.getElementById('tab-content-portfolio');
const tabContentChain = document.getElementById('tab-content-chain');
const tabContentBox = document.getElementById('tab-content-box');
const tabContentRealized = document.getElementById('tab-content-realized');
const tabContentTransactions = document.getElementById('tab-content-transactions');

const allTabBtns = [tabBtnPortfolio, tabBtnChain, tabBtnBox, tabBtnRealized, tabBtnTransactions];
const allTabContents = [tabContentPortfolio, tabContentChain, tabContentBox, tabContentRealized, tabContentTransactions];

// Map of hash fragment -> { btn, content } for each tab
const TAB_MAP = {
    portfolio:    { btn: tabBtnPortfolio,    content: tabContentPortfolio },
    chain:        { btn: tabBtnChain,        content: tabContentChain },
    box:          { btn: tabBtnBox,          content: tabContentBox },
    realized:     { btn: tabBtnRealized,     content: tabContentRealized },
    transactions: { btn: tabBtnTransactions, content: tabContentTransactions },
};

let txnsLoaded = false;
let realizedLoaded = false;

function switchTab(activeBtn, activeContent, tabKey) {
    allTabBtns.forEach(b => b && b.classList.remove('active'));
    allTabContents.forEach(c => c && c.classList.remove('active-tab-content'));
    if (activeBtn) activeBtn.classList.add('active');
    if (activeContent) activeContent.classList.add('active-tab-content');
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
    currentTabKey = tabKey in TAB_MAP ? tabKey : 'portfolio';
    const entry = TAB_MAP[currentTabKey];
    switchTab(entry.btn, entry.content, currentTabKey);

    if (currentTabKey === 'transactions') {
        if (!txnsLoaded) {
            txnsLoaded = true;
            fetchTransactions();
        }
    } else if (currentTabKey === 'realized') {
        if (!realizedLoaded) {
            realizedLoaded = true;
            fetchRealized();
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

if (tabBtnPortfolio && tabBtnChain && tabBtnBox && tabBtnRealized && tabBtnTransactions) {
    tabBtnPortfolio.addEventListener('click',    () => navigateToTab('portfolio'));
    tabBtnChain.addEventListener('click',        () => navigateToTab('chain'));
    tabBtnBox.addEventListener('click',          () => navigateToTab('box'));
    tabBtnRealized.addEventListener('click',     () => navigateToTab('realized'));
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

// =====================================================================================
// --- REALIZED GAIN/LOSS ---
// =====================================================================================
const handleRealizedFilter = () => {
    const symbolInput = document.getElementById('realized-symbol');
    const minDateInput = document.getElementById('realized-min-date');
    const accountSelect = document.getElementById('realized-account');
    const typeSelect = document.getElementById('realized-type');
    const symbolVal = symbolInput ? symbolInput.value.trim().toUpperCase() : 'ALL';
    const minDateVal = minDateInput ? minDateInput.value : '';
    const accountVal = accountSelect ? accountSelect.value : 'ALL';
    const typeVal = typeSelect ? typeSelect.value : 'ALL';
    applyRealizedFilters(symbolVal, minDateVal, accountVal, typeVal);
};

document.getElementById('btn-filter-realized')?.addEventListener('click', handleRealizedFilter);
document.getElementById('realized-account')?.addEventListener('change', handleRealizedFilter);
document.getElementById('realized-type')?.addEventListener('change', handleRealizedFilter);
document.getElementById('realized-symbol')?.addEventListener('keyup', (e) => {
    if (e.key === 'Enter') handleRealizedFilter();
});
document.getElementById('realized-min-date')?.addEventListener('keyup', (e) => {
    if (e.key === 'Enter') handleRealizedFilter();
});

document.getElementById('btn-reset-realized')?.addEventListener('click', () => {
    const symbolInput = document.getElementById('realized-symbol');
    const minDateInput = document.getElementById('realized-min-date');
    const accountSelect = document.getElementById('realized-account');
    const typeSelect = document.getElementById('realized-type');
    if (symbolInput) symbolInput.value = 'ALL';
    if (accountSelect) accountSelect.value = 'ALL';
    if (typeSelect) typeSelect.value = 'ALL';
    const currentYear = new Date().getFullYear();
    const defaultMinDate = `${currentYear}-01-01`;
    if (minDateInput) minDateInput.value = defaultMinDate;
    applyRealizedFilters('ALL', defaultMinDate, 'ALL', 'ALL');
});


// =====================================================================================
// --- GLOBAL CLICK & COLLAPSIBLE DELEGATION ---
// =====================================================================================
document.addEventListener('click', (e) => {
    // Roll Chain / Option Actions Button
    const chainBtn = e.target.closest('.btn-icon-chain');
    if (chainBtn) {
        e.preventDefault();
        const symbol = chainBtn.getAttribute('data-symbol');
        if (symbol) fetchAndShowRollChain(symbol);
        return;
    }

    // Equity ticker '···' button (Quick jump to Chain tab for this symbol)
    const stockBtn = e.target.closest('.symbol-equity-wrap .btn-row-action');
    if (stockBtn) {
        e.preventDefault();
        const symEl = stockBtn.parentElement.querySelector('.symbol-equity-ticker');
        if (symEl) {
            const sym = symEl.textContent.trim();
            window.location.hash = 'chain';
            const chainSymbolInput = document.getElementById('chain-symbol');
            if (chainSymbolInput) {
                chainSymbolInput.value = sym;
                document.getElementById('btn-fetch-chain')?.click();
            }
        }
        return;
    }

    if (e.target.id === 'modal-roll-close' || e.target.closest('#modal-roll-close')) {
        closeRollChainModal();
        return;
    }

    if (e.target.id === 'roll-chain-modal') {
        closeRollChainModal();
        return;
    }
});



import { auth, signInWithEmailAndPassword, signOut, onAuthStateChanged } from './auth.js';
import { checkSchwabStatus, fetchSchwabPortfolio, fetchOptionChain, fetchSPXBoxes, fetchTransactions, syncTransactions, applyTransactionFilters, rawChainData, fetchRealized, applyRealizedFilters, fetchAndShowRollChain, submitOrder, fetchOptionChainRaw } from './api.js';
import { showView, clearDashboard, lastPositions, closeRollChainModal, openOrderModal, closeOrderModal, renderOptionChainTable, renderRollCandidatesTable } from './ui.js';
import { baseUnderlying, isPutOption, formatOptionSymbol, escapeHtml } from './utils.js';
import { initStockPage, loadStockData, onStocksTabActivated, resizeStockChart } from './stocks/stock-page.js';

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
        case 'stocks':
            loadStockData();
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
const tabBtnStocks = document.getElementById('tab-btn-stocks');
const tabBtnChain = document.getElementById('tab-btn-chain');
const tabBtnBox = document.getElementById('tab-btn-box');
const tabBtnRealized = document.getElementById('tab-btn-realized');
const tabBtnTransactions = document.getElementById('tab-btn-transactions');
const tabContentPortfolio = document.getElementById('tab-content-portfolio');
const tabContentStocks = document.getElementById('tab-content-stocks');
const tabContentChain = document.getElementById('tab-content-chain');
const tabContentBox = document.getElementById('tab-content-box');
const tabContentRealized = document.getElementById('tab-content-realized');
const tabContentTransactions = document.getElementById('tab-content-transactions');

const allTabBtns = [tabBtnPortfolio, tabBtnStocks, tabBtnChain, tabBtnBox, tabBtnRealized, tabBtnTransactions];
const allTabContents = [tabContentPortfolio, tabContentStocks, tabContentChain, tabContentBox, tabContentRealized, tabContentTransactions];

// Map of hash fragment -> { btn, content } for each tab
const TAB_MAP = {
    portfolio:    { btn: tabBtnPortfolio,    content: tabContentPortfolio },
    stocks:       { btn: tabBtnStocks,       content: tabContentStocks },
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

    if (currentTabKey === 'stocks') {
        onStocksTabActivated();
    } else if (currentTabKey === 'transactions') {
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

if (tabBtnPortfolio && tabBtnStocks && tabBtnChain && tabBtnBox && tabBtnRealized && tabBtnTransactions) {
    tabBtnPortfolio.addEventListener('click',    () => navigateToTab('portfolio'));
    tabBtnStocks.addEventListener('click',       () => navigateToTab('stocks'));
    tabBtnChain.addEventListener('click',        () => navigateToTab('chain'));
    tabBtnBox.addEventListener('click',          () => navigateToTab('box'));
    tabBtnRealized.addEventListener('click',     () => navigateToTab('realized'));
    tabBtnTransactions.addEventListener('click', () => navigateToTab('transactions'));
}

window.addEventListener('resize', resizeStockChart);


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
// =====================================================================================
// --- TRANSACTIONS ---
// =====================================================================================
document.getElementById('btn-sync-transactions')?.addEventListener('click', syncTransactions);

const handleTransactionFilter = () => {
    applyTransactionFilters();
};

document.getElementById('btn-filter-transactions')?.addEventListener('click', handleTransactionFilter);
document.getElementById('txn-account')?.addEventListener('change', handleTransactionFilter);
document.getElementById('txn-type')?.addEventListener('change', handleTransactionFilter);
document.getElementById('txn-from-date')?.addEventListener('change', handleTransactionFilter);
document.getElementById('txn-to-date')?.addEventListener('change', handleTransactionFilter);
document.getElementById('txn-symbol')?.addEventListener('keyup', (e) => {
    if (e.key === 'Enter') handleTransactionFilter();
});
document.getElementById('txn-from-date')?.addEventListener('keyup', (e) => {
    if (e.key === 'Enter') handleTransactionFilter();
});
document.getElementById('txn-to-date')?.addEventListener('keyup', (e) => {
    if (e.key === 'Enter') handleTransactionFilter();
});

document.getElementById('btn-reset-transactions')?.addEventListener('click', () => {
    const symbolInput = document.getElementById('txn-symbol');
    const accountSelect = document.getElementById('txn-account');
    const typeSelect = document.getElementById('txn-type');
    const fromDateInput = document.getElementById('txn-from-date');
    const toDateInput = document.getElementById('txn-to-date');

    if (symbolInput) symbolInput.value = 'ALL';
    if (accountSelect) accountSelect.value = 'ALL';
    if (typeSelect) typeSelect.value = 'TRADE';
    if (fromDateInput) fromDateInput.value = '';
    if (toDateInput) toDateInput.value = '';

    applyTransactionFilters();
});

// =====================================================================================
// --- REALIZED GAIN/LOSS ---
// =====================================================================================
const handleRealizedFilter = () => {
    applyRealizedFilters();
};

document.getElementById('btn-filter-realized')?.addEventListener('click', handleRealizedFilter);
document.getElementById('realized-account')?.addEventListener('change', handleRealizedFilter);
document.getElementById('realized-type')?.addEventListener('change', handleRealizedFilter);
document.getElementById('realized-symbol')?.addEventListener('keyup', (e) => {
    if (e.key === 'Enter') handleRealizedFilter();
});
document.getElementById('realized-from-date')?.addEventListener('change', handleRealizedFilter);
document.getElementById('realized-from-date')?.addEventListener('keyup', (e) => {
    if (e.key === 'Enter') handleRealizedFilter();
});
document.getElementById('realized-to-date')?.addEventListener('change', handleRealizedFilter);
document.getElementById('realized-to-date')?.addEventListener('keyup', (e) => {
    if (e.key === 'Enter') handleRealizedFilter();
});

document.getElementById('btn-reset-realized')?.addEventListener('click', () => {
    const symbolInput = document.getElementById('realized-symbol');
    const fromDateInput = document.getElementById('realized-from-date');
    const toDateInput = document.getElementById('realized-to-date');
    const accountSelect = document.getElementById('realized-account');
    const typeSelect = document.getElementById('realized-type');
    if (symbolInput) symbolInput.value = 'ALL';
    if (accountSelect) accountSelect.value = 'ALL';
    if (typeSelect) typeSelect.value = 'ALL';
    const currentYear = new Date().getFullYear();
    const defaultFromDate = `${currentYear}-01-01`;
    if (fromDateInput) fromDateInput.value = defaultFromDate;
    if (toDateInput) toDateInput.value = '';
    applyRealizedFilters();
});


// =====================================================================================
// --- GLOBAL CLICK & COLLAPSIBLE DELEGATION ---
// =====================================================================================
document.addEventListener('click', (e) => {
    // Chain Tab: Buy / Sell buttons
    const tradeBtn = e.target.closest('.btn-trade-buy, .btn-trade-sell');
    if (tradeBtn) {
        e.preventDefault();
        const symbol = tradeBtn.dataset.symbol;
        const action = tradeBtn.dataset.action; // 'BTO' or 'STO'
        const price = tradeBtn.dataset.price;
        const mark = tradeBtn.dataset.mark;
        const bid = tradeBtn.dataset.bid;
        const ask = tradeBtn.dataset.ask;

        openOrderModal({
            symbol,
            instruction: action,
            quantity: 1,
            price,
            duration: 'GOOD_TILL_CANCEL',
            mark,
            bid,
            ask
        });
        return;
    }

    // Option row '···' dropdown trigger
    const optionMenuBtn = e.target.closest('.btn-option-menu-trigger');
    if (optionMenuBtn) {
        e.preventDefault();
        e.stopPropagation();

        const symbol = optionMenuBtn.dataset.symbol;
        const account = optionMenuBtn.dataset.account;
        const qty = parseFloat(optionMenuBtn.dataset.qty || '0');
        const cost = parseFloat(optionMenuBtn.dataset.cost || '0');
        const val = parseFloat(optionMenuBtn.dataset.val || '0');

        const menu = document.getElementById('option-context-menu');
        if (!menu) return;

        menu.dataset.symbol = symbol;
        menu.dataset.account = account;
        menu.dataset.qty = qty;
        menu.dataset.cost = cost;
        menu.dataset.val = val;

        const isShort = qty < 0;
        const closeLabel = document.getElementById('context-menu-close-label');
        if (closeLabel) {
            closeLabel.textContent = isShort ? 'BTC (Buy to Close)' : 'STC (Sell to Close)';
        }

        const rect = optionMenuBtn.getBoundingClientRect();
        menu.classList.remove('hidden');

        const menuWidth = 170;
        let left = rect.left;
        if (left + menuWidth > window.innerWidth - 10) {
            left = window.innerWidth - menuWidth - 10;
        }
        let top = rect.bottom + 4;
        if (top + 130 > window.innerHeight) {
            top = rect.top - 120;
        }
        menu.style.top = `${Math.max(10, top)}px`;
        menu.style.left = `${Math.max(10, left)}px`;
        return;
    }

    // Option Context Menu Action: Close (BTC / STC)
    const closeItem = e.target.closest('#context-menu-close-action');
    if (closeItem) {
        e.preventDefault();
        const menu = document.getElementById('option-context-menu');
        const symbol = menu.dataset.symbol;
        const account = menu.dataset.account;
        const qty = parseFloat(menu.dataset.qty || '0');
        const cost = parseFloat(menu.dataset.cost || '0');
        const val = parseFloat(menu.dataset.val || '0');

        const isShort = qty < 0;
        const instruction = isShort ? 'BTC' : 'STC';
        const buyPrice = Math.abs(cost) || Math.abs(val) || 0;
        const limitPrice = Number((buyPrice * 0.3).toFixed(2));

        openOrderModal({
            symbol,
            instruction,
            quantity: Math.abs(qty) || 1,
            price: limitPrice,
            duration: 'GOOD_TILL_CANCEL',
            account,
            buyPrice
        });
        menu.classList.add('hidden');
        return;
    }

    // Option Context Menu Action: Roll
    const rollItem = e.target.closest('#context-menu-roll-action');
    if (rollItem) {
        e.preventDefault();
        const menu = document.getElementById('option-context-menu');
        const symbol = menu.dataset.symbol;
        const account = menu.dataset.account;
        const qty = parseFloat(menu.dataset.qty || '0');
        const cost = parseFloat(menu.dataset.cost || '0');
        const val = parseFloat(menu.dataset.val || '0');

        const targetMark = Math.abs(val) || Math.abs(cost) || 0;
        const underlying = baseUnderlying(symbol);
        const isPut = isPutOption(symbol);

        let dte = 0;
        const pos = (lastPositions || []).find(p => p.symbol === symbol && String(p.accountNumber) === String(account));
        if (pos && pos.dte !== undefined) dte = pos.dte;

        menu.classList.add('hidden');

        // Open Order Modal in Roll Mode
        openOrderModal({
            mode: 'roll',
            symbol,
            underlying,
            account,
            quantity: Math.abs(qty) || 1,
            mark: targetMark,
            dte,
            isPut
        });

        // Load candidate options chain directly into the roll modal
        loadRollCandidatesForModal(symbol, underlying, isPut ? 'PUT' : 'CALL', targetMark, dte);
        return;
    }

    // Option Context Menu Action: Roll History
    const histItem = e.target.closest('#context-menu-history-action');
    if (histItem) {
        e.preventDefault();
        const menu = document.getElementById('option-context-menu');
        const symbol = menu.dataset.symbol;
        if (symbol) fetchAndShowRollChain(symbol);
        menu.classList.add('hidden');
        return;
    }

    // Click outside floating context menu -> hide it
    const menu = document.getElementById('option-context-menu');
    if (menu && !menu.classList.contains('hidden') && !e.target.closest('#option-context-menu')) {
        menu.classList.add('hidden');
    }

    // Clear roll filter button in Chain tab
    if (e.target.id === 'btn-clear-roll-filter' || e.target.closest('#btn-clear-roll-filter')) {
        e.preventDefault();
        window.activeRollFilter = null;
        renderOptionChainTable(rawChainData.chain || []);
        return;
    }

    // Roll Chain / Option Actions Button (legacy or fallback)
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

    // Modal Close Buttons
    if (e.target.id === 'modal-roll-close' || e.target.closest('#modal-roll-close')) {
        closeRollChainModal();
        return;
    }

    if (e.target.id === 'roll-chain-modal') {
        closeRollChainModal();
        return;
    }

    if (e.target.id === 'modal-order-close' || e.target.closest('#modal-order-close') || e.target.id === 'btn-order-cancel') {
        closeOrderModal();
        return;
    }

    if (e.target.id === 'order-modal') {
        closeOrderModal();
        return;
    }
});

// Auto-close context menu on window scroll
window.addEventListener('scroll', () => {
    document.getElementById('option-context-menu')?.classList.add('hidden');
}, true);


// =====================================================================================
// --- ORDER MODAL SUBMISSION / PREVIEW ---
// =====================================================================================
async function loadRollCandidatesForModal(symbol, underlying, contractType, targetMark, currentDte) {
    const container = document.getElementById('roll-chain-candidates-container');
    if (!container) return;

    container.innerHTML = `<div class="no-data-msg" style="padding: 16px;"><p>Loading live options chain for ${underlying}...</p></div>`;

    try {
        const data = await fetchOptionChainRaw(underlying, contractType);
        const rawChain = data.chain || [];

        window._activeRollContext = {
            targetSymbol: symbol,
            underlying,
            contractType,
            mark: targetMark,
            dte: currentDte,
            chain: rawChain,
            selectedSymbol: ''
        };

        refreshRollCandidatesDisplay();
    } catch (err) {
        console.error('Failed to load roll chain:', err);
        container.innerHTML = `<div class="no-data-msg" style="color:var(--accent-red); padding: 16px;"><p>Failed to fetch option chain: ${err.message}</p></div>`;
    }
}

function refreshRollCandidatesDisplay() {
    const ctx = window._activeRollContext;
    if (!ctx || !ctx.chain) return;

    const filterVal = document.getElementById('roll-chain-expiry-filter')?.value || 'later';
    let candidates = ctx.chain.filter(c => c.symbol !== ctx.targetSymbol);

    if (filterVal === 'later') {
        const minDte = (ctx.dte !== undefined && ctx.dte >= 0) ? ctx.dte : 0;
        candidates = candidates.filter(c => (c.dte !== undefined ? c.dte : 0) >= minDte);
    }

    // Sort: primarily by DTE / expiration date ascending, then by strike ascending
    candidates.sort((a, b) => {
        const dteA = a.dte !== undefined ? a.dte : 9999;
        const dteB = b.dte !== undefined ? b.dte : 9999;
        if (dteA !== dteB) return dteA - dteB;
        return (a.strikePrice || 0) - (b.strikePrice || 0);
    });

    renderRollCandidatesTable(candidates, ctx, ctx.selectedSymbol);
}

// Click listener for target candidate selection
document.getElementById('roll-chain-candidates-container')?.addEventListener('click', (e) => {
    const row = e.target.closest('.roll-candidate-row');
    if (!row) return;

    const sym = row.dataset.symbol;
    const mark = parseFloat(row.dataset.mark) || 0;
    const diff = parseFloat(row.dataset.diff) || 0;

    const ctx = window._activeRollContext;
    if (ctx) ctx.selectedSymbol = sym;

    // Highlight row
    document.querySelectorAll('.roll-candidate-row').forEach(r => {
        r.classList.remove('selected-roll-candidate');
        const btn = r.querySelector('.btn-select-target');
        if (btn) btn.textContent = 'Select';
    });
    row.classList.add('selected-roll-candidate');
    const btn = row.querySelector('.btn-select-target');
    if (btn) btn.textContent = '✓ Selected';

    // Update Leg 2 UI
    const openSymbolEl = document.getElementById('roll-open-symbol');
    if (openSymbolEl) openSymbolEl.textContent = formatOptionSymbol(sym);
    const openMarkEl = document.getElementById('roll-open-mark');
    if (openMarkEl) openMarkEl.textContent = `Mark: ~$${mark.toFixed(2)}`;
    const targetInput = document.getElementById('roll-target-symbol');
    if (targetInput) targetInput.value = sym;

    // Auto-calculate Net Credit / Debit Limit Price
    const orderTypeEl = document.getElementById('roll-order-type');
    const priceEl = document.getElementById('roll-price');
    const hintEl = document.getElementById('roll-price-hint');

    const currentMark = ctx ? ctx.mark : 0;
    if (diff >= 0) {
        if (orderTypeEl) orderTypeEl.value = 'NET_CREDIT';
        if (priceEl) priceEl.value = diff.toFixed(2);
        if (hintEl) hintEl.textContent = `Current Mark: $${currentMark.toFixed(2)} | Target Mark: $${mark.toFixed(2)} => Net Credit: $${diff.toFixed(2)}`;
    } else {
        if (orderTypeEl) orderTypeEl.value = 'NET_DEBIT';
        if (priceEl) priceEl.value = Math.abs(diff).toFixed(2);
        if (hintEl) hintEl.textContent = `Current Mark: $${currentMark.toFixed(2)} | Target Mark: $${mark.toFixed(2)} => Net Debit: $${Math.abs(diff).toFixed(2)}`;
    }
});

document.getElementById('roll-chain-expiry-filter')?.addEventListener('change', () => {
    refreshRollCandidatesDisplay();
});

async function handleOrderSubmit(preview = false) {
    const isRoll = !document.getElementById('order-roll-section')?.classList.contains('hidden');

    const statusEl = document.getElementById('order-status-msg');
    const submitBtn = document.getElementById('btn-order-submit');
    const previewBtn = document.getElementById('btn-order-preview');

    function showStatus(html, type) {
        if (!statusEl) return;
        statusEl.className = `order-status-msg ${type}`;
        statusEl.innerHTML = html;
        statusEl.classList.remove('hidden');
    }

    let payload;
    let desc = '';

    if (isRoll) {
        const closeSymbol = document.getElementById('order-symbol')?.value.trim();
        const openSymbol = document.getElementById('roll-target-symbol')?.value.trim();
        const account = document.getElementById('roll-account')?.value;
        const quantity = parseInt(document.getElementById('roll-quantity')?.value, 10);
        const orderType = document.getElementById('roll-order-type')?.value || 'NET_CREDIT';
        const price = parseFloat(document.getElementById('roll-price')?.value);
        const duration = document.getElementById('roll-duration')?.value || 'GOOD_TILL_CANCEL';

        if (!openSymbol) {
            showStatus('Please select a target option contract from the chain table below.', 'error');
            return;
        }
        if (isNaN(quantity) || quantity <= 0) {
            showStatus('Quantity must be at least 1.', 'error');
            return;
        }
        if (isNaN(price) || price < 0) {
            showStatus('Net price must be greater than or equal to 0.00.', 'error');
            return;
        }

        payload = {
            account,
            roll: true,
            close_symbol: closeSymbol,
            open_symbol: openSymbol,
            quantity,
            order_type: orderType,
            price,
            duration,
            session: 'NORMAL',
            preview
        };

        const typeLabel = orderType === 'NET_CREDIT' ? 'Net Credit' : 'Net Debit';
        desc = `Roll ${quantity}x Close <strong>${formatOptionSymbol(closeSymbol)}</strong> ➔ Open <strong>${formatOptionSymbol(openSymbol)}</strong> @ $${price.toFixed(2)} (${typeLabel}, ${duration})`;
    } else {
        const symbol = document.getElementById('order-symbol')?.value.trim();
        const account = document.getElementById('order-account')?.value;
        const instruction = document.getElementById('order-instruction')?.value;
        const quantity = parseInt(document.getElementById('order-quantity')?.value, 10);
        const orderType = document.getElementById('order-type')?.value || 'LIMIT';
        const price = parseFloat(document.getElementById('order-price')?.value);
        const duration = document.getElementById('order-duration')?.value || 'GOOD_TILL_CANCEL';

        if (!symbol) {
            showStatus('Invalid symbol.', 'error');
            return;
        }
        if (isNaN(quantity) || quantity <= 0) {
            showStatus('Quantity must be at least 1.', 'error');
            return;
        }
        if (orderType === 'LIMIT' && (isNaN(price) || price < 0)) {
            showStatus('Limit price must be greater than or equal to 0.', 'error');
            return;
        }
        if (['NET_DEBIT', 'NET_CREDIT'].includes(orderType) && (isNaN(price) || price < 0)) {
            showStatus('Price is required for this order type.', 'error');
            return;
        }

        const priceRequired = ['LIMIT', 'NET_DEBIT', 'NET_CREDIT'].includes(orderType);

        payload = {
            account,
            symbol,
            instruction,
            quantity,
            order_type: orderType,
            duration,
            session: 'NORMAL',
            preview
        };
        if (priceRequired) {
            payload.price = price;
        }

        desc = `${instruction} ${quantity}x <strong>${formatOptionSymbol(symbol)}</strong> @ $${priceRequired ? price.toFixed(2) : 'MKT'} (${duration})`;
    }

    try {
        if (submitBtn) submitBtn.disabled = true;
        if (previewBtn) previewBtn.disabled = true;

        showStatus(`<p style="margin:0;">${preview ? 'Simulating preview with Schwab...' : 'Submitting order to Schwab...'}</p>`, 'preview-info');

        const res = await submitOrder(payload);

        if (preview) {
            const previewData = res.preview || res || {};
            const valResult = previewData.orderValidationResult || 'OK';
            const comm = previewData.commissionAndFee?.commission?.commissionsTotal ?? 0;
            showStatus(`
                <strong>✓ Preview Result: ${valResult}</strong><br>
                Action: ${desc}<br>
                Est. Commission / Fee: $${Number(comm).toFixed(2)}
            `, 'preview-info');
        } else {
            const orderId = res.order_id || res.orderId || 'Submitted';
            showStatus(`
                <strong>✓ Order Placed Successfully!</strong><br>
                Order ID: <strong>#${orderId}</strong><br>
                ${desc}
            `, 'success');

            setTimeout(() => {
                fetchSchwabPortfolio();
            }, 1500);
        }
    } catch (err) {
        console.error('Order submission error:', err);
        showStatus(`<strong>Order Error:</strong> ${escapeHtml(err.message)}`, 'error');
    } finally {
        if (submitBtn) submitBtn.disabled = false;
        if (previewBtn) previewBtn.disabled = false;
    }
}

document.getElementById('btn-order-preview')?.addEventListener('click', () => handleOrderSubmit(true));
document.getElementById('btn-order-submit')?.addEventListener('click', () => handleOrderSubmit(false));





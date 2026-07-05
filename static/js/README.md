# Frontend Architecture

This document outlines the structure of the frontend codebase in `static/js`. The application uses Vanilla JavaScript with ES6 Modules to organize and manage logic.

## Module Breakdown

1. **`main.js`**: The entry point of the application. It handles routing between views (Login vs Main Dashboard), sets up global event listeners, and manages tab navigation (Portfolio vs Option Chains). It coordinates between the Auth, API, and UI modules.

2. **`auth.js`**: Encapsulates Firebase authentication logic. It exports the initialized `auth` instance and standard login/logout functions. `main.js` listens to `onAuthStateChanged` to manage view states.

3. **`api.js`**: Contains all network requests. Functions include `checkSchwabStatus`, `connectSchwab`, `disconnectSchwab`, `fetchSchwabPortfolio`, and `fetchOptionChain`. It directly calls UI rendering functions from `ui.js` when data is retrieved.

4. **`ui.js`**: Responsible for DOM manipulation and rendering. It handles injecting HTML for the dashboard summaries, positions table, orders table, and the options chain explorer. It avoids duplicating rendering logic by utilizing shared helper functions.

5. **`utils.js`**: Pure functional utilities that have no side-effects or DOM dependencies. Contains currency/number formatting, P/L display calculation logic, badge class assignment, and array sorting logic for grouping positions.

## Design Decisions
- **No Build Step**: The frontend uses native browser ES6 Modules (`<script type="module">`). There is no bundler (like Webpack or Vite) involved in this vanilla stack.
- **De-duplication**: Table rendering for Orders and Positions utilizes the same `getPLFormatting` and `getSymbolBadgeClass` utility functions to maintain visual consistency and reduce HTML boilerplate.

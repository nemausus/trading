# Codebase Maintenance Rules

## Trailing Whitespace Cleanup Rule
After editing, creating, or modifying any code files in this workspace (Python, Javascript, CSS, HTML, Markdown, etc.), the agent MUST always run the trailing space post-processing script:
```bash
python scripts/remove_trailing_spaces.py
```
This keeps all codebase files cleanly formatted and free of trailing spaces/tabs.

---

## Python Coding Conventions

### Shared Constants
- `SCHWAB_REQUEST_TIMEOUT` and `SCHWAB_TZ` are defined **once** in `constants.py`.
  Never redefine them locally in any module. Always import from `constants`.
- Module-level constants (e.g. `_BATCH_SIZE`, `_SPX_BOX_ROUNDING`) must be placed
  at the top of the file, not inside functions or methods.

### Logging Style
- All `logging` calls must use **`%`-style formatting**, not f-strings.
  - ✅ `logging.error("Failed for user %s: %s", uid, e)`
  - ❌ `logging.error(f"Failed for user {uid}: {e}")`
- This applies to `logging.info`, `logging.warning`, `logging.error`, and `logging.debug`.
- `app.logger.*` calls in `app.py` (Flask context) follow the same `%`-style rule.

### Flask Application Structure (`app.py`)
- `app = Flask(__name__)` must be defined **before** any function that references it
  (including decorators that call `app.logger`).
- Do **not** put raw `requests` HTTP calls inside Flask route handlers.
  All Schwab API calls belong in `schwab_portfolio.py` or the appropriate service module.
- Use the `@require_firebase_auth` + `@require_schwab_token` decorator stack for any
  route that needs both Firebase auth and a Schwab access token. Do not copy-paste the
  token-fetch-or-400 block into new routes.
- When adding a new Schwab data route, follow this pattern:
  ```python
  @app.route('/api/schwab/<endpoint>')
  @limiter.limit("<N> per minute")
  @require_firebase_auth
  @require_schwab_token
  def my_route(decoded_token, access_token):
      uid = decoded_token['uid']
      ...
  ```

### Input Validation
- Validate query parameters strictly: use `int()` / `float()` and catch `ValueError`
  to return a 400. Do not silently discard invalid tokens (e.g. non-digit values in a
  comma-separated list).
- Reuse `_validate_range(name, value, *, lo, hi, typ)` in `schwab_portfolio.py` for
  numeric range checks instead of repeating the isinstance/bounds pattern.

### Firestore (`firestore_db.py`)
- `get_db()` is a lazy singleton. Do not call `firestore.client()` directly anywhere
  else in the codebase.
- Use `db.get_all(doc_refs)` for batch existence checks instead of N individual `.get()`
  calls in a loop.
- Batch write constants (`_BATCH_SIZE`) must be at module level.

### Helper Extraction
- Business logic inside long functions should be extracted to clearly named private
  helpers (prefix `_`) with docstrings.
- Examples of established helpers that must not be inlined again:
  - `_is_short_put(pos)` — short-put predicate in `schwab_portfolio.py`
  - `_merge_orders(active_orders, pos_index)` — order enrichment in `schwab_portfolio.py`
  - `_normalize_to_seconds(iso_str)` — ISO offset normalisation in `schwab_transactions.py`
  - `_validate_range(name, value, *, lo, hi, typ)` — param validation in `schwab_portfolio.py`

### Silent Fallbacks
- Functions that silently fall back to a default on error **must** log a `warning` before
  doing so, so bugs are diagnosable without a debugger.
  - Example: `to_iso_datetime_str` logs the bad value before returning `now()`.

### Class-Level Constants
- Constants that control class behaviour (e.g. timeouts, buffer sizes) belong at
  **class level**, not inside individual methods.
  - Example: `SchwabAuthManager.EXPIRATION_BUFFER_SECONDS = 300`

### PEP 8
- Two blank lines between every top-level function and class definition.
- One blank line between methods inside a class.
- Use `python3 scripts/remove_trailing_spaces.py` (not `python`) as the interpreter
  command on this machine.

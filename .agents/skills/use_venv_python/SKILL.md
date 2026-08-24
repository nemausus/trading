---
name: use_venv_python
description: Instructions for executing Python scripts, running tests, and executing CLI utilities using the local virtual environment interpreter (.venv/bin/python).
---

# Use Virtual Environment Python Skill

This skill provides instructions to ensure all Python commands, test executions, and CLI tools run using the workspace's local virtual environment interpreter (`./.venv/bin/python`).

## Usage Instructions

1. **Always Use `.venv/bin/python` for Execution**:
   When invoking Python scripts, running tests, or executing CLI utilities in this workspace, ALWAYS use `./.venv/bin/python` instead of system `python` or `python3`:
   ```bash
   ./.venv/bin/python script.py --account acc2 txns
   ./.venv/bin/python -m unittest discover tests
   ```

2. **Why This Is Required**:
   System `python` / `python3` does not include project dependencies (`firebase-admin`, `requests`, `python-dotenv`, etc.). The virtual environment at `./.venv` contains all installed workspace requirements.

3. **Post-Processing Exception**:
   The trailing whitespace cleanup script uses the standard command:
   ```bash
   python3 scripts/remove_trailing_spaces.py
   ```

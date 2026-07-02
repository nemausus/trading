# Codebase Maintenance Rules

## Trailing Whitespace Cleanup Rule
After editing, creating, or modifying any code files in this workspace (Python, Javascript, CSS, HTML, Markdown, etc.), the agent MUST always run the trailing space post-processing script:
```bash
python scripts/remove_trailing_spaces.py
```
This keeps all codebase files cleanly formatted and free of trailing spaces/tabs.

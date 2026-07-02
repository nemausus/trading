---
name: remove_trailing_spaces
description: Stuffs post-processing routines to strip trailing spaces and whitespaces from generated or edited codebase files.
---

# Remove Trailing Spaces Skill

This skill provides a post-processing routine to strip all trailing spaces/tabs from codebase files after generation or edit.

## Usage Instructions
Run the utility script in the workspace using the python command:
```bash
python scripts/remove_trailing_spaces.py
```
This script recursively scans the project workspace (excluding environment, version control, and temporary folders) and strips trailing space/tab characters from all lines.

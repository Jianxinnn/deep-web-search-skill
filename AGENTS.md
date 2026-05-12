# AGENTS.md

This repository is a standalone Deep Web Search skill distribution.

Guidelines:

- Keep this project thin. Do not copy external core source code, provider payloads, run bundles, `.venv`, or `.git` history into it.
- The installable skill lives in `skills/deep-web-search/`.
- The standalone CLI lives in `skills/deep-web-search/scripts/deep_web_search.py`.
- Generated bundle outputs must be written to the caller's working directory, not inside this skill repository.
- Skill instructions should tell agents how to run the bundled script for deep academic search.

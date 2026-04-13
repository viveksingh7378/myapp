"""
ai_agent — AI-powered code analysis and self-healing pipeline.

Modules
-------
analyzer    Main entry point: scans source files, calls Gemini/Ollama,
            applies fixes, and pushes changes to GitHub.
log_parser  Parses Jenkins/pytest log output into structured error records.
remediate   Applies file-level fix actions (replace, insert_before,
            insert_after) returned by the AI.
validator   Post-fix validation: re-runs flake8/pytest to confirm fixes
            did not introduce new errors.

Environment variables required at runtime
-----------------------------------------
GEMINI_API_KEY   Google Gemini API key (primary AI backend).
GITHUB_TOKEN     Fine-grained or classic PAT with repo write access
                 (used to push AI-generated fixes back to GitHub).
"""

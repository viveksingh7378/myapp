"""
AI Code Analyzer — powered by Google Gemini

Gemini reads every source file and finds syntax errors itself.
It applies single-line fixes, runs tests to verify, then pushes ONLY if tests pass.
"""

import os
import sys
import json
import subprocess
import time
from collections import defaultdict

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ANALYSIS_LOG = os.path.join(PROJECT_ROOT, "analysis_output.txt")

SKIP_DIRS = {"venv", "__pycache__", ".git", ".pytest_cache", "node_modules"}
SKIP_FILES = {"analysis_output.txt", "validation_output.txt",
              "test_output.txt", "lint_output.txt", "trivy-report.json"}
ANALYZE_EXTS = {".py", ".html", ".htm", ".js", ".css", ".json"}
MAX_FILE_CHARS = 60000  # large enough for all project files; only trim if truly huge


# ── Collect source files ──────────────────────────────────────────

def collect_files():
    files = {}
    for dirpath, dirnames, filenames in os.walk(PROJECT_ROOT):
        dirnames[:] = [d for d in dirnames
                       if d not in SKIP_DIRS and not d.startswith(".")]
        for filename in filenames:
            if filename in SKIP_FILES:
                continue
            ext = os.path.splitext(filename)[1].lower()
            if ext not in ANALYZE_EXTS:
                continue
            full_path = os.path.join(dirpath, filename)
            rel_path = os.path.relpath(full_path, PROJECT_ROOT)
            try:
                with open(full_path, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
                if len(content) > MAX_FILE_CHARS:
                    half = MAX_FILE_CHARS // 2
                    content = (content[:half]
                               + f"\n... [truncated] ...\n"
                               + content[-half:])
                files[rel_path] = content
            except Exception as e:
                print(f"  Warning: could not read {rel_path} — {e}")
    return files


# ── Build Gemini prompt ───────────────────────────────────────────

def build_prompt(files_dict):
    file_sections = ""
    for rel_path, content in files_dict.items():
        numbered = "\n".join(f"{i+1:4d} | {line}"
                             for i, line in enumerate(content.splitlines()))
        file_sections += f"\n{'='*60}\nFILE: {rel_path}\n{'='*60}\n{numbered}\n"

    prompt = f"""You are a CI/CD pipeline repair agent. Your ONLY job is to find
SYNTAX ERRORS that would cause the code to crash or fail to import.

Project files:
{file_sections}

STRICT RULES — follow exactly:

1. ONLY report syntax errors that BREAK execution:
   - Python: missing colon after def/if/for/class, wrong indentation, missing import, undefined name
   - HTML: missing required tags (<html>, <head>, <body>), unclosed tags
   - CSS: mismatched braces
   - JSON: invalid syntax (trailing commas, unquoted keys)

2. DO NOT report or fix:
   - Code style, formatting, or naming preferences
   - Architecture improvements, race conditions, thread safety
   - Logic that works but could be improved
   - Anything needing more than one line to fix

3. EVERY fix must be a SINGLE LINE change:
   - original_line = copy ONE line exactly as it appears in the file (character for character)
   - fixed_line = the corrected version of only that one line
   - NEVER put \\n inside original_line or fixed_line
   - NEVER suggest replacing a single line with multiple lines

4. original_line must EXACTLY match the file content (copy it directly from the numbered listing)

Return ONLY raw JSON, no markdown, no code fences.

If no syntax errors found:
{{"status": "clean", "message": "No syntax errors found", "issues": []}}

If errors found:
{{
  "status": "issues_found",
  "summary": "one sentence describing the syntax errors found",
  "issues": [
    {{
      "file_path": "relative/path.py",
      "language": "python|html|css|json",
      "line_number": 42,
      "original_line": "exact single line from the file",
      "fixed_line": "corrected single line",
"description": "one sentence: what syntax error this fixes",
      "severity": "error"
    }}
  ]
}}"""
    return prompt


# ── Call Gemini ───────────────────────────────────────────────────

def call_gemini_analyze(prompt):
    from google import genai
    from google.genai import errors as genai_errors

    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    models = ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-2.0-flash-lite"]

    for model_name in models:
        try:
            print(f"  Trying {model_name}...")
            response = client.models.generate_content(model=model_name, contents=prompt)
            return response.text.strip()
        except genai_errors.ClientError as e:
            if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                print(f"  {model_name} quota exceeded — trying next...")
                time.sleep(5)
                continue
            else:
                raise e
    raise Exception("All Gemini models exhausted")


# ── Validate a fix before applying ───────────────────────────────

def is_safe_fix(issue):
    """Reject any fix that is unsafe: multi-line, empty, or line-deleting."""
    orig = issue.get("original_line", "")
    fixed = issue.get("fixed_line", "")
    loc = f"{issue['file_path']} line {issue.get('line_number')}"

    # original_line must actually identify a real line
    if not orig.strip():
        print(f"  ⚠ Skipping fix with empty original_line for {loc}")
        return False

    # fixed_line must not be empty — we never delete lines
    if not fixed.strip():
        print(f"  ⚠ Skipping fix with empty fixed_line (would delete line) for {loc}")
        return False

    # no newlines in either side — truly single-line only
    if "\n" in orig or "\n" in fixed:
        print(f"  ⚠ Skipping multi-line fix for {loc}")
        return False
    if "\\n" in orig or "\\n" in fixed:
        print(f"  ⚠ Skipping fix with escaped newline for {loc}")
        return False

    # original and fixed must actually differ (compare raw — indentation changes are valid)
    if orig == fixed:
        print(f"  ⚠ Skipping no-op fix (original == fixed) for {loc}")
        return False

    return True


# ── Apply a single fix ────────────────────────────────────────────

def apply_fix(file_path, line_number, original_line, fixed_line):
    full_path = os.path.join(PROJECT_ROOT, file_path)
    if not os.path.exists(full_path):
        print(f"  ✗ File not found: {full_path}")
        return False

    with open(full_path, "r", encoding="utf-8", errors="replace") as f:
        lines = f.readlines()

    # Strategy 1: exact line number match
    if line_number and 1 <= line_number <= len(lines):
        actual = lines[line_number - 1].rstrip("\n").rstrip("\r")
        orig = original_line.strip()
        # orig must be non-empty AND the stripped content must match the actual line
        if orig and (orig in actual or actual.strip() in orig):
            ending = "\n" if lines[line_number - 1].endswith("\n") else ""
            # Preserve fixed_line exactly as Gemini wrote it (including indentation)
            lines[line_number - 1] = fixed_line + ending
            with open(full_path, "w", encoding="utf-8") as f:
                f.writelines(lines)
            print(f"  ✓ Fixed line {line_number} in {file_path}")
            return True

    # Strategy 2: search all lines (strip-compare for matching, preserve indent when writing)
    if original_line.strip():
        for i, line in enumerate(lines):
            if original_line.strip() in line:
                ending = "\n" if line.endswith("\n") else ""
                # Replace the stripped core content, then attach the new leading indent
                new_line = line.replace(line.rstrip("\n").rstrip("\r"), fixed_line, 1)
                if not new_line.endswith("\n"):
                    new_line += ending
                lines[i] = new_line
                with open(full_path, "w", encoding="utf-8") as f:
                    f.writelines(lines)
                print(f"  ✓ Fixed line {i+1} via search in {file_path}")
                return True

    print(f"  ✗ Could not locate: {repr(original_line)} in {file_path}")
    return False


# ── Run pytest ────────────────────────────────────────────────────

def run_tests():
    print("\nAI Analyzer: Running pytest to verify fixes...")
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/", "--tb=short", "-q"],
        capture_output=True, text=True, cwd=PROJECT_ROOT
    )
    print(result.stdout)
    if result.returncode == 0:
        print("AI Analyzer: All tests passed ✓")
        return True
    print("AI Analyzer: Tests still failing:")
    print(result.stderr or result.stdout)
    return False


# ── Git commit and push ───────────────────────────────────────────

def git_commit_and_push(fixed_files, summary):
    repo_url = subprocess.run(
        ["git", "config", "--get", "remote.origin.url"],
        capture_output=True, text=True, cwd=PROJECT_ROOT
    ).stdout.strip()

    github_token = os.environ.get("GITHUB_TOKEN", "")
    if github_token and "github.com" in repo_url:
        authed_url = repo_url.replace("https://", f"https://{github_token}@")
        subprocess.run(["git", "remote", "set-url", "origin", authed_url], cwd=PROJECT_ROOT)

    subprocess.run(["git", "config", "user.email", "ai-bot@pipeline.local"], cwd=PROJECT_ROOT)
    subprocess.run(["git", "config", "user.name", "AI-Remediation-Bot"], cwd=PROJECT_ROOT)

    for fp in fixed_files:
        subprocess.run(["git", "add", os.path.join(PROJECT_ROOT, fp)], cwd=PROJECT_ROOT)

    result = subprocess.run(
        ["git", "commit", "-m", f"AI-Fix: {summary[:72]}"],
        capture_output=True, text=True, cwd=PROJECT_ROOT
    )
    if result.returncode != 0:
        print(f"AI Analyzer: Git commit failed — {result.stderr}")
        return False

    push = subprocess.run(
        ["git", "push", "origin", "HEAD:main"],
        capture_output=True, text=True, cwd=PROJECT_ROOT
    )
    if push.returncode == 0:
        print("AI Analyzer: Pushed fix to GitHub ✓")
        return True
    print(f"AI Analyzer: Push failed — {push.stderr}")
    return False


# ── Main ──────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("AI Code Analyzer — Powered by Google Gemini")
    print(f"Project root: {PROJECT_ROOT}")
    print("=" * 60)

    # Step 1: collect files
    print("\nStep 1: Collecting source files...")
    files = collect_files()
    for path in files:
        print(f"  → {path} ({len(files[path])} chars)")
    print(f"  Total: {len(files)} files")

    # Step 2: send to Gemini
    print("\nStep 2: Sending all files to Gemini for analysis...")
    prompt = build_prompt(files)
    raw = call_gemini_analyze(prompt)
    print(f"\nStep 3: Gemini response:\n{raw}\n")

    # Step 3: parse response
    try:
        clean = raw.replace("```json", "").replace("```", "").strip()
        analysis = json.loads(clean)
    except json.JSONDecodeError as e:
        print(f"AI Analyzer: Could not parse Gemini response — {e}")
        sys.exit(2)

    with open(ANALYSIS_LOG, "w") as f:
        f.write(json.dumps(analysis, indent=2))

    # Step 4: check if clean
    if analysis.get("status") == "clean" or not analysis.get("issues"):
        print("AI Analyzer: Gemini found NO syntax errors — all files look correct ✓")
        sys.exit(0)

    # Step 5: report issues
    issues = analysis["issues"]
    errors = [i for i in issues if i.get("severity") == "error"]
    print(f"AI Analyzer: Gemini found {len(errors)} error(s)")
    print(f"Summary: {analysis.get('summary', '')}\n")
    for issue in issues:
        print(f"  [{issue.get('severity','?').upper()}] {issue['file_path']} "
              f"line {issue.get('line_number','?')}: {issue['description']}")

    # Step 6: apply only SAFE single-line fixes (errors only, skip warnings)
    print("\nStep 4: Applying fixes...")
    fixed_files = set()
    applied = 0

    by_file = defaultdict(list)
    for issue in issues:
        if issue.get("severity") == "error" and is_safe_fix(issue):
            by_file[issue["file_path"]].append(issue)

    for file_path, file_issues in by_file.items():
        # apply in reverse line order so earlier fixes don't shift later line numbers
        for issue in sorted(file_issues, key=lambda x: x.get("line_number", 0), reverse=True):
            ok = apply_fix(
                issue["file_path"],
                issue.get("line_number"),
                issue.get("original_line", ""),
                issue.get("fixed_line", "")
            )
            if ok:
                fixed_files.add(issue["file_path"])
                applied += 1

    print(f"\nApplied {applied} fix(es) across {len(fixed_files)} file(s)")

    if applied == 0:
        print("AI Analyzer: Gemini found potential issues but all proposed fixes were invalid")
        print("  (empty fixed_line, no-op, or multi-line fix rejected by safety checks)")
        print("  Proceeding — downstream Lint and Test stages will catch real errors ✓")
        sys.exit(0)

    # Step 5: verify Python syntax on every modified .py file before running tests
    print("\nStep 5: Verifying syntax of modified Python files...")
    syntax_ok = True
    for fp in fixed_files:
        if not fp.endswith(".py"):
            continue
        full_path = os.path.join(PROJECT_ROOT, fp)
        result = subprocess.run(
            [sys.executable, "-m", "py_compile", full_path],
            capture_output=True, text=True
        )
        if result.returncode != 0:
            print(f"  ✗ {fp} has a syntax error after fix: {result.stderr.strip()}")
            syntax_ok = False
        else:
            print(f"  ✓ {fp} syntax OK")

    if not syntax_ok:
        print("\nAI Analyzer: Fix introduced a syntax error — NOT running tests, NOT pushing")
        sys.exit(2)

    # Step 7: run tests — ONLY push if tests pass
    tests_pass = run_tests()

    if not tests_pass:
        print("\nAI Analyzer: Tests still failing after fixes — NOT pushing to GitHub")
        print("Human intervention required to review the remaining errors.")
        sys.exit(2)

    # Step 8: push only after tests pass
    summary = analysis.get("summary", "fixed syntax errors detected by Gemini")
    committed = git_commit_and_push(list(fixed_files), summary)

    if committed:
        print("\nAI Analyzer: Self-healing complete ✓ — pipeline will retrigger")
        sys.exit(1)   # exit 1 = fixed & pushed, Jenkins should retrigger
    else:
        print("\nAI Analyzer: Push failed")
        sys.exit(2)


if __name__ == "__main__":
    main()

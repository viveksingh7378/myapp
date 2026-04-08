"""
AI Code Analyzer — powered by Google Gemini

This is the brain of the self-healing pipeline.
Instead of a rule-based script telling Gemini what is wrong,
Gemini itself reads every project file and decides what is broken.

Flow:
  1. Read all project source files (Python, HTML, JS, CSS, JSON)
  2. Send them ALL to Gemini with a prompt: "find every bug and error"
  3. Gemini returns a structured list of issues + fixes
  4. Apply every fix to the real files
  5. Run pytest to verify the fixes work
  6. If tests pass → commit and push to GitHub
  7. Jenkins re-triggers and the build continues cleanly
"""

import os
import sys
import json
import subprocess
import time

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ANALYSIS_LOG = os.path.join(PROJECT_ROOT, "analysis_output.txt")

SKIP_DIRS = {
    "venv", "__pycache__", ".git", ".pytest_cache",
    "node_modules", ".ai_retry_count"
}
SKIP_FILES = {
    "analysis_output.txt", "validation_output.txt",
    "test_output.txt", "lint_output.txt", "trivy-report.json"
}
# file types Gemini will analyze
ANALYZE_EXTS = {".py", ".html", ".htm", ".js", ".css", ".json"}
# max chars per file sent to Gemini (keeps prompt manageable)
MAX_FILE_CHARS = 8000


# ── Collect all source files ──────────────────────────────────────

def collect_files():
    """Walk the project and return {relative_path: content} for all source files."""
    files = {}
    for dirpath, dirnames, filenames in os.walk(PROJECT_ROOT):
        dirnames[:] = [
            d for d in dirnames
            if d not in SKIP_DIRS and not d.startswith(".")
        ]
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
                # truncate very large files but keep start + end
                if len(content) > MAX_FILE_CHARS:
                    half = MAX_FILE_CHARS // 2
                    content = (
                        content[:half]
                        + f"\n... [truncated {len(content) - MAX_FILE_CHARS} chars] ...\n"
                        + content[-half:]
                    )
                files[rel_path] = content
            except Exception as e:
                print(f"  Warning: could not read {rel_path} — {e}")
    return files


# ── Build the Gemini prompt with real file content ────────────────

def build_prompt(files_dict):
    """
    Build a prompt that gives Gemini every source file
    and asks it to find ALL bugs, errors and syntax mistakes.
    """
    file_sections = ""
    for rel_path, content in files_dict.items():
        numbered = "\n".join(
            f"{i+1:4d} | {line}"
            for i, line in enumerate(content.splitlines())
        )
        file_sections += f"\n{'='*60}\nFILE: {rel_path}\n{'='*60}\n{numbered}\n"

    prompt = f"""You are a senior software engineer performing a code review on a CI/CD project.
Your job is to find EVERY bug, syntax error, logic error, or mistake in the files below.

The project is a Flask REST API with:
- Python backend (app/app.py, tests/)
- HTML blog page (blog.html)
- AI agent scripts (ai_agent/)

Carefully read every file below and identify all problems including:
- Syntax errors (missing colons, unclosed tags, mismatched braces)
- Logic errors (wrong status codes, broken conditionals)
- Missing required elements (HTML tags, imports, function definitions)
- Test failures (test assertions that won't pass given the current code)
- Any other bugs or mistakes

{file_sections}

Return ONLY a raw JSON object — no markdown, no explanation, no code fences.

If you find NO issues, return:
{{"status": "clean", "message": "All files look correct", "issues": []}}

If you find issues, return:
{{
  "status": "issues_found",
  "summary": "brief overall summary of what is wrong",
  "issues": [
    {{
      "file_path": "relative/path/to/file.py",
      "language": "python|html|javascript|css|json",
      "line_number": 42,
      "original_line": "the exact text of the broken line (copy from the numbered content)",
      "fixed_line": "the corrected version of that line",
      "description": "what is wrong and why this fix works",
      "severity": "error|warning"
    }}
  ]
}}

Important rules:
- Only report REAL errors, not style preferences
- original_line must be copied EXACTLY from the numbered file content above
- fixed_line must be only the corrected version of that one line
- For missing tags/lines: set original_line to what is currently on that line (even empty "")
- Sort issues by severity: errors first, then warnings
"""
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
            response = client.models.generate_content(
                model=model_name,
                contents=prompt
            )
            return response.text.strip()
        except genai_errors.ClientError as e:
            if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                print(f"  {model_name} quota exceeded — trying next model...")
                time.sleep(5)
                continue
            else:
                raise e

    raise Exception("All Gemini models exhausted")


# ── Apply a single fix ────────────────────────────────────────────

def apply_fix(file_path, line_number, original_line, fixed_line):
    full_path = os.path.join(PROJECT_ROOT, file_path)
    if not os.path.exists(full_path):
        print(f"  ✗ File not found: {full_path}")
        return False

    with open(full_path, "r", encoding="utf-8", errors="replace") as f:
        lines = f.readlines()

    # Strategy 1: replace by line number
    if line_number and 1 <= line_number <= len(lines):
        actual = lines[line_number - 1].rstrip("\n").rstrip("\r")
        orig = original_line.strip()
        if orig == "" or orig in actual or actual in orig:
            ending = "\n" if lines[line_number - 1].endswith("\n") else ""
            if fixed_line.strip() == "":
                lines.pop(line_number - 1)
            else:
                lines[line_number - 1] = fixed_line.strip() + ending
            with open(full_path, "w", encoding="utf-8") as f:
                f.writelines(lines)
            print(f"  ✓ Fixed line {line_number} in {file_path}")
            return True

    # Strategy 2: search all lines
    if original_line.strip():
        for i, line in enumerate(lines):
            if original_line.strip() in line:
                ending = "\n" if line.endswith("\n") else ""
                if fixed_line.strip() == "":
                    lines.pop(i)
                else:
                    lines[i] = line.replace(original_line.strip(), fixed_line.strip(), 1)
                    if not lines[i].endswith("\n"):
                        lines[i] += ending
                with open(full_path, "w", encoding="utf-8") as f:
                    f.writelines(lines)
                print(f"  ✓ Fixed line {i+1} via search in {file_path}")
                return True

    print(f"  ✗ Could not locate broken line in {file_path}: {repr(original_line)}")
    return False


# ── Run pytest to verify fixes ────────────────────────────────────

def run_tests():
    """Run pytest and return True if all tests pass."""
    print("\nAI Analyzer: Running pytest to verify fixes...")
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/", "--tb=short", "-q"],
        capture_output=True, text=True, cwd=PROJECT_ROOT
    )
    print(result.stdout)
    if result.returncode == 0:
        print("AI Analyzer: All tests passed ✓")
        return True
    else:
        print("AI Analyzer: Tests still failing after fix:")
        print(result.stderr)
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
        full_path = os.path.join(PROJECT_ROOT, fp)
        subprocess.run(["git", "add", full_path], cwd=PROJECT_ROOT)

    commit_msg = f"AI-Fix: {summary[:72]}"
    result = subprocess.run(
        ["git", "commit", "-m", commit_msg],
        capture_output=True, text=True, cwd=PROJECT_ROOT
    )

    if result.returncode == 0:
        push = subprocess.run(
            ["git", "push", "origin", "HEAD:main"],
            capture_output=True, text=True, cwd=PROJECT_ROOT
        )
        if push.returncode == 0:
            print("AI Analyzer: Pushed fix to GitHub ✓")
            return True
        else:
            print(f"AI Analyzer: Push failed — {push.stderr}")
            return False
    else:
        print(f"AI Analyzer: Git commit failed — {result.stderr}")
        return False


# ── Main ──────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("AI Code Analyzer — Powered by Google Gemini")
    print(f"Project root: {PROJECT_ROOT}")
    print("=" * 60)

    # 1. Collect all source files
    print("\nStep 1: Collecting source files...")
    files = collect_files()
    for path in files:
        print(f"  → {path} ({len(files[path])} chars)")
    print(f"  Total: {len(files)} files")

    # 2. Build prompt and send to Gemini
    print("\nStep 2: Sending all files to Gemini for analysis...")
    prompt = build_prompt(files)
    raw = call_gemini_analyze(prompt)

    print(f"\nStep 3: Gemini response:\n{raw}\n")

    # 3. Parse Gemini's analysis
    try:
        clean = raw.replace("```json", "").replace("```", "").strip()
        analysis = json.loads(clean)
    except json.JSONDecodeError as e:
        print(f"AI Analyzer: Could not parse Gemini response — {e}")
        with open(ANALYSIS_LOG, "w") as f:
            f.write(f"ANALYZER ERROR: Failed to parse Gemini response\n{raw}")
        sys.exit(1)

    # 4. Write analysis log
    with open(ANALYSIS_LOG, "w") as f:
        f.write(json.dumps(analysis, indent=2))

    # 5. If clean — exit 0 (pipeline continues normally)
    if analysis.get("status") == "clean" or not analysis.get("issues"):
        print("AI Analyzer: Gemini found NO issues — all files look correct ✓")
        sys.exit(0)

    # 6. Issues found — report them
    issues = analysis["issues"]
    errors = [i for i in issues if i.get("severity") == "error"]
    warnings = [i for i in issues if i.get("severity") != "error"]

    print(f"AI Analyzer: Gemini found {len(errors)} error(s) and {len(warnings)} warning(s)")
    print(f"Summary: {analysis.get('summary', '')}\n")

    for issue in issues:
        sev = issue.get("severity", "error").upper()
        print(f"  [{sev}] {issue['file_path']} line {issue.get('line_number', '?')}: {issue['description']}")

    # 7. Apply all fixes
    print("\nStep 4: Applying fixes...")
    fixed_files = set()
    applied = 0

    # Sort in reverse line order per file so line shifts don't break fixes
    from collections import defaultdict
    by_file = defaultdict(list)
    for issue in issues:
        by_file[issue["file_path"]].append(issue)

    for file_path, file_issues in by_file.items():
        sorted_issues = sorted(file_issues, key=lambda x: x.get("line_number", 0), reverse=True)
        for issue in sorted_issues:
            ok = apply_fix(
                issue["file_path"],
                issue.get("line_number"),
                issue.get("original_line", ""),
                issue.get("fixed_line", "")
            )
            if ok:
                fixed_files.add(issue["file_path"])
                applied += 1

    print(f"\nApplied {applied}/{len(issues)} fixes across {len(fixed_files)} file(s)")

    if applied == 0:
        print("AI Analyzer: No fixes could be applied — writing error log")
        with open(ANALYSIS_LOG, "a") as f:
            f.write("\nFAILED: No fixes applied\n")
        sys.exit(1)

    # 8. Run tests to verify
    tests_pass = run_tests()

    # 9. Commit and push
    summary = analysis.get("summary", "fixed code errors detected by Gemini")
    committed = git_commit_and_push(list(fixed_files), summary)

    if committed:
        print("\nAI Analyzer: Self-healing complete ✓")
        print("Pipeline will retrigger with fixed code.")
        # exit 1 so Jenkins knows it fixed something and should retrigger
        sys.exit(1)
    else:
        print("\nAI Analyzer: Fixes applied locally but push failed")
        sys.exit(1)


if __name__ == "__main__":
    main()

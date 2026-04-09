"""
AI Code Analyzer — powered by Google Gemini

Gemini reads every source file, finds syntax errors, and fixes them.
Supports three fix actions:
  replace      — overwrite an existing broken line
  insert_before — insert a new line before an anchor line
  insert_after  — insert a new line after an anchor line
"""

import os
import sys
import json
import subprocess
import time
from collections import defaultdict

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ANALYSIS_LOG = os.path.join(PROJECT_ROOT, "analysis_output.txt")

SKIP_DIRS  = {"venv", "__pycache__", ".git", ".pytest_cache", "node_modules"}
SKIP_FILES = {"analysis_output.txt", "validation_output.txt",
              "test_output.txt", "lint_output.txt", "trivy-report.json"}
ANALYZE_EXTS = {".py", ".html", ".htm", ".js", ".css", ".json"}
MAX_FILE_CHARS = 60000


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
            rel_path  = os.path.relpath(full_path, PROJECT_ROOT)
            try:
                with open(full_path, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
                if len(content) > MAX_FILE_CHARS:
                    half = MAX_FILE_CHARS // 2
                    content = (content[:half]
                               + "\n... [file truncated — middle omitted] ...\n"
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

    prompt = f"""You are a CI/CD self-healing agent. Analyze every file below and find
ALL syntax errors that would cause the code to fail, crash, or render incorrectly.

Project files:
{file_sections}

════════════════════════════════════════
WHAT TO FIND — errors in ANY language:

Python  : missing colon (def/if/for/class), wrong indentation, unclosed bracket,
          undefined name used as function, invalid syntax
HTML    : missing required tags (<html>, <head>, <body>, <style>, <script>),
          tag written as <lang="en"> instead of <html lang="en">,
          unclosed tags, malformed tag names
CSS     : unclosed braces {{ }}, missing semicolons on property values
JavaScript: missing semicolons, unclosed brackets/braces, undefined variables
JSON    : trailing commas, unquoted keys, mismatched brackets

WHAT NOT TO REPORT:
  - Code style, naming, or formatting preferences
  - Logic improvements or refactoring
  - Warnings that don't break execution

════════════════════════════════════════
THREE FIX ACTIONS — use the right one:

1. "replace"       — a line EXISTS but is broken; overwrite it with the fix
   Example: <lang="en">  →  replace with  <html lang="en">

2. "insert_before" — a required line is COMPLETELY MISSING; insert the new line
                     BEFORE the anchor_line you specify
   Example: <style> tag is missing before `:root {{`

3. "insert_after"  — a required line is COMPLETELY MISSING; insert the new line
                     AFTER the anchor_line you specify
   Example: <head> tag is missing after `<html lang="en">`

RULES FOR ALL ACTIONS:
  • anchor_line / original_line must be copied EXACTLY from the file (character for character)
  • fixed_line must be a SINGLE line — never put \\n inside it
  • fixed_line must not be empty
  • For "replace": original_line and fixed_line must differ

════════════════════════════════════════
Return ONLY raw JSON — no markdown, no code fences.

If no errors found:
{{"status": "clean", "message": "No syntax errors found", "issues": []}}

If errors found:
{{
  "status": "issues_found",
  "summary": "one sentence describing all errors found",
  "issues": [
    {{
      "file_path": "relative/path/to/file",
      "language": "python|html|css|javascript|json",
      "line_number": 42,
      "action": "replace|insert_before|insert_after",
      "original_line": "exact line from file (anchor for insert, broken line for replace)",
      "fixed_line": "the corrected or new single line",
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

    # Ordered by capability; includes multiple fallbacks across model families
    models = [
        "gemini-2.5-flash",
        "gemini-2.0-flash",
        "gemini-2.0-flash-lite",
        "gemini-1.5-flash",
        "gemini-1.5-flash-8b",
    ]

    for model_name in models:
        for attempt in range(3):
            try:
                print(f"  Trying {model_name} (attempt {attempt + 1})...")
                response = client.models.generate_content(
                    model=model_name, contents=prompt)
                print(f"  ✓ Got response from {model_name}")
                return response.text.strip()

            except genai_errors.ClientError as e:
                err = str(e)
                if "429" in err or "RESOURCE_EXHAUSTED" in err:
                    # Rate-limit: wait longer — free tier resets per minute
                    wait = 60 if attempt == 0 else 90
                    print(f"  {model_name} rate-limited — waiting {wait}s then trying next model...")
                    time.sleep(wait)
                    break  # move to next model after wait
                else:
                    print(f"  {model_name} client error: {e} — skipping")
                    break

            except genai_errors.ServerError as e:
                # 503 server overload — retry same model with backoff
                wait = 20 * (attempt + 1)
                print(f"  {model_name} server error (attempt {attempt+1}/3): {e}")
                if attempt < 2:
                    print(f"  Retrying in {wait}s...")
                    time.sleep(wait)
                else:
                    print(f"  {model_name} unavailable after 3 attempts — trying next model...")

            except Exception as e:
                print(f"  {model_name} unexpected error: {e} — skipping")
                break

    # ── All Gemini models failed — try Ollama as local fallback ──
    print("\n  All Gemini models unavailable — trying Ollama local fallback...")
    return call_ollama_analyze(prompt)


# ── Ollama local fallback ─────────────────────────────────────────

def call_ollama_analyze(prompt):
    """
    Fallback: call a locally running Ollama model when all Gemini models fail.
    Ollama must be running: `ollama serve`
    Preferred models (install with `ollama pull <model>`):
      ollama pull codellama        (best for code analysis)
      ollama pull deepseek-coder   (great alternative)
      ollama pull llama3           (general purpose fallback)
    """
    import urllib.request
    import urllib.error

    OLLAMA_URL = "http://localhost:11434/api/generate"

    # Try these models in order — use whichever is installed
    models = ["codellama", "deepseek-coder", "llama3", "mistral", "llama2"]

    for model_name in models:
        try:
            print(f"  Trying Ollama model: {model_name}...")
            payload = json.dumps({
                "model": model_name,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.1,   # low temp = more deterministic JSON
                    "num_predict": 4096,  # enough tokens for the full response
                }
            }).encode("utf-8")

            req = urllib.request.Request(
                OLLAMA_URL,
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            req.add_header("Connection", "keep-alive")

            with urllib.request.urlopen(req, timeout=120) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                text = result.get("response", "").strip()
                if text:
                    print(f"  ✓ Got response from Ollama ({model_name})")
                    return text
                else:
                    print(f"  {model_name} returned empty response — trying next...")

        except urllib.error.URLError as e:
            if "Connection refused" in str(e) or "Connection reset" in str(e):
                print("  Ollama is not running on this machine.")
                print("  To enable: install Ollama from https://ollama.com then run: ollama serve")
                return None
            print(f"  Ollama {model_name} error: {e} — trying next model...")

        except Exception as e:
            print(f"  Ollama {model_name} unexpected error: {e} — trying next model...")

    print("  No Ollama models available. Install one with: ollama pull codellama")
    return None


# ── Validate a fix before applying ───────────────────────────────

def is_safe_fix(issue):
    action      = issue.get("action", "replace")
    orig        = issue.get("original_line", "")
    fixed       = issue.get("fixed_line", "")
    loc         = f"{issue.get('file_path')} line {issue.get('line_number')}"

    # anchor/original must not be empty — we need it to locate the insertion point
    if not orig.strip():
        print(f"  ⚠ Skipping — empty original_line/anchor for {loc}")
        return False

    # fixed_line must have content — never delete or insert a blank line
    if not fixed.strip():
        print(f"  ⚠ Skipping — empty fixed_line for {loc}")
        return False

    # no real newlines ever
    for val, label in [(orig, "original_line"), (fixed, "fixed_line")]:
        if "\n" in val or "\\n" in val:
            print(f"  ⚠ Skipping — {label} contains newline for {loc}")
            return False

    # for replace: the two lines must actually differ
    if action == "replace" and orig == fixed:
        print(f"  ⚠ Skipping no-op replace (original == fixed) for {loc}")
        return False

    if action not in ("replace", "insert_before", "insert_after"):
        print(f"  ⚠ Unknown action '{action}' for {loc}")
        return False

    return True


# ── Apply a single fix ────────────────────────────────────────────

def apply_fix(issue):
    file_path   = issue["file_path"]
    action      = issue.get("action", "replace")
    line_number = issue.get("line_number")
    original    = issue.get("original_line", "")
    fixed       = issue.get("fixed_line", "")

    full_path = os.path.join(PROJECT_ROOT, file_path)
    if not os.path.exists(full_path):
        print(f"  ✗ File not found: {full_path}")
        return False

    with open(full_path, "r", encoding="utf-8", errors="replace") as f:
        lines = f.readlines()

    # ── REPLACE ──────────────────────────────────────────────────
    if action == "replace":
        # Strategy 1: use line number hint
        if line_number and 1 <= line_number <= len(lines):
            actual = lines[line_number - 1].rstrip("\n").rstrip("\r")
            if original.strip() and (original.strip() in actual
                                     or actual.strip() in original.strip()):
                ending = "\n" if lines[line_number - 1].endswith("\n") else ""
                lines[line_number - 1] = fixed + ending
                _write(full_path, lines)
                print(f"  ✓ [replace] line {line_number} in {file_path}")
                return True

        # Strategy 2: search whole file
        for i, line in enumerate(lines):
            if original.strip() in line:
                ending  = "\n" if line.endswith("\n") else ""
                new_line = line.replace(line.rstrip("\n\r"), fixed, 1)
                if not new_line.endswith("\n"):
                    new_line += ending
                lines[i] = new_line
                _write(full_path, lines)
                print(f"  ✓ [replace] found at line {i+1} in {file_path}")
                return True

        print(f"  ✗ [replace] could not find: {repr(original)} in {file_path}")
        return False

    # ── INSERT_BEFORE / INSERT_AFTER ─────────────────────────────
    if action in ("insert_before", "insert_after"):
        anchor = original.strip()
        target_idx = None

        # prefer line number hint first
        if line_number and 1 <= line_number <= len(lines):
            actual = lines[line_number - 1].rstrip("\n\r")
            if anchor in actual or actual.strip() in anchor:
                target_idx = line_number - 1

        # fallback: search whole file
        if target_idx is None:
            for i, line in enumerate(lines):
                if anchor in line:
                    target_idx = i
                    break

        if target_idx is None:
            print(f"  ✗ [{action}] anchor not found: {repr(original)} in {file_path}")
            return False

        # detect indentation from anchor line for consistency
        anchor_line = lines[target_idx]
        indent = len(anchor_line) - len(anchor_line.lstrip())
        new_line = " " * indent + fixed.strip() + "\n"

        insert_idx = target_idx if action == "insert_before" else target_idx + 1
        lines.insert(insert_idx, new_line)
        _write(full_path, lines)
        verb = "before" if action == "insert_before" else "after"
        print(f"  ✓ [{action}] inserted '{fixed.strip()}' {verb} line {target_idx+1} in {file_path}")
        return True

    return False


def _write(path, lines):
    with open(path, "w", encoding="utf-8") as f:
        f.writelines(lines)


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
        authed = repo_url.replace("https://", f"https://{github_token}@")
        subprocess.run(["git", "remote", "set-url", "origin", authed],
                       cwd=PROJECT_ROOT)

    subprocess.run(["git", "config", "user.email", "ai-bot@pipeline.local"],
                   cwd=PROJECT_ROOT)
    subprocess.run(["git", "config", "user.name",  "AI-Remediation-Bot"],
                   cwd=PROJECT_ROOT)

    for fp in fixed_files:
        subprocess.run(["git", "add", os.path.join(PROJECT_ROOT, fp)],
                       cwd=PROJECT_ROOT)

    result = subprocess.run(
        ["git", "commit", "-m", f"AI-Fix: {summary[:72]}"],
        capture_output=True, text=True, cwd=PROJECT_ROOT
    )
    if result.returncode != 0:
        print(f"AI Analyzer: git commit failed — {result.stderr}")
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

    # Step 2: build prompt and call Gemini
    print("\nStep 2: Sending all files to Gemini for analysis...")
    prompt = build_prompt(files)
    raw    = call_gemini_analyze(prompt)

    if raw is None:
        print("\nAI Analyzer: All Gemini models unavailable — skipping analysis.")
        print("Lint and Test stages will catch any errors ✓")
        sys.exit(0)

    print(f"\nStep 3: Gemini response:\n{raw}\n")

    # Step 3: parse JSON
    try:
        clean    = raw.replace("```json", "").replace("```", "").strip()
        analysis = json.loads(clean)
    except json.JSONDecodeError as e:
        print(f"AI Analyzer: Could not parse Gemini response — {e}")
        print("Skipping — Lint and Test stages will catch any errors ✓")
        sys.exit(0)

    with open(ANALYSIS_LOG, "w") as f:
        f.write(json.dumps(analysis, indent=2))

    if analysis.get("status") == "clean" or not analysis.get("issues"):
        print("AI Analyzer: No syntax errors found — all files are clean ✓")
        sys.exit(0)

    # Step 4: report and filter issues
    issues = [i for i in analysis.get("issues", [])
              if i.get("severity") == "error"]
    print(f"AI Analyzer: Gemini found {len(issues)} error(s)")
    print(f"Summary: {analysis.get('summary', '')}\n")
    for issue in issues:
        action = issue.get("action", "replace")
        print(f"  [{issue.get('severity','?').upper()}] {issue['file_path']} "
              f"line {issue.get('line_number','?')} [{action}]: {issue['description']}")

    # Step 5: apply fixes — process each file in reverse line order
    print("\nStep 4: Applying fixes...")
    fixed_files = set()
    applied = 0

    by_file = defaultdict(list)
    for issue in issues:
        if is_safe_fix(issue):
            by_file[issue["file_path"]].append(issue)

    for file_path, file_issues in by_file.items():
        # reverse order: insertions/replacements at higher line numbers first
        # so that earlier line numbers are not shifted
        for issue in sorted(file_issues,
                            key=lambda x: x.get("line_number", 0),
                            reverse=True):
            if apply_fix(issue):
                fixed_files.add(file_path)
                applied += 1

    print(f"\nApplied {applied} fix(es) across {len(fixed_files)} file(s)")

    if applied == 0:
        print("AI Analyzer: No valid fixes could be applied.")
        print("Lint and Test stages will catch real errors ✓")
        sys.exit(0)

    # Step 6: verify Python files compile cleanly
    print("\nStep 5: Verifying Python syntax on modified files...")
    syntax_ok = True
    for fp in fixed_files:
        if not fp.endswith(".py"):
            continue
        full_path = os.path.join(PROJECT_ROOT, fp)
        r = subprocess.run([sys.executable, "-m", "py_compile", full_path],
                           capture_output=True, text=True)
        if r.returncode != 0:
            print(f"  ✗ {fp}: syntax error after fix — {r.stderr.strip()}")
            syntax_ok = False
        else:
            print(f"  ✓ {fp}: syntax OK")

    if not syntax_ok:
        print("\nAI Analyzer: A fix introduced a syntax error — NOT pushing.")
        sys.exit(2)

    # Step 7: run tests
    if not run_tests():
        print("\nAI Analyzer: Tests still failing — NOT pushing to GitHub.")
        sys.exit(2)

    # Step 8: commit and push
    summary   = analysis.get("summary", "fixed syntax errors detected by Gemini")
    committed = git_commit_and_push(list(fixed_files), summary)

    if committed:
        print("\nAI Analyzer: Self-healing complete ✓")
        sys.exit(1)
    else:
        print("\nAI Analyzer: Push failed")
        sys.exit(2)


if __name__ == "__main__":
    main()

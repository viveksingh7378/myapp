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

# Max chars sent to AI per chunk — keep below Gemini's context limit
MAX_CHUNK_CHARS = 80000
# If a file exceeds this, split it into overlapping chunks so no line is missed
CHUNK_OVERLAP   = 2000   # overlap between chunks to catch errors at split boundaries


# ── Collect source files (with chunking for large files) ─────────

def split_into_chunks(content, rel_path):
    """
    Split a large file into overlapping line-based chunks so no line is skipped.
    Each chunk keeps a small overlap with the previous to catch errors at boundaries.
    Returns list of (chunk_label, chunk_content) tuples.
    """
    lines = content.splitlines(keepends=True)
    chunks = []
    start_line = 0
    chunk_idx  = 1

    while start_line < len(lines):
        chunk_lines = []
        char_count  = 0
        end_line    = start_line

        while end_line < len(lines) and char_count < MAX_CHUNK_CHARS:
            chunk_lines.append(lines[end_line])
            char_count += len(lines[end_line])
            end_line   += 1

        label   = f"{rel_path} [chunk {chunk_idx}, lines {start_line+1}–{end_line}]"
        chunks.append((label, rel_path, start_line + 1, "".join(chunk_lines)))

        # Move forward, but keep CHUNK_OVERLAP chars of overlap
        overlap_chars = 0
        overlap_line  = end_line
        while overlap_line > start_line and overlap_chars < CHUNK_OVERLAP:
            overlap_line  -= 1
            overlap_chars += len(lines[overlap_line])

        start_line = max(end_line - max(1, end_line - overlap_line), end_line)
        # If we didn't advance, force forward to avoid infinite loop
        if start_line <= (chunk_idx - 1) * (end_line - start_line):
            start_line = end_line
        chunk_idx += 1

    return chunks


def collect_files():
    """
    Collect all source files. Large files are split into chunks so the AI
    sees every line — no more silent truncation in the middle of a file.
    Returns dict: label → {"rel_path": ..., "line_start": ..., "content": ...}
    """
    file_map = {}

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

                if len(content) <= MAX_CHUNK_CHARS:
                    # Small file — send as-is
                    file_map[rel_path] = {
                        "rel_path":   rel_path,
                        "line_start": 1,
                        "content":    content,
                    }
                else:
                    # Large file — split into chunks (NO truncation)
                    chunks = split_into_chunks(content, rel_path)
                    print(f"  ⚡ Large file split into {len(chunks)} chunk(s): {rel_path}")
                    for label, rp, line_start, chunk_content in chunks:
                        file_map[label] = {
                            "rel_path":   rp,
                            "line_start": line_start,
                            "content":    chunk_content,
                        }

            except Exception as e:
                print(f"  Warning: could not read {rel_path} — {e}")

    return file_map


# ── Build Gemini prompt ───────────────────────────────────────────

def build_prompt(files_dict):
    file_sections = ""
    for label, meta in files_dict.items():
        content    = meta["content"]
        line_start = meta["line_start"]
        # Number each line with its TRUE line number in the original file
        numbered = "\n".join(
            f"{line_start + i:4d} | {line}"
            for i, line in enumerate(content.splitlines())
        )
        file_sections += f"\n{'='*60}\nFILE: {label}\n{'='*60}\n{numbered}\n"

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
        "gemini-2.5-pro",
        "gemini-2.0-flash",
        "gemini-2.0-flash-lite",
        "gemini-2.0-flash-exp",
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
    """Apply a fix and return the actual line number found, or False on failure."""
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
                print_fix_diff(issue, line_number)
                return line_number

        # Strategy 2: search whole file
        for i, line in enumerate(lines):
            if original.strip() in line:
                ending  = "\n" if line.endswith("\n") else ""
                new_line = line.replace(line.rstrip("\n\r"), fixed, 1)
                if not new_line.endswith("\n"):
                    new_line += ending
                lines[i] = new_line
                _write(full_path, lines)
                print_fix_diff(issue, i + 1)
                return i + 1

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
        print_fix_diff(issue, target_idx + 1)
        return target_idx + 1

    return False


def _write(path, lines):
    with open(path, "w", encoding="utf-8") as f:
        f.writelines(lines)


# ── Pretty-print a single fix diff ───────────────────────────────

def print_fix_diff(issue, line_found):
    """Print a Jenkins-friendly before/after box for one fix."""
    file_path   = issue.get("file_path", "?")
    action      = issue.get("action", "replace")
    description = issue.get("description", "")
    original    = issue.get("original_line", "").strip()
    fixed       = issue.get("fixed_line", "").strip()
    lang        = issue.get("language", "").upper()

    W = 70  # box width
    sep = "─" * W

    action_label = {
        "replace":       "REPLACE  (broken line → fixed line)",
        "insert_before": "INSERT BEFORE anchor line",
        "insert_after":  "INSERT AFTER  anchor line",
    }.get(action, action.upper())

    print(f"\n┌{sep}┐")
    print(f"│  🔧 AI FIX APPLIED  [{lang}]" + " " * (W - 22 - len(lang)) + "│")
    print(f"├{sep}┤")
    print(f"│  File   : {file_path[:W-12]:<{W-12}}│")
    print(f"│  Line   : {str(line_found):<{W-12}}│")
    print(f"│  Action : {action_label:<{W-12}}│")
    desc_short = description[:W-12] if description else "-"
    print(f"│  Issue  : {desc_short:<{W-12}}│")
    print(f"├{sep}┤")

    if action == "replace":
        before_label = "  ✗ ERROR  "
        after_label  = "  ✓ FIXED  "
    else:
        before_label = "  ⚓ ANCHOR "
        after_label  = "  ✚ ADDED  "

    # Truncate long lines so they fit in the box
    max_code = W - 14
    orig_display  = original[:max_code] + ("…" if len(original)  > max_code else "")
    fixed_display = fixed[:max_code]    + ("…" if len(fixed)     > max_code else "")

    print(f"│{before_label}: {orig_display:<{max_code+2}}│")
    print(f"│           {'↓':<{W-11}}│")
    print(f"│{after_label}: {fixed_display:<{max_code+2}}│")
    print(f"└{sep}┘")


# ── Print full summary table of all applied fixes ─────────────────

def print_fix_summary(applied_fixes):
    """Print a compact table of all fixes applied this run."""
    if not applied_fixes:
        return

    print("\n")
    W = 72
    print("═" * W)
    title = f"  AI AUTO-FIX SUMMARY — {len(applied_fixes)} CHANGE(S) APPLIED  "
    print(title.center(W))
    print("═" * W)

    for idx, fix in enumerate(applied_fixes, 1):
        file_path   = fix.get("file_path", "?")
        line_found  = fix.get("line_found", "?")
        action      = fix.get("action", "replace")
        original    = fix.get("original_line", "").strip()
        fixed_line  = fix.get("fixed_line", "").strip()
        description = fix.get("description", "")

        print(f"\n  #{idx}  {file_path}  (line {line_found})  [{action}]")
        print(f"       Issue : {description[:60]}")
        max_w = 60
        orig_d  = original[:max_w]  + ("…" if len(original)  > max_w else "")
        fixed_d = fixed_line[:max_w] + ("…" if len(fixed_line) > max_w else "")

        if action == "replace":
            print(f"       BEFORE: {orig_d}")
            print(f"       AFTER : {fixed_d}")
        else:
            verb = "BEFORE" if action == "insert_before" else "AFTER"
            print(f"       ANCHOR ({verb}): {orig_d}")
            print(f"       INSERTED      : {fixed_d}")

        print(f"       {'─'*65}")

    print("═" * W)
    print()


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

def local_syntax_check():
    """
    Run fast local syntax checkers BEFORE calling the AI.
    Catches Python/JS/CSS/HTML errors instantly without spending API quota.
    Returns list of dicts: [{file, line, error}]
    """
    import re as _re
    findings = []
    print("\nPre-flight: Local syntax checks...")

    for dirpath, dirnames, filenames in os.walk(PROJECT_ROOT):
        dirnames[:] = [d for d in dirnames
                       if d not in SKIP_DIRS and not d.startswith(".")]
        for filename in filenames:
            ext = os.path.splitext(filename)[1].lower()
            full_path = os.path.join(dirpath, filename)
            rel_path  = os.path.relpath(full_path, PROJECT_ROOT)

            # ── Python: use py_compile ──────────────────────────
            if ext == ".py":
                r = subprocess.run(
                    [sys.executable, "-m", "py_compile", full_path],
                    capture_output=True, text=True
                )
                if r.returncode != 0:
                    findings.append({"file": rel_path, "tool": "py_compile",
                                     "error": r.stderr.strip()})
                    print(f"  ✗ Python syntax error: {rel_path}")
                    print(f"    {r.stderr.strip()}")

            # ── JavaScript: use node --check ────────────────────
            elif ext in (".js",):
                r = subprocess.run(
                    ["node", "--check", full_path],
                    capture_output=True, text=True
                )
                if r.returncode != 0:
                    findings.append({"file": rel_path, "tool": "node",
                                     "error": r.stderr.strip()})
                    print(f"  ✗ JS syntax error: {rel_path}")
                    print(f"    {r.stderr.strip()}")

            # ── HTML: check CSS brace balance + extract/check JS ─
            elif ext in (".html", ".htm"):
                try:
                    with open(full_path, "r", encoding="utf-8", errors="replace") as f:
                        html_content = f.read()

                    # CSS brace balance check
                    css_blocks = _re.findall(r'<style[^>]*>(.*?)</style>',
                                             html_content, _re.DOTALL)
                    css_text = "".join(css_blocks)
                    opens  = css_text.count("{")
                    closes = css_text.count("}")
                    if opens != closes:
                        msg = (f"CSS brace mismatch: {opens} open vs {closes} close"
                               f" (delta: {opens - closes:+d})")
                        findings.append({"file": rel_path, "tool": "css-brace",
                                         "error": msg})
                        print(f"  ✗ {rel_path}: {msg}")

                        # Pin down the line
                        lines = html_content.splitlines()
                        depth = 0
                        in_style = False
                        for ln_num, ln in enumerate(lines, 1):
                            if "<style" in ln:  in_style = True
                            if "</style>" in ln: in_style = False
                            if in_style:
                                for ch in ln:
                                    if ch == "{": depth += 1
                                    elif ch == "}": depth -= 1
                                if depth < 0:
                                    print(f"    First negative depth at line {ln_num}: {ln.strip()}")
                                    break

                    # Inline JS check
                    js_blocks = _re.findall(r'<script[^>]*>(.*?)</script>',
                                            html_content, _re.DOTALL)
                    if js_blocks:
                        js_tmp = "/tmp/_inline_js_check.js"
                        with open(js_tmp, "w") as jf:
                            jf.write("\n".join(js_blocks))
                        r = subprocess.run(
                            ["node", "--check", js_tmp],
                            capture_output=True, text=True
                        )
                        if r.returncode != 0:
                            findings.append({"file": rel_path, "tool": "node-inline-js",
                                             "error": r.stderr.strip()})
                            print(f"  ✗ Inline JS error in {rel_path}")
                            print(f"    {r.stderr.strip()}")

                except Exception as e:
                    print(f"  Warning: could not check {rel_path} — {e}")

    if not findings:
        print("  ✓ All files passed local syntax checks")
    else:
        print(f"\n  Found {len(findings)} local syntax issue(s) — AI will also scan for fixes")
    return findings


def main():
    print("=" * 60)
    print("AI Code Analyzer — Powered by Google Gemini")
    print(f"Project root: {PROJECT_ROOT}")
    print("=" * 60)

    # Step 0: fast local syntax checks (before calling AI)
    local_findings = local_syntax_check()

    # Step 1: collect files
    print("\nStep 1: Collecting source files...")
    files = collect_files()
    seen_files = set()
    for label, meta in files.items():
        rp = meta["rel_path"]
        if rp not in seen_files:
            print(f"  → {rp} ({len(meta['content'])} chars in this chunk)")
            seen_files.add(rp)
    print(f"  Total: {len(seen_files)} file(s), {len(files)} chunk(s) sent to AI")

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
    fixed_files  = set()
    applied      = 0
    applied_fixes = []   # track details for summary

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
            result = apply_fix(issue)
            if result is not False:
                fixed_files.add(file_path)
                applied += 1
                # Record for the summary table
                applied_fixes.append({**issue, "line_found": result})

    # Print the full summary diff table after all fixes
    print_fix_summary(applied_fixes)
    print(f"Applied {applied} fix(es) across {len(fixed_files)} file(s)")

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

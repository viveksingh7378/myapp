import os
import sys
import json
import subprocess
from log_parser import extract_error_context, extract_broken_files

MAX_RETRIES = 2
RETRY_FILE = ".ai_retry_count"

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ── Retry helpers ─────────────────────────────────────────────────

def get_retry_count():
    if os.path.exists(RETRY_FILE):
        return int(open(RETRY_FILE).read().strip())
    return 0


def increment_retry():
    count = get_retry_count() + 1
    open(RETRY_FILE, 'w').write(str(count))
    return count


def reset_retry():
    if os.path.exists(RETRY_FILE):
        os.remove(RETRY_FILE)


# ── Read actual broken file ───────────────────────────────────────

def read_broken_file(file_path):
    """
    Read the real content of the broken file so Gemini
    can see exactly what's there — no more guessing.
    """
    full_path = os.path.join(PROJECT_ROOT, file_path)
    if not os.path.exists(full_path):
        return None
    with open(full_path, 'r', encoding='utf-8', errors='replace') as f:
        return f.read()


# ── Call Gemini with full file context ───────────────────────────

def call_gemini(error_context, file_path=None, file_content=None):
    import time
    from google import genai
    from google.genai import errors as genai_errors

    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

    # Build the file context block if we have the real file
    file_block = ""
    if file_path and file_content:
        # number every line so Gemini can reference exact line numbers
        numbered = "\n".join(
            f"{i+1:4d} | {line}"
            for i, line in enumerate(file_content.splitlines())
        )
        file_block = f"""
The broken file is: {file_path}
Here is its FULL content with line numbers:

{numbered}
"""

    prompt = f"""You are an expert software engineer working on a CI/CD pipeline.
A code validation or test just failed. The error may be in ANY language:
Python, HTML, JavaScript, CSS, JSON, YAML, or others.

{file_block}

ERROR LOG:
{error_context}

Your job: find the exact broken line and return the fix as a JSON object.

Rules:
- Use the actual file content above — do NOT guess
- Return the EXACT line number (1-indexed) of the broken line
- "original_line" must be copied exactly from the file (including indentation)
- "fixed_line" must be the corrected version of ONLY that line
- If multiple lines need fixing, fix the most critical one first
- Return ONLY raw JSON — no markdown, no code fences, no explanation

JSON format:
{{
  "root_cause": "one sentence: what is wrong and in which file",
  "file_path": "relative path e.g. blog.html or app/app.py",
  "language": "python|html|javascript|css|json|yaml|other",
  "line_number": 42,
  "original_line": "the exact broken line copied from the file above",
  "fixed_line": "the corrected version of that line",
  "confidence": 0.95
}}"""

    models_to_try = ["gemini-2.0-flash", "gemini-2.5-flash", "gemini-2.0-flash-lite"]

    for model_name in models_to_try:
        try:
            print(f"AI Agent: Trying model {model_name}...")
            response = client.models.generate_content(
                model=model_name,
                contents=prompt
            )
            return response.text.strip()
        except genai_errors.ClientError as e:
            if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                print(f"AI Agent: {model_name} quota exceeded, trying next...")
                time.sleep(5)
                continue
            else:
                raise e

    raise Exception("AI Agent: All models exhausted — quota exceeded on all")


# ── Apply fix by line number (reliable) ──────────────────────────

def apply_fix(file_path, line_number, original_line, fixed_line):
    full_path = os.path.join(PROJECT_ROOT, file_path)
    print(f"AI Agent: Opening {full_path}")

    if not os.path.exists(full_path):
        print(f"AI Agent: File not found — {full_path}")
        return False

    with open(full_path, 'r', encoding='utf-8', errors='replace') as f:
        lines = f.readlines()

    total_lines = len(lines)

    # ── Strategy 1: replace by exact line number ──────────────────
    if line_number and 1 <= line_number <= total_lines:
        actual = lines[line_number - 1].rstrip('\n')
        # confirm the line roughly matches what Gemini said
        if original_line.strip() in actual or actual.strip() in original_line.strip():
            # preserve original line ending
            ending = '\n' if lines[line_number - 1].endswith('\n') else ''
            lines[line_number - 1] = fixed_line + ending
            print(f"AI Agent: Fixed line {line_number} in {file_path}")
            with open(full_path, 'w', encoding='utf-8') as f:
                f.writelines(lines)
            return True
        else:
            print(f"AI Agent: Line {line_number} content mismatch — trying search fallback")
            print(f"  Expected: {repr(original_line.strip())}")
            print(f"  Got:      {repr(actual.strip())}")

    # ── Strategy 2: search every line for the broken content ──────
    print("AI Agent: Searching all lines for the broken content...")
    for i, line in enumerate(lines):
        if original_line.strip() and original_line.strip() in line:
            ending = '\n' if line.endswith('\n') else ''
            lines[i] = line.replace(original_line.strip(), fixed_line.strip(), 1) + (
                '' if line.endswith('\n') else ''
            )
            # make sure we keep the newline
            if not lines[i].endswith('\n'):
                lines[i] += ending
            print(f"AI Agent: Fixed at line {i+1} via search in {file_path}")
            with open(full_path, 'w', encoding='utf-8') as f:
                f.writelines(lines)
            return True

    # ── Strategy 3: whole-file string replace (last resort) ───────
    print("AI Agent: Trying whole-file string replace as last resort...")
    content = "".join(lines)
    if original_line.strip() in content:
        content = content.replace(original_line.strip(), fixed_line.strip(), 1)
        with open(full_path, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"AI Agent: Fixed via whole-file replace in {file_path}")
        return True

    print(f"AI Agent: Could not locate the broken content in {file_path}")
    print(f"  Looking for: {repr(original_line)}")
    return False


# ── Git commit and push ───────────────────────────────────────────

def git_commit_fix(file_path, root_cause):
    repo_url = subprocess.run(
        ["git", "config", "--get", "remote.origin.url"],
        capture_output=True, text=True
    ).stdout.strip()

    github_token = os.environ.get("GITHUB_TOKEN", "")

    if github_token and "github.com" in repo_url:
        authed_url = repo_url.replace("https://", f"https://{github_token}@")
        subprocess.run(["git", "remote", "set-url", "origin", authed_url])

    subprocess.run(["git", "config", "user.email", "ai-bot@pipeline.local"])
    subprocess.run(["git", "config", "user.name", "AI-Remediation-Bot"])

    full_path = os.path.join(PROJECT_ROOT, file_path)
    subprocess.run(["git", "add", full_path])

    result = subprocess.run(
        ["git", "commit", "-m", f"AI-Fix: {root_cause[:72]}"],
        capture_output=True, text=True
    )

    if result.returncode == 0:
        push = subprocess.run(
            ["git", "push", "origin", "HEAD:main"],
            capture_output=True, text=True
        )
        if push.returncode == 0:
            print("AI Agent: Fix committed and pushed to GitHub ✓")
            return True
        else:
            print(f"AI Agent: Push failed — {push.stderr}")
            return False
    else:
        print(f"AI Agent: Git commit failed — {result.stderr}")
        return False


# ── Main remediation flow ─────────────────────────────────────────

def remediate(log_file_path):
    retries = get_retry_count()
    if retries >= MAX_RETRIES:
        print(f"AI Agent: Max retries ({MAX_RETRIES}) reached. Human intervention needed.")
        reset_retry()
        sys.exit(1)

    print(f"AI Agent: Attempt {retries + 1} of {MAX_RETRIES}")

    # 1. Extract error context from the log
    error_context = extract_error_context(log_file_path)
    print(f"AI Agent: Extracted error context ({len(error_context)} chars)")

    # 2. Find which file(s) are broken
    broken_files = extract_broken_files(log_file_path)
    print(f"AI Agent: Broken files detected: {broken_files}")

    # 3. Read the actual content of the first broken file
    file_path = broken_files[0] if broken_files else None
    file_content = None
    if file_path:
        file_content = read_broken_file(file_path)
        if file_content:
            print(f"AI Agent: Read {len(file_content)} chars from {file_path}")
        else:
            print(f"AI Agent: Warning — could not read {file_path}, Gemini will work from error log only")

    # 4. Call Gemini with error + real file content
    print("AI Agent: Sending to Gemini for analysis...")
    raw_response = call_gemini(error_context, file_path, file_content)
    print(f"AI Agent: Raw response:\n{raw_response}")

    # 5. Parse JSON
    try:
        clean = raw_response.replace("```json", "").replace("```", "").strip()
        fix = json.loads(clean)
    except json.JSONDecodeError as e:
        print(f"AI Agent: Failed to parse Gemini response as JSON — {e}")
        increment_retry()
        sys.exit(1)

    print(f"AI Agent: Root cause  — {fix['root_cause']}")
    print(f"AI Agent: File        — {fix['file_path']}")
    print(f"AI Agent: Line        — {fix.get('line_number', 'N/A')}")
    print(f"AI Agent: Confidence  — {fix['confidence']}")

    # 6. Skip if confidence too low
    if fix['confidence'] < 0.75:
        print("AI Agent: Confidence too low — skipping auto-fix")
        increment_retry()
        sys.exit(1)

    # 7. Apply fix using line number + fallback strategies
    success = apply_fix(
        fix['file_path'],
        fix.get('line_number'),
        fix.get('original_line', fix.get('original_code', '')),
        fix.get('fixed_line', fix.get('fixed_code', ''))
    )

    if not success:
        print("AI Agent: All fix strategies failed")
        increment_retry()
        sys.exit(1)

    # 8. Commit and push to GitHub
    committed = git_commit_fix(fix['file_path'], fix['root_cause'])
    if not committed:
        increment_retry()
        sys.exit(1)

    increment_retry()
    print("AI Agent: Self-healing complete — pipeline will retrigger ✓")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python remediate.py <log_file>")
        sys.exit(1)
    remediate(sys.argv[1])

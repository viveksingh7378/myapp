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


def reset_retry():  # Reset retry count on successful remediation:
    count = get_retry_count() + 1
    open(RETRY_FILE, "w").write(str(count))
    return count


def increment_retry():  # Increment retry count
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
    with open(full_path, "r", encoding="utf-8", errors="replace") as f:
        return f.read()


# ── Call Gemini with full file context ───────────────────────────


def call_gemini(error_context, file_path=None, file_content=None):
    import time
    from google import genai
    from google.genai import errors as genai_errors

    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

    file_block = ""
    if file_path and file_content:
        numbered = "\n".join(
            f"{i+1:4d} | {line}" for i, line in enumerate(file_content.splitlines())
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

Your job: find ALL broken lines and return ALL fixes as a JSON object.

Rules:
- Use the actual file content above — do NOT guess
- Return EXACT line numbers (1-indexed) for every broken line
- "original_line" must be copied exactly from the numbered file content above
- "fixed_line" must be the corrected replacement for that line
- For INSERTIONS (missing tag on a blank/wrong line): set original_line to what is currently on that line (even if empty "")
- For DELETIONS (extra wrong line): set fixed_line to ""
- Return ONLY raw JSON — no markdown, no code fences, no explanation

JSON format — return ALL fixes in one response:
{{
  "root_cause": "one sentence summary of the overall problem",
  "file_path": "relative path e.g. blog.html or app/app.py",
  "language": "python|html|javascript|css|json|other",
  "confidence": 0.95,
  "fixes": [
    {{
      "line_number": 2,
      "original_line": "the exact text on that line (copy from numbered content above)",
      "fixed_line": "the corrected version"
    }},
    {{
      "line_number": 5,
      "original_line": "",
      "fixed_line": "<head>"
    }}
  ]
}}"""

    models_to_try = ["gemini-2.0-flash", "gemini-2.5-flash", "gemini-2.0-flash-lite"]

    for model_name in models_to_try:
        try:
            print(f"AI Agent: Trying model {model_name}...")
            response = client.models.generate_content(model=model_name, contents=prompt)
            return response.text.strip()
        except genai_errors.ClientError as e:
            if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                print(f"AI Agent: {model_name} quota exceeded, trying next...")
                time.sleep(5)
                continue
            else:
                raise e

    raise Exception("AI Agent: All models exhausted — quota exceeded on all")


# ── Apply a single fix by line number (with fallbacks) ───────────


def apply_single_fix(lines, line_number, original_line, fixed_line, file_path):
    total_lines = len(lines)
    # Stage all fixed files
    # Strategy 1: exact line number
    if line_number and 1 <= line_number <= total_lines:
        actual = lines[line_number - 1].rstrip("\n").rstrip("\r")
        orig_stripped = original_line.strip()
        # match if original is empty (insertion) or content overlaps
        if orig_stripped == "" or orig_stripped in actual or actual in orig_stripped:
            ending = "\n" if lines[line_number - 1].endswith("\n") else ""
            if fixed_line.strip() == "":
                # deletion — remove the line entirely
                lines.pop(line_number - 1)
            else:
                lines[line_number - 1] = fixed_line.strip() + ending
            print(
                f"  ✓ Fixed line {line_number}: {repr(original_line.strip())} → {repr(fixed_line.strip())}"
            )
            return True
        else:
            print(
                f"  ⚠ Line {line_number} mismatch — expected {repr(orig_stripped)}, got {repr(actual)}"
            )

    # Strategy 2: search all lines
    if original_line.strip():
        for i, line in enumerate(lines):
            if original_line.strip() in line:
                ending = "\n" if line.endswith("\n") else ""
                if fixed_line.strip() == "":
                    lines.pop(i)
                else:
                    lines[i] = line.replace(
                        original_line.strip(), fixed_line.strip(), 1
                    )
                    if not lines[i].endswith("\n"):
                        lines[i] += ending
                print(
                    f"  ✓ Fixed line {i+1} via search: {repr(original_line.strip())} → {repr(fixed_line.strip())}"
                )
                return True

    print(f"  ✗ Could not locate: {repr(original_line.strip())}")
    return False


# ── Apply ALL fixes to a file in one pass ────────────────────────


def apply_all_fixes(file_path, fixes_list):
    full_path = os.path.join(PROJECT_ROOT, file_path)
    print(f"AI Agent: Applying {len(fixes_list)} fix(es) to {full_path}")

    if not os.path.exists(full_path):
        print(f"AI Agent: File not found — {full_path}")
        return False

    with open(full_path, "r", encoding="utf-8", errors="replace") as f:
        lines = f.readlines()

    # Sort fixes in reverse line order so line numbers stay valid after edits
    sorted_fixes = sorted(
        fixes_list, key=lambda x: x.get("line_number", 0), reverse=True
    )

    applied = 0
    for fix in sorted_fixes:
        ok = apply_single_fix(
            lines,
            fix.get("line_number"),
            fix.get("original_line", fix.get("original_code", "")),
            fix.get("fixed_line", fix.get("fixed_code", "")),
            file_path,
        )
        if ok:
            applied += 1

    with open(full_path, "w", encoding="utf-8") as f:
        f.writelines(lines)

    print(f"AI Agent: Applied {applied}/{len(fixes_list)} fixes to {file_path}")
    return applied > 0


# ── Git commit and push ───────────────────────────────────────────


def git_commit_and_push(file_paths, root_cause):
    repo_url = subprocess.run(
        ["git", "config", "--get", "remote.origin.url"], capture_output=True, text=True
    ).stdout.strip()

    github_token = os.environ.get("GITHUB_TOKEN", "")
    if github_token and "github.com" in repo_url:
        authed_url = repo_url.replace("https://", f"https://{github_token}@")
        subprocess.run(["git", "remote", "set-url", "origin", authed_url])

    subprocess.run(["git", "config", "user.email", "ai-bot@pipeline.local"])
    subprocess.run(["git", "config", "user.name", "AI-Remediation-Bot"])

    # stage all fixed files
    for fp in file_paths:
        full_path = os.path.join(PROJECT_ROOT, fp)
        subprocess.run(["git", "add", full_path])

    result = subprocess.run(
        ["git", "commit", "-m", f"AI-Fix: {root_cause[:72]}"],
        capture_output=True,
        text=True,
    )

    if result.returncode == 0:
        push = subprocess.run(
            ["git", "push", "origin", "HEAD:main"], capture_output=True, text=True
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
        print(
            f"AI Agent: Max retries ({MAX_RETRIES}) reached. Human intervention needed."
        )
        reset_retry()
        sys.exit(1)

    print(f"AI Agent: Attempt {retries + 1} of {MAX_RETRIES}")

    # 1. Extract error context
    error_context = extract_error_context(log_file_path)
    print(f"AI Agent: Extracted error context ({len(error_context)} chars)")

    # 2. Find broken files
    broken_files = extract_broken_files(log_file_path)
    print(f"AI Agent: Broken files detected: {broken_files}")

    # 3. Read the first broken file's actual content
    # WARNING: This agent is currently designed to fix only the first broken file found.
    # For multi-file errors, it would need to iterate through broken_files
    # and call Gemini for each, or Gemini's response format would need to support multiple files.
    file_path = broken_files[0] if broken_files else None
    file_content = read_broken_file(file_path) if file_path else None
    if file_content:
        print(f"AI Agent: Read {len(file_content)} chars from {file_path}")
    elif file_path:
        print(f"AI Agent: Warning — could not read {file_path}")

    # 4. Call Gemini — now asks for ALL fixes in one shot
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

    print(f"AI Agent: Root cause — {fix['root_cause']}")
    print(f"AI Agent: File       — {fix['file_path']}")
    print(f"AI Agent: Confidence — {fix['confidence']}")

    if fix["confidence"] < 0.75:
        print("AI Agent: Confidence too low — skipping auto-fix")
        increment_retry()
        sys.exit(1)

    # 6. Apply ALL fixes in one pass
    fixes_list = fix.get("fixes")

    # backwards-compat: single fix format
    if not fixes_list:
        fixes_list = [
            {
                "line_number": fix.get("line_number"),
                "original_line": fix.get("original_line", fix.get("original_code", "")),
                "fixed_line": fix.get("fixed_line", fix.get("fixed_code", "")),
            }
        ]

    print(f"AI Agent: Applying {len(fixes_list)} fix(es)...")
    success = apply_all_fixes(fix["file_path"], fixes_list)

    if not success:
        print("AI Agent: Failed to apply fixes")
        increment_retry()
        sys.exit(1)

    # 7. Commit and push all changes in one commit
    committed = git_commit_and_push([fix["file_path"]], fix["root_cause"])
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

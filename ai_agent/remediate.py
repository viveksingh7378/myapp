import os
import sys
import json
import subprocess
from log_parser import extract_error_context, get_failed_test_file

MAX_RETRIES = 2
RETRY_FILE = ".ai_retry_count"


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


def call_gemini(error_context):
    from google import genai

    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

    prompt = f"""You are an expert Python developer working on a CI/CD pipeline.
A test just failed. Analyze the error log below and return ONLY a JSON object.

Rules:
- Find the exact file and line causing the error
- Common errors: missing colon, wrong indentation, undefined variable, wrong import
- Return ONLY raw JSON, no markdown, no explanation, no code fences

JSON format:
{{
  "root_cause": "one sentence explanation",
  "file_path": "relative path like app/app.py",
  "original_code": "the exact broken line as it appears in the file",
  "fixed_code": "the corrected line",
  "confidence": 0.95
}}

Error log:
{error_context}"""

    response = client.models.generate_content(
        model="gemini-2.0-flash",
        contents=prompt
    )
    return response.text.strip()


def apply_fix(file_path, original_code, fixed_code):
    with open(file_path, 'r') as f:
        content = f.read()

    if original_code not in content:
        print(f"AI Agent: Could not find the exact line to fix in {file_path}")
        return False

    new_content = content.replace(original_code, fixed_code, 1)

    with open(file_path, 'w') as f:
        f.write(new_content)

    print(f"AI Agent: Fixed {file_path}")
    return True


def git_commit_fix(file_path, root_cause):
    subprocess.run(["git", "config", "user.email", "ai-bot@pipeline.local"])
    subprocess.run(["git", "config", "user.name", "AI-Remediation-Bot"])
    subprocess.run(["git", "add", file_path])
    result = subprocess.run(
        ["git", "commit", "-m", f"AI-Fix: {root_cause[:72]}"],
        capture_output=True, text=True
    )
    if result.returncode == 0:
        subprocess.run(["git", "push"])
        print("AI Agent: Fix committed and pushed successfully")
        return True
    else:
        print(f"AI Agent: Git commit failed — {result.stderr}")
        return False


def remediate(log_file_path):
    retries = get_retry_count()
    if retries >= MAX_RETRIES:
        print(f"AI Agent: Max retries ({MAX_RETRIES}) reached. Human intervention needed.")
        reset_retry()
        sys.exit(1)

    print(f"AI Agent: Attempt {retries + 1} of {MAX_RETRIES}")

    error_context = extract_error_context(log_file_path)
    print(f"AI Agent: Extracted error context ({len(error_context)} chars)")

    print("AI Agent: Sending to Gemini for analysis...")
    raw_response = call_gemini(error_context)
    print(f"AI Agent: Raw response received:\n{raw_response}")

    try:
        clean = raw_response.replace("```json", "").replace("```", "").strip()
        fix = json.loads(clean)
    except json.JSONDecodeError as e:
        print(f"AI Agent: Failed to parse response as JSON — {e}")
        increment_retry()
        sys.exit(1)

    print(f"AI Agent: Root cause — {fix['root_cause']}")
    print(f"AI Agent: Confidence — {fix['confidence']}")

    if fix['confidence'] < 0.75:
        print("AI Agent: Confidence too low, skipping auto-fix")
        sys.exit(1)

    success = apply_fix(fix['file_path'], fix['original_code'], fix['fixed_code'])
    if not success:
        increment_retry()
        sys.exit(1)

    committed = git_commit_fix(fix['file_path'], fix['root_cause'])
    if not committed:
        increment_retry()
        sys.exit(1)

    increment_retry()
    print("AI Agent: Self-healing complete. Pipeline will retrigger.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python remediate.py <log_file>")
        sys.exit(1)
    remediate(sys.argv[1])
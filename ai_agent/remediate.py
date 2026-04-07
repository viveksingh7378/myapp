import sys
import os
import json
import subprocess
from google import genai

MAX_RETRIES = 2
RETRY_COUNT_FILE = ".ai_retry_count"


def get_retry_count():
    if os.path.exists(RETRY_COUNT_FILE):
        return int(open(RETRY_COUNT_FILE).read().strip())
    return 0


def increment_retry():
    count = get_retry_count() + 1
    open(RETRY_COUNT_FILE, 'w').write(str(count))
    return count


def reset_retry():
    if os.path.exists(RETRY_COUNT_FILE):
        os.remove(RETRY_COUNT_FILE)


def analyze_and_fix(log_file_path):
    retries = get_retry_count()
    if retries >= MAX_RETRIES:
        print("AI Agent: Max retries reached. Notifying human.")
        reset_retry()
        sys.exit(1)

    with open(log_file_path, 'r') as f:
        logs = f.read()

    error_context = "\n".join(logs.splitlines()[-80:])

    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

    prompt = f"""You are an expert Python developer.
A CI/CD pipeline test failed. Analyze this error log and respond ONLY with valid JSON.
No explanation, no markdown, no backticks — pure JSON only.

{{
  "root_cause": "one sentence explanation",
  "file_path": "relative path to file to fix",
  "original_code": "exact broken code string",
  "fixed_code": "corrected code string",
  "confidence": 0.95
}}

Error log:
{error_context}"""

    response = client.models.generate_content(
        model="gemini-2.0-flash-lite",
        contents=prompt
    )

    raw = response.text.strip()

    # Clean up in case Gemini wraps in backticks
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip()

    fix = json.loads(raw)
    print(f"AI Root Cause: {fix['root_cause']}")
    print(f"Confidence: {fix['confidence']}")

    if fix["confidence"] < 0.8:
        print("Confidence too low — skipping auto-fix.")
        sys.exit(1)

    # Apply the fix
    with open(fix["file_path"], 'r') as f:
        content = f.read()

    if fix["original_code"] not in content:
        print("Could not locate the broken code in file — skipping.")
        sys.exit(1)

    content = content.replace(fix["original_code"], fix["fixed_code"])

    with open(fix["file_path"], 'w') as f:
        f.write(content)

    # Git commit the fix
    subprocess.run(["git", "config", "user.email", "ai-bot@pipeline.local"])
    subprocess.run(["git", "config", "user.name", "AI-Remediation-Bot"])
    subprocess.run(["git", "add", fix["file_path"]])
    subprocess.run(["git", "commit", "-m", f"AI-Fix: {fix['root_cause'][:60]}"])
    subprocess.run(["git", "push"])

    increment_retry()
    print("AI fix applied and pushed to repo.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 remediate.py <log_file>")
        sys.exit(1)
    analyze_and_fix(sys.argv[1])
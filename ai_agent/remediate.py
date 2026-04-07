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
    import time
    from google import genai
    from google.genai import errors as genai_errors

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

    models_to_try = ["gemini-1.5-flash", "gemini-1.0-pro"]

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
                print(f"AI Agent: {model_name} quota exceeded, trying next model...")
                time.sleep(5)
                continue
            else:
                raise e

    raise Exception("AI Agent: All models exhausted — quota exceeded on all")
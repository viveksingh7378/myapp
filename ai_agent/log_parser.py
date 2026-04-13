import re
import os


def extract_error_context(log_file_path, lines=60):
    with open(log_file_path, "r") as f:
        all_lines = f.readlines()

    # find the line where the error starts
    error_start = 0
    for i, line in enumerate(all_lines):
        if any(
            keyword in line
            for keyword in ["FAILED", "ERROR", "error", "Exception", "SyntaxError"]
        ):
            error_start = max(0, i - 5)
            break

    # return 60 lines from that point
    relevant = all_lines[error_start : error_start + lines]
    return "".join(relevant)


def get_failed_test_file(log_file_path):
    """Legacy: extract first .py file path from log."""
    with open(log_file_path, "r") as f:
        content = f.read()

    match = re.search(r"([\w/]+\.py)", content)
    if match:
        return match.group(1)
    return None


def extract_broken_files(log_file_path):
    """
    Extract broken file paths from any error log — any language.
    Priority: validator.py format first (most precise), then pytest format.
    Returns a list of relative file paths like ['blog.html', 'app/app.py']
    """
    with open(log_file_path, "r") as f:
        content = f.read()

    found = []

    # Priority 1: validator.py format  →  "ERROR: /abs/path/blog.html: ..."
    # or "ERROR: blog.html: ..."  — strip absolute path to get relative
    for match in re.finditer(
        r"(?:ERROR|SyntaxError):\s+(?:[^\s:]+/)?"
        r"([\w][\w./\-]*\.(?:py|html|htm|js|css|json|yaml|yml)):",
        content,
    ):
        path = match.group(1)
        # keep only the filename / short relative path
        # e.g. strip leading "workspace/myapp-pipeline/" prefixes
        # Make sure PROJECT_ROOT is available in this module, e.g., via import or parameter
        PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        rel = os.path.relpath(path, PROJECT_ROOT)
        if rel and rel not in found:
            found.append(rel)

    if found:
        return found

    # Priority 2: pytest format  →  File "/abs/path/app/app.py", line N
    for match in re.finditer(r'File "([^"]+\.(?:py|html|js|css|json))"', content):
        path = match.group(1)
        # Make sure PROJECT_ROOT is available in this module, e.g., via import or parameter
        PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        rel = os.path.relpath(path, PROJECT_ROOT)
        if rel and rel not in found:
            found.append(rel)

    return found

import re
import os


def extract_error_context(log_file_path, lines=60):
    with open(log_file_path, 'r') as f:
        all_lines = f.readlines()

    # find the line where the error starts
    error_start = 0
    for i, line in enumerate(all_lines):
        if any(keyword in line for keyword in ['FAILED', 'ERROR', 'error', 'Exception', 'SyntaxError']):
            error_start = max(0, i - 5)
            break

    # return 60 lines from that point
    relevant = all_lines[error_start: error_start + lines]
    return "".join(relevant)


def get_failed_test_file(log_file_path):
    """Legacy: extract first .py file path from log."""
    with open(log_file_path, 'r') as f:
        content = f.read()

    match = re.search(r'([\w/]+\.py)', content)
    if match:
        return match.group(1)
    return None


def extract_broken_files(log_file_path):
    """
    Extract ALL broken file paths from any error log — any language.
    Handles both validator.py output and pytest output.
    Returns a list of relative file paths like ['blog.html', 'app/app.py']
    """
    with open(log_file_path, 'r') as f:
        content = f.read()

    found = []

    # Pattern 1: validator.py format  →  "ERROR: blog.html: ..."
    for match in re.finditer(r'(?:ERROR|SyntaxError):\s+([\w./\-]+\.\w+):', content):
        path = match.group(1)
        if path not in found:
            found.append(path)

    # Pattern 2: pytest format  →  "File /abs/path/app/app.py, line N"
    for match in re.finditer(r'File "?([^":\n]+\.(?:py|html|js|css|json))"?', content):
        path = match.group(1)
        # strip absolute prefix to get relative path
        rel = re.sub(r'^.+/myapp/', '', path)
        if rel not in found:
            found.append(rel)

    # Pattern 3: plain filename  →  "app/app.py"
    for match in re.finditer(r'([\w]+(?:/[\w]+)*\.(?:py|html|js|css|json))', content):
        path = match.group(1)
        if path not in found:
            found.append(path)

    return found

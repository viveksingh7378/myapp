import re

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
    with open(log_file_path, 'r') as f:
        content = f.read()

    # extract which file failed e.g. "app/app.py", "tests/test_app.py"
    match = re.search(r'([\w/]+\.py)', content)
    if match:
        return match.group(1)
    return None
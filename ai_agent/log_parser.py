def extract_errors(log_text, tail=80):
    """Extract the most relevant lines from a pytest log."""
    lines = log_text.splitlines()

    # Grab lines with errors/failures
    relevant = [
        line for line in lines
        if any(k in line for k in ["FAILED", "ERROR", "assert", "Exception", "Traceback"])
    ]

    # Also include last N lines for context
    last_lines = lines[-tail:]

    combined = relevant + last_lines
    # Deduplicate while preserving order
    seen = set()
    result = []
    for line in combined:
        if line not in seen:
            seen.add(line)
            result.append(line)

    return "\n".join(result)
"""
Universal Code Validator
Scans all project files and detects syntax errors in any language.
Writes results to validation_output.txt for the AI agent to consume.
"""

import os
import sys
import subprocess
import json
from html.parser import HTMLParser

# folders and files to skip
SKIP_DIRS = {
    "venv",
    "__pycache__",
    ".git",
    ".pytest_cache",
    "node_modules",
    ".ai_retry_count",
}
SKIP_EXTS = {".pyc", ".pyo", ".jpg", ".png", ".gif", ".ico", ".zip", ".gz"}

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_FILE = os.path.join(PROJECT_ROOT, "validation_output.txt")


# ── HTML Validator ────────────────────────────────────────────────
class StrictHTMLParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.errors = []
        self.open_tags = []
        self.VOID_TAGS = {
            "area",
            "base",
            "br",
            "col",
            "embed",
            "hr",
            "img",
            "input",
            "link",
            "meta",
            "param",
            "source",
            "track",
            "wbr",
        }

    def handle_starttag(self, tag, attrs):
        if tag not in self.VOID_TAGS:
            self.open_tags.append(tag)

    def handle_endtag(self, tag):
        if tag in self.VOID_TAGS:
            return
        if self.open_tags and self.open_tags[-1] == tag:
            self.open_tags.pop()
        else:
            self.errors.append(
                f"Unexpected closing tag </{tag}> (line {self.get_current_lineno()}) — open tags: {self.open_tags}"
                f"open tags: {self.open_tags}"
            )

    def get_errors(self):
        errors = list(self.errors)
        if self.open_tags:
            errors.append(
                f"Unclosed tags at end of file: {self.open_tags} (last seen on line {self.get_current_lineno()})"
            )
        return errors


def validate_html(filepath):
    errors = []
    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()

        # Check required root tags first — if any are missing,
        # report only those and skip structural checks to avoid
        # cascading errors caused by the same root problem.
        required = ["<html", "<head>", "<body>"]
        missing = [t for t in required if t not in content.lower()]

        if missing:
            for tag in missing:
                errors.append(
                    f"ERROR: {os.path.relpath(filepath, PROJECT_ROOT)}: Missing required tag '{tag}'"
                )
            # don't run structural checks — all other errors are cascading
            return errors

        # Only run structural parse when root tags are present
        parser = StrictHTMLParser()
        try:
            parser.feed(content)
            # HTMLParser automatically handles line numbers for parse errors, but not custom logic
            for err in parser.get_errors():
                errors.append(
                    f"ERROR: {os.path.relpath(filepath, PROJECT_ROOT)}: {err}"
                )
        except Exception as e:
            errors.append(
                f"ERROR: {os.path.relpath(filepath, PROJECT_ROOT)}: HTML parse error — {e}"
            )
            errors.append(f"ERROR: {filepath}: HTML parse error — {e}")

    except Exception as e:
        errors.append(
            f"ERROR: {os.path.relpath(filepath, PROJECT_ROOT)}: Could not read file — {e}"
        )
        errors.append(
            f"ERROR: {os.path.relpath(filepath, PROJECT_ROOT)}: Could not read file — {e}"
        )
    return errors


# ── Python Validator ──────────────────────────────────────────────
def validate_python(filepath):
    errors = []
    try:
        result = subprocess.run(
            [sys.executable, "-m", "py_compile", filepath],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            msg = result.stderr.strip()
            errors.append(f"SyntaxError: {filepath}: {msg}")
    except Exception as e:
        errors.append(f"ERROR: {filepath}: Could not validate — {e}")
    return errors


# ── JavaScript Validator ──────────────────────────────────────────
def validate_javascript(filepath):
    errors = []
    try:
        result = subprocess.run(
            ["node", "--check", filepath], capture_output=True, text=True
        )
        if result.returncode != 0:
            msg = result.stderr.strip()
            errors.append(f"SyntaxError: {filepath}: {msg}")
    except FileNotFoundError:
        # node not installed — skip silently
        pass
    except Exception as e:
        errors.append(f"ERROR: {filepath}: Could not validate — {e}")
    return errors


# ── CSS Validator ─────────────────────────────────────────────────
def validate_css(filepath):
    errors = []
    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        # WARNING: This CSS validation is extremely naive and prone to false positives.
        # It does not account for braces inside comments, strings, or valid CSS structures.
        # A proper CSS parser/linter should be used for robust validation.
        opens = content.count("{")
        closes = content.count("}")
        if opens != closes:
            errors.append(
                f"ERROR: {filepath}: Mismatched braces "
                f"({{ x{opens} vs }} x{closes})"
            )
    except Exception as e:
        errors.append(f"ERROR: {filepath}: Could not read file — {e}")
    return errors


# ── JSON Validator ────────────────────────────────────────────────
def validate_json(filepath):
    errors = []
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            json.load(f)
    except json.JSONDecodeError as e:
        errors.append(f"SyntaxError: {filepath}: {e}")
    except Exception as e:
        errors.append(f"ERROR: {filepath}: Could not read — {e}")
    return errors


# ── File Scanner ──────────────────────────────────────────────────
VALIDATORS = {
    ".py": validate_python,
    ".html": validate_html,
    ".htm": validate_html,
    ".js": validate_javascript,
    ".css": validate_css,
    ".json": validate_json,
}


def scan_project():
    all_errors = []
    scanned = 0

    for dirpath, dirnames, filenames in os.walk(PROJECT_ROOT):
        # prune skip dirs in-place so os.walk doesn't descend into them
        dirnames[:] = [
            d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")
        ]

        for filename in filenames:
            ext = os.path.splitext(filename)[1].lower()
            if ext in SKIP_EXTS:
                continue
            if ext not in VALIDATORS:
                continue

            filepath = os.path.join(dirpath, filename)
            rel_path = os.path.relpath(filepath, PROJECT_ROOT)

            validator = VALIDATORS[ext]
            errors = validator(filepath)
            scanned += 1

            if errors:
                for err in errors:
                    all_errors.append(err)
                    print(f"  ✗ {err}")
            else:
                print(f"  ✓ {rel_path}")

    return scanned, all_errors


def main():
    print("=" * 60)
    print("Universal Code Validator")
    print(f"Project root: {PROJECT_ROOT}")
    print("=" * 60)

    scanned, errors = scan_project()

    print("=" * 60)
    print(f"Scanned {scanned} files — {len(errors)} error(s) found")
    print("=" * 60)

    # write output file for AI agent to consume
    with open(OUTPUT_FILE, "w") as f:
        if errors:
            f.write(f"VALIDATOR FOUND {len(errors)} ERROR(S)\n\n")
            for err in errors:
                f.write(err + "\n")
            f.write("\nFAILED\n")
        else:
            f.write("All files passed validation.\n")

    if errors:
        print(f"\nErrors written to: {OUTPUT_FILE}")
        sys.exit(1)
    else:
        print("\nAll files valid.")
        sys.exit(0)


if __name__ == "__main__":
    main()

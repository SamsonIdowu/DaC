#!/usr/bin/env python3
"""Validate the Wazuh ruleset in this repository. Fails closed.

The checks run against the whole checked-out tree rather than a diff. In a
``pull_request`` run that tree is the merge of the PR into ``main``, i.e. exactly
what will be deployed, so renamed, moved, and newly added files are all handled
the same way and duplicates across several files in one PR are caught.

Errors (exit code 1):
  * a symlink anywhere in the repository (the deploy job runs chown/chmod as root)
  * a file under rules/ or decoders/ that is not a top-level *.xml file
  * a rules/ or decoders/ file that cannot be read or parsed
  * a <rule> without a purely numeric id
  * the same rule id defined more than once
  * a rule id outside the custom range that does not set overwrite="yes"

Warnings (shown for reviewers, do not fail the check):
  * overwrite="yes" rules, which replace an existing (usually built-in) rule
  * level="0" rules, which silence every event they match
"""

import os
import re
import subprocess
import sys
import xml.parsers.expat
from collections import defaultdict
from pathlib import Path

# Wazuh reserves ids below 100000 for its built-in ruleset; local rules belong
# in 100000-120000 (https://documentation.wazuh.com/current/user-manual/ruleset/).
CUSTOM_ID_MIN = 100000
CUSTOM_ID_MAX = 120000

RULESET_DIRS = ("rules", "decoders")
SYMLINK_MODE = "120000"

IN_ACTIONS = os.environ.get("GITHUB_ACTIONS") == "true"

# Wazuh's own XML reader is more lenient than a standards-compliant parser. These
# two rewrites accept what Wazuh accepts while keeping line numbers unchanged.
XML_DECLARATION = re.compile(r"\A\s*<\?xml[^>]*\?>")
BARE_AMPERSAND = re.compile(r"&(?!(?:[A-Za-z][A-Za-z0-9]*|#[0-9]+|#x[0-9A-Fa-f]+);)")


class Report:
    def __init__(self):
        self.errors = 0
        self.warnings = 0

    def _emit(self, kind, message, path=None, line=None):
        where = f"{path}:{line}" if path and line else (str(path) if path else "")
        icon = "❌" if kind == "error" else "⚠️"
        print(f"{icon} {where + ': ' if where else ''}{message}")
        if IN_ACTIONS:
            location = ""
            if path:
                location = f" file={path}" + (f",line={line}" if line else "")
            print(f"::{kind}{location}::{message}")

    def error(self, message, path=None, line=None):
        self.errors += 1
        self._emit("error", message, path, line)

    def warning(self, message, path=None, line=None):
        self.warnings += 1
        self._emit("warning", message, path, line)


def git(*args):
    return subprocess.run(["git", *args], capture_output=True, text=True, check=True).stdout


def tracked_files():
    """Yield (mode, path) for every tracked file, NUL-separated so no path is quoted."""
    for entry in git("ls-files", "--stage", "-z").split("\0"):
        if not entry:
            continue
        meta, path = entry.split("\t", 1)
        yield meta.split()[0], path


def parse_rules(path, text):
    """Return [(raw_id, attrs, line)] for every <rule>, or raise ExpatError."""
    text = XML_DECLARATION.sub(lambda m: re.sub(r"[^\n]", " ", m.group(0)), text)
    text = BARE_AMPERSAND.sub("&amp;", text)

    rules = []
    parser = xml.parsers.expat.ParserCreate()

    def start(name, attrs):
        if name == "rule":
            rules.append((attrs.get("id"), attrs, parser.CurrentLineNumber))

    parser.StartElementHandler = start
    # Rule files have several top-level elements (<group>, <var>), so wrap them.
    # The opening tag adds no newline, so reported line numbers match the file.
    parser.Parse(f"<root>{text}</root>", True)
    return rules


def main():
    os.chdir(git("rev-parse", "--show-toplevel").strip())
    report = Report()

    ruleset_files = []
    for mode, path in tracked_files():
        if mode == SYMLINK_MODE:
            report.error("symlinks are not allowed in this repository", path)
            continue
        parts = Path(path).parts
        if parts[0] in RULESET_DIRS:
            if len(parts) != 2 or not path.endswith(".xml"):
                report.error(
                    f"only top-level *.xml files are deployed from {parts[0]}/", path
                )
                continue
            ruleset_files.append(Path(path))

    id_locations = defaultdict(list)
    rule_count = 0

    for path in sorted(ruleset_files):
        try:
            text = path.read_bytes().decode("utf-8")
            rules = parse_rules(path, text)
        except (OSError, UnicodeDecodeError) as e:
            report.error(f"could not read file: {e}", path)
            continue
        except xml.parsers.expat.ExpatError as e:
            report.error(f"XML parse error: {xml.parsers.expat.errors.messages[e.code]}",
                         path, e.lineno)
            continue

        if path.parts[0] != "rules":
            continue  # decoders only need to be well-formed

        for raw_id, attrs, line in rules:
            rule_count += 1
            rule_id = (raw_id or "").strip()
            if not re.fullmatch(r"[0-9]+", rule_id):
                report.error(f"rule has a missing or non-numeric id: {raw_id!r}", path, line)
                continue
            rule_id = int(rule_id)
            id_locations[rule_id].append((path, line))

            overwrite = attrs.get("overwrite", "").strip().lower() == "yes"
            in_range = CUSTOM_ID_MIN <= rule_id <= CUSTOM_ID_MAX
            if overwrite:
                report.warning(f"rule {rule_id} uses overwrite=\"yes\" and replaces an "
                               "existing rule; review it carefully", path, line)
            elif not in_range:
                report.error(f"rule id {rule_id} is outside the custom range "
                             f"{CUSTOM_ID_MIN}-{CUSTOM_ID_MAX}; pick a custom id, or set "
                             "overwrite=\"yes\" if replacing a built-in rule is intended",
                             path, line)
            if attrs.get("level", "").strip() == "0":
                report.warning(f"rule {rule_id} has level=\"0\" and will silence every "
                               "event it matches; review it carefully", path, line)

    for rule_id, locations in sorted(id_locations.items()):
        if len(locations) > 1:
            where = ", ".join(f"{p}:{line}" for p, line in locations)
            for path, line in locations:
                report.error(f"rule id {rule_id} is defined {len(locations)} times ({where})",
                             path, line)

    print(f"\n🔍 Checked {len(ruleset_files)} ruleset file(s), {rule_count} rule(s): "
          f"{report.errors} error(s), {report.warnings} warning(s).")
    if report.errors:
        print("❌ Ruleset check failed.")
        sys.exit(1)
    print("✅ Ruleset check passed.")


if __name__ == "__main__":
    main()

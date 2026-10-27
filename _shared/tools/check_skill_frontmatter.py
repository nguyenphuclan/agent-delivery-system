"""Assert every SKILL.md can actually be read by the router.

Why this exists: a skill whose frontmatter does not parse loses its `description` AND its
`triggers`, so the router never reaches it - and nothing says so. The listing just shows the first
heading where the description should be. Measured 2026-08-21: 8 of 63 skills were in that state,
and one of them (the live-API test skill) was the reason "test live api" kept routing to an inline
script for a whole session.

An audit step already claimed to "spot-check each SKILL.md frontmatter". Prose did not catch
these; this does.

    python check_skill_frontmatter.py [skills_dir]      (default: ~/.claude/skills)

Exit 0 = every skill parses. Exit 1 = at least one is unreadable. Prints the cause per skill.

Two distinct faults, both silent:
  * a UTF-8 BOM before the opening `---`  -> the frontmatter block is never recognised
  * invalid YAML inside it, most often an unquoted scalar containing ": "  (e.g.
    `description: ... Purpose: catch ...`) -> parse error, description falls back to a heading
"""
import glob
import io
import os
import sys

try:
    import yaml
except ImportError:
    print("PyYAML not installed - cannot check")
    sys.exit(1)


def check(path):
    """Return None when fine, else a one-line reason."""
    raw = io.open(path, "rb").read()
    if raw[:3] == b"\xef\xbb\xbf":
        return "BOM before the opening --- (strip the first 3 bytes)"
    text = raw.decode("utf-8", errors="replace")
    if not text.startswith("---"):
        return "does not open with ---"
    parts = text.split("---")
    if len(parts) < 3:
        return "frontmatter block never closes"
    try:
        data = yaml.safe_load(parts[1])
    except Exception as e:
        return "YAML: " + str(e).split("\n")[0]
    if not isinstance(data, dict):
        return "frontmatter is not a mapping"
    for key in ("name", "description"):
        if not data.get(key):
            return "missing `%s`" % key
    return None


def main():
    root = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        os.path.expanduser("~"), ".claude", "skills")
    files = sorted(glob.glob(os.path.join(root, "*", "SKILL.md")))
    if not files:
        print("no SKILL.md found under " + root)
        return 1
    bad = []
    for p in files:
        reason = check(p)
        if reason:
            bad.append((os.path.basename(os.path.dirname(p)), reason))
    print("skills checked: %d   unreadable: %d" % (len(files), len(bad)))
    for name, reason in bad:
        print("  BROKEN  %-26s %s" % (name, reason))
    if bad:
        print("")
        print("A broken frontmatter means the router sees no description and no triggers.")
        print("Fix by quoting the description (or using a block scalar) and removing any BOM.")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())

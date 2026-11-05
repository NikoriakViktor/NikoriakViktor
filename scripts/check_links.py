"""Check that every relative link and image in README.md and pages/*.md exists.

Usage: python scripts/check_links.py   (exit code 1 if anything is missing)
External links (http/https/mailto) are skipped: they change outside this repo.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LINK = re.compile(r'\]\(([^)\s]+)\)|(?:src|href)="([^"]+)"')


def main() -> int:
    missing = []
    for md in [ROOT / "README.md", *sorted((ROOT / "pages").glob("*.md"))]:
        for m in LINK.finditer(md.read_text(encoding="utf-8")):
            target = m.group(1) or m.group(2)
            if re.match(r"^(https?:|mailto:|#)", target):
                continue
            path = (md.parent / target.split("#")[0]).resolve()
            if not path.exists():
                missing.append(f"{md.relative_to(ROOT)} → {target}")
    for item in missing:
        print("missing:", item)
    print(f"{'FAIL' if missing else 'OK'}: {len(missing)} missing local links")
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())

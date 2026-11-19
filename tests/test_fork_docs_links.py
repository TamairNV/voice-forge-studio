import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LINK = re.compile(r"\]\(([^)\s]+)\)")


def _markdown_files():
    yield ROOT / "README.md"
    yield from (ROOT / "docs").rglob("*.md")


FENCE = re.compile(r"```.*?```", re.S)


def test_relative_links_resolve():
    broken = []
    for md in _markdown_files():
        text = FENCE.sub("", md.read_text(encoding="utf-8", errors="ignore"))
        for target in LINK.findall(text):
            if target.startswith(("http://", "https://", "#", "mailto:")):
                continue
            path = (md.parent / target.split("#", 1)[0]).resolve()
            if not path.exists():
                broken.append(f"{md.relative_to(ROOT)} -> {target}")
    assert broken == []

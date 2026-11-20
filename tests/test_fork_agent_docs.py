from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_claude_md():
    text = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    assert "127.0.0.1" in text and "@AGENTS.md" in text and "0.0.0.0" not in text


def test_agents_md():
    assert "2026-11-19-roadmap.md" in (ROOT / "AGENTS.md").read_text(encoding="utf-8")


def test_readme():
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "uvicorn" in text and "FORK-NOTICE.md" in text and "0.0.0.0" not in text


def test_docs_are_ascii():
    for name in ("README.md", "CLAUDE.md", "AGENTS.md", "FORK-NOTICE.md"):
        (ROOT / name).read_text(encoding="utf-8").encode("ascii")

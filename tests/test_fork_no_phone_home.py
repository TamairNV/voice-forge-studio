from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BANNED_HOSTS = ["voicestudio.sh", "supermetry.com", "posthog", "twilio.com", "jsdelivr.net"]
# Files that still mention a banned host because a later task removes them.
# Each entry names that task. Task 29 empties this set.
PENDING: dict[str, str] = {}


def test_no_phone_home_hosts_in_backend():
    hits = sorted(
        (path.relative_to(ROOT).as_posix(), host)
        for path in (ROOT / "backend").rglob("*.py")
        for host in BANNED_HOSTS
        if host in path.read_text(encoding="utf-8", errors="ignore")
        and path.relative_to(ROOT).as_posix() not in PENDING
    )
    assert hits == []

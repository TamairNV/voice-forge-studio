"""Voice Forge tables: characters, emotion profiles, casts, scenes and takes.

Revision ID: 0019_voice_forge_tables
Revises: 0018_pronunciation_profile_scope

Additive and idempotent migration introducing the five Voice Forge tables
(``vf_characters``, ``vf_profiles``, ``vf_casts``, ``vf_scenes``, ``vf_takes``)
also declared in ``core/db.py``'s ``_BASE_SCHEMA``.
"""
from collections.abc import Sequence

from alembic import op

revision: str = "0019_voice_forge_tables"
down_revision: str | None = "0018_pronunciation_profile_scope"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS vf_characters (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            ref_text TEXT NOT NULL DEFAULT '',
            audio_file TEXT NOT NULL DEFAULT '',
            source_model TEXT NOT NULL DEFAULT '',
            favorite INTEGER NOT NULL DEFAULT 0,
            tags_json TEXT NOT NULL DEFAULT '[]',
            extra_json TEXT NOT NULL DEFAULT '{}',
            created_at REAL NOT NULL DEFAULT 0,
            updated_at REAL NOT NULL DEFAULT 0
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS vf_profiles (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            clips_json TEXT NOT NULL DEFAULT '{}',
            extra_json TEXT NOT NULL DEFAULT '{}',
            created_at REAL NOT NULL DEFAULT 0,
            updated_at REAL NOT NULL DEFAULT 0
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS vf_casts (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            title TEXT NOT NULL DEFAULT '',
            script TEXT NOT NULL DEFAULT '',
            mapping_json TEXT NOT NULL DEFAULT '{}',
            lines_json TEXT NOT NULL DEFAULT '[]',
            temperature REAL,
            extra_json TEXT NOT NULL DEFAULT '{}',
            created_at REAL NOT NULL DEFAULT 0,
            updated_at REAL NOT NULL DEFAULT 0
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS vf_scenes (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL DEFAULT '',
            filename TEXT NOT NULL DEFAULT '',
            duration_sec REAL NOT NULL DEFAULT 0,
            elapsed_sec REAL NOT NULL DEFAULT 0,
            model_swaps INTEGER NOT NULL DEFAULT 0,
            line_count INTEGER NOT NULL DEFAULT 0,
            cast_json TEXT NOT NULL DEFAULT '{}',
            segments_json TEXT NOT NULL DEFAULT '[]',
            extra_json TEXT NOT NULL DEFAULT '{}',
            created_at REAL NOT NULL DEFAULT 0
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS vf_takes (
            id TEXT PRIMARY KEY,
            text TEXT NOT NULL DEFAULT '',
            model_id TEXT NOT NULL DEFAULT '',
            character_id TEXT NOT NULL DEFAULT '',
            filename TEXT NOT NULL DEFAULT '',
            duration_sec REAL NOT NULL DEFAULT 0,
            elapsed_sec REAL NOT NULL DEFAULT 0,
            extra_json TEXT NOT NULL DEFAULT '{}',
            created_at REAL NOT NULL DEFAULT 0
        )
        """
    )


def downgrade() -> None:
    """Keep user-authored Voice Forge records on downgrade (additive migration)."""

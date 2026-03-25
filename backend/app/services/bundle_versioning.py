"""Bundle versioning service.

Every generated bundle is versioned and tracked:
- Stores metadata (who, when, what SRS, validation result)
- Tracks upload status and results
- Enables rollback (download previous versions)
- Compares versions (what changed between v1 and v2)
"""

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from app import db

logger = logging.getLogger(__name__)


# ── Schema ────────────────────────────────────────────────────────────────────

BUNDLE_VERSION_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS bundle_versions (
    id              TEXT PRIMARY KEY,
    org_id          TEXT NOT NULL,
    user_id         TEXT NOT NULL,
    bundle_id       TEXT NOT NULL,
    bundle_name     TEXT NOT NULL,
    version_number  INT NOT NULL DEFAULT 1,
    srs_snapshot    JSONB DEFAULT '{}'::jsonb,
    file_path       TEXT,
    file_size       BIGINT DEFAULT 0,
    validation_result JSONB,
    upload_result   JSONB,
    status          TEXT NOT NULL DEFAULT 'generated',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_bundle_versions_org_id ON bundle_versions(org_id);
CREATE INDEX IF NOT EXISTS idx_bundle_versions_bundle_id ON bundle_versions(bundle_id);
CREATE INDEX IF NOT EXISTS idx_bundle_versions_created_at ON bundle_versions(created_at);
"""


async def init_bundle_version_schema() -> None:
    """Create the bundle_versions table if it does not exist."""
    if not db._pool:
        logger.warning("DB pool not available — bundle version schema creation skipped")
        return
    try:
        async with db._pool.acquire() as conn:
            await conn.execute(BUNDLE_VERSION_SCHEMA_SQL)
        logger.info("Bundle version schema ready")
    except Exception as e:
        logger.error("Failed to create bundle version schema: %s", e)


# ── Core functions ────────────────────────────────────────────────────────────

async def save_version(
    org_id: str,
    user_id: str,
    bundle_id: str,
    bundle_name: str,
    srs_snapshot: dict[str, Any] | None = None,
    file_path: str | None = None,
    file_size: int = 0,
) -> dict | None:
    """Save a new bundle version. Automatically increments version_number per org."""
    if not db._pool:
        logger.debug("Bundle version save skipped (no DB)")
        return None

    version_id = str(uuid.uuid4())

    try:
        async with db._pool.acquire() as conn:
            # Get next version number for this org
            max_version = await conn.fetchval(
                "SELECT COALESCE(MAX(version_number), 0) FROM bundle_versions WHERE org_id = $1",
                org_id,
            )
            next_version = max_version + 1

            row = await conn.fetchrow(
                """
                INSERT INTO bundle_versions
                    (id, org_id, user_id, bundle_id, bundle_name, version_number,
                     srs_snapshot, file_path, file_size, status)
                VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb, $8, $9, 'generated')
                RETURNING *
                """,
                version_id,
                org_id,
                user_id,
                bundle_id,
                bundle_name,
                next_version,
                json.dumps(srs_snapshot) if srs_snapshot else "{}",
                file_path,
                file_size,
            )
            return dict(row) if row else None
    except Exception as e:
        logger.error("Failed to save bundle version: %s", e)
        return None


async def get_versions(org_id: str, limit: int = 20) -> list[dict]:
    """List bundle versions for an org, newest first."""
    if not db._pool:
        return []

    try:
        async with db._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, org_id, user_id, bundle_id, bundle_name, version_number,
                       file_size, status, created_at, updated_at
                FROM bundle_versions
                WHERE org_id = $1
                ORDER BY version_number DESC
                LIMIT $2
                """,
                org_id,
                limit,
            )
            return [dict(r) for r in rows]
    except Exception as e:
        logger.error("Failed to get bundle versions: %s", e)
        return []


async def get_version(version_id: str) -> dict | None:
    """Get a specific version with full details including SRS snapshot."""
    if not db._pool:
        return None

    try:
        async with db._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM bundle_versions WHERE id = $1",
                version_id,
            )
            return dict(row) if row else None
    except Exception as e:
        logger.error("Failed to get bundle version %s: %s", version_id, e)
        return None


async def mark_uploaded(version_id: str, upload_result: dict[str, Any]) -> dict | None:
    """Record a successful bundle upload against a version."""
    if not db._pool:
        return None

    try:
        async with db._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                UPDATE bundle_versions
                SET upload_result = $1::jsonb,
                    status = 'uploaded',
                    updated_at = now()
                WHERE id = $2
                RETURNING *
                """,
                json.dumps(upload_result),
                version_id,
            )
            return dict(row) if row else None
    except Exception as e:
        logger.error("Failed to mark bundle version uploaded: %s", e)
        return None


async def mark_validated(version_id: str, validation_result: dict[str, Any]) -> dict | None:
    """Record a validation result against a version."""
    if not db._pool:
        return None

    try:
        async with db._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                UPDATE bundle_versions
                SET validation_result = $1::jsonb,
                    status = 'validated',
                    updated_at = now()
                WHERE id = $2
                RETURNING *
                """,
                json.dumps(validation_result),
                version_id,
            )
            return dict(row) if row else None
    except Exception as e:
        logger.error("Failed to mark bundle version validated: %s", e)
        return None


async def get_latest_version(org_id: str) -> dict | None:
    """Get the most recent bundle version for an org."""
    if not db._pool:
        return None

    try:
        async with db._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT * FROM bundle_versions
                WHERE org_id = $1
                ORDER BY version_number DESC
                LIMIT 1
                """,
                org_id,
            )
            return dict(row) if row else None
    except Exception as e:
        logger.error("Failed to get latest bundle version: %s", e)
        return None


async def compare_versions(version_id_1: str, version_id_2: str) -> dict[str, Any]:
    """Compare two bundle versions by diffing their SRS snapshots.

    Returns a structured diff showing:
    - Added/removed subject types
    - Added/removed programs
    - Added/removed encounter types
    - Changed forms (added/removed fields)
    - Changed concepts
    """
    v1 = await get_version(version_id_1)
    v2 = await get_version(version_id_2)

    if not v1 or not v2:
        return {"error": "One or both versions not found"}

    srs1 = v1.get("srs_snapshot") or {}
    srs2 = v2.get("srs_snapshot") or {}

    # Parse JSONB — asyncpg may return a string or already-decoded dict
    if isinstance(srs1, str):
        srs1 = json.loads(srs1) if srs1 else {}
    if isinstance(srs2, str):
        srs2 = json.loads(srs2) if srs2 else {}

    diff: dict[str, Any] = {
        "version_1": {"id": version_id_1, "version_number": v1.get("version_number"), "created_at": str(v1.get("created_at", ""))},
        "version_2": {"id": version_id_2, "version_number": v2.get("version_number"), "created_at": str(v2.get("created_at", ""))},
        "changes": {},
    }

    # Compare top-level named lists
    for key in ("subjectTypes", "programs", "encounterTypes"):
        items1 = {_item_name(i) for i in srs1.get(key, [])}
        items2 = {_item_name(i) for i in srs2.get(key, [])}
        added = sorted(items2 - items1)
        removed = sorted(items1 - items2)
        if added or removed:
            diff["changes"][key] = {"added": added, "removed": removed}

    # Compare forms — deeper: look at fields within each form
    forms1 = {f.get("name", ""): f for f in srs1.get("forms", [])}
    forms2 = {f.get("name", ""): f for f in srs2.get("forms", [])}
    form_names1 = set(forms1.keys())
    form_names2 = set(forms2.keys())

    forms_diff: dict[str, Any] = {}

    for name in sorted(form_names2 - form_names1):
        forms_diff[name] = {"status": "added"}
    for name in sorted(form_names1 - form_names2):
        forms_diff[name] = {"status": "removed"}

    # For forms present in both, compare fields
    for name in sorted(form_names1 & form_names2):
        fields1 = _extract_field_names(forms1[name])
        fields2 = _extract_field_names(forms2[name])
        added_fields = sorted(fields2 - fields1)
        removed_fields = sorted(fields1 - fields2)
        if added_fields or removed_fields:
            forms_diff[name] = {
                "status": "modified",
                "fields_added": added_fields,
                "fields_removed": removed_fields,
            }

    if forms_diff:
        diff["changes"]["forms"] = forms_diff

    # Compare concepts
    concepts1 = {c.get("name", "") for c in srs1.get("concepts", [])}
    concepts2 = {c.get("name", "") for c in srs2.get("concepts", [])}
    if concepts1 != concepts2:
        diff["changes"]["concepts"] = {
            "added": sorted(concepts2 - concepts1),
            "removed": sorted(concepts1 - concepts2),
        }

    return diff


async def get_version_history(org_id: str) -> list[dict]:
    """Full timeline of bundle versions with status for an org."""
    if not db._pool:
        return []

    try:
        async with db._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, org_id, user_id, bundle_id, bundle_name, version_number,
                       file_size, status,
                       validation_result IS NOT NULL as is_validated,
                       upload_result IS NOT NULL as is_uploaded,
                       created_at, updated_at
                FROM bundle_versions
                WHERE org_id = $1
                ORDER BY version_number ASC
                """,
                org_id,
            )
            return [dict(r) for r in rows]
    except Exception as e:
        logger.error("Failed to get version history: %s", e)
        return []


# ── Helpers ───────────────────────────────────────────────────────────────────

def _item_name(item: Any) -> str:
    """Extract a name from a list item (could be str or dict)."""
    if isinstance(item, str):
        return item
    if isinstance(item, dict):
        return item.get("name", str(item))
    return str(item)


def _extract_field_names(form: dict[str, Any]) -> set[str]:
    """Extract all field/concept names from a form definition."""
    names: set[str] = set()
    for group in form.get("formElementGroups", []):
        for elem in group.get("formElements", []):
            concept = elem.get("concept", {})
            name = elem.get("name") or concept.get("name", "")
            if name:
                names.add(name)
    return names

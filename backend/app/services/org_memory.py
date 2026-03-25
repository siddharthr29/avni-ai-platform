"""Org Memory Service.

Automatically learns and remembers org-specific context:
- Subject types, programs, encounter types from uploaded bundles
- Concept vocabulary (what concepts this org uses)
- Terminology preferences (CHW vs ASHA, beneficiary vs mother)
- Previous bundle history
- Avni server connection details

This context is injected into every LLM call so the AI
"knows" the org without being told every time.
"""

import json
import logging
from datetime import datetime
from typing import Any

from app.config import settings

logger = logging.getLogger(__name__)

# Schema for the org_memory table — executed during init
ORG_MEMORY_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS org_memory (
    id              SERIAL PRIMARY KEY,
    org_id          TEXT NOT NULL,
    memory_type     TEXT NOT NULL,
    memory_key      TEXT NOT NULL,
    memory_value    JSONB NOT NULL DEFAULT '{}'::jsonb,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(org_id, memory_type, memory_key)
);
CREATE INDEX IF NOT EXISTS idx_org_memory_org_id ON org_memory(org_id);
CREATE INDEX IF NOT EXISTS idx_org_memory_type ON org_memory(org_id, memory_type);
"""


def _get_pool():
    """Get the database pool, returning None if unavailable."""
    try:
        from app.db import _pool
        return _pool
    except Exception:
        return None


async def ensure_schema() -> None:
    """Create the org_memory table if it doesn't exist."""
    pool = _get_pool()
    if not pool:
        return
    try:
        async with pool.acquire() as conn:
            await conn.execute(ORG_MEMORY_SCHEMA_SQL)
        logger.info("org_memory schema ready")
    except Exception as e:
        logger.error("Failed to create org_memory schema: %s", e)


async def learn_from_bundle(org_id: str, bundle_path_or_data: dict | str) -> dict[str, int]:
    """Extract and store org entities from a bundle.

    Parses subject types, programs, encounter types, concepts, and forms
    from a bundle (either a dict of parsed JSON files or a path to a bundle directory).

    Args:
        org_id: The organisation identifier.
        bundle_path_or_data: Either a dict with bundle file contents keyed by filename,
                             or a string path to a bundle directory.

    Returns:
        A summary dict with counts of extracted entities per type.
    """
    pool = _get_pool()
    if not pool:
        logger.warning("DB not connected — skipping org memory learning for org %s", org_id)
        return {"status": "skipped", "reason": "db_not_connected"}

    # If given a path, load the bundle files
    if isinstance(bundle_path_or_data, str):
        bundle_data = await _load_bundle_from_path(bundle_path_or_data)
    else:
        bundle_data = bundle_path_or_data

    counts: dict[str, int] = {}

    # Extract subject types
    subject_types = bundle_data.get("subjectTypes.json", [])
    if isinstance(subject_types, list):
        entities = [{"name": st.get("name"), "type": st.get("type", "Person"),
                      "uuid": st.get("uuid")} for st in subject_types if st.get("name")]
        await _store_memory(org_id, "subject_types", "all", entities)
        counts["subject_types"] = len(entities)

    # Extract programs
    programs = bundle_data.get("programs.json", [])
    if isinstance(programs, list):
        entities = [{"name": p.get("name"), "uuid": p.get("uuid"),
                      "colour": p.get("colour")} for p in programs if p.get("name")]
        await _store_memory(org_id, "programs", "all", entities)
        counts["programs"] = len(entities)

    # Extract encounter types
    encounter_types = bundle_data.get("encounterTypes.json", [])
    if isinstance(encounter_types, list):
        entities = [{"name": et.get("name"), "uuid": et.get("uuid"),
                      "entityEligibilityCheckRule": et.get("entityEligibilityCheckRule")}
                    for et in encounter_types if et.get("name")]
        await _store_memory(org_id, "encounter_types", "all", entities)
        counts["encounter_types"] = len(entities)

    # Extract concepts (summary — name + dataType only to keep it compact)
    concepts = bundle_data.get("concepts.json", [])
    if isinstance(concepts, list):
        concept_summaries = []
        for c in concepts:
            name = c.get("name")
            if not name:
                continue
            summary: dict[str, Any] = {
                "name": name,
                "dataType": c.get("dataType", "Text"),
                "uuid": c.get("uuid"),
            }
            # For coded concepts, include answer names
            if c.get("dataType") == "Coded" and c.get("answers"):
                summary["answers"] = [
                    a.get("answerConcept", {}).get("name", a.get("name", ""))
                    for a in c["answers"]
                    if a.get("answerConcept", {}).get("name") or a.get("name")
                ]
            concept_summaries.append(summary)
        await _store_memory(org_id, "concepts", "all", concept_summaries)
        counts["concepts"] = len(concept_summaries)

    # Extract form mappings summary
    form_mappings = bundle_data.get("formMappings.json", [])
    if isinstance(form_mappings, list):
        mapping_summaries = [
            {
                "formName": fm.get("formName"),
                "formType": fm.get("formType"),
                "subjectType": fm.get("subjectTypeUUID") or fm.get("subjectType"),
                "programName": fm.get("programName"),
                "encounterTypeName": fm.get("encounterTypeName"),
            }
            for fm in form_mappings
            if fm.get("formName") or fm.get("formType")
        ]
        await _store_memory(org_id, "form_mappings", "all", mapping_summaries)
        counts["form_mappings"] = len(mapping_summaries)

    # Store bundle history entry
    await _store_memory(org_id, "bundle_history", datetime.utcnow().isoformat(), {
        "extracted_at": datetime.utcnow().isoformat(),
        "counts": counts,
    })

    logger.info("Learned from bundle for org %s: %s", org_id, counts)
    return counts


async def learn_from_avni_org(org_id: str, auth_token: str) -> dict[str, int]:
    """Fetch current org config from Avni API and store in org memory.

    Args:
        org_id: The organisation identifier.
        auth_token: Avni AUTH-TOKEN for API access.

    Returns:
        A summary dict with counts of fetched entities.
    """
    pool = _get_pool()
    if not pool:
        return {"status": "skipped", "reason": "db_not_connected"}

    import httpx

    counts: dict[str, int] = {}
    base_url = settings.AVNI_BASE_URL
    headers = {"AUTH-TOKEN": auth_token, "Content-Type": "application/json"}

    async with httpx.AsyncClient(timeout=30.0) as client:
        # Fetch subject types
        try:
            resp = await client.get(f"{base_url}/web/subjectType", headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                subject_types = data if isinstance(data, list) else data.get("content", [])
                entities = [{"name": st.get("name"), "type": st.get("type", "Person"),
                              "uuid": st.get("uuid")} for st in subject_types if st.get("name")]
                await _store_memory(org_id, "subject_types", "all", entities)
                counts["subject_types"] = len(entities)
        except Exception as e:
            logger.warning("Failed to fetch subject types for org %s: %s", org_id, e)

        # Fetch programs
        try:
            resp = await client.get(f"{base_url}/web/program", headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                programs = data if isinstance(data, list) else data.get("content", [])
                entities = [{"name": p.get("name"), "uuid": p.get("uuid")}
                            for p in programs if p.get("name")]
                await _store_memory(org_id, "programs", "all", entities)
                counts["programs"] = len(entities)
        except Exception as e:
            logger.warning("Failed to fetch programs for org %s: %s", org_id, e)

        # Fetch encounter types
        try:
            resp = await client.get(f"{base_url}/web/encounterType", headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                enc_types = data if isinstance(data, list) else data.get("content", [])
                entities = [{"name": et.get("name"), "uuid": et.get("uuid")}
                            for et in enc_types if et.get("name")]
                await _store_memory(org_id, "encounter_types", "all", entities)
                counts["encounter_types"] = len(entities)
        except Exception as e:
            logger.warning("Failed to fetch encounter types for org %s: %s", org_id, e)

    # Store connection details
    await _store_memory(org_id, "connection", "avni_server", {
        "base_url": base_url,
        "last_synced": datetime.utcnow().isoformat(),
        "counts": counts,
    })

    logger.info("Learned from Avni org %s: %s", org_id, counts)
    return counts


async def get_org_context_prompt(org_id: str) -> str:
    """Generate a system prompt fragment with org context.

    Returns a formatted string describing the org's known entities,
    suitable for injection into a system prompt.

    Args:
        org_id: The organisation identifier.

    Returns:
        A formatted context string, or empty string if no memory exists.
    """
    pool = _get_pool()
    if not pool:
        return ""

    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT memory_type, memory_key, memory_value FROM org_memory WHERE org_id = $1",
                org_id,
            )
    except Exception as e:
        logger.error("Failed to fetch org memory for %s: %s", org_id, e)
        return ""

    if not rows:
        return ""

    # Organize memories by type
    memories: dict[str, Any] = {}
    for row in rows:
        mem_type = row["memory_type"]
        mem_value = row["memory_value"]
        if isinstance(mem_value, str):
            try:
                mem_value = json.loads(mem_value)
            except json.JSONDecodeError:
                pass
        memories[mem_type] = mem_value

    # Build the context prompt
    parts: list[str] = [f"\n## Organisation Context (auto-learned for org: {org_id})\n"]

    # Subject types
    subject_types = memories.get("subject_types", [])
    if subject_types and isinstance(subject_types, list):
        names = [st.get("name", "?") for st in subject_types[:20]]
        parts.append(f"**Subject Types:** {', '.join(names)}")

    # Programs
    programs = memories.get("programs", [])
    if programs and isinstance(programs, list):
        names = [p.get("name", "?") for p in programs[:20]]
        parts.append(f"**Programs:** {', '.join(names)}")

    # Encounter types
    enc_types = memories.get("encounter_types", [])
    if enc_types and isinstance(enc_types, list):
        names = [et.get("name", "?") for et in enc_types[:30]]
        parts.append(f"**Encounter Types:** {', '.join(names)}")

    # Concepts summary
    concepts = memories.get("concepts", [])
    if concepts and isinstance(concepts, list):
        # Group by data type for a compact summary
        by_type: dict[str, list[str]] = {}
        for c in concepts[:200]:
            dt = c.get("dataType", "Text")
            by_type.setdefault(dt, []).append(c.get("name", "?"))
        concept_lines = []
        for dt, names_list in sorted(by_type.items()):
            preview = ", ".join(names_list[:10])
            suffix = f" (+{len(names_list) - 10} more)" if len(names_list) > 10 else ""
            concept_lines.append(f"  - {dt}: {preview}{suffix}")
        parts.append(f"**Concepts ({len(concepts)} total):**")
        parts.extend(concept_lines)

    # Terminology
    terminology = memories.get("terminology", {})
    if terminology and isinstance(terminology, dict):
        term_lines = [f"  - {k} -> {v}" for k, v in terminology.items()]
        parts.append("**Org Terminology:**")
        parts.extend(term_lines)

    # Connection info
    connection = memories.get("connection", {})
    if connection and isinstance(connection, dict):
        parts.append(f"**Avni Server:** {connection.get('base_url', 'unknown')}")
        if connection.get("last_synced"):
            parts.append(f"**Last Synced:** {connection['last_synced']}")

    return "\n".join(parts)


async def update_terminology(org_id: str, term_map: dict[str, str]) -> dict:
    """Store org-specific terminology preferences.

    Args:
        org_id: The organisation identifier.
        term_map: Dict of standard_term -> org_preferred_term.
                  Example: {"CHW": "ASHA", "beneficiary": "mother"}

    Returns:
        The merged terminology dict.
    """
    pool = _get_pool()
    if not pool:
        return term_map

    # Fetch existing terminology
    existing: dict[str, str] = {}
    try:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT memory_value FROM org_memory WHERE org_id = $1 AND memory_type = 'terminology' AND memory_key = 'all'",
                org_id,
            )
            if row:
                val = row["memory_value"]
                if isinstance(val, str):
                    existing = json.loads(val)
                else:
                    existing = val
    except Exception:
        pass

    # Merge — new values override existing
    merged = {**existing, **term_map}
    await _store_memory(org_id, "terminology", "all", merged)
    return merged


async def merge_org_memories(org_id: str, new_data: dict[str, Any]) -> dict[str, int]:
    """Merge new info into org memory without losing existing data.

    Args:
        org_id: The organisation identifier.
        new_data: Dict keyed by memory_type with values to merge.
                  List values are merged by name (deduplication).
                  Dict values are shallow-merged.

    Returns:
        Counts of items per memory type after merge.
    """
    pool = _get_pool()
    if not pool:
        return {}

    counts: dict[str, int] = {}

    for mem_type, new_value in new_data.items():
        # Fetch existing
        existing_value: Any = None
        try:
            async with pool.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT memory_value FROM org_memory WHERE org_id = $1 AND memory_type = $2 AND memory_key = 'all'",
                    org_id, mem_type,
                )
                if row:
                    existing_value = row["memory_value"]
                    if isinstance(existing_value, str):
                        existing_value = json.loads(existing_value)
        except Exception:
            pass

        # Merge strategy depends on type
        if isinstance(new_value, list) and isinstance(existing_value, list):
            # Deduplicate by name
            existing_names = {item.get("name") for item in existing_value if isinstance(item, dict)}
            for item in new_value:
                if isinstance(item, dict) and item.get("name") not in existing_names:
                    existing_value.append(item)
                    existing_names.add(item.get("name"))
            merged = existing_value
        elif isinstance(new_value, dict) and isinstance(existing_value, dict):
            merged = {**existing_value, **new_value}
        else:
            merged = new_value

        await _store_memory(org_id, mem_type, "all", merged)
        counts[mem_type] = len(merged) if isinstance(merged, (list, dict)) else 1

    return counts


async def get_all_memories(org_id: str) -> dict[str, Any]:
    """Get all org memories as a dict keyed by memory_type.

    Args:
        org_id: The organisation identifier.

    Returns:
        Dict of memory_type -> memory_value.
    """
    pool = _get_pool()
    if not pool:
        return {}

    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT memory_type, memory_key, memory_value, updated_at FROM org_memory WHERE org_id = $1",
                org_id,
            )
    except Exception as e:
        logger.error("Failed to fetch org memories for %s: %s", org_id, e)
        return {}

    result: dict[str, Any] = {}
    for row in rows:
        mem_type = row["memory_type"]
        mem_value = row["memory_value"]
        if isinstance(mem_value, str):
            try:
                mem_value = json.loads(mem_value)
            except json.JSONDecodeError:
                pass
        result[mem_type] = mem_value

    return result


# ── Internal helpers ─────────────────────────────────────────────────────────


async def _store_memory(org_id: str, memory_type: str, memory_key: str, value: Any) -> None:
    """Upsert a memory entry."""
    pool = _get_pool()
    if not pool:
        return

    try:
        value_json = json.dumps(value, default=str)
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO org_memory (org_id, memory_type, memory_key, memory_value, updated_at)
                VALUES ($1, $2, $3, $4::jsonb, now())
                ON CONFLICT (org_id, memory_type, memory_key) DO UPDATE SET
                    memory_value = EXCLUDED.memory_value,
                    updated_at = now()
                """,
                org_id, memory_type, memory_key, value_json,
            )
    except Exception as e:
        logger.error("Failed to store org memory (%s/%s/%s): %s", org_id, memory_type, memory_key, e)


async def _load_bundle_from_path(bundle_path: str) -> dict[str, Any]:
    """Load bundle JSON files from a directory path."""
    import os

    bundle_data: dict[str, Any] = {}
    if not os.path.isdir(bundle_path):
        logger.warning("Bundle path does not exist: %s", bundle_path)
        return bundle_data

    for filename in os.listdir(bundle_path):
        if filename.endswith(".json"):
            filepath = os.path.join(bundle_path, filename)
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    bundle_data[filename] = json.load(f)
            except Exception as e:
                logger.warning("Failed to load bundle file %s: %s", filepath, e)

    return bundle_data

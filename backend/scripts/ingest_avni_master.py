#!/usr/bin/env python3
"""Comprehensive Avni Master Knowledge Ingestion.

Ingests knowledge from ALL Avni sources to create an AI that thinks like
an Avni creator/architect. Sources:

1. orgs-bundle/ — 18 production org bundles (concepts, forms, rules, configs)
2. avni-server-master/ — Server source code (domain models, bundle import, rules, validation)
3. avni-webapp-master/ — Web app (form designer, rule editor, bundle upload)
4. avni-client-master/ — Mobile client (rule execution, sync, form rendering)
5. avni-etl-main/ — ETL pipeline (data flow, reporting)

Usage:
    python scripts/ingest_avni_master.py \
        --database-url postgresql://samanvay@localhost:5432/avni_ai
"""

import argparse
import asyncio
import json
import logging
import os
import re
import sys
import time
from typing import Any

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_BACKEND_DIR = os.path.dirname(_SCRIPT_DIR)
sys.path.insert(0, _BACKEND_DIR)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger("ingest_avni_master")

CHUNK_SIZE = 800
CHUNK_OVERLAP = 150

BASE_DIR = "/Users/samanvay/Downloads/All/avni-ai"


# ── Helpers ──────────────────────────────────────────────────────────────────

def chunk_text(text: str, source: str, metadata: dict | None = None) -> list[dict[str, Any]]:
    """Split text into overlapping chunks with metadata."""
    chunks: list[dict[str, Any]] = []
    sections = re.split(r"(?=^#{1,4}\s)", text, flags=re.MULTILINE)
    heading = ""
    for section in sections:
        section = section.strip()
        if not section:
            continue
        hm = re.match(r"^(#{1,4}\s+.+?)$", section, re.MULTILINE)
        if hm:
            heading = hm.group(1).strip("# ").strip()
        if len(section) <= CHUNK_SIZE:
            item = {"content": section, "heading": heading, "source_file": source}
            if metadata:
                item.update(metadata)
            chunks.append(item)
        else:
            start = 0
            while start < len(section):
                end = start + CHUNK_SIZE
                item = {"content": section[start:end], "heading": heading, "source_file": source}
                if metadata:
                    item.update(metadata)
                chunks.append(item)
                start = end - CHUNK_OVERLAP
                if start >= len(section):
                    break
    return chunks


def chunk_code(text: str, source: str, language: str, metadata: dict | None = None) -> list[dict[str, Any]]:
    """Split source code into meaningful chunks."""
    chunks: list[dict[str, Any]] = []
    # Split by class/function boundaries for better semantics
    if language == "java":
        # Split on class, interface, or method declarations
        parts = re.split(r'(?=\n\s*(?:public|private|protected|static|abstract|@)\s)', text)
    elif language in ("js", "jsx", "ts"):
        # Split on function/class/export declarations
        parts = re.split(r'(?=\n(?:export |const |function |class |async function ))', text)
    else:
        parts = [text]

    for part in parts:
        part = part.strip()
        if not part or len(part) < 30:
            continue
        if len(part) <= CHUNK_SIZE * 2:
            item = {"content": part[:CHUNK_SIZE * 2], "source_file": source, "language": language}
            if metadata:
                item.update(metadata)
            chunks.append(item)
        else:
            # Further split long blocks
            start = 0
            while start < len(part):
                end = start + CHUNK_SIZE * 2
                item = {"content": part[start:end], "source_file": source, "language": language}
                if metadata:
                    item.update(metadata)
                chunks.append(item)
                start = end - CHUNK_OVERLAP
                if start >= len(part):
                    break
    return chunks


def read_json_safe(path: str) -> Any:
    """Read JSON file, return None on failure."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def read_file_safe(path: str, max_size: int = 100_000) -> str:
    """Read text file, return empty on failure or if too large."""
    try:
        size = os.path.getsize(path)
        if size > max_size:
            return ""
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()
    except Exception:
        return ""


# ── 1. ORG BUNDLES ──────────────────────────────────────────────────────────

def collect_org_bundles() -> list[dict[str, Any]]:
    """Extract knowledge from 18 production org bundles."""
    orgs_dir = os.path.join(BASE_DIR, "orgs-bundle")
    if not os.path.isdir(orgs_dir):
        logger.warning("orgs-bundle not found: %s", orgs_dir)
        return []

    items: list[dict[str, Any]] = []

    for org_name in sorted(os.listdir(orgs_dir)):
        org_path = os.path.join(orgs_dir, org_name)
        if not os.path.isdir(org_path):
            continue

        logger.info("  Processing org: %s", org_name)
        meta = {"org": org_name}

        # ── Concepts ──
        concepts = read_json_safe(os.path.join(org_path, "concepts.json"))
        if isinstance(concepts, list):
            # Extract concept patterns with full detail
            for c in concepts:
                if not isinstance(c, dict):
                    continue
                name = c.get("name", "")
                dt = c.get("dataType", "")
                if not name:
                    continue
                parts = [f"Concept '{name}' (dataType: {dt})"]
                if c.get("unit"):
                    parts.append(f"unit: {c['unit']}")
                if c.get("lowAbsolute") is not None:
                    parts.append(f"range: {c.get('lowAbsolute')}-{c.get('highAbsolute')}")
                answers = c.get("answers", [])
                if isinstance(answers, list) and answers:
                    ans_names = [a.get("answerConcept", {}).get("name", "") if isinstance(a, dict) else str(a)
                                 for a in answers[:15]]
                    ans_names = [a for a in ans_names if a]
                    if ans_names:
                        parts.append(f"options: {', '.join(ans_names)}")
                kv = c.get("keyValues", [])
                if kv:
                    parts.append(f"keyValues: {json.dumps(kv)[:200]}")

                items.append({
                    "content": f"[{org_name}] {' | '.join(parts)}",
                    "source_file": f"orgs-bundle/{org_name}/concepts.json",
                    **meta,
                })

        # ── Programs ──
        programs = read_json_safe(os.path.join(org_path, "programs.json"))
        if isinstance(programs, list):
            for p in programs:
                if not isinstance(p, dict):
                    continue
                name = p.get("name", "")
                if not name:
                    continue
                parts = [f"Program '{name}'"]
                if p.get("colour"):
                    parts.append(f"colour: {p['colour']}")
                if p.get("enrolmentEligibilityCheckDeclarativeRule"):
                    parts.append("has eligibility rule")
                if p.get("enrolmentSummaryRule"):
                    parts.append("has summary rule")
                if p.get("programSubjectLabel"):
                    parts.append(f"subjectLabel: {p['programSubjectLabel']}")
                items.append({
                    "content": f"[{org_name}] {' | '.join(parts)}",
                    "source_file": f"orgs-bundle/{org_name}/programs.json",
                    **meta,
                })

        # ── Encounter Types ──
        enc_types = read_json_safe(os.path.join(org_path, "encounterTypes.json"))
        if isinstance(enc_types, list):
            for et in enc_types:
                if not isinstance(et, dict):
                    continue
                name = et.get("name", "")
                if name:
                    items.append({
                        "content": f"[{org_name}] EncounterType '{name}'" +
                                   (f" | eligibility rule present" if et.get("encounterEligibilityCheckDeclarativeRule") else ""),
                        "source_file": f"orgs-bundle/{org_name}/encounterTypes.json",
                        **meta,
                    })

        # ── Subject Types ──
        sub_types = read_json_safe(os.path.join(org_path, "subjectTypes.json"))
        if isinstance(sub_types, list):
            for st in sub_types:
                if not isinstance(st, dict):
                    continue
                name = st.get("name", "")
                stype = st.get("type", "")
                if name:
                    parts = [f"SubjectType '{name}' (type: {stype})"]
                    if st.get("group"):
                        parts.append("isGroup: true")
                    if st.get("household"):
                        parts.append("isHousehold: true")
                    if st.get("registrationEligibilityCheckDeclarativeRule"):
                        parts.append("has registration eligibility rule")
                    items.append({
                        "content": f"[{org_name}] {' | '.join(parts)}",
                        "source_file": f"orgs-bundle/{org_name}/subjectTypes.json",
                        **meta,
                    })

        # ── Form Mappings ──
        fm = read_json_safe(os.path.join(org_path, "formMappings.json"))
        if isinstance(fm, list):
            for mapping in fm:
                if not isinstance(mapping, dict):
                    continue
                parts = [f"FormMapping"]
                if mapping.get("formName"):
                    parts.append(f"form: {mapping['formName']}")
                if mapping.get("formType"):
                    parts.append(f"formType: {mapping['formType']}")
                if mapping.get("subjectTypeUUID"):
                    parts.append(f"subjectType: {mapping.get('subjectTypeName', mapping['subjectTypeUUID'][:8])}")
                if mapping.get("programUUID"):
                    parts.append(f"program: {mapping.get('programName', mapping['programUUID'][:8])}")
                if mapping.get("encounterTypeUUID"):
                    parts.append(f"encounterType: {mapping.get('encounterTypeName', mapping['encounterTypeUUID'][:8])}")
                items.append({
                    "content": f"[{org_name}] {' | '.join(parts)}",
                    "source_file": f"orgs-bundle/{org_name}/formMappings.json",
                    **meta,
                })

        # ── Forms (structure only, not full JSON) ──
        forms_dir = os.path.join(org_path, "forms")
        if os.path.isdir(forms_dir):
            for form_file in os.listdir(forms_dir):
                if not form_file.endswith(".json"):
                    continue
                form_data = read_json_safe(os.path.join(forms_dir, form_file))
                if not isinstance(form_data, dict):
                    continue
                fname = form_data.get("name", form_file)
                ftype = form_data.get("formType", "")
                groups = form_data.get("formElementGroups", [])
                total_elements = sum(len(g.get("formElements", [])) for g in groups if isinstance(g, dict))
                has_rules = bool(form_data.get("decisionRule") or form_data.get("visitScheduleRule") or form_data.get("validationRule"))

                parts = [f"Form '{fname}' (formType: {ftype})"]
                parts.append(f"{len(groups)} groups, {total_elements} elements")
                if has_rules:
                    rule_types = []
                    if form_data.get("decisionRule"):
                        rule_types.append("decision")
                    if form_data.get("visitScheduleRule"):
                        rule_types.append("visitSchedule")
                    if form_data.get("validationRule"):
                        rule_types.append("validation")
                    if form_data.get("checklistsRule"):
                        rule_types.append("checklist")
                    parts.append(f"rules: {', '.join(rule_types)}")

                items.append({
                    "content": f"[{org_name}] {' | '.join(parts)}",
                    "source_file": f"orgs-bundle/{org_name}/forms/{form_file}",
                    **meta,
                })

                # Extract actual rule code if present
                for rule_key in ("decisionRule", "visitScheduleRule", "validationRule", "checklistsRule"):
                    rule_code = form_data.get(rule_key, "")
                    if rule_code and len(rule_code) > 20:
                        items.append({
                            "content": f"[{org_name}] {rule_key} for form '{fname}':\n{rule_code[:1500]}",
                            "source_file": f"orgs-bundle/{org_name}/forms/{form_file}",
                            "rule_type": rule_key,
                            **meta,
                        })

                # Extract declarative rules from form elements
                for group in groups:
                    if not isinstance(group, dict):
                        continue
                    for elem in group.get("formElements", []):
                        if not isinstance(elem, dict):
                            continue
                        decl_rule = elem.get("declarativeRule")
                        if decl_rule and isinstance(decl_rule, list) and len(decl_rule) > 0:
                            concept_name = elem.get("concept", {}).get("name", "unknown")
                            items.append({
                                "content": f"[{org_name}] Declarative skip logic for '{concept_name}' in form '{fname}':\n{json.dumps(decl_rule, indent=None)[:1000]}",
                                "source_file": f"orgs-bundle/{org_name}/forms/{form_file}",
                                "rule_type": "declarativeRule",
                                **meta,
                            })

        # ── Groups & Privileges ──
        groups_data = read_json_safe(os.path.join(org_path, "groups.json"))
        privs = read_json_safe(os.path.join(org_path, "groupPrivilege.json"))
        if isinstance(groups_data, list):
            group_names = [g.get("name", "") for g in groups_data if isinstance(g, dict)]
            if group_names:
                items.append({
                    "content": f"[{org_name}] User groups: {', '.join(group_names)}",
                    "source_file": f"orgs-bundle/{org_name}/groups.json",
                    **meta,
                })
        if isinstance(privs, list) and privs:
            items.append({
                "content": f"[{org_name}] {len(privs)} privilege entries configured",
                "source_file": f"orgs-bundle/{org_name}/groupPrivilege.json",
                **meta,
            })

        # ── Report Cards & Dashboards ──
        cards = read_json_safe(os.path.join(org_path, "reportCard.json"))
        if isinstance(cards, list):
            for card in cards[:20]:
                if not isinstance(card, dict):
                    continue
                card_name = card.get("name", "")
                if card_name:
                    items.append({
                        "content": f"[{org_name}] ReportCard '{card_name}'" +
                                   (f" | standardReportCardType: {card['standardReportCardType']}" if card.get("standardReportCardType") else ""),
                        "source_file": f"orgs-bundle/{org_name}/reportCard.json",
                        **meta,
                    })

    logger.info("  Org bundles: %d items collected", len(items))
    return items


# ── 2. SERVER SOURCE CODE ───────────────────────────────────────────────────

def collect_server_source() -> list[dict[str, Any]]:
    """Extract key knowledge from avni-server Java source code."""
    server_dir = os.path.join(BASE_DIR, "avni-server-master")
    if not os.path.isdir(server_dir):
        logger.warning("avni-server not found: %s", server_dir)
        return []

    items: list[dict[str, Any]] = []

    # Key files to ingest (curated for maximum learning value)
    key_files = [
        # Bundle import — THE most critical file
        "avni-server-api/src/main/java/org/avni/server/importer/batch/zip/BundleZipFileImporter.java",
        # Domain models
        "avni-server-data/src/main/java/org/avni/server/domain/Concept.java",
        "avni-server-data/src/main/java/org/avni/server/application/Form.java",
        "avni-server-data/src/main/java/org/avni/server/application/FormElement.java",
        "avni-server-data/src/main/java/org/avni/server/application/FormElementGroup.java",
        "avni-server-data/src/main/java/org/avni/server/application/FormMapping.java",
        "avni-server-data/src/main/java/org/avni/server/domain/Program.java",
        "avni-server-data/src/main/java/org/avni/server/domain/ProgramEnrolment.java",
        "avni-server-data/src/main/java/org/avni/server/domain/ProgramEncounter.java",
        "avni-server-data/src/main/java/org/avni/server/domain/EncounterType.java",
        "avni-server-data/src/main/java/org/avni/server/domain/SubjectType.java",
        "avni-server-data/src/main/java/org/avni/server/domain/Encounter.java",
        "avni-server-data/src/main/java/org/avni/server/domain/Individual.java",
        "avni-server-data/src/main/java/org/avni/server/domain/ConceptAnswer.java",
        "avni-server-data/src/main/java/org/avni/server/domain/ConceptDataType.java",
        "avni-server-data/src/main/java/org/avni/server/domain/GroupPrivilege.java",
        "avni-server-data/src/main/java/org/avni/server/domain/Dashboard.java",
        "avni-server-data/src/main/java/org/avni/server/domain/ReportCard.java",
        "avni-server-data/src/main/java/org/avni/server/application/FormType.java",
        # Services — business logic
        "avni-server-api/src/main/java/org/avni/server/service/ConceptService.java",
        "avni-server-api/src/main/java/org/avni/server/service/FormService.java",
        "avni-server-api/src/main/java/org/avni/server/service/FormMappingService.java",
        "avni-server-api/src/main/java/org/avni/server/service/RuleService.java",
        "avni-server-api/src/main/java/org/avni/server/service/EnhancedValidationService.java",
        "avni-server-api/src/main/java/org/avni/server/service/RuleDependencyService.java",
        "avni-server-api/src/main/java/org/avni/server/service/ProgramEnrolmentService.java",
        "avni-server-api/src/main/java/org/avni/server/service/EncounterService.java",
        "avni-server-api/src/main/java/org/avni/server/service/IndividualService.java",
        "avni-server-api/src/main/java/org/avni/server/service/GroupPrivilegeService.java",
        # Controllers — API contracts
        "avni-server-api/src/main/java/org/avni/server/web/FormController.java",
        "avni-server-api/src/main/java/org/avni/server/web/ConceptController.java",
        "avni-server-api/src/main/java/org/avni/server/web/FormMappingController.java",
        "avni-server-api/src/main/java/org/avni/server/web/RuleController.java",
        "avni-server-api/src/main/java/org/avni/server/web/ImplementationController.java",
        "avni-server-api/src/main/java/org/avni/server/web/SubjectTypeController.java",
        "avni-server-api/src/main/java/org/avni/server/web/ProgramController.java",
        "avni-server-api/src/main/java/org/avni/server/web/EncounterTypeController.java",
        # Rule server
        "avni-rule-server/src/main/java/org/avni/ruleServer/RuleService.java",
        # Bundle handling
        "avni-server-api/src/main/java/org/avni/server/importer/batch/zip/BundleZip.java",
        "avni-server-api/src/main/java/org/avni/server/importer/batch/zip/BundleFile.java",
        "avni-server-api/src/main/java/org/avni/server/importer/batch/zip/BundleFolder.java",
    ]

    for rel_path in key_files:
        full_path = os.path.join(server_dir, rel_path)
        content = read_file_safe(full_path)
        if not content:
            continue
        chunks = chunk_code(content, f"avni-server/{rel_path}", "java", {"component": "server"})
        items.extend(chunks)

    # Also ingest the DB schema doc
    schema_path = os.path.join(server_dir, "AVNI_DB_SCHEMA_FULL.md")
    schema = read_file_safe(schema_path, max_size=200_000)
    if schema:
        items.extend(chunk_text(schema, "avni-server/AVNI_DB_SCHEMA_FULL.md", {"component": "server"}))

    # Architecture doc
    arch_path = os.path.join(server_dir, "ArchitectureDocumentRecord.md")
    arch = read_file_safe(arch_path)
    if arch:
        items.extend(chunk_text(arch, "avni-server/ArchitectureDocumentRecord.md", {"component": "server"}))

    logger.info("  Server source: %d items collected", len(items))
    return items


# ── 3. WEBAPP SOURCE CODE ───────────────────────────────────────────────────

def collect_webapp_source() -> list[dict[str, Any]]:
    """Extract key knowledge from avni-webapp React source."""
    webapp_dir = os.path.join(BASE_DIR, "avni-webapp-master", "src")
    if not os.path.isdir(webapp_dir):
        logger.warning("avni-webapp not found: %s", webapp_dir)
        return []

    items: list[dict[str, Any]] = []

    # Key files for understanding form design, rules, and bundle upload
    key_files = [
        "formDesigner/common/FormDesignerHandlers.jsx",
        "formDesigner/common/SampleRule.js",
        "formDesigner/components/FormElementDetails.jsx",
        "formDesigner/components/FormElement.jsx",
        "formDesigner/components/DeclarativeRuleEditor.jsx",
        "formDesigner/components/FormDesigner.jsx",
        "formDesigner/components/FormSettings.jsx",
        "adminApp/WorklistUpdationRule.jsx",
        "adminApp/components/CreateEditFilters.jsx",
        "adminApp/domain/formMapping.js",
        "upload/api.js",
        "upload/sagas.js",
        "common/adapters.js",
        "dataEntryApp/services/RuleEvaluationService.js",
    ]

    for rel_path in key_files:
        full_path = os.path.join(webapp_dir, rel_path)
        content = read_file_safe(full_path, max_size=80_000)
        if not content:
            continue
        lang = "jsx" if rel_path.endswith(".jsx") else "js"
        chunks = chunk_code(content, f"avni-webapp/{rel_path}", lang, {"component": "webapp"})
        items.extend(chunks)

    # Also scan for any rule-related files we might have missed
    for root, dirs, files in os.walk(webapp_dir):
        dirs[:] = [d for d in dirs if d not in ("node_modules", ".git", "build", "dist", "__tests__")]
        for fname in files:
            if "rule" in fname.lower() and fname.endswith((".js", ".jsx", ".ts", ".tsx")):
                rel = os.path.relpath(os.path.join(root, fname), os.path.join(BASE_DIR, "avni-webapp-master"))
                full_path = os.path.join(root, fname)
                if any(rel.endswith(kf) for kf in key_files):
                    continue  # Already processed
                content = read_file_safe(full_path, max_size=50_000)
                if content:
                    lang = "jsx" if fname.endswith((".jsx", ".tsx")) else "js"
                    chunks = chunk_code(content, f"avni-webapp/{rel}", lang, {"component": "webapp"})
                    items.extend(chunks)

    logger.info("  Webapp source: %d items collected", len(items))
    return items


# ── 4. CLIENT SOURCE CODE ───────────────────────────────────────────────────

def collect_client_source() -> list[dict[str, Any]]:
    """Extract key knowledge from avni-client React Native source."""
    client_dir = os.path.join(BASE_DIR, "avni-client-master", "packages", "openchs-android", "src")
    if not os.path.isdir(client_dir):
        logger.warning("avni-client not found: %s", client_dir)
        return []

    items: list[dict[str, Any]] = []

    # Key service files for understanding rule execution, sync, and form rendering
    key_files = [
        "service/RuleService.js",
        "service/RuleEvaluationService.js",
        "service/SyncService.js",
        "service/FormMappingService.js",
        "service/ConceptService.js",
        "service/ProgramEnrolmentService.js",
        "service/ProgramEncounterService.js",
        "service/EncounterService.js",
        "service/IndividualService.js",
        "service/EntitySyncStatusService.js",
        "framework/db/RealmFactory.js",
        "framework/http/requests.js",
        "action/reducer.js",
        "views/form/formElement/AbstractFormElement.js",
        "views/form/FormElementGroup.js",
    ]

    for rel_path in key_files:
        full_path = os.path.join(client_dir, rel_path)
        content = read_file_safe(full_path, max_size=50_000)
        if not content:
            continue
        chunks = chunk_code(content, f"avni-client/{rel_path}", "js", {"component": "client"})
        items.extend(chunks)

    # Scan models for data structure understanding
    models_dir = os.path.join(client_dir, "models")
    if os.path.isdir(models_dir):
        for fname in os.listdir(models_dir):
            if fname.endswith(".js") and not fname.startswith("test"):
                content = read_file_safe(os.path.join(models_dir, fname), max_size=30_000)
                if content and len(content) > 100:
                    chunks = chunk_code(content, f"avni-client/models/{fname}", "js", {"component": "client"})
                    items.extend(chunks)

    logger.info("  Client source: %d items collected", len(items))
    return items


# ── 5. ETL SOURCE CODE ──────────────────────────────────────────────────────

def collect_etl_source() -> list[dict[str, Any]]:
    """Extract key knowledge from avni-etl."""
    etl_dir = os.path.join(BASE_DIR, "avni-etl-main", "src", "main", "java", "org", "avniproject", "etl")
    if not os.path.isdir(etl_dir):
        logger.warning("avni-etl not found: %s", etl_dir)
        return []

    items: list[dict[str, Any]] = []

    # Collect all Java files
    for root, dirs, files in os.walk(etl_dir):
        for fname in files:
            if fname.endswith(".java"):
                full_path = os.path.join(root, fname)
                content = read_file_safe(full_path, max_size=30_000)
                if content and len(content) > 100:
                    rel = os.path.relpath(full_path, os.path.join(BASE_DIR, "avni-etl-main"))
                    chunks = chunk_code(content, f"avni-etl/{rel}", "java", {"component": "etl"})
                    items.extend(chunks)

    logger.info("  ETL source: %d items collected", len(items))
    return items


# ── Main Ingestion ──────────────────────────────────────────────────────────

async def run_ingestion(database_url: str, batch_size: int) -> None:
    """Run the full Avni Master knowledge ingestion."""
    from app.services.rag.embeddings import EmbeddingClient
    from app.services.rag.vector_store import VectorStore
    from app.services.rag.contextual_retrieval import ContextualRetrieval

    # Collect all items
    logger.info("Collecting knowledge from all Avni sources...")
    start = time.time()

    all_items: dict[str, list[dict[str, Any]]] = {}

    logger.info("1/5: Collecting org bundles...")
    all_items["org_bundles"] = collect_org_bundles()

    logger.info("2/5: Collecting server source...")
    all_items["server_code"] = collect_server_source()

    logger.info("3/5: Collecting webapp source...")
    all_items["webapp_code"] = collect_webapp_source()

    logger.info("4/5: Collecting client source...")
    all_items["client_code"] = collect_client_source()

    logger.info("5/5: Collecting ETL source...")
    all_items["etl_code"] = collect_etl_source()

    total_items = sum(len(v) for v in all_items.values())
    collect_time = time.time() - start
    logger.info("Collection complete: %d items in %.1fs", total_items, collect_time)

    for name, items in all_items.items():
        logger.info("  %s: %d items", name, len(items))

    # Initialize pipeline
    embedding_client = EmbeddingClient()
    vector_store = VectorStore(dsn=database_url, embedding_dimension=embedding_client.dimension)
    await vector_store.initialize()

    cr = ContextualRetrieval(
        claude_client=None,
        embedding_client=embedding_client,
        vector_store=vector_store,
    )

    # Ingest each collection
    ingest_start = time.time()
    stats: dict[str, int] = {}

    for collection_name, items in all_items.items():
        if not items:
            continue
        logger.info("Ingesting %s (%d items)...", collection_name, len(items))
        count = await cr.ingest_collection(
            collection_name, items, "content",
            source_file=collection_name,
            batch_size=batch_size,
            use_context=False,
        )
        stats[collection_name] = count

    ingest_time = time.time() - ingest_start
    total = sum(stats.values())

    print(f"\n{'=' * 60}")
    print(f"  AVNI MASTER KNOWLEDGE INGESTION COMPLETE")
    print(f"{'=' * 60}")
    print(f"Total chunks: {total:,}")
    print(f"Collection time: {collect_time:.1f}s")
    print(f"Ingestion time: {ingest_time:.1f}s")
    print(f"Throughput: {total / max(ingest_time, 0.1):.0f} chunks/sec")
    print()
    print("Collections:")
    for coll, count in sorted(stats.items(), key=lambda x: -x[1]):
        print(f"  {coll:20s} {count:6,d} chunks")
    print()

    await vector_store.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Avni Master Knowledge Ingestion")
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL", ""), help="PostgreSQL URL")
    parser.add_argument("--batch-size", type=int, default=50)
    args = parser.parse_args()

    if not args.database_url:
        print("ERROR: No database URL. Set DATABASE_URL or use --database-url.", file=sys.stderr)
        sys.exit(1)

    asyncio.run(run_ingestion(args.database_url, args.batch_size))


if __name__ == "__main__":
    main()

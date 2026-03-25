"""Knowledge ingestion pipeline for the Avni AI Platform.

Loads all knowledge sources from the training data directory and ingests
them into the pgvector-backed RAG pipeline. Each source becomes a
"collection" in the vector store:

    concepts     -- 4,949 concept patterns (field definitions)
    forms        -- 280 form patterns across 6 organizations
    rules        -- 132+ rule templates (JavaScript)
    transcripts  -- Video tutorial transcript chunks
    support      -- Troubleshooting and support patterns
    knowledge    -- Built-in Avni data model knowledge
    srs_examples -- Bundle generation guide and SRS patterns
"""

import json
import logging
import os
import re
from typing import Any

from app.services.rag.contextual_retrieval import ContextualRetrieval

logger = logging.getLogger(__name__)

# Chunk size for splitting long text (transcripts, guides)
_CHUNK_SIZE = 800
_CHUNK_OVERLAP = 150


class KnowledgeIngestion:
    """Ingest all Avni knowledge collections into the RAG pipeline.

    Processes each data source, normalizes content into searchable text chunks,
    and passes them through ContextualRetrieval for embedding + storage.
    """

    def __init__(self, contextual_retrieval: ContextualRetrieval) -> None:
        self.cr = contextual_retrieval

    async def ingest_all(
        self,
        data_dir: str,
        use_context: bool = True,
        batch_size: int = 50,
    ) -> dict[str, int]:
        """Ingest all knowledge collections.

        Args:
            data_dir: Path to app/knowledge/data/ directory.
            use_context: If True, generate contextual prefixes using Claude
                         (slower, better retrieval quality). If False, skip
                         context generation (faster, for development).
            batch_size: Items per batch for embedding + insertion.

        Returns:
            Dict mapping collection name to number of chunks ingested.
        """
        stats: dict[str, int] = {}

        logger.info(
            "Starting knowledge ingestion from '%s' (contextual=%s)",
            data_dir, use_context,
        )

        # 1. Concepts (4,949)
        stats["concepts"] = await self._ingest_concepts(data_dir, use_context, batch_size)

        # 2. Forms (280)
        stats["forms"] = await self._ingest_forms(data_dir, use_context, batch_size)

        # 3. Rules (132+)
        stats["rules"] = await self._ingest_rules(data_dir, use_context, batch_size)

        # 4. Video transcripts
        stats["transcripts"] = await self._ingest_transcripts(data_dir, use_context, batch_size)

        # 5. Support patterns (built-in)
        stats["support"] = await self._ingest_support_patterns(use_context, batch_size)

        # 6. Built-in Avni knowledge
        stats["knowledge"] = await self._ingest_builtin_knowledge(use_context, batch_size)

        # 7. SRS / bundle generation guide
        stats["srs_examples"] = await self._ingest_srs_examples(data_dir, use_context, batch_size)

        total = sum(stats.values())
        logger.info("Ingestion complete: %d total chunks across %d collections", total, len(stats))
        for coll, count in stats.items():
            logger.info("  %s: %d chunks", coll, count)

        return stats

    # ------------------------------------------------------------------
    # Concepts
    # ------------------------------------------------------------------

    async def _ingest_concepts(
        self, data_dir: str, use_context: bool, batch_size: int
    ) -> int:
        """Ingest concept patterns. Each concept becomes one chunk."""
        concepts_file = os.path.join(data_dir, "concept_patterns.json")
        if not os.path.exists(concepts_file):
            logger.warning("Concepts file not found: %s", concepts_file)
            return 0

        with open(concepts_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        if not isinstance(data, dict):
            return 0

        items: list[dict[str, Any]] = []
        for data_type, concepts in data.items():
            if not isinstance(concepts, list):
                continue
            for concept in concepts:
                name = concept.get("name", "")
                uuid_val = concept.get("uuid", "")
                org = concept.get("org", "")
                answers = concept.get("answers", 0)

                content = f"Concept: {name} | Type: {data_type}"
                if concept.get("unit"):
                    content += f" | Unit: {concept['unit']}"
                if isinstance(answers, list) and answers:
                    answer_names = [
                        a.get("name", "") for a in answers if isinstance(a, dict) and a.get("name")
                    ]
                    if answer_names:
                        content += f" | Options: {', '.join(answer_names[:20])}"
                elif isinstance(answers, int) and answers > 0:
                    content += f" | {answers} answer options"

                items.append({
                    "content": content,
                    "name": name,
                    "dataType": data_type,
                    "uuid": uuid_val,
                    "org": org,
                    "source_file": "concept_patterns.json",
                })

        return await self.cr.ingest_collection(
            "concepts", items, "content",
            source_file="concept_patterns.json",
            batch_size=batch_size,
            use_context=use_context,
        )

    # ------------------------------------------------------------------
    # Forms
    # ------------------------------------------------------------------

    async def _ingest_forms(
        self, data_dir: str, use_context: bool, batch_size: int
    ) -> int:
        """Ingest form patterns. Each form becomes one chunk."""
        forms_file = os.path.join(data_dir, "form_patterns.json")
        if not os.path.exists(forms_file):
            logger.warning("Forms file not found: %s", forms_file)
            return 0

        with open(forms_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        if not isinstance(data, list):
            return 0

        items: list[dict[str, Any]] = []
        for form in data:
            name = form.get("name", "")
            form_type = form.get("formType", "")
            org = form.get("org", "")
            group_count = form.get("groupCount", 0)
            element_count = form.get("elementCount", 0)

            features: list[str] = []
            if form.get("hasDecisionRule"):
                features.append("decision rule")
            if form.get("hasValidationRule"):
                features.append("validation rule")
            if form.get("hasVisitScheduleRule"):
                features.append("visit scheduling rule")
            if form.get("hasSkipLogic"):
                features.append("skip logic")
            if form.get("hasQuestionGroups"):
                features.append("question groups")

            feature_str = ", ".join(features) if features else "none"
            content = (
                f"Form: {name} | Type: {form_type} | Org: {org} | "
                f"{group_count} groups, {element_count} elements | "
                f"Rules: {feature_str}"
            )

            items.append({
                "content": content,
                "name": name,
                "formType": form_type,
                "org": org,
                "groupCount": group_count,
                "elementCount": element_count,
                "features": features,
                "source_file": "form_patterns.json",
            })

        return await self.cr.ingest_collection(
            "forms", items, "content",
            source_file="form_patterns.json",
            batch_size=batch_size,
            use_context=use_context,
        )

    # ------------------------------------------------------------------
    # Rules
    # ------------------------------------------------------------------

    async def _ingest_rules(
        self, data_dir: str, use_context: bool, batch_size: int
    ) -> int:
        """Ingest rule templates. Each rule becomes one chunk."""
        rules_file = os.path.join(data_dir, "rule_templates.json")
        if not os.path.exists(rules_file):
            logger.warning("Rules file not found: %s", rules_file)
            return 0

        with open(rules_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        if not isinstance(data, list):
            return 0

        items: list[dict[str, Any]] = []
        for rule in data:
            rule_type = rule.get("type", "unknown")
            form_name = rule.get("formName", "")
            form_type = rule.get("formType", "")
            org = rule.get("org", "")
            code = rule.get("rule", "")

            # Truncate very long rule code for embedding (keep first 1500 chars)
            code_preview = code[:1500] if code else ""

            content = (
                f"Rule template ({rule_type}) for form '{form_name}' "
                f"(formType: {form_type}, org: {org}):\n{code_preview}"
            )

            items.append({
                "content": content,
                "ruleType": rule_type,
                "formName": form_name,
                "formType": form_type,
                "org": org,
                "source_file": "rule_templates.json",
            })

        return await self.cr.ingest_collection(
            "rules", items, "content",
            source_file="rule_templates.json",
            batch_size=batch_size,
            use_context=use_context,
        )

    # ------------------------------------------------------------------
    # Transcripts
    # ------------------------------------------------------------------

    async def _ingest_transcripts(
        self, data_dir: str, use_context: bool, batch_size: int
    ) -> int:
        """Ingest video transcript chunks."""
        items: list[dict[str, Any]] = []

        for filename in ("video1_english.md", "video2_english.md"):
            filepath = os.path.join(data_dir, filename)
            if not os.path.exists(filepath):
                logger.warning("Transcript file not found: %s", filepath)
                continue

            with open(filepath, "r", encoding="utf-8") as f:
                text = f.read()

            chunks = self._chunk_markdown(text, filename)
            items.extend(chunks)

        if not items:
            return 0

        return await self.cr.ingest_collection(
            "transcripts", items, "content",
            source_file="video_transcripts",
            batch_size=batch_size,
            use_context=use_context,
        )

    # ------------------------------------------------------------------
    # Support patterns
    # ------------------------------------------------------------------

    async def _ingest_support_patterns(
        self, use_context: bool, batch_size: int
    ) -> int:
        """Ingest built-in support/troubleshooting patterns."""
        items: list[dict[str, Any]] = [
            {
                "content": (
                    "Sync failure due to concept UUID mismatch: When a concept UUID in the "
                    "form JSON doesn't match the concepts.json, sync will fail with a "
                    "'Concept not found' error. Fix: Regenerate the bundle ensuring concept "
                    "UUIDs are consistent across all files."
                ),
                "category": "sync_error",
                "source_file": "builtin",
            },
            {
                "content": (
                    "Form not showing on mobile: Check 1) FormMapping exists for the correct "
                    "subjectType and program/encounterType combination. 2) User's group has "
                    "the required privilege (RegisterSubject, PerformVisit, etc.). 3) The form "
                    "is not voided. 4) Sync is complete."
                ),
                "category": "form_visibility",
                "source_file": "builtin",
            },
            {
                "content": (
                    "Bundle upload error 'Entity not found': This means a referenced entity "
                    "(concept, program, encounterType, subjectType) hasn't been created yet. "
                    "The zip file entries must be in the correct dependency order. Ensure "
                    "concepts.json comes before forms, and forms come before formMappings."
                ),
                "category": "bundle_upload",
                "source_file": "builtin",
            },
            {
                "content": (
                    "Duplicate concept name error: Avni requires unique concept names. If two "
                    "forms use different concepts with the same name, rename one to be unique "
                    "(e.g., 'Hb' vs 'Hb TB'). Answer concepts (dataType: NA) also share the "
                    "global namespace."
                ),
                "category": "concept_collision",
                "source_file": "builtin",
            },
            {
                "content": (
                    "Data not appearing in reports: Check 1) The concept used in the report "
                    "matches the exact concept name and UUID from the form. 2) The report card "
                    "query filters are correct. 3) Data has been synced to the server. "
                    "4) User has ViewSubject/ViewVisit privileges."
                ),
                "category": "reporting",
                "source_file": "builtin",
            },
            {
                "content": (
                    "Visit not being scheduled: Check 1) The visit scheduling rule is correctly "
                    "defined. 2) The encounterType exists and has a form mapping. 3) The program "
                    "enrollment is active (not exited). 4) The rule conditions are met. "
                    "5) Check for JavaScript errors in the rule."
                ),
                "category": "visit_scheduling",
                "source_file": "builtin",
            },
            {
                "content": (
                    "Skip logic not working: Check 1) The rule references the correct concept "
                    "name or UUID. 2) The FormElementStatusHandler is returning the correct "
                    "FormElementStatus. 3) The observation value comparison uses the right type "
                    "(string vs concept name). 4) Check browser console for JavaScript errors."
                ),
                "category": "skip_logic",
                "source_file": "builtin",
            },
            {
                "content": (
                    "App crashing on form open: Check 1) All concepts referenced in the form "
                    "exist in concepts.json. 2) No circular references in question groups. "
                    "3) The form JSON is valid and well-formed. 4) Check for excessively large "
                    "forms (>200 elements)."
                ),
                "category": "app_crash",
                "source_file": "builtin",
            },
            {
                "content": (
                    "Avni sync works offline-first. Data entered on mobile is stored in local "
                    "SQLite and synced to the server when network is available. Sync issues can "
                    "arise from: 1) Network timeouts 2) Server-side validation failures "
                    "3) Concept UUID mismatches 4) Missing form mappings 5) Large media files. "
                    "Check sync telemetry at /api/syncTelemetry for diagnostics."
                ),
                "category": "sync_overview",
                "source_file": "builtin",
            },
        ]

        return await self.cr.ingest_collection(
            "support", items, "content",
            source_file="builtin",
            batch_size=batch_size,
            use_context=use_context,
        )

    # ------------------------------------------------------------------
    # Built-in Avni knowledge
    # ------------------------------------------------------------------

    async def _ingest_builtin_knowledge(
        self, use_context: bool, batch_size: int
    ) -> int:
        """Ingest built-in Avni data model and domain knowledge."""
        items: list[dict[str, Any]] = [
            {
                "content": (
                    "SubjectType defines the entity being tracked (e.g., Individual, "
                    "Household, Group). Properties: name, type (Person/Individual/Household/"
                    "Group), uuid, active. A Person subject type enables first/middle/last "
                    "name and date of birth fields."
                ),
                "topic": "data_model",
                "source_file": "builtin",
            },
            {
                "content": (
                    "Program represents a longitudinal tracking workflow (e.g., Pregnancy "
                    "Program, TB Program). Properties: name, uuid, colour, "
                    "enrolmentEligibilityCheckRule. Subjects are enrolled in programs and "
                    "can have multiple encounters within each program."
                ),
                "topic": "data_model",
                "source_file": "builtin",
            },
            {
                "content": (
                    "EncounterType defines a visit type, either within a program "
                    "(ProgramEncounter) or standalone (Encounter/GeneralEncounter). "
                    "Properties: name, uuid, active. Each encounter type is linked to forms "
                    "via FormMappings."
                ),
                "topic": "data_model",
                "source_file": "builtin",
            },
            {
                "content": (
                    "Form is a collection of FormElementGroups, each containing FormElements. "
                    "formType can be: IndividualProfile, ProgramEnrolment, ProgramExit, "
                    "ProgramEncounter, ProgramEncounterCancellation, Encounter, "
                    "IndividualEncounterCancellation. Each FormElement references a Concept."
                ),
                "topic": "data_model",
                "source_file": "builtin",
            },
            {
                "content": (
                    "Concept is a reusable field definition. dataType can be: Text, Numeric, "
                    "Date, DateTime, Time, Coded, Image, Notes, NA, Id, Video, Audio, File, "
                    "Location, PhoneNumber, GroupAffiliation, Subject, Encounter, "
                    "QuestionGroup, Duration. Coded concepts have an 'answers' array of "
                    "answer concepts (dataType: NA). Numeric concepts can have unit, "
                    "lowAbsolute, highAbsolute."
                ),
                "topic": "data_model",
                "source_file": "builtin",
            },
            {
                "content": (
                    "FormMapping links a form to a SubjectType and optionally a Program and "
                    "EncounterType. This determines when and where a form appears in the app. "
                    "Properties: formUUID, subjectTypeUUID, programUUID, encounterTypeUUID, "
                    "formType."
                ),
                "topic": "data_model",
                "source_file": "builtin",
            },
            {
                "content": (
                    "Groups define user roles (e.g., Everyone, Admin, Supervisor, MLHW). "
                    "GroupPrivileges grant permissions per group per entity type. Privilege "
                    "types: ViewSubject, RegisterSubject, EditSubject, VoidSubject, "
                    "EnrolSubject, ViewEnrolmentDetails, EditEnrolmentDetails, ExitEnrolment, "
                    "ViewVisit, ScheduleVisit, PerformVisit, EditVisit, CancelVisit, "
                    "ViewChecklist, EditChecklist."
                ),
                "topic": "data_model",
                "source_file": "builtin",
            },
            {
                "content": (
                    "The Avni implementation bundle is a zip file containing JSON "
                    "configuration files that must be uploaded in a specific dependency order: "
                    "1. addressLevelTypes 2. subjectTypes 3. operationalSubjectTypes "
                    "4. encounterTypes 5. operationalEncounterTypes 6. programs "
                    "7. operationalPrograms 8. concepts 9. forms/* 10. formMappings "
                    "11. groups 12. groupPrivilege. Violating this order causes upload "
                    "failures due to missing references."
                ),
                "topic": "bundle",
                "source_file": "builtin",
            },
            {
                "content": (
                    "The SRS (Scoping & Requirement Specification) document has 9 tabs: "
                    "1. Help & Status Tracker 2. Program Summary 3. Program Detail "
                    "4. User Persona 5. W3H (What/When/Who/How) 6. Forms "
                    "7. Visit Scheduling 8. Offline Dashboard Cards 9. Permissions. "
                    "The W3H tab is the heart of the scoping document."
                ),
                "topic": "srs",
                "source_file": "builtin",
            },
            {
                "content": (
                    "Avni rules are written in JavaScript and run on the mobile app. Types: "
                    "1. Skip logic rules (show/hide form elements based on conditions) "
                    "2. Calculated/computed fields (auto-compute values like BMI, age) "
                    "3. Validation rules (enforce data quality) "
                    "4. Decision rules (set observations based on calculations) "
                    "5. Visit scheduling rules (auto-schedule follow-up encounters) "
                    "6. Eligibility rules (determine program enrollment eligibility) "
                    "7. Summary rules (display computed summaries on dashboards)."
                ),
                "topic": "rules",
                "source_file": "builtin",
            },
            {
                "content": (
                    "Common Avni concepts across implementations: "
                    "Height (Numeric, cm), Weight (Numeric, kg), MUAC (Numeric, cm), "
                    "Hb (Numeric, g/dL), BMI (Numeric, computed), "
                    "Gender (Coded: Male/Female), Date of Birth (Date), "
                    "BP Systolic (Numeric, mmHg), BP Diastolic (Numeric, mmHg)."
                ),
                "topic": "concepts",
                "source_file": "builtin",
            },
            {
                "content": (
                    "Avni supports multiple sectors: "
                    "MCH (Maternal & Child Health): pregnancy tracking, immunization, growth "
                    "monitoring. WASH (Water & Sanitation): water source monitoring, toilet "
                    "construction tracking. Education: student enrollment, attendance, "
                    "learning outcomes. Nutrition: malnutrition screening (SAM/MAM), CMAM "
                    "programs. TB: treatment tracking (DOTS), follow-ups. "
                    "Livelihoods: SHG tracking, income monitoring."
                ),
                "topic": "sectors",
                "source_file": "builtin",
            },
            {
                "content": (
                    "Skip logic rule template: Show/hide a form element based on another "
                    "field's value. Use FormElementStatusHandler and FormElementStatus. "
                    "Check coded observations with getObservationValue('Question Name'). "
                    "Return FormElementStatus(formElement.uuid, true/false) to show/hide."
                ),
                "topic": "rule_template",
                "source_file": "builtin",
            },
            {
                "content": (
                    "Calculated field rule template: Auto-compute BMI from Height and Weight. "
                    "Get height and weight via programEncounter.getObservationValue(). "
                    "Calculate BMI = weight / (height_m * height_m). Set result with "
                    "programEncounter.setObservation('BMI', roundedValue)."
                ),
                "topic": "rule_template",
                "source_file": "builtin",
            },
            {
                "content": (
                    "Visit scheduling rule template: Schedule a follow-up encounter using "
                    "VisitScheduleBuilder. Set earliestDate and maxDate relative to the "
                    "current encounter or enrollment date. Specify encounterType name. "
                    "Return scheduleBuilder.getAll()."
                ),
                "topic": "rule_template",
                "source_file": "builtin",
            },
            {
                "content": (
                    "Validation rule template: Validate a numeric field is within range. "
                    "Return an array of validation results with success (boolean), "
                    "messageKey (error message), and formIdentifier (field name). "
                    "Check value bounds using getObservationValue()."
                ),
                "topic": "rule_template",
                "source_file": "builtin",
            },
            {
                "content": (
                    "Decision rule template: Classify malnutrition based on Z-score. "
                    "Get Weight for Height Z-score observation. Compare against thresholds: "
                    "< -3 = SAM, < -2 = MAM, >= -2 = Normal. Return decisions array "
                    "with name and value pairs."
                ),
                "topic": "rule_template",
                "source_file": "builtin",
            },
        ]

        return await self.cr.ingest_collection(
            "knowledge", items, "content",
            source_file="builtin",
            batch_size=batch_size,
            use_context=use_context,
        )

    # ------------------------------------------------------------------
    # SRS / Bundle generation guide
    # ------------------------------------------------------------------

    async def _ingest_srs_examples(
        self, data_dir: str, use_context: bool, batch_size: int
    ) -> int:
        """Ingest SRS examples and bundle generation guide."""
        guide_file = os.path.join(data_dir, "bundle_generation_guide.json")
        if not os.path.exists(guide_file):
            logger.warning("Bundle generation guide not found: %s", guide_file)
            return 0

        with open(guide_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        if not isinstance(data, dict):
            return 0

        items: list[dict[str, Any]] = []

        # Overview
        overview = data.get("overview", {})
        if overview:
            desc = overview.get("description", "")
            components = overview.get("bundleComponents", [])
            items.append({
                "content": (
                    f"Bundle generation guide: {desc}. "
                    f"Components: {', '.join(components) if components else 'N/A'}"
                ),
                "section": "overview",
                "source_file": "bundle_generation_guide.json",
            })

        # Source documents
        source_docs = data.get("sourceDocuments", {})
        for doc_key, doc_val in source_docs.items():
            if isinstance(doc_val, dict):
                desc = doc_val.get("description", "")
                sheets = doc_val.get("criticalSheets", [])
                checks = doc_val.get("criticalChecks", [])
                sheet_names = [
                    s.get("name", "") for s in sheets if isinstance(s, dict)
                ]
                content_parts = [f"Source document '{doc_key}': {desc}"]
                if sheet_names:
                    content_parts.append(f"Sheets: {', '.join(sheet_names)}")
                if checks:
                    content_parts.append(f"Critical checks: {'; '.join(checks)}")
                items.append({
                    "content": " | ".join(content_parts),
                    "section": "source_documents",
                    "source_file": "bundle_generation_guide.json",
                })

        # Critical rules, common mistakes, and other sections
        for key in (
            "criticalRules", "commonMistakes", "conceptHandling",
            "formGeneration", "zipCreation", "formTypes", "dataTypes",
            "skipLogicPatterns", "formMappingRules",
        ):
            section = data.get(key)
            if isinstance(section, dict):
                text = json.dumps(section, indent=None, ensure_ascii=False)
                # Split long sections into chunks
                if len(text) > _CHUNK_SIZE:
                    for chunk_text in self._split_text(text, _CHUNK_SIZE, _CHUNK_OVERLAP):
                        items.append({
                            "content": f"Bundle guide - {key}: {chunk_text}",
                            "section": key,
                            "source_file": "bundle_generation_guide.json",
                        })
                else:
                    items.append({
                        "content": f"Bundle guide - {key}: {text}",
                        "section": key,
                        "source_file": "bundle_generation_guide.json",
                    })
            elif isinstance(section, list):
                for item_val in section[:20]:
                    if isinstance(item_val, str):
                        items.append({
                            "content": f"Bundle guide - {key}: {item_val}",
                            "section": key,
                            "source_file": "bundle_generation_guide.json",
                        })
                    elif isinstance(item_val, dict):
                        text = json.dumps(item_val, indent=None, ensure_ascii=False)
                        items.append({
                            "content": f"Bundle guide - {key}: {text}",
                            "section": key,
                            "source_file": "bundle_generation_guide.json",
                        })

        if not items:
            return 0

        return await self.cr.ingest_collection(
            "srs_examples", items, "content",
            source_file="bundle_generation_guide.json",
            batch_size=batch_size,
            use_context=use_context,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _chunk_markdown(
        self, text: str, source: str
    ) -> list[dict[str, Any]]:
        """Split markdown text into overlapping chunks, preserving section context."""
        chunks: list[dict[str, Any]] = []

        # Split by headings to preserve section context
        sections = re.split(r"(?=^#{1,4}\s)", text, flags=re.MULTILINE)

        current_heading = ""
        for section in sections:
            section = section.strip()
            if not section:
                continue

            # Extract heading if present
            heading_match = re.match(r"^(#{1,4}\s+.+?)$", section, re.MULTILINE)
            if heading_match:
                current_heading = heading_match.group(1).strip("# ").strip()

            # If small enough, keep as one chunk
            if len(section) <= _CHUNK_SIZE:
                chunks.append({
                    "content": section,
                    "heading": current_heading,
                    "source": source,
                    "source_file": source,
                })
            else:
                # Split into overlapping chunks
                for chunk_text in self._split_text(section, _CHUNK_SIZE, _CHUNK_OVERLAP):
                    chunks.append({
                        "content": chunk_text,
                        "heading": current_heading,
                        "source": source,
                        "source_file": source,
                    })

        return chunks

    @staticmethod
    def _split_text(
        text: str, chunk_size: int, overlap: int
    ) -> list[str]:
        """Split text into overlapping chunks."""
        chunks: list[str] = []
        start = 0
        while start < len(text):
            end = start + chunk_size
            chunk = text[start:end]
            chunks.append(chunk)
            start = end - overlap
            if start >= len(text):
                break
        return chunks

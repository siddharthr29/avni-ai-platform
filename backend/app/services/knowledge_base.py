import json
import logging
import re
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from app.models.schemas import KnowledgeResult

logger = logging.getLogger(__name__)

# Root directory for bundled training data
_DATA_DIR = Path(__file__).resolve().parent.parent / "knowledge" / "data"

# Chunk size (in characters) for splitting transcript markdown into searchable chunks
_TRANSCRIPT_CHUNK_SIZE = 800
_TRANSCRIPT_CHUNK_OVERLAP = 150


class KnowledgeBase:
    """Knowledge base backed by real Avni training data.

    Loads data lazily on first access to keep startup fast. Training data comes
    from the ``app/knowledge/data/`` directory which contains:

    - ``uuid_registry.json`` -- 143 standard answer UUIDs
    - ``concept_patterns.json`` -- 4,949 concept patterns from 6 orgs
    - ``form_patterns.json`` -- 280 form patterns
    - ``rule_templates.json`` -- 132 rule templates
    - ``bundle_generation_guide.json`` -- implementation guide
    - ``video1_english.md`` / ``video2_english.md`` -- scoping tutorial transcripts

    Search uses keyword + SequenceMatcher fuzzy matching (same as v1).
    """

    def __init__(self) -> None:
        self._loaded = False

        # Flat concept entries (text + tags dicts) for search
        self._concepts: list[dict[str, Any]] = []

        # Rule entries
        self._rules: list[dict[str, Any]] = []

        # Form pattern entries
        self._forms: list[dict[str, Any]] = []

        # Support / troubleshooting entries
        self._tickets: list[dict[str, Any]] = []

        # General Avni knowledge entries (data model, SRS, sectors, etc.)
        self._avni_knowledge: list[dict[str, Any]] = []

        # Transcript knowledge chunks
        self._transcript_chunks: list[dict[str, Any]] = []

        # UUID registry: answer_name -> uuid
        self._uuid_registry: dict[str, str] = {}

        # Raw rule template objects (for richer search)
        self._rule_templates: list[dict[str, Any]] = []

    # ------------------------------------------------------------------
    # Lazy loading
    # ------------------------------------------------------------------

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        self._load_all()
        self._loaded = True

    def _load_all(self) -> None:
        """Load every data source. Missing files are silently skipped."""
        self._load_builtin_knowledge()
        self._load_uuid_registry()
        self._load_concept_patterns()
        self._load_form_patterns()
        self._load_rule_templates()
        self._load_bundle_generation_guide()
        self._load_transcript_knowledge()

        logger.info(
            "Knowledge base loaded: %d concepts, %d forms, %d rules, "
            "%d UUIDs, %d knowledge entries, %d transcript chunks, %d tickets",
            len(self._concepts),
            len(self._forms),
            len(self._rules),
            len(self._uuid_registry),
            len(self._avni_knowledge),
            len(self._transcript_chunks),
            len(self._tickets),
        )

    # ------------------------------------------------------------------
    # Data loaders
    # ------------------------------------------------------------------

    def _read_json(self, filename: str) -> Any:
        """Read a JSON file from the data directory, return None on failure."""
        filepath = _DATA_DIR / filename
        if not filepath.is_file():
            logger.warning("Training data file not found: %s", filepath)
            return None
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            logger.warning("Failed to parse %s", filepath, exc_info=True)
            return None

    def _read_text(self, filename: str) -> str | None:
        """Read a text/markdown file from the data directory."""
        filepath = _DATA_DIR / filename
        if not filepath.is_file():
            logger.warning("Training data file not found: %s", filepath)
            return None
        try:
            return filepath.read_text(encoding="utf-8")
        except Exception:
            logger.warning("Failed to read %s", filepath, exc_info=True)
            return None

    # -- UUID registry --------------------------------------------------

    def _load_uuid_registry(self) -> None:
        data = self._read_json("uuid_registry.json")
        if not data or not isinstance(data, dict):
            return
        self._uuid_registry = dict(data)
        # Also store lower-cased key -> uuid for case-insensitive lookup
        # We keep original-cased keys as primary, add lowercase aliases
        lower_map: dict[str, str] = {}
        for name, uid in data.items():
            lk = name.lower()
            if lk not in lower_map:
                lower_map[lk] = uid
        # Merge lowercase aliases (don't overwrite exact-case entries)
        for lk, uid in lower_map.items():
            if lk not in self._uuid_registry:
                self._uuid_registry[lk] = uid

    # -- Concept patterns -----------------------------------------------

    def _load_concept_patterns(self) -> None:
        data = self._read_json("concept_patterns.json")
        if not data or not isinstance(data, dict):
            return

        for data_type, concepts in data.items():
            if not isinstance(concepts, list):
                continue
            for concept in concepts:
                name = concept.get("name", "")
                uid = concept.get("uuid", "")
                org = concept.get("org", "")
                answers_count = concept.get("answers", 0)

                tags = [
                    name.lower(),
                    data_type.lower(),
                    "concept",
                ]
                if org:
                    tags.append(org.lower())

                text = f"Concept: {name} (dataType: {data_type}, uuid: {uid}, org: {org})"
                if answers_count and isinstance(answers_count, int) and answers_count > 0:
                    text += f" [{answers_count} answer options]"

                self._concepts.append({
                    "text": text,
                    "category": "concepts",
                    "tags": tags,
                    "name": name,
                    "dataType": data_type,
                    "uuid": uid,
                    "org": org,
                })

    # -- Form patterns --------------------------------------------------

    def _load_form_patterns(self) -> None:
        data = self._read_json("form_patterns.json")
        if not data or not isinstance(data, list):
            return

        for form in data:
            name = form.get("name", "")
            form_type = form.get("formType", "")
            org = form.get("org", "")
            group_count = form.get("groupCount", 0)
            element_count = form.get("elementCount", 0)

            features = []
            if form.get("hasDecisionRule"):
                features.append("decision")
            if form.get("hasValidationRule"):
                features.append("validation")
            if form.get("hasVisitScheduleRule"):
                features.append("visit scheduling")
            if form.get("hasSkipLogic"):
                features.append("skip logic")
            if form.get("hasQuestionGroups"):
                features.append("question groups")

            tags = [
                name.lower(),
                form_type.lower(),
                "form",
            ]
            if org:
                tags.append(org.lower())
            tags.extend(features)

            feature_str = ", ".join(features) if features else "none"
            text = (
                f"Form: {name} (type: {form_type}, org: {org}, "
                f"{group_count} groups, {element_count} elements, "
                f"rules: {feature_str})"
            )

            self._forms.append({
                "text": text,
                "category": "forms",
                "tags": tags,
                "name": name,
                "formType": form_type,
                "org": org,
                "groupCount": group_count,
                "elementCount": element_count,
            })

    # -- Rule templates -------------------------------------------------

    def _load_rule_templates(self) -> None:
        data = self._read_json("rule_templates.json")
        if not data or not isinstance(data, list):
            return

        self._rule_templates = list(data)

        for rule in data:
            rule_type = rule.get("type", "unknown")
            form_name = rule.get("formName", "")
            form_type = rule.get("formType", "")
            org = rule.get("org", "")
            code = rule.get("rule", "")

            tags = [
                rule_type.lower(),
                form_name.lower(),
                form_type.lower(),
                "rule",
                "rule template",
            ]
            if org:
                tags.append(org.lower())

            # Add more descriptive tags based on rule type
            if rule_type == "visitSchedule":
                tags.extend(["visit", "scheduling", "schedule", "follow up"])
            elif rule_type == "decision":
                tags.extend(["decision", "classification", "computed"])

            # Truncate code for the text field (keep first 500 chars for search)
            code_preview = code[:500] if code else ""
            text = (
                f"Rule template ({rule_type}) for form '{form_name}' "
                f"(formType: {form_type}, org: {org}):\n{code_preview}"
            )

            self._rules.append({
                "text": text,
                "category": "rules",
                "tags": tags,
                "type": rule_type,
                "formName": form_name,
                "formType": form_type,
                "org": org,
            })

    # -- Bundle generation guide ----------------------------------------

    def _load_bundle_generation_guide(self) -> None:
        data = self._read_json("bundle_generation_guide.json")
        if not data or not isinstance(data, dict):
            return

        # Extract key sections into knowledge entries
        overview = data.get("overview", {})
        if overview:
            desc = overview.get("description", "")
            components = overview.get("bundleComponents", [])
            self._avni_knowledge.append({
                "text": f"Bundle generation guide: {desc}. "
                        f"Components: {', '.join(components)}",
                "category": "bundle",
                "tags": ["bundle", "generation", "guide", "components", "implementation"],
            })

        source_docs = data.get("sourceDocuments", {})
        for doc_key, doc_val in source_docs.items():
            if isinstance(doc_val, dict):
                desc = doc_val.get("description", "")
                sheets = doc_val.get("criticalSheets", [])
                checks = doc_val.get("criticalChecks", [])
                sheet_names = [s.get("name", "") for s in sheets if isinstance(s, dict)]
                text_parts = [f"Source document '{doc_key}': {desc}"]
                if sheet_names:
                    text_parts.append(f"Sheets: {', '.join(sheet_names)}")
                if checks:
                    text_parts.append(f"Critical checks: {'; '.join(checks)}")
                self._avni_knowledge.append({
                    "text": " ".join(text_parts),
                    "category": "bundle",
                    "tags": ["bundle", "source", doc_key.lower(), "guide"],
                })

        # Extract critical rules / lessons if present
        for key in ("criticalRules", "commonMistakes", "conceptHandling",
                     "formGeneration", "zipCreation"):
            section = data.get(key)
            if isinstance(section, dict):
                text = json.dumps(section, indent=None, ensure_ascii=False)[:600]
                self._avni_knowledge.append({
                    "text": f"Bundle guide - {key}: {text}",
                    "category": "bundle",
                    "tags": ["bundle", "guide", key.lower()],
                })
            elif isinstance(section, list):
                for item in section[:10]:
                    if isinstance(item, str):
                        self._avni_knowledge.append({
                            "text": f"Bundle guide - {key}: {item}",
                            "category": "bundle",
                            "tags": ["bundle", "guide", key.lower()],
                        })

    # -- Transcript knowledge -------------------------------------------

    def _load_transcript_knowledge(self) -> None:
        for filename in ("video1_english.md", "video2_english.md"):
            text = self._read_text(filename)
            if not text:
                continue
            chunks = self._chunk_markdown(text, filename)
            self._transcript_chunks.extend(chunks)

    def _chunk_markdown(self, text: str, source: str) -> list[dict[str, Any]]:
        """Split markdown into overlapping chunks for search."""
        chunks: list[dict[str, Any]] = []

        # Split by headings first to preserve section context
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

            # If section is small enough, keep as one chunk
            if len(section) <= _TRANSCRIPT_CHUNK_SIZE:
                tags = self._extract_tags_from_text(section)
                tags.extend(["transcript", "scoping", "srs", source.replace(".md", "")])
                if current_heading:
                    tags.append(current_heading.lower())
                chunks.append({
                    "text": section,
                    "category": "knowledge",
                    "tags": tags,
                    "source": source,
                    "heading": current_heading,
                })
            else:
                # Split into overlapping chunks
                start = 0
                while start < len(section):
                    end = start + _TRANSCRIPT_CHUNK_SIZE
                    chunk_text = section[start:end]

                    tags = self._extract_tags_from_text(chunk_text)
                    tags.extend(["transcript", "scoping", "srs", source.replace(".md", "")])
                    if current_heading:
                        tags.append(current_heading.lower())

                    chunks.append({
                        "text": chunk_text,
                        "category": "knowledge",
                        "tags": tags,
                        "source": source,
                        "heading": current_heading,
                    })

                    start = end - _TRANSCRIPT_CHUNK_OVERLAP
                    if start >= len(section):
                        break

        return chunks

    @staticmethod
    def _extract_tags_from_text(text: str) -> list[str]:
        """Extract meaningful tags from a text chunk."""
        tags: list[str] = []
        # Look for bold terms in markdown
        bold_terms = re.findall(r"\*\*([^*]+)\*\*", text)
        for term in bold_terms[:8]:
            tags.append(term.lower().strip())

        # Look for Avni-specific keywords
        avni_keywords = [
            "form", "visit", "schedule", "permission", "dashboard", "card",
            "registration", "enrollment", "enrolment", "encounter", "program",
            "concept", "field", "data type", "mandatory", "skip logic",
            "validation", "w3h", "srs", "scoping", "user persona",
            "anthropometry", "cancellation", "overdue", "void",
        ]
        text_lower = text.lower()
        for kw in avni_keywords:
            if kw in text_lower:
                tags.append(kw)

        return tags

    # -- Built-in knowledge (always available) --------------------------

    def _load_builtin_knowledge(self) -> None:
        """Load built-in Avni knowledge that is always available."""
        self._avni_knowledge = [
            {
                "text": "SubjectType defines the entity being tracked (e.g., Individual, Household, Group). "
                        "Properties: name, type (Person/Individual/Household/Group), uuid, active. "
                        "A Person subject type enables first/middle/last name and date of birth fields.",
                "category": "data_model",
                "tags": ["subject", "subjecttype", "person", "individual", "household", "group", "registration"],
            },
            {
                "text": "Program represents a longitudinal tracking workflow (e.g., Pregnancy Program, TB Program). "
                        "Properties: name, uuid, colour, enrolmentEligibilityCheckRule. "
                        "Subjects are enrolled in programs and can have multiple encounters within each program.",
                "category": "data_model",
                "tags": ["program", "enrolment", "enrollment", "longitudinal", "tracking"],
            },
            {
                "text": "EncounterType defines a visit type, either within a program (ProgramEncounter) or "
                        "standalone (Encounter/GeneralEncounter). Properties: name, uuid, active. "
                        "Each encounter type is linked to forms via FormMappings.",
                "category": "data_model",
                "tags": ["encounter", "visit", "encounter type", "program encounter", "general encounter"],
            },
            {
                "text": "Form is a collection of FormElementGroups, each containing FormElements. "
                        "formType can be: IndividualProfile, ProgramEnrolment, ProgramExit, ProgramEncounter, "
                        "ProgramEncounterCancellation, Encounter, IndividualEncounterCancellation. "
                        "Each FormElement references a Concept.",
                "category": "data_model",
                "tags": ["form", "form element", "form group", "form type", "registration form", "encounter form"],
            },
            {
                "text": "Concept is a reusable field definition. dataType can be: Text, Numeric, Date, DateTime, "
                        "Time, Coded, Image, Notes, NA, Id, Video, Audio, File, Location, PhoneNumber, GroupAffiliation, "
                        "Subject, Encounter, QuestionGroup, Duration. Coded concepts have an 'answers' array of "
                        "answer concepts (dataType: NA). Numeric concepts can have unit, lowAbsolute, highAbsolute.",
                "category": "data_model",
                "tags": ["concept", "field", "data type", "coded", "numeric", "text", "date", "answers"],
            },
            {
                "text": "FormMapping links a form to a SubjectType and optionally a Program and EncounterType. "
                        "This determines when and where a form appears in the app. "
                        "Properties: formUUID, subjectTypeUUID, programUUID, encounterTypeUUID, formType.",
                "category": "data_model",
                "tags": ["form mapping", "mapping", "link", "association"],
            },
            {
                "text": "Groups define user roles (e.g., Everyone, Admin, Supervisor, MLHW). "
                        "GroupPrivileges grant permissions per group per entity type. "
                        "Privilege types: ViewSubject, RegisterSubject, EditSubject, VoidSubject, "
                        "EnrolSubject, ViewEnrolmentDetails, EditEnrolmentDetails, ExitEnrolment, "
                        "ViewVisit, ScheduleVisit, PerformVisit, EditVisit, CancelVisit, ViewChecklist, EditChecklist.",
                "category": "data_model",
                "tags": ["group", "privilege", "permission", "role", "access control"],
            },
            {
                "text": "The Avni implementation bundle is a zip file containing JSON configuration files "
                        "that must be uploaded in a specific dependency order: "
                        "1. addressLevelTypes 2. subjectTypes 3. operationalSubjectTypes "
                        "4. encounterTypes 5. operationalEncounterTypes 6. programs 7. operationalPrograms "
                        "8. concepts 9. forms/* 10. formMappings 11. groups 12. groupPrivilege. "
                        "Violating this order causes upload failures due to missing references.",
                "category": "bundle",
                "tags": ["bundle", "zip", "upload", "order", "dependency", "implementation"],
            },
            {
                "text": "The SRS (Scoping & Requirement Specification) document has 9 tabs: "
                        "1. Help & Status Tracker 2. Program Summary 3. Program Detail 4. User Persona "
                        "5. W3H (What/When/Who/How) 6. Forms 7. Visit Scheduling 8. Offline Dashboard Cards "
                        "9. Permissions. The W3H tab is the heart of the scoping document.",
                "category": "srs",
                "tags": ["srs", "scoping", "requirement", "specification", "tabs", "w3h"],
            },
            {
                "text": "Avni rules are written in JavaScript and run on the mobile app. Types include: "
                        "1. Skip logic rules (show/hide form elements based on conditions) "
                        "2. Calculated/computed fields (auto-compute values like BMI, age) "
                        "3. Validation rules (enforce data quality) "
                        "4. Decision rules (set observations based on calculations, e.g., Z-scores) "
                        "5. Visit scheduling rules (auto-schedule follow-up encounters) "
                        "6. Eligibility rules (determine program enrollment eligibility) "
                        "7. Summary rules (display computed summaries on subject/program dashboards).",
                "category": "rules",
                "tags": ["rule", "javascript", "skip logic", "validation", "calculation", "scheduling", "decision"],
            },
            {
                "text": "Common Avni concepts across implementations: "
                        "Height (Numeric, cm), Weight (Numeric, kg), MUAC (Numeric, cm), "
                        "Hb (Numeric, g/dL), BMI (Numeric, computed), "
                        "Gender (Coded: Male/Female), Date of Birth (Date), "
                        "BP Systolic (Numeric, mmHg), BP Diastolic (Numeric, mmHg).",
                "category": "concepts",
                "tags": ["concept", "height", "weight", "muac", "hb", "bmi", "gender", "blood pressure", "common"],
            },
            {
                "text": "Avni sync works offline-first. Data entered on mobile is stored in local SQLite "
                        "and synced to the server when network is available. Sync issues can arise from: "
                        "1. Network timeouts 2. Server-side validation failures 3. Concept UUID mismatches "
                        "4. Missing form mappings 5. Large media files. "
                        "Check sync telemetry at /api/syncTelemetry for diagnostics.",
                "category": "troubleshooting",
                "tags": ["sync", "offline", "network", "timeout", "error", "troubleshoot", "sqlite"],
            },
            {
                "text": "Avni supports multiple sectors: "
                        "MCH (Maternal & Child Health): pregnancy tracking, immunization, growth monitoring. "
                        "WASH (Water & Sanitation): water source monitoring, toilet construction tracking. "
                        "Education: student enrollment, attendance, learning outcomes. "
                        "Nutrition: malnutrition screening (SAM/MAM), CMAM programs, growth charts. "
                        "TB: treatment tracking (DOTS), follow-ups, medication compliance. "
                        "Livelihoods: SHG tracking, income monitoring, skill development.",
                "category": "sectors",
                "tags": ["sector", "mch", "wash", "education", "nutrition", "tb", "livelihoods", "ngo"],
            },
        ]

        # Built-in rule template knowledge (kept for backward compatibility)
        builtin_rules = [
            {
                "text": "Skip logic rule template: Show/hide a form element based on another field's value.\n"
                        "```javascript\n"
                        "const statusHandler = new FormElementStatusHandler({formElement});\n"
                        "const show = new FormElementStatus(formElement.uuid, true);\n"
                        "const hide = new FormElementStatus(formElement.uuid, false);\n"
                        "// Check a coded observation\n"
                        "const answer = statusHandler.programEnrolment.getObservationValue('Question Name');\n"
                        "return answer === 'Yes' ? show : hide;\n"
                        "```",
                "category": "rules",
                "tags": ["skip logic", "show", "hide", "form element", "visibility", "rule template"],
            },
            {
                "text": "Calculated field rule template: Auto-compute BMI from Height and Weight.\n"
                        "```javascript\n"
                        "const height = programEncounter.getObservationValue('Height');\n"
                        "const weight = programEncounter.getObservationValue('Weight');\n"
                        "if (height && weight && height > 0) {\n"
                        "  const heightM = height / 100;\n"
                        "  const bmi = weight / (heightM * heightM);\n"
                        "  programEncounter.setObservation('BMI', Math.round(bmi * 10) / 10);\n"
                        "}\n"
                        "```",
                "category": "rules",
                "tags": ["calculated", "computed", "bmi", "formula", "auto", "rule template"],
            },
            {
                "text": "Visit scheduling rule template: Schedule a follow-up encounter.\n"
                        "```javascript\n"
                        "const scheduleBuilder = new VisitScheduleBuilder({programEnrolment});\n"
                        "const earliestDate = moment(programEnrolment.enrolmentDateTime).add(30, 'days');\n"
                        "const maxDate = moment(earliestDate).add(7, 'days');\n"
                        "scheduleBuilder.add({\n"
                        "  name: 'Follow Up Visit',\n"
                        "  encounterType: 'Follow Up',\n"
                        "  earliestDate: earliestDate.toDate(),\n"
                        "  maxDate: maxDate.toDate()\n"
                        "});\n"
                        "return scheduleBuilder.getAll();\n"
                        "```",
                "category": "rules",
                "tags": ["visit", "scheduling", "follow up", "encounter", "schedule", "rule template"],
            },
            {
                "text": "Validation rule template: Validate a numeric field is within range.\n"
                        "```javascript\n"
                        "const validationResults = [];\n"
                        "const value = programEncounter.getObservationValue('Weight');\n"
                        "if (value !== undefined && (value < 0.5 || value > 200)) {\n"
                        "  validationResults.push({\n"
                        "    success: false,\n"
                        "    messageKey: 'Weight must be between 0.5 and 200 kg',\n"
                        "    formIdentifier: 'Weight'\n"
                        "  });\n"
                        "}\n"
                        "return validationResults;\n"
                        "```",
                "category": "rules",
                "tags": ["validation", "range", "check", "error", "rule template"],
            },
            {
                "text": "Decision rule template: Classify malnutrition based on Z-score.\n"
                        "```javascript\n"
                        "const decisions = [];\n"
                        "const whz = programEncounter.getObservationValue('Weight for Height Z-score');\n"
                        "if (whz < -3) {\n"
                        "  decisions.push({name: 'Nutritional Status', value: 'SAM'});\n"
                        "} else if (whz < -2) {\n"
                        "  decisions.push({name: 'Nutritional Status', value: 'MAM'});\n"
                        "} else {\n"
                        "  decisions.push({name: 'Nutritional Status', value: 'Normal'});\n"
                        "}\n"
                        "return decisions;\n"
                        "```",
                "category": "rules",
                "tags": ["decision", "classification", "malnutrition", "z-score", "sam", "mam", "rule template"],
            },
        ]
        self._rules.extend(builtin_rules)

        # Common support patterns
        self._tickets = [
            {
                "text": "Sync failure due to concept UUID mismatch: When a concept UUID in the form JSON "
                        "doesn't match the concepts.json, sync will fail with a 'Concept not found' error. "
                        "Fix: Regenerate the bundle ensuring concept UUIDs are consistent across all files.",
                "category": "troubleshooting",
                "tags": ["sync", "uuid", "mismatch", "concept", "error", "not found"],
            },
            {
                "text": "Form not showing on mobile: Check 1) FormMapping exists for the correct subjectType "
                        "and program/encounterType combination. 2) User's group has the required privilege "
                        "(RegisterSubject, PerformVisit, etc.). 3) The form is not voided. 4) Sync is complete.",
                "category": "troubleshooting",
                "tags": ["form", "missing", "not showing", "mobile", "mapping", "privilege"],
            },
            {
                "text": "Bundle upload error 'Entity not found': This means a referenced entity (concept, "
                        "program, encounterType, subjectType) hasn't been created yet. The zip file entries "
                        "must be in the correct dependency order. Ensure concepts.json comes before forms, "
                        "and forms come before formMappings.",
                "category": "troubleshooting",
                "tags": ["upload", "entity", "not found", "order", "dependency", "bundle"],
            },
            {
                "text": "Duplicate concept name error: Avni requires unique concept names. If two forms use "
                        "different concepts with the same name, rename one to be unique (e.g., 'Hb' vs 'Hb TB'). "
                        "Answer concepts (dataType: NA) also share the global namespace.",
                "category": "troubleshooting",
                "tags": ["duplicate", "concept", "name", "collision", "unique"],
            },
            {
                "text": "Data not appearing in reports: Check 1) The concept used in the report matches the "
                        "exact concept name and UUID from the form. 2) The report card query filters are correct. "
                        "3) Data has been synced to the server. 4) User has ViewSubject/ViewVisit privileges.",
                "category": "troubleshooting",
                "tags": ["report", "data", "missing", "dashboard", "card", "query"],
            },
            {
                "text": "Visit not being scheduled: Check 1) The visit scheduling rule is correctly defined. "
                        "2) The encounterType exists and has a form mapping. 3) The program enrollment is active "
                        "(not exited). 4) The rule conditions are met. 5) Check for JavaScript errors in the rule.",
                "category": "troubleshooting",
                "tags": ["visit", "schedule", "not scheduled", "rule", "encounter"],
            },
            {
                "text": "Skip logic not working: Check 1) The rule references the correct concept name or UUID. "
                        "2) The FormElementStatusHandler is returning the correct FormElementStatus. "
                        "3) The observation value comparison uses the right type (string vs concept name). "
                        "4) Check browser console for JavaScript errors.",
                "category": "troubleshooting",
                "tags": ["skip logic", "rule", "not working", "form element", "visibility"],
            },
            {
                "text": "App crashing on form open: Check 1) All concepts referenced in the form exist in "
                        "concepts.json. 2) No circular references in question groups. 3) The form JSON is "
                        "valid and well-formed. 4) Check for excessively large forms (>200 elements).",
                "category": "troubleshooting",
                "tags": ["crash", "form", "error", "open", "concepts", "json"],
            },
        ]

    # ------------------------------------------------------------------
    # Scoring / search engine
    # ------------------------------------------------------------------

    def _fuzzy_score(self, query: str, text: str, tags: list[str]) -> float:
        """Compute a relevance score combining tag matching and text similarity."""
        query_lower = query.lower()
        query_words = set(re.split(r"\W+", query_lower))

        # Tag matching (strongest signal)
        tag_hits = 0
        for tag in tags:
            tag_lower = tag.lower()
            if tag_lower in query_lower:
                tag_hits += 2
            elif any(w in tag_lower for w in query_words if len(w) > 2):
                tag_hits += 1
        tag_score = min(tag_hits / max(len(tags), 1), 1.0)

        # Keyword presence in text
        text_lower = text.lower()
        word_hits = sum(1 for w in query_words if len(w) > 2 and w in text_lower)
        keyword_score = min(word_hits / max(len(query_words), 1), 1.0)

        # SequenceMatcher for overall similarity
        seq_score = SequenceMatcher(None, query_lower[:100], text_lower[:200]).ratio()

        # Weighted combination
        return (tag_score * 0.5) + (keyword_score * 0.35) + (seq_score * 0.15)

    def _search_collection(
        self,
        collection: list[dict[str, Any]],
        query: str,
        category: str,
        limit: int,
    ) -> list[KnowledgeResult]:
        scored: list[tuple[float, dict[str, Any]]] = []
        for entry in collection:
            score = self._fuzzy_score(
                query, entry["text"], entry.get("tags", [])
            )
            if score > 0.05:
                scored.append((score, entry))

        scored.sort(key=lambda x: x[0], reverse=True)

        return [
            KnowledgeResult(
                text=entry["text"],
                category=entry.get("category", category),
                score=round(score, 3),
                metadata={"tags": entry.get("tags", [])},
            )
            for score, entry in scored[:limit]
        ]

    # ------------------------------------------------------------------
    # Public search methods
    # ------------------------------------------------------------------

    def search_concepts(self, query: str, limit: int = 10) -> list[KnowledgeResult]:
        """Search concept-related knowledge.

        Searches across 4,949 real concept patterns plus built-in data model
        knowledge.
        """
        self._ensure_loaded()
        concept_entries = [
            e for e in self._avni_knowledge
            if e.get("category") in ("concepts", "data_model")
        ] + self._concepts
        return self._search_collection(concept_entries, query, "concepts", limit)

    def search_forms(self, query: str, limit: int = 10) -> list[KnowledgeResult]:
        """Search form patterns.

        Searches across 280 real form patterns from 6 organizations.
        """
        self._ensure_loaded()
        form_entries = [
            e for e in self._avni_knowledge
            if e.get("category") in ("data_model",) and "form" in str(e.get("tags", []))
        ] + self._forms
        return self._search_collection(form_entries, query, "forms", limit)

    def search_rules(self, query: str, rule_type: str | None = None, limit: int = 10) -> list[KnowledgeResult]:
        """Search rule templates and documentation.

        Searches across 132 real rule templates plus built-in rule knowledge.
        Optionally filter by rule_type ('visitSchedule', 'decision', etc.).
        """
        self._ensure_loaded()
        rule_entries = [
            e for e in self._avni_knowledge
            if e.get("category") == "rules"
        ] + self._rules

        if rule_type:
            rule_type_lower = rule_type.lower()
            rule_entries = [
                e for e in rule_entries
                if rule_type_lower in str(e.get("tags", [])).lower()
                or rule_type_lower in e.get("type", "").lower()
            ]

        return self._search_collection(rule_entries, query, "rules", limit)

    def search_tickets(self, query: str, limit: int = 10) -> list[KnowledgeResult]:
        """Search support patterns and troubleshooting knowledge."""
        self._ensure_loaded()
        ticket_entries = [
            e for e in self._avni_knowledge
            if e.get("category") in ("troubleshooting", "sectors")
        ] + self._tickets
        return self._search_collection(ticket_entries, query, "troubleshooting", limit)

    def search_knowledge(self, query: str, limit: int = 10) -> list[KnowledgeResult]:
        """Search transcript knowledge and general Avni documentation.

        Searches YouTube tutorial transcripts about SRS scoping, split into
        searchable chunks.
        """
        self._ensure_loaded()
        return self._search_collection(
            self._transcript_chunks + self._avni_knowledge,
            query,
            "knowledge",
            limit,
        )

    def search_all(self, query: str, limit: int = 10) -> list[KnowledgeResult]:
        """Search across all knowledge categories."""
        self._ensure_loaded()
        all_entries = (
            self._avni_knowledge
            + self._rules
            + self._tickets
            + self._concepts
            + self._forms
            + self._transcript_chunks
        )
        return self._search_collection(all_entries, query, "general", limit)

    def get_uuid(self, answer_name: str) -> str | None:
        """Look up a standard UUID from the registry by concept/answer name.

        Tries exact match first, then case-insensitive match.
        """
        self._ensure_loaded()
        # Exact match
        result = self._uuid_registry.get(answer_name)
        if result:
            return result
        # Case-insensitive match
        return self._uuid_registry.get(answer_name.lower())

    # ------------------------------------------------------------------
    # External data loading (for programmatic use)
    # ------------------------------------------------------------------

    def load_external_concepts(self, concepts_data: list[dict[str, Any]]) -> None:
        """Load concept data from an external source (e.g., a training dataset)."""
        for concept in concepts_data:
            name = concept.get("name", "")
            data_type = concept.get("dataType", "")
            uuid_val = concept.get("uuid", "")

            entry: dict[str, Any] = {
                "text": f"Concept: {name} (dataType: {data_type}, uuid: {uuid_val})",
                "category": "concepts",
                "tags": [
                    name.lower(),
                    data_type.lower(),
                    "concept",
                ],
            }

            if concept.get("answers"):
                answer_names = [a.get("name", "") for a in concept["answers"]]
                entry["text"] += f" Answers: {', '.join(answer_names)}"
                for a_name in answer_names:
                    entry["tags"].append(a_name.lower())

            if concept.get("unit"):
                entry["text"] += f" Unit: {concept['unit']}"
                entry["tags"].append(concept["unit"].lower())

            self._concepts.append(entry)
            if uuid_val:
                self._uuid_registry[name] = uuid_val

        logger.info("Loaded %d external concepts into knowledge base", len(concepts_data))

    def load_external_rules(self, rules_data: list[dict[str, Any]]) -> None:
        """Load rule data from an external source."""
        for rule in rules_data:
            entry = {
                "text": rule.get("text", rule.get("code", "")),
                "category": "rules",
                "tags": rule.get("tags", ["rule"]),
            }
            self._rules.append(entry)

        logger.info("Loaded %d external rules into knowledge base", len(rules_data))


# Singleton instance
knowledge_base = KnowledgeBase()

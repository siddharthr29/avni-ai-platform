"""
Production Bundle Reference
============================
Comprehensive analysis of 17+ real Avni production org bundles.
Used by the bundle generator to understand what production-quality bundles look like.

Source directories analyzed:
  - /Users/samanvay/Downloads/All/avni-ai/orgs-bundle/ (17 orgs)
  - /Users/samanvay/Downloads/All/avni-ai/sangwari-bundle/
  - /Users/samanvay/Downloads/All/avni-ai/bhs-phulwari-bundle/
"""

# =============================================================================
# SECTION 1: PER-ORG STATISTICS
# =============================================================================

ORG_STATS = {
    "Ashwini uat": {
        "concepts": 6130,
        "data_types": {"NA": 3864, "Text": 666, "Numeric": 306, "Coded": 1120, "Date": 160, "DateTime": 12, "Notes": 1, "Image": 1},
        "form_mappings": 97,
        "forms": 92,
        "form_types": {"Encounter": 14, "ProgramEncounter": 42, "ProgramEncounterCancellation": 9, "IndividualEncounterCancellation": 4, "ProgramExit": 7, "ProgramEnrolment": 12, "ChecklistItem": 1, "IndividualProfile": 3},
        "programs": ["Stroke Care", "Alcohol de-addiction", "Family Planning", "Suicide Prevention", "Child", "Covid", "TB", "Mental Health", "Sickle Cell", "Mother", "Screening Program", "Chronic sickness"],
        "encounter_types": 56,
        "subject_types": [
            {"name": "Village Monitoring", "type": "Individual"},
            {"name": "Individual", "type": "Person"},
            {"name": "Household Survey", "type": "Household"},
        ],
        "complexity": "VERY_HIGH",
        "description": "Large tribal health org with 12 programs spanning maternal health, child health, chronic disease, mental health, and infectious disease. Most complex bundle by concept count.",
    },
    "Animedh Charitable Trust DNH": {
        "concepts": 1159,
        "data_types": {"Coded": 266, "NA": 736, "Text": 79, "QuestionGroup": 13, "Notes": 7, "Numeric": 29, "Date": 18, "Subject": 5, "ImageV2": 2, "Image": 1, "DateTime": 1, "Duration": 1, "Video": 1},
        "form_mappings": 106,
        "forms": 99,
        "form_types": {"ProgramEncounter": 28, "ProgramEncounterCancellation": 27, "ProgramEnrolment": 15, "ProgramExit": 15, "IndividualProfile": 7, "IndividualEncounterCancellation": 3, "Encounter": 3, "ChecklistItem": 1},
        "programs": ["DNH-ECD Individual Referral", "Need Assessment - Referral", "Pregnancy - Referral", "Child - Referral", "Mantrana (adolescents)", "Child", "DNH-ECC", "NK Individual Referral", "Pregnancy", "Needs Assessment", "NK Home-based/PTOT intervention", "Child Development Categorisation", "Mantrana - Referral"],
        "encounter_types": 33,
        "subject_types": [
            {"name": "Person", "type": "Person"},
            {"name": "Household", "type": "Household"},
            {"name": "Volunteer", "type": "Person"},
            {"name": "Adolescent group", "type": "Group"},
            {"name": "School Group", "type": "Group"},
            {"name": "Aanganwadi", "type": "Group"},
        ],
        "complexity": "VERY_HIGH",
        "description": "Complex multi-program bundle covering child development, pregnancy, adolescent mentoring, with referral programs for each. Uses QuestionGroups, Videos, and multiple subject types.",
    },
    "APF Odisha": {
        "concepts": 951,
        "data_types": {"NA": 426, "Coded": 287, "Text": 67, "Numeric": 132, "Location": 2, "Id": 4, "Date": 32, "QuestionGroup": 1},
        "form_mappings": 53,
        "forms": 70,
        "form_types": {"ProgramEncounter": 18, "ProgramEncounterCancellation": 21, "ChecklistItem": 1, "IndividualProfile": 10, "Encounter": 7, "IndividualEncounterCancellation": 7, "ProgramEnrolment": 2, "ProgramExit": 2, "Location": 2},
        "programs": ["Pregnancy", "Child"],
        "encounter_types": 23,
        "subject_types": [
            {"name": "TIMS for Poshan Sathi", "type": "User"},
            {"name": "Village Profile", "type": "Individual"},
            {"name": "Household", "type": "Group"},
            {"name": "AWC Profile", "type": "Individual"},
            {"name": "Individual", "type": "Person"},
        ],
        "complexity": "HIGH",
        "description": "Nutrition program (Poshan) with complex visit scheduling, growth monitoring, and QRT follow-ups. Has the most sophisticated visit schedule rules and edit form rules.",
    },
    "Collectives for Integrated Livelihood Initiatives (CInI)": {
        "concepts": 1467,
        "data_types": {"NA": 637, "Text": 189, "Coded": 388, "Numeric": 200, "Subject": 10, "Date": 17, "Image": 5, "QuestionGroup": 10, "Location": 1, "File": 8, "Audio": 1, "Notes": 1},
        "form_mappings": 78,
        "forms": 71,
        "form_types": {"IndividualProfile": 12, "Encounter": 30, "IndividualEncounterCancellation": 29},
        "programs": [],
        "encounter_types": 31,
        "subject_types": [
            {"name": "CRP/BRP", "type": "Person"},
            {"name": "State", "type": "Individual"},
            {"name": "Anganwadi", "type": "Individual"},
            {"name": "Volunteer", "type": "Individual"},
            {"name": "Block", "type": "Individual"},
            {"name": "District", "type": "Individual"},
            {"name": "School", "type": "Individual"},
            {"name": "Activity", "type": "Individual"},
            {"name": "Action Item", "type": "Individual"},
            {"name": "Field Coordinator", "type": "Individual"},
            {"name": "School Teacher", "type": "Individual"},
            {"name": "Anganwadi Teacher", "type": "Individual"},
        ],
        "complexity": "HIGH",
        "description": "No programs - uses only general encounters. Has 12 subject types representing an organizational hierarchy (State > District > Block > School/Anganwadi). Uses Audio, File, and Subject data types.",
    },
    "MLD Trust": {
        "concepts": 1062,
        "data_types": {"NA": 541, "Coded": 300, "Text": 138, "Numeric": 69, "PhoneNumber": 1, "Date": 5, "QuestionGroup": 7, "Subject": 1},
        "form_mappings": 27,
        "forms": 27,
        "form_types": {"ProgramEncounterCancellation": 10, "ProgramEncounter": 10, "ProgramEnrolment": 3, "ProgramExit": 3, "IndividualProfile": 1},
        "programs": ["Child", "Pregnancy", "Malnutrition Program"],
        "encounter_types": 10,
        "subject_types": [{"name": "Individual", "type": "Person"}],
        "complexity": "HIGH",
        "description": "MCH bundle with cross-subject decision rules (child birth form looks up mother's pregnancy data). Uses QuestionGroups and complex high-risk assessment logic.",
    },
    "Goonj": {
        "concepts": 938,
        "data_types": {"NA": 585, "Coded": 97, "Text": 123, "Subject": 2, "Encounter": 2, "QuestionGroup": 13, "Date": 6, "Location": 5, "Image": 10, "Numeric": 88, "DateTime": 1, "ImageV2": 1, "File": 1, "PhoneNumber": 2, "GroupAffiliation": 2},
        "form_mappings": 10,
        "forms": 22,
        "form_types": {"Encounter": 5, "IndividualProfile": 10, "Location": 2, "IndividualEncounterCancellation": 5},
        "programs": [],
        "encounter_types": 5,
        "subject_types": [
            {"name": "Demand", "type": "Individual"},
            {"name": "Distribution", "type": "Individual"},
            {"name": "Dispatch", "type": "Individual"},
            {"name": "Activity", "type": "Individual"},
            {"name": "Inventory Item", "type": "Individual"},
            {"name": "Village", "type": "Group"},
        ],
        "complexity": "MEDIUM",
        "description": "Supply chain / logistics org. Uses Encounter and GroupAffiliation data types. Has role-based edit form rules and duplicate village validation.",
    },
    "IPH Sickle Cell": {
        "concepts": 538,
        "data_types": {"NA": 181, "Text": 135, "Coded": 107, "Numeric": 54, "Date": 16, "File": 23, "QuestionGroup": 5, "Notes": 2, "DateTime": 3, "Image": 7, "Id": 1, "Time": 1, "Location": 2, "PhoneNumber": 1},
        "form_mappings": 41,
        "forms": 41,
        "form_types": {"IndividualEncounterCancellation": 7, "ProgramEncounter": 6, "Encounter": 7, "ProgramEnrolment": 6, "ProgramExit": 6, "IndividualProfile": 3, "ProgramEncounterCancellation": 6},
        "programs": ["Sickle Cell Trait (Carrier)", "Sickle cell disease (Affected)", "Thalassemia Minor (Carrier)", "G6PD deficient (10% -80%)", "G6PD deficient (less than 10%)", "Thalassemia Major (Affected)"],
        "encounter_types": 13,
        "subject_types": [
            {"name": "Participant", "type": "Person"},
            {"name": "Family", "type": "Household"},
        ],
        "complexity": "HIGH",
        "description": "Clinical genetics screening with 6 disease-specific programs. Uses File uploads extensively (23 File concepts) for lab reports. Has Household subject type for family tracking.",
    },
    "Gubbachi": {
        "concepts": 141,
        "data_types": {"NA": 73, "Text": 26, "QuestionGroup": 7, "Coded": 21, "Subject": 9, "PhoneNumber": 1, "Date": 3, "Numeric": 1},
        "form_mappings": 38,
        "forms": 35,
        "form_types": {"IndividualEncounterCancellation": 9, "Encounter": 7, "IndividualProfile": 5, "ProgramEncounter": 4, "ProgramEnrolment": 3, "ProgramExit": 3, "ProgramEncounterCancellation": 4},
        "programs": ["English Medium"],
        "encounter_types": 12,
        "subject_types": [
            {"name": "Teacher", "type": "Individual"},
            {"name": "Student", "type": "Person"},
            {"name": "Activity", "type": "Individual"},
            {"name": "Class", "type": "Group"},
        ],
        "complexity": "MEDIUM",
        "description": "Education org with attendance tracking using Group subjects (Class -> Students). Has complex validation rules that cross-check grouped observations with total student counts.",
    },
    "JSS": {
        "concepts": 310,
        "data_types": {"NA": 218, "Coded": 46, "Date": 4, "Numeric": 12, "Text": 23, "Subject": 3, "Id": 1, "Location": 1, "GroupAffiliation": 2},
        "form_mappings": 13,
        "forms": 13,
        "form_types": {"IndividualProfile": 2, "Encounter": 3, "ProgramEncounterCancellation": 1, "IndividualEncounterCancellation": 3, "ProgramEncounter": 2, "ProgramExit": 1, "ProgramEnrolment": 1},
        "programs": ["Phulwari"],
        "encounter_types": 5,
        "subject_types": [
            {"name": "Phulwari", "type": "Group"},
            {"name": "Individual", "type": "Person"},
        ],
        "complexity": "MEDIUM",
        "description": "Childcare center (Phulwari) program. Group subjects for centers with member children. Complex cancellation-based visit rescheduling with day-of-month scheduling from group properties.",
    },
    "Maitrayana": {
        "concepts": 253,
        "data_types": {"NA": 193, "Text": 16, "Coded": 26, "Subject": 10, "Numeric": 4, "Image": 1, "Date": 2, "PhoneNumber": 1},
        "form_mappings": 40,
        "forms": 42,
        "form_types": {"ProgramEncounter": 10, "ProgramExit": 9, "ProgramEnrolment": 9, "ProgramEncounterCancellation": 10, "IndividualProfile": 4},
        "programs": ["D_Vriddhi", "E_Be Ambitious", "B_Camp", "C_Club", "F_Economic Justice Program", "A_YPI Pragati", "G_I am Job Ready"],
        "encounter_types": 10,
        "subject_types": [
            {"name": "Participant", "type": "Person"},
            {"name": "Batch", "type": "Group"},
        ],
        "complexity": "MEDIUM",
        "description": "Youth development org with 7 programs covering life skills, employment, clubs. Uses alphabetical prefix naming (A_, B_, C_) for program ordering. Has edit form rules with time-based restrictions.",
    },
    "Purna Clinic": {
        "concepts": 327,
        "data_types": {"NA": 186, "Coded": 82, "QuestionGroup": 3, "Text": 27, "Numeric": 21, "Date": 3, "PhoneNumber": 2, "Duration": 3},
        "form_mappings": 10,
        "forms": 11,
        "form_types": {"ProgramEncounter": 2, "ProgramExit": 1, "IndividualProfile": 2, "ProgramEncounterCancellation": 2, "IndividualEncounterCancellation": 1, "Encounter": 2, "ProgramEnrolment": 1},
        "programs": ["Chronic Disease"],
        "encounter_types": 3,
        "subject_types": [
            {"name": "Individual", "type": "Person"},
            {"name": "Household", "type": "Household"},
        ],
        "complexity": "MEDIUM",
        "description": "Chronic disease management with cross-encounter BP comparisons. Skip logic compares current encounter values with previous encounter values to show different treatment pathways.",
    },
    "JK Lakshmi Cement": {
        "concepts": 262,
        "data_types": {"NA": 142, "Numeric": 34, "Coded": 54, "Date": 10, "Text": 20, "QuestionGroup": 1, "Subject": 1},
        "form_mappings": 22,
        "forms": 22,
        "programs": ["Child", "Pregnancy"],
        "encounter_types": 7,
        "subject_types": [
            {"name": "Individual", "type": "Person"},
            {"name": "Household", "type": "Household"},
        ],
        "complexity": "MEDIUM",
        "description": "CSR-funded MCH program with standard pregnancy and child tracking.",
    },
    "atul_uat": {
        "concepts": 874,
        "data_types": {"NA": 521, "Coded": 189, "Numeric": 47, "Text": 90, "QuestionGroup": 6, "Date": 13, "Subject": 6, "Image": 1, "Time": 1},
        "form_mappings": 37,
        "forms": 42,
        "programs": ["Community Screening", "Pregnancy", "Child"],
        "encounter_types": 13,
        "subject_types": [
            {"name": "School", "type": "Group"},
            {"name": "Individual", "type": "Person"},
            {"name": "Group Details", "type": "Group"},
            {"name": "Household", "type": "Household"},
        ],
        "complexity": "HIGH",
        "description": "CSR health program with community screening, pregnancy, and child tracking. Has complex FEG skip logic that checks across past encounters and enrolment-level conditions.",
    },
    "Uninhibited": {
        "concepts": 621,
        "data_types": {"NA": 398, "Text": 51, "Coded": 149, "Numeric": 10, "PhoneNumber": 1, "Date": 2, "QuestionGroup": 5, "Subject": 4, "GroupAffiliation": 1},
        "form_mappings": 19,
        "forms": 19,
        "programs": ["PS 4.1 Period Tracking Program"],
        "encounter_types": 6,
        "subject_types": [
            {"name": "School audit survey", "type": "Individual"},
            {"name": "Student", "type": "Person"},
            {"name": "School", "type": "Individual"},
        ],
        "complexity": "LOW",
        "description": "Menstrual health and school audit program. Simple single program with school and student tracking.",
    },
    "Hasiru Dala": {
        "concepts": 921,
        "data_types": {"NA": 495, "Text": 135, "Coded": 204, "Numeric": 68, "Date": 3, "Image": 16},
        "form_mappings": 1,
        "forms": 1,
        "programs": [],
        "encounter_types": 0,
        "subject_types": [{"name": "Individual", "type": "Person"}],
        "complexity": "LOW",
        "description": "Registration-only bundle with 921 concepts in a single registration form. No programs, no encounters. Largest single-form bundle.",
    },
    "Astitva": {
        "concepts": 184,
        "data_types": {"NA": 76, "Text": 30, "Date": 8, "Numeric": 39, "Coded": 28, "Image": 3},
        "form_mappings": 26,
        "forms": 26,
        "programs": ["Nourish - Pregnancy", "Nourish - Child"],
        "encounter_types": 10,
        "subject_types": [
            {"name": "Beneficiary", "type": "Person"},
            {"name": "Anganwadi", "type": "Individual"},
        ],
        "complexity": "LOW",
        "description": "Simple MCH nutrition program with pregnancy and child tracking at Anganwadi centers.",
    },
    "Sangwari": {
        "concepts": 427,
        "data_types": {"Text": 80, "Date": 22, "Coded": 114, "NA": 151, "Numeric": 54, "Notes": 5, "Time": 1},
        "form_mappings": 28,
        "forms": 26,
        "form_types": {"Encounter": 1, "ProgramEncounterCancellation": 7, "ProgramEncounter": 8, "IndividualEncounterCancellation": 1, "ProgramEnrolment": 5, "ProgramExit": 3, "IndividualProfile": 1},
        "programs": ["Pregnancy Program", "Child Screening Program", "Poshanghar Community Based Severe Malnutrition Care", "Home Based Community Based Severe Malnutrition Care", "TB Program"],
        "encounter_types": 9,
        "subject_types": [{"name": "Individual", "type": "Person"}],
        "complexity": "MEDIUM",
        "description": "AI-generated bundle for nutrition and malnutrition care. 5 programs including TB. Generated using srs-bundle-generator v2.0.0.",
    },
    "BHS Phulwari": {
        "concepts": 71,
        "data_types": {"Numeric": 6, "Text": 12, "Coded": 12, "Date": 4, "PhoneNumber": 1, "QuestionGroup": 1, "Subject": 1, "NA": 34},
        "form_mappings": 10,
        "forms": 10,
        "form_types": {"ProgramEncounterCancellation": 2, "ProgramEncounter": 2, "Encounter": 1, "IndividualProfile": 2, "ProgramExit": 1, "IndividualEncounterCancellation": 1, "ProgramEnrolment": 1},
        "programs": ["Child"],
        "encounter_types": 3,
        "subject_types": [
            {"name": "Individual", "type": "Person"},
            {"name": "Phulwari", "type": "Individual"},
        ],
        "complexity": "LOW",
        "description": "Minimal child care center bundle with just 71 concepts. Good example of a simple, clean bundle.",
    },
}


# =============================================================================
# SECTION 2: AGGREGATE STATISTICS
# =============================================================================

AGGREGATE_STATS = {
    "total_orgs_analyzed": 19,
    "concept_counts": {
        "min": 71,
        "max": 6130,
        "median_approx": 538,
        "total_across_orgs": 17653,
    },
    "form_counts": {
        "min": 1,
        "max": 99,
        "median_approx": 26,
    },
    "program_counts": {
        "min": 0,
        "max": 15,
        "orgs_with_zero_programs": 4,
        "orgs_with_5_plus_programs": 5,
    },
    "rule_counts_across_all_orgs": {
        "decisionRule": 44,
        "visitScheduleRule": 166,
        "validationRule": 78,
        "checklistsRule": 3,
        "editFormRule": 6,
        "feg_rule_skip_logic": 230,
        "fe_rule_element_level": 0,
        "total_rules": 527,
    },
    "orgs_with_rules": {
        "decisionRule": ["APF Odisha", "Animedh Charitable Trust DNH", "IPH Sickle Cell", "Purna Clinic", "MLD Trust", "Goonj", "atul_uat", "Ashwini uat"],
        "visitScheduleRule": ["JK Lakshmi Cement", "Uninhibited", "APF Odisha", "Animedh Charitable Trust DNH", "IPH Sickle Cell", "Purna Clinic", "Gubbachi", "CInI", "JSS", "atul_uat", "Ashwini uat"],
        "validationRule": ["APF Odisha", "Animedh Charitable Trust DNH", "IPH Sickle Cell", "Gubbachi", "CInI", "MLD Trust", "JSS", "Goonj", "atul_uat"],
        "editFormRule": ["Maitrayana", "IPH Sickle Cell", "Goonj", "APF Odisha"],
    },
    "most_common_data_types": [
        "NA (answer options - largest category in every org)",
        "Coded (multi/single select questions)",
        "Text (free text)",
        "Numeric (numbers)",
        "Date",
        "QuestionGroup (repeating groups)",
        "Subject (reference to another subject)",
        "Image/ImageV2",
        "PhoneNumber",
        "File",
        "Location",
        "Duration",
        "Notes",
        "GroupAffiliation",
    ],
}


# =============================================================================
# SECTION 3: COMMON PATTERNS ACROSS ORGS
# =============================================================================

COMMON_PATTERNS = {
    "bundle_file_structure": {
        "required_files": [
            "concepts.json",
            "forms/ (directory with form JSON files)",
            "formMappings.json",
            "encounterTypes.json",
            "programs.json",
            "subjectTypes.json",
            "operationalEncounterTypes.json",
            "operationalPrograms.json",
            "operationalSubjectTypes.json",
            "addressLevelTypes.json",
            "groups.json",
            "groupPrivilege.json",
        ],
        "optional_files": [
            "checklist.json",
            "groupRole.json",
            "individualRelation.json",
            "relationshipType.json",
            "identifierSource.json",
            "messagRule.json",
            "menuItem.json",
            "documentations.json",
            "organisationConfig.json",
            "reportCard.json",
            "reportDashboard.json",
            "groupDashboards.json",
            "ruleDependency.json",
            "translations/ (directory)",
            "extensions/ (directory - HTML, images)",
        ],
        "note": "Every form mapping needs a corresponding form file in forms/",
    },

    "form_types_and_when_used": {
        "IndividualProfile": "Registration form - one per subject type",
        "ProgramEnrolment": "One per program - collects data at program entry",
        "ProgramExit": "One per program - collects data at program exit",
        "ProgramEncounter": "Repeatable visits within a program",
        "ProgramEncounterCancellation": "Cancellation form for scheduled program visits",
        "Encounter": "General encounters not tied to a program",
        "IndividualEncounterCancellation": "Cancellation form for general encounters",
        "ChecklistItem": "Vaccination/immunization checklists",
        "Location": "Location-specific data collection forms",
    },

    "concept_naming_conventions": {
        "answer_options_NA_type": "Short descriptive labels: 'Yes', 'No', 'Normal', 'Abnormal', '1', '2', etc.",
        "question_concepts_Coded": "Full question text as name: 'Has she been dealing with any complications?', 'Was blood examination done'",
        "question_concepts_Numeric": "Measurement names: 'Systolic', 'Diastolic', 'Weight', 'Height', 'Hb', 'Temperature'",
        "question_concepts_Text": "Descriptive labels: 'Other complications?', 'Remarks', 'Address'",
        "voided_naming": "Voided items get suffix: '(voided~<id>)' e.g. 'Action (voided~276410)'",
        "common_prefixes": "Some orgs use domain prefixes like 'ADP_Current patient status', 'ADMISSION DUE TO...'",
        "program_ordering": "Maitrayana uses alphabetical prefixes: 'A_YPI Pragati', 'B_Camp', 'C_Club'",
    },

    "form_structure_patterns": {
        "typical_feg_count": "5-15 form element groups per form",
        "typical_elements_per_feg": "1-20 form elements per group",
        "large_forms": "ANC forms often have 60-80+ elements across 10-15 groups",
        "small_forms": "Cancellation forms typically have 1-3 elements",
        "feg_naming": "Groups represent logical sections: 'Vitals', 'Lab Diagnostics', 'Physical Examination', 'Counselling'",
    },

    "visit_scheduling_patterns": [
        "Monthly recurring visits (Growth Monitoring - schedule next month on specific day)",
        "PNC visit chains (Day 3 -> Day 7 -> Day 14 -> Day 21 -> Day 28 -> Day 42)",
        "Conditional follow-up based on encounter outcomes (SAM -> home visit)",
        "Cancellation rescheduling (if cancelled, schedule same type for next interval)",
        "Daily visits that skip Sundays (attendance tracking)",
        "Bi-annual visits (Albendazole in Feb and Aug)",
        "Post-NRC discharge follow-up visits",
        "Training completion visits (monthly cycle)",
    ],

    "decision_rule_patterns": [
        "Complications builder with multiple condition checks",
        "High-risk assessment from vital signs (BP, Hb, weight)",
        "Referral advice based on clinical thresholds",
        "Treatment recommendations based on lab values",
        "Cross-encounter comparisons (current vs previous ANC data)",
        "Cross-subject lookups (child birth form accesses mother's pregnancy data)",
        "Nutritional status classification (SAM/MAM/Normal)",
    ],

    "validation_rule_patterns": [
        "Overdue visit prevention ('cannot complete overdue visit')",
        "Date range validation (encounter date within schedule month)",
        "Cancel-before-schedule prevention",
        "Duplicate subject prevention (village already exists)",
        "Student count reconciliation (all students must be accounted for)",
    ],

    "skip_logic_patterns": [
        "Simple coded answer visibility (show group if answer is X)",
        "Multi-condition visibility (show if condition A AND (B OR NOT C))",
        "Time-based visibility (show MUAC section only after 180 days)",
        "Cross-encounter visibility (show section based on previous visit BP)",
        "Value-already-filled preservation (never hide if value exists)",
        "Cross-encounter history check (check if any past encounter has specific answer)",
    ],

    "edit_form_rule_patterns": [
        "Time-based edit restriction (cannot edit after 3 days)",
        "Role-based edit restriction (only field supervisor can edit)",
        "Combined time + role restriction",
        "Previous month edit restriction (cannot edit cancelled visits from previous month)",
    ],

    "multi_program_patterns": [
        "MCH split: Separate Pregnancy and Child programs",
        "Referral programs: Mirror programs for referral tracking (e.g. 'Pregnancy' + 'Pregnancy - Referral')",
        "Disease-specific programs: Each condition gets its own program (IPH has 6)",
        "Life cycle programs: Youth development with ordered stages (A_, B_, C_)",
    ],

    "subject_type_patterns": [
        "Person: Human individuals being tracked",
        "Individual: Non-person entities (schools, villages, centers, activities)",
        "Household: Family units containing Person members",
        "Group: Container subjects (Class, Phulwari, Batch) with member subjects",
        "User: Field worker/staff tracking (rare, used by APF Odisha)",
    ],
}


# =============================================================================
# SECTION 4: FORM MAPPING STRUCTURE
# =============================================================================

FORM_MAPPING_STRUCTURE = {
    "description": "Form mappings connect forms to subject types, programs, and encounter types",
    "required_fields": ["uuid", "formUUID", "subjectTypeUUID"],
    "optional_fields": ["programUUID", "encounterTypeUUID", "formType", "formName"],
    "rules": [
        "IndividualProfile forms: only need subjectTypeUUID",
        "ProgramEnrolment/ProgramExit forms: need subjectTypeUUID + programUUID",
        "ProgramEncounter/ProgramEncounterCancellation: need subjectTypeUUID + programUUID + encounterTypeUUID",
        "Encounter/IndividualEncounterCancellation: need subjectTypeUUID + encounterTypeUUID (no programUUID)",
    ],
    "typical_mapping_counts": {
        "per_subject_type": "1 IndividualProfile mapping",
        "per_program": "1 ProgramEnrolment + 1 ProgramExit mapping",
        "per_program_encounter_type": "1 ProgramEncounter + 1 ProgramEncounterCancellation mapping",
        "per_general_encounter_type": "1 Encounter + 1 IndividualEncounterCancellation mapping",
    },
}


# =============================================================================
# SECTION 5: RULE API REFERENCE (from production usage)
# =============================================================================

RULE_API_PATTERNS = {
    "standard_rule_signature": '"use strict";\n({params, imports}) => { ... }',
    "params_fields": {
        "entity": "The current entity (programEncounter, encounter, individual, programEnrolment)",
        "decisions": "Pre-initialized decisions object with encounterDecisions, enrolmentDecisions, registrationDecisions arrays",
        "formElementGroup": "The current FEG (for skip logic rules)",
        "formElement": "The current form element (for element-level rules)",
        "checklistDetails": "Available checklist definitions (for checklist rules)",
        "services": {"individualService": "For cross-subject lookups (getSubjectByUUID)"},
        "user": "Current user info",
        "myUserGroups": "User's group memberships",
        "db": "Realm database access (for edit form rules)",
    },
    "imports_fields": {
        "moment": "Moment.js for date handling",
        "lodash": "Lodash for utilities (_, chain, filter, etc.)",
        "rulesConfig": {
            "RuleCondition": "Fluent condition builder",
            "complicationsBuilder": "Builder for decision outputs (complications, recommendations, referrals)",
            "VisitScheduleBuilder": "Builder for scheduling follow-up visits",
            "FormElementStatus": "Return value for skip logic (uuid, visibility, value)",
        },
        "common": {
            "createValidationError": "Create a validation error message",
            "contains": "Check if array contains value",
        },
        "motherCalculations": "Maternal health calculation utilities",
    },
    "entity_api": {
        "getObservationValue(conceptNameOrUUID)": "Get raw observation value",
        "getObservationReadableValue(conceptNameOrUUID)": "Get human-readable observation value",
        "programEnrolment.getEncountersOfType(typeName)": "Get encounters of specific type in enrolment",
        "programEnrolment.hasCompletedEncounterOfType(typeName)": "Check if encounter type is completed",
        "programEnrolment.getObservationReadableValueInEntireEnrolment(concept)": "Get value across all encounters in enrolment",
        "programEnrolment.lastFulfilledEncounter(type1, type2)": "Get most recent completed encounter of types",
        "programEnrolment.isActive": "Check if enrolment is not exited",
        "individual.groups": "Get group memberships",
        "individual.groupSubjects": "Get group subjects for a group",
        "individual.lowestAddressLevel": "Get the most specific address level",
        "individual.dateOfBirth": "Date of birth",
        "individual.getEncounters()": "Get all encounters for individual",
        "findCancelEncounterObservationReadableValue(concept)": "Get observation from cancellation form",
        "findGroupedObservation(conceptUUID)": "Get QuestionGroup observations",
    },
    "rule_condition_fluent_api": {
        "when.valueInEncounter(concept)": "Check value in current encounter",
        "when.valueInEnrolment(concept)": "Check value in enrolment",
        "when.valueInEntireEnrolment(concept)": "Check value across all encounters in enrolment",
        "when.valueInCancelEncounter(concept)": "Check value in cancellation encounter",
        "when.encounterType.equals(name)": "Check encounter type",
        ".containsAnswerConceptName(name)": "Check if coded answer contains specific option",
        ".containsAnyAnswerConceptName(name1, name2)": "Check if coded answer contains any of specified options",
        ".lessThan(n) / .greaterThan(n)": "Numeric comparisons",
        ".lessThanOrEqualTo(n) / .greaterThanOrEqualTo(n)": "Numeric comparisons inclusive",
        ".is.no / .is.yes": "Boolean checks",
        ".and / .or": "Logical combinators",
        ".matches()": "Execute the condition and return boolean",
    },
    "visit_schedule_builder_api": {
        "scheduleBuilder.add({name, encounterType, earliestDate, maxDate, visitCreationStrategy})": "Add a scheduled visit",
        "scheduleBuilder.getAllUnique(key)": "Get unique scheduled visits",
        "visitCreationStrategy": "'createNew' to always create new visit",
    },
}

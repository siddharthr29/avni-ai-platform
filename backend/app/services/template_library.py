"""Pre-built SRS templates for common NGO implementation domains.

Each template is a complete SRSData dict that can be passed to
bundle_generator.generate_from_srs() to create a full Avni bundle.

Templates include:
1. Maternal & Child Health (MCH)
2. Nutrition (SAM/MAM screening)
3. WASH (Water, Sanitation, Hygiene)
4. Education
5. Livelihoods (SHG/Microfinance)

Each has realistic subject types, programs, encounter types,
forms with proper fields, and common concepts.
"""

from __future__ import annotations

import copy
from typing import Any


# ---------------------------------------------------------------------------
# Template 1: Maternal & Child Health (MCH)
# ---------------------------------------------------------------------------

MCH_TEMPLATE: dict[str, Any] = {
    "orgName": "MCH Program",
    "subjectTypes": [
        {"name": "Mother", "type": "Person"},
        {"name": "Child", "type": "Person"},
        {"name": "Household", "type": "Household"},
    ],
    "programs": [
        {"name": "Pregnancy", "colour": "#E91E63"},
        {"name": "Child Growth Monitoring", "colour": "#4CAF50"},
        {"name": "Immunization", "colour": "#2196F3"},
    ],
    "encounterTypes": [
        "ANC Visit",
        "PNC Visit",
        "Delivery",
        "Growth Monitoring Visit",
        "Immunization Visit",
        "ANC Visit Cancel",
        "PNC Visit Cancel",
        "Growth Monitoring Visit Cancel",
        "Immunization Visit Cancel",
    ],
    "groups": ["Everyone", "ASHA", "ANM", "Supervisor"],
    "addressLevelTypes": [
        {"name": "State", "level": 4},
        {"name": "District", "level": 3, "parent": "State"},
        {"name": "Block", "level": 2, "parent": "District"},
        {"name": "Village", "level": 1, "parent": "Block"},
    ],
    "programEncounterMappings": [
        {"program": "Pregnancy", "encounterTypes": ["ANC Visit", "PNC Visit", "Delivery"]},
        {"program": "Child Growth Monitoring", "encounterTypes": ["Growth Monitoring Visit"]},
        {"program": "Immunization", "encounterTypes": ["Immunization Visit"]},
    ],
    "generalEncounterTypes": [],
    "forms": [
        # ── Mother Registration ──────────────────────────────────────────
        {
            "name": "Mother Registration",
            "formType": "IndividualProfile",
            "groups": [
                {
                    "name": "Basic Details",
                    "fields": [
                        {"name": "Full Name", "dataType": "Text", "mandatory": True},
                        {"name": "Age", "dataType": "Numeric", "mandatory": True, "lowAbsolute": 14, "highAbsolute": 50, "unit": "years"},
                        {"name": "Husband Name", "dataType": "Text", "mandatory": True},
                        {"name": "Phone Number", "dataType": "Text", "mandatory": False},
                        {"name": "Aadhaar Number", "dataType": "Text", "mandatory": False},
                    ],
                },
                {
                    "name": "Medical History",
                    "fields": [
                        {"name": "Blood Group", "dataType": "Coded", "mandatory": False, "type": "SingleSelect",
                         "options": ["A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"]},
                        {"name": "Gravida", "dataType": "Numeric", "mandatory": False, "lowAbsolute": 1, "highAbsolute": 15},
                        {"name": "Parity", "dataType": "Numeric", "mandatory": False, "lowAbsolute": 0, "highAbsolute": 14},
                        {"name": "History of Complications", "dataType": "Coded", "mandatory": False, "type": "MultiSelect",
                         "options": ["None", "Eclampsia", "Preterm delivery", "Stillbirth", "C-section", "Postpartum haemorrhage"]},
                    ],
                },
            ],
        },

        # ── Pregnancy Enrolment ──────────────────────────────────────────
        {
            "name": "Pregnancy Enrolment",
            "formType": "ProgramEnrolment",
            "programName": "Pregnancy",
            "groups": [
                {
                    "name": "Pregnancy Details",
                    "fields": [
                        {"name": "Last Menstrual Period", "dataType": "Date", "mandatory": True},
                        {"name": "Estimated Delivery Date", "dataType": "Date", "mandatory": False},
                        {"name": "High Risk Pregnancy", "dataType": "Coded", "mandatory": True, "type": "SingleSelect",
                         "options": ["Yes", "No"]},
                        {"name": "Registered at PHC", "dataType": "Coded", "mandatory": True, "type": "SingleSelect",
                         "options": ["Yes", "No"]},
                        {"name": "JSY Beneficiary", "dataType": "Coded", "mandatory": False, "type": "SingleSelect",
                         "options": ["Yes", "No"]},
                    ],
                },
            ],
        },

        # ── ANC Visit ────────────────────────────────────────────────────
        {
            "name": "ANC Visit",
            "formType": "ProgramEncounter",
            "programName": "Pregnancy",
            "encounterTypeName": "ANC Visit",
            "groups": [
                {
                    "name": "Vitals",
                    "fields": [
                        {"name": "Weight", "dataType": "Numeric", "mandatory": True, "unit": "kg", "lowAbsolute": 30, "highAbsolute": 150},
                        {"name": "BP Systolic", "dataType": "Numeric", "mandatory": True, "unit": "mmHg", "lowAbsolute": 60, "highAbsolute": 260},
                        {"name": "BP Diastolic", "dataType": "Numeric", "mandatory": True, "unit": "mmHg", "lowAbsolute": 40, "highAbsolute": 160},
                        {"name": "Hemoglobin", "dataType": "Numeric", "mandatory": True, "unit": "g/dL", "lowAbsolute": 4, "highAbsolute": 18},
                    ],
                },
                {
                    "name": "Investigations",
                    "fields": [
                        {"name": "Urine Albumin", "dataType": "Coded", "mandatory": False, "type": "SingleSelect",
                         "options": ["Nil", "Trace", "+", "++", "+++"]},
                        {"name": "Urine Sugar", "dataType": "Coded", "mandatory": False, "type": "SingleSelect",
                         "options": ["Nil", "Trace", "+", "++", "+++"]},
                        {"name": "Foetal Heart Rate", "dataType": "Numeric", "mandatory": False, "unit": "bpm", "lowAbsolute": 100, "highAbsolute": 180},
                        {"name": "Foetal Position", "dataType": "Coded", "mandatory": False, "type": "SingleSelect",
                         "options": ["Cephalic", "Breech", "Transverse", "Not yet determined"]},
                        {"name": "IFA Tablets Given", "dataType": "Coded", "mandatory": True, "type": "SingleSelect",
                         "options": ["Yes", "No"]},
                    ],
                },
            ],
        },

        # ── ANC Visit Cancel ─────────────────────────────────────────────
        {
            "name": "ANC Visit Cancel",
            "formType": "ProgramEncounterCancellation",
            "programName": "Pregnancy",
            "encounterTypeName": "ANC Visit",
            "groups": [
                {
                    "name": "Cancellation Details",
                    "fields": [
                        {"name": "Cancellation Reason", "dataType": "Coded", "mandatory": True, "type": "SingleSelect",
                         "options": ["Unavailable", "Migrated", "Refused", "Delivered elsewhere", "Other"]},
                        {"name": "Other Reason", "dataType": "Text", "mandatory": False},
                    ],
                },
            ],
        },

        # ── Delivery ─────────────────────────────────────────────────────
        {
            "name": "Delivery",
            "formType": "ProgramEncounter",
            "programName": "Pregnancy",
            "encounterTypeName": "Delivery",
            "groups": [
                {
                    "name": "Delivery Information",
                    "fields": [
                        {"name": "Delivery Date", "dataType": "Date", "mandatory": True},
                        {"name": "Delivery Type", "dataType": "Coded", "mandatory": True, "type": "SingleSelect",
                         "options": ["Normal", "Assisted", "C-Section"]},
                        {"name": "Place of Delivery", "dataType": "Coded", "mandatory": True, "type": "SingleSelect",
                         "options": ["Home", "Sub Centre", "PHC", "CHC", "District Hospital", "Private Hospital"]},
                        {"name": "Delivery Outcome", "dataType": "Coded", "mandatory": True, "type": "SingleSelect",
                         "options": ["Live Birth", "Still Birth", "Abortion"]},
                        {"name": "Birth Weight", "dataType": "Numeric", "mandatory": True, "unit": "kg", "lowAbsolute": 0.5, "highAbsolute": 6},
                        {"name": "Gender of Baby", "dataType": "Coded", "mandatory": True, "type": "SingleSelect",
                         "options": ["Male", "Female"]},
                    ],
                },
            ],
        },

        # ── PNC Visit ────────────────────────────────────────────────────
        {
            "name": "PNC Visit",
            "formType": "ProgramEncounter",
            "programName": "Pregnancy",
            "encounterTypeName": "PNC Visit",
            "groups": [
                {
                    "name": "Mother Assessment",
                    "fields": [
                        {"name": "Mother Temperature", "dataType": "Numeric", "mandatory": True, "unit": "F", "lowAbsolute": 95, "highAbsolute": 106},
                        {"name": "Breast Feeding", "dataType": "Coded", "mandatory": True, "type": "SingleSelect",
                         "options": ["Exclusive", "Partial", "Not at all"]},
                        {"name": "Lochia", "dataType": "Coded", "mandatory": False, "type": "SingleSelect",
                         "options": ["Normal", "Foul smelling", "Heavy bleeding"]},
                        {"name": "Danger Signs in Mother", "dataType": "Coded", "mandatory": False, "type": "MultiSelect",
                         "options": ["None", "High fever", "Excessive bleeding", "Convulsions", "Severe headache", "Blurred vision"]},
                    ],
                },
            ],
        },

        # ── PNC Visit Cancel ─────────────────────────────────────────────
        {
            "name": "PNC Visit Cancel",
            "formType": "ProgramEncounterCancellation",
            "programName": "Pregnancy",
            "encounterTypeName": "PNC Visit",
            "groups": [
                {
                    "name": "Cancellation Details",
                    "fields": [
                        {"name": "Cancellation Reason", "dataType": "Coded", "mandatory": True, "type": "SingleSelect",
                         "options": ["Unavailable", "Migrated", "Refused", "Other"]},
                        {"name": "Other Reason", "dataType": "Text", "mandatory": False},
                    ],
                },
            ],
        },

        # ── Child Registration ───────────────────────────────────────────
        {
            "name": "Child Registration",
            "formType": "IndividualProfile",
            "groups": [
                {
                    "name": "Child Details",
                    "fields": [
                        {"name": "Child Name", "dataType": "Text", "mandatory": True},
                        {"name": "Date of Birth", "dataType": "Date", "mandatory": True},
                        {"name": "Gender", "dataType": "Coded", "mandatory": True, "type": "SingleSelect",
                         "options": ["Male", "Female"]},
                        {"name": "Birth Weight", "dataType": "Numeric", "mandatory": True, "unit": "kg", "lowAbsolute": 0.5, "highAbsolute": 6},
                        {"name": "Birth Order", "dataType": "Numeric", "mandatory": False, "lowAbsolute": 1, "highAbsolute": 15},
                    ],
                },
            ],
        },

        # ── Child Growth Monitoring Enrolment ────────────────────────────
        {
            "name": "Child Growth Monitoring Enrolment",
            "formType": "ProgramEnrolment",
            "programName": "Child Growth Monitoring",
            "groups": [
                {
                    "name": "Enrolment Details",
                    "fields": [
                        {"name": "Enrolment Date", "dataType": "Date", "mandatory": True},
                        {"name": "Mother Name", "dataType": "Text", "mandatory": False},
                        {"name": "Referral Source", "dataType": "Coded", "mandatory": False, "type": "SingleSelect",
                         "options": ["ASHA", "Anganwadi", "Self", "PHC", "Other"]},
                    ],
                },
            ],
        },

        # ── Growth Monitoring Visit ──────────────────────────────────────
        {
            "name": "Growth Monitoring Visit",
            "formType": "ProgramEncounter",
            "programName": "Child Growth Monitoring",
            "encounterTypeName": "Growth Monitoring Visit",
            "groups": [
                {
                    "name": "Anthropometry",
                    "fields": [
                        {"name": "Child Weight", "dataType": "Numeric", "mandatory": True, "unit": "kg", "lowAbsolute": 1, "highAbsolute": 40},
                        {"name": "Child Height", "dataType": "Numeric", "mandatory": True, "unit": "cm", "lowAbsolute": 30, "highAbsolute": 150},
                        {"name": "MUAC", "dataType": "Numeric", "mandatory": False, "unit": "cm", "lowAbsolute": 5, "highAbsolute": 25},
                    ],
                },
                {
                    "name": "Feeding Practices",
                    "fields": [
                        {"name": "Currently Breastfeeding", "dataType": "Coded", "mandatory": True, "type": "SingleSelect",
                         "options": ["Yes", "No"]},
                        {"name": "Complementary Feeding Started", "dataType": "Coded", "mandatory": False, "type": "SingleSelect",
                         "options": ["Yes", "No"]},
                        {"name": "Nutritional Status", "dataType": "Coded", "mandatory": False, "type": "SingleSelect",
                         "options": ["Normal", "Moderate Underweight", "Severe Underweight"]},
                    ],
                },
            ],
        },

        # ── Growth Monitoring Visit Cancel ────────────────────────────────
        {
            "name": "Growth Monitoring Visit Cancel",
            "formType": "ProgramEncounterCancellation",
            "programName": "Child Growth Monitoring",
            "encounterTypeName": "Growth Monitoring Visit",
            "groups": [
                {
                    "name": "Cancellation Details",
                    "fields": [
                        {"name": "Cancellation Reason", "dataType": "Coded", "mandatory": True, "type": "SingleSelect",
                         "options": ["Unavailable", "Migrated", "Refused", "Other"]},
                        {"name": "Other Reason", "dataType": "Text", "mandatory": False},
                    ],
                },
            ],
        },

        # ── Immunization Enrolment ───────────────────────────────────────
        {
            "name": "Immunization Enrolment",
            "formType": "ProgramEnrolment",
            "programName": "Immunization",
            "groups": [
                {
                    "name": "Enrolment Details",
                    "fields": [
                        {"name": "Enrolment Date", "dataType": "Date", "mandatory": True},
                        {"name": "Previous Vaccination Status", "dataType": "Coded", "mandatory": False, "type": "SingleSelect",
                         "options": ["Up to date", "Partial", "None"]},
                    ],
                },
            ],
        },

        # ── Immunization Visit ───────────────────────────────────────────
        {
            "name": "Immunization Visit",
            "formType": "ProgramEncounter",
            "programName": "Immunization",
            "encounterTypeName": "Immunization Visit",
            "groups": [
                {
                    "name": "Vaccine Details",
                    "fields": [
                        {"name": "Vaccine Given", "dataType": "Coded", "mandatory": True, "type": "SingleSelect",
                         "options": ["BCG", "OPV-0", "OPV-1", "OPV-2", "OPV-3", "Hepatitis B Birth Dose",
                                     "Pentavalent-1", "Pentavalent-2", "Pentavalent-3",
                                     "Measles-1", "Measles-2", "Vitamin A"]},
                        {"name": "Vaccination Date", "dataType": "Date", "mandatory": True},
                        {"name": "Batch Number", "dataType": "Text", "mandatory": False},
                        {"name": "Next Due Date", "dataType": "Date", "mandatory": False},
                        {"name": "Adverse Event", "dataType": "Coded", "mandatory": False, "type": "SingleSelect",
                         "options": ["None", "Mild fever", "Swelling at site", "Allergic reaction", "Other"]},
                    ],
                },
            ],
        },

        # ── Immunization Visit Cancel ─────────────────────────────────────
        {
            "name": "Immunization Visit Cancel",
            "formType": "ProgramEncounterCancellation",
            "programName": "Immunization",
            "encounterTypeName": "Immunization Visit",
            "groups": [
                {
                    "name": "Cancellation Details",
                    "fields": [
                        {"name": "Cancellation Reason", "dataType": "Coded", "mandatory": True, "type": "SingleSelect",
                         "options": ["Unavailable", "Migrated", "Refused", "Child unwell", "Other"]},
                        {"name": "Other Reason", "dataType": "Text", "mandatory": False},
                    ],
                },
            ],
        },

        # ── Pregnancy Exit ───────────────────────────────────────────────
        {
            "name": "Pregnancy Exit",
            "formType": "ProgramExit",
            "programName": "Pregnancy",
            "groups": [
                {
                    "name": "Exit Details",
                    "fields": [
                        {"name": "Exit Reason", "dataType": "Coded", "mandatory": True, "type": "SingleSelect",
                         "options": ["Delivery completed", "Miscarriage", "Abortion", "Death", "Migrated", "Other"]},
                        {"name": "Exit Date", "dataType": "Date", "mandatory": True},
                    ],
                },
            ],
        },
    ],
}


# ---------------------------------------------------------------------------
# Template 2: Nutrition (SAM/MAM Screening)
# ---------------------------------------------------------------------------

NUTRITION_TEMPLATE: dict[str, Any] = {
    "orgName": "Nutrition Program",
    "subjectTypes": [
        {"name": "Individual", "type": "Person"},
        {"name": "Household", "type": "Household"},
    ],
    "programs": [
        {"name": "SAM Treatment", "colour": "#F44336"},
        {"name": "MAM Treatment", "colour": "#FF9800"},
        {"name": "ICDS Supplementary Nutrition", "colour": "#8BC34A"},
    ],
    "encounterTypes": [
        "Nutrition Screening",
        "SAM Follow-up",
        "MAM Follow-up",
        "Discharge Assessment",
        "ICDS Distribution",
        "SAM Follow-up Cancel",
        "MAM Follow-up Cancel",
    ],
    "groups": ["Everyone", "Anganwadi Worker", "Supervisor", "CDPO"],
    "addressLevelTypes": [
        {"name": "State", "level": 4},
        {"name": "District", "level": 3, "parent": "State"},
        {"name": "ICDS Project", "level": 2, "parent": "District"},
        {"name": "Anganwadi Centre", "level": 1, "parent": "ICDS Project"},
    ],
    "programEncounterMappings": [
        {"program": "SAM Treatment", "encounterTypes": ["SAM Follow-up"]},
        {"program": "MAM Treatment", "encounterTypes": ["MAM Follow-up"]},
        {"program": "ICDS Supplementary Nutrition", "encounterTypes": ["ICDS Distribution"]},
    ],
    "generalEncounterTypes": ["Nutrition Screening", "Discharge Assessment"],
    "forms": [
        # ── Individual Registration ──────────────────────────────────────
        {
            "name": "Individual Registration",
            "formType": "IndividualProfile",
            "groups": [
                {
                    "name": "Demographics",
                    "fields": [
                        {"name": "Full Name", "dataType": "Text", "mandatory": True},
                        {"name": "Date of Birth", "dataType": "Date", "mandatory": True},
                        {"name": "Gender", "dataType": "Coded", "mandatory": True, "type": "SingleSelect",
                         "options": ["Male", "Female"]},
                        {"name": "Father Name", "dataType": "Text", "mandatory": False},
                        {"name": "Mother Name", "dataType": "Text", "mandatory": False},
                        {"name": "Caste Category", "dataType": "Coded", "mandatory": False, "type": "SingleSelect",
                         "options": ["General", "OBC", "SC", "ST"]},
                    ],
                },
            ],
        },

        # ── Nutrition Screening ──────────────────────────────────────────
        {
            "name": "Nutrition Screening",
            "formType": "Encounter",
            "encounterTypeName": "Nutrition Screening",
            "groups": [
                {
                    "name": "Anthropometry",
                    "fields": [
                        {"name": "Weight", "dataType": "Numeric", "mandatory": True, "unit": "kg", "lowAbsolute": 1, "highAbsolute": 50},
                        {"name": "Height", "dataType": "Numeric", "mandatory": True, "unit": "cm", "lowAbsolute": 30, "highAbsolute": 170},
                        {"name": "MUAC", "dataType": "Numeric", "mandatory": True, "unit": "cm", "lowAbsolute": 5, "highAbsolute": 25},
                    ],
                },
                {
                    "name": "Clinical Assessment",
                    "fields": [
                        {"name": "Bilateral Pitting Edema", "dataType": "Coded", "mandatory": True, "type": "SingleSelect",
                         "options": ["None", "Mild (+)", "Moderate (++)", "Severe (+++)"]},
                        {"name": "Weight-for-Height Z-Score", "dataType": "Numeric", "mandatory": False, "lowAbsolute": -5, "highAbsolute": 5},
                        {"name": "Weight-for-Age Z-Score", "dataType": "Numeric", "mandatory": False, "lowAbsolute": -5, "highAbsolute": 5},
                        {"name": "Height-for-Age Z-Score", "dataType": "Numeric", "mandatory": False, "lowAbsolute": -5, "highAbsolute": 5},
                        {"name": "Nutrition Classification", "dataType": "Coded", "mandatory": True, "type": "SingleSelect",
                         "options": ["Normal", "MAM", "SAM", "SAM with complications"]},
                        {"name": "Referred to NRC", "dataType": "Coded", "mandatory": False, "type": "SingleSelect",
                         "options": ["Yes", "No"]},
                    ],
                },
            ],
        },

        # ── SAM Treatment Enrolment ──────────────────────────────────────
        {
            "name": "SAM Treatment Enrolment",
            "formType": "ProgramEnrolment",
            "programName": "SAM Treatment",
            "groups": [
                {
                    "name": "Enrolment Details",
                    "fields": [
                        {"name": "Enrolment Date", "dataType": "Date", "mandatory": True},
                        {"name": "Admission Weight", "dataType": "Numeric", "mandatory": True, "unit": "kg", "lowAbsolute": 1, "highAbsolute": 30},
                        {"name": "Admission MUAC", "dataType": "Numeric", "mandatory": True, "unit": "cm", "lowAbsolute": 5, "highAbsolute": 20},
                        {"name": "Appetite Test Result", "dataType": "Coded", "mandatory": True, "type": "SingleSelect",
                         "options": ["Pass", "Fail"]},
                        {"name": "Medical Complications", "dataType": "Coded", "mandatory": False, "type": "MultiSelect",
                         "options": ["None", "Diarrhoea", "ARI", "Fever", "Skin infection", "TB", "HIV"]},
                    ],
                },
            ],
        },

        # ── SAM Follow-up ───────────────────────────────────────────────
        {
            "name": "SAM Follow-up",
            "formType": "ProgramEncounter",
            "programName": "SAM Treatment",
            "encounterTypeName": "SAM Follow-up",
            "groups": [
                {
                    "name": "Follow-up Assessment",
                    "fields": [
                        {"name": "Current Weight", "dataType": "Numeric", "mandatory": True, "unit": "kg", "lowAbsolute": 1, "highAbsolute": 30},
                        {"name": "Current MUAC", "dataType": "Numeric", "mandatory": True, "unit": "cm", "lowAbsolute": 5, "highAbsolute": 20},
                        {"name": "RUTF Sachets Consumed", "dataType": "Numeric", "mandatory": True, "lowAbsolute": 0, "highAbsolute": 150},
                        {"name": "Weight Gain (g/kg/day)", "dataType": "Numeric", "mandatory": False, "lowAbsolute": -10, "highAbsolute": 30},
                        {"name": "Complications", "dataType": "Coded", "mandatory": False, "type": "MultiSelect",
                         "options": ["None", "Vomiting", "Diarrhoea", "Fever", "Skin rash", "Oedema"]},
                    ],
                },
            ],
        },

        # ── SAM Follow-up Cancel ─────────────────────────────────────────
        {
            "name": "SAM Follow-up Cancel",
            "formType": "ProgramEncounterCancellation",
            "programName": "SAM Treatment",
            "encounterTypeName": "SAM Follow-up",
            "groups": [
                {
                    "name": "Cancellation Details",
                    "fields": [
                        {"name": "Cancellation Reason", "dataType": "Coded", "mandatory": True, "type": "SingleSelect",
                         "options": ["Unavailable", "Migrated", "Refused", "Admitted to NRC", "Death", "Other"]},
                        {"name": "Other Reason", "dataType": "Text", "mandatory": False},
                    ],
                },
            ],
        },

        # ── MAM Treatment Enrolment ──────────────────────────────────────
        {
            "name": "MAM Treatment Enrolment",
            "formType": "ProgramEnrolment",
            "programName": "MAM Treatment",
            "groups": [
                {
                    "name": "Enrolment Details",
                    "fields": [
                        {"name": "Enrolment Date", "dataType": "Date", "mandatory": True},
                        {"name": "Admission Weight", "dataType": "Numeric", "mandatory": True, "unit": "kg", "lowAbsolute": 1, "highAbsolute": 30},
                        {"name": "Admission MUAC", "dataType": "Numeric", "mandatory": True, "unit": "cm", "lowAbsolute": 5, "highAbsolute": 20},
                        {"name": "Supplementary Food Type", "dataType": "Coded", "mandatory": False, "type": "SingleSelect",
                         "options": ["Take Home Ration", "Hot Cooked Meal", "Energy Dense Food"]},
                    ],
                },
            ],
        },

        # ── MAM Follow-up ───────────────────────────────────────────────
        {
            "name": "MAM Follow-up",
            "formType": "ProgramEncounter",
            "programName": "MAM Treatment",
            "encounterTypeName": "MAM Follow-up",
            "groups": [
                {
                    "name": "Follow-up Assessment",
                    "fields": [
                        {"name": "Current Weight", "dataType": "Numeric", "mandatory": True, "unit": "kg", "lowAbsolute": 1, "highAbsolute": 30},
                        {"name": "Current MUAC", "dataType": "Numeric", "mandatory": True, "unit": "cm", "lowAbsolute": 5, "highAbsolute": 20},
                        {"name": "Supplementary Food Received", "dataType": "Coded", "mandatory": True, "type": "SingleSelect",
                         "options": ["Yes", "No"]},
                        {"name": "Nutrition Counselling Done", "dataType": "Coded", "mandatory": False, "type": "SingleSelect",
                         "options": ["Yes", "No"]},
                    ],
                },
            ],
        },

        # ── MAM Follow-up Cancel ─────────────────────────────────────────
        {
            "name": "MAM Follow-up Cancel",
            "formType": "ProgramEncounterCancellation",
            "programName": "MAM Treatment",
            "encounterTypeName": "MAM Follow-up",
            "groups": [
                {
                    "name": "Cancellation Details",
                    "fields": [
                        {"name": "Cancellation Reason", "dataType": "Coded", "mandatory": True, "type": "SingleSelect",
                         "options": ["Unavailable", "Migrated", "Refused", "Other"]},
                        {"name": "Other Reason", "dataType": "Text", "mandatory": False},
                    ],
                },
            ],
        },

        # ── Discharge Assessment ─────────────────────────────────────────
        {
            "name": "Discharge Assessment",
            "formType": "Encounter",
            "encounterTypeName": "Discharge Assessment",
            "groups": [
                {
                    "name": "Discharge Details",
                    "fields": [
                        {"name": "Discharge Weight", "dataType": "Numeric", "mandatory": True, "unit": "kg", "lowAbsolute": 1, "highAbsolute": 30},
                        {"name": "Discharge MUAC", "dataType": "Numeric", "mandatory": True, "unit": "cm", "lowAbsolute": 5, "highAbsolute": 20},
                        {"name": "Discharge Outcome", "dataType": "Coded", "mandatory": True, "type": "SingleSelect",
                         "options": ["Recovered", "Defaulter", "Non-responder", "Death", "Referred"]},
                        {"name": "Duration of Treatment", "dataType": "Numeric", "mandatory": False, "unit": "weeks", "lowAbsolute": 1, "highAbsolute": 52},
                    ],
                },
            ],
        },

        # ── SAM Treatment Exit ───────────────────────────────────────────
        {
            "name": "SAM Treatment Exit",
            "formType": "ProgramExit",
            "programName": "SAM Treatment",
            "groups": [
                {
                    "name": "Exit Details",
                    "fields": [
                        {"name": "Exit Reason", "dataType": "Coded", "mandatory": True, "type": "SingleSelect",
                         "options": ["Recovered", "Defaulter", "Non-responder", "Death", "Referred to hospital", "Other"]},
                        {"name": "Exit Date", "dataType": "Date", "mandatory": True},
                    ],
                },
            ],
        },

        # ── MAM Treatment Exit ───────────────────────────────────────────
        {
            "name": "MAM Treatment Exit",
            "formType": "ProgramExit",
            "programName": "MAM Treatment",
            "groups": [
                {
                    "name": "Exit Details",
                    "fields": [
                        {"name": "Exit Reason", "dataType": "Coded", "mandatory": True, "type": "SingleSelect",
                         "options": ["Recovered", "Defaulter", "Non-responder", "Death", "Upgraded to SAM", "Other"]},
                        {"name": "Exit Date", "dataType": "Date", "mandatory": True},
                    ],
                },
            ],
        },
    ],
}


# ---------------------------------------------------------------------------
# Template 3: WASH (Water, Sanitation, Hygiene)
# ---------------------------------------------------------------------------

WASH_TEMPLATE: dict[str, Any] = {
    "orgName": "WASH Program",
    "subjectTypes": [
        {"name": "Household", "type": "Household"},
        {"name": "Water Source", "type": "Person"},
        {"name": "School", "type": "Person"},
    ],
    "programs": [],
    "encounterTypes": [
        "Household WASH Survey",
        "Water Quality Test",
        "School WASH Audit",
    ],
    "groups": ["Everyone", "Field Worker", "Engineer", "Supervisor"],
    "addressLevelTypes": [
        {"name": "State", "level": 4},
        {"name": "District", "level": 3, "parent": "State"},
        {"name": "Block", "level": 2, "parent": "District"},
        {"name": "Gram Panchayat", "level": 1, "parent": "Block"},
    ],
    "programEncounterMappings": [],
    "generalEncounterTypes": ["Household WASH Survey", "Water Quality Test", "School WASH Audit"],
    "forms": [
        # ── Household Registration ───────────────────────────────────────
        {
            "name": "Household Registration",
            "formType": "IndividualProfile",
            "groups": [
                {
                    "name": "Household Details",
                    "fields": [
                        {"name": "Head of Household", "dataType": "Text", "mandatory": True},
                        {"name": "Number of Members", "dataType": "Numeric", "mandatory": True, "lowAbsolute": 1, "highAbsolute": 30},
                        {"name": "BPL Card", "dataType": "Coded", "mandatory": False, "type": "SingleSelect",
                         "options": ["Yes", "No"]},
                        {"name": "House Type", "dataType": "Coded", "mandatory": False, "type": "SingleSelect",
                         "options": ["Kutcha", "Semi-pucca", "Pucca"]},
                    ],
                },
            ],
        },

        # ── Household WASH Survey ────────────────────────────────────────
        {
            "name": "Household WASH Survey",
            "formType": "Encounter",
            "encounterTypeName": "Household WASH Survey",
            "groups": [
                {
                    "name": "Water",
                    "fields": [
                        {"name": "Primary Water Source", "dataType": "Coded", "mandatory": True, "type": "SingleSelect",
                         "options": ["Piped water", "Hand pump", "Open well", "Borewell", "River/pond", "Tanker", "Packaged water"]},
                        {"name": "Distance to Water Source", "dataType": "Coded", "mandatory": False, "type": "SingleSelect",
                         "options": ["Within premises", "Less than 500m", "500m to 1km", "More than 1km"]},
                        {"name": "Water Treatment Method", "dataType": "Coded", "mandatory": False, "type": "MultiSelect",
                         "options": ["None", "Boiling", "Chlorination", "Alum", "SODIS", "RO/Filter", "Straining"]},
                        {"name": "Water Available Daily", "dataType": "Coded", "mandatory": True, "type": "SingleSelect",
                         "options": ["Yes", "No", "Intermittent"]},
                    ],
                },
                {
                    "name": "Sanitation",
                    "fields": [
                        {"name": "Toilet Type", "dataType": "Coded", "mandatory": True, "type": "SingleSelect",
                         "options": ["No toilet (OD)", "Pit latrine", "VIP latrine", "Pour flush", "Flush toilet", "Twin pit"]},
                        {"name": "Toilet Functional", "dataType": "Coded", "mandatory": False, "type": "SingleSelect",
                         "options": ["Yes", "No", "Partially"]},
                        {"name": "All Members Use Toilet", "dataType": "Coded", "mandatory": False, "type": "SingleSelect",
                         "options": ["Yes", "No"]},
                        {"name": "SBM Beneficiary", "dataType": "Coded", "mandatory": False, "type": "SingleSelect",
                         "options": ["Yes", "No"]},
                    ],
                },
                {
                    "name": "Hygiene",
                    "fields": [
                        {"name": "Handwashing Facility", "dataType": "Coded", "mandatory": True, "type": "SingleSelect",
                         "options": ["None", "Water only", "Water and soap", "Water and ash"]},
                        {"name": "Handwashing Location", "dataType": "Coded", "mandatory": False, "type": "SingleSelect",
                         "options": ["Near toilet", "Near kitchen", "Other", "Not available"]},
                        {"name": "Waste Disposal Method", "dataType": "Coded", "mandatory": False, "type": "SingleSelect",
                         "options": ["Open dumping", "Pit composting", "Municipal collection", "Burning", "Segregation and recycling"]},
                    ],
                },
            ],
        },

        # ── Water Source Registration ────────────────────────────────────
        {
            "name": "Water Source Registration",
            "formType": "IndividualProfile",
            "groups": [
                {
                    "name": "Source Details",
                    "fields": [
                        {"name": "Source Name", "dataType": "Text", "mandatory": True},
                        {"name": "Source Type", "dataType": "Coded", "mandatory": True, "type": "SingleSelect",
                         "options": ["Borewell", "Open well", "Hand pump", "Spring", "Surface water", "Piped supply"]},
                        {"name": "Year of Installation", "dataType": "Numeric", "mandatory": False, "lowAbsolute": 1950, "highAbsolute": 2030},
                        {"name": "Households Served", "dataType": "Numeric", "mandatory": False, "lowAbsolute": 1, "highAbsolute": 5000},
                        {"name": "GPS Latitude", "dataType": "Numeric", "mandatory": False, "lowAbsolute": -90, "highAbsolute": 90},
                        {"name": "GPS Longitude", "dataType": "Numeric", "mandatory": False, "lowAbsolute": -180, "highAbsolute": 180},
                    ],
                },
            ],
        },

        # ── Water Quality Test ───────────────────────────────────────────
        {
            "name": "Water Quality Test",
            "formType": "Encounter",
            "encounterTypeName": "Water Quality Test",
            "groups": [
                {
                    "name": "Physical Parameters",
                    "fields": [
                        {"name": "pH", "dataType": "Numeric", "mandatory": True, "lowAbsolute": 0, "highAbsolute": 14},
                        {"name": "Turbidity", "dataType": "Numeric", "mandatory": True, "unit": "NTU", "lowAbsolute": 0, "highAbsolute": 1000},
                        {"name": "TDS", "dataType": "Numeric", "mandatory": False, "unit": "ppm", "lowAbsolute": 0, "highAbsolute": 5000},
                        {"name": "Colour", "dataType": "Coded", "mandatory": False, "type": "SingleSelect",
                         "options": ["Clear", "Slightly coloured", "Coloured", "Highly coloured"]},
                        {"name": "Odour", "dataType": "Coded", "mandatory": False, "type": "SingleSelect",
                         "options": ["None", "Slight", "Objectionable"]},
                    ],
                },
                {
                    "name": "Chemical Parameters",
                    "fields": [
                        {"name": "Residual Chlorine", "dataType": "Numeric", "mandatory": False, "unit": "mg/L", "lowAbsolute": 0, "highAbsolute": 5},
                        {"name": "Iron", "dataType": "Numeric", "mandatory": False, "unit": "mg/L", "lowAbsolute": 0, "highAbsolute": 50},
                        {"name": "Fluoride", "dataType": "Numeric", "mandatory": False, "unit": "mg/L", "lowAbsolute": 0, "highAbsolute": 20},
                        {"name": "Arsenic", "dataType": "Numeric", "mandatory": False, "unit": "mg/L", "lowAbsolute": 0, "highAbsolute": 1},
                        {"name": "Nitrate", "dataType": "Numeric", "mandatory": False, "unit": "mg/L", "lowAbsolute": 0, "highAbsolute": 500},
                    ],
                },
                {
                    "name": "Bacteriological",
                    "fields": [
                        {"name": "E. coli (MPN/100mL)", "dataType": "Numeric", "mandatory": True, "lowAbsolute": 0, "highAbsolute": 10000},
                        {"name": "Total Coliform (MPN/100mL)", "dataType": "Numeric", "mandatory": False, "lowAbsolute": 0, "highAbsolute": 50000},
                        {"name": "Water Safety", "dataType": "Coded", "mandatory": True, "type": "SingleSelect",
                         "options": ["Safe", "Unsafe - treat before use", "Unsafe - do not use"]},
                    ],
                },
            ],
        },

        # ── School Registration ──────────────────────────────────────────
        {
            "name": "School Registration",
            "formType": "IndividualProfile",
            "groups": [
                {
                    "name": "School Details",
                    "fields": [
                        {"name": "School Name", "dataType": "Text", "mandatory": True},
                        {"name": "School Type", "dataType": "Coded", "mandatory": True, "type": "SingleSelect",
                         "options": ["Government", "Government Aided", "Private", "Kendriya Vidyalaya"]},
                        {"name": "UDISE Code", "dataType": "Text", "mandatory": False},
                        {"name": "Total Students", "dataType": "Numeric", "mandatory": True, "lowAbsolute": 1, "highAbsolute": 5000},
                        {"name": "Total Staff", "dataType": "Numeric", "mandatory": False, "lowAbsolute": 1, "highAbsolute": 300},
                    ],
                },
            ],
        },

        # ── School WASH Audit ────────────────────────────────────────────
        {
            "name": "School WASH Audit",
            "formType": "Encounter",
            "encounterTypeName": "School WASH Audit",
            "groups": [
                {
                    "name": "Water Facilities",
                    "fields": [
                        {"name": "Drinking Water Available", "dataType": "Coded", "mandatory": True, "type": "SingleSelect",
                         "options": ["Yes", "No"]},
                        {"name": "Water Source in School", "dataType": "Coded", "mandatory": False, "type": "SingleSelect",
                         "options": ["Piped", "Hand pump", "Borewell", "Tanker", "None"]},
                        {"name": "Water Purification System", "dataType": "Coded", "mandatory": False, "type": "SingleSelect",
                         "options": ["None", "RO", "UV", "Chlorination", "Other"]},
                    ],
                },
                {
                    "name": "Sanitation Facilities",
                    "fields": [
                        {"name": "Number of Toilets (Boys)", "dataType": "Numeric", "mandatory": True, "lowAbsolute": 0, "highAbsolute": 100},
                        {"name": "Number of Toilets (Girls)", "dataType": "Numeric", "mandatory": True, "lowAbsolute": 0, "highAbsolute": 100},
                        {"name": "Toilets Functional", "dataType": "Coded", "mandatory": True, "type": "SingleSelect",
                         "options": ["All", "Most", "Some", "None"]},
                        {"name": "Menstrual Hygiene Facility", "dataType": "Coded", "mandatory": False, "type": "SingleSelect",
                         "options": ["Yes - vending machine", "Yes - pad disposal", "Both", "None"]},
                    ],
                },
                {
                    "name": "Hygiene",
                    "fields": [
                        {"name": "Handwashing Stations", "dataType": "Numeric", "mandatory": True, "lowAbsolute": 0, "highAbsolute": 50},
                        {"name": "Soap Available", "dataType": "Coded", "mandatory": True, "type": "SingleSelect",
                         "options": ["Yes", "No"]},
                        {"name": "Hygiene Education Conducted", "dataType": "Coded", "mandatory": False, "type": "SingleSelect",
                         "options": ["Yes - regularly", "Yes - occasionally", "No"]},
                    ],
                },
            ],
        },
    ],
}


# ---------------------------------------------------------------------------
# Template 4: Education
# ---------------------------------------------------------------------------

EDUCATION_TEMPLATE: dict[str, Any] = {
    "orgName": "Education Program",
    "subjectTypes": [
        {"name": "Student", "type": "Person"},
        {"name": "School", "type": "Person"},
    ],
    "programs": [
        {"name": "Academic Tracking", "colour": "#3F51B5"},
    ],
    "encounterTypes": [
        "Monthly Assessment",
        "Parent Meeting",
        "School Inspection",
        "Monthly Assessment Cancel",
    ],
    "groups": ["Everyone", "Teacher", "Block Resource Person", "District Coordinator"],
    "addressLevelTypes": [
        {"name": "State", "level": 4},
        {"name": "District", "level": 3, "parent": "State"},
        {"name": "Block", "level": 2, "parent": "District"},
        {"name": "Cluster", "level": 1, "parent": "Block"},
    ],
    "programEncounterMappings": [
        {"program": "Academic Tracking", "encounterTypes": ["Monthly Assessment", "Parent Meeting"]},
    ],
    "generalEncounterTypes": ["School Inspection"],
    "forms": [
        # ── Student Registration ─────────────────────────────────────────
        {
            "name": "Student Registration",
            "formType": "IndividualProfile",
            "groups": [
                {
                    "name": "Personal Details",
                    "fields": [
                        {"name": "Student Name", "dataType": "Text", "mandatory": True},
                        {"name": "Date of Birth", "dataType": "Date", "mandatory": True},
                        {"name": "Gender", "dataType": "Coded", "mandatory": True, "type": "SingleSelect",
                         "options": ["Male", "Female", "Other"]},
                        {"name": "Aadhaar Number", "dataType": "Text", "mandatory": False},
                    ],
                },
                {
                    "name": "Academic Details",
                    "fields": [
                        {"name": "Current Grade", "dataType": "Coded", "mandatory": True, "type": "SingleSelect",
                         "options": ["1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12"]},
                        {"name": "Section", "dataType": "Coded", "mandatory": False, "type": "SingleSelect",
                         "options": ["A", "B", "C", "D"]},
                        {"name": "Medium of Instruction", "dataType": "Coded", "mandatory": False, "type": "SingleSelect",
                         "options": ["Hindi", "English", "Marathi", "Tamil", "Telugu", "Kannada", "Bengali", "Other"]},
                        {"name": "Category", "dataType": "Coded", "mandatory": False, "type": "SingleSelect",
                         "options": ["General", "OBC", "SC", "ST", "EWS"]},
                        {"name": "Disability", "dataType": "Coded", "mandatory": False, "type": "SingleSelect",
                         "options": ["None", "Visual", "Hearing", "Locomotor", "Intellectual", "Multiple"]},
                    ],
                },
                {
                    "name": "Parent/Guardian",
                    "fields": [
                        {"name": "Father Name", "dataType": "Text", "mandatory": False},
                        {"name": "Mother Name", "dataType": "Text", "mandatory": False},
                        {"name": "Guardian Phone", "dataType": "Text", "mandatory": False},
                        {"name": "Annual Family Income", "dataType": "Coded", "mandatory": False, "type": "SingleSelect",
                         "options": ["Below 1 lakh", "1-3 lakh", "3-5 lakh", "Above 5 lakh"]},
                    ],
                },
            ],
        },

        # ── Academic Tracking Enrolment ──────────────────────────────────
        {
            "name": "Academic Tracking Enrolment",
            "formType": "ProgramEnrolment",
            "programName": "Academic Tracking",
            "groups": [
                {
                    "name": "Enrolment Details",
                    "fields": [
                        {"name": "Academic Year", "dataType": "Coded", "mandatory": True, "type": "SingleSelect",
                         "options": ["2024-25", "2025-26", "2026-27"]},
                        {"name": "Enrolment Date", "dataType": "Date", "mandatory": True},
                        {"name": "Previous Year Result", "dataType": "Coded", "mandatory": False, "type": "SingleSelect",
                         "options": ["Promoted", "Detained", "New admission", "Transfer"]},
                        {"name": "Baseline Literacy Level", "dataType": "Coded", "mandatory": False, "type": "SingleSelect",
                         "options": ["Cannot read", "Letter level", "Word level", "Para level", "Story level"]},
                        {"name": "Baseline Numeracy Level", "dataType": "Coded", "mandatory": False, "type": "SingleSelect",
                         "options": ["Cannot recognise numbers", "1-9", "10-99", "Subtraction", "Division"]},
                    ],
                },
            ],
        },

        # ── Monthly Assessment ───────────────────────────────────────────
        {
            "name": "Monthly Assessment",
            "formType": "ProgramEncounter",
            "programName": "Academic Tracking",
            "encounterTypeName": "Monthly Assessment",
            "groups": [
                {
                    "name": "Attendance",
                    "fields": [
                        {"name": "Days Present", "dataType": "Numeric", "mandatory": True, "lowAbsolute": 0, "highAbsolute": 31, "unit": "days"},
                        {"name": "Total Working Days", "dataType": "Numeric", "mandatory": True, "lowAbsolute": 0, "highAbsolute": 31, "unit": "days"},
                    ],
                },
                {
                    "name": "Subject Scores",
                    "fields": [
                        {"name": "Language Score", "dataType": "Numeric", "mandatory": True, "lowAbsolute": 0, "highAbsolute": 100, "unit": "marks"},
                        {"name": "Mathematics Score", "dataType": "Numeric", "mandatory": True, "lowAbsolute": 0, "highAbsolute": 100, "unit": "marks"},
                        {"name": "Science Score", "dataType": "Numeric", "mandatory": False, "lowAbsolute": 0, "highAbsolute": 100, "unit": "marks"},
                        {"name": "Social Studies Score", "dataType": "Numeric", "mandatory": False, "lowAbsolute": 0, "highAbsolute": 100, "unit": "marks"},
                        {"name": "English Score", "dataType": "Numeric", "mandatory": False, "lowAbsolute": 0, "highAbsolute": 100, "unit": "marks"},
                    ],
                },
                {
                    "name": "Teacher Observations",
                    "fields": [
                        {"name": "Learning Level", "dataType": "Coded", "mandatory": False, "type": "SingleSelect",
                         "options": ["Below grade level", "At grade level", "Above grade level"]},
                        {"name": "Behaviour", "dataType": "Coded", "mandatory": False, "type": "SingleSelect",
                         "options": ["Good", "Satisfactory", "Needs improvement"]},
                        {"name": "Remarks", "dataType": "Notes", "mandatory": False},
                    ],
                },
            ],
        },

        # ── Monthly Assessment Cancel ────────────────────────────────────
        {
            "name": "Monthly Assessment Cancel",
            "formType": "ProgramEncounterCancellation",
            "programName": "Academic Tracking",
            "encounterTypeName": "Monthly Assessment",
            "groups": [
                {
                    "name": "Cancellation Details",
                    "fields": [
                        {"name": "Cancellation Reason", "dataType": "Coded", "mandatory": True, "type": "SingleSelect",
                         "options": ["Student absent", "School closed", "Dropped out", "Transferred", "Other"]},
                        {"name": "Other Reason", "dataType": "Text", "mandatory": False},
                    ],
                },
            ],
        },

        # ── Parent Meeting ───────────────────────────────────────────────
        {
            "name": "Parent Meeting",
            "formType": "ProgramEncounter",
            "programName": "Academic Tracking",
            "encounterTypeName": "Parent Meeting",
            "groups": [
                {
                    "name": "Meeting Details",
                    "fields": [
                        {"name": "Meeting Date", "dataType": "Date", "mandatory": True},
                        {"name": "Parent Attended", "dataType": "Coded", "mandatory": True, "type": "SingleSelect",
                         "options": ["Father", "Mother", "Guardian", "None"]},
                        {"name": "Topics Discussed", "dataType": "Coded", "mandatory": False, "type": "MultiSelect",
                         "options": ["Academic performance", "Attendance", "Behaviour", "Health", "Home learning", "Future plans"]},
                        {"name": "Parent Feedback", "dataType": "Notes", "mandatory": False},
                        {"name": "Action Items", "dataType": "Notes", "mandatory": False},
                    ],
                },
            ],
        },

        # ── School Registration ──────────────────────────────────────────
        {
            "name": "School Registration",
            "formType": "IndividualProfile",
            "groups": [
                {
                    "name": "School Information",
                    "fields": [
                        {"name": "School Name", "dataType": "Text", "mandatory": True},
                        {"name": "UDISE Code", "dataType": "Text", "mandatory": False},
                        {"name": "School Type", "dataType": "Coded", "mandatory": True, "type": "SingleSelect",
                         "options": ["Government", "Government Aided", "Private", "Kendriya Vidyalaya", "Navodaya"]},
                        {"name": "Grades Offered", "dataType": "Coded", "mandatory": True, "type": "MultiSelect",
                         "options": ["Primary (1-5)", "Upper Primary (6-8)", "Secondary (9-10)", "Higher Secondary (11-12)"]},
                        {"name": "Total Enrolment", "dataType": "Numeric", "mandatory": True, "lowAbsolute": 1, "highAbsolute": 5000},
                        {"name": "Number of Teachers", "dataType": "Numeric", "mandatory": True, "lowAbsolute": 1, "highAbsolute": 300},
                    ],
                },
            ],
        },

        # ── School Inspection ────────────────────────────────────────────
        {
            "name": "School Inspection",
            "formType": "Encounter",
            "encounterTypeName": "School Inspection",
            "groups": [
                {
                    "name": "Infrastructure",
                    "fields": [
                        {"name": "Classrooms Available", "dataType": "Numeric", "mandatory": True, "lowAbsolute": 1, "highAbsolute": 100},
                        {"name": "Classrooms in Good Condition", "dataType": "Numeric", "mandatory": True, "lowAbsolute": 0, "highAbsolute": 100},
                        {"name": "Drinking Water Available", "dataType": "Coded", "mandatory": True, "type": "SingleSelect",
                         "options": ["Yes", "No"]},
                        {"name": "Functional Toilets", "dataType": "Coded", "mandatory": True, "type": "SingleSelect",
                         "options": ["Adequate", "Inadequate", "None"]},
                        {"name": "Electricity Available", "dataType": "Coded", "mandatory": True, "type": "SingleSelect",
                         "options": ["Yes", "No", "Irregular"]},
                    ],
                },
                {
                    "name": "Academic Assessment",
                    "fields": [
                        {"name": "Teachers Present Today", "dataType": "Numeric", "mandatory": True, "lowAbsolute": 0, "highAbsolute": 300},
                        {"name": "Mid Day Meal Served", "dataType": "Coded", "mandatory": True, "type": "SingleSelect",
                         "options": ["Yes", "No", "Not applicable"]},
                        {"name": "SMC Meeting Conducted", "dataType": "Coded", "mandatory": False, "type": "SingleSelect",
                         "options": ["Yes - this month", "Yes - last month", "No - over 2 months"]},
                        {"name": "Overall Rating", "dataType": "Coded", "mandatory": True, "type": "SingleSelect",
                         "options": ["Excellent", "Good", "Average", "Below Average", "Poor"]},
                        {"name": "Inspector Remarks", "dataType": "Notes", "mandatory": False},
                    ],
                },
            ],
        },

        # ── Academic Tracking Exit ───────────────────────────────────────
        {
            "name": "Academic Tracking Exit",
            "formType": "ProgramExit",
            "programName": "Academic Tracking",
            "groups": [
                {
                    "name": "Exit Details",
                    "fields": [
                        {"name": "Exit Reason", "dataType": "Coded", "mandatory": True, "type": "SingleSelect",
                         "options": ["Promoted", "Completed", "Dropped out", "Transferred", "Other"]},
                        {"name": "Exit Date", "dataType": "Date", "mandatory": True},
                    ],
                },
            ],
        },
    ],
}


# ---------------------------------------------------------------------------
# Template 5: Livelihoods (SHG / Microfinance)
# ---------------------------------------------------------------------------

LIVELIHOODS_TEMPLATE: dict[str, Any] = {
    "orgName": "Livelihoods Program",
    "subjectTypes": [
        {"name": "Individual", "type": "Person"},
        {"name": "SHG", "type": "Group"},
    ],
    "programs": [
        {"name": "SHG Program", "colour": "#9C27B0"},
        {"name": "Skill Training", "colour": "#FF5722"},
    ],
    "encounterTypes": [
        "SHG Meeting",
        "Loan Disbursement",
        "Training Session",
        "Follow-up Visit",
        "SHG Meeting Cancel",
        "Follow-up Visit Cancel",
    ],
    "groups": ["Everyone", "Community Mobilizer", "Block Coordinator", "Project Manager"],
    "addressLevelTypes": [
        {"name": "State", "level": 4},
        {"name": "District", "level": 3, "parent": "State"},
        {"name": "Block", "level": 2, "parent": "District"},
        {"name": "Village", "level": 1, "parent": "Block"},
    ],
    "programEncounterMappings": [
        {"program": "SHG Program", "encounterTypes": ["SHG Meeting", "Loan Disbursement"]},
        {"program": "Skill Training", "encounterTypes": ["Training Session", "Follow-up Visit"]},
    ],
    "generalEncounterTypes": [],
    "forms": [
        # ── Individual Registration ──────────────────────────────────────
        {
            "name": "Individual Registration",
            "formType": "IndividualProfile",
            "groups": [
                {
                    "name": "Personal Details",
                    "fields": [
                        {"name": "Full Name", "dataType": "Text", "mandatory": True},
                        {"name": "Age", "dataType": "Numeric", "mandatory": True, "unit": "years", "lowAbsolute": 18, "highAbsolute": 80},
                        {"name": "Gender", "dataType": "Coded", "mandatory": True, "type": "SingleSelect",
                         "options": ["Male", "Female", "Other"]},
                        {"name": "Marital Status", "dataType": "Coded", "mandatory": False, "type": "SingleSelect",
                         "options": ["Married", "Unmarried", "Widowed", "Divorced"]},
                        {"name": "Phone Number", "dataType": "Text", "mandatory": False},
                        {"name": "Aadhaar Number", "dataType": "Text", "mandatory": False},
                    ],
                },
                {
                    "name": "Socio-Economic Details",
                    "fields": [
                        {"name": "Caste Category", "dataType": "Coded", "mandatory": False, "type": "SingleSelect",
                         "options": ["General", "OBC", "SC", "ST"]},
                        {"name": "Education Level", "dataType": "Coded", "mandatory": False, "type": "SingleSelect",
                         "options": ["Illiterate", "Primary", "Middle", "Secondary", "Higher Secondary", "Graduate", "Post Graduate"]},
                        {"name": "Primary Occupation", "dataType": "Coded", "mandatory": True, "type": "SingleSelect",
                         "options": ["Agriculture", "Agricultural labour", "Non-farm labour", "Livestock", "Self-employed", "Salaried", "Unemployed", "Other"]},
                        {"name": "Monthly Family Income", "dataType": "Numeric", "mandatory": False, "unit": "INR", "lowAbsolute": 0, "highAbsolute": 500000},
                        {"name": "Land Owned", "dataType": "Numeric", "mandatory": False, "unit": "acres", "lowAbsolute": 0, "highAbsolute": 100},
                        {"name": "BPL Card", "dataType": "Coded", "mandatory": False, "type": "SingleSelect",
                         "options": ["Yes", "No"]},
                    ],
                },
            ],
        },

        # ── SHG Registration ────────────────────────────────────────────
        {
            "name": "SHG Registration",
            "formType": "IndividualProfile",
            "groups": [
                {
                    "name": "SHG Details",
                    "fields": [
                        {"name": "SHG Name", "dataType": "Text", "mandatory": True},
                        {"name": "Formation Date", "dataType": "Date", "mandatory": True},
                        {"name": "Number of Members", "dataType": "Numeric", "mandatory": True, "lowAbsolute": 5, "highAbsolute": 20},
                        {"name": "Monthly Savings Amount", "dataType": "Numeric", "mandatory": True, "unit": "INR", "lowAbsolute": 10, "highAbsolute": 5000},
                        {"name": "Meeting Day", "dataType": "Coded", "mandatory": True, "type": "SingleSelect",
                         "options": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]},
                    ],
                },
                {
                    "name": "Bank Details",
                    "fields": [
                        {"name": "Bank Name", "dataType": "Text", "mandatory": True},
                        {"name": "Bank Account Number", "dataType": "Text", "mandatory": True},
                        {"name": "IFSC Code", "dataType": "Text", "mandatory": False},
                        {"name": "Bank Linkage", "dataType": "Coded", "mandatory": False, "type": "SingleSelect",
                         "options": ["Not linked", "Savings linked", "Credit linked", "Both"]},
                        {"name": "Grading", "dataType": "Coded", "mandatory": False, "type": "SingleSelect",
                         "options": ["Not graded", "Grade A", "Grade B", "Grade C"]},
                    ],
                },
            ],
        },

        # ── SHG Program Enrolment ────────────────────────────────────────
        {
            "name": "SHG Program Enrolment",
            "formType": "ProgramEnrolment",
            "programName": "SHG Program",
            "groups": [
                {
                    "name": "Enrolment Details",
                    "fields": [
                        {"name": "Enrolment Date", "dataType": "Date", "mandatory": True},
                        {"name": "Promoted By", "dataType": "Coded", "mandatory": False, "type": "SingleSelect",
                         "options": ["NRLM", "NGO", "Bank", "Self-formed"]},
                        {"name": "Initial Corpus", "dataType": "Numeric", "mandatory": False, "unit": "INR", "lowAbsolute": 0, "highAbsolute": 1000000},
                    ],
                },
            ],
        },

        # ── SHG Meeting ─────────────────────────────────────────────────
        {
            "name": "SHG Meeting",
            "formType": "ProgramEncounter",
            "programName": "SHG Program",
            "encounterTypeName": "SHG Meeting",
            "groups": [
                {
                    "name": "Attendance & Savings",
                    "fields": [
                        {"name": "Members Present", "dataType": "Numeric", "mandatory": True, "lowAbsolute": 0, "highAbsolute": 20},
                        {"name": "Total Members", "dataType": "Numeric", "mandatory": True, "lowAbsolute": 5, "highAbsolute": 20},
                        {"name": "Savings Collected", "dataType": "Numeric", "mandatory": True, "unit": "INR", "lowAbsolute": 0, "highAbsolute": 100000},
                        {"name": "Cumulative Savings", "dataType": "Numeric", "mandatory": False, "unit": "INR", "lowAbsolute": 0, "highAbsolute": 10000000},
                    ],
                },
                {
                    "name": "Loans & Repayment",
                    "fields": [
                        {"name": "Loans Disbursed This Meeting", "dataType": "Numeric", "mandatory": False, "lowAbsolute": 0, "highAbsolute": 10},
                        {"name": "Loan Amount Disbursed", "dataType": "Numeric", "mandatory": False, "unit": "INR", "lowAbsolute": 0, "highAbsolute": 500000},
                        {"name": "Loan Repayment Collected", "dataType": "Numeric", "mandatory": False, "unit": "INR", "lowAbsolute": 0, "highAbsolute": 500000},
                        {"name": "Overdue Amount", "dataType": "Numeric", "mandatory": False, "unit": "INR", "lowAbsolute": 0, "highAbsolute": 1000000},
                        {"name": "Minutes Recorded", "dataType": "Coded", "mandatory": False, "type": "SingleSelect",
                         "options": ["Yes", "No"]},
                    ],
                },
            ],
        },

        # ── SHG Meeting Cancel ───────────────────────────────────────────
        {
            "name": "SHG Meeting Cancel",
            "formType": "ProgramEncounterCancellation",
            "programName": "SHG Program",
            "encounterTypeName": "SHG Meeting",
            "groups": [
                {
                    "name": "Cancellation Details",
                    "fields": [
                        {"name": "Cancellation Reason", "dataType": "Coded", "mandatory": True, "type": "SingleSelect",
                         "options": ["Quorum not met", "Festival/holiday", "Weather", "Members unavailable", "Other"]},
                        {"name": "Other Reason", "dataType": "Text", "mandatory": False},
                    ],
                },
            ],
        },

        # ── Loan Disbursement ────────────────────────────────────────────
        {
            "name": "Loan Disbursement",
            "formType": "ProgramEncounter",
            "programName": "SHG Program",
            "encounterTypeName": "Loan Disbursement",
            "groups": [
                {
                    "name": "Loan Details",
                    "fields": [
                        {"name": "Borrower Name", "dataType": "Text", "mandatory": True},
                        {"name": "Loan Amount", "dataType": "Numeric", "mandatory": True, "unit": "INR", "lowAbsolute": 500, "highAbsolute": 500000},
                        {"name": "Loan Purpose", "dataType": "Coded", "mandatory": True, "type": "SingleSelect",
                         "options": ["Agriculture", "Livestock", "Small business", "Education", "Health", "House repair", "Consumption", "Other"]},
                        {"name": "Interest Rate", "dataType": "Numeric", "mandatory": True, "unit": "%", "lowAbsolute": 0, "highAbsolute": 36},
                        {"name": "Repayment Period", "dataType": "Numeric", "mandatory": True, "unit": "months", "lowAbsolute": 1, "highAbsolute": 60},
                        {"name": "Loan Source", "dataType": "Coded", "mandatory": False, "type": "SingleSelect",
                         "options": ["Internal lending", "Bank loan", "Revolving fund", "CIF"]},
                    ],
                },
            ],
        },

        # ── Skill Training Enrolment ─────────────────────────────────────
        {
            "name": "Skill Training Enrolment",
            "formType": "ProgramEnrolment",
            "programName": "Skill Training",
            "groups": [
                {
                    "name": "Training Details",
                    "fields": [
                        {"name": "Training Domain", "dataType": "Coded", "mandatory": True, "type": "SingleSelect",
                         "options": ["Tailoring", "Food Processing", "Livestock Management", "Vermicomposting",
                                     "Mushroom Cultivation", "Computer Literacy", "Beauty Parlour", "Other"]},
                        {"name": "Training Duration", "dataType": "Numeric", "mandatory": True, "unit": "days", "lowAbsolute": 1, "highAbsolute": 180},
                        {"name": "Training Start Date", "dataType": "Date", "mandatory": True},
                        {"name": "Training Centre", "dataType": "Text", "mandatory": False},
                    ],
                },
            ],
        },

        # ── Training Session ─────────────────────────────────────────────
        {
            "name": "Training Session",
            "formType": "ProgramEncounter",
            "programName": "Skill Training",
            "encounterTypeName": "Training Session",
            "groups": [
                {
                    "name": "Session Details",
                    "fields": [
                        {"name": "Session Topic", "dataType": "Text", "mandatory": True},
                        {"name": "Session Number", "dataType": "Numeric", "mandatory": True, "lowAbsolute": 1, "highAbsolute": 200},
                        {"name": "Attendance", "dataType": "Coded", "mandatory": True, "type": "SingleSelect",
                         "options": ["Present", "Absent", "Late"]},
                        {"name": "Practical Component", "dataType": "Coded", "mandatory": False, "type": "SingleSelect",
                         "options": ["Yes", "No"]},
                        {"name": "Assessment Score", "dataType": "Numeric", "mandatory": False, "lowAbsolute": 0, "highAbsolute": 100, "unit": "marks"},
                    ],
                },
            ],
        },

        # ── Follow-up Visit ──────────────────────────────────────────────
        {
            "name": "Follow-up Visit",
            "formType": "ProgramEncounter",
            "programName": "Skill Training",
            "encounterTypeName": "Follow-up Visit",
            "groups": [
                {
                    "name": "Post-Training Assessment",
                    "fields": [
                        {"name": "Using Skills Learned", "dataType": "Coded", "mandatory": True, "type": "SingleSelect",
                         "options": ["Yes - full time", "Yes - part time", "No"]},
                        {"name": "Monthly Income from Activity", "dataType": "Numeric", "mandatory": False, "unit": "INR", "lowAbsolute": 0, "highAbsolute": 100000},
                        {"name": "Challenges Faced", "dataType": "Coded", "mandatory": False, "type": "MultiSelect",
                         "options": ["None", "Lack of capital", "No market access", "Raw material shortage", "Competition", "Family resistance", "Other"]},
                        {"name": "Support Needed", "dataType": "Coded", "mandatory": False, "type": "MultiSelect",
                         "options": ["None", "Additional training", "Credit linkage", "Market linkage", "Raw material", "Mentoring"]},
                        {"name": "Remarks", "dataType": "Notes", "mandatory": False},
                    ],
                },
            ],
        },

        # ── Follow-up Visit Cancel ───────────────────────────────────────
        {
            "name": "Follow-up Visit Cancel",
            "formType": "ProgramEncounterCancellation",
            "programName": "Skill Training",
            "encounterTypeName": "Follow-up Visit",
            "groups": [
                {
                    "name": "Cancellation Details",
                    "fields": [
                        {"name": "Cancellation Reason", "dataType": "Coded", "mandatory": True, "type": "SingleSelect",
                         "options": ["Unavailable", "Migrated", "Refused", "Other"]},
                        {"name": "Other Reason", "dataType": "Text", "mandatory": False},
                    ],
                },
            ],
        },

        # ── SHG Program Exit ────────────────────────────────────────────
        {
            "name": "SHG Program Exit",
            "formType": "ProgramExit",
            "programName": "SHG Program",
            "groups": [
                {
                    "name": "Exit Details",
                    "fields": [
                        {"name": "Exit Reason", "dataType": "Coded", "mandatory": True, "type": "SingleSelect",
                         "options": ["SHG dissolved", "Member expelled", "Migrated", "Death", "Voluntary exit", "Other"]},
                        {"name": "Exit Date", "dataType": "Date", "mandatory": True},
                    ],
                },
            ],
        },

        # ── Skill Training Exit ──────────────────────────────────────────
        {
            "name": "Skill Training Exit",
            "formType": "ProgramExit",
            "programName": "Skill Training",
            "groups": [
                {
                    "name": "Exit Details",
                    "fields": [
                        {"name": "Exit Reason", "dataType": "Coded", "mandatory": True, "type": "SingleSelect",
                         "options": ["Training completed", "Dropped out", "Migrated", "Other"]},
                        {"name": "Exit Date", "dataType": "Date", "mandatory": True},
                        {"name": "Certification", "dataType": "Coded", "mandatory": False, "type": "SingleSelect",
                         "options": ["Certificate issued", "Not eligible", "Pending"]},
                    ],
                },
            ],
        },
    ],
}


# ---------------------------------------------------------------------------
# Template registry
# ---------------------------------------------------------------------------

_TEMPLATES: dict[str, dict[str, Any]] = {
    "mch": MCH_TEMPLATE,
    "nutrition": NUTRITION_TEMPLATE,
    "wash": WASH_TEMPLATE,
    "education": EDUCATION_TEMPLATE,
    "livelihoods": LIVELIHOODS_TEMPLATE,
}

_TEMPLATE_META: dict[str, dict[str, str]] = {
    "mch": {
        "name": "Maternal & Child Health",
        "description": "ANC/PNC visits, delivery tracking, child growth monitoring, and immunization. "
                       "Designed for ASHA workers and ANMs at PHC/Sub Centre level.",
        "icon": "baby",
    },
    "nutrition": {
        "name": "Nutrition (SAM/MAM Screening)",
        "description": "Community-based management of acute malnutrition. Screening, SAM/MAM treatment, "
                       "RUTF distribution, and ICDS supplementary nutrition. For Anganwadi workers and CDPOs.",
        "icon": "apple",
    },
    "wash": {
        "name": "WASH (Water, Sanitation & Hygiene)",
        "description": "Household WASH surveys, water quality testing, and school WASH audits. "
                       "Covers SBM (Swachh Bharat Mission) indicators and JJM (Jal Jeevan Mission) water source monitoring.",
        "icon": "droplet",
    },
    "education": {
        "name": "Education",
        "description": "Student academic tracking, monthly assessments, parent meetings, and school inspections. "
                       "Supports ASER-style learning level assessments and UDISE integration.",
        "icon": "book",
    },
    "livelihoods": {
        "name": "Livelihoods (SHG / Microfinance)",
        "description": "Self-Help Group management, meeting tracking, savings and loan disbursement, "
                       "skill training, and post-training follow-up. Aligned with NRLM/DAY-NRLM framework.",
        "icon": "briefcase",
    },
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_template_categories() -> list[str]:
    """Return the list of available template domain keys."""
    return list(_TEMPLATES.keys())


def list_templates() -> list[dict[str, Any]]:
    """Return summary metadata for every template (no full SRS payload)."""
    summaries: list[dict[str, Any]] = []
    for key, meta in _TEMPLATE_META.items():
        tpl = _TEMPLATES[key]
        total_fields = sum(
            len(field)
            for form in tpl["forms"]
            for field in [
                [f for g in form["groups"] for f in g["fields"]]
            ]
        )
        summaries.append({
            "domain": key,
            "name": meta["name"],
            "description": meta["description"],
            "icon": meta["icon"],
            "subjectTypes": [s["name"] for s in tpl["subjectTypes"]],
            "programs": [p["name"] for p in tpl.get("programs", [])],
            "formsCount": len(tpl["forms"]),
            "totalFields": total_fields,
            "encounterTypes": tpl.get("encounterTypes", []),
        })
    return summaries


def get_template(domain: str) -> dict[str, Any]:
    """Return the full SRS template dict for *domain*.

    Raises ``KeyError`` if the domain is not found.
    """
    key = domain.lower().replace(" ", "_").replace("-", "_")
    if key not in _TEMPLATES:
        raise KeyError(
            f"Unknown template domain '{domain}'. "
            f"Available: {', '.join(_TEMPLATES.keys())}"
        )
    return copy.deepcopy(_TEMPLATES[key])


def customize_template(domain: str, overrides: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of the template for *domain* with *overrides* merged in.

    Supported override keys:
    - ``orgName``          — replace organisation name
    - ``groups``           — replace user groups list
    - ``addressLevelTypes`` — replace address hierarchy
    - ``addPrograms``      — list of program dicts to append
    - ``removePrograms``   — list of program names to remove
    - ``addEncounterTypes`` — list of encounter type names to append
    - ``removeEncounterTypes`` — list of encounter type names to remove
    - ``addForms``         — list of form dicts to append
    - ``removeForms``      — list of form names to remove

    Any other top-level key present in the template is replaced wholesale.
    """
    tpl = get_template(domain)  # already a deep copy

    # Simple top-level replacements
    for simple_key in ("orgName", "groups", "addressLevelTypes", "subjectTypes"):
        if simple_key in overrides:
            tpl[simple_key] = overrides[simple_key]

    # Additive / subtractive programs
    if "addPrograms" in overrides:
        tpl["programs"].extend(overrides["addPrograms"])
    if "removePrograms" in overrides:
        remove_set = {n.lower() for n in overrides["removePrograms"]}
        tpl["programs"] = [
            p for p in tpl["programs"]
            if p["name"].lower() not in remove_set
        ]

    # Additive / subtractive encounter types
    if "addEncounterTypes" in overrides:
        tpl["encounterTypes"].extend(overrides["addEncounterTypes"])
    if "removeEncounterTypes" in overrides:
        remove_set = {n.lower() for n in overrides["removeEncounterTypes"]}
        tpl["encounterTypes"] = [
            et for et in tpl["encounterTypes"]
            if et.lower() not in remove_set
        ]

    # Additive / subtractive forms
    if "addForms" in overrides:
        tpl["forms"].extend(overrides["addForms"])
    if "removeForms" in overrides:
        remove_set = {n.lower() for n in overrides["removeForms"]}
        tpl["forms"] = [
            f for f in tpl["forms"]
            if f["name"].lower() not in remove_set
        ]

    # programEncounterMappings and generalEncounterTypes overrides
    if "programEncounterMappings" in overrides:
        tpl["programEncounterMappings"] = overrides["programEncounterMappings"]
    if "generalEncounterTypes" in overrides:
        tpl["generalEncounterTypes"] = overrides["generalEncounterTypes"]

    return tpl

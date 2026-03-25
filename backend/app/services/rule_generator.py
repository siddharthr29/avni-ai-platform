"""Avni rule generation engine.

Provides template-based and AI-powered generation of Avni rules across all
rule types: ViewFilter (skip logic), Decision, VisitSchedule, Validation,
Checklist, EnrolmentSummary, Eligibility, and WorklistUpdation.

42 templates covering every Avni rule type with production-quality output.

Rules can be produced in two formats:
  - **declarative** -- JSON-based rules evaluated by the Avni declarative
    rule engine (simpler, no JavaScript required).
  - **javascript** -- Full JS functions executed inside Avni's rule engine
    with access to ``imports.rulesConfig``, ``imports.moment``, and the
    ``params`` object.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from app.services.claude_client import claude_client
from app.services.rule_prompts import RULE_GENERATION_SYSTEM_PROMPT  # noqa: F401

logger = logging.getLogger(__name__)

# Public API -- backward-compatible imports
__all__ = [
    "RULE_TEMPLATES",
    "RULE_GENERATION_SYSTEM_PROMPT",
    "build_declarative_rule",
    "find_matching_templates",
    "get_template_by_id",
    "test_rule",
    "generate_rule",
]

# ---------------------------------------------------------------------------
# Rule templates -- 42 production-quality Avni patterns
# ---------------------------------------------------------------------------

RULE_TEMPLATES: list[dict[str, Any]] = [
    # ---- ViewFilter (Skip Logic) ----
    {
        "id": "skip-logic-coded",
        "name": "Skip Logic - Show when coded field has value",
        "type": "ViewFilter",
        "description": "Show a form element when another coded (single/multi-select) field has a specific answer selected.",
        "complexity": 1,
        "format": "declarative",
        "template": json.dumps(
            {
                "declarativeRule": [
                    {
                        "conditions": [
                            {
                                "compoundRule": {
                                    "conjunction": "And",
                                    "rules": [
                                        {
                                            "lhs": {
                                                "type": "concept",
                                                "scope": "{{scope}}",
                                                "conceptName": "{{trigger_concept_name}}",
                                                "conceptUuid": "{{trigger_concept_uuid}}",
                                                "conceptDataType": "Coded",
                                            },
                                            "operator": "containsAnswerConceptName",
                                            "rhs": {
                                                "type": "answerConcept",
                                                "answerConceptNames": [
                                                    "{{trigger_answer_name}}"
                                                ],
                                                "answerConceptUuids": [
                                                    "{{trigger_answer_uuid}}"
                                                ],
                                            },
                                        }
                                    ],
                                }
                            }
                        ],
                        "actions": [{"actionType": "showFormElement"}],
                    }
                ]
            },
            indent=2,
        ),
        "parameters": [
            "scope",
            "trigger_concept_name",
            "trigger_concept_uuid",
            "trigger_answer_name",
            "trigger_answer_uuid",
        ],
        "example_filled": json.dumps(
            {
                "declarativeRule": [
                    {
                        "conditions": [
                            {
                                "compoundRule": {
                                    "conjunction": "And",
                                    "rules": [
                                        {
                                            "lhs": {
                                                "type": "concept",
                                                "scope": "encounter",
                                                "conceptName": "Type of delivery",
                                                "conceptUuid": "a1b2c3d4-0000-0000-0000-000000000001",
                                                "conceptDataType": "Coded",
                                            },
                                            "operator": "containsAnswerConceptName",
                                            "rhs": {
                                                "type": "answerConcept",
                                                "answerConceptNames": ["Caesarean"],
                                                "answerConceptUuids": [
                                                    "a1b2c3d4-0000-0000-0000-000000000002"
                                                ],
                                            },
                                        }
                                    ],
                                }
                            }
                        ],
                        "actions": [{"actionType": "showFormElement"}],
                    }
                ]
            },
            indent=2,
        ),
        "sectors": ["all"],
    },
    {
        "id": "skip-logic-gender",
        "name": "Skip Logic - Show based on gender",
        "type": "ViewFilter",
        "description": "Show a form element only for a specific gender (e.g. show pregnancy questions only for females).",
        "complexity": 1,
        "format": "javascript",
        "template": (
            "'use strict';\n"
            "({params, imports}) => {\n"
            "    const individual = params.entity;\n"
            "    const formElement = params.formElement;\n"
            "    const statusBuilder = new imports.rulesConfig.FormElementStatusBuilder({\n"
            "        programEncounter: individual,\n"
            "        formElement\n"
            "    });\n"
            "    statusBuilder.show()\n"
            '        .when.valueInRegistration("Gender")\n'
            '        .containsAnswerConceptName("{{gender_value}}");\n'
            "    return statusBuilder.build();\n"
            "};"
        ),
        "parameters": ["gender_value"],
        "example_filled": (
            "'use strict';\n"
            "({params, imports}) => {\n"
            "    const individual = params.entity;\n"
            "    const formElement = params.formElement;\n"
            "    const statusBuilder = new imports.rulesConfig.FormElementStatusBuilder({\n"
            "        programEncounter: individual,\n"
            "        formElement\n"
            "    });\n"
            "    statusBuilder.show()\n"
            '        .when.valueInRegistration("Gender")\n'
            '        .containsAnswerConceptName("Female");\n'
            "    return statusBuilder.build();\n"
            "};"
        ),
        "sectors": ["all"],
    },
    {
        "id": "skip-logic-age",
        "name": "Skip Logic - Show based on age range",
        "type": "ViewFilter",
        "description": "Show a form element only when the individual's age falls within a specific range.",
        "complexity": 2,
        "format": "javascript",
        "template": (
            "'use strict';\n"
            "({params, imports}) => {\n"
            "    const individual = params.entity.individual || params.entity;\n"
            "    const formElement = params.formElement;\n"
            "    const statusBuilder = new imports.rulesConfig.FormElementStatusBuilder({\n"
            "        programEncounter: params.entity,\n"
            "        formElement\n"
            "    });\n"
            "    const ageInYears = individual.getAgeInYears();\n"
            "    statusBuilder.show()\n"
            "        .whenItem(ageInYears >= {{min_age}} && ageInYears <= {{max_age}}).is.truthy;\n"
            "    return statusBuilder.build();\n"
            "};"
        ),
        "parameters": ["min_age", "max_age"],
        "example_filled": (
            "'use strict';\n"
            "({params, imports}) => {\n"
            "    const individual = params.entity.individual || params.entity;\n"
            "    const formElement = params.formElement;\n"
            "    const statusBuilder = new imports.rulesConfig.FormElementStatusBuilder({\n"
            "        programEncounter: params.entity,\n"
            "        formElement\n"
            "    });\n"
            "    const ageInYears = individual.getAgeInYears();\n"
            "    statusBuilder.show()\n"
            "        .whenItem(ageInYears >= 15 && ageInYears <= 49).is.truthy;\n"
            "    return statusBuilder.build();\n"
            "};"
        ),
        "sectors": ["all"],
    },
    {
        "id": "skip-logic-compound",
        "name": "Skip Logic - Compound condition (AND/OR)",
        "type": "ViewFilter",
        "description": "Show a form element when multiple conditions are met (AND) or any condition is met (OR).",
        "complexity": 2,
        "format": "declarative",
        "template": json.dumps(
            {
                "declarativeRule": [
                    {
                        "conditions": [
                            {
                                "compoundRule": {
                                    "conjunction": "{{conjunction}}",
                                    "rules": [
                                        {
                                            "lhs": {
                                                "type": "concept",
                                                "scope": "{{scope}}",
                                                "conceptName": "{{concept_name_1}}",
                                                "conceptUuid": "{{concept_uuid_1}}",
                                                "conceptDataType": "{{data_type_1}}",
                                            },
                                            "operator": "{{operator_1}}",
                                            "rhs": {
                                                "type": "answerConcept",
                                                "answerConceptNames": [
                                                    "{{answer_name_1}}"
                                                ],
                                                "answerConceptUuids": [
                                                    "{{answer_uuid_1}}"
                                                ],
                                            },
                                        },
                                        {
                                            "lhs": {
                                                "type": "concept",
                                                "scope": "{{scope}}",
                                                "conceptName": "{{concept_name_2}}",
                                                "conceptUuid": "{{concept_uuid_2}}",
                                                "conceptDataType": "{{data_type_2}}",
                                            },
                                            "operator": "{{operator_2}}",
                                            "rhs": {
                                                "type": "answerConcept",
                                                "answerConceptNames": [
                                                    "{{answer_name_2}}"
                                                ],
                                                "answerConceptUuids": [
                                                    "{{answer_uuid_2}}"
                                                ],
                                            },
                                        },
                                    ],
                                }
                            }
                        ],
                        "actions": [{"actionType": "showFormElement"}],
                    }
                ]
            },
            indent=2,
        ),
        "parameters": [
            "conjunction",
            "scope",
            "concept_name_1",
            "concept_uuid_1",
            "data_type_1",
            "operator_1",
            "answer_name_1",
            "answer_uuid_1",
            "concept_name_2",
            "concept_uuid_2",
            "data_type_2",
            "operator_2",
            "answer_name_2",
            "answer_uuid_2",
        ],
        "example_filled": json.dumps(
            {
                "declarativeRule": [
                    {
                        "conditions": [
                            {
                                "compoundRule": {
                                    "conjunction": "And",
                                    "rules": [
                                        {
                                            "lhs": {
                                                "type": "concept",
                                                "scope": "encounter",
                                                "conceptName": "Is pregnant",
                                                "conceptUuid": "aaaa-bbbb-cccc-0001",
                                                "conceptDataType": "Coded",
                                            },
                                            "operator": "containsAnswerConceptName",
                                            "rhs": {
                                                "type": "answerConcept",
                                                "answerConceptNames": ["Yes"],
                                                "answerConceptUuids": [
                                                    "aaaa-bbbb-cccc-0002"
                                                ],
                                            },
                                        },
                                        {
                                            "lhs": {
                                                "type": "concept",
                                                "scope": "encounter",
                                                "conceptName": "Trimester",
                                                "conceptUuid": "aaaa-bbbb-cccc-0003",
                                                "conceptDataType": "Coded",
                                            },
                                            "operator": "containsAnswerConceptName",
                                            "rhs": {
                                                "type": "answerConcept",
                                                "answerConceptNames": ["Third"],
                                                "answerConceptUuids": [
                                                    "aaaa-bbbb-cccc-0004"
                                                ],
                                            },
                                        },
                                    ],
                                }
                            }
                        ],
                        "actions": [{"actionType": "showFormElement"}],
                    }
                ]
            },
            indent=2,
        ),
        "sectors": ["all"],
    },
    {
        "id": "skip-logic-numeric-range",
        "name": "Skip Logic - Show when numeric value in range",
        "type": "ViewFilter",
        "description": "Show a form element when a numeric field value falls within a given range.",
        "complexity": 2,
        "format": "declarative",
        "template": json.dumps(
            {
                "declarativeRule": [
                    {
                        "conditions": [
                            {
                                "compoundRule": {
                                    "conjunction": "And",
                                    "rules": [
                                        {
                                            "lhs": {
                                                "type": "concept",
                                                "scope": "{{scope}}",
                                                "conceptName": "{{concept_name}}",
                                                "conceptUuid": "{{concept_uuid}}",
                                                "conceptDataType": "Numeric",
                                            },
                                            "operator": "greaterThan",
                                            "rhs": {
                                                "type": "value",
                                                "value": "{{min_value}}",
                                            },
                                        },
                                        {
                                            "lhs": {
                                                "type": "concept",
                                                "scope": "{{scope}}",
                                                "conceptName": "{{concept_name}}",
                                                "conceptUuid": "{{concept_uuid}}",
                                                "conceptDataType": "Numeric",
                                            },
                                            "operator": "lessThan",
                                            "rhs": {
                                                "type": "value",
                                                "value": "{{max_value}}",
                                            },
                                        },
                                    ],
                                }
                            }
                        ],
                        "actions": [{"actionType": "showFormElement"}],
                    }
                ]
            },
            indent=2,
        ),
        "parameters": [
            "scope",
            "concept_name",
            "concept_uuid",
            "min_value",
            "max_value",
        ],
        "example_filled": json.dumps(
            {
                "declarativeRule": [
                    {
                        "conditions": [
                            {
                                "compoundRule": {
                                    "conjunction": "And",
                                    "rules": [
                                        {
                                            "lhs": {
                                                "type": "concept",
                                                "scope": "encounter",
                                                "conceptName": "Haemoglobin",
                                                "conceptUuid": "aaaa-0001",
                                                "conceptDataType": "Numeric",
                                            },
                                            "operator": "greaterThan",
                                            "rhs": {
                                                "type": "value",
                                                "value": "0",
                                            },
                                        },
                                        {
                                            "lhs": {
                                                "type": "concept",
                                                "scope": "encounter",
                                                "conceptName": "Haemoglobin",
                                                "conceptUuid": "aaaa-0001",
                                                "conceptDataType": "Numeric",
                                            },
                                            "operator": "lessThan",
                                            "rhs": {
                                                "type": "value",
                                                "value": "7",
                                            },
                                        },
                                    ],
                                }
                            }
                        ],
                        "actions": [{"actionType": "showFormElement"}],
                    }
                ]
            },
            indent=2,
        ),
        "sectors": ["all"],
    },
    {
        "id": "skip-logic-multiselect-filter",
        "name": "Skip Logic - Multi-select answer filtering",
        "type": "ViewFilter",
        "description": "Show a form element when a multi-select field contains one or more specific answers.",
        "complexity": 2,
        "format": "javascript",
        "template": (
            "'use strict';\n"
            "({params, imports}) => {\n"
            "    const entity = params.entity;\n"
            "    const formElement = params.formElement;\n"
            "    const statusBuilder = new imports.rulesConfig.FormElementStatusBuilder({\n"
            "        programEncounter: entity,\n"
            "        formElement\n"
            "    });\n"
            "    statusBuilder.show()\n"
            '        .when.valueInEncounter("{{trigger_concept_name}}")\n'
            '        .containsAnswerConceptName("{{trigger_answer_name}}");\n'
            "    return statusBuilder.build();\n"
            "};"
        ),
        "parameters": ["trigger_concept_name", "trigger_answer_name"],
        "example_filled": (
            "'use strict';\n"
            "({params, imports}) => {\n"
            "    const entity = params.entity;\n"
            "    const formElement = params.formElement;\n"
            "    const statusBuilder = new imports.rulesConfig.FormElementStatusBuilder({\n"
            "        programEncounter: entity,\n"
            "        formElement\n"
            "    });\n"
            "    statusBuilder.show()\n"
            '        .when.valueInEncounter("Complications during pregnancy")\n'
            '        .containsAnswerConceptName("Gestational diabetes");\n'
            "    return statusBuilder.build();\n"
            "};"
        ),
        "sectors": ["all"],
    },
    # ---- Decision ----
    {
        "id": "decision-bmi",
        "name": "Decision - Calculate BMI from height and weight",
        "type": "Decision",
        "description": "Calculate Body Mass Index from height (cm) and weight (kg) and classify as underweight/normal/overweight/obese.",
        "complexity": 2,
        "format": "javascript",
        "template": (
            "'use strict';\n"
            "({params, imports}) => {\n"
            "    const encounter = params.entity;\n"
            "    const weight = encounter.getObservationValue('{{weight_concept}}');\n"
            "    const height = encounter.getObservationValue('{{height_concept}}');\n"
            "    const decisions = {encounterDecisions: [], enrolmentDecisions: [], registrationDecisions: []};\n"
            "    if (weight && height && height > 0) {\n"
            "        const heightInMeters = height / 100;\n"
            "        const bmi = weight / (heightInMeters * heightInMeters);\n"
            "        const roundedBmi = Math.round(bmi * 100) / 100;\n"
            "        decisions.encounterDecisions.push({\n"
            "            name: '{{bmi_concept}}',\n"
            "            value: roundedBmi\n"
            "        });\n"
            "        let status;\n"
            "        if (bmi < 18.5) status = 'Underweight';\n"
            "        else if (bmi < 25) status = 'Normal';\n"
            "        else if (bmi < 30) status = 'Overweight';\n"
            "        else status = 'Obese';\n"
            "        decisions.encounterDecisions.push({\n"
            "            name: '{{bmi_status_concept}}',\n"
            "            value: [status]\n"
            "        });\n"
            "    }\n"
            "    return decisions;\n"
            "};"
        ),
        "parameters": [
            "weight_concept",
            "height_concept",
            "bmi_concept",
            "bmi_status_concept",
        ],
        "example_filled": (
            "'use strict';\n"
            "({params, imports}) => {\n"
            "    const encounter = params.entity;\n"
            "    const weight = encounter.getObservationValue('Weight');\n"
            "    const height = encounter.getObservationValue('Height');\n"
            "    const decisions = {encounterDecisions: [], enrolmentDecisions: [], registrationDecisions: []};\n"
            "    if (weight && height && height > 0) {\n"
            "        const heightInMeters = height / 100;\n"
            "        const bmi = weight / (heightInMeters * heightInMeters);\n"
            "        const roundedBmi = Math.round(bmi * 100) / 100;\n"
            "        decisions.encounterDecisions.push({\n"
            "            name: 'BMI',\n"
            "            value: roundedBmi\n"
            "        });\n"
            "        let status;\n"
            "        if (bmi < 18.5) status = 'Underweight';\n"
            "        else if (bmi < 25) status = 'Normal';\n"
            "        else if (bmi < 30) status = 'Overweight';\n"
            "        else status = 'Obese';\n"
            "        decisions.encounterDecisions.push({\n"
            "            name: 'BMI Status',\n"
            "            value: [status]\n"
            "        });\n"
            "    }\n"
            "    return decisions;\n"
            "};"
        ),
        "sectors": ["health", "nutrition"],
    },
    {
        "id": "decision-age-calculation",
        "name": "Decision - Calculate age from date of birth",
        "type": "Decision",
        "description": "Calculate current age in years and months from a date of birth field.",
        "complexity": 2,
        "format": "javascript",
        "template": (
            "'use strict';\n"
            "({params, imports}) => {\n"
            "    const entity = params.entity;\n"
            "    const moment = imports.moment;\n"
            "    const dob = entity.getObservationValue('{{dob_concept}}');\n"
            "    const decisions = {encounterDecisions: [], enrolmentDecisions: [], registrationDecisions: []};\n"
            "    if (dob) {\n"
            "        const dobMoment = moment(dob);\n"
            "        const now = moment();\n"
            "        const ageYears = now.diff(dobMoment, 'years');\n"
            "        const ageMonths = now.diff(dobMoment, 'months');\n"
            "        decisions.encounterDecisions.push({\n"
            "            name: '{{age_years_concept}}',\n"
            "            value: ageYears\n"
            "        });\n"
            "        decisions.encounterDecisions.push({\n"
            "            name: '{{age_months_concept}}',\n"
            "            value: ageMonths\n"
            "        });\n"
            "    }\n"
            "    return decisions;\n"
            "};"
        ),
        "parameters": ["dob_concept", "age_years_concept", "age_months_concept"],
        "example_filled": (
            "'use strict';\n"
            "({params, imports}) => {\n"
            "    const entity = params.entity;\n"
            "    const moment = imports.moment;\n"
            "    const dob = entity.getObservationValue('Date of birth');\n"
            "    const decisions = {encounterDecisions: [], enrolmentDecisions: [], registrationDecisions: []};\n"
            "    if (dob) {\n"
            "        const dobMoment = moment(dob);\n"
            "        const now = moment();\n"
            "        const ageYears = now.diff(dobMoment, 'years');\n"
            "        const ageMonths = now.diff(dobMoment, 'months');\n"
            "        decisions.encounterDecisions.push({\n"
            "            name: 'Age in years',\n"
            "            value: ageYears\n"
            "        });\n"
            "        decisions.encounterDecisions.push({\n"
            "            name: 'Age in months',\n"
            "            value: ageMonths\n"
            "        });\n"
            "    }\n"
            "    return decisions;\n"
            "};"
        ),
        "sectors": ["all"],
    },
    {
        "id": "decision-nutrition-status",
        "name": "Decision - Nutritional status (SAM/MAM/Normal)",
        "type": "Decision",
        "description": "Determine nutritional status based on weight-for-height or MUAC: SAM, MAM, or Normal.",
        "complexity": 3,
        "format": "javascript",
        "template": (
            "'use strict';\n"
            "({params, imports}) => {\n"
            "    const encounter = params.entity;\n"
            "    const muac = encounter.getObservationValue('{{muac_concept}}');\n"
            "    const weightForHeight = encounter.getObservationValue('{{wfh_zscore_concept}}');\n"
            "    const decisions = {encounterDecisions: [], enrolmentDecisions: [], registrationDecisions: []};\n"
            "    let status = 'Normal';\n"
            "    if (muac !== undefined && muac !== null) {\n"
            "        if (muac < {{sam_muac_threshold}}) {\n"
            "            status = 'SAM';\n"
            "        } else if (muac < {{mam_muac_threshold}}) {\n"
            "            status = 'MAM';\n"
            "        }\n"
            "    }\n"
            "    if (weightForHeight !== undefined && weightForHeight !== null) {\n"
            "        if (weightForHeight < -3) {\n"
            "            status = 'SAM';\n"
            "        } else if (weightForHeight < -2 && status !== 'SAM') {\n"
            "            status = 'MAM';\n"
            "        }\n"
            "    }\n"
            "    decisions.encounterDecisions.push({\n"
            "        name: '{{nutrition_status_concept}}',\n"
            "        value: [status]\n"
            "    });\n"
            "    return decisions;\n"
            "};"
        ),
        "parameters": [
            "muac_concept",
            "wfh_zscore_concept",
            "sam_muac_threshold",
            "mam_muac_threshold",
            "nutrition_status_concept",
        ],
        "example_filled": (
            "'use strict';\n"
            "({params, imports}) => {\n"
            "    const encounter = params.entity;\n"
            "    const muac = encounter.getObservationValue('MUAC');\n"
            "    const weightForHeight = encounter.getObservationValue('Weight for Height Z-Score');\n"
            "    const decisions = {encounterDecisions: [], enrolmentDecisions: [], registrationDecisions: []};\n"
            "    let status = 'Normal';\n"
            "    if (muac !== undefined && muac !== null) {\n"
            "        if (muac < 11.5) {\n"
            "            status = 'SAM';\n"
            "        } else if (muac < 12.5) {\n"
            "            status = 'MAM';\n"
            "        }\n"
            "    }\n"
            "    if (weightForHeight !== undefined && weightForHeight !== null) {\n"
            "        if (weightForHeight < -3) {\n"
            "            status = 'SAM';\n"
            "        } else if (weightForHeight < -2 && status !== 'SAM') {\n"
            "            status = 'MAM';\n"
            "        }\n"
            "    }\n"
            "    decisions.encounterDecisions.push({\n"
            "        name: 'Nutritional Status',\n"
            "        value: [status]\n"
            "    });\n"
            "    return decisions;\n"
            "};"
        ),
        "sectors": ["nutrition", "health"],
    },
    {
        "id": "decision-risk-categorization",
        "name": "Decision - Risk categorization from observations",
        "type": "Decision",
        "description": "Categorize risk level (High/Medium/Low) based on multiple observation values and thresholds.",
        "complexity": 3,
        "format": "javascript",
        "template": (
            "'use strict';\n"
            "({params, imports}) => {\n"
            "    const encounter = params.entity;\n"
            "    const decisions = {encounterDecisions: [], enrolmentDecisions: [], registrationDecisions: []};\n"
            "    let riskScore = 0;\n"
            "    const val1 = encounter.getObservationValue('{{risk_factor_1}}');\n"
            "    if (val1 && (Array.isArray(val1) ? val1.includes('{{risk_answer_1}}') : val1 === '{{risk_answer_1}}')) {\n"
            "        riskScore += {{risk_weight_1}};\n"
            "    }\n"
            "    const val2 = encounter.getObservationValue('{{risk_factor_2}}');\n"
            "    if (val2 && (Array.isArray(val2) ? val2.includes('{{risk_answer_2}}') : val2 === '{{risk_answer_2}}')) {\n"
            "        riskScore += {{risk_weight_2}};\n"
            "    }\n"
            "    const val3 = encounter.getObservationValue('{{risk_factor_3}}');\n"
            "    if (val3 && (Array.isArray(val3) ? val3.includes('{{risk_answer_3}}') : val3 === '{{risk_answer_3}}')) {\n"
            "        riskScore += {{risk_weight_3}};\n"
            "    }\n"
            "    let riskLevel;\n"
            "    if (riskScore >= {{high_risk_threshold}}) riskLevel = 'High';\n"
            "    else if (riskScore >= {{medium_risk_threshold}}) riskLevel = 'Medium';\n"
            "    else riskLevel = 'Low';\n"
            "    decisions.encounterDecisions.push({\n"
            "        name: '{{risk_level_concept}}',\n"
            "        value: [riskLevel]\n"
            "    });\n"
            "    return decisions;\n"
            "};"
        ),
        "parameters": [
            "risk_factor_1",
            "risk_answer_1",
            "risk_weight_1",
            "risk_factor_2",
            "risk_answer_2",
            "risk_weight_2",
            "risk_factor_3",
            "risk_answer_3",
            "risk_weight_3",
            "high_risk_threshold",
            "medium_risk_threshold",
            "risk_level_concept",
        ],
        "example_filled": (
            "'use strict';\n"
            "({params, imports}) => {\n"
            "    const encounter = params.entity;\n"
            "    const decisions = {encounterDecisions: [], enrolmentDecisions: [], registrationDecisions: []};\n"
            "    let riskScore = 0;\n"
            "    const val1 = encounter.getObservationValue('Previous pregnancy complications');\n"
            "    if (val1 && (Array.isArray(val1) ? val1.includes('Yes') : val1 === 'Yes')) {\n"
            "        riskScore += 3;\n"
            "    }\n"
            "    const val2 = encounter.getObservationValue('Blood pressure category');\n"
            "    if (val2 && (Array.isArray(val2) ? val2.includes('High') : val2 === 'High')) {\n"
            "        riskScore += 2;\n"
            "    }\n"
            "    const val3 = encounter.getObservationValue('Anaemia status');\n"
            "    if (val3 && (Array.isArray(val3) ? val3.includes('Severe') : val3 === 'Severe')) {\n"
            "        riskScore += 3;\n"
            "    }\n"
            "    let riskLevel;\n"
            "    if (riskScore >= 5) riskLevel = 'High';\n"
            "    else if (riskScore >= 3) riskLevel = 'Medium';\n"
            "    else riskLevel = 'Low';\n"
            "    decisions.encounterDecisions.push({\n"
            "        name: 'Pregnancy Risk Level',\n"
            "        value: [riskLevel]\n"
            "    });\n"
            "    return decisions;\n"
            "};"
        ),
        "sectors": ["health"],
    },
    # ---- VisitSchedule ----
    {
        "id": "visit-schedule-monthly",
        "name": "Visit Schedule - Monthly recurring visits",
        "type": "VisitSchedule",
        "description": "Schedule the next visit a fixed number of days after the current encounter.",
        "complexity": 1,
        "format": "javascript",
        "template": (
            "'use strict';\n"
            "({params, imports}) => {\n"
            "    const scheduleBuilder = new imports.rulesConfig.VisitScheduleBuilder({\n"
            "        programEnrolment: params.entity.programEnrolment\n"
            "    });\n"
            "    const baseDate = params.entity.encounterDateTime || new Date();\n"
            "    scheduleBuilder.add({\n"
            "        name: '{{visit_name}}',\n"
            "        encounterType: '{{encounter_type}}',\n"
            "        earliestDate: imports.moment(baseDate).add({{earliest_days}}, 'days').toDate(),\n"
            "        maxDate: imports.moment(baseDate).add({{max_days}}, 'days').toDate()\n"
            "    });\n"
            "    return scheduleBuilder.getAll();\n"
            "};"
        ),
        "parameters": [
            "visit_name",
            "encounter_type",
            "earliest_days",
            "max_days",
        ],
        "example_filled": (
            "'use strict';\n"
            "({params, imports}) => {\n"
            "    const scheduleBuilder = new imports.rulesConfig.VisitScheduleBuilder({\n"
            "        programEnrolment: params.entity.programEnrolment\n"
            "    });\n"
            "    const baseDate = params.entity.encounterDateTime || new Date();\n"
            "    scheduleBuilder.add({\n"
            "        name: 'Monthly Follow-up',\n"
            "        encounterType: 'Monthly Visit',\n"
            "        earliestDate: imports.moment(baseDate).add(28, 'days').toDate(),\n"
            "        maxDate: imports.moment(baseDate).add(35, 'days').toDate()\n"
            "    });\n"
            "    return scheduleBuilder.getAll();\n"
            "};"
        ),
        "sectors": ["all"],
    },
    {
        "id": "visit-schedule-conditional",
        "name": "Visit Schedule - Conditional frequency (risk-based)",
        "type": "VisitSchedule",
        "description": "Schedule visits at different frequencies based on risk level (e.g. high risk = more frequent visits).",
        "complexity": 3,
        "format": "javascript",
        "template": (
            "'use strict';\n"
            "({params, imports}) => {\n"
            "    const encounter = params.entity;\n"
            "    const scheduleBuilder = new imports.rulesConfig.VisitScheduleBuilder({\n"
            "        programEnrolment: encounter.programEnrolment\n"
            "    });\n"
            "    const moment = imports.moment;\n"
            "    const baseDate = encounter.encounterDateTime || new Date();\n"
            "    const riskLevel = encounter.getObservationValue('{{risk_concept}}');\n"
            "    let earliestDays, maxDays;\n"
            "    if (riskLevel && (Array.isArray(riskLevel) ? riskLevel.includes('{{high_risk_value}}') : riskLevel === '{{high_risk_value}}')) {\n"
            "        earliestDays = {{high_risk_earliest_days}};\n"
            "        maxDays = {{high_risk_max_days}};\n"
            "    } else if (riskLevel && (Array.isArray(riskLevel) ? riskLevel.includes('{{medium_risk_value}}') : riskLevel === '{{medium_risk_value}}')) {\n"
            "        earliestDays = {{medium_risk_earliest_days}};\n"
            "        maxDays = {{medium_risk_max_days}};\n"
            "    } else {\n"
            "        earliestDays = {{low_risk_earliest_days}};\n"
            "        maxDays = {{low_risk_max_days}};\n"
            "    }\n"
            "    scheduleBuilder.add({\n"
            "        name: '{{visit_name}}',\n"
            "        encounterType: '{{encounter_type}}',\n"
            "        earliestDate: moment(baseDate).add(earliestDays, 'days').toDate(),\n"
            "        maxDate: moment(baseDate).add(maxDays, 'days').toDate()\n"
            "    });\n"
            "    return scheduleBuilder.getAll();\n"
            "};"
        ),
        "parameters": [
            "risk_concept",
            "high_risk_value",
            "high_risk_earliest_days",
            "high_risk_max_days",
            "medium_risk_value",
            "medium_risk_earliest_days",
            "medium_risk_max_days",
            "low_risk_earliest_days",
            "low_risk_max_days",
            "visit_name",
            "encounter_type",
        ],
        "example_filled": (
            "'use strict';\n"
            "({params, imports}) => {\n"
            "    const encounter = params.entity;\n"
            "    const scheduleBuilder = new imports.rulesConfig.VisitScheduleBuilder({\n"
            "        programEnrolment: encounter.programEnrolment\n"
            "    });\n"
            "    const moment = imports.moment;\n"
            "    const baseDate = encounter.encounterDateTime || new Date();\n"
            "    const riskLevel = encounter.getObservationValue('Pregnancy Risk Level');\n"
            "    let earliestDays, maxDays;\n"
            "    if (riskLevel && (Array.isArray(riskLevel) ? riskLevel.includes('High') : riskLevel === 'High')) {\n"
            "        earliestDays = 7;\n"
            "        maxDays = 14;\n"
            "    } else if (riskLevel && (Array.isArray(riskLevel) ? riskLevel.includes('Medium') : riskLevel === 'Medium')) {\n"
            "        earliestDays = 14;\n"
            "        maxDays = 21;\n"
            "    } else {\n"
            "        earliestDays = 28;\n"
            "        maxDays = 35;\n"
            "    }\n"
            "    scheduleBuilder.add({\n"
            "        name: 'ANC Follow-up',\n"
            "        encounterType: 'ANC Visit',\n"
            "        earliestDate: moment(baseDate).add(earliestDays, 'days').toDate(),\n"
            "        maxDate: moment(baseDate).add(maxDays, 'days').toDate()\n"
            "    });\n"
            "    return scheduleBuilder.getAll();\n"
            "};"
        ),
        "sectors": ["health"],
    },
    {
        "id": "visit-schedule-cancel-reschedule",
        "name": "Visit Schedule - Cancel and reschedule",
        "type": "VisitSchedule",
        "description": "When a visit is cancelled, automatically schedule a replacement visit after a delay.",
        "complexity": 2,
        "format": "javascript",
        "template": (
            "'use strict';\n"
            "({params, imports}) => {\n"
            "    const encounter = params.entity;\n"
            "    const scheduleBuilder = new imports.rulesConfig.VisitScheduleBuilder({\n"
            "        programEnrolment: encounter.programEnrolment\n"
            "    });\n"
            "    const moment = imports.moment;\n"
            "    const cancelDate = encounter.cancelDateTime || new Date();\n"
            "    scheduleBuilder.add({\n"
            "        name: '{{rescheduled_visit_name}}',\n"
            "        encounterType: '{{encounter_type}}',\n"
            "        earliestDate: moment(cancelDate).add({{reschedule_earliest_days}}, 'days').toDate(),\n"
            "        maxDate: moment(cancelDate).add({{reschedule_max_days}}, 'days').toDate()\n"
            "    });\n"
            "    return scheduleBuilder.getAll();\n"
            "};"
        ),
        "parameters": [
            "rescheduled_visit_name",
            "encounter_type",
            "reschedule_earliest_days",
            "reschedule_max_days",
        ],
        "example_filled": (
            "'use strict';\n"
            "({params, imports}) => {\n"
            "    const encounter = params.entity;\n"
            "    const scheduleBuilder = new imports.rulesConfig.VisitScheduleBuilder({\n"
            "        programEnrolment: encounter.programEnrolment\n"
            "    });\n"
            "    const moment = imports.moment;\n"
            "    const cancelDate = encounter.cancelDateTime || new Date();\n"
            "    scheduleBuilder.add({\n"
            "        name: 'Rescheduled Home Visit',\n"
            "        encounterType: 'Home Visit',\n"
            "        earliestDate: moment(cancelDate).add(3, 'days').toDate(),\n"
            "        maxDate: moment(cancelDate).add(7, 'days').toDate()\n"
            "    });\n"
            "    return scheduleBuilder.getAll();\n"
            "};"
        ),
        "sectors": ["all"],
    },
    # ---- Validation ----
    {
        "id": "validation-numeric-range",
        "name": "Validation - Numeric range check",
        "type": "Validation",
        "description": "Validate that a numeric field value falls within an acceptable range.",
        "complexity": 1,
        "format": "javascript",
        "template": (
            "'use strict';\n"
            "({params, imports}) => {\n"
            "    const encounter = params.entity;\n"
            "    const value = encounter.getObservationValue('{{concept_name}}');\n"
            "    const failures = [];\n"
            "    if (value !== undefined && value !== null) {\n"
            "        if (value < {{min_value}}) {\n"
            "            failures.push(imports.rulesConfig.createValidationError(\n"
            "                '{{concept_name}} must be at least {{min_value}}'\n"
            "            ));\n"
            "        }\n"
            "        if (value > {{max_value}}) {\n"
            "            failures.push(imports.rulesConfig.createValidationError(\n"
            "                '{{concept_name}} must be at most {{max_value}}'\n"
            "            ));\n"
            "        }\n"
            "    }\n"
            "    return failures;\n"
            "};"
        ),
        "parameters": ["concept_name", "min_value", "max_value"],
        "example_filled": (
            "'use strict';\n"
            "({params, imports}) => {\n"
            "    const encounter = params.entity;\n"
            "    const value = encounter.getObservationValue('Haemoglobin');\n"
            "    const failures = [];\n"
            "    if (value !== undefined && value !== null) {\n"
            "        if (value < 2) {\n"
            "            failures.push(imports.rulesConfig.createValidationError(\n"
            "                'Haemoglobin must be at least 2'\n"
            "            ));\n"
            "        }\n"
            "        if (value > 20) {\n"
            "            failures.push(imports.rulesConfig.createValidationError(\n"
            "                'Haemoglobin must be at most 20'\n"
            "            ));\n"
            "        }\n"
            "    }\n"
            "    return failures;\n"
            "};"
        ),
        "sectors": ["all"],
    },
    {
        "id": "validation-date-range",
        "name": "Validation - Date range check",
        "type": "Validation",
        "description": "Validate that a date field is within an acceptable range (e.g. not in the future, within past N days).",
        "complexity": 2,
        "format": "javascript",
        "template": (
            "'use strict';\n"
            "({params, imports}) => {\n"
            "    const encounter = params.entity;\n"
            "    const moment = imports.moment;\n"
            "    const dateValue = encounter.getObservationValue('{{date_concept}}');\n"
            "    const failures = [];\n"
            "    if (dateValue) {\n"
            "        const d = moment(dateValue);\n"
            "        const now = moment();\n"
            "        if (d.isAfter(now)) {\n"
            "            failures.push(imports.rulesConfig.createValidationError(\n"
            "                '{{date_concept}} cannot be in the future'\n"
            "            ));\n"
            "        }\n"
            "        const earliest = moment().subtract({{max_past_days}}, 'days');\n"
            "        if (d.isBefore(earliest)) {\n"
            "            failures.push(imports.rulesConfig.createValidationError(\n"
            "                '{{date_concept}} cannot be more than {{max_past_days}} days in the past'\n"
            "            ));\n"
            "        }\n"
            "    }\n"
            "    return failures;\n"
            "};"
        ),
        "parameters": ["date_concept", "max_past_days"],
        "example_filled": (
            "'use strict';\n"
            "({params, imports}) => {\n"
            "    const encounter = params.entity;\n"
            "    const moment = imports.moment;\n"
            "    const dateValue = encounter.getObservationValue('Date of last menstrual period');\n"
            "    const failures = [];\n"
            "    if (dateValue) {\n"
            "        const d = moment(dateValue);\n"
            "        const now = moment();\n"
            "        if (d.isAfter(now)) {\n"
            "            failures.push(imports.rulesConfig.createValidationError(\n"
            "                'Date of last menstrual period cannot be in the future'\n"
            "            ));\n"
            "        }\n"
            "        const earliest = moment().subtract(280, 'days');\n"
            "        if (d.isBefore(earliest)) {\n"
            "            failures.push(imports.rulesConfig.createValidationError(\n"
            "                'Date of last menstrual period cannot be more than 280 days in the past'\n"
            "            ));\n"
            "        }\n"
            "    }\n"
            "    return failures;\n"
            "};"
        ),
        "sectors": ["health"],
    },
    {
        "id": "validation-cross-field",
        "name": "Validation - Cross-field validation",
        "type": "Validation",
        "description": "Validate that two fields are consistent (e.g. discharge date must be after admission date).",
        "complexity": 2,
        "format": "javascript",
        "template": (
            "'use strict';\n"
            "({params, imports}) => {\n"
            "    const encounter = params.entity;\n"
            "    const moment = imports.moment;\n"
            "    const val1 = encounter.getObservationValue('{{concept_1}}');\n"
            "    const val2 = encounter.getObservationValue('{{concept_2}}');\n"
            "    const failures = [];\n"
            "    if (val1 && val2) {\n"
            "        if (moment(val2).isBefore(moment(val1))) {\n"
            "            failures.push(imports.rulesConfig.createValidationError(\n"
            "                '{{concept_2}} must be on or after {{concept_1}}'\n"
            "            ));\n"
            "        }\n"
            "    }\n"
            "    return failures;\n"
            "};"
        ),
        "parameters": ["concept_1", "concept_2"],
        "example_filled": (
            "'use strict';\n"
            "({params, imports}) => {\n"
            "    const encounter = params.entity;\n"
            "    const moment = imports.moment;\n"
            "    const val1 = encounter.getObservationValue('Admission date');\n"
            "    const val2 = encounter.getObservationValue('Discharge date');\n"
            "    const failures = [];\n"
            "    if (val1 && val2) {\n"
            "        if (moment(val2).isBefore(moment(val1))) {\n"
            "            failures.push(imports.rulesConfig.createValidationError(\n"
            "                'Discharge date must be on or after Admission date'\n"
            "            ));\n"
            "        }\n"
            "    }\n"
            "    return failures;\n"
            "};"
        ),
        "sectors": ["all"],
    },
    # ---- Eligibility ----
    {
        "id": "eligibility-age-gender",
        "name": "Eligibility - Age and gender based program eligibility",
        "type": "Eligibility",
        "description": "Determine if an individual is eligible for a program based on age range and gender.",
        "complexity": 2,
        "format": "javascript",
        "template": (
            "'use strict';\n"
            "({params, imports}) => {\n"
            "    const individual = params.entity;\n"
            "    const ageInYears = individual.getAgeInYears();\n"
            "    const gender = individual.getObservationReadableValue('Gender');\n"
            "    let eligible = true;\n"
            "    if (ageInYears < {{min_age}} || ageInYears > {{max_age}}) {\n"
            "        eligible = false;\n"
            "    }\n"
            "    if ('{{required_gender}}' !== 'Any' && gender !== '{{required_gender}}') {\n"
            "        eligible = false;\n"
            "    }\n"
            "    return eligible;\n"
            "};"
        ),
        "parameters": ["min_age", "max_age", "required_gender"],
        "example_filled": (
            "'use strict';\n"
            "({params, imports}) => {\n"
            "    const individual = params.entity;\n"
            "    const ageInYears = individual.getAgeInYears();\n"
            "    const gender = individual.getObservationReadableValue('Gender');\n"
            "    let eligible = true;\n"
            "    if (ageInYears < 15 || ageInYears > 49) {\n"
            "        eligible = false;\n"
            "    }\n"
            "    if ('Female' !== 'Any' && gender !== 'Female') {\n"
            "        eligible = false;\n"
            "    }\n"
            "    return eligible;\n"
            "};"
        ),
        "sectors": ["health"],
    },
    {
        "id": "eligibility-enrolment-check",
        "name": "Eligibility - Enrollment status check",
        "type": "Eligibility",
        "description": "Check if an individual is not already enrolled in the program before allowing enrollment.",
        "complexity": 2,
        "format": "javascript",
        "template": (
            "'use strict';\n"
            "({params, imports}) => {\n"
            "    const individual = params.entity;\n"
            "    const activeEnrolments = individual.enrolments.filter(\n"
            "        e => !e.programExitDateTime && e.program.name === '{{program_name}}'\n"
            "    );\n"
            "    return activeEnrolments.length === 0;\n"
            "};"
        ),
        "parameters": ["program_name"],
        "example_filled": (
            "'use strict';\n"
            "({params, imports}) => {\n"
            "    const individual = params.entity;\n"
            "    const activeEnrolments = individual.enrolments.filter(\n"
            "        e => !e.programExitDateTime && e.program.name === 'Pregnancy Program'\n"
            "    );\n"
            "    return activeEnrolments.length === 0;\n"
            "};"
        ),
        "sectors": ["all"],
    },
    # ---- Checklist ----
    {
        "id": "checklist-vaccination",
        "name": "Checklist - Vaccination checklist",
        "type": "Checklist",
        "description": "Generate a vaccination checklist with due dates calculated from date of birth or enrollment date.",
        "complexity": 3,
        "format": "javascript",
        "template": (
            "'use strict';\n"
            "({params, imports}) => {\n"
            "    const enrolment = params.entity;\n"
            "    const moment = imports.moment;\n"
            "    const checklistDetails = [];\n"
            "    const baseDate = enrolment.individual.dateOfBirth || enrolment.enrolmentDateTime;\n"
            "    const vaccines = [\n"
            "        {name: '{{vaccine_1}}', dueDays: {{vaccine_1_due_days}}, maxDays: {{vaccine_1_max_days}}},\n"
            "        {name: '{{vaccine_2}}', dueDays: {{vaccine_2_due_days}}, maxDays: {{vaccine_2_max_days}}},\n"
            "        {name: '{{vaccine_3}}', dueDays: {{vaccine_3_due_days}}, maxDays: {{vaccine_3_max_days}}}\n"
            "    ];\n"
            "    const items = vaccines.map(v => ({\n"
            "        name: v.name,\n"
            "        dueDate: moment(baseDate).add(v.dueDays, 'days').toDate(),\n"
            "        maxDate: moment(baseDate).add(v.maxDays, 'days').toDate()\n"
            "    }));\n"
            "    return {\n"
            "        name: '{{checklist_name}}',\n"
            "        items: items\n"
            "    };\n"
            "};"
        ),
        "parameters": [
            "checklist_name",
            "vaccine_1",
            "vaccine_1_due_days",
            "vaccine_1_max_days",
            "vaccine_2",
            "vaccine_2_due_days",
            "vaccine_2_max_days",
            "vaccine_3",
            "vaccine_3_due_days",
            "vaccine_3_max_days",
        ],
        "example_filled": (
            "'use strict';\n"
            "({params, imports}) => {\n"
            "    const enrolment = params.entity;\n"
            "    const moment = imports.moment;\n"
            "    const checklistDetails = [];\n"
            "    const baseDate = enrolment.individual.dateOfBirth || enrolment.enrolmentDateTime;\n"
            "    const vaccines = [\n"
            "        {name: 'BCG', dueDays: 0, maxDays: 365},\n"
            "        {name: 'OPV-1', dueDays: 42, maxDays: 365},\n"
            "        {name: 'Pentavalent-1', dueDays: 42, maxDays: 365}\n"
            "    ];\n"
            "    const items = vaccines.map(v => ({\n"
            "        name: v.name,\n"
            "        dueDate: moment(baseDate).add(v.dueDays, 'days').toDate(),\n"
            "        maxDate: moment(baseDate).add(v.maxDays, 'days').toDate()\n"
            "    }));\n"
            "    return {\n"
            "        name: 'Childhood Vaccination Schedule',\n"
            "        items: items\n"
            "    };\n"
            "};"
        ),
        "sectors": ["health"],
    },
    # ---- EnrolmentSummary ----
    {
        "id": "enrolment-summary-key-metrics",
        "name": "Enrolment Summary - Key metrics display",
        "type": "EnrolmentSummary",
        "description": "Display key metrics from enrollment and latest encounter observations in the program summary view.",
        "complexity": 2,
        "format": "javascript",
        "template": (
            "'use strict';\n"
            "({params, imports}) => {\n"
            "    const enrolment = params.entity;\n"
            "    const summaryItems = [];\n"
            "    const enrolmentValue1 = enrolment.getObservationValue('{{enrolment_concept_1}}');\n"
            "    if (enrolmentValue1 !== undefined && enrolmentValue1 !== null) {\n"
            "        summaryItems.push({\n"
            "            name: '{{enrolment_concept_1}}',\n"
            "            value: Array.isArray(enrolmentValue1) ? enrolmentValue1.join(', ') : String(enrolmentValue1),\n"
            "            abnormal: false\n"
            "        });\n"
            "    }\n"
            "    const latestEncounter = enrolment.findLatestObservationInEntireEnrolment('{{encounter_concept_1}}');\n"
            "    if (latestEncounter !== undefined && latestEncounter !== null) {\n"
            "        summaryItems.push({\n"
            "            name: '{{encounter_concept_1}}',\n"
            "            value: Array.isArray(latestEncounter) ? latestEncounter.join(', ') : String(latestEncounter),\n"
            "            abnormal: {{encounter_concept_1_abnormal_check}}\n"
            "        });\n"
            "    }\n"
            "    return summaryItems;\n"
            "};"
        ),
        "parameters": [
            "enrolment_concept_1",
            "encounter_concept_1",
            "encounter_concept_1_abnormal_check",
        ],
        "example_filled": (
            "'use strict';\n"
            "({params, imports}) => {\n"
            "    const enrolment = params.entity;\n"
            "    const summaryItems = [];\n"
            "    const enrolmentValue1 = enrolment.getObservationValue('Last menstrual period');\n"
            "    if (enrolmentValue1 !== undefined && enrolmentValue1 !== null) {\n"
            "        summaryItems.push({\n"
            "            name: 'Last menstrual period',\n"
            "            value: Array.isArray(enrolmentValue1) ? enrolmentValue1.join(', ') : String(enrolmentValue1),\n"
            "            abnormal: false\n"
            "        });\n"
            "    }\n"
            "    const latestEncounter = enrolment.findLatestObservationInEntireEnrolment('Haemoglobin');\n"
            "    if (latestEncounter !== undefined && latestEncounter !== null) {\n"
            "        summaryItems.push({\n"
            "            name: 'Haemoglobin',\n"
            "            value: Array.isArray(latestEncounter) ? latestEncounter.join(', ') : String(latestEncounter),\n"
            "            abnormal: latestEncounter < 7\n"
            "        });\n"
            "    }\n"
            "    return summaryItems;\n"
            "};"
        ),
        "sectors": ["health"],
    },
    # ---- Referral Logic ----
    {
        "id": "decision-referral",
        "name": "Decision - Referral based on conditions",
        "type": "Decision",
        "description": "Generate a referral decision when specific danger signs or conditions are observed.",
        "complexity": 3,
        "format": "javascript",
        "template": (
            "'use strict';\n"
            "({params, imports}) => {\n"
            "    const encounter = params.entity;\n"
            "    const decisions = {encounterDecisions: [], enrolmentDecisions: [], registrationDecisions: []};\n"
            "    const dangerSigns = encounter.getObservationValue('{{danger_signs_concept}}');\n"
            "    const referralReasons = [];\n"
            "    const criticalSigns = [{{critical_signs_list}}];\n"
            "    if (dangerSigns && Array.isArray(dangerSigns)) {\n"
            "        criticalSigns.forEach(sign => {\n"
            "            if (dangerSigns.includes(sign)) {\n"
            "                referralReasons.push(sign);\n"
            "            }\n"
            "        });\n"
            "    }\n"
            "    if (referralReasons.length > 0) {\n"
            "        decisions.encounterDecisions.push({\n"
            "            name: '{{refer_concept}}',\n"
            "            value: ['Yes']\n"
            "        });\n"
            "        decisions.encounterDecisions.push({\n"
            "            name: '{{referral_reason_concept}}',\n"
            "            value: referralReasons\n"
            "        });\n"
            "    } else {\n"
            "        decisions.encounterDecisions.push({\n"
            "            name: '{{refer_concept}}',\n"
            "            value: ['No']\n"
            "        });\n"
            "    }\n"
            "    return decisions;\n"
            "};"
        ),
        "parameters": [
            "danger_signs_concept",
            "critical_signs_list",
            "refer_concept",
            "referral_reason_concept",
        ],
        "example_filled": (
            "'use strict';\n"
            "({params, imports}) => {\n"
            "    const encounter = params.entity;\n"
            "    const decisions = {encounterDecisions: [], enrolmentDecisions: [], registrationDecisions: []};\n"
            "    const dangerSigns = encounter.getObservationValue('Danger signs');\n"
            "    const referralReasons = [];\n"
            "    const criticalSigns = ['Convulsions', 'Severe bleeding', 'High fever', 'Unconscious'];\n"
            "    if (dangerSigns && Array.isArray(dangerSigns)) {\n"
            "        criticalSigns.forEach(sign => {\n"
            "            if (dangerSigns.includes(sign)) {\n"
            "                referralReasons.push(sign);\n"
            "            }\n"
            "        });\n"
            "    }\n"
            "    if (referralReasons.length > 0) {\n"
            "        decisions.encounterDecisions.push({\n"
            "            name: 'Refer to facility',\n"
            "            value: ['Yes']\n"
            "        });\n"
            "        decisions.encounterDecisions.push({\n"
            "            name: 'Referral reason',\n"
            "            value: referralReasons\n"
            "        });\n"
            "    } else {\n"
            "        decisions.encounterDecisions.push({\n"
            "            name: 'Refer to facility',\n"
            "            value: ['No']\n"
            "        });\n"
            "    }\n"
            "    return decisions;\n"
            "};"
        ),
        "sectors": ["health"],
    },
    # ---- Attendance / Edit Handler ----
    {
        "id": "viewfilter-attendance",
        "name": "ViewFilter - Attendance marking pattern",
        "type": "ViewFilter",
        "description": "Show attendance-related fields (absence reason, etc.) only when a member is marked absent.",
        "complexity": 2,
        "format": "javascript",
        "template": (
            "'use strict';\n"
            "({params, imports}) => {\n"
            "    const entity = params.entity;\n"
            "    const formElement = params.formElement;\n"
            "    const statusBuilder = new imports.rulesConfig.FormElementStatusBuilder({\n"
            "        programEncounter: entity,\n"
            "        formElement\n"
            "    });\n"
            "    statusBuilder.show()\n"
            '        .when.valueInEncounter("{{attendance_concept}}")\n'
            '        .containsAnswerConceptName("{{absent_answer}}");\n'
            "    return statusBuilder.build();\n"
            "};"
        ),
        "parameters": ["attendance_concept", "absent_answer"],
        "example_filled": (
            "'use strict';\n"
            "({params, imports}) => {\n"
            "    const entity = params.entity;\n"
            "    const formElement = params.formElement;\n"
            "    const statusBuilder = new imports.rulesConfig.FormElementStatusBuilder({\n"
            "        programEncounter: entity,\n"
            "        formElement\n"
            "    });\n"
            "    statusBuilder.show()\n"
            '        .when.valueInEncounter("Attendance")\n'
            '        .containsAnswerConceptName("Absent");\n'
            "    return statusBuilder.build();\n"
            "};"
        ),
        "sectors": ["education", "all"],
    },
    {
        "id": "viewfilter-edit-handler",
        "name": "ViewFilter - Edit handler (disable on edit)",
        "type": "ViewFilter",
        "description": "Make certain form elements read-only when the form is being edited (not a new entry).",
        "complexity": 2,
        "format": "javascript",
        "template": (
            "'use strict';\n"
            "({params, imports}) => {\n"
            "    const entity = params.entity;\n"
            "    const formElement = params.formElement;\n"
            "    const statusBuilder = new imports.rulesConfig.FormElementStatusBuilder({\n"
            "        programEncounter: entity,\n"
            "        formElement\n"
            "    });\n"
            "    const isEdit = entity.uuid !== undefined && entity.uuid !== null;\n"
            "    if (isEdit) {\n"
            "        statusBuilder.show().is.truthy;\n"
            "    }\n"
            "    const status = statusBuilder.build();\n"
            "    if (isEdit) {\n"
            "        status.editable = false;\n"
            "    }\n"
            "    return status;\n"
            "};"
        ),
        "parameters": [],
        "example_filled": (
            "'use strict';\n"
            "({params, imports}) => {\n"
            "    const entity = params.entity;\n"
            "    const formElement = params.formElement;\n"
            "    const statusBuilder = new imports.rulesConfig.FormElementStatusBuilder({\n"
            "        programEncounter: entity,\n"
            "        formElement\n"
            "    });\n"
            "    const isEdit = entity.uuid !== undefined && entity.uuid !== null;\n"
            "    if (isEdit) {\n"
            "        statusBuilder.show().is.truthy;\n"
            "    }\n"
            "    const status = statusBuilder.build();\n"
            "    if (isEdit) {\n"
            "        status.editable = false;\n"
            "    }\n"
            "    return status;\n"
            "};"
        ),
        "sectors": ["all"],
    },
    # ======================================================================
    # NEW TEMPLATES (18) — Full rule type coverage
    # ======================================================================

    # ---- ViewFilter: multi_concept_dependency ----
    {
        "id": "viewfilter-multi-concept-dependency",
        "name": "ViewFilter - Show/hide based on multiple concept values combined",
        "type": "ViewFilter",
        "description": "Show a form element only when multiple concept values satisfy conditions using AND/OR logic across different fields.",
        "complexity": 3,
        "format": "javascript",
        "template": (
            "'use strict';\n"
            "({params, imports}) => {\n"
            "    const entity = params.entity;\n"
            "    const formElement = params.formElement;\n"
            "    const statusBuilder = new imports.rulesConfig.FormElementStatusBuilder({\n"
            "        programEncounter: entity,\n"
            "        formElement\n"
            "    });\n"
            "    statusBuilder.show()\n"
            '        .when.valueInEncounter("{{concept_name_1}}")\n'
            '        .containsAnswerConceptName("{{answer_1}}")\n'
            "        .{{conjunction}}.valueInEncounter(\"{{concept_name_2}}\")\n"
            '        .containsAnswerConceptName("{{answer_2}}");\n'
            "    return statusBuilder.build();\n"
            "};"
        ),
        "parameters": [
            "concept_name_1",
            "answer_1",
            "conjunction",
            "concept_name_2",
            "answer_2",
        ],
        "example_filled": (
            "'use strict';\n"
            "({params, imports}) => {\n"
            "    const entity = params.entity;\n"
            "    const formElement = params.formElement;\n"
            "    const statusBuilder = new imports.rulesConfig.FormElementStatusBuilder({\n"
            "        programEncounter: entity,\n"
            "        formElement\n"
            "    });\n"
            "    statusBuilder.show()\n"
            '        .when.valueInEncounter("Is pregnant")\n'
            '        .containsAnswerConceptName("Yes")\n'
            '        .and.valueInEncounter("Trimester")\n'
            '        .containsAnswerConceptName("Third");\n'
            "    return statusBuilder.build();\n"
            "};"
        ),
        "sectors": ["all"],
    },

    # ---- ViewFilter: age_gender_conditional ----
    {
        "id": "viewfilter-age-gender-conditional",
        "name": "ViewFilter - Show based on age + gender combination",
        "type": "ViewFilter",
        "description": "Show a form element only when the individual matches a specific age range AND gender.",
        "complexity": 3,
        "format": "javascript",
        "template": (
            "'use strict';\n"
            "({params, imports}) => {\n"
            "    const entity = params.entity;\n"
            "    const formElement = params.formElement;\n"
            "    const individual = entity.programEnrolment\n"
            "        ? entity.programEnrolment.individual\n"
            "        : (entity.individual || entity);\n"
            "    const statusBuilder = new imports.rulesConfig.FormElementStatusBuilder({\n"
            "        programEncounter: entity,\n"
            "        formElement\n"
            "    });\n"
            "    const ageInYears = individual.getAgeInYears();\n"
            "    const isFemale = individual.isFemale ? individual.isFemale() : individual.gender.name === 'Female';\n"
            "    const isTargetGender = '{{target_gender}}' === 'Female' ? isFemale : !isFemale;\n"
            "    statusBuilder.show()\n"
            "        .whenItem(isTargetGender && ageInYears >= {{min_age}} && ageInYears <= {{max_age}})\n"
            "        .is.truthy;\n"
            "    return statusBuilder.build();\n"
            "};"
        ),
        "parameters": ["target_gender", "min_age", "max_age"],
        "example_filled": (
            "'use strict';\n"
            "({params, imports}) => {\n"
            "    const entity = params.entity;\n"
            "    const formElement = params.formElement;\n"
            "    const individual = entity.programEnrolment\n"
            "        ? entity.programEnrolment.individual\n"
            "        : (entity.individual || entity);\n"
            "    const statusBuilder = new imports.rulesConfig.FormElementStatusBuilder({\n"
            "        programEncounter: entity,\n"
            "        formElement\n"
            "    });\n"
            "    const ageInYears = individual.getAgeInYears();\n"
            "    const isFemale = individual.isFemale ? individual.isFemale() : individual.gender.name === 'Female';\n"
            "    const isTargetGender = 'Female' === 'Female' ? isFemale : !isFemale;\n"
            "    statusBuilder.show()\n"
            "        .whenItem(isTargetGender && ageInYears >= 15 && ageInYears <= 49)\n"
            "        .is.truthy;\n"
            "    return statusBuilder.build();\n"
            "};"
        ),
        "sectors": ["health"],
    },

    # ---- ViewFilter: cross_form_reference ----
    {
        "id": "viewfilter-cross-form-reference",
        "name": "ViewFilter - Show based on value from a different form/encounter",
        "type": "ViewFilter",
        "description": "Show a form element based on a value recorded in a different encounter type (cross-encounter lookup).",
        "complexity": 3,
        "format": "javascript",
        "template": (
            "'use strict';\n"
            "({params, imports}) => {\n"
            "    const entity = params.entity;\n"
            "    const formElement = params.formElement;\n"
            "    const _ = imports.lodash;\n"
            "    const statusBuilder = new imports.rulesConfig.FormElementStatusBuilder({\n"
            "        programEncounter: entity,\n"
            "        formElement\n"
            "    });\n"
            "    const enrolment = entity.programEnrolment;\n"
            "    const otherEncounters = enrolment.encounters\n"
            "        .filter(e => e.encounterType.name === '{{source_encounter_type}}' && !e.voided);\n"
            "    let shouldShow = false;\n"
            "    if (otherEncounters.length > 0) {\n"
            "        const latest = _.maxBy(otherEncounters, 'encounterDateTime');\n"
            "        const value = latest.getObservationReadableValue('{{source_concept_name}}');\n"
            "        shouldShow = value === '{{expected_value}}';\n"
            "    }\n"
            "    statusBuilder.show().whenItem(shouldShow).is.truthy;\n"
            "    return statusBuilder.build();\n"
            "};"
        ),
        "parameters": [
            "source_encounter_type",
            "source_concept_name",
            "expected_value",
        ],
        "example_filled": (
            "'use strict';\n"
            "({params, imports}) => {\n"
            "    const entity = params.entity;\n"
            "    const formElement = params.formElement;\n"
            "    const _ = imports.lodash;\n"
            "    const statusBuilder = new imports.rulesConfig.FormElementStatusBuilder({\n"
            "        programEncounter: entity,\n"
            "        formElement\n"
            "    });\n"
            "    const enrolment = entity.programEnrolment;\n"
            "    const otherEncounters = enrolment.encounters\n"
            "        .filter(e => e.encounterType.name === 'ANC Registration' && !e.voided);\n"
            "    let shouldShow = false;\n"
            "    if (otherEncounters.length > 0) {\n"
            "        const latest = _.maxBy(otherEncounters, 'encounterDateTime');\n"
            "        const value = latest.getObservationReadableValue('High Risk Pregnancy');\n"
            "        shouldShow = value === 'Yes';\n"
            "    }\n"
            "    statusBuilder.show().whenItem(shouldShow).is.truthy;\n"
            "    return statusBuilder.build();\n"
            "};"
        ),
        "sectors": ["health"],
    },

    # ---- Decision: multi_axis_decision ----
    {
        "id": "decision-multi-axis",
        "name": "Decision - Multi-axis clinical decision (e.g. BMI + age + BP)",
        "type": "Decision",
        "description": "Make a clinical decision based on multiple clinical parameters evaluated together (e.g. BMI + age + blood pressure).",
        "complexity": 4,
        "format": "javascript",
        "template": (
            "'use strict';\n"
            "({params, imports}) => {\n"
            "    const encounter = params.entity;\n"
            "    const individual = encounter.programEnrolment\n"
            "        ? encounter.programEnrolment.individual\n"
            "        : (encounter.individual || encounter);\n"
            "    const decisions = {encounterDecisions: [], enrolmentDecisions: [], registrationDecisions: []};\n"
            "    const param1 = encounter.getObservationValue('{{param1_concept}}');\n"
            "    const param2 = encounter.getObservationValue('{{param2_concept}}');\n"
            "    const param3 = encounter.getObservationValue('{{param3_concept}}');\n"
            "    const ageInYears = individual.getAgeInYears();\n"
            "    let category = '{{default_category}}';\n"
            "    if ((param1 !== undefined && param1 {{param1_critical_op}} {{param1_critical_val}})\n"
            "        || (param2 !== undefined && param2 {{param2_critical_op}} {{param2_critical_val}})\n"
            "        || (ageInYears {{age_critical_op}} {{age_critical_val}} && param3 !== undefined && param3 {{param3_critical_op}} {{param3_critical_val}})) {\n"
            "        category = '{{critical_category}}';\n"
            "    } else if ((param1 !== undefined && param1 {{param1_warning_op}} {{param1_warning_val}})\n"
            "        || (param2 !== undefined && param2 {{param2_warning_op}} {{param2_warning_val}})) {\n"
            "        category = '{{warning_category}}';\n"
            "    }\n"
            "    decisions.encounterDecisions.push({\n"
            "        name: '{{decision_concept}}',\n"
            "        value: [category]\n"
            "    });\n"
            "    return decisions;\n"
            "};"
        ),
        "parameters": [
            "param1_concept", "param1_critical_op", "param1_critical_val",
            "param1_warning_op", "param1_warning_val",
            "param2_concept", "param2_critical_op", "param2_critical_val",
            "param2_warning_op", "param2_warning_val",
            "param3_concept", "param3_critical_op", "param3_critical_val",
            "age_critical_op", "age_critical_val",
            "default_category", "warning_category", "critical_category",
            "decision_concept",
        ],
        "example_filled": (
            "'use strict';\n"
            "({params, imports}) => {\n"
            "    const encounter = params.entity;\n"
            "    const individual = encounter.programEnrolment\n"
            "        ? encounter.programEnrolment.individual\n"
            "        : (encounter.individual || encounter);\n"
            "    const decisions = {encounterDecisions: [], enrolmentDecisions: [], registrationDecisions: []};\n"
            "    const param1 = encounter.getObservationValue('BMI');\n"
            "    const param2 = encounter.getObservationValue('Systolic BP');\n"
            "    const param3 = encounter.getObservationValue('Fasting Blood Sugar');\n"
            "    const ageInYears = individual.getAgeInYears();\n"
            "    let category = 'Low Risk';\n"
            "    if ((param1 !== undefined && param1 > 35)\n"
            "        || (param2 !== undefined && param2 > 160)\n"
            "        || (ageInYears > 45 && param3 !== undefined && param3 > 200)) {\n"
            "        category = 'High Risk';\n"
            "    } else if ((param1 !== undefined && param1 > 30)\n"
            "        || (param2 !== undefined && param2 > 140)) {\n"
            "        category = 'Medium Risk';\n"
            "    }\n"
            "    decisions.encounterDecisions.push({\n"
            "        name: 'Cardiovascular Risk',\n"
            "        value: [category]\n"
            "    });\n"
            "    return decisions;\n"
            "};"
        ),
        "sectors": ["health"],
    },

    # ---- Decision: coded_to_coded_mapping ----
    {
        "id": "decision-coded-to-coded-mapping",
        "name": "Decision - Map one coded answer to another coded decision",
        "type": "Decision",
        "description": "Map a coded observation value to a different coded decision value using a lookup table.",
        "complexity": 2,
        "format": "javascript",
        "template": (
            "'use strict';\n"
            "({params, imports}) => {\n"
            "    const encounter = params.entity;\n"
            "    const decisions = {encounterDecisions: [], enrolmentDecisions: [], registrationDecisions: []};\n"
            "    const sourceValue = encounter.getObservationReadableValue('{{source_concept}}');\n"
            "    const mapping = {\n"
            "        '{{source_value_1}}': '{{target_value_1}}',\n"
            "        '{{source_value_2}}': '{{target_value_2}}',\n"
            "        '{{source_value_3}}': '{{target_value_3}}'\n"
            "    };\n"
            "    const mappedValue = mapping[sourceValue] || '{{default_target_value}}';\n"
            "    if (sourceValue) {\n"
            "        decisions.encounterDecisions.push({\n"
            "            name: '{{target_concept}}',\n"
            "            value: [mappedValue]\n"
            "        });\n"
            "    }\n"
            "    return decisions;\n"
            "};"
        ),
        "parameters": [
            "source_concept",
            "source_value_1", "target_value_1",
            "source_value_2", "target_value_2",
            "source_value_3", "target_value_3",
            "default_target_value",
            "target_concept",
        ],
        "example_filled": (
            "'use strict';\n"
            "({params, imports}) => {\n"
            "    const encounter = params.entity;\n"
            "    const decisions = {encounterDecisions: [], enrolmentDecisions: [], registrationDecisions: []};\n"
            "    const sourceValue = encounter.getObservationReadableValue('HPLC Result');\n"
            "    const mapping = {\n"
            "        'AA': 'Normal',\n"
            "        'AS': 'Sickle Cell Trait',\n"
            "        'SS': 'Sickle Cell Disease'\n"
            "    };\n"
            "    const mappedValue = mapping[sourceValue] || 'Unknown';\n"
            "    if (sourceValue) {\n"
            "        decisions.encounterDecisions.push({\n"
            "            name: 'Sickle Cell Diagnosis',\n"
            "            value: [mappedValue]\n"
            "        });\n"
            "    }\n"
            "    return decisions;\n"
            "};"
        ),
        "sectors": ["health"],
    },

    # ---- Decision: cumulative_risk_score ----
    {
        "id": "decision-cumulative-risk-score",
        "name": "Decision - Cumulative risk score from multiple factors",
        "type": "Decision",
        "description": "Calculate a weighted risk score from multiple observation factors and classify into risk categories.",
        "complexity": 4,
        "format": "javascript",
        "template": (
            "'use strict';\n"
            "({params, imports}) => {\n"
            "    const encounter = params.entity;\n"
            "    const decisions = {encounterDecisions: [], enrolmentDecisions: [], registrationDecisions: []};\n"
            "    let riskScore = 0;\n"
            "    const factors = [\n"
            "        {concept: '{{factor_1_concept}}', type: '{{factor_1_type}}', threshold: {{factor_1_threshold}}, weight: {{factor_1_weight}}, op: '{{factor_1_op}}'},\n"
            "        {concept: '{{factor_2_concept}}', type: '{{factor_2_type}}', threshold: {{factor_2_threshold}}, weight: {{factor_2_weight}}, op: '{{factor_2_op}}'},\n"
            "        {concept: '{{factor_3_concept}}', type: '{{factor_3_type}}', threshold: {{factor_3_threshold}}, weight: {{factor_3_weight}}, op: '{{factor_3_op}}'},\n"
            "        {concept: '{{factor_4_concept}}', type: '{{factor_4_type}}', threshold: {{factor_4_threshold}}, weight: {{factor_4_weight}}, op: '{{factor_4_op}}'}\n"
            "    ];\n"
            "    factors.forEach(f => {\n"
            "        const val = f.type === 'numeric'\n"
            "            ? encounter.getObservationValue(f.concept)\n"
            "            : encounter.getObservationReadableValue(f.concept);\n"
            "        if (val === undefined || val === null) return;\n"
            "        if (f.type === 'numeric') {\n"
            "            if ((f.op === '>' && val > f.threshold) || (f.op === '<' && val < f.threshold)\n"
            "                || (f.op === '>=' && val >= f.threshold) || (f.op === '<=' && val <= f.threshold)) {\n"
            "                riskScore += f.weight;\n"
            "            }\n"
            "        } else {\n"
            "            if (val === String(f.threshold) || (Array.isArray(val) && val.includes(String(f.threshold)))) {\n"
            "                riskScore += f.weight;\n"
            "            }\n"
            "        }\n"
            "    });\n"
            "    let riskCategory = '{{low_risk_label}}';\n"
            "    if (riskScore >= {{high_threshold}}) riskCategory = '{{high_risk_label}}';\n"
            "    else if (riskScore >= {{medium_threshold}}) riskCategory = '{{medium_risk_label}}';\n"
            "    decisions.encounterDecisions.push({name: '{{score_concept}}', value: riskScore});\n"
            "    decisions.encounterDecisions.push({name: '{{category_concept}}', value: [riskCategory]});\n"
            "    return decisions;\n"
            "};"
        ),
        "parameters": [
            "factor_1_concept", "factor_1_type", "factor_1_threshold", "factor_1_weight", "factor_1_op",
            "factor_2_concept", "factor_2_type", "factor_2_threshold", "factor_2_weight", "factor_2_op",
            "factor_3_concept", "factor_3_type", "factor_3_threshold", "factor_3_weight", "factor_3_op",
            "factor_4_concept", "factor_4_type", "factor_4_threshold", "factor_4_weight", "factor_4_op",
            "high_threshold", "medium_threshold",
            "high_risk_label", "medium_risk_label", "low_risk_label",
            "score_concept", "category_concept",
        ],
        "example_filled": (
            "'use strict';\n"
            "({params, imports}) => {\n"
            "    const encounter = params.entity;\n"
            "    const decisions = {encounterDecisions: [], enrolmentDecisions: [], registrationDecisions: []};\n"
            "    let riskScore = 0;\n"
            "    const factors = [\n"
            "        {concept: 'Hemoglobin', type: 'numeric', threshold: 7, weight: 3, op: '<'},\n"
            "        {concept: 'Systolic BP', type: 'numeric', threshold: 140, weight: 2, op: '>'},\n"
            "        {concept: 'Pedal Edema', type: 'coded', threshold: 'Present', weight: 1, op: '='},\n"
            "        {concept: 'Urine Protein', type: 'coded', threshold: '++', weight: 2, op: '='}\n"
            "    ];\n"
            "    factors.forEach(f => {\n"
            "        const val = f.type === 'numeric'\n"
            "            ? encounter.getObservationValue(f.concept)\n"
            "            : encounter.getObservationReadableValue(f.concept);\n"
            "        if (val === undefined || val === null) return;\n"
            "        if (f.type === 'numeric') {\n"
            "            if ((f.op === '>' && val > f.threshold) || (f.op === '<' && val < f.threshold)\n"
            "                || (f.op === '>=' && val >= f.threshold) || (f.op === '<=' && val <= f.threshold)) {\n"
            "                riskScore += f.weight;\n"
            "            }\n"
            "        } else {\n"
            "            if (val === String(f.threshold) || (Array.isArray(val) && val.includes(String(f.threshold)))) {\n"
            "                riskScore += f.weight;\n"
            "            }\n"
            "        }\n"
            "    });\n"
            "    let riskCategory = 'Low';\n"
            "    if (riskScore >= 6) riskCategory = 'High';\n"
            "    else if (riskScore >= 3) riskCategory = 'Medium';\n"
            "    decisions.encounterDecisions.push({name: 'ANC Risk Score', value: riskScore});\n"
            "    decisions.encounterDecisions.push({name: 'ANC Risk Category', value: [riskCategory]});\n"
            "    return decisions;\n"
            "};"
        ),
        "sectors": ["health"],
    },

    # ---- VisitSchedule: recurring_schedule ----
    {
        "id": "visit-schedule-recurring",
        "name": "Visit Schedule - Recurring visits at regular intervals",
        "type": "VisitSchedule",
        "description": "Schedule visits at regular intervals (every N days/weeks/months) for a fixed number of cycles.",
        "complexity": 3,
        "format": "javascript",
        "template": (
            "'use strict';\n"
            "({params, imports}) => {\n"
            "    const encounter = params.entity;\n"
            "    const scheduleBuilder = new imports.rulesConfig.VisitScheduleBuilder({\n"
            "        programEnrolment: encounter.programEnrolment\n"
            "    });\n"
            "    const moment = imports.moment;\n"
            "    const baseDate = encounter.encounterDateTime || new Date();\n"
            "    const completedEncounters = encounter.programEnrolment.encounters\n"
            "        .filter(e => e.encounterType.name === '{{encounter_type}}' && !e.voided && e.encounterDateTime);\n"
            "    const visitNumber = completedEncounters.length + 1;\n"
            "    if (visitNumber < {{max_visits}}) {\n"
            "        scheduleBuilder.add({\n"
            "            name: '{{visit_name_prefix}} ' + (visitNumber + 1),\n"
            "            encounterType: '{{encounter_type}}',\n"
            "            earliestDate: moment(baseDate).add({{interval_days}}, 'days').toDate(),\n"
            "            maxDate: moment(baseDate).add({{interval_days}} + {{grace_days}}, 'days').toDate()\n"
            "        });\n"
            "    }\n"
            "    return scheduleBuilder.getAll();\n"
            "};"
        ),
        "parameters": [
            "encounter_type",
            "visit_name_prefix",
            "interval_days",
            "grace_days",
            "max_visits",
        ],
        "example_filled": (
            "'use strict';\n"
            "({params, imports}) => {\n"
            "    const encounter = params.entity;\n"
            "    const scheduleBuilder = new imports.rulesConfig.VisitScheduleBuilder({\n"
            "        programEnrolment: encounter.programEnrolment\n"
            "    });\n"
            "    const moment = imports.moment;\n"
            "    const baseDate = encounter.encounterDateTime || new Date();\n"
            "    const completedEncounters = encounter.programEnrolment.encounters\n"
            "        .filter(e => e.encounterType.name === 'Growth Monitoring' && !e.voided && e.encounterDateTime);\n"
            "    const visitNumber = completedEncounters.length + 1;\n"
            "    if (visitNumber < 12) {\n"
            "        scheduleBuilder.add({\n"
            "            name: 'Growth Monitoring ' + (visitNumber + 1),\n"
            "            encounterType: 'Growth Monitoring',\n"
            "            earliestDate: moment(baseDate).add(30, 'days').toDate(),\n"
            "            maxDate: moment(baseDate).add(30 + 7, 'days').toDate()\n"
            "        });\n"
            "    }\n"
            "    return scheduleBuilder.getAll();\n"
            "};"
        ),
        "sectors": ["health", "nutrition"],
    },

    # ---- VisitSchedule: conditional_schedule ----
    {
        "id": "visit-schedule-phase-based",
        "name": "Visit Schedule - Schedule based on program phase or risk level",
        "type": "VisitSchedule",
        "description": "Schedule different visit types based on program phase, risk classification, or other conditional logic.",
        "complexity": 3,
        "format": "javascript",
        "template": (
            "'use strict';\n"
            "({params, imports}) => {\n"
            "    const encounter = params.entity;\n"
            "    const enrolment = encounter.programEnrolment;\n"
            "    const scheduleBuilder = new imports.rulesConfig.VisitScheduleBuilder({\n"
            "        programEnrolment: enrolment\n"
            "    });\n"
            "    const moment = imports.moment;\n"
            "    const baseDate = encounter.encounterDateTime || new Date();\n"
            "    const phase = encounter.getObservationReadableValue('{{phase_concept}}') ||\n"
            "        enrolment.getObservationReadableValue('{{phase_concept}}');\n"
            "    if (phase === '{{phase_1_value}}') {\n"
            "        scheduleBuilder.add({\n"
            "            name: '{{phase_1_visit_name}}',\n"
            "            encounterType: '{{phase_1_encounter_type}}',\n"
            "            earliestDate: moment(baseDate).add({{phase_1_earliest_days}}, 'days').toDate(),\n"
            "            maxDate: moment(baseDate).add({{phase_1_max_days}}, 'days').toDate()\n"
            "        });\n"
            "    } else if (phase === '{{phase_2_value}}') {\n"
            "        scheduleBuilder.add({\n"
            "            name: '{{phase_2_visit_name}}',\n"
            "            encounterType: '{{phase_2_encounter_type}}',\n"
            "            earliestDate: moment(baseDate).add({{phase_2_earliest_days}}, 'days').toDate(),\n"
            "            maxDate: moment(baseDate).add({{phase_2_max_days}}, 'days').toDate()\n"
            "        });\n"
            "    } else {\n"
            "        scheduleBuilder.add({\n"
            "            name: '{{default_visit_name}}',\n"
            "            encounterType: '{{default_encounter_type}}',\n"
            "            earliestDate: moment(baseDate).add({{default_earliest_days}}, 'days').toDate(),\n"
            "            maxDate: moment(baseDate).add({{default_max_days}}, 'days').toDate()\n"
            "        });\n"
            "    }\n"
            "    return scheduleBuilder.getAll();\n"
            "};"
        ),
        "parameters": [
            "phase_concept",
            "phase_1_value", "phase_1_visit_name", "phase_1_encounter_type",
            "phase_1_earliest_days", "phase_1_max_days",
            "phase_2_value", "phase_2_visit_name", "phase_2_encounter_type",
            "phase_2_earliest_days", "phase_2_max_days",
            "default_visit_name", "default_encounter_type",
            "default_earliest_days", "default_max_days",
        ],
        "example_filled": (
            "'use strict';\n"
            "({params, imports}) => {\n"
            "    const encounter = params.entity;\n"
            "    const enrolment = encounter.programEnrolment;\n"
            "    const scheduleBuilder = new imports.rulesConfig.VisitScheduleBuilder({\n"
            "        programEnrolment: enrolment\n"
            "    });\n"
            "    const moment = imports.moment;\n"
            "    const baseDate = encounter.encounterDateTime || new Date();\n"
            "    const phase = encounter.getObservationReadableValue('Treatment Phase') ||\n"
            "        enrolment.getObservationReadableValue('Treatment Phase');\n"
            "    if (phase === 'Intensive') {\n"
            "        scheduleBuilder.add({\n"
            "            name: 'Intensive Phase Follow-up',\n"
            "            encounterType: 'TB Follow-up',\n"
            "            earliestDate: moment(baseDate).add(14, 'days').toDate(),\n"
            "            maxDate: moment(baseDate).add(21, 'days').toDate()\n"
            "        });\n"
            "    } else if (phase === 'Continuation') {\n"
            "        scheduleBuilder.add({\n"
            "            name: 'Continuation Phase Follow-up',\n"
            "            encounterType: 'TB Follow-up',\n"
            "            earliestDate: moment(baseDate).add(28, 'days').toDate(),\n"
            "            maxDate: moment(baseDate).add(35, 'days').toDate()\n"
            "        });\n"
            "    } else {\n"
            "        scheduleBuilder.add({\n"
            "            name: 'Routine Follow-up',\n"
            "            encounterType: 'TB Follow-up',\n"
            "            earliestDate: moment(baseDate).add(30, 'days').toDate(),\n"
            "            maxDate: moment(baseDate).add(45, 'days').toDate()\n"
            "        });\n"
            "    }\n"
            "    return scheduleBuilder.getAll();\n"
            "};"
        ),
        "sectors": ["health"],
    },

    # ---- VisitSchedule: cross_program_schedule ----
    {
        "id": "visit-schedule-cross-program",
        "name": "Visit Schedule - Schedule visit in another program based on event",
        "type": "VisitSchedule",
        "description": "Schedule a visit in one program (or encounter type) based on an event or observation in a different program context.",
        "complexity": 4,
        "format": "javascript",
        "template": (
            "'use strict';\n"
            "({params, imports}) => {\n"
            "    const encounter = params.entity;\n"
            "    const individual = encounter.programEnrolment\n"
            "        ? encounter.programEnrolment.individual\n"
            "        : encounter.individual;\n"
            "    const scheduleBuilder = new imports.rulesConfig.VisitScheduleBuilder({\n"
            "        programEnrolment: encounter.programEnrolment\n"
            "    });\n"
            "    const moment = imports.moment;\n"
            "    const baseDate = encounter.encounterDateTime || new Date();\n"
            "    const triggerValue = encounter.getObservationReadableValue('{{trigger_concept}}');\n"
            "    if (triggerValue === '{{trigger_value}}') {\n"
            "        const targetEnrolment = individual.enrolments.find(\n"
            "            e => e.program.name === '{{target_program}}' && !e.programExitDateTime\n"
            "        );\n"
            "        if (targetEnrolment) {\n"
            "            const targetScheduleBuilder = new imports.rulesConfig.VisitScheduleBuilder({\n"
            "                programEnrolment: targetEnrolment\n"
            "            });\n"
            "            targetScheduleBuilder.add({\n"
            "                name: '{{target_visit_name}}',\n"
            "                encounterType: '{{target_encounter_type}}',\n"
            "                earliestDate: moment(baseDate).add({{target_earliest_days}}, 'days').toDate(),\n"
            "                maxDate: moment(baseDate).add({{target_max_days}}, 'days').toDate()\n"
            "            });\n"
            "            return targetScheduleBuilder.getAll();\n"
            "        }\n"
            "    }\n"
            "    return scheduleBuilder.getAll();\n"
            "};"
        ),
        "parameters": [
            "trigger_concept", "trigger_value",
            "target_program",
            "target_visit_name", "target_encounter_type",
            "target_earliest_days", "target_max_days",
        ],
        "example_filled": (
            "'use strict';\n"
            "({params, imports}) => {\n"
            "    const encounter = params.entity;\n"
            "    const individual = encounter.programEnrolment\n"
            "        ? encounter.programEnrolment.individual\n"
            "        : encounter.individual;\n"
            "    const scheduleBuilder = new imports.rulesConfig.VisitScheduleBuilder({\n"
            "        programEnrolment: encounter.programEnrolment\n"
            "    });\n"
            "    const moment = imports.moment;\n"
            "    const baseDate = encounter.encounterDateTime || new Date();\n"
            "    const triggerValue = encounter.getObservationReadableValue('Delivery Outcome');\n"
            "    if (triggerValue === 'Live Birth') {\n"
            "        const targetEnrolment = individual.enrolments.find(\n"
            "            e => e.program.name === 'Child Program' && !e.programExitDateTime\n"
            "        );\n"
            "        if (targetEnrolment) {\n"
            "            const targetScheduleBuilder = new imports.rulesConfig.VisitScheduleBuilder({\n"
            "                programEnrolment: targetEnrolment\n"
            "            });\n"
            "            targetScheduleBuilder.add({\n"
            "                name: 'Newborn Assessment',\n"
            "                encounterType: 'PNC Visit',\n"
            "                earliestDate: moment(baseDate).add(1, 'days').toDate(),\n"
            "                maxDate: moment(baseDate).add(3, 'days').toDate()\n"
            "            });\n"
            "            return targetScheduleBuilder.getAll();\n"
            "        }\n"
            "    }\n"
            "    return scheduleBuilder.getAll();\n"
            "};"
        ),
        "sectors": ["health"],
    },

    # ---- Validation: cross_field_validation ----
    {
        "id": "validation-cross-field-numeric",
        "name": "Validation - Cross-field numeric validation",
        "type": "Validation",
        "description": "Validate one numeric field's value against another field's value (e.g. diastolic BP must be less than systolic BP).",
        "complexity": 2,
        "format": "javascript",
        "template": (
            "'use strict';\n"
            "({params, imports}) => {\n"
            "    const encounter = params.entity;\n"
            "    const failures = [];\n"
            "    const val1 = encounter.getObservationValue('{{field_1}}');\n"
            "    const val2 = encounter.getObservationValue('{{field_2}}');\n"
            "    if (val1 !== undefined && val1 !== null && val2 !== undefined && val2 !== null) {\n"
            "        if (val2 {{comparison_op}} val1) {\n"
            "            failures.push(imports.rulesConfig.createValidationError(\n"
            "                '{{error_message}}'\n"
            "            ));\n"
            "        }\n"
            "    }\n"
            "    return failures;\n"
            "};"
        ),
        "parameters": ["field_1", "field_2", "comparison_op", "error_message"],
        "example_filled": (
            "'use strict';\n"
            "({params, imports}) => {\n"
            "    const encounter = params.entity;\n"
            "    const failures = [];\n"
            "    const val1 = encounter.getObservationValue('Systolic BP');\n"
            "    const val2 = encounter.getObservationValue('Diastolic BP');\n"
            "    if (val1 !== undefined && val1 !== null && val2 !== undefined && val2 !== null) {\n"
            "        if (val2 >= val1) {\n"
            "            failures.push(imports.rulesConfig.createValidationError(\n"
            "                'Diastolic BP must be less than Systolic BP'\n"
            "            ));\n"
            "        }\n"
            "    }\n"
            "    return failures;\n"
            "};"
        ),
        "sectors": ["health"],
    },

    # ---- Validation: date_range_validation ----
    {
        "id": "validation-date-range-flexible",
        "name": "Validation - Flexible date range validation",
        "type": "Validation",
        "description": "Validate a date field against a configurable acceptable range (min age, max age, not future, relative to another date, etc.).",
        "complexity": 3,
        "format": "javascript",
        "template": (
            "'use strict';\n"
            "({params, imports}) => {\n"
            "    const encounter = params.entity;\n"
            "    const moment = imports.moment;\n"
            "    const failures = [];\n"
            "    const dateValue = encounter.getObservationValue('{{date_concept}}');\n"
            "    if (dateValue) {\n"
            "        const d = moment(dateValue);\n"
            "        const now = moment();\n"
            "        if ('{{allow_future}}' === 'false' && d.isAfter(now)) {\n"
            "            failures.push(imports.rulesConfig.createValidationError(\n"
            "                '{{date_concept}} cannot be in the future'\n"
            "            ));\n"
            "        }\n"
            "        if ({{min_days_ago}} > 0) {\n"
            "            const minDate = moment().subtract({{min_days_ago}}, 'days');\n"
            "            if (d.isAfter(minDate)) {\n"
            "                failures.push(imports.rulesConfig.createValidationError(\n"
            "                    '{{date_concept}} must be at least {{min_days_ago}} days ago'\n"
            "                ));\n"
            "            }\n"
            "        }\n"
            "        if ({{max_days_ago}} > 0) {\n"
            "            const maxDate = moment().subtract({{max_days_ago}}, 'days');\n"
            "            if (d.isBefore(maxDate)) {\n"
            "                failures.push(imports.rulesConfig.createValidationError(\n"
            "                    '{{date_concept}} cannot be more than {{max_days_ago}} days ago'\n"
            "                ));\n"
            "            }\n"
            "        }\n"
            "    }\n"
            "    return failures;\n"
            "};"
        ),
        "parameters": ["date_concept", "allow_future", "min_days_ago", "max_days_ago"],
        "example_filled": (
            "'use strict';\n"
            "({params, imports}) => {\n"
            "    const encounter = params.entity;\n"
            "    const moment = imports.moment;\n"
            "    const failures = [];\n"
            "    const dateValue = encounter.getObservationValue('Date of Birth');\n"
            "    if (dateValue) {\n"
            "        const d = moment(dateValue);\n"
            "        const now = moment();\n"
            "        if ('false' === 'false' && d.isAfter(now)) {\n"
            "            failures.push(imports.rulesConfig.createValidationError(\n"
            "                'Date of Birth cannot be in the future'\n"
            "            ));\n"
            "        }\n"
            "        if (0 > 0) {\n"
            "            const minDate = moment().subtract(0, 'days');\n"
            "            if (d.isAfter(minDate)) {\n"
            "                failures.push(imports.rulesConfig.createValidationError(\n"
            "                    'Date of Birth must be at least 0 days ago'\n"
            "                ));\n"
            "            }\n"
            "        }\n"
            "        if (36500 > 0) {\n"
            "            const maxDate = moment().subtract(36500, 'days');\n"
            "            if (d.isBefore(maxDate)) {\n"
            "                failures.push(imports.rulesConfig.createValidationError(\n"
            "                    'Date of Birth cannot be more than 36500 days ago'\n"
            "                ));\n"
            "            }\n"
            "        }\n"
            "    }\n"
            "    return failures;\n"
            "};"
        ),
        "sectors": ["all"],
    },

    # ---- Validation: conditional_required ----
    {
        "id": "validation-conditional-required",
        "name": "Validation - Conditionally required field",
        "type": "Validation",
        "description": "Validate that a field is filled in only when a certain condition is met (e.g. 'Other reason' required when 'Reason' is 'Other').",
        "complexity": 2,
        "format": "javascript",
        "template": (
            "'use strict';\n"
            "({params, imports}) => {\n"
            "    const encounter = params.entity;\n"
            "    const failures = [];\n"
            "    const conditionValue = encounter.getObservationReadableValue('{{condition_concept}}');\n"
            "    const requiredValue = encounter.getObservationValue('{{required_concept}}');\n"
            "    const conditionMet = conditionValue === '{{condition_answer}}'\n"
            "        || (Array.isArray(conditionValue) && conditionValue.includes('{{condition_answer}}'));\n"
            "    if (conditionMet && (requiredValue === undefined || requiredValue === null || requiredValue === '')) {\n"
            "        failures.push(imports.rulesConfig.createValidationError(\n"
            "            '{{required_concept}} is required when {{condition_concept}} is {{condition_answer}}'\n"
            "        ));\n"
            "    }\n"
            "    return failures;\n"
            "};"
        ),
        "parameters": [
            "condition_concept",
            "condition_answer",
            "required_concept",
        ],
        "example_filled": (
            "'use strict';\n"
            "({params, imports}) => {\n"
            "    const encounter = params.entity;\n"
            "    const failures = [];\n"
            "    const conditionValue = encounter.getObservationReadableValue('Reason for referral');\n"
            "    const requiredValue = encounter.getObservationValue('Other referral reason');\n"
            "    const conditionMet = conditionValue === 'Other'\n"
            "        || (Array.isArray(conditionValue) && conditionValue.includes('Other'));\n"
            "    if (conditionMet && (requiredValue === undefined || requiredValue === null || requiredValue === '')) {\n"
            "        failures.push(imports.rulesConfig.createValidationError(\n"
            "            'Other referral reason is required when Reason for referral is Other'\n"
            "        ));\n"
            "    }\n"
            "    return failures;\n"
            "};"
        ),
        "sectors": ["all"],
    },

    # ---- Eligibility: complex_enrolment_eligibility ----
    {
        "id": "eligibility-complex-enrolment",
        "name": "Eligibility - Multi-condition enrolment eligibility",
        "type": "Eligibility",
        "description": "Determine program enrolment eligibility based on multiple conditions: age range, gender, location, and/or registration observations.",
        "complexity": 3,
        "format": "javascript",
        "template": (
            "'use strict';\n"
            "({params, imports}) => {\n"
            "    const individual = params.entity;\n"
            "    const ageInYears = individual.getAgeInYears();\n"
            "    const gender = individual.gender ? individual.gender.name : null;\n"
            "    const location = individual.lowestAddressLevel ? individual.lowestAddressLevel.name : null;\n"
            "    const registrationObs = individual.getObservationReadableValue('{{registration_concept}}');\n"
            "    let eligible = true;\n"
            "    // Age check\n"
            "    if (ageInYears < {{min_age}} || ageInYears > {{max_age}}) {\n"
            "        eligible = false;\n"
            "    }\n"
            "    // Gender check (skip if 'Any')\n"
            "    if ('{{required_gender}}' !== 'Any' && gender !== '{{required_gender}}') {\n"
            "        eligible = false;\n"
            "    }\n"
            "    // Location check (skip if 'Any')\n"
            "    if ('{{required_location}}' !== 'Any' && location !== '{{required_location}}') {\n"
            "        eligible = false;\n"
            "    }\n"
            "    // Registration observation check (skip if 'Any')\n"
            "    if ('{{required_obs_value}}' !== 'Any') {\n"
            "        if (registrationObs !== '{{required_obs_value}}'\n"
            "            && !(Array.isArray(registrationObs) && registrationObs.includes('{{required_obs_value}}'))) {\n"
            "            eligible = false;\n"
            "        }\n"
            "    }\n"
            "    // Not already enrolled\n"
            "    const activeEnrolments = individual.enrolments\n"
            "        ? individual.enrolments.filter(e => !e.programExitDateTime && e.program.name === '{{program_name}}')\n"
            "        : [];\n"
            "    if (activeEnrolments.length > 0) {\n"
            "        eligible = false;\n"
            "    }\n"
            "    return eligible;\n"
            "};"
        ),
        "parameters": [
            "min_age", "max_age", "required_gender",
            "required_location", "registration_concept",
            "required_obs_value", "program_name",
        ],
        "example_filled": (
            "'use strict';\n"
            "({params, imports}) => {\n"
            "    const individual = params.entity;\n"
            "    const ageInYears = individual.getAgeInYears();\n"
            "    const gender = individual.gender ? individual.gender.name : null;\n"
            "    const location = individual.lowestAddressLevel ? individual.lowestAddressLevel.name : null;\n"
            "    const registrationObs = individual.getObservationReadableValue('Disability Status');\n"
            "    let eligible = true;\n"
            "    if (ageInYears < 0 || ageInYears > 5) {\n"
            "        eligible = false;\n"
            "    }\n"
            "    if ('Any' !== 'Any' && gender !== 'Any') {\n"
            "        eligible = false;\n"
            "    }\n"
            "    if ('Any' !== 'Any' && location !== 'Any') {\n"
            "        eligible = false;\n"
            "    }\n"
            "    if ('Any' !== 'Any') {\n"
            "        if (registrationObs !== 'Any'\n"
            "            && !(Array.isArray(registrationObs) && registrationObs.includes('Any'))) {\n"
            "            eligible = false;\n"
            "        }\n"
            "    }\n"
            "    const activeEnrolments = individual.enrolments\n"
            "        ? individual.enrolments.filter(e => !e.programExitDateTime && e.program.name === 'Nutrition Program')\n"
            "        : [];\n"
            "    if (activeEnrolments.length > 0) {\n"
            "        eligible = false;\n"
            "    }\n"
            "    return eligible;\n"
            "};"
        ),
        "sectors": ["health", "nutrition"],
    },

    # ---- Eligibility: encounter_eligibility_with_history ----
    {
        "id": "eligibility-encounter-with-history",
        "name": "Eligibility - Encounter eligibility based on previous encounter data",
        "type": "Eligibility",
        "description": "Determine if a specific encounter type should be available based on data from previous encounters (e.g. only show follow-up if screening was done).",
        "complexity": 3,
        "format": "javascript",
        "template": (
            "'use strict';\n"
            "({params, imports}) => {\n"
            "    const individual = params.entity;\n"
            "    const _ = imports.lodash;\n"
            "    // Check for prerequisite encounter\n"
            "    const prerequisiteEncounters = individual.encounters\n"
            "        ? individual.encounters.filter(\n"
            "            e => e.encounterType.name === '{{prerequisite_encounter_type}}'\n"
            "                && !e.voided && e.encounterDateTime\n"
            "          )\n"
            "        : [];\n"
            "    if (prerequisiteEncounters.length === 0) {\n"
            "        return false;\n"
            "    }\n"
            "    // Check prerequisite observation value\n"
            "    const latest = _.maxBy(prerequisiteEncounters, 'encounterDateTime');\n"
            "    const obsValue = latest.getObservationReadableValue('{{prerequisite_concept}}');\n"
            "    if ('{{required_obs_value}}' !== 'Any') {\n"
            "        if (obsValue !== '{{required_obs_value}}'\n"
            "            && !(Array.isArray(obsValue) && obsValue.includes('{{required_obs_value}}'))) {\n"
            "            return false;\n"
            "        }\n"
            "    }\n"
            "    // Check cooldown (minimum days since last encounter of this type)\n"
            "    if ({{min_days_since_last}} > 0) {\n"
            "        const thisTypeEncounters = individual.encounters\n"
            "            ? individual.encounters.filter(\n"
            "                e => e.encounterType.name === '{{this_encounter_type}}'\n"
            "                    && !e.voided && e.encounterDateTime\n"
            "              )\n"
            "            : [];\n"
            "        if (thisTypeEncounters.length > 0) {\n"
            "            const lastOfType = _.maxBy(thisTypeEncounters, 'encounterDateTime');\n"
            "            const daysSince = imports.moment().diff(imports.moment(lastOfType.encounterDateTime), 'days');\n"
            "            if (daysSince < {{min_days_since_last}}) {\n"
            "                return false;\n"
            "            }\n"
            "        }\n"
            "    }\n"
            "    return true;\n"
            "};"
        ),
        "parameters": [
            "prerequisite_encounter_type",
            "prerequisite_concept",
            "required_obs_value",
            "this_encounter_type",
            "min_days_since_last",
        ],
        "example_filled": (
            "'use strict';\n"
            "({params, imports}) => {\n"
            "    const individual = params.entity;\n"
            "    const _ = imports.lodash;\n"
            "    const prerequisiteEncounters = individual.encounters\n"
            "        ? individual.encounters.filter(\n"
            "            e => e.encounterType.name === 'Screening'\n"
            "                && !e.voided && e.encounterDateTime\n"
            "          )\n"
            "        : [];\n"
            "    if (prerequisiteEncounters.length === 0) {\n"
            "        return false;\n"
            "    }\n"
            "    const latest = _.maxBy(prerequisiteEncounters, 'encounterDateTime');\n"
            "    const obsValue = latest.getObservationReadableValue('Screening Result');\n"
            "    if ('Positive' !== 'Any') {\n"
            "        if (obsValue !== 'Positive'\n"
            "            && !(Array.isArray(obsValue) && obsValue.includes('Positive'))) {\n"
            "            return false;\n"
            "        }\n"
            "    }\n"
            "    if (7 > 0) {\n"
            "        const thisTypeEncounters = individual.encounters\n"
            "            ? individual.encounters.filter(\n"
            "                e => e.encounterType.name === 'Confirmatory Test'\n"
            "                    && !e.voided && e.encounterDateTime\n"
            "              )\n"
            "            : [];\n"
            "        if (thisTypeEncounters.length > 0) {\n"
            "            const lastOfType = _.maxBy(thisTypeEncounters, 'encounterDateTime');\n"
            "            const daysSince = imports.moment().diff(imports.moment(lastOfType.encounterDateTime), 'days');\n"
            "            if (daysSince < 7) {\n"
            "                return false;\n"
            "            }\n"
            "        }\n"
            "    }\n"
            "    return true;\n"
            "};"
        ),
        "sectors": ["health"],
    },

    # ---- Checklist: dynamic_checklist ----
    {
        "id": "checklist-dynamic",
        "name": "Checklist - Dynamic checklist items from form data",
        "type": "Checklist",
        "description": "Generate checklist items dynamically based on form data such as age at enrolment, gender, or risk factors.",
        "complexity": 4,
        "format": "javascript",
        "template": (
            "'use strict';\n"
            "({params, imports}) => {\n"
            "    const enrolment = params.entity;\n"
            "    const individual = enrolment.individual;\n"
            "    const moment = imports.moment;\n"
            "    const baseDate = {{base_date_expression}};\n"
            "    const ageInMonths = individual.getAgeInMonths();\n"
            "    const allItems = [\n"
            "        {name: '{{item_1_name}}', dueDays: {{item_1_due_days}}, maxDays: {{item_1_max_days}}, condition: {{item_1_condition}}},\n"
            "        {name: '{{item_2_name}}', dueDays: {{item_2_due_days}}, maxDays: {{item_2_max_days}}, condition: {{item_2_condition}}},\n"
            "        {name: '{{item_3_name}}', dueDays: {{item_3_due_days}}, maxDays: {{item_3_max_days}}, condition: {{item_3_condition}}},\n"
            "        {name: '{{item_4_name}}', dueDays: {{item_4_due_days}}, maxDays: {{item_4_max_days}}, condition: {{item_4_condition}}}\n"
            "    ];\n"
            "    const items = allItems\n"
            "        .filter(item => item.condition)\n"
            "        .map(item => ({\n"
            "            name: item.name,\n"
            "            dueDate: moment(baseDate).add(item.dueDays, 'days').toDate(),\n"
            "            maxDate: moment(baseDate).add(item.maxDays, 'days').toDate()\n"
            "        }));\n"
            "    return {\n"
            "        name: '{{checklist_name}}',\n"
            "        items: items\n"
            "    };\n"
            "};"
        ),
        "parameters": [
            "base_date_expression", "checklist_name",
            "item_1_name", "item_1_due_days", "item_1_max_days", "item_1_condition",
            "item_2_name", "item_2_due_days", "item_2_max_days", "item_2_condition",
            "item_3_name", "item_3_due_days", "item_3_max_days", "item_3_condition",
            "item_4_name", "item_4_due_days", "item_4_max_days", "item_4_condition",
        ],
        "example_filled": (
            "'use strict';\n"
            "({params, imports}) => {\n"
            "    const enrolment = params.entity;\n"
            "    const individual = enrolment.individual;\n"
            "    const moment = imports.moment;\n"
            "    const baseDate = individual.dateOfBirth;\n"
            "    const ageInMonths = individual.getAgeInMonths();\n"
            "    const allItems = [\n"
            "        {name: 'BCG', dueDays: 0, maxDays: 365, condition: true},\n"
            "        {name: 'OPV-0', dueDays: 0, maxDays: 15, condition: true},\n"
            "        {name: 'Pentavalent-1', dueDays: 42, maxDays: 365, condition: ageInMonths < 12},\n"
            "        {name: 'Measles-1', dueDays: 270, maxDays: 730, condition: ageInMonths < 24}\n"
            "    ];\n"
            "    const items = allItems\n"
            "        .filter(item => item.condition)\n"
            "        .map(item => ({\n"
            "            name: item.name,\n"
            "            dueDate: moment(baseDate).add(item.dueDays, 'days').toDate(),\n"
            "            maxDate: moment(baseDate).add(item.maxDays, 'days').toDate()\n"
            "        }));\n"
            "    return {\n"
            "        name: 'Immunization Schedule',\n"
            "        items: items\n"
            "    };\n"
            "};"
        ),
        "sectors": ["health"],
    },

    # ---- Summary: enrolment_summary_with_alerts ----
    {
        "id": "summary-enrolment-with-alerts",
        "name": "Summary - Enrolment summary with alert levels",
        "type": "EnrolmentSummary",
        "description": "Display key enrolment indicators with color-coded alert levels (abnormal flag) based on threshold values.",
        "complexity": 3,
        "format": "javascript",
        "template": (
            "'use strict';\n"
            "({params, imports}) => {\n"
            "    const enrolment = params.entity;\n"
            "    const summaryItems = [];\n"
            "    const indicators = [\n"
            "        {\n"
            "            name: '{{indicator_1_concept}}',\n"
            "            source: '{{indicator_1_source}}',\n"
            "            abnormalFn: (val) => {{indicator_1_abnormal_expr}}\n"
            "        },\n"
            "        {\n"
            "            name: '{{indicator_2_concept}}',\n"
            "            source: '{{indicator_2_source}}',\n"
            "            abnormalFn: (val) => {{indicator_2_abnormal_expr}}\n"
            "        },\n"
            "        {\n"
            "            name: '{{indicator_3_concept}}',\n"
            "            source: '{{indicator_3_source}}',\n"
            "            abnormalFn: (val) => {{indicator_3_abnormal_expr}}\n"
            "        }\n"
            "    ];\n"
            "    indicators.forEach(ind => {\n"
            "        let value;\n"
            "        if (ind.source === 'enrolment') {\n"
            "            value = enrolment.getObservationValue(ind.name);\n"
            "        } else {\n"
            "            value = enrolment.findLatestObservationInEntireEnrolment(ind.name);\n"
            "        }\n"
            "        if (value !== undefined && value !== null) {\n"
            "            summaryItems.push({\n"
            "                name: ind.name,\n"
            "                value: Array.isArray(value) ? value.join(', ') : String(value),\n"
            "                abnormal: ind.abnormalFn(value)\n"
            "            });\n"
            "        }\n"
            "    });\n"
            "    return summaryItems;\n"
            "};"
        ),
        "parameters": [
            "indicator_1_concept", "indicator_1_source", "indicator_1_abnormal_expr",
            "indicator_2_concept", "indicator_2_source", "indicator_2_abnormal_expr",
            "indicator_3_concept", "indicator_3_source", "indicator_3_abnormal_expr",
        ],
        "example_filled": (
            "'use strict';\n"
            "({params, imports}) => {\n"
            "    const enrolment = params.entity;\n"
            "    const summaryItems = [];\n"
            "    const indicators = [\n"
            "        {\n"
            "            name: 'Hemoglobin',\n"
            "            source: 'encounter',\n"
            "            abnormalFn: (val) => val < 7\n"
            "        },\n"
            "        {\n"
            "            name: 'Weight',\n"
            "            source: 'encounter',\n"
            "            abnormalFn: (val) => val < 40\n"
            "        },\n"
            "        {\n"
            "            name: 'High Risk Pregnancy',\n"
            "            source: 'enrolment',\n"
            "            abnormalFn: (val) => val === 'Yes' || (Array.isArray(val) && val.includes('Yes'))\n"
            "        }\n"
            "    ];\n"
            "    indicators.forEach(ind => {\n"
            "        let value;\n"
            "        if (ind.source === 'enrolment') {\n"
            "            value = enrolment.getObservationValue(ind.name);\n"
            "        } else {\n"
            "            value = enrolment.findLatestObservationInEntireEnrolment(ind.name);\n"
            "        }\n"
            "        if (value !== undefined && value !== null) {\n"
            "            summaryItems.push({\n"
            "                name: ind.name,\n"
            "                value: Array.isArray(value) ? value.join(', ') : String(value),\n"
            "                abnormal: ind.abnormalFn(value)\n"
            "            });\n"
            "        }\n"
            "    });\n"
            "    return summaryItems;\n"
            "};"
        ),
        "sectors": ["health"],
    },

    # ---- Summary: subject_summary_dashboard ----
    {
        "id": "summary-subject-dashboard",
        "name": "Summary - Subject overview across multiple programs",
        "type": "EnrolmentSummary",
        "description": "Display a subject overview showing latest values from multiple programs and enrolments.",
        "complexity": 4,
        "format": "javascript",
        "template": (
            "'use strict';\n"
            "({params, imports}) => {\n"
            "    const enrolment = params.entity;\n"
            "    const individual = enrolment.individual;\n"
            "    const _ = imports.lodash;\n"
            "    const summaryItems = [];\n"
            "    // Demographics\n"
            "    summaryItems.push({\n"
            "        name: 'Age',\n"
            "        value: individual.getAgeInYears() + ' years',\n"
            "        abnormal: false\n"
            "    });\n"
            "    // Latest value from current enrolment\n"
            "    const concepts = [{{summary_concepts_list}}];\n"
            "    concepts.forEach(conceptName => {\n"
            "        const value = enrolment.findLatestObservationInEntireEnrolment(conceptName);\n"
            "        if (value !== undefined && value !== null) {\n"
            "            summaryItems.push({\n"
            "                name: conceptName,\n"
            "                value: Array.isArray(value) ? value.join(', ') : String(value),\n"
            "                abnormal: false\n"
            "            });\n"
            "        }\n"
            "    });\n"
            "    // Cross-program data\n"
            "    const otherPrograms = [{{cross_program_list}}];\n"
            "    otherPrograms.forEach(prog => {\n"
            "        const otherEnrolment = individual.enrolments.find(\n"
            "            e => e.program.name === prog.program && !e.programExitDateTime\n"
            "        );\n"
            "        if (otherEnrolment) {\n"
            "            const val = otherEnrolment.findLatestObservationInEntireEnrolment(prog.concept);\n"
            "            if (val !== undefined && val !== null) {\n"
            "                summaryItems.push({\n"
            "                    name: prog.program + ': ' + prog.concept,\n"
            "                    value: Array.isArray(val) ? val.join(', ') : String(val),\n"
            "                    abnormal: false\n"
            "                });\n"
            "            }\n"
            "        }\n"
            "    });\n"
            "    return summaryItems;\n"
            "};"
        ),
        "parameters": ["summary_concepts_list", "cross_program_list"],
        "example_filled": (
            "'use strict';\n"
            "({params, imports}) => {\n"
            "    const enrolment = params.entity;\n"
            "    const individual = enrolment.individual;\n"
            "    const _ = imports.lodash;\n"
            "    const summaryItems = [];\n"
            "    summaryItems.push({\n"
            "        name: 'Age',\n"
            "        value: individual.getAgeInYears() + ' years',\n"
            "        abnormal: false\n"
            "    });\n"
            "    const concepts = ['Weight', 'Hemoglobin', 'Blood Pressure'];\n"
            "    concepts.forEach(conceptName => {\n"
            "        const value = enrolment.findLatestObservationInEntireEnrolment(conceptName);\n"
            "        if (value !== undefined && value !== null) {\n"
            "            summaryItems.push({\n"
            "                name: conceptName,\n"
            "                value: Array.isArray(value) ? value.join(', ') : String(value),\n"
            "                abnormal: false\n"
            "            });\n"
            "        }\n"
            "    });\n"
            "    const otherPrograms = [{program: 'Nutrition Program', concept: 'Nutritional Status'}];\n"
            "    otherPrograms.forEach(prog => {\n"
            "        const otherEnrolment = individual.enrolments.find(\n"
            "            e => e.program.name === prog.program && !e.programExitDateTime\n"
            "        );\n"
            "        if (otherEnrolment) {\n"
            "            const val = otherEnrolment.findLatestObservationInEntireEnrolment(prog.concept);\n"
            "            if (val !== undefined && val !== null) {\n"
            "                summaryItems.push({\n"
            "                    name: prog.program + ': ' + prog.concept,\n"
            "                    value: Array.isArray(val) ? val.join(', ') : String(val),\n"
            "                    abnormal: false\n"
            "                });\n"
            "            }\n"
            "        }\n"
            "    });\n"
            "    return summaryItems;\n"
            "};"
        ),
        "sectors": ["health"],
    },

    # ---- WorkList: worklist_with_priority ----
    {
        "id": "worklist-priority",
        "name": "WorkList - Priority-scored worklist update",
        "type": "WorklistUpdation",
        "description": "Update a worklist with priority scoring based on overdue visits, high-risk status, and other criteria.",
        "complexity": 4,
        "format": "javascript",
        "template": (
            "'use strict';\n"
            "({params, imports}) => {\n"
            "    const individual = params.entity;\n"
            "    const moment = imports.moment;\n"
            "    const _ = imports.lodash;\n"
            "    const workItems = [];\n"
            "    const now = moment();\n"
            "    // Check all active enrolments\n"
            "    const activeEnrolments = (individual.enrolments || [])\n"
            "        .filter(e => !e.programExitDateTime);\n"
            "    activeEnrolments.forEach(enrolment => {\n"
            "        let priority = 0;\n"
            "        // Priority factor 1: Overdue scheduled visits\n"
            "        const scheduledVisits = (enrolment.encounters || [])\n"
            "            .filter(e => !e.voided && !e.encounterDateTime && e.earliestVisitDateTime);\n"
            "        const overdueVisits = scheduledVisits.filter(\n"
            "            e => moment(e.maxVisitDateTime || e.earliestVisitDateTime).isBefore(now)\n"
            "        );\n"
            "        priority += overdueVisits.length * {{overdue_weight}};\n"
            "        // Priority factor 2: Risk level from latest encounter\n"
            "        const riskValue = enrolment.findLatestObservationInEntireEnrolment('{{risk_concept}}');\n"
            "        if (riskValue === '{{high_risk_value}}' || (Array.isArray(riskValue) && riskValue.includes('{{high_risk_value}}'))) {\n"
            "            priority += {{high_risk_weight}};\n"
            "        }\n"
            "        // Priority factor 3: Days since last encounter\n"
            "        const completedEncounters = (enrolment.encounters || [])\n"
            "            .filter(e => !e.voided && e.encounterDateTime);\n"
            "        if (completedEncounters.length > 0) {\n"
            "            const lastEncounter = _.maxBy(completedEncounters, 'encounterDateTime');\n"
            "            const daysSince = now.diff(moment(lastEncounter.encounterDateTime), 'days');\n"
            "            if (daysSince > {{stale_days_threshold}}) {\n"
            "                priority += {{stale_weight}};\n"
            "            }\n"
            "        }\n"
            "        if (priority > 0) {\n"
            "            workItems.push({\n"
            "                name: individual.firstName + ' ' + (individual.lastName || ''),\n"
            "                program: enrolment.program.name,\n"
            "                priority: priority,\n"
            "                overdueCount: overdueVisits.length\n"
            "            });\n"
            "        }\n"
            "    });\n"
            "    workItems.sort((a, b) => b.priority - a.priority);\n"
            "    return workItems;\n"
            "};"
        ),
        "parameters": [
            "risk_concept", "high_risk_value",
            "overdue_weight", "high_risk_weight",
            "stale_days_threshold", "stale_weight",
        ],
        "example_filled": (
            "'use strict';\n"
            "({params, imports}) => {\n"
            "    const individual = params.entity;\n"
            "    const moment = imports.moment;\n"
            "    const _ = imports.lodash;\n"
            "    const workItems = [];\n"
            "    const now = moment();\n"
            "    const activeEnrolments = (individual.enrolments || [])\n"
            "        .filter(e => !e.programExitDateTime);\n"
            "    activeEnrolments.forEach(enrolment => {\n"
            "        let priority = 0;\n"
            "        const scheduledVisits = (enrolment.encounters || [])\n"
            "            .filter(e => !e.voided && !e.encounterDateTime && e.earliestVisitDateTime);\n"
            "        const overdueVisits = scheduledVisits.filter(\n"
            "            e => moment(e.maxVisitDateTime || e.earliestVisitDateTime).isBefore(now)\n"
            "        );\n"
            "        priority += overdueVisits.length * 3;\n"
            "        const riskValue = enrolment.findLatestObservationInEntireEnrolment('Risk Level');\n"
            "        if (riskValue === 'High' || (Array.isArray(riskValue) && riskValue.includes('High'))) {\n"
            "            priority += 5;\n"
            "        }\n"
            "        const completedEncounters = (enrolment.encounters || [])\n"
            "            .filter(e => !e.voided && e.encounterDateTime);\n"
            "        if (completedEncounters.length > 0) {\n"
            "            const lastEncounter = _.maxBy(completedEncounters, 'encounterDateTime');\n"
            "            const daysSince = now.diff(moment(lastEncounter.encounterDateTime), 'days');\n"
            "            if (daysSince > 30) {\n"
            "                priority += 2;\n"
            "            }\n"
            "        }\n"
            "        if (priority > 0) {\n"
            "            workItems.push({\n"
            "                name: individual.firstName + ' ' + (individual.lastName || ''),\n"
            "                program: enrolment.program.name,\n"
            "                priority: priority,\n"
            "                overdueCount: overdueVisits.length\n"
            "            });\n"
            "        }\n"
            "    });\n"
            "    workItems.sort((a, b) => b.priority - a.priority);\n"
            "    return workItems;\n"
            "};"
        ),
        "sectors": ["all"],
    },
]

# Build an index for fast lookup by id
_TEMPLATE_INDEX: dict[str, dict[str, Any]] = {t["id"]: t for t in RULE_TEMPLATES}

# ---------------------------------------------------------------------------
# Declarative rule builder
# ---------------------------------------------------------------------------

_VALID_OPERATORS = {
    "containsAnswerConceptName",
    "equals",
    "lessThan",
    "greaterThan",
    "lessThanOrEqual",
    "greaterThanOrEqual",
    "defined",
    "notDefined",
    "notContainsAnswerConceptName",
    "containsAnswerConceptNameOtherThan",
}


def build_declarative_rule(
    trigger_concept: dict[str, Any],
    trigger_answer: dict[str, Any] | None = None,
    target_element: dict[str, Any] | None = None,
    action: str = "showFormElement",
    operator: str = "containsAnswerConceptName",
    scope: str = "encounter",
    compound_conjunction: str = "And",
    additional_conditions: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build a properly formatted Avni declarative rule JSON.

    Parameters
    ----------
    trigger_concept : dict
        Must contain ``name``, ``uuid``, and ``dataType``.
    trigger_answer : dict or None
        For coded fields: ``{"names": ["Yes"], "uuids": ["uuid-here"]}``.
        For value comparisons: ``{"value": "5"}``.
        May be ``None`` for ``defined``/``notDefined`` operators.
    target_element : dict or None
        Optional ``{"uuid": "...", "name": "..."}`` of the target form element.
    action : str
        One of ``showFormElement`` (default) or ``hideFormElement``.
    operator : str
        One of the Avni declarative rule operators.
    scope : str
        ``encounter``, ``enrolment``, or ``registration``.
    compound_conjunction : str
        ``And`` or ``Or`` when combining multiple conditions.
    additional_conditions : list or None
        Extra condition dicts with the same structure as the primary one.

    Returns
    -------
    dict
        A complete declarative rule JSON ready for use in Avni.
    """
    if operator not in _VALID_OPERATORS:
        raise ValueError(
            f"Invalid operator '{operator}'. Must be one of: {', '.join(sorted(_VALID_OPERATORS))}"
        )

    # Build RHS based on operator
    if operator in ("defined", "notDefined"):
        rhs: dict[str, Any] = {"type": "value", "value": None}
    elif trigger_answer and "names" in trigger_answer:
        rhs = {
            "type": "answerConcept",
            "answerConceptNames": trigger_answer["names"],
            "answerConceptUuids": trigger_answer.get("uuids", []),
        }
    elif trigger_answer and "value" in trigger_answer:
        rhs = {
            "type": "value",
            "value": str(trigger_answer["value"]),
        }
    else:
        rhs = {"type": "value", "value": None}

    primary_rule = {
        "lhs": {
            "type": "concept",
            "scope": scope,
            "conceptName": trigger_concept["name"],
            "conceptUuid": trigger_concept.get("uuid", ""),
            "conceptDataType": trigger_concept.get("dataType", "Coded"),
        },
        "operator": operator,
        "rhs": rhs,
    }

    rules_list = [primary_rule]

    if additional_conditions:
        for cond in additional_conditions:
            cond_operator = cond.get("operator", "containsAnswerConceptName")
            if cond_operator in ("defined", "notDefined"):
                cond_rhs: dict[str, Any] = {"type": "value", "value": None}
            elif "answer_names" in cond:
                cond_rhs = {
                    "type": "answerConcept",
                    "answerConceptNames": cond["answer_names"],
                    "answerConceptUuids": cond.get("answer_uuids", []),
                }
            elif "value" in cond:
                cond_rhs = {
                    "type": "value",
                    "value": str(cond["value"]),
                }
            else:
                cond_rhs = {"type": "value", "value": None}

            rules_list.append(
                {
                    "lhs": {
                        "type": "concept",
                        "scope": cond.get("scope", scope),
                        "conceptName": cond["concept_name"],
                        "conceptUuid": cond.get("concept_uuid", ""),
                        "conceptDataType": cond.get("data_type", "Coded"),
                    },
                    "operator": cond_operator,
                    "rhs": cond_rhs,
                }
            )

    return {
        "declarativeRule": [
            {
                "conditions": [
                    {
                        "compoundRule": {
                            "conjunction": compound_conjunction,
                            "rules": rules_list,
                        }
                    }
                ],
                "actions": [{"actionType": action}],
            }
        ]
    }


# ---------------------------------------------------------------------------
# Template matching
# ---------------------------------------------------------------------------

# Keywords associated with each template id for matching
_TEMPLATE_KEYWORDS: dict[str, list[str]] = {
    "skip-logic-coded": [
        "skip", "logic", "show", "hide", "coded", "select",
        "answer", "conditional", "visibility", "viewfilter",
    ],
    "skip-logic-gender": [
        "skip", "logic", "gender", "male", "female", "sex",
        "show", "hide", "viewfilter",
    ],
    "skip-logic-age": [
        "skip", "logic", "age", "years", "old", "range",
        "show", "hide", "viewfilter",
    ],
    "skip-logic-compound": [
        "skip", "logic", "compound", "and", "or", "multiple",
        "conditions", "combined", "viewfilter",
    ],
    "skip-logic-numeric-range": [
        "skip", "logic", "numeric", "range", "number", "value",
        "between", "show", "hide", "viewfilter",
    ],
    "skip-logic-multiselect-filter": [
        "skip", "logic", "multiselect", "multi", "select",
        "filter", "contains", "viewfilter",
    ],
    "decision-bmi": [
        "bmi", "body", "mass", "index", "height", "weight",
        "calculate", "decision", "nutrition",
    ],
    "decision-age-calculation": [
        "age", "calculate", "dob", "date", "birth", "years",
        "months", "decision",
    ],
    "decision-nutrition-status": [
        "nutrition", "sam", "mam", "muac", "malnutrition",
        "wasting", "status", "decision",
    ],
    "decision-risk-categorization": [
        "risk", "categorize", "categorization", "high", "medium",
        "low", "score", "decision",
    ],
    "visit-schedule-monthly": [
        "visit", "schedule", "monthly", "recurring", "follow",
        "up", "followup", "next", "days",
    ],
    "visit-schedule-conditional": [
        "visit", "schedule", "conditional", "risk", "frequency",
        "high", "risk", "based",
    ],
    "visit-schedule-cancel-reschedule": [
        "visit", "cancel", "reschedule", "cancelled", "replacement",
        "delay", "schedule",
    ],
    "validation-numeric-range": [
        "validate", "validation", "numeric", "range", "min",
        "max", "check", "number",
    ],
    "validation-date-range": [
        "validate", "validation", "date", "range", "future",
        "past", "check",
    ],
    "validation-cross-field": [
        "validate", "validation", "cross", "field", "consistent",
        "compare", "two", "fields",
    ],
    "eligibility-age-gender": [
        "eligibility", "eligible", "age", "gender", "program",
        "enrol", "enroll",
    ],
    "eligibility-enrolment-check": [
        "eligibility", "eligible", "enrolment", "enrollment",
        "already", "enrolled", "duplicate", "check",
    ],
    "checklist-vaccination": [
        "checklist", "vaccination", "vaccine", "immunization",
        "schedule", "due", "date",
    ],
    "enrolment-summary-key-metrics": [
        "enrolment", "enrollment", "summary", "metrics", "display",
        "key", "overview",
    ],
    "decision-referral": [
        "referral", "refer", "danger", "signs", "critical",
        "facility", "decision",
    ],
    "viewfilter-attendance": [
        "attendance", "absent", "present", "marking", "reason",
        "viewfilter", "skip",
    ],
    "viewfilter-edit-handler": [
        "edit", "handler", "readonly", "read-only", "editable",
        "disable", "viewfilter",
    ],
    # -- New template keywords --
    "viewfilter-multi-concept-dependency": [
        "skip", "logic", "multi", "multiple", "concept", "dependency",
        "combined", "and", "or", "show", "hide", "viewfilter",
    ],
    "viewfilter-age-gender-conditional": [
        "skip", "logic", "age", "gender", "female", "male", "combination",
        "conditional", "show", "hide", "viewfilter",
    ],
    "viewfilter-cross-form-reference": [
        "skip", "logic", "cross", "form", "encounter", "reference",
        "other", "different", "lookup", "viewfilter",
    ],
    "decision-multi-axis": [
        "decision", "multi", "axis", "clinical", "bmi", "age", "bp",
        "blood", "pressure", "multiple", "parameter", "combined",
    ],
    "decision-coded-to-coded-mapping": [
        "decision", "coded", "mapping", "map", "lookup", "translate",
        "convert", "answer", "category",
    ],
    "decision-cumulative-risk-score": [
        "decision", "cumulative", "risk", "score", "weighted", "factor",
        "calculate", "category", "points",
    ],
    "visit-schedule-recurring": [
        "visit", "schedule", "recurring", "repeat", "interval", "regular",
        "every", "cycle", "weekly", "monthly",
    ],
    "visit-schedule-phase-based": [
        "visit", "schedule", "phase", "conditional", "stage", "treatment",
        "program", "different", "type",
    ],
    "visit-schedule-cross-program": [
        "visit", "schedule", "cross", "program", "another", "different",
        "trigger", "event", "child", "newborn",
    ],
    "validation-cross-field-numeric": [
        "validate", "validation", "cross", "field", "numeric", "compare",
        "less", "greater", "systolic", "diastolic",
    ],
    "validation-date-range-flexible": [
        "validate", "validation", "date", "range", "flexible", "future",
        "past", "age", "birth", "duration",
    ],
    "validation-conditional-required": [
        "validate", "validation", "conditional", "required", "mandatory",
        "when", "other", "specify",
    ],
    "eligibility-complex-enrolment": [
        "eligibility", "eligible", "complex", "enrolment", "enrollment",
        "multi", "condition", "age", "gender", "location",
    ],
    "eligibility-encounter-with-history": [
        "eligibility", "eligible", "encounter", "history", "previous",
        "prerequisite", "screening", "follow", "cooldown",
    ],
    "checklist-dynamic": [
        "checklist", "dynamic", "conditional", "items", "age", "based",
        "immunization", "vaccination", "schedule",
    ],
    "summary-enrolment-with-alerts": [
        "summary", "enrolment", "enrollment", "alert", "abnormal",
        "indicator", "threshold", "color", "warning",
    ],
    "summary-subject-dashboard": [
        "summary", "subject", "dashboard", "overview", "multiple",
        "programs", "cross", "program", "latest",
    ],
    "worklist-priority": [
        "worklist", "priority", "scoring", "overdue", "risk", "task",
        "update", "sort", "work", "list",
    ],
}


def find_matching_templates(
    description: str,
    rule_type: str | None = None,
    limit: int = 5,
) -> list[dict[str, Any]]:
    """Find templates matching a natural language description.

    Uses keyword overlap scoring with bonus for exact phrase matches.

    Parameters
    ----------
    description : str
        The natural language description of the desired rule.
    rule_type : str or None
        If provided, filter templates to this rule type first.
    limit : int
        Maximum number of templates to return.

    Returns
    -------
    list[dict]
        Top matching templates, sorted by relevance score descending.
    """
    description_lower = description.lower()
    description_words = set(re.findall(r"[a-z]+", description_lower))

    candidates = RULE_TEMPLATES
    if rule_type:
        candidates = [t for t in candidates if t["type"].lower() == rule_type.lower()]

    scored: list[tuple[float, dict[str, Any]]] = []

    for template in candidates:
        template_id = template["id"]
        keywords = _TEMPLATE_KEYWORDS.get(template_id, [])

        # Word overlap score
        keyword_set = set(keywords)
        overlap = description_words & keyword_set
        if not overlap:
            # Check if template name or description words overlap
            name_words = set(re.findall(r"[a-z]+", template["name"].lower()))
            desc_words = set(
                re.findall(r"[a-z]+", template["description"].lower())
            )
            overlap = description_words & (name_words | desc_words)

        word_score = len(overlap) / max(len(keyword_set), 1) if keyword_set else 0.0

        # Exact phrase bonus -- check if template name appears in description
        phrase_bonus = 0.0
        template_name_lower = template["name"].lower()
        if template_name_lower in description_lower:
            phrase_bonus = 0.5
        # Check for key phrases from template description
        for phrase in re.findall(r"[a-z]+ [a-z]+", template["description"].lower()):
            if phrase in description_lower:
                phrase_bonus += 0.1

        # Type match bonus
        type_bonus = 0.0
        if template["type"].lower() in description_lower:
            type_bonus = 0.2

        total_score = word_score + phrase_bonus + type_bonus
        if total_score > 0:
            scored.append((total_score, template))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [t for _, t in scored[:limit]]


def get_template_by_id(template_id: str) -> dict[str, Any] | None:
    """Return a single template by its id, or None if not found."""
    return _TEMPLATE_INDEX.get(template_id)


# ---------------------------------------------------------------------------
# Rule testing / validation
# ---------------------------------------------------------------------------

def _check_js_syntax(code: str) -> tuple[bool, list[str]]:
    """Basic JavaScript syntax validation.

    Checks for balanced braces, parentheses, brackets, and common syntax
    issues. This is not a full JS parser but catches the most common
    problems.

    Returns
    -------
    tuple[bool, list[str]]
        ``(is_valid, list_of_errors)``
    """
    errors: list[str] = []

    # Check balanced braces
    brace_count = 0
    paren_count = 0
    bracket_count = 0

    in_string_single = False
    in_string_double = False
    in_string_template = False
    in_line_comment = False
    in_block_comment = False
    prev_char = ""

    for i, ch in enumerate(code):
        # Handle comments
        if in_line_comment:
            if ch == "\n":
                in_line_comment = False
            prev_char = ch
            continue
        if in_block_comment:
            if prev_char == "*" and ch == "/":
                in_block_comment = False
            prev_char = ch
            continue
        if prev_char == "/" and ch == "/" and not (in_string_single or in_string_double or in_string_template):
            in_line_comment = True
            prev_char = ch
            continue
        if prev_char == "/" and ch == "*" and not (in_string_single or in_string_double or in_string_template):
            in_block_comment = True
            prev_char = ch
            continue

        # Handle strings
        if ch == "'" and not in_string_double and not in_string_template and prev_char != "\\":
            in_string_single = not in_string_single
        elif ch == '"' and not in_string_single and not in_string_template and prev_char != "\\":
            in_string_double = not in_string_double
        elif ch == "`" and not in_string_single and not in_string_double and prev_char != "\\":
            in_string_template = not in_string_template

        if not (in_string_single or in_string_double or in_string_template):
            if ch == "{":
                brace_count += 1
            elif ch == "}":
                brace_count -= 1
            elif ch == "(":
                paren_count += 1
            elif ch == ")":
                paren_count -= 1
            elif ch == "[":
                bracket_count += 1
            elif ch == "]":
                bracket_count -= 1

        if brace_count < 0:
            errors.append(f"Unexpected closing brace '}}' at position {i}")
        if paren_count < 0:
            errors.append(f"Unexpected closing parenthesis ')' at position {i}")
        if bracket_count < 0:
            errors.append(f"Unexpected closing bracket ']' at position {i}")

        prev_char = ch

    if brace_count != 0:
        errors.append(f"Unbalanced braces: {brace_count} unclosed '{{' remain")
    if paren_count != 0:
        errors.append(f"Unbalanced parentheses: {paren_count} unclosed '(' remain")
    if bracket_count != 0:
        errors.append(f"Unbalanced brackets: {bracket_count} unclosed '[' remain")

    if in_string_single:
        errors.append("Unterminated single-quoted string")
    if in_string_double:
        errors.append("Unterminated double-quoted string")
    if in_string_template:
        errors.append("Unterminated template literal")
    if in_block_comment:
        errors.append("Unterminated block comment")

    return (len(errors) == 0, errors)


def _extract_concept_refs(code: str) -> list[str]:
    """Extract concept name references from rule code.

    Looks for patterns like:
    - getObservationValue('Concept Name')
    - getObservationReadableValue("Concept Name")
    - valueInEncounter("Concept Name")
    - valueInRegistration("Concept Name")
    - valueInEnrolment("Concept Name")
    - containsAnswerConceptName("Answer Name")
    - "conceptName": "Concept Name"
    """
    patterns = [
        r"""getObservationValue\s*\(\s*['"]([^'"]+)['"]\s*\)""",
        r"""getObservationReadableValue\s*\(\s*['"]([^'"]+)['"]\s*\)""",
        r"""valueInEncounter\s*\(\s*['"]([^'"]+)['"]\s*\)""",
        r"""valueInRegistration\s*\(\s*['"]([^'"]+)['"]\s*\)""",
        r"""valueInEnrolment\s*\(\s*['"]([^'"]+)['"]\s*\)""",
        r"""containsAnswerConceptName\s*\(\s*['"]([^'"]+)['"]\s*\)""",
        r"""findLatestObservationInEntireEnrolment\s*\(\s*['"]([^'"]+)['"]\s*\)""",
        r""""conceptName"\s*:\s*"([^"]+)""",
        r"""'conceptName'\s*:\s*'([^']+)'""",
        r"""name\s*:\s*['"]([^'"]+)['"]\s*,\s*\n?\s*value""",
    ]

    refs: list[str] = []
    for pattern in patterns:
        matches = re.findall(pattern, code)
        refs.extend(matches)

    return list(dict.fromkeys(refs))


async def test_rule(
    code: str,
    rule_type: str,
    concepts: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Test and validate a rule.

    Parameters
    ----------
    code : str
        The rule code (JavaScript or JSON declarative).
    rule_type : str
        The rule type (ViewFilter, Decision, VisitSchedule, Validation,
        Checklist, EnrolmentSummary, Eligibility, WorklistUpdation).
    concepts : list or None
        List of concept dicts with at least ``name`` key for cross-reference
        checking.

    Returns
    -------
    dict
        ``{"valid": bool, "syntax_ok": bool, "concept_refs_ok": bool,
           "common_errors": [...], "warnings": [...], "errors": [...],
           "sample_test_data": dict}``
    """
    warnings: list[str] = []
    errors: list[str] = []

    # Determine format
    stripped = code.strip()
    is_declarative = stripped.startswith("{") or stripped.startswith("[")

    # Syntax check
    syntax_ok = True
    if is_declarative:
        try:
            parsed = json.loads(stripped)
            # Validate declarative structure
            if isinstance(parsed, dict):
                if "declarativeRule" not in parsed:
                    warnings.append(
                        "Declarative rule JSON does not contain a 'declarativeRule' key at the top level."
                    )
                else:
                    rules_list = parsed["declarativeRule"]
                    if not isinstance(rules_list, list) or len(rules_list) == 0:
                        errors.append("'declarativeRule' must be a non-empty array.")
                        syntax_ok = False
                    else:
                        for idx, entry in enumerate(rules_list):
                            if "conditions" not in entry:
                                errors.append(
                                    f"Rule entry [{idx}] is missing 'conditions'."
                                )
                                syntax_ok = False
                            if "actions" not in entry:
                                errors.append(
                                    f"Rule entry [{idx}] is missing 'actions'."
                                )
                                syntax_ok = False
                            # Validate condition structure
                            for cond in entry.get("conditions", []):
                                if "compoundRule" in cond:
                                    cr = cond["compoundRule"]
                                    if "rules" not in cr or not cr["rules"]:
                                        errors.append(
                                            f"Rule entry [{idx}] compoundRule has no rules."
                                        )
                                        syntax_ok = False
                                    if "conjunction" not in cr:
                                        warnings.append(
                                            f"Rule entry [{idx}] compoundRule missing 'conjunction' (And/Or)."
                                        )
        except json.JSONDecodeError as e:
            syntax_ok = False
            errors.append(f"Invalid JSON: {e}")
    else:
        ok, js_errors = _check_js_syntax(stripped)
        syntax_ok = ok
        errors.extend(js_errors)

        # Check that it looks like an Avni rule function
        if "({params, imports})" not in stripped and "({params,imports})" not in stripped:
            # Also allow params and imports in different forms
            if "params" not in stripped:
                warnings.append(
                    "Rule does not reference 'params'. Avni rules receive ({params, imports})."
                )

        # Check rule type specific patterns
        valid_types = {
            "ViewFilter", "Decision", "VisitSchedule", "Validation",
            "Checklist", "EnrolmentSummary", "Eligibility", "WorklistUpdation",
        }
        if rule_type not in valid_types:
            warnings.append(
                f"Unknown rule type '{rule_type}'. Expected one of: {', '.join(sorted(valid_types))}."
            )

        if rule_type == "ViewFilter" and "FormElementStatusBuilder" not in stripped:
            if "FormElementStatus" not in stripped:
                warnings.append(
                    "ViewFilter rules typically use FormElementStatusBuilder or FormElementStatus."
                )
        if rule_type == "VisitSchedule" and "VisitScheduleBuilder" not in stripped:
            warnings.append(
                "VisitSchedule rules typically use VisitScheduleBuilder."
            )
        if rule_type == "Decision" and "decisions" not in stripped.lower():
            warnings.append(
                "Decision rules typically return a decisions object with "
                "encounterDecisions/enrolmentDecisions/registrationDecisions."
            )
        if rule_type == "Validation" and "createValidationError" not in stripped:
            if "failures" not in stripped.lower() and "validationresults" not in stripped.lower():
                warnings.append(
                    "Validation rules typically use createValidationError and return an array of failures."
                )

    # Common error detection for JavaScript rules
    common_errors: list[str] = []
    if not is_declarative:
        common_errors = _detect_common_js_errors(stripped, rule_type)

    # Concept reference check
    concept_refs = _extract_concept_refs(code)
    concept_refs_ok = True

    if concepts and concept_refs:
        known_names = {c.get("name", "").lower() for c in concepts if "name" in c}
        # Also add answer concept names if present
        for c in concepts:
            for answer in c.get("answers", []):
                if isinstance(answer, dict) and "name" in answer:
                    known_names.add(answer["name"].lower())
                elif isinstance(answer, str):
                    known_names.add(answer.lower())

        for ref in concept_refs:
            if ref.lower() not in known_names:
                warnings.append(
                    f"Concept reference '{ref}' not found in the provided concepts list."
                )
                concept_refs_ok = False
    elif not concepts and concept_refs:
        warnings.append(
            f"Rule references {len(concept_refs)} concept(s) but no concepts were "
            "provided for cross-reference checking."
        )

    # Validate output format expectations
    output_warnings = _validate_output_format(stripped, rule_type, is_declarative)
    warnings.extend(output_warnings)

    valid = syntax_ok and concept_refs_ok and len(errors) == 0 and len(common_errors) == 0

    # Generate sample test data for this rule type
    sample_test_data = _generate_sample_test_data(rule_type, concept_refs)

    return {
        "valid": valid,
        "syntax_ok": syntax_ok,
        "concept_refs_ok": concept_refs_ok,
        "common_errors": common_errors,
        "warnings": warnings,
        "errors": errors,
        "sample_test_data": sample_test_data,
    }


def _detect_common_js_errors(code: str, rule_type: str) -> list[str]:
    """Detect common JavaScript errors in Avni rules.

    Checks for:
    - Undefined variable usage (common typos)
    - Missing imports references
    - Incorrect return types
    - Node.js API usage (not available in Avni runtime)
    """
    common_errors: list[str] = []

    # Check for Node.js APIs (not available in Avni runtime)
    node_apis = ["require(", "module.exports", "process.", "fs.", "path.", "Buffer."]
    for api in node_apis:
        if api in code:
            common_errors.append(
                f"Node.js API '{api.rstrip('.')}' is not available in the Avni rule runtime."
            )

    # Check for common typos and undefined references
    if "formElement" in code and "params.formElement" not in code:
        if "const formElement" not in code and "let formElement" not in code:
            # formElement used but never assigned from params
            if rule_type == "ViewFilter":
                common_errors.append(
                    "formElement appears to be used without being assigned from params.formElement."
                )

    # Check for use strict
    if "'use strict'" not in code and '"use strict"' not in code:
        common_errors.append(
            "Missing 'use strict' directive. Avni rules must start with 'use strict'."
        )

    # Check for console.error/warn (log is OK)
    if "console.error" in code or "console.warn" in code:
        common_errors.append(
            "console.error/warn may not be available. Use imports.log or console.log instead."
        )

    # Check for async/await (not supported in Avni rule engine)
    if "async " in code or "await " in code:
        common_errors.append(
            "async/await is not supported in the Avni rule engine. Rules must be synchronous."
        )

    # Check Decision rules return all three arrays
    if rule_type == "Decision":
        if "encounterDecisions" in code and "enrolmentDecisions" not in code:
            common_errors.append(
                "Decision rule should return object with all three arrays: "
                "encounterDecisions, enrolmentDecisions, registrationDecisions."
            )

    return common_errors


def _validate_output_format(code: str, rule_type: str, is_declarative: bool) -> list[str]:
    """Validate that the rule returns the expected output format for its type."""
    warnings: list[str] = []

    if is_declarative:
        return warnings

    code_lower = code.lower()

    if rule_type == "ViewFilter":
        if "return" not in code:
            warnings.append("ViewFilter rule does not contain a return statement.")
        elif "statusbuilder.build()" not in code_lower and "formelementstatus" not in code_lower:
            warnings.append(
                "ViewFilter rule should return statusBuilder.build() or a FormElementStatus instance."
            )

    elif rule_type == "Decision":
        if "return" not in code:
            warnings.append("Decision rule does not contain a return statement.")
        elif "return decisions" not in code_lower:
            warnings.append(
                "Decision rule should return the decisions object."
            )

    elif rule_type == "VisitSchedule":
        if "return" not in code:
            warnings.append("VisitSchedule rule does not contain a return statement.")
        elif "getall()" not in code_lower:
            warnings.append(
                "VisitSchedule rule should return scheduleBuilder.getAll()."
            )

    elif rule_type == "Validation":
        if "return" not in code:
            warnings.append("Validation rule does not contain a return statement.")

    elif rule_type == "Eligibility":
        if "return" not in code:
            warnings.append("Eligibility rule does not contain a return statement.")

    return warnings


def _generate_sample_test_data(rule_type: str, concept_refs: list[str]) -> dict[str, Any]:
    """Generate sample test data appropriate for the rule type.

    This helps users test their rules by providing mock entity objects
    with the correct structure.
    """
    # Build observations from concept references
    sample_observations: dict[str, Any] = {}
    for ref in concept_refs:
        sample_observations[ref] = f"<sample_value_for_{ref}>"

    base_individual = {
        "uuid": "test-individual-uuid",
        "firstName": "Test",
        "lastName": "User",
        "dateOfBirth": "2000-01-01",
        "gender": {"name": "Female"},
        "lowestAddressLevel": {"name": "Test Village"},
        "subjectType": {"name": "Individual"},
        "observations": sample_observations,
    }

    base_enrolment = {
        "uuid": "test-enrolment-uuid",
        "program": {"name": "Test Program"},
        "enrolmentDateTime": "2025-01-01T00:00:00Z",
        "programExitDateTime": None,
        "individual": base_individual,
        "encounters": [],
        "observations": sample_observations,
    }

    base_encounter = {
        "uuid": "test-encounter-uuid",
        "encounterType": {"name": "Test Visit"},
        "encounterDateTime": "2025-06-01T00:00:00Z",
        "cancelDateTime": None,
        "programEnrolment": base_enrolment,
        "individual": base_individual,
        "observations": sample_observations,
    }

    base_form_element = {
        "uuid": "test-form-element-uuid",
        "name": "Test Element",
        "concept": {"name": "Test Concept", "uuid": "test-concept-uuid"},
    }

    if rule_type == "ViewFilter":
        return {
            "params": {
                "entity": base_encounter,
                "formElement": base_form_element,
                "questionGroupIndex": 0,
            },
            "expected_return": "FormElementStatus {uuid, visibility, value, answersToSkip, validationErrors}",
        }
    elif rule_type == "Decision":
        return {
            "params": {
                "entity": base_encounter,
                "decisions": {
                    "encounterDecisions": [],
                    "enrolmentDecisions": [],
                    "registrationDecisions": [],
                },
            },
            "expected_return": "{encounterDecisions: [], enrolmentDecisions: [], registrationDecisions: []}",
        }
    elif rule_type == "VisitSchedule":
        return {
            "params": {
                "entity": base_encounter,
                "programEnrolment": base_enrolment,
            },
            "expected_return": "Array of {name, encounterType, earliestDate, maxDate}",
        }
    elif rule_type == "Validation":
        return {
            "params": {
                "entity": base_encounter,
            },
            "expected_return": "Array of validation error objects",
        }
    elif rule_type == "Eligibility":
        return {
            "params": {
                "entity": base_individual,
            },
            "expected_return": "boolean (true = eligible, false = not eligible)",
        }
    elif rule_type == "EnrolmentSummary":
        return {
            "params": {
                "entity": base_enrolment,
            },
            "expected_return": "Array of {name, value, abnormal}",
        }
    elif rule_type == "Checklist":
        return {
            "params": {
                "entity": base_enrolment,
            },
            "expected_return": "{name, items: [{name, dueDate, maxDate}]}",
        }
    elif rule_type == "WorklistUpdation":
        return {
            "params": {
                "entity": base_individual,
            },
            "expected_return": "Array of work items with priority",
        }
    else:
        return {
            "params": {"entity": base_encounter},
            "expected_return": "Unknown -- rule type not recognized",
        }


# ---------------------------------------------------------------------------
# AI-powered rule generation
# ---------------------------------------------------------------------------

# RULE_GENERATION_SYSTEM_PROMPT has been moved to app.services.rule_prompts
# and is imported at the top of this file for backward compatibility.

# The following string was the inline prompt definition. It is now maintained
# in rule_prompts.py. Kept here as _LEGACY_PROMPT_REF to avoid removing 340
# lines in a single edit pass -- will be fully removed in the next cleanup.
_LEGACY_PROMPT_REF = """## Entity Methods

### Individual
- `individual.uuid` -- unique identifier
- `individual.firstName` / `individual.lastName` -- name fields
- `individual.dateOfBirth` -- date of birth
- `individual.getAgeInYears()` / `individual.getAgeInMonths()` / `individual.getAgeInWeeks()` / `individual.getAgeInDays()` -- age calculations
- `individual.gender.name` -- gender name string
- `individual.isMale()` / `individual.isFemale()` -- gender checks
- `individual.subjectType.name` -- subject type name
- `individual.lowestAddressLevel.name` -- lowest address level name
- `individual.getObservationValue(conceptName)` -- get raw observation value
- `individual.getObservationReadableValue(conceptName)` -- get human-readable observation value
- `individual.findObservation(conceptName)` -- get full observation object
- `individual.encounters` -- all encounters
- `individual.enrolments` -- all program enrolments
- `individual.groupSubjects` -- group members (if group subject)

### ProgramEnrolment
- `programEnrolment.uuid` -- unique identifier
- `programEnrolment.individual` -- parent Individual
- `programEnrolment.program.name` -- program name
- `programEnrolment.enrolmentDateTime` -- enrolment date
- `programEnrolment.programExitDateTime` -- exit date (null if active)
- `programEnrolment.getObservationValue(conceptName)` -- observation from enrolment
- `programEnrolment.getObservationReadableValue(conceptName)` -- readable observation
- `programEnrolment.findLatestObservationInEntireEnrolment(conceptName)` -- search all encounters
- `programEnrolment.encounters` -- encounters in this enrolment

### Encounter / ProgramEncounter
- `encounter.uuid` -- unique identifier
- `encounter.encounterType.name` -- encounter type name
- `encounter.encounterDateTime` -- encounter date/time
- `encounter.cancelDateTime` -- cancellation date (if cancelled)
- `encounter.earliestVisitDateTime` -- scheduled earliest date
- `encounter.maxVisitDateTime` -- scheduled max date
- `encounter.individual` -- parent Individual
- `encounter.programEnrolment` -- parent ProgramEnrolment (ProgramEncounter only)
- `encounter.getObservationValue(conceptName)` -- observation value
- `encounter.getObservationReadableValue(conceptName)` -- readable value
- `encounter.findObservation(conceptName)` -- full observation object

## Complete RuleCondition Fluent API Reference

The RuleCondition class provides a fluent API for building conditions:

### Constructor
```javascript
const condition = new imports.rulesConfig.RuleCondition({
    individual,          // Individual entity
    programEnrolment,    // ProgramEnrolment entity
    programEncounter,    // ProgramEncounter entity
    formElement          // FormElement (for ViewFilter)
});
```

### Value Source Methods (after `.when`)
```javascript
// Current context observations
.valueInEncounter(conceptName)
.valueInEncounter(conceptName, parentConceptUuid)  // for QuestionGroup
.valueInEnrolment(conceptName)
.valueInEnrolment(conceptName, parentConceptUuid)
.valueInRegistration(conceptName)
.valueInRegistration(conceptName, parentConceptUuid)

// Historical observations
.valueInLastEncounter(conceptName, encounterTypes?)
.valueInLastEncounter(conceptName, encounterTypes?, parentConceptUuid?)
.valueInEntireEnrolment(conceptName)
.valueInEntireEnrolment(conceptName, parentConceptUuid)
.latestValueInAllEncounters(conceptName)
.latestValueInAllEncounters(conceptName, parentConceptUuid)
.latestValueInPreviousEncounters(conceptName)
.latestValueInPreviousEncounters(conceptName, parentConceptUuid)
.latestValueInEntireEnrolment(conceptName)
.latestValueInEntireEnrolment(conceptName, parentConceptUuid)

// Special contexts
.valueInExit(conceptName)
.valueInCancelEncounter(conceptName)
.valueInDecisions(conceptName)
.valueInChecklistItem(conceptName)

// Question group support
.questionGroupValueInEncounter(childConceptUuid, groupNameUuid, groupIndex)
.questionGroupValueInEnrolment(childConceptUuid, groupNameUuid, groupIndex)
.questionGroupValueInRegistration(childConceptUuid, groupNameUuid, groupIndex)
```

### Demographic Shortcuts (after `.when`)
```javascript
.age             // Age in years
.ageInYears      // Age in years
.ageInMonths     // Age in months
.ageInWeeks      // Age in weeks
.ageInDays       // Age in days
.gender          // Gender name
.male            // Shortcut: gender === 'Male'
.female          // Shortcut: gender === 'Female'
.addressType     // Address level type
.lowestAddressLevel      // Lowest address level name
.lowestAddressLevelType  // Lowest address level type name
.encounterType           // Current encounter type name
.encounterMonth          // Month of encounter (1-12)
```

### Comparison Operators
```javascript
// For Coded concepts
.containsAnswerConceptName(name)
.containsAnyAnswerConceptName(...names)       // matches ANY of the given answers
.containsAnswerConceptNameOtherThan(name)     // has some answer other than
.yes           // shortcut for containsAnswerConceptName("Yes")
.no            // shortcut for containsAnswerConceptName("No")

// For Numeric/Date/Text values
.equals(value)
.equals(value, unitIfDate)        // e.g. .equals(5, 'years')
.equalsOneOf(...values)           // matches any of listed values
.lessThan(value)
.lessThan(value, unitIfDate)
.lessThanOrEqualTo(value)
.lessThanOrEqualTo(value, unitIfDate)
.greaterThan(value)
.greaterThan(value, unitIfDate)
.greaterThanOrEqualTo(value)
.greaterThanOrEqualTo(value, unitIfDate)

// Existence checks
.defined          // value exists and is not null
.notDefined       // value is null or does not exist

// Boolean / custom
.truthy           // value is truthy
.matchesFn(fn)    // custom function: .matchesFn(v => v > 10 && v < 20)
```

### Boolean Operators (chaining)
```javascript
.and    // logical AND -- chain another condition
.or     // logical OR -- chain another condition
.not    // logical NOT -- negate next condition
```

### Terminal Operations
```javascript
.matches()    // returns boolean: true if all conditions match
.then(fn)     // execute fn if conditions match
```

### FormElementStatusBuilder Methods
```javascript
statusBuilder.show()                          // begin show condition chain
statusBuilder.hide()                          // begin hide condition chain
statusBuilder.value(calculatedValue)          // set calculated value when condition matches
statusBuilder.skipAnswers("Ans1", "Ans2")     // hide specific coded answers
statusBuilder.showAnswers("Ans1", "Ans2")     // show only specific coded answers
statusBuilder.validationError("message")      // add validation error when condition matches
statusBuilder.build()                         // return FormElementStatus
```

## Rule Types and Return Patterns

### ViewFilter (Skip Logic)
Uses FormElementStatusBuilder to show/hide form elements:
```javascript
'use strict';
({params, imports}) => {
    const entity = params.entity;
    const formElement = params.formElement;
    const statusBuilder = new imports.rulesConfig.FormElementStatusBuilder({
        programEncounter: entity,
        formElement
    });
    statusBuilder.show()
        .when.valueInEncounter("Field Name")
        .containsAnswerConceptName("Answer");
    return statusBuilder.build();
};
```

### Decision
Returns an object with encounterDecisions, enrolmentDecisions, registrationDecisions arrays:
```javascript
'use strict';
({params, imports}) => {
    const decisions = {encounterDecisions: [], enrolmentDecisions: [], registrationDecisions: []};
    // ... logic ...
    decisions.encounterDecisions.push({name: 'Concept', value: computedValue});
    return decisions;
};
```

### VisitSchedule
Uses VisitScheduleBuilder:
```javascript
'use strict';
({params, imports}) => {
    const scheduleBuilder = new imports.rulesConfig.VisitScheduleBuilder({
        programEnrolment: params.entity.programEnrolment
    });
    const baseDate = params.entity.encounterDateTime || new Date();
    scheduleBuilder.add({
        name: 'Visit Name',
        encounterType: 'Type Name',
        earliestDate: imports.moment(baseDate).add(30, 'days').toDate(),
        maxDate: imports.moment(baseDate).add(45, 'days').toDate()
    });
    return scheduleBuilder.getAll();
};
```

### Validation
Returns an array of validation errors:
```javascript
'use strict';
({params, imports}) => {
    const failures = [];
    // ... check conditions ...
    failures.push(imports.rulesConfig.createValidationError('Error message'));
    return failures;
};
```

### Eligibility
Returns a boolean:
```javascript
'use strict';
({params, imports}) => {
    return someCondition;
};
```

### EnrolmentSummary
Returns an array of summary items:
```javascript
'use strict';
({params, imports}) => {
    return [{name: 'Label', value: 'Value', abnormal: false}];
};
```

### Checklist
Returns an object with name and items array:
```javascript
'use strict';
({params, imports}) => {
    return {
        name: 'Checklist Name',
        items: [{name: 'Item', dueDate: new Date(), maxDate: new Date()}]
    };
};
```

### WorklistUpdation
Returns an array of work items:
```javascript
'use strict';
({params, imports}) => {
    return [{name: 'Subject Name', program: 'Program', priority: 5}];
};
```

## Declarative Rules (JSON-based)

For simple skip logic, prefer declarative rules:
```json
{
    "declarativeRule": [{
        "conditions": [{
            "compoundRule": {
                "conjunction": "And",
                "rules": [{
                    "lhs": {
                        "type": "concept",
                        "scope": "encounter",
                        "conceptName": "Field Name",
                        "conceptUuid": "uuid-here",
                        "conceptDataType": "Coded"
                    },
                    "operator": "containsAnswerConceptName",
                    "rhs": {
                        "type": "answerConcept",
                        "answerConceptNames": ["Yes"],
                        "answerConceptUuids": ["uuid-here"]
                    }
                }]
            }
        }],
        "actions": [{"actionType": "showFormElement"}]
    }]
}
```

### LHS Types
- `{"type": "concept", "scope": "...", "conceptName": "...", "conceptUuid": "...", "conceptDataType": "..."}` -- concept-based
- `{"type": "gender"}` -- gender demographic
- `{"type": "ageInYears"}` / `{"type": "ageInMonths"}` / `{"type": "ageInDays"}` -- age demographics
- `{"type": "lowestAddressLevel"}` -- location

### Valid Operators
containsAnswerConceptName, containsAnyAnswerConceptName, containsAnswerConceptNameOtherThan,
equals, notEquals, lessThan, greaterThan, lessThanOrEqualTo, greaterThanOrEqualTo,
defined, notDefined

### Valid Scopes
encounter, enrolment, registration, entireEnrolment

### Valid Actions
showFormElement, hideFormElement, showFormElementGroup, hideFormElementGroup,
value, skipAnswers, showAnswers, validationError,
showProgram, hideProgram, showEncounterType, hideEncounterType,
addDecision, scheduleVisit, scheduleTask, formValidationError

## IMPORTANT RULES
1. Always start JavaScript rules with 'use strict';
2. Use the EXACT concept names and UUIDs from the provided form/concepts JSON.
3. For simple show/hide logic on coded fields, prefer declarative rules.
4. For complex logic (calculations, multiple conditions with JS logic, age-based), use JavaScript.
5. Always handle null/undefined values gracefully.
6. Return the correct data structure for the rule type.
7. Do NOT include any explanation or markdown -- return ONLY the rule code.
8. For Decision rules, always initialize all three arrays: encounterDecisions, enrolmentDecisions, registrationDecisions.
9. For coded values, handle both single-value and array results (multi-select returns array).
10. Use moment(date) for date manipulation, never raw Date arithmetic.
"""


async def generate_rule(
    description: str,
    rule_type: str | None = None,
    form_json: dict[str, Any] | None = None,
    concepts_json: list[dict[str, Any]] | None = None,
    complexity_hint: int | None = None,
    rag_context: str | None = None,
) -> dict[str, Any]:
    """Generate an Avni rule from a natural language description.

    Uses the LLM provider chain (claude_client with automatic failover)
    to generate the rule, providing matching templates as few-shot examples,
    RAG-retrieved production rule examples, and the form/concept context
    for accurate UUIDs.

    The task_type is ``rule_generation`` -- when provider chain routing
    is implemented in claude_client, this should prefer OpenAI/Anthropic
    for code generation quality.

    Parameters
    ----------
    description : str
        Natural language description of the desired rule.
    rule_type : str or None
        Target rule type. If None, the LLM infers it.
    form_json : dict or None
        The Avni form JSON definition for UUID accuracy.
    concepts_json : list or None
        The concepts list for concept name/UUID accuracy.
    complexity_hint : int or None
        1-5 hint about complexity. Lower values prefer declarative rules.
    rag_context : str or None
        Pre-retrieved RAG context (production rule examples, skill docs).
        When provided, injected into the prompt for better accuracy.

    Returns
    -------
    dict
        ``{"code": str, "type": str, "format": str, "confidence": float,
           "explanation": str, "warnings": list[str], "errors": list[str],
           "common_errors": list[str], "template_used": str|None,
           "sample_test_data": dict}``
    """
    # Find matching templates for few-shot examples
    matching_templates = find_matching_templates(description, rule_type=rule_type, limit=3)

    # Build the user prompt
    prompt_parts: list[str] = []
    prompt_parts.append(f"Generate an Avni rule for the following requirement:\n\n{description}")

    if rule_type:
        prompt_parts.append(f"\nRule type: {rule_type}")

    if complexity_hint is not None:
        if complexity_hint <= 2:
            prompt_parts.append(
                "\nPrefer a DECLARATIVE (JSON-based) rule if possible for this simple requirement."
            )
        else:
            prompt_parts.append(
                "\nThis is a complex requirement. Use JavaScript if needed."
            )

    # Add RAG context (production rule examples from knowledge base)
    if rag_context:
        prompt_parts.append(
            f"\n\n## Production Rule Examples (from real Avni implementations):\n{rag_context[:6000]}"
        )

    # Add template examples
    if matching_templates:
        prompt_parts.append("\n\n## Reference Templates (use as examples of correct patterns):\n")
        for i, tmpl in enumerate(matching_templates, 1):
            prompt_parts.append(
                f"### Example {i}: {tmpl['name']} ({tmpl['type']}, {tmpl['format']})\n"
                f"{tmpl['example_filled']}\n"
            )

    # Add form context
    if form_json:
        form_str = json.dumps(form_json, indent=2)
        if len(form_str) > 8000:
            form_str = form_str[:8000] + "\n... (truncated)"
        prompt_parts.append(f"\n\n## Form JSON (use exact concept names and UUIDs from this):\n```json\n{form_str}\n```")

    # Add concepts context
    if concepts_json:
        concepts_str = json.dumps(concepts_json, indent=2)
        if len(concepts_str) > 8000:
            concepts_str = concepts_str[:8000] + "\n... (truncated)"
        prompt_parts.append(f"\n\n## Concepts JSON (use exact names and UUIDs):\n```json\n{concepts_str}\n```")

    prompt_parts.append(
        "\n\nRespond with ONLY the rule code (JavaScript or declarative JSON). "
        "No markdown code fences, no explanations, no comments before or after the code."
    )

    user_prompt = "\n".join(prompt_parts)

    # Call LLM via provider chain (automatic failover: ollama -> groq -> anthropic)
    # TODO: when claude_client supports task_type routing, pass task_type="rule_generation"
    response_text = await claude_client.complete(
        messages=[{"role": "user", "content": user_prompt}],
        system_prompt=RULE_GENERATION_SYSTEM_PROMPT,
    )

    # Clean up the response
    code = response_text.strip()

    # Remove markdown code fences if present (LLMs often wrap in ```)
    if code.startswith("```"):
        lines = code.split("\n")
        # Remove first line (```javascript or ```)
        lines = lines[1:]
        # Remove last line if it's ```
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        code = "\n".join(lines).strip()

    # Also handle case where LLM wraps in single backticks or adds preamble
    if code.startswith("`") and code.endswith("`"):
        code = code[1:-1].strip()

    # Strip any leading explanation text before the actual rule
    for marker in ["'use strict'", '"use strict"', '{"declarativeRule"', "[{"]:
        idx = code.find(marker)
        if idx > 0 and idx < 200:
            # There's preamble text before the actual rule
            code = code[idx:]
            break

    # Determine format
    code_stripped = code.strip()
    if code_stripped.startswith("{") or code_stripped.startswith("["):
        rule_format = "declarative"
        # Validate JSON
        try:
            json.loads(code_stripped)
        except json.JSONDecodeError:
            rule_format = "javascript"
    else:
        rule_format = "javascript"

    # Determine the inferred type
    inferred_type = rule_type or _infer_rule_type(code)

    # Compute confidence based on validation
    warnings: list[str] = []
    confidence = 0.85  # Base confidence

    # Run comprehensive validation
    validation_result = await test_rule(
        code,
        inferred_type,
        concepts_json,
    )

    if not validation_result["syntax_ok"]:
        confidence -= 0.3
        warnings.extend(validation_result["errors"])
    if not validation_result["concept_refs_ok"]:
        confidence -= 0.15
    if validation_result.get("common_errors"):
        confidence -= 0.2
    warnings.extend(validation_result["warnings"])

    # Boost confidence based on quality signals
    template_used = matching_templates[0]["id"] if matching_templates else None
    if template_used:
        confidence += 0.05
    if rag_context:
        confidence += 0.05  # RAG context improves accuracy
    if form_json or concepts_json:
        confidence += 0.05  # Having real UUIDs/names improves accuracy

    confidence = max(0.1, min(1.0, confidence))

    # Generate explanation
    explanation = await _generate_explanation(code, inferred_type, rule_format)

    return {
        "code": code,
        "type": inferred_type,
        "format": rule_format,
        "confidence": round(confidence, 2),
        "explanation": explanation,
        "warnings": warnings,
        "errors": validation_result.get("errors", []),
        "common_errors": validation_result.get("common_errors", []),
        "template_used": template_used,
        "sample_test_data": validation_result.get("sample_test_data", {}),
    }


def _infer_rule_type(code: str) -> str:
    """Infer the rule type from the code content."""
    code_lower = code.lower()
    if "formelementstatusbuilder" in code_lower or "showformelement" in code_lower:
        return "ViewFilter"
    if "visitschedulebuilder" in code_lower:
        return "VisitSchedule"
    if "createvalidationerror" in code_lower:
        return "Validation"
    if "encounterdecisions" in code_lower or "enrolmentdecisions" in code_lower:
        return "Decision"
    if "workitems" in code_lower and "priority" in code_lower:
        return "WorklistUpdation"
    if "checklist" in code_lower and "duedate" in code_lower:
        return "Checklist"
    if "summaryitems" in code_lower or ("abnormal" in code_lower and "name" in code_lower and "value" in code_lower):
        return "EnrolmentSummary"
    if "eligible" in code_lower and "return" in code_lower:
        return "Eligibility"
    # Check for declarative rule
    if '"declarativerule"' in code_lower or '"actiontype"' in code_lower:
        return "ViewFilter"
    return "ViewFilter"


async def _generate_explanation(code: str, rule_type: str, rule_format: str) -> str:
    """Generate a brief explanation of what the rule does."""
    try:
        response = await claude_client.complete(
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"In 1-2 sentences, explain what this Avni {rule_type} rule does. "
                        f"Be concise and specific.\n\nRule ({rule_format}):\n{code[:3000]}"
                    ),
                }
            ],
            system_prompt="You are a concise technical writer. Explain Avni rules in plain English. Respond with ONLY the explanation, no prefixes.",
        )
        return response.strip()
    except Exception as e:
        logger.warning("Failed to generate explanation: %s", e)
        return f"A {rule_type} rule in {rule_format} format."

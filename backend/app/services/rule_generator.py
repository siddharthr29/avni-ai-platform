"""Avni rule generation engine.

Provides template-based and AI-powered generation of Avni rules across all
rule types: ViewFilter (skip logic), Decision, VisitSchedule, Validation,
Checklist, EnrolmentSummary, and Eligibility.

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

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Rule templates -- 20+ real Avni patterns
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
        The rule type (ViewFilter, Decision, etc.).
    concepts : list or None
        List of concept dicts with at least ``name`` key for cross-reference
        checking.

    Returns
    -------
    dict
        ``{"valid": bool, "syntax_ok": bool, "concept_refs_ok": bool,
           "warnings": [...], "errors": [...]}``
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
            "Checklist", "EnrolmentSummary", "Eligibility",
        }
        if rule_type not in valid_types:
            warnings.append(
                f"Unknown rule type '{rule_type}'. Expected one of: {', '.join(sorted(valid_types))}."
            )

        if rule_type == "ViewFilter" and "FormElementStatusBuilder" not in stripped:
            warnings.append(
                "ViewFilter rules typically use FormElementStatusBuilder."
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

    valid = syntax_ok and concept_refs_ok and len(errors) == 0

    return {
        "valid": valid,
        "syntax_ok": syntax_ok,
        "concept_refs_ok": concept_refs_ok,
        "warnings": warnings,
        "errors": errors,
    }


# ---------------------------------------------------------------------------
# AI-powered rule generation
# ---------------------------------------------------------------------------

RULE_GENERATION_SYSTEM_PROMPT = """You are an expert Avni rule writer. You generate rules for the Avni field data collection platform.

## Avni Rule Execution Context

Avni rules are JavaScript functions that receive `({params, imports})`:
- `params.entity` -- the current entity (ProgramEncounter, ProgramEnrolment, Individual, etc.)
- `params.formElement` -- the current form element (for ViewFilter rules)
- `imports.rulesConfig` -- rule utilities (FormElementStatusBuilder, VisitScheduleBuilder, createValidationError)
- `imports.moment` -- moment.js for date operations

## Entity Methods

Common methods available on entities:
- `entity.getObservationValue('Concept Name')` -- get observation value
- `entity.getObservationReadableValue('Concept Name')` -- get human-readable observation value
- `individual.getAgeInYears()` -- get age in years
- `individual.getAgeInMonths()` -- get age in months
- `individual.dateOfBirth` -- date of birth
- `individual.gender.name` -- gender name
- `enrolment.findLatestObservationInEntireEnrolment('Concept Name')` -- search all encounters
- `enrolment.enrolmentDateTime` -- enrollment date

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

StatusBuilder methods:
- `.when.valueInEncounter("name")` / `.when.valueInRegistration("name")` / `.when.valueInEnrolment("name")`
- `.containsAnswerConceptName("answer")` / `.containsAnswerConceptNameOtherThan("answer")`
- `.is.defined` / `.is.notDefined` / `.is.truthy`
- `.whenItem(booleanExpression).is.truthy`

### Decision
Returns an object with encounterDecisions, enrolmentDecisions, registrationDecisions arrays:
```javascript
'use strict';
({params, imports}) => {
    const decisions = {encounterDecisions: [], enrolmentDecisions: [], registrationDecisions: []};
    // ... logic
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
    // ... check conditions
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

Valid operators: containsAnswerConceptName, equals, lessThan, greaterThan, defined, notDefined, notContainsAnswerConceptName, containsAnswerConceptNameOtherThan, lessThanOrEqual, greaterThanOrEqual
Valid scopes: encounter, enrolment, registration
Valid actions: showFormElement, hideFormElement

## IMPORTANT RULES
1. Always start JavaScript rules with 'use strict';
2. Use the EXACT concept names and UUIDs from the provided form/concepts JSON.
3. For simple show/hide logic on coded fields, prefer declarative rules.
4. For complex logic (calculations, multiple conditions with JS logic, age-based), use JavaScript.
5. Always handle null/undefined values gracefully.
6. Return the correct data structure for the rule type.
7. Do NOT include any explanation or markdown -- return ONLY the rule code.
"""


async def generate_rule(
    description: str,
    rule_type: str | None = None,
    form_json: dict[str, Any] | None = None,
    concepts_json: list[dict[str, Any]] | None = None,
    complexity_hint: int | None = None,
) -> dict[str, Any]:
    """Generate an Avni rule from a natural language description.

    Uses Claude to generate the rule, providing matching templates as
    few-shot examples and the form/concept context for accurate UUIDs.

    Parameters
    ----------
    description : str
        Natural language description of the desired rule.
    rule_type : str or None
        Target rule type. If None, Claude infers it.
    form_json : dict or None
        The Avni form JSON definition for UUID accuracy.
    concepts_json : list or None
        The concepts list for concept name/UUID accuracy.
    complexity_hint : int or None
        1-5 hint about complexity. Lower values prefer declarative rules.

    Returns
    -------
    dict
        ``{"code": str, "type": str, "format": str, "confidence": float,
           "explanation": str, "warnings": list[str], "template_used": str|None}``
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

    # Call Claude
    response_text = await claude_client.complete(
        messages=[{"role": "user", "content": user_prompt}],
        system_prompt=RULE_GENERATION_SYSTEM_PROMPT,
    )

    # Clean up the response
    code = response_text.strip()

    # Remove markdown code fences if present
    if code.startswith("```"):
        lines = code.split("\n")
        # Remove first line (```javascript or ```)
        lines = lines[1:]
        # Remove last line if it's ```
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        code = "\n".join(lines).strip()

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

    # Run validation
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
    warnings.extend(validation_result["warnings"])

    # Boost confidence if a template was matched
    template_used = matching_templates[0]["id"] if matching_templates else None
    if template_used:
        confidence += 0.05

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
        "template_used": template_used,
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
    if "checklist" in code_lower:
        return "Checklist"
    if "summaryitems" in code_lower or "abnormal" in code_lower:
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

"""
Complex Rule Examples from Production Avni Bundles
====================================================
25 real rule examples extracted from production org bundles, categorized by type.
Each example includes the rule code, description, source org, and pattern it represents.

These examples serve as templates for the bundle generator to produce production-quality rules.
"""


# =============================================================================
# CATEGORY 1: DECISION RULES (Clinical decisions, risk assessment, referrals)
# =============================================================================

DECISION_RULES = [
    {
        "id": "DR-01",
        "title": "PNC Complications Decision with Multiple Builders",
        "org": "Ashwini uat",
        "form": "PNC.json",
        "pattern": "MULTI_OUTPUT_DECISION - Multiple complicationsBuilder instances producing separate decision outputs (complications, treatment, referrals)",
        "description": "Evaluates PNC complications (Post-Partum Haemorrhage, UTI, Genital Tract Infection, Mastitis, Post Operative Infection), determines treatment (Calcium, Iron based on Hb), and generates referral advice. Uses _.intersection to avoid double-counting complications.",
        "rule": '''"use strict";
({params, imports}) => {
    const programEncounter = params.entity;
    const decisions = params.decisions;
    const complicationsBuilder = new imports.rulesConfig.complicationsBuilder({
        programEncounter: programEncounter,
        complicationsConcept: "PNC Complications"
    });

    complicationsBuilder.addComplication("Post-Partum Haemorrhage")
        .when.valueInEncounter("Any vaginal problems").containsAnswerConceptName("Bad-smelling lochia")
        .or.when.valueInEncounter("Post-Partum Haemorrhage symptoms").containsAnyAnswerConceptName("Difficulty breathing", "Bad headache", "Blurred vision")
        .or.when.valueInEncounter("Systolic").is.lessThan(90)
        .or.when.valueInEncounter("Diastolic").is.lessThan(60);

    complicationsBuilder.addComplication("Urinary Tract Infection")
        .when.valueInEncounter("Any abdominal problems").containsAnswerConceptName("Abdominal pain")
        .or.when.valueInEncounter("Any difficulties with urinating").containsAnyAnswerConceptName("Difficulty passing urine", "Burning Urination");

    complicationsBuilder.addComplication("Genital Tract Infection")
        .when.valueInEncounter("Any abdominal problems").containsAnswerConceptName("Uterus is soft or tender")
        .or.when.valueInEncounter("Any vaginal problems").containsAnswerConceptName("Heavy bleeding per vaginum");

    complicationsBuilder.addComplication("Mastitis")
        .when.valueInEncounter("Any breast problems").containsAnyAnswerConceptName("Breast hardness", "Nipple hardness", "Cracked Nipple");

    complicationsBuilder.addComplication("Post Operative Infection")
        .when.valueInEncounter("How is the Cesarean incision area").containsAnyAnswerConceptName("Looks red", "Indurated", "Filled with pus");

    // Infection check: only flag if temperature is high AND no other complication explains it
    const existingComplications = complicationsBuilder.getComplications().value;
    const existingComplicationsThatCanResultInHighTemperature = ["Post-Partum Haemorrhage", "Urinary Tract Infection", "Genital Tract Infection", "Mastitis", "Post Operative Infection"];
    complicationsBuilder.addComplication("Infection")
        .when.valueInEncounter("Temperature").is.greaterThanOrEqualTo(99)
        .and.whenItem(existingComplications).matchesFn((existingComplications) => {
        return _.intersection(existingComplicationsThatCanResultInHighTemperature, existingComplications).length === 0;
    });

    complicationsBuilder.addComplication("Post-Partum Depression")
        .when.valueInEncounter("Post-Partum Depression Symptoms").containsAnyAnswerConceptName("Insomnia", "Loss of appetite", "Weakness", "Irritability");

    complicationsBuilder.addComplication("Post-Partum Eclampsia")
        .when.valueInEncounter("Convulsions").containsAnswerConceptName("Present")
        .and.valueInEncounter("Systolic").is.greaterThanOrEqualTo(140)
        .or.valueInEncounter("Diastolic").is.greaterThanOrEqualTo(90);

    decisions.encounterDecisions.push(complicationsBuilder.getComplications());

    // Treatment builder - separate output concept
    const treatmentBuilder = new imports.rulesConfig.complicationsBuilder({
        programEncounter: programEncounter,
        complicationsConcept: "Treatment"
    });
    treatmentBuilder.addComplication("Calcium 1g/day");
    treatmentBuilder.addComplication("Ferrous Sulphate (100mg) 1 OD")
        .when.valueInEncounter("Hb % Level").greaterThanOrEqualTo(11);
    treatmentBuilder.addComplication("Ferrous Sulphate (200mg) 1 OD")
        .when.valueInEncounter("Hb % Level").lessThan(11);
    decisions.encounterDecisions.push(treatmentBuilder.getComplications());

    // Referral advice - yet another output concept
    const referralAdvice = new imports.rulesConfig.complicationsBuilder({
        programEncounter: programEncounter,
        complicationsConcept: "Refer to the hospital immediately for"
    });
    referralAdvice.addComplication("Hypertension")
        .when.valueInEncounter("Systolic").greaterThanOrEqualTo(140)
        .or.when.valueInEncounter("Diastolic").greaterThanOrEqualTo(90);
    decisions.encounterDecisions.push(referralAdvice.getComplications());

    return decisions;
};''',
    },

    {
        "id": "DR-02",
        "title": "Child PNC Recommendations and Referral Advice",
        "org": "Ashwini uat",
        "form": "Child PNC.json",
        "pattern": "VITAL_SIGNS_THRESHOLD - Multiple vital sign checks generating recommendations and referral advice with both numeric and coded answer conditions",
        "description": "Checks child pulse, respiratory rate, temperature, birth weight, reflexes, muscle tone, jaundice, urination/meconium timing to generate care recommendations and hospital referral advice.",
        "rule": '''"use strict";
({params, imports}) => {
    const programEncounter = params.entity;
    const decisions = params.decisions;

    const recommendationBuilder = new imports.rulesConfig.complicationsBuilder({
        programEncounter: programEncounter,
        complicationsConcept: "Recommendations"
    });

    recommendationBuilder.addComplication("Keep the baby warm")
        .when.valueInEncounter("Child Pulse").lessThan(60)
        .or.when.valueInEncounter("Child Pulse").greaterThan(100)
        .or.when.valueInEncounter("Child Respiratory Rate").lessThan(30)
        .or.when.valueInEncounter("Child Respiratory Rate").greaterThan(60);

    recommendationBuilder.addComplication("Keep the baby warm by giving mother's skin to skin contact and covering the baby's head, hands and feet with a cap, gloves and socks resp.")
        .when.valueInEncounter("Child Temperature").lessThan(97.5);

    recommendationBuilder.addComplication("Give exclusive breast feeding")
        .when.encounterType.equals("Child PNC")
        .and.valueInEncounter("Is baby exclusively breastfeeding").containsAnswerConceptName("No");

    decisions.encounterDecisions.push(recommendationBuilder.getComplications());

    const referralAdvice = new imports.rulesConfig.complicationsBuilder({
        programEncounter: programEncounter,
        complicationsConcept: "Refer to the hospital immediately for"
    });

    referralAdvice.addComplication("Child born Underweight")
        .when.valueInEncounter("Birth Weight").lessThan(2);
    referralAdvice.addComplication("Colour of child is Pale or Blue")
        .when.valueInEncounter("Colour of child").containsAnswerConceptName("Blue/pale");
    referralAdvice.addComplication("Reflex Absent")
        .when.valueInEncounter("Reflex").containsAnswerConceptName("Absent");
    referralAdvice.addComplication("Low Pulse")
        .when.valueInEncounter("Child Pulse").lessThan(60);
    referralAdvice.addComplication("High Temperature")
        .when.valueInEncounter("Child Temperature").greaterThan(99.5);
    referralAdvice.addComplication("Urine not passed for more than 48 hours after birth")
        .when.encounterType.equals("Child PNC")
        .when.valueInEncounter("Duration in hours between birth and first urination").greaterThan(48);

    decisions.encounterDecisions.push(referralAdvice.getComplications());
    return decisions;
};''',
    },

    {
        "id": "DR-03",
        "title": "Cross-Subject Decision Rule (Child looks up Mother's data)",
        "org": "MLD Trust",
        "form": "Birth Form.json",
        "pattern": "CROSS_SUBJECT_LOOKUP - Uses individualService.getSubjectByUUID to access mother's pregnancy enrolment data from child's birth encounter",
        "description": "From a child's birth form, looks up the mother's UUID, finds the matching pregnancy enrolment by comparing delivery date with child DOB, then accesses ANC encounter data for high-risk condition assessment.",
        "rule": '''"use strict";
({params, imports}) => {
    const programEncounter = params.entity;
    const decisions = params.decisions;
    const moment = imports.moment;
    const _ = imports.lodash;
    const individualService = params.services.individualService;
    let mother = null;
    let ancEncounters = [];
    let latestAnc = null;

    const individual = programEncounter.programEnrolment.individual;
    const motherUUID = individual.getObservationValue("670f4d67-851d-4c6e-acd4-7c537715c908");
    if(motherUUID){
        mother = individualService.getSubjectByUUID(motherUUID)
    }
    if(mother){
        let pregnancyEnrolments = mother.enrolments;
        let requiredEnrolment = null;
        for (const enrolment of pregnancyEnrolments) {
            let deliveryEncounter = enrolment.getEncountersOfType("Delivery");
            if(deliveryEncounter.length == 0) continue;
            else deliveryEncounter = deliveryEncounter[0];

            const deliveryDate = moment(deliveryEncounter.getObservationValue("76d5d509-ca1b-45b7-863f-536d5f65d06f")).startOf('day');
            const childDOB = moment(individual.dateOfBirth).startOf('day');
            const differenceInDays = deliveryDate.diff(childDOB, 'days');
            if(differenceInDays <= 2 && differenceInDays >= -2){
                requiredEnrolment = enrolment;
                break;
            }
        }
        if(requiredEnrolment){
            ancEncounters = requiredEnrolment.getEncountersOfType("ANC");
            if(ancEncounters.length > 0) latestAnc = ancEncounters[0];
        }
    }

    // High-risk condition list using RuleCondition
    const highRiskConditionList = [
        {
            value: "Head Size: Small or Big",
            conditionRule: new imports.rulesConfig.RuleCondition({programEncounter})
                .when.valueInEncounter("2fddc3fb-41b2-4030-abc2-01e29dac1b92")
                .containsAnyAnswerConceptName("87beb69f-2dc7-4400-95ac-cfeb052bd18a","63aadedb-be59-4712-a0b2-0db28b47da22").matches()
        },
        {
            value: "Birth Weight less than 1.5 kg",
            conditionRule: new imports.rulesConfig.RuleCondition({programEncounter})
                .when.valueInEncounter("148fb61a-9d85-4876-b20f-50235c0d1d6e").lessThan(1.5).matches()
        },
        {
            value: "Gestation age less than 32 weeks",
            conditionRule: new imports.rulesConfig.RuleCondition({programEncounter})
                .when.valueInEncounter("2bb79ac5-463b-4940-aa70-5c1b5cfd2045")
                .containsAnswerConceptName("066a76ab-bfdb-4d7f-a75c-e920f73390e9").matches()
        },
    ];

    function getMatchingConditions(conditionList) {
        return conditionList
            .filter(condition => condition.conditionRule)
            .map(condition => condition.value);
    }

    // Push high-risk conditions as decision output
    const matchingHighRiskConditions = getMatchingConditions(highRiskConditionList);
    if (matchingHighRiskConditions.length > 0) {
        decisions.encounterDecisions.push({
            name: "High Risk Conditions",
            value: matchingHighRiskConditions
        });
    }
    return decisions;
};''',
    },

    {
        "id": "DR-04",
        "title": "ANC High-Risk Assessment with Hb-based Anemia Classification",
        "org": "APF Odisha",
        "form": "ANC.json",
        "pattern": "MULTI_THRESHOLD_CLASSIFICATION - Classifies anemia severity from Hb values and checks multiple pre-morbidity conditions using reusable helper function",
        "description": "Classifies anemia (Severe <7, Moderate 7-10, Mild 10-11), checks 13 pre-morbidity conditions via a reusable UUID checker function, and assesses weight gain adequacy by comparing with previous ANC encounters.",
        "rule": '''"use strict";
({params, imports}) => {
    const programEncounter = params.entity;
    const decisions = params.decisions;
    const moment = imports.moment;

    function pregnancyInducedMorbidityConditionChecker(answerConceptUUID) {
        return new imports.rulesConfig.RuleCondition({programEncounter})
            .when.valueInEncounter("12d99265-c769-4236-aff5-fcba73976396")
            .containsAnswerConceptName(answerConceptUUID)
            .matches();
    }

    function getHighRiskConditions(){
        const ancHighRiskValues = ["Severe anemia", "Moderate anemia", "Mild anemia",
            "Inadequate Weight Gain during Pregnancy", "Hypertension",
            "Diabetes/ Gestational Diabetes", "Tuberculosis", "Asthma",
            "Pre-eclampsia", "Sickle cell anemia", "Thalassemia",
            "Heart conditions", "Hypothyroidism", "Syphillis",
            "Other pre-morbidity conditions"];

        const hbValue = programEncounter.getObservationReadableValue("68bc6e51-eb49-4816-b78b-2427bbab8d92");
        const isSevereAnemia = hbValue && hbValue < 7;
        const isModerateAnemia = hbValue && hbValue >= 7 && hbValue < 10;
        const isMildAnemia = hbValue && hbValue >= 10 && hbValue < 11;
        const isHypertension = pregnancyInducedMorbidityConditionChecker("621462ed-23da-4b73-b590-4af8ccf34b45");
        const isDiabetes = pregnancyInducedMorbidityConditionChecker("9f6c206e-f04a-4a2a-b3ae-78edbffb0f62");
        // ... (13 more condition checks)

        let isInadequateWeightGain = false;
        const ancPreviousEncounters = programEncounter.programEnrolment
            .getEncountersOfType("ANC")
            .filter(enc => enc.encounterDateTime && moment(enc.encounterDateTime).isBefore(moment(programEncounter.encounterDateTime)));
        if (ancPreviousEncounters.length > 0) {
            const previousWeight = ancPreviousEncounters[0].getObservationReadableValue("weight-uuid");
            const currentWeight = programEncounter.getObservationReadableValue("weight-uuid");
            if (previousWeight && currentWeight && (currentWeight - previousWeight) < 2) {
                isInadequateWeightGain = true;
            }
        }

        const conditions = [isSevereAnemia, isModerateAnemia, isMildAnemia, isInadequateWeightGain, isHypertension, isDiabetes];
        return ancHighRiskValues.filter((_, i) => conditions[i]);
    }

    const highRiskConditions = getHighRiskConditions();
    if (highRiskConditions.length > 0) {
        decisions.encounterDecisions.push({
            name: "High Risk Conditions",
            value: highRiskConditions
        });
    }
    return decisions;
};''',
    },

    {
        "id": "DR-05",
        "title": "ANC Decision with Investigation Tracking by Trimester",
        "org": "Ashwini uat",
        "form": "ANC.json",
        "pattern": "TRIMESTER_BASED_INVESTIGATION - Tracks which investigations are due per trimester and generates recommendations based on pregnancy week calculation",
        "description": "Calculates pregnancy week from LMP, determines trimester, checks if required investigations (Paracheck, Hb, VDRL, HIV, etc.) have been done for each trimester, and generates high-risk conditions based on vitals and medical history.",
        "rule": '''"use strict";
({params, imports}) => {
    const programEncounter = params.entity;
    const decisions = params.decisions;
    const moment = imports.moment;

    const lmpDate = programEncounter.programEnrolment.getObservationValue('Last menstrual period');
    const pregnancyPeriodInWeeks = imports.moment(programEncounter.encounterDateTime).diff(lmpDate, 'weeks');

    const systolic = programEncounter.getObservationValue('Systolic');
    const diastolic = programEncounter.getObservationValue('Diastolic');
    const isBloodPressureHigh = (systolic >= 140) || (diastolic >= 90);

    let highRiskConditions = programEncounter.programEnrolment
        .getObservationReadableValueInEntireEnrolment('High Risk Conditions');
    const isEssentialHypertensive = highRiskConditions &&
        highRiskConditions.indexOf('Essential Hypertension') >= 0;

    const medicalHistory = ["Hypertension", "Heart-related Diseases", "Diabetes",
        "Sickle Cell", "Epilepsy", "Renal Disease", "HIV/AIDS", "Hepatitis B Positive"];

    const investigations = [
        ["Paracheck", [1, 2, 3]], ["Hb", [1, 2, 3]],
        ["VDRL", [1]], ["HIV/AIDS Test", [1]], ["HbsAg", [1]],
        ["Sickling Test", [1]], ["Hb Electrophoresis", [1]],
        ["Urine Albumin", [1, 2, 3]], ["Urine Sugar", [1, 2, 3]]
    ];

    // Determine current trimester
    const currentTrimester = pregnancyPeriodInWeeks <= 12 ? 1 :
                            pregnancyPeriodInWeeks <= 28 ? 2 : 3;

    // Check which investigations are due
    const dueInvestigations = investigations
        .filter(([name, trimesters]) => trimesters.includes(currentTrimester))
        .map(([name]) => name);

    // ... push to decisions
    return decisions;
};''',
    },
]


# =============================================================================
# CATEGORY 2: VISIT SCHEDULE RULES (Scheduling follow-up visits)
# =============================================================================

VISIT_SCHEDULE_RULES = [
    {
        "id": "VS-01",
        "title": "PNC Visit Chain Scheduling (Day 3 -> 7 -> 14 -> 21 -> 28 -> 42)",
        "org": "APF Odisha",
        "form": "PNC Encounter.json",
        "pattern": "INTERVAL_CHAIN - Progressive interval-based visit chain where each visit schedules the next at a predefined interval from a base date (delivery date)",
        "description": "After delivery, PNC visits are scheduled at days 3, 7, 14, 21, 28, and 42 from delivery date. Each completed PNC encounter schedules the next one in the chain.",
        "rule": '''"use strict";
({ params, imports }) => {
    const programEncounter = params.entity;
    const moment = imports.moment;
    const _ = imports.lodash;
    const scheduleBuilder = new imports.rulesConfig.VisitScheduleBuilder({programEncounter});

    const nextSchedules = {
        3: {'nextInterval': 7, 'encounterNo': 2},
        7: {'nextInterval': 14, 'encounterNo': 3},
        14: {'nextInterval': 21, 'encounterNo': 4},
        21: {'nextInterval': 28, 'encounterNo': 5},
        28: {'nextInterval': 42, 'encounterNo': 6},
    };

    const deliveryEncounter = programEncounter.programEnrolment.lastFulfilledEncounter("Delivery");
    if (!deliveryEncounter) return scheduleBuilder.getAllUnique("encounterType");

    const deliveryDate = deliveryEncounter.getObservationValue('f72ec1db-50d5-409e-883a-421825fbebb5');
    const currentInterval = moment(programEncounter.earliestVisitDateTime).diff(moment(deliveryDate), 'days');

    // Find closest matching interval
    const closestKey = Object.keys(nextSchedules)
        .map(Number)
        .reduce((prev, curr) => Math.abs(curr - currentInterval) < Math.abs(prev - currentInterval) ? curr : prev);

    const nextSchedule = nextSchedules[closestKey];
    if (nextSchedule) {
        const earliestDate = moment(deliveryDate).add(nextSchedule.nextInterval, 'days').toDate();
        scheduleBuilder.add({
            name: `PNC ${nextSchedule.encounterNo}`,
            encounterType: 'PNC',
            earliestDate: moment(earliestDate).startOf('day').toDate(),
            maxDate: moment(earliestDate).add(3, 'days').endOf('day').toDate(),
        });
    }

    return scheduleBuilder.getAllUnique("encounterType");
};''',
    },

    {
        "id": "VS-02",
        "title": "Conditional Child Home Visit Based on Nutritional Status",
        "org": "APF Odisha",
        "form": "Child Home Visit.json",
        "pattern": "CONDITIONAL_FOLLOWUP - Schedules follow-up visits based on encounter outcomes (nutritional status, QRT results, NRC discharge)",
        "description": "Schedules child home visits based on QRT encounter dates, growth monitoring results (SAM/MAM/GF1/GF2), NRC discharge, and medical facility referral status. Uses interval calculation from last QRT date.",
        "rule": '''"use strict";
({params, imports}) => {
    const programEncounter = params.entity;
    const programEnrolment = programEncounter.programEnrolment;
    const moment = imports.moment;
    const scheduleBuilder = new imports.rulesConfig.VisitScheduleBuilder({programEncounter});

    function isVisitAlreadyScheduled(earliestDate, encounterType, encounterName) {
        const earliestVisitDateTime = moment(earliestDate);
        return programEnrolment.encounters.some(enc =>
            enc.encounterType.name === encounterType &&
            enc.name === encounterName &&
            moment(enc.earliestVisitDateTime).isSame(earliestVisitDateTime, 'day')
        );
    }

    function getChildHomeVisitDate(qrtEncounterDate) {
        const intervalInDays = moment(programEncounter.earliestVisitDateTime).diff(moment(qrtEncounterDate), 'days');
        let daysToAdd = 0;
        if (intervalInDays <= 15) daysToAdd = 30;
        else if (intervalInDays <= 30) daysToAdd = 45;
        else if (intervalInDays <= 45) daysToAdd = 60;
        return daysToAdd !== 0 ? moment(qrtEncounterDate).add(daysToAdd, 'days').toDate() : null;
    }

    function lastfilledEncounter(encounterType) {
        const lastVisitEncounters = programEncounter.programEnrolment.getEncountersOfType(encounterType, false);
        return _.chain(lastVisitEncounters)
            .filter((encounter) => encounter.encounterDateTime && encounter.voided == false)
            .maxBy((encounter) => encounter.encounterDateTime)
            .value();
    }

    const qrtEncounter = lastfilledEncounter('QRT Child');
    if (qrtEncounter && programEncounter.name != 'Child Home Visit - Post NRC') {
        const qrtEncounterDate = moment(qrtEncounter.encounterDateTime).toDate();
        const visitDate = getChildHomeVisitDate(qrtEncounterDate);
        const takenToMedicalFacility = qrtEncounter.getObservationReadableValue("QRT facilitated child to medical facility?") == "Yes";
        const latestGMEncounter = lastfilledEncounter('Growth Monitoring');
        const isSAMInLatestGMEncounter = latestGMEncounter.getObservationReadableValue("Nutritional Status") == "SAM";

        if ((takenToMedicalFacility || isSAMInLatestGMEncounter) && !_.isNil(visitDate)) {
            scheduleBuilder.add({
                name: 'Child Home Visit',
                encounterType: 'Child Home Visit',
                earliestDate: moment(visitDate).startOf('day').toDate(),
                maxDate: moment(visitDate).add(7, 'days').endOf('day').toDate(),
                visitCreationStrategy: "createNew"
            });
        }
    }

    return scheduleBuilder.getAllUnique("encounterType");
};''',
    },

    {
        "id": "VS-03",
        "title": "Multi-Encounter-Type Cancellation Rescheduler",
        "org": "JSS",
        "form": "Default Program Encounter Cancellation Form.json",
        "pattern": "CANCELLATION_RESCHEDULE - Routes cancellation rescheduling logic based on encounter type name, with different scheduling strategies per type",
        "description": "Handles cancellation rescheduling for Anthropometry Assessment (monthly on specific day from group subject), Albendazole (bi-annual Feb/Aug), and generic encounters. Uses group subject's 'Day of month' property.",
        "rule": '''"use strict";
({params, imports}) => {
    const programEncounter = params.entity;
    let visitCancelReason = programEncounter.findCancelEncounterObservationReadableValue('Visit cancel reason');
    if (visitCancelReason === 'Program exit') return [];

    const encounterTypeName = programEncounter.encounterType.name;
    const moment = imports.moment;
    const _ = imports.lodash;

    if (encounterTypeName === 'Anthropometry Assessment') {
        const myGroups = programEncounter.programEnrolment.individual.groups;
        if (!programEncounter.programEnrolment.isActive || _.isEmpty(myGroups)) return [];

        const groupSubject = _.get(_.find(myGroups, g => !g.voided && g.groupSubject.subjectType.name === 'Phulwari'), 'groupSubject');
        const scheduleBuilder = new imports.rulesConfig.VisitScheduleBuilder({
            programEnrolment: programEncounter.programEnrolment
        });

        if(!_.isNil(groupSubject)){
            const dayOfMonth = groupSubject.getObservationReadableValue("Day of month for growth monitoring visit");
            const scheduledDateTime = programEncounter.earliestVisitDateTime;
            var monthForNextVisit = moment(scheduledDateTime).month() != 11 ? moment(scheduledDateTime).month() + 1 : 0;
            let earliestDate = moment(scheduledDateTime).add(1, 'M').date(dayOfMonth).toDate();
            const maxDate = moment(earliestDate).add(3, 'days').toDate();

            scheduleBuilder.add({
                name: "Growth Monitoring Visit",
                encounterType: "Anthropometry Assessment",
                earliestDate: earliestDate,
                maxDate: maxDate
            });
        }
        return scheduleBuilder.getAllUnique("encounterType");

    } else if (encounterTypeName === 'Albendazole') {
        const FEB = 1;
        const AUG = 7;
        const findSlot = (anyDate) => {
            anyDate = moment(anyDate).startOf('day').toDate();
            if (moment(anyDate).month() < FEB) return moment(anyDate).startOf('month').month(FEB).toDate();
            if (moment(anyDate).month() === FEB) return anyDate;
            if (moment(anyDate).month() < AUG) return moment(anyDate).startOf('month').month(AUG).toDate();
            if (moment(anyDate).month() === AUG) return anyDate;
            return moment(anyDate).add(1, 'year').month(FEB).startOf('month').toDate();
        };
        // ... schedule next Albendazole slot
    }
    return [];
};''',
    },

    {
        "id": "VS-04",
        "title": "Daily Attendance with Sunday Skip and Absence Tracking",
        "org": "JSS",
        "form": "Daily Attendance Form.json",
        "pattern": "DAILY_RECURRING_WITH_SKIP - Daily visit scheduling that skips Sundays and tracks 3-consecutive-day absences across group members",
        "description": "Schedules next daily attendance (skipping Sundays), then cross-checks attendance across 3 consecutive days to identify persistently absent children. Uses group subject members for child list.",
        "rule": '''"use strict";
({ params, imports }) => {
    const encounter = params.entity;
    const scheduleBuilder = new imports.rulesConfig.VisitScheduleBuilder({encounter});
    const visitDate = encounter.earliestVisitDateTime || encounter.encounterDateTime;
    let earliestVisitDate = imports.moment(visitDate).add(1, 'days').toDate();
    let weekDayName = imports.moment(earliestVisitDate).format('ddd');

    if(_.isEqual(weekDayName,'Sun')){
        earliestVisitDate = imports.moment(visitDate).add(2, 'days').toDate();
        weekDayName = imports.moment(earliestVisitDate).format('ddd');
    }

    scheduleBuilder.add({
        name: "Daily Attendance -" + weekDayName,
        encounterType: "Daily Attendance Form",
        earliestDate: earliestVisitDate,
        maxDate: earliestVisitDate
    });

    // Track 3-day consecutive absence
    const groupSubject = params.entity.individual.groupSubjects;
    const children = [];
    groupSubject.forEach((gs) => {
        if (!gs.memberSubject.voided) children.push(gs.memberSubject.uuid);
    });

    let currentVisitAttendance = encounter.getObservationReadableValue('Children present in phulwari');
    const encounters = encounter.individual.getEncounters(true);

    let enc1 = _.chain(encounters)
        .filter((enc) => enc.encounterDateTime && enc.encounterDateTime < encounter.encounterDateTime)
        .nth(0).value();
    let enc2 = _.chain(encounters)
        .filter((enc) => enc.encounterDateTime && enc.encounterDateTime < encounter.encounterDateTime)
        .nth(1).value();

    if (enc1 && enc2) {
        let enc1Absent = _.difference(children, enc1.getObservationReadableValue('Children present in phulwari'));
        let enc2Absent = _.difference(children, enc2.getObservationReadableValue('Children present in phulwari'));
        let currentAbsent = _.difference(children, currentVisitAttendance);

        let threeVisitAbsent = _.chain(currentAbsent)
            .filter(e => _.includes(enc1Absent, e))
            .filter(e => _.includes(enc2Absent, e))
            .value();
        // Alert for persistently absent children
    }

    return scheduleBuilder.getAllUnique("encounterType");
};''',
    },

    {
        "id": "VS-05",
        "title": "Registration-Triggered Multi-Encounter Scheduling",
        "org": "CInI",
        "form": "School Registration.json",
        "pattern": "REGISTRATION_MULTI_SCHEDULE - Upon registration, schedules multiple different encounter types with different frequencies and date calculation strategies",
        "description": "Upon school registration, schedules Library Monthly Report (monthly), SMC School Monitoring (monthly), and Monthly School Monitoring encounters. Uses IST timezone offset and academic year (April-March) calculations.",
        "rule": '''"use strict";
({params, imports}) => {
    const individual = params.entity;
    const moment = imports.moment;
    const scheduleBuilder = new imports.rulesConfig.VisitScheduleBuilder({individual});

    const isLibraryMonthlyReportPresent = individual.getEncounters().filter(encounter =>
        encounter.name === 'Library Monthly Report' && encounter.encounterDateTime && !encounter.cancelDateTime && !encounter.voided
    ).length > 0;

    if (!isLibraryMonthlyReportPresent) {
        const firstDayOfNextMonth = moment(individual.registrationDate).utcOffset("+05:30")
            .add(1, 'months').startOf('month').add(1, "D").utc().toDate();
        scheduleBuilder.add({
            name: "Library Monthly Report",
            encounterType: "Library Monthly Report",
            earliestDate: firstDayOfNextMonth,
            maxDate: moment(firstDayOfNextMonth).add(25, 'days').toDate()
        });
    }

    // Academic year calculation (April to March)
    const getApril = (date) => {
        const month = moment(date).utcOffset("+05:30").month();
        const year = moment(date).utcOffset("+05:30").year();
        if(month < 3) return moment({year: year-1, month: 3, day: 1}).utcOffset("+05:30").add(1, "D").utc();
        return moment({year: year, month: 3, day: 1}).utcOffset("+05:30").add(1, "D").utc();
    };

    return scheduleBuilder.getAll();
};''',
    },

    {
        "id": "VS-06",
        "title": "Cancellation Rescheduling with Numbered Follow-up Names",
        "org": "Animedh Charitable Trust DNH",
        "form": "Child Home Visit Anthropometry Encounter Cancellation.json",
        "pattern": "NUMBERED_FOLLOWUP_RESCHEDULE - Increments visit number on cancellation (Visit 1 -> Visit 2 -> Visit 3...) with different intervals based on nutritional z-scores",
        "description": "On cancellation, determines the next numbered follow-up name (e.g. 'Child Home Visit Anthropometry 3'), then calculates scheduling interval based on the latest weight-for-height and weight-for-age z-scores.",
        "rule": '''"use strict";
({ params, imports }) => {
    const programEncounter = params.entity;
    const moment = imports.moment;
    const scheduleBuilder = new imports.rulesConfig.VisitScheduleBuilder({ programEncounter });
    const cancelDateTime = programEncounter.cancelDateTime;

    function getNextFollowUpName(currentFollowupName) {
        if (!currentFollowupName || currentFollowupName.trim() === "") {
            return "Child Home Visit Anthropometry 1";
        }
        const parts = currentFollowupName.trim().replace(/\\s+/g, ' ').split(' ');
        const lastPart = parts[parts.length - 1];
        const currentNumber = parseInt(lastPart, 10);
        if (isNaN(currentNumber)) return "Child Home Visit Anthropometry 1";
        return `Child Home Visit Anthropometry ${currentNumber + 1}`;
    }

    const nextFollowupName = getNextFollowUpName(programEncounter.name);

    // Determine interval based on nutritional z-scores from latest completed encounter
    let childHomeVisitEncounters = programEncounter.programEnrolment.getEncountersOfType('Child Home Visit Anthropometry') || [];
    const allCompleted = childHomeVisitEncounters.filter(enc => enc.encounterDateTime);

    let earliestDate = moment(cancelDateTime).add(30, "days").startOf("day").toDate();
    let maxDate = moment(cancelDateTime).add(37, "days").endOf("day").toDate();

    if (allCompleted.length > 0) {
        const latest = allCompleted[0];
        const wfhZScore = latest.getObservationValue("Weight for height z-score");
        // Adjust interval based on z-score severity
        if (wfhZScore && wfhZScore < -3) {
            earliestDate = moment(cancelDateTime).add(15, "days").startOf("day").toDate();
            maxDate = moment(cancelDateTime).add(22, "days").endOf("day").toDate();
        }
    }

    scheduleBuilder.add({
        name: nextFollowupName,
        encounterType: 'Child Home Visit Anthropometry',
        earliestDate: earliestDate,
        maxDate: maxDate
    });

    return scheduleBuilder.getAllUnique("encounterType");
};''',
    },

    {
        "id": "VS-07",
        "title": "Delivery-Triggered PNC First Visit Scheduling",
        "org": "APF Odisha",
        "form": "Delivery Encounter.json",
        "pattern": "ENCOUNTER_TRIGGERS_NEW_TYPE - Completing one encounter type triggers scheduling of a different encounter type",
        "description": "When delivery encounter is completed, checks if any PNC encounters exist. If not, schedules the first PNC visit at 3 days after delivery date.",
        "rule": '''"use strict";
({ params, imports }) => {
    const programEncounter = params.entity;
    const scheduleBuilder = new imports.rulesConfig.VisitScheduleBuilder({programEncounter});

    const noPNCEncounters = programEncounter.programEnrolment.encounters
        .filter((enc) => enc.encounterType.name == 'PNC').length == 0;

    if(noPNCEncounters){
        const dateOfDelivery = programEncounter.getObservationValue('f72ec1db-50d5-409e-883a-421825fbebb5');
        const earliestDate = imports.moment(dateOfDelivery).add(3, 'days').startOf('day').toDate();
        const maxDate = imports.moment(earliestDate).add(3, 'days').endOf('day').toDate();

        scheduleBuilder.add({
            name: 'PNC 1',
            encounterType: 'PNC',
            earliestDate: earliestDate,
            maxDate: maxDate,
        });
    }

    return scheduleBuilder.getAllUnique("encounterType");
};''',
    },

    {
        "id": "VS-08",
        "title": "Training Visit with Dynamic Month-Based Naming",
        "org": "APF Odisha",
        "form": "Training.json",
        "pattern": "DYNAMIC_VISIT_NAMING - Generates visit names with month/year context and checks for duplicates before scheduling",
        "description": "Schedules monthly training completion visits with names like 'Training Completion - for January 2024'. Checks if a visit with that name already exists before creating.",
        "rule": '''"use strict";
({ params, imports }) => {
    const encounter = params.entity;
    const moment = imports.moment;
    const scheduleBuilder = new imports.rulesConfig.VisitScheduleBuilder({encounter});
    const visitMonthYear = moment(encounter.encounterDateTime).format('MMMM YYYY');
    const visitName = `Training Completion - for ${visitMonthYear}`;

    function visitAlreadyScheduled(visitType, visitName){
        return encounter.individual.getEncounters().some((enc) =>
            enc.encounterType.name == visitType &&
            enc.name == visitName &&
            !enc.voided
        );
    }

    if (!visitAlreadyScheduled("Training Completion", visitName)) {
        const earliestDate = moment(encounter.encounterDateTime).endOf('month').toDate();
        scheduleBuilder.add({
            name: visitName,
            encounterType: "Training Completion",
            earliestDate: earliestDate,
            maxDate: moment(earliestDate).add(7, 'days').toDate()
        });
    }

    return scheduleBuilder.getAll();
};''',
    },
]


# =============================================================================
# CATEGORY 3: VALIDATION RULES
# =============================================================================

VALIDATION_RULES = [
    {
        "id": "VR-01",
        "title": "Student Count Reconciliation Across Grouped Observations",
        "org": "Gubbachi",
        "form": "Daily Activity Update & Reflections Encounter.json",
        "pattern": "GROUP_OBSERVATION_RECONCILIATION - Validates that all group members are accounted for across multiple grouped observation fields",
        "description": "Ensures all students in the class are accounted for - either in 'completed activities' or in the 'remedial activities' QuestionGroup. Uses findGroupedObservation to count students in repeated groups.",
        "rule": """'use strict';
({params, imports}) => {
    const programEncounter = params.entity;
    const _ = imports.lodash;
    const validationResults = [];

    if(programEncounter.programEnrolment.individual && programEncounter.programEnrolment.individual.groupSubjects) {
        let membersubjects = programEncounter.programEnrolment.individual.groupSubjects.filter(gs => !gs.voided);
        const totalStudents = membersubjects.length;

        let studentsCompletedActivities = programEncounter.getObservationValue('e0d1c2b3-a4f5-6789-3456-789012345007') || [];
        const completedCount = Array.isArray(studentsCompletedActivities) ? studentsCompletedActivities.length : 0;

        let groupedObservation = programEncounter.findGroupedObservation('c0d1e2f3-a4b5-6789-3456-789012345003');
        let remedialStudentsCount = 0;

        if(groupedObservation && groupedObservation.length > 0) {
            groupedObservation.forEach((group) => {
                let studentObs = group.groupObservations.find(obs => obs.concept.uuid === '8fb8200c-3ec8-408c-a67d-fda6e2a41f1a');
                let reasonObs = group.groupObservations.find(obs => obs.concept.uuid === 'f1e2d3c4-b5a6-7890-4567-890123456005');
                if(studentObs && studentObs.valueJSON && studentObs.valueJSON.answer &&
                   reasonObs && reasonObs.valueJSON && reasonObs.valueJSON.answer) {
                    const studentsInGroup = studentObs.valueJSON.answer;
                    remedialStudentsCount += Array.isArray(studentsInGroup) ? studentsInGroup.length : 1;
                }
            });
        }

        const accountedStudents = completedCount + remedialStudentsCount;
        if(accountedStudents < totalStudents) {
            const missingCount = totalStudents - accountedStudents;
            validationResults.push(imports.common.createValidationError(
                `Please account for all students. ${missingCount} student(s) not accounted for.`
            ));
        }
    }
    return validationResults;
};""",
    },

    {
        "id": "VR-02",
        "title": "Duplicate Village Prevention with Location Matching",
        "org": "Goonj",
        "form": "Village Registration.json",
        "pattern": "DUPLICATE_SUBJECT_PREVENTION - Uses individualService to check for existing subjects in the same location to prevent duplicates",
        "description": "Before registering a village, checks if another village already exists in the same address level. For 'Other' locations, compares Other Block and Other Village text fields with case-insensitive matching.",
        "rule": """'use strict';
({params, imports}) => {
    const individual = params.entity;
    const moment = imports.moment;
    const _ = imports.lodash;
    const validationResults = [];
    const individualService = params.services.individualService;

    function toStartCase(str) {
        return str.trim().toLowerCase().split(/[\\s]+/)
            .map(word => word.charAt(0).toUpperCase() + word.slice(1)).join(' ');
    }

    const isLocationMatch = (e1, e2, location) => {
        const {uuid, name} = location;
        const loc1 = e1.getObservationReadableValue(uuid) || "";
        const loc2 = e2.getObservationReadableValue(uuid) || "";
        return toStartCase(loc1) === toStartCase(loc2);
    };

    const OtherLocations = [
        {name: "Other Block", uuid: "e2d35dee-c34f-4f54-a68b-f32ee81835b6"},
        {name: "Other Village", uuid: "16b4db7c-e0a8-41f1-ac67-07470a762d9f"}
    ];

    let villages = individualService.getSubjectsInLocation(individual.lowestAddressLevel, 'Village');

    if(villages && villages.length > 0){
        villages = villages.filter(({voided, uuid}) => !voided && (uuid != individual.uuid));
        if(villages.length > 0){
            let isPresent = true;
            const otherBlock = individual.getObservationReadableValue("e2d35dee-c34f-4f54-a68b-f32ee81835b6");
            const otherVillage = individual.getObservationReadableValue("16b4db7c-e0a8-41f1-ac67-07470a762d9f");
            if(otherBlock || otherVillage){
                villages = villages.filter(village =>
                    isLocationMatch(village, individual, OtherLocations[0]) &&
                    isLocationMatch(village, individual, OtherLocations[1]));
                isPresent = villages.length > 0;
            }
            if(isPresent){
                validationResults.push(imports.common.createValidationError(
                    "Village for specified geographical location already exists."));
            }
        }
    }
    return validationResults;
};""",
    },

    {
        "id": "VR-03",
        "title": "Overdue Visit Prevention with Date Range Validation",
        "org": "APF Odisha",
        "form": "ANC.json",
        "pattern": "DATE_RANGE_VALIDATION - Prevents completion of overdue visits and validates encounter date falls within the scheduled month",
        "description": "Two validations: (1) Cannot complete an overdue visit - must cancel it instead. (2) Encounter date must fall within the same month as the scheduled date.",
        "rule": """'use strict';
({params, imports}) => {
    const programEncounter = params.entity;
    const moment = imports.moment;
    const validationResults = [];

    const isMaxVisitDateTimeGreaterThanToday = moment(programEncounter.maxVisitDateTime).isBefore(moment(), 'day');
    if (isMaxVisitDateTimeGreaterThanToday) {
        validationResults.push(imports.common.createValidationError(
            "You cannot complete an overdue visit. Please cancel this visit."));
    }

    const scheduleDate = programEncounter.earliestVisitDateTime;
    const isBeforeScheduleMonth = moment(programEncounter.encounterDateTime)
        .isBefore(moment(scheduleDate).startOf('month'));
    const isAfterScheduleMonth = moment(programEncounter.encounterDateTime)
        .isAfter(moment(scheduleDate).endOf('month'));

    if (isBeforeScheduleMonth || isAfterScheduleMonth) {
        validationResults.push(imports.common.createValidationError(
            "Visit date must be within the scheduled month."));
    }

    return validationResults;
};""",
    },

    {
        "id": "VR-04",
        "title": "Cancel-Before-Schedule Prevention",
        "org": "APF Odisha",
        "form": "PW Home Visit Cancellation.json",
        "pattern": "CANCEL_DATE_VALIDATION - Prevents cancellation before the scheduled visit date",
        "description": "Validates that the cancellation date is not before the earliest scheduled visit date.",
        "rule": """'use strict';
({params, imports}) => {
    const programEncounter = params.entity;
    const moment = imports.moment;
    const validationResults = [];

    const isBeforeScheduleDate = moment(programEncounter.cancelDateTime)
        .isBefore(moment(programEncounter.earliestVisitDateTime), 'day');

    if (isBeforeScheduleDate) {
        validationResults.push(
            imports.common.createValidationError("You cannot cancel a visit before its scheduled date.")
        );
    }

    return validationResults;
};""",
    },
]


# =============================================================================
# CATEGORY 4: SKIP LOGIC (FEG) RULES
# =============================================================================

SKIP_LOGIC_RULES = [
    {
        "id": "SL-01",
        "title": "Cross-Encounter Skip Logic with Value Preservation",
        "org": "atul_uat",
        "form": "ANC - Follow Up Encounter.json",
        "pattern": "CROSS_ENCOUNTER_SKIP_WITH_PRESERVATION - Checks past encounters for existing answers, but never hides a field that already has a value in the current encounter",
        "description": "Three-step visibility: (1) Never hide if value already exists in current encounter. (2) Check past encounters for 'Yes' answer - if found, hide. (3) Check enrolment-level condition. Complex layered visibility logic.",
        "rule": """'use strict';
({ params, imports }) => {
    const programEncounter = params.entity;
    const formElementGroup = params.formElementGroup;
    const RuleCondition = imports.rulesConfig.RuleCondition;

    const yesConceptUUID = "f7a3a360-58d3-4987-99ff-e7fb97f911a0";
    const fieldConceptUUID = "bb3a806d-2b8b-4982-a46c-b82204cac8a1";

    return formElementGroup.formElements.map((formElement) => {
        let visibility = true;

        // STEP 1: Never hide if value already exists in current encounter
        const existingValue = programEncounter.getObservationValue(fieldConceptUUID);
        const isValueAlreadyFilled = existingValue !== undefined && existingValue !== null;

        if (!isValueAlreadyFilled) {
            // STEP 2: Check past encounters
            const ancFollowUps = programEncounter.programEnrolment.encounters
                .filter(e => e.encounterType.name === "ANC - Follow Up");

            if (ancFollowUps.length > 0) {
                const anyEncounterHasYes = ancFollowUps.some(enc =>
                    new RuleCondition({ programEncounter: enc, formElement })
                        .when.valueInEncounter(fieldConceptUUID)
                        .containsAnswerConceptName(yesConceptUUID)
                        .matches()
                );
                if (anyEncounterHasYes) visibility = false;
            } else {
                // STEP 3: Check enrolment-level
                const enrolmentHasYes = new RuleCondition({ programEncounter, formElement })
                    .when.valueInEntireEnrolment(fieldConceptUUID)
                    .containsAnswerConceptName(yesConceptUUID)
                    .matches();
                if (enrolmentHasYes) visibility = false;
            }
        }

        return new imports.rulesConfig.FormElementStatus(formElement.uuid, visibility, null);
    });
};""",
    },

    {
        "id": "SL-02",
        "title": "Cross-Encounter BP Comparison Skip Logic",
        "org": "Purna Clinic",
        "form": "Chronic Disease Follow up.json",
        "pattern": "PREVIOUS_ENCOUNTER_VALUE_COMPARISON - Shows/hides form sections based on values from the previous encounter of the same type",
        "description": "Shows a treatment section only if the previous follow-up encounter had BP >= 140/90, AND the current encounter also shows elevated BP. Combines cross-encounter and within-encounter conditions.",
        "rule": """'use strict';
({params, imports}) => {
    const programEncounter = params.entity;
    const moment = imports.moment;
    const formElementGroup = params.formElementGroup;
    let visibility = true;

    const previousEncounter = programEncounter.programEnrolment.getEncountersOfType(programEncounter.encounterType.name)
        .filter((enc) => enc.encounterDateTime)
        .filter((enc) => enc.encounterDateTime < programEncounter.encounterDateTime);

    const systolicUUID = '3d0a4600-6f0b-464f-baf1-66947448b7d1';
    const diastolicUUID = '0116b8fa-d2cf-4063-84fa-c7f47e41b92b';

    if(previousEncounter && previousEncounter.length > 0) {
        const systolic = previousEncounter[0].getObservationReadableValue(systolicUUID);
        const diastolic = previousEncounter[0].getObservationReadableValue(diastolicUUID);
        if(systolic && diastolic && (systolic >= 140 || systolic <= 160) && (diastolic >= 90 || diastolic <= 100)) {
            visibility = true;
        } else {
            visibility = false;
        }
    } else {
        visibility = false;
    }

    return formElementGroup.formElements.map((formElement) => {
        const condition1 = new imports.rulesConfig.RuleCondition({programEncounter, formElement})
            .when.valueInEncounter(systolicUUID).greaterThanOrEqualTo(140).matches();
        const condition2 = new imports.rulesConfig.RuleCondition({programEncounter, formElement})
            .when.valueInEncounter(diastolicUUID).greaterThanOrEqualTo(90).matches();

        visibility = visibility && (condition1 && condition2);
        return new imports.rulesConfig.FormElementStatus(formElement.uuid, visibility, null);
    });
};""",
    },

    {
        "id": "SL-03",
        "title": "Time-Based MUAC Section Visibility (180 days since enrolment/last assessment)",
        "org": "MLD Trust",
        "form": "Child Monthly Gradation Form.json",
        "pattern": "TIME_INTERVAL_VISIBILITY - Shows form section only after a specific time interval has elapsed since enrolment or last assessment",
        "description": "Shows MUAC measurement section only if 180 days have passed since the last MUAC measurement (or since enrolment if no prior measurements). Also requires the form not to be in cancelled state.",
        "rule": """'use strict';
({params, imports}) => {
    const programEncounter = params.entity;
    const moment = imports.moment;
    const formElementGroup = params.formElementGroup;
    let visibility = true;
    const encounterDateTime = moment(programEncounter.encounterDateTime);
    const programEnrolment = programEncounter.programEnrolment;

    let is180DaysDone = false;

    const childGradationEncounter = programEnrolment.getEncountersOfType(programEncounter.encounterType.name)
        .filter((enc) => moment(enc.encounterDateTime).isSameOrBefore(encounterDateTime)
            && enc.uuid != programEncounter.uuid
            && enc.getObservationValue("506884c5-b725-4c35-9507-3be4da7826c5") != null);

    if(childGradationEncounter.length == 0){
        const programEnrolmentDateTime = moment(programEnrolment.enrolmentDateTime);
        if(encounterDateTime.diff(programEnrolmentDateTime, 'days') >= 180){
            is180DaysDone = true;
        }
    } else {
        const latestEncounterDateTime = moment(childGradationEncounter[0].encounterDateTime);
        if(encounterDateTime.diff(latestEncounterDateTime, 'days') >= 180){
            is180DaysDone = true;
        }
    }

    return formElementGroup.formElements.map((formElement) => {
        const formNotCancelled = new imports.rulesConfig.RuleCondition({programEncounter, formElement})
            .when.valueInEncounter("c6fc9a05-bae7-4efd-842a-308b89f1ae70")
            .containsAnswerConceptName("81b675d6-277b-46c8-9e9d-703d940c7f69").matches();

        visibility = is180DaysDone && formNotCancelled;
        return new imports.rulesConfig.FormElementStatus(formElement.uuid, visibility, null);
    });
};""",
    },

    {
        "id": "SL-04",
        "title": "Multi-Condition Training Topic Skip Logic",
        "org": "APF Odisha",
        "form": "Training Completion.json",
        "pattern": "MULTI_CONDITION_CODED - Shows section if topic was requested AND (all topics done OR this specific topic not yet done)",
        "description": "Controls visibility of training topic sections. Shows a topic section if: the topic was in the requested training list AND (either all topics are marked done OR this topic is NOT in the not-done list).",
        "rule": """'use strict';
({params, imports}) => {
    const encounter = params.entity;
    const formElementGroup = params.formElementGroup;
    let visibility = true;

    return formElementGroup.formElements.map((formElement) => {
        const isTopicRequested = new imports.rulesConfig.RuleCondition({encounter, formElement})
            .when.valueInEncounter("ae7ca272-c8e8-4d49-92db-1dca212b83fe")
            .containsAnswerConceptName("faa583de-ead4-4380-98d5-41f625fd5c8a").matches();

        const trainingDoneForAllTopics = new imports.rulesConfig.RuleCondition({encounter, formElement})
            .when.valueInEncounter("845560bd-23d1-4137-9781-ec7ebdd12e89")
            .containsAnswerConceptName("8ebbf088-f292-483e-9084-7de919ce67b7").matches();

        const isTopicNotDone = new imports.rulesConfig.RuleCondition({encounter, formElement})
            .when.valueInEncounter("6f234049-60e8-4d8f-b70a-7a7712f6398b")
            .containsAnswerConceptName("faa583de-ead4-4380-98d5-41f625fd5c8a").matches();

        visibility = isTopicRequested && (trainingDoneForAllTopics || !isTopicNotDone);
        return new imports.rulesConfig.FormElementStatus(formElement.uuid, visibility, null);
    });
};""",
    },

    {
        "id": "SL-05",
        "title": "Auto-Naming from Location with Side Effects",
        "org": "Goonj",
        "form": "Village Registration.json",
        "pattern": "SIDE_EFFECT_SKIP_LOGIC - FEG rule that modifies entity properties (sets individual name from location) as a side effect of visibility calculation",
        "description": "Sets the village subject's name from the address level name or from 'Other Village' text field. This is a side effect performed inside the skip logic rule.",
        "rule": """'use strict';
({params, imports}) => {
    const individual = params.entity;
    const formElementGroup = params.formElementGroup;
    let visibility = true;

    function toStartCase(str) {
        return str.trim().toLowerCase().split(/[\\s]+/)
            .map(word => word.charAt(0).toUpperCase() + word.slice(1)).join(' ');
    }

    return formElementGroup.formElements.map((formElement) => {
        if(individual) {
            if(individual.lowestAddressLevel && individual.lowestAddressLevel.name === 'Other') {
                const otherVillageName = individual.getObservationReadableValue('16b4db7c-e0a8-41f1-ac67-07470a762d9f');
                if (otherVillageName) {
                    individual.firstName = toStartCase(otherVillageName);
                    individual.name = toStartCase(otherVillageName);
                }
            } else if(individual.lowestAddressLevel) {
                individual.firstName = toStartCase(individual.lowestAddressLevel.name);
                individual.name = toStartCase(individual.lowestAddressLevel.name);
            }
        }
        return new imports.rulesConfig.FormElementStatus(formElement.uuid, visibility, null);
    });
};""",
    },
]


# =============================================================================
# CATEGORY 5: EDIT FORM RULES
# =============================================================================

EDIT_FORM_RULES = [
    {
        "id": "EF-01",
        "title": "Role + Time + Ownership Edit Restriction",
        "org": "Goonj",
        "form": "Village Assessment Encounter Form.json",
        "pattern": "ROLE_TIME_OWNERSHIP - Restricts editing based on user role, record ownership (created by same user), and time window (3 days)",
        "description": "Uses Realm DB to reload encounter and check createdByUUID. Only the creating user (if Field User or Field Supervisor) can edit within 3 days of the encounter date.",
        "rule": '''"use strict";
({params, imports}) => {
    const {entity, form, services, entityContext, myUserGroups, user, db} = params;
    const moment = imports.moment;

    const encounterReloaded = db.objects('Encounter').filtered('uuid = $0', entity.uuid)[0];
    const userGroups = myUserGroups.map((grp) => grp.groupName);

    const isUserFieldUser = userGroups.includes('Field Users');
    const isUserFieldSupervisor = userGroups.includes('Field Supervisor');

    const createdBy = encounterReloaded ? encounterReloaded.createdByUUID : null;
    const sameUser = createdBy === user.userUUID;

    const userCanEdit = (isUserFieldSupervisor || isUserFieldUser) && sameUser;

    const currentDate = moment();
    const encounterDate = moment(entity.encounterDateTime);
    const thresholdDate = encounterDate.clone().add(3, 'days');
    const isEncounterDateWithinThreeDays = thresholdDate.isSameOrAfter(currentDate, 'day');

    const editableValue = userCanEdit && isEncounterDateWithinThreeDays;

    return {
        editable: {
            value: editableValue,
            messageKey: !editableValue ?
                (!userCanEdit ? 'Not authorized to edit this record' :
                'Edit window has expired (3 days)') : undefined
        }
    };
};''',
    },

    {
        "id": "EF-02",
        "title": "Previous Month Edit Prevention for Cancelled Visits",
        "org": "APF Odisha",
        "form": "Growth Monitoring Encounter Cancellation.json",
        "pattern": "MONTH_BOUNDARY_EDIT - Prevents editing cancelled visits from a previous month",
        "description": "Simple but important rule: if a visit was cancelled and the scheduled date (earliestVisitDateTime) was in a previous month, editing is not allowed.",
        "rule": '''"use strict";
({ params, imports }) => {
    const { entity } = params;
    const moment = imports.moment;

    const isCancelledPreviousMonth =
        entity.cancelDateTime &&
        moment(entity.earliestVisitDateTime).isBefore(moment(), 'month');

    if (isCancelledPreviousMonth) {
        return {
            eligible: {
                value: false,
                message: "Cancelled visits from a previous month cannot be edited."
            }
        };
    }

    return { eligible: { value: true } };
};''',
    },

    {
        "id": "EF-03",
        "title": "Simple Time-Based Edit Restriction with User Group Check",
        "org": "Maitrayana",
        "form": "YPI Pragati Lifeskill Session Attendance Encounter.json",
        "pattern": "TIME_AND_ROLE_EDIT - Allows edit only for specific user group and within 3-day window",
        "description": "Users in the 'Users' group can edit encounters within 3 days of the encounter date. After 3 days, the form becomes read-only.",
        "rule": '''"use strict";
({params, imports}) => {
    const {entity, form, services, entityContext, myUserGroups, userInfo} = params;
    const _ = imports.lodash;
    const moment = imports.moment;
    const userGroupExists = _.find(myUserGroups, userGroup => userGroup.groupName === 'Users');
    const hasBeenThreeDays = moment(params.entity.encounterDateTime).isBefore(moment().subtract(3, 'days'));
    return {
        editable: {
            value: !!userGroupExists && !hasBeenThreeDays,
            messageKey: "Cannot edit after 3 days"
        }
    };
};''',
    },
]


# =============================================================================
# CATEGORY 6: CHECKLIST RULES
# =============================================================================

CHECKLIST_RULES = [
    {
        "id": "CL-01",
        "title": "Vaccination Checklist from Child Enrolment",
        "org": "APF Odisha / Animedh / Ashwini",
        "form": "Child Enrolment.json",
        "pattern": "VACCINATION_CHECKLIST - Standard pattern for creating vaccination checklists based on child's date of birth",
        "description": "Creates a vaccination checklist using the child's date of birth as the base date. Maps all checklist items from the configured vaccination schedule.",
        "rule": """'use strict';
({params, imports}) => {
    let vaccination = params.checklistDetails.find(cd => cd.name === 'Vaccination');
    if (vaccination === undefined) return [];

    const vaccinationList = {
        baseDate: params.entity.individual.dateOfBirth,
        detail: {uuid: vaccination.uuid},
        items: vaccination.items.map(vi => ({
            detail: {uuid: vi.uuid}
        }))
    };

    return [vaccinationList];
};""",
    },
]


# =============================================================================
# SUMMARY: PATTERN INDEX
# =============================================================================

PATTERN_INDEX = {
    "Decision Rules": {
        "MULTI_OUTPUT_DECISION": "Multiple complicationsBuilder instances for different output concepts (DR-01)",
        "VITAL_SIGNS_THRESHOLD": "Threshold-based recommendations from vital signs (DR-02)",
        "CROSS_SUBJECT_LOOKUP": "Looking up data from a different subject (DR-03)",
        "MULTI_THRESHOLD_CLASSIFICATION": "Classifying conditions from numeric ranges (DR-04)",
        "TRIMESTER_BASED_INVESTIGATION": "Tracking investigations by pregnancy trimester (DR-05)",
    },
    "Visit Schedule Rules": {
        "INTERVAL_CHAIN": "Progressive interval-based visit chains (VS-01)",
        "CONDITIONAL_FOLLOWUP": "Follow-up based on encounter outcomes (VS-02)",
        "CANCELLATION_RESCHEDULE": "Rescheduling on cancellation by encounter type (VS-03)",
        "DAILY_RECURRING_WITH_SKIP": "Daily visits that skip weekends (VS-04)",
        "REGISTRATION_MULTI_SCHEDULE": "Multiple encounter types from registration (VS-05)",
        "NUMBERED_FOLLOWUP_RESCHEDULE": "Auto-incrementing numbered visits (VS-06)",
        "ENCOUNTER_TRIGGERS_NEW_TYPE": "One encounter triggers a different type (VS-07)",
        "DYNAMIC_VISIT_NAMING": "Date-based dynamic visit names (VS-08)",
    },
    "Validation Rules": {
        "GROUP_OBSERVATION_RECONCILIATION": "Reconciling counts across grouped observations (VR-01)",
        "DUPLICATE_SUBJECT_PREVENTION": "Preventing duplicate registrations (VR-02)",
        "DATE_RANGE_VALIDATION": "Overdue/schedule month validation (VR-03)",
        "CANCEL_DATE_VALIDATION": "Preventing cancellation before schedule date (VR-04)",
    },
    "Skip Logic Rules": {
        "CROSS_ENCOUNTER_SKIP_WITH_PRESERVATION": "Past encounter check with value preservation (SL-01)",
        "PREVIOUS_ENCOUNTER_VALUE_COMPARISON": "Comparing with previous encounter values (SL-02)",
        "TIME_INTERVAL_VISIBILITY": "Showing fields after time interval (SL-03)",
        "MULTI_CONDITION_CODED": "Multiple coded answer conditions combined (SL-04)",
        "SIDE_EFFECT_SKIP_LOGIC": "Entity modification as side effect (SL-05)",
    },
    "Edit Form Rules": {
        "ROLE_TIME_OWNERSHIP": "Role + time + ownership restrictions (EF-01)",
        "MONTH_BOUNDARY_EDIT": "Previous month edit prevention (EF-02)",
        "TIME_AND_ROLE_EDIT": "Simple time + role edit restriction (EF-03)",
    },
    "Checklist Rules": {
        "VACCINATION_CHECKLIST": "Standard vaccination checklist pattern (CL-01)",
    },
}

# Total examples: 25 (5 decision + 8 visit schedule + 4 validation + 5 skip logic + 3 edit form + 1 checklist = 26)

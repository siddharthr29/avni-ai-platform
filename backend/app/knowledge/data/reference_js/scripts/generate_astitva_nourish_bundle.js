#!/usr/bin/env node
/**
 * Astitva Nourish Program Bundle Generator
 *
 * Generates complete AVNI bundle from the SRS Excel file.
 *
 * Programs:
 *   - Nourish - Pregnancy (for pregnant/lactating mothers)
 *   - Nourish - Child (for children 0-5 years)
 *
 * Subject Types:
 *   - Beneficiary (Person)
 *   - Anganwadi Center (Group/Location)
 *
 * Usage:
 *   node scripts/generate_astitva_nourish_bundle.js
 */

const XLSX = require('xlsx');
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

// ═══════════════════════════════════════════════════════════════════════════
// CONFIGURATION
// ═══════════════════════════════════════════════════════════════════════════

const INPUT_FILE = '/Users/samanvay/Downloads/All/avni-ai/srs/Astitva Nourish Program Forms.xlsx';
const OUTPUT_DIR = path.join(__dirname, '..', 'output', 'Astitva-Nourish-Program');

// Column mapping for this SRS format
const COLUMN_MAP = {
  pageName: '__EMPTY',
  fieldName: '__EMPTY_1',
  dataType: '__EMPTY_2',
  mandatory: '__EMPTY_3',
  userSystem: '__EMPTY_4',
  allowNegative: 'Numeric Datatype',
  allowDecimal: '__EMPTY_5',
  minMaxLimit: '__EMPTY_6',
  unit: '__EMPTY_7',
  allowCurrentDate: 'Date Datatype',
  allowFutureDate: '__EMPTY_8',
  allowPastDate: '__EMPTY_9',
  selectionType: 'Pre added Options Datatype',
  options: '__EMPTY_10',
  uniqueOption: '__EMPTY_11',
  optionCondition: '__EMPTY_12',
  whenToShow: '__EMPTY_13',
  whenNotToShow: '__EMPTY_14'
};

// Sheets to skip (metadata/non-form sheets)
const SKIP_SHEETS = [
  'Other Important links',
  'Draft',
  'Mobile Dashboard',
  'Reports',
  'Permissions',
  'Field Visit report',
  'Behavioural Assessment'
];

// Standard UUIDs from existing AVNI implementations
const STANDARD_UUIDS = {
  // Common answers
  'Yes': 'e1018fd6-6a74-45e5-9191-6dec7647d817',
  'No': 'cca1df60-04c2-497c-a5ad-47438ae9fb7c',
  'None': '02188bcb-32da-44fd-bb5a-867f13f37b43',
  'NA': '7926ed86-c1f1-4567-a46b-bad1d248ed34',
  'N/A': '7926ed86-c1f1-4567-a46b-bad1d248ed34',
  'Other': 'dde76252-3032-41f5-ab53-1802951574ee',
  'Others': 'dde76252-3032-41f5-ab53-1802951574ee',

  // Genders
  'Male': 'b175441e-e0ce-4b35-b492-08df1521dd42',
  'Female': '4e92d0cf-426e-4e55-9162-711f60e722cb',

  // Social categories
  'General': '32b27bce-8c35-4bc8-896e-42f40bb7f8bd',
  'OBC': '27a2b135-1ac7-4bc5-9751-48718a637246',
  'SC': '12b98c8a-f3bd-476e-94e0-1246b66aa8b3',
  'ST': '6b6435f0-ab89-44bf-adb4-da5c27bbb78a',

  // Nutrition categories
  'Normal': 'a9b8c7d6-e5f4-4321-a987-654321fedcba',
  'SAM': 'sam12345-6789-abcd-ef01-234567890abc',
  'MAM': 'mam12345-6789-abcd-ef01-234567890abc',
  'SUW': 'suw12345-6789-abcd-ef01-234567890abc',
  'MUW': 'muw12345-6789-abcd-ef01-234567890abc',

  // Delivery types
  'C-section': 'csection-1234-5678-9abc-def012345678',
};

// Exclusive options that need unique: true in multi-select
const EXCLUSIVE_OPTIONS = ['None', 'NA', 'N/A', 'Not Applicable', 'No complications'];

// Normal ranges for common vitals/measurements
const NORMAL_RANGES = {
  'Weight': { lowAbsolute: 0, highAbsolute: 300, unit: 'kg' },
  'Height': { lowAbsolute: 0, highAbsolute: 250, unit: 'cm' },
  'HB Level': { lowAbsolute: 2, highAbsolute: 20, lowNormal: 11, highNormal: 16, unit: 'g/dL' },
  'HB': { lowAbsolute: 2, highAbsolute: 20, lowNormal: 11, highNormal: 16, unit: 'g/dL' },
  'BP Systolic': { lowAbsolute: 60, highAbsolute: 250, lowNormal: 90, highNormal: 140, unit: 'mmHg' },
  'BP Distolic': { lowAbsolute: 40, highAbsolute: 150, lowNormal: 60, highNormal: 90, unit: 'mmHg' },
  'Birth Weight': { lowAbsolute: 0.5, highAbsolute: 7, unit: 'kg' },
  'Birth Height': { lowAbsolute: 20, highAbsolute: 70, unit: 'cm' },
  'Age': { lowAbsolute: 0, highAbsolute: 120, unit: 'years' },
  'Order of Birth': { lowAbsolute: 1, highAbsolute: 15 },
};

// Form type classification based on sheet name
const FORM_TYPE_RULES = [
  { pattern: /registration/i, formType: 'IndividualProfile' },
  { pattern: /enrol(l)?ment/i, formType: 'ProgramEnrolment' },
  { pattern: /exit/i, formType: 'ProgramExit' },
  { pattern: /cancellation/i, formType: 'ProgramEncounterCancellation' },
];

// Program mapping based on sheet name
const PROGRAM_RULES = [
  { pattern: /pregnancy|AN |anc|pnc|mother|delivery|HCCM/i, program: 'Nourish - Pregnancy' },
  { pattern: /child|growth monitoring/i, program: 'Nourish - Child' },
];

// Subject type based on sheet name
const SUBJECT_TYPE_RULES = [
  { pattern: /anganwadi/i, subjectType: 'Anganwadi Center' },
  { pattern: /leave form/i, subjectType: 'Staff' },
];

// ═══════════════════════════════════════════════════════════════════════════
// UTILITY FUNCTIONS
// ═══════════════════════════════════════════════════════════════════════════

function generateUUID(seed) {
  // Check standard UUIDs first
  if (STANDARD_UUIDS[seed]) return STANDARD_UUIDS[seed];

  // Generate deterministic UUID from seed
  const hash = crypto.createHash('md5').update(seed).digest('hex');
  return `${hash.slice(0, 8)}-${hash.slice(8, 12)}-${hash.slice(12, 16)}-${hash.slice(16, 20)}-${hash.slice(20, 32)}`;
}

function parseOptions(optionsStr) {
  if (!optionsStr || typeof optionsStr !== 'string') return [];

  // Clean up the string
  let cleaned = optionsStr.trim();
  if (cleaned === '—' || cleaned === '-' || cleaned === '–') return [];

  let options = [];

  // Try different delimiters
  if (cleaned.includes('\n')) {
    options = cleaned.split('\n');
  } else if (cleaned.includes(',')) {
    options = cleaned.split(',');
  } else if (cleaned.includes(';')) {
    options = cleaned.split(';');
  } else {
    options = [cleaned];
  }

  // Clean and filter options
  return options
    .map(o => o.trim())
    .filter(o => o.length > 0 && o !== '—' && o !== '-' && o !== '–' && !o.toLowerCase().includes('list'));
}

function mapDataType(typeStr) {
  if (!typeStr) return 'Text';

  const type = typeStr.toLowerCase().trim();

  if (type.includes('pre added') || type.includes('dropdown') || type.includes('select')) return 'Coded';
  if (type.includes('numeric') || type.includes('number') || type.includes('integer')) return 'Numeric';
  if (type.includes('date') && !type.includes('datetime')) return 'Date';
  if (type.includes('datetime')) return 'DateTime';
  if (type.includes('image') || type.includes('photo')) return 'Image';
  if (type.includes('phone')) return 'PhoneNumber';
  if (type.includes('notes')) return 'Notes';
  if (type.includes('subject') || type.includes('location')) return 'Subject';
  if (type.includes('auto')) return 'Numeric'; // Auto-calculated fields are usually numeric

  return 'Text';
}

function getFormType(sheetName) {
  for (const rule of FORM_TYPE_RULES) {
    if (rule.pattern.test(sheetName)) {
      return rule.formType;
    }
  }
  return 'ProgramEncounter'; // Default to program encounter
}

function getProgram(sheetName) {
  for (const rule of PROGRAM_RULES) {
    if (rule.pattern.test(sheetName)) {
      return rule.program;
    }
  }
  return null; // General encounter
}

function getSubjectType(sheetName) {
  for (const rule of SUBJECT_TYPE_RULES) {
    if (rule.pattern.test(sheetName)) {
      return rule.subjectType;
    }
  }
  return 'Beneficiary'; // Default subject type
}

function isExclusiveOption(optionName) {
  return EXCLUSIVE_OPTIONS.some(exclusive =>
    optionName.toLowerCase() === exclusive.toLowerCase()
  );
}

function parseMinMax(limitStr) {
  if (!limitStr || typeof limitStr !== 'string') return null;

  // Match patterns like "0-100", "18 - 80", "min 0 max 120"
  const rangeMatch = limitStr.match(/(\d+(?:\.\d+)?)\s*[-–to]\s*(\d+(?:\.\d+)?)/);
  if (rangeMatch) {
    return {
      lowAbsolute: parseFloat(rangeMatch[1]),
      highAbsolute: parseFloat(rangeMatch[2])
    };
  }

  return null;
}

function parseSkipLogic(whenToShow, whenNotToShow, conceptUuidMap) {
  if (!whenToShow && !whenNotToShow) return null;

  const rules = [];

  // Parse "When to show" conditions
  if (whenToShow && typeof whenToShow === 'string' && whenToShow.trim()) {
    const conditions = parseConditions(whenToShow, conceptUuidMap, 'show');
    if (conditions) rules.push(...conditions);
  }

  // Parse "When NOT to show" conditions
  if (whenNotToShow && typeof whenNotToShow === 'string' && whenNotToShow.trim()) {
    const conditions = parseConditions(whenNotToShow, conceptUuidMap, 'hide');
    if (conditions) rules.push(...conditions);
  }

  return rules.length > 0 ? rules : null;
}

function parseConditions(conditionStr, conceptUuidMap, actionType) {
  // Common patterns: "Field = Value", "Field != Value", "Field contains Value"
  const patterns = [
    { regex: /(.+?)\s*=\s*['"]?(.+?)['"]?$/i, operator: 'containsAnswerConceptName' },
    { regex: /(.+?)\s*!=\s*['"]?(.+?)['"]?$/i, operator: 'notContainsAnswerConceptName' },
    { regex: /(.+?)\s*>\s*(\d+(?:\.\d+)?)/i, operator: 'greaterThan' },
    { regex: /(.+?)\s*<\s*(\d+(?:\.\d+)?)/i, operator: 'lessThan' },
    { regex: /(.+?)\s*>=\s*(\d+(?:\.\d+)?)/i, operator: 'greaterThanOrEqualTo' },
    { regex: /(.+?)\s*<=\s*(\d+(?:\.\d+)?)/i, operator: 'lessThanOrEqualTo' },
  ];

  for (const pattern of patterns) {
    const match = conditionStr.match(pattern.regex);
    if (match) {
      const conceptName = match[1].trim();
      const value = match[2].trim();
      const conceptUuid = conceptUuidMap[conceptName];

      if (conceptUuid) {
        const isNumeric = !isNaN(parseFloat(value));
        return [{
          actions: [{ actionType: actionType === 'show' ? 'showFormElement' : 'hideFormElement' }],
          conditions: [{
            compoundRule: {
              rules: [{
                lhs: {
                  type: 'concept',
                  scope: 'encounter',
                  conceptName: conceptName,
                  conceptUuid: conceptUuid,
                  conceptDataType: isNumeric ? 'Numeric' : 'Coded'
                },
                rhs: isNumeric
                  ? { type: 'value', value: parseFloat(value) }
                  : { type: 'answerConcept', answerConceptNames: [value] },
                operator: pattern.operator
              }],
              conjunction: 'and'
            }
          }]
        }];
      }
    }
  }

  return null;
}

// ═══════════════════════════════════════════════════════════════════════════
// MAIN GENERATOR CLASS
// ═══════════════════════════════════════════════════════════════════════════

class AstitvaNourishBundleGenerator {
  constructor() {
    this.concepts = new Map();
    this.answers = new Map();
    this.forms = [];
    this.programs = new Map();
    this.encounterTypes = new Map();
    this.subjectTypes = new Map();
    this.formMappings = [];
    this.conceptUuidMap = {};
  }

  generate() {
    console.log('\n🌱 Astitva Nourish Program Bundle Generator');
    console.log('═'.repeat(55));
    console.log(`   Input: ${path.basename(INPUT_FILE)}`);
    console.log(`   Output: ${OUTPUT_DIR}`);
    console.log('═'.repeat(55) + '\n');

    // Create output directories
    fs.mkdirSync(OUTPUT_DIR, { recursive: true });
    fs.mkdirSync(path.join(OUTPUT_DIR, 'forms'), { recursive: true });

    // Read Excel file
    console.log(`📖 Reading Excel file...`);
    const workbook = XLSX.readFile(INPUT_FILE);
    console.log(`   Found ${workbook.SheetNames.length} sheets\n`);

    // Initialize subject types
    this.initializeSubjectTypes();

    // Initialize programs
    this.initializePrograms();

    // Process each sheet
    for (const sheetName of workbook.SheetNames) {
      if (SKIP_SHEETS.includes(sheetName) || this.shouldSkipSheet(sheetName)) {
        console.log(`⏭️  Skipping: ${sheetName}`);
        continue;
      }

      console.log(`\n📋 Processing: ${sheetName}`);
      this.processSheet(workbook.Sheets[sheetName], sheetName);
    }

    // Generate all output files
    this.writeAllFiles();

    this.printSummary();
  }

  shouldSkipSheet(sheetName) {
    const name = sheetName.toLowerCase();
    return name.includes('dashboard') ||
           name.includes('report') && !name.includes('field visit report') ||
           name.includes('permission') ||
           name.includes('important link') ||
           name.includes('draft');
  }

  initializeSubjectTypes() {
    // Beneficiary (main subject type)
    this.subjectTypes.set('Beneficiary', {
      name: 'Beneficiary',
      uuid: generateUUID('subject-Beneficiary'),
      active: true,
      type: 'Person',
      allowMiddleName: false,
      allowProfilePicture: true,
      shouldSyncByLocation: true,
      settings: {
        displayRegistrationDetails: true,
        displayPlannedEncounters: true
      },
      voided: false
    });

    // Anganwadi Center (group subject)
    this.subjectTypes.set('Anganwadi Center', {
      name: 'Anganwadi Center',
      uuid: generateUUID('subject-Anganwadi Center'),
      active: true,
      type: 'Group',
      allowMiddleName: false,
      allowProfilePicture: false,
      shouldSyncByLocation: true,
      group: true,
      household: false,
      settings: {
        displayRegistrationDetails: true,
        displayPlannedEncounters: true
      },
      voided: false
    });
  }

  initializePrograms() {
    // Nourish - Pregnancy Program
    this.programs.set('Nourish - Pregnancy', {
      name: 'Nourish - Pregnancy',
      uuid: generateUUID('program-Nourish - Pregnancy'),
      colour: '#E91E63',
      voided: false,
      active: true,
      enrolmentSummaryRule: '',
      enrolmentEligibilityCheckRule: '',
      programSubjectLabel: 'AN Mother',
      manualEnrolmentEligibilityCheckRule: '',
      manualEligibilityCheckRequired: false
    });

    // Nourish - Child Program
    this.programs.set('Nourish - Child', {
      name: 'Nourish - Child',
      uuid: generateUUID('program-Nourish - Child'),
      colour: '#4CAF50',
      voided: false,
      active: true,
      enrolmentSummaryRule: '',
      enrolmentEligibilityCheckRule: '',
      programSubjectLabel: 'Child',
      manualEnrolmentEligibilityCheckRule: '',
      manualEligibilityCheckRequired: false,
      showGrowthChart: true
    });
  }

  processSheet(sheet, sheetName) {
    const data = XLSX.utils.sheet_to_json(sheet, { defval: '' });
    if (data.length <= 1) {
      console.log('   ⚠️ Empty or header-only sheet');
      return;
    }

    // Skip header row
    const rows = data.slice(1);

    const formName = sheetName.trim();
    const formUuid = generateUUID(`form-${formName}`);
    const formType = getFormType(formName);
    const program = getProgram(formName);
    const subjectType = getSubjectType(formName);

    console.log(`   Form Type: ${formType}`);
    if (program) console.log(`   Program: ${program}`);
    console.log(`   Subject Type: ${subjectType}`);

    const formElementGroups = [];
    let currentGroup = null;
    let groupOrder = 0;
    let elementOrder = 0;

    for (const row of rows) {
      const fieldName = String(row[COLUMN_MAP.fieldName] || '').trim();
      if (!fieldName || fieldName.length < 2 || fieldName.toLowerCase() === 'field name') continue;

      const pageName = String(row[COLUMN_MAP.pageName] || 'General').trim() || 'General';
      const dataType = String(row[COLUMN_MAP.dataType] || 'Text').trim();
      const mandatory = String(row[COLUMN_MAP.mandatory] || '').toLowerCase() === 'yes';
      const options = parseOptions(row[COLUMN_MAP.options]);
      const selectionType = String(row[COLUMN_MAP.selectionType] || '').toLowerCase();
      const unit = row[COLUMN_MAP.unit];
      const minMaxLimit = row[COLUMN_MAP.minMaxLimit];
      const whenToShow = row[COLUMN_MAP.whenToShow];
      const whenNotToShow = row[COLUMN_MAP.whenNotToShow];
      const uniqueOption = row[COLUMN_MAP.uniqueOption];

      // Create or switch to form element group
      if (!currentGroup || currentGroup.name !== pageName) {
        if (currentGroup && currentGroup.formElements.length > 0) {
          formElementGroups.push(currentGroup);
        }
        groupOrder++;
        elementOrder = 0;
        currentGroup = {
          uuid: generateUUID(`feg-${formName}-${pageName}-${groupOrder}`),
          name: pageName,
          displayOrder: groupOrder,
          formElements: [],
          timed: false,
          display: pageName
        };
      }

      // Determine concept data type
      const conceptDataType = mapDataType(dataType);
      const conceptUuid = generateUUID(`concept-${fieldName}`);
      this.conceptUuidMap[fieldName] = conceptUuid;

      // Create concept
      const concept = {
        name: fieldName,
        uuid: conceptUuid,
        dataType: conceptDataType,
        active: true
      };

      // Add numeric properties
      if (conceptDataType === 'Numeric') {
        // Check for predefined normal ranges
        const normalRange = NORMAL_RANGES[fieldName];
        if (normalRange) {
          Object.assign(concept, normalRange);
        } else {
          // Parse from SRS
          const parsedRange = parseMinMax(minMaxLimit);
          if (parsedRange) {
            Object.assign(concept, parsedRange);
          }
          if (unit) {
            concept.unit = unit;
          }
        }
      }

      // Add answers for coded concepts
      if (conceptDataType === 'Coded' && options.length > 0) {
        concept.answers = options.map((opt, idx) => {
          const answerUuid = STANDARD_UUIDS[opt] || generateUUID(`answer-${opt}`);
          const answer = {
            name: opt,
            uuid: answerUuid,
            order: idx
          };

          // Mark exclusive options
          if (isExclusiveOption(opt) || (uniqueOption && opt === uniqueOption.trim())) {
            answer.unique = true;
          }

          // Store answer concept
          if (!this.answers.has(opt)) {
            this.answers.set(opt, {
              name: opt,
              uuid: answerUuid,
              dataType: 'NA',
              active: true
            });
          }

          return answer;
        });
      }

      this.concepts.set(fieldName, concept);

      // Create form element
      elementOrder++;
      const isMultiSelect = selectionType.includes('multi');

      const formElement = {
        name: fieldName,
        uuid: generateUUID(`fe-${formName}-${fieldName}-${elementOrder}`),
        keyValues: [],
        concept: {
          name: fieldName,
          uuid: conceptUuid,
          dataType: conceptDataType,
          answers: concept.answers || [],
          active: true,
          media: []
        },
        displayOrder: elementOrder,
        type: isMultiSelect ? 'MultiSelect' : 'SingleSelect',
        mandatory: mandatory
      };

      // Add skip logic as declarative rule
      const skipRule = parseSkipLogic(whenToShow, whenNotToShow, this.conceptUuidMap);
      if (skipRule) {
        formElement.declarativeRule = skipRule;
      }

      currentGroup.formElements.push(formElement);
      console.log(`   ✓ ${fieldName} (${conceptDataType}${mandatory ? ' *' : ''})${isMultiSelect ? ' [Multi]' : ''}`);
    }

    // Add last group
    if (currentGroup && currentGroup.formElements.length > 0) {
      formElementGroups.push(currentGroup);
    }

    if (formElementGroups.length === 0) {
      console.log('   ⚠️ No form elements extracted');
      return;
    }

    // Create form
    const form = {
      name: formName,
      uuid: formUuid,
      formType: formType,
      formElementGroups: formElementGroups,
      decisionRule: '',
      visitScheduleRule: '',
      validationRule: '',
      checklistsRule: '',
      decisionConcepts: []
    };

    this.forms.push(form);

    // Create encounter type for encounters
    if (formType === 'ProgramEncounter' || formType === 'Encounter') {
      const encounterName = formName;
      if (!this.encounterTypes.has(encounterName)) {
        this.encounterTypes.set(encounterName, {
          name: encounterName,
          uuid: generateUUID(`encounter-${encounterName}`),
          entityEligibilityCheckRule: '',
          active: true,
          immutable: false
        });
      }
    }

    // Create form mapping
    const mapping = {
      uuid: generateUUID(`mapping-${formName}`),
      formUUID: formUuid,
      formType: formType,
      formName: formName,
      enableApproval: false,
      isVoided: false
    };

    // Set subject type
    mapping.subjectTypeUUID = this.subjectTypes.get(subjectType)?.uuid ||
                              this.subjectTypes.get('Beneficiary').uuid;

    // Add program for program forms
    if (program && formType.startsWith('Program')) {
      mapping.programUUID = this.programs.get(program)?.uuid;
    }

    // Add encounter type for encounters
    if (formType === 'ProgramEncounter' || formType === 'Encounter') {
      mapping.encounterTypeUUID = generateUUID(`encounter-${formName}`);
    }

    this.formMappings.push(mapping);
  }

  writeAllFiles() {
    console.log('\n📁 Writing output files...');

    // 1. Write concepts
    const allConcepts = [
      ...Array.from(this.answers.values()),
      ...Array.from(this.concepts.values())
    ];
    fs.writeFileSync(
      path.join(OUTPUT_DIR, 'concepts.json'),
      JSON.stringify(allConcepts, null, 2)
    );
    console.log(`   ✓ concepts.json (${allConcepts.length} concepts)`);

    // 2. Write forms
    for (const form of this.forms) {
      fs.writeFileSync(
        path.join(OUTPUT_DIR, 'forms', `${form.name}.json`),
        JSON.stringify(form, null, 2)
      );
    }
    console.log(`   ✓ forms/ (${this.forms.length} forms)`);

    // 3. Write cancellation forms
    let cancellationCount = 0;
    for (const [name, et] of this.encounterTypes) {
      const cancellationForm = {
        name: `${name} Cancellation`,
        uuid: generateUUID(`form-cancel-${name}`),
        formType: 'ProgramEncounterCancellation',
        formElementGroups: []
      };
      fs.writeFileSync(
        path.join(OUTPUT_DIR, 'forms', `${name} Cancellation.json`),
        JSON.stringify(cancellationForm, null, 2)
      );
      cancellationCount++;

      // Add cancellation form mapping
      const program = getProgram(name);
      const mapping = {
        uuid: generateUUID(`mapping-cancel-${name}`),
        formUUID: cancellationForm.uuid,
        subjectTypeUUID: this.subjectTypes.get('Beneficiary').uuid,
        formType: 'ProgramEncounterCancellation',
        formName: cancellationForm.name,
        encounterTypeUUID: et.uuid,
        enableApproval: false,
        isVoided: false
      };
      if (program) {
        mapping.programUUID = this.programs.get(program)?.uuid;
      }
      this.formMappings.push(mapping);
    }
    console.log(`   ✓ cancellation forms (${cancellationCount} forms)`);

    // 4. Write subject types
    fs.writeFileSync(
      path.join(OUTPUT_DIR, 'subjectTypes.json'),
      JSON.stringify(Array.from(this.subjectTypes.values()), null, 2)
    );
    console.log(`   ✓ subjectTypes.json (${this.subjectTypes.size} types)`);

    // 5. Write programs
    const programsWithRules = Array.from(this.programs.values()).map(prog => {
      // Add eligibility rules
      if (prog.name === 'Nourish - Pregnancy') {
        prog.enrolmentEligibilityCheckDeclarativeRule = [{
          actions: [{ actionType: 'showProgram' }],
          conditions: [{
            compoundRule: {
              rules: [{
                lhs: { type: 'gender' },
                rhs: { type: 'value', value: 'Female' },
                operator: 'equals'
              }]
            }
          }]
        }];
      } else if (prog.name === 'Nourish - Child') {
        prog.enrolmentEligibilityCheckDeclarativeRule = [{
          actions: [{ actionType: 'showProgram' }],
          conditions: [{
            compoundRule: {
              rules: [{
                lhs: { type: 'ageInYears' },
                rhs: { type: 'value', value: 5 },
                operator: 'lessThanOrEqualTo'
              }],
              conjunction: 'and'
            }
          }]
        }];
      }
      return prog;
    });
    fs.writeFileSync(
      path.join(OUTPUT_DIR, 'programs.json'),
      JSON.stringify(programsWithRules, null, 2)
    );
    console.log(`   ✓ programs.json (${this.programs.size} programs)`);

    // 6. Write encounter types
    fs.writeFileSync(
      path.join(OUTPUT_DIR, 'encounterTypes.json'),
      JSON.stringify(Array.from(this.encounterTypes.values()), null, 2)
    );
    console.log(`   ✓ encounterTypes.json (${this.encounterTypes.size} types)`);

    // 7. Write form mappings
    fs.writeFileSync(
      path.join(OUTPUT_DIR, 'formMappings.json'),
      JSON.stringify(this.formMappings, null, 2)
    );
    console.log(`   ✓ formMappings.json (${this.formMappings.length} mappings)`);

    // 8. Write operational configs
    this.writeOperationalConfigs();

    // 9. Write address level types
    this.writeAddressLevelTypes();

    // 10. Write individual relations
    this.writeIndividualRelations();

    // 11. Write organisation config
    this.writeOrganisationConfig();

    // 12. Write groups and privileges (CRITICAL for permissions)
    this.writeGroupsAndPrivileges();

    // 13. Write standard report cards
    this.writeReportCards();
  }

  writeOperationalConfigs() {
    // Operational Encounter Types
    const opEncounters = Array.from(this.encounterTypes.values()).map(et => ({
      encounterType: { uuid: et.uuid, name: et.name },
      uuid: generateUUID(`op-enc-${et.name}`),
      name: et.name,
      voided: false
    }));
    fs.writeFileSync(
      path.join(OUTPUT_DIR, 'operationalEncounterTypes.json'),
      JSON.stringify(opEncounters, null, 2)
    );
    console.log(`   ✓ operationalEncounterTypes.json`);

    // Operational Programs
    const opPrograms = Array.from(this.programs.values()).map(prog => ({
      program: { uuid: prog.uuid, name: prog.name },
      uuid: generateUUID(`op-prog-${prog.name}`),
      name: prog.name,
      voided: false,
      programSubjectLabel: prog.programSubjectLabel
    }));
    fs.writeFileSync(
      path.join(OUTPUT_DIR, 'operationalPrograms.json'),
      JSON.stringify(opPrograms, null, 2)
    );
    console.log(`   ✓ operationalPrograms.json`);

    // Operational Subject Types
    const opSubjects = Array.from(this.subjectTypes.values()).map(st => ({
      subjectType: { uuid: st.uuid, name: st.name },
      uuid: generateUUID(`op-subject-${st.name}`),
      name: st.name,
      voided: false
    }));
    fs.writeFileSync(
      path.join(OUTPUT_DIR, 'operationalSubjectTypes.json'),
      JSON.stringify(opSubjects, null, 2)
    );
    console.log(`   ✓ operationalSubjectTypes.json`);
  }

  writeAddressLevelTypes() {
    const addressTypes = [
      { uuid: generateUUID('addr-state'), name: 'State', level: 1, isRegistrationLocation: false, parent: null },
      { uuid: generateUUID('addr-district'), name: 'District', level: 2, isRegistrationLocation: false, parent: { name: 'State', uuid: generateUUID('addr-state') } },
      { uuid: generateUUID('addr-block'), name: 'Block', level: 3, isRegistrationLocation: false, parent: { name: 'District', uuid: generateUUID('addr-district') } },
      { uuid: generateUUID('addr-village'), name: 'Village', level: 4, isRegistrationLocation: true, parent: { name: 'Block', uuid: generateUUID('addr-block') } },
      { uuid: generateUUID('addr-hamlet'), name: 'Hamlet', level: 5, isRegistrationLocation: true, parent: { name: 'Village', uuid: generateUUID('addr-village') } },
    ];
    fs.writeFileSync(
      path.join(OUTPUT_DIR, 'addressLevelTypes.json'),
      JSON.stringify(addressTypes, null, 2)
    );
    console.log(`   ✓ addressLevelTypes.json`);
  }

  writeIndividualRelations() {
    const relations = [
      { name: 'Father', gender: 'Male' },
      { name: 'Mother', gender: 'Female' },
      { name: 'Son', gender: 'Male' },
      { name: 'Daughter', gender: 'Female' },
      { name: 'Husband', gender: 'Male' },
      { name: 'Wife', gender: 'Female' },
      { name: 'Brother', gender: 'Male' },
      { name: 'Sister', gender: 'Female' },
      { name: 'Guardian', gender: 'Male' },
      { name: 'Guardian', gender: 'Female' },
    ].map(rel => ({
      id: null,
      name: rel.name,
      uuid: generateUUID(`relation-${rel.name}-${rel.gender}`),
      voided: false,
      genders: [{
        uuid: STANDARD_UUIDS[rel.gender],
        name: rel.gender,
        voided: false
      }]
    }));

    fs.writeFileSync(
      path.join(OUTPUT_DIR, 'individualRelation.json'),
      JSON.stringify(relations, null, 2)
    );
    console.log(`   ✓ individualRelation.json`);

    // Relationship types
    const relationshipTypes = [
      { from: 'Father', to: 'Son' },
      { from: 'Father', to: 'Daughter' },
      { from: 'Mother', to: 'Son' },
      { from: 'Mother', to: 'Daughter' },
      { from: 'Husband', to: 'Wife' },
    ].map(rel => ({
      uuid: generateUUID(`reltype-${rel.from}-${rel.to}`),
      name: `${rel.from}-${rel.to}`,
      individualAIsToBRelation: {
        name: rel.from,
        uuid: generateUUID(`relation-${rel.from}-Male`)
      },
      individualBIsToARelation: {
        name: rel.to,
        uuid: generateUUID(`relation-${rel.to}-${rel.to === 'Wife' || rel.to === 'Daughter' ? 'Female' : 'Male'}`)
      },
      voided: false
    }));

    fs.writeFileSync(
      path.join(OUTPUT_DIR, 'relationshipType.json'),
      JSON.stringify(relationshipTypes, null, 2)
    );
    console.log(`   ✓ relationshipType.json`);
  }

  writeOrganisationConfig() {
    const config = {
      uuid: generateUUID('org-config-Astitva-Nourish'),
      settings: {
        languages: ['en', 'hi'],
        myDashboardFilters: [],
        searchFilters: [],
        enableMessaging: false
      }
    };
    fs.writeFileSync(
      path.join(OUTPUT_DIR, 'organisationConfig.json'),
      JSON.stringify(config, null, 2)
    );
    console.log(`   ✓ organisationConfig.json`);
  }

  writeGroupsAndPrivileges() {
    // Define user groups based on typical AVNI org structure
    const groups = [
      { name: 'Everyone', uuid: generateUUID('group-Everyone'), notEveryoneGroup: false },
      { name: 'CHW', uuid: generateUUID('group-CHW') },
      { name: 'Supervisor', uuid: generateUUID('group-Supervisor') },
      { name: 'Program Manager', uuid: generateUUID('group-Program Manager') },
      { name: 'Admin', uuid: generateUUID('group-Admin') },
    ];

    fs.writeFileSync(
      path.join(OUTPUT_DIR, 'groups.json'),
      JSON.stringify(groups, null, 2)
    );
    console.log(`   ✓ groups.json (${groups.length} groups)`);

    // Generate privileges for each group
    const privileges = [];
    const privilegeTypes = [
      // Subject privileges
      'ViewSubject', 'RegisterSubject', 'EditSubject', 'VoidSubject',
      // Enrolment privileges
      'EnrolSubject', 'ViewEnrolmentDetails', 'EditEnrolmentDetails', 'ExitEnrolment',
      // Visit privileges
      'ViewVisit', 'ScheduleVisit', 'PerformVisit', 'EditVisit', 'CancelVisit',
      // Other privileges
      'AddMember', 'EditMember', 'RemoveMember',
    ];

    // CHW: Full access to most things
    const chwGroup = groups.find(g => g.name === 'CHW');
    // Supervisor: Same as CHW + additional
    const supervisorGroup = groups.find(g => g.name === 'Supervisor');
    // Admin: Full access
    const adminGroup = groups.find(g => g.name === 'Admin');

    for (const subjectType of this.subjectTypes.values()) {
      for (const privilegeType of privilegeTypes) {
        // CHW privileges
        privileges.push({
          uuid: generateUUID(`priv-${chwGroup.name}-${privilegeType}-${subjectType.name}`),
          groupUUID: chwGroup.uuid,
          privilegeType: privilegeType,
          subjectTypeUUID: subjectType.uuid,
          programUUID: null,
          encounterTypeUUID: null,
          allow: true,
          voided: false
        });

        // Supervisor privileges
        privileges.push({
          uuid: generateUUID(`priv-${supervisorGroup.name}-${privilegeType}-${subjectType.name}`),
          groupUUID: supervisorGroup.uuid,
          privilegeType: privilegeType,
          subjectTypeUUID: subjectType.uuid,
          programUUID: null,
          encounterTypeUUID: null,
          allow: true,
          voided: false
        });

        // Admin privileges
        privileges.push({
          uuid: generateUUID(`priv-${adminGroup.name}-${privilegeType}-${subjectType.name}`),
          groupUUID: adminGroup.uuid,
          privilegeType: privilegeType,
          subjectTypeUUID: subjectType.uuid,
          programUUID: null,
          encounterTypeUUID: null,
          allow: true,
          voided: false
        });
      }
    }

    // Add program-specific privileges
    for (const program of this.programs.values()) {
      const programPrivilegeTypes = [
        'EnrolSubject', 'ViewEnrolmentDetails', 'EditEnrolmentDetails', 'ExitEnrolment'
      ];
      for (const privilegeType of programPrivilegeTypes) {
        for (const group of [chwGroup, supervisorGroup, adminGroup]) {
          privileges.push({
            uuid: generateUUID(`priv-${group.name}-${privilegeType}-${program.name}`),
            groupUUID: group.uuid,
            privilegeType: privilegeType,
            subjectTypeUUID: this.subjectTypes.get('Beneficiary').uuid,
            programUUID: program.uuid,
            encounterTypeUUID: null,
            allow: true,
            voided: false
          });
        }
      }
    }

    // Add encounter-specific privileges
    for (const encounterType of this.encounterTypes.values()) {
      const encPrivilegeTypes = ['ViewVisit', 'ScheduleVisit', 'PerformVisit', 'EditVisit', 'CancelVisit'];
      for (const privilegeType of encPrivilegeTypes) {
        for (const group of [chwGroup, supervisorGroup, adminGroup]) {
          privileges.push({
            uuid: generateUUID(`priv-${group.name}-${privilegeType}-${encounterType.name}`),
            groupUUID: group.uuid,
            privilegeType: privilegeType,
            subjectTypeUUID: this.subjectTypes.get('Beneficiary').uuid,
            programUUID: null,
            encounterTypeUUID: encounterType.uuid,
            allow: true,
            voided: false
          });
        }
      }
    }

    fs.writeFileSync(
      path.join(OUTPUT_DIR, 'groupPrivilege.json'),
      JSON.stringify(privileges, null, 2)
    );
    console.log(`   ✓ groupPrivilege.json (${privileges.length} privileges)`);
  }

  writeReportCards() {
    // Standard report card types from AVNI
    const standardCardTypes = {
      scheduledVisits: '27020b32-c21b-43a4-81bd-7b88ad3a6ef0',
      overdueVisits: '9f88bee5-2ab9-4ac5-ae19-d07e9715bdb5',
      total: '1fbcadf3-bf1a-439e-9e13-24adddfbf6c0',
      recentRegistrations: '88a7514c-48c0-4d5d-a421-d074e43bb36c',
      recentEnrolments: 'a5efc04c-317a-4823-a203-e62603454a65',
      recentVisits: '77b5b3fa-de35-4f24-996b-2842492ea6e0',
    };

    const reportCards = [
      {
        uuid: generateUUID('card-scheduled-visits'),
        name: 'Scheduled Visits',
        description: 'Visits scheduled for today',
        color: '#388e3c',
        nested: false,
        count: 1,
        standardReportCardType: standardCardTypes.scheduledVisits,
        standardReportCardInputSubjectTypes: [],
        standardReportCardInputPrograms: [],
        standardReportCardInputEncounterTypes: [],
        voided: false
      },
      {
        uuid: generateUUID('card-overdue-visits'),
        name: 'Overdue Visits',
        description: 'Visits that are past their due date',
        color: '#d32f2f',
        nested: false,
        count: 2,
        standardReportCardType: standardCardTypes.overdueVisits,
        standardReportCardInputSubjectTypes: [],
        standardReportCardInputPrograms: [],
        standardReportCardInputEncounterTypes: [],
        voided: false
      },
      {
        uuid: generateUUID('card-total-beneficiaries'),
        name: 'Total Beneficiaries',
        description: 'Total registered beneficiaries',
        color: '#1976d2',
        nested: false,
        count: 3,
        standardReportCardType: standardCardTypes.total,
        standardReportCardInputSubjectTypes: [{ uuid: this.subjectTypes.get('Beneficiary').uuid }],
        standardReportCardInputPrograms: [],
        standardReportCardInputEncounterTypes: [],
        voided: false
      },
      {
        uuid: generateUUID('card-recent-registrations'),
        name: 'Recent Registrations',
        description: 'Recently registered beneficiaries',
        color: '#7b1fa2',
        nested: false,
        count: 4,
        standardReportCardType: standardCardTypes.recentRegistrations,
        standardReportCardInputSubjectTypes: [],
        standardReportCardInputPrograms: [],
        standardReportCardInputEncounterTypes: [],
        voided: false
      },
      {
        uuid: generateUUID('card-recent-enrolments'),
        name: 'Recent Enrolments',
        description: 'Recent program enrolments',
        color: '#00796b',
        nested: false,
        count: 5,
        standardReportCardType: standardCardTypes.recentEnrolments,
        standardReportCardInputSubjectTypes: [],
        standardReportCardInputPrograms: [],
        standardReportCardInputEncounterTypes: [],
        voided: false
      },
    ];

    fs.writeFileSync(
      path.join(OUTPUT_DIR, 'reportCard.json'),
      JSON.stringify(reportCards, null, 2)
    );
    console.log(`   ✓ reportCard.json (${reportCards.length} cards)`);

    // Create dashboard to assign report cards
    const reportDashboard = [
      {
        uuid: generateUUID('dashboard-main'),
        name: 'Main Dashboard',
        description: 'Default dashboard for all users',
        sections: [
          {
            uuid: generateUUID('section-visits'),
            name: 'Visits',
            description: 'Visit tracking',
            displayOrder: 1,
            viewType: 'Default',
            cards: [
              { uuid: reportCards[0].uuid, displayOrder: 1 },
              { uuid: reportCards[1].uuid, displayOrder: 2 },
            ]
          },
          {
            uuid: generateUUID('section-beneficiaries'),
            name: 'Beneficiaries',
            description: 'Beneficiary statistics',
            displayOrder: 2,
            viewType: 'Default',
            cards: [
              { uuid: reportCards[2].uuid, displayOrder: 1 },
              { uuid: reportCards[3].uuid, displayOrder: 2 },
              { uuid: reportCards[4].uuid, displayOrder: 3 },
            ]
          }
        ],
        voided: false
      }
    ];

    fs.writeFileSync(
      path.join(OUTPUT_DIR, 'reportDashboard.json'),
      JSON.stringify(reportDashboard, null, 2)
    );
    console.log(`   ✓ reportDashboard.json`);

    // Assign dashboard to all groups
    const groupDashboards = [];
    const groups = JSON.parse(fs.readFileSync(path.join(OUTPUT_DIR, 'groups.json'), 'utf8'));
    for (const group of groups) {
      groupDashboards.push({
        uuid: generateUUID(`group-dashboard-${group.name}`),
        groupUUID: group.uuid,
        dashboardUUID: reportDashboard[0].uuid,
        primaryDashboard: true,
        voided: false
      });
    }

    fs.writeFileSync(
      path.join(OUTPUT_DIR, 'groupDashboards.json'),
      JSON.stringify(groupDashboards, null, 2)
    );
    console.log(`   ✓ groupDashboards.json`);
  }

  printSummary() {
    console.log('\n' + '═'.repeat(55));
    console.log('📊 GENERATION COMPLETE');
    console.log('═'.repeat(55));
    console.log(`   Concepts: ${this.concepts.size + this.answers.size}`);
    console.log(`      - Questions: ${this.concepts.size}`);
    console.log(`      - Answers: ${this.answers.size}`);
    console.log(`   Forms: ${this.forms.length}`);
    console.log(`   Cancellation Forms: ${this.encounterTypes.size}`);
    console.log(`   Programs: ${this.programs.size}`);
    console.log(`      - Nourish - Pregnancy`);
    console.log(`      - Nourish - Child`);
    console.log(`   Encounter Types: ${this.encounterTypes.size}`);
    console.log(`   Subject Types: ${this.subjectTypes.size}`);
    console.log(`      - Beneficiary`);
    console.log(`      - Anganwadi Center`);
    console.log(`   Form Mappings: ${this.formMappings.length}`);
    console.log('═'.repeat(55));
    console.log(`📁 Output: ${OUTPUT_DIR}`);
  }

  runValidation() {
    console.log('\n' + '═'.repeat(55));
    console.log('🔍 RUNNING BUNDLE VALIDATION');
    console.log('═'.repeat(55));

    // Import the validator
    const { BundleValidator } = require('../validators/bundle_validator.js');
    const validator = new BundleValidator(OUTPUT_DIR);

    // Run validation (suppress default output, we'll handle it)
    const originalLog = console.log;
    const logs = [];
    console.log = (...args) => logs.push(args.join(' '));

    const result = validator.validate();

    console.log = originalLog;

    // Process results
    if (result.errors.length === 0 && result.warnings.length === 0) {
      console.log('\n✅ VALIDATION PASSED - Bundle is ready for upload!\n');
      return { success: true, errors: [], warnings: [] };
    }

    // Show errors
    if (result.errors.length > 0) {
      console.log(`\n❌ VALIDATION FAILED - ${result.errors.length} error(s) found:\n`);
      for (const error of result.errors) {
        console.log(`   ❌ ${error}`);
      }

      // Provide actionable fixes
      console.log('\n📋 SUGGESTED FIXES:\n');
      for (const error of result.errors) {
        const fix = this.suggestFix(error);
        if (fix) {
          console.log(`   → ${fix}`);
        }
      }
    }

    // Show warnings
    if (result.warnings.length > 0) {
      console.log(`\n⚠️  WARNINGS - ${result.warnings.length} issue(s) to review:\n`);
      for (const warning of result.warnings) {
        console.log(`   ⚠️  ${warning}`);
      }
    }

    return result;
  }

  suggestFix(error) {
    // Provide actionable suggestions based on error type
    if (error.includes('DUPLICATE UUID')) {
      return 'Check concepts.json for duplicate UUIDs. Ensure each concept has a unique UUID.';
    }
    if (error.includes('DUPLICATE CONCEPT NAME')) {
      return 'Same concept name appears with different UUIDs. Consolidate to single UUID.';
    }
    if (error.includes('Missing CRITICAL file: groups.json')) {
      return 'Generator should create groups.json. Re-run generator or add manually.';
    }
    if (error.includes('Missing CRITICAL file: groupPrivilege.json')) {
      return 'Generator should create groupPrivilege.json. Re-run generator or add manually.';
    }
    if (error.includes('ANSWER UUID MISMATCH')) {
      return 'Answer UUID in form differs from concepts.json. Update form to use master UUID.';
    }
    return null;
  }

  checkSRSCompleteness() {
    console.log('\n' + '═'.repeat(55));
    console.log('📋 CHECKING SRS COMPLETENESS');
    console.log('═'.repeat(55));

    const missingInfo = [];

    // Check if we have enough data for a complete bundle
    if (this.subjectTypes.size === 0) {
      missingInfo.push({
        item: 'Subject Types',
        suggestion: 'SRS should define subject types (e.g., Beneficiary, Household)',
        srsLocation: 'Look for "Subject Types" or "Modelling" sheet'
      });
    }

    if (this.programs.size === 0) {
      missingInfo.push({
        item: 'Programs',
        suggestion: 'SRS should define programs (e.g., Maternal Health, Child Health)',
        srsLocation: 'Look for "Programs" or "Modelling" sheet'
      });
    }

    if (this.forms.length === 0) {
      missingInfo.push({
        item: 'Forms',
        suggestion: 'SRS should have form definitions with fields',
        srsLocation: 'Each form should be a separate sheet with field definitions'
      });
    }

    if (this.concepts.size === 0) {
      missingInfo.push({
        item: 'Concepts/Fields',
        suggestion: 'No form fields found. Check column mapping matches SRS format',
        srsLocation: 'Form sheets should have Field Name, Data Type, Options columns'
      });
    }

    // Check for common missing SRS elements
    const hasUserGroups = this.checkSRSForUserGroups();
    if (!hasUserGroups) {
      missingInfo.push({
        item: 'User Groups/Permissions',
        suggestion: 'Using default groups (CHW, Supervisor, Admin). Customize if needed.',
        srsLocation: 'Look for "Permissions" or "User Roles" sheet in SRS'
      });
    }

    const hasDashboardSpec = this.checkSRSForDashboards();
    if (!hasDashboardSpec) {
      missingInfo.push({
        item: 'Dashboard Specifications',
        suggestion: 'Using standard report cards. Customize based on org needs.',
        srsLocation: 'Look for "Mobile Dashboard" or "Offline Dashboard" sheet in SRS'
      });
    }

    if (missingInfo.length > 0) {
      console.log('\n⚠️  SRS COMPLETENESS CHECK:\n');
      for (const info of missingInfo) {
        console.log(`   📌 ${info.item}`);
        console.log(`      Suggestion: ${info.suggestion}`);
        console.log(`      SRS Location: ${info.srsLocation}`);
        console.log('');
      }
      return { complete: false, missingInfo };
    }

    console.log('\n✅ SRS appears complete for bundle generation\n');
    return { complete: true, missingInfo: [] };
  }

  checkSRSForUserGroups() {
    // Check if SRS has user group definitions
    // This would parse the Excel file for a Permissions/User Roles sheet
    // For now, return false to use defaults
    return false;
  }

  checkSRSForDashboards() {
    // Check if SRS has dashboard specifications
    // This would parse the Excel file for a Dashboard sheet
    // For now, return false to use defaults
    return false;
  }

  printNextSteps(validationResult) {
    console.log('\n' + '═'.repeat(55));
    console.log('📋 NEXT STEPS');
    console.log('═'.repeat(55));

    if (!validationResult.valid) {
      console.log('\n❌ Bundle has errors that must be fixed before upload:\n');
      console.log('  1. Fix the errors listed above');
      console.log('  2. Re-run the generator');
      console.log('  3. Or manually fix the JSON files\n');
      return;
    }

    console.log('\n✅ Bundle is ready! Follow these steps:\n');
    console.log('  1. Review generated files for accuracy');
    console.log('  2. Customize groups.json if different user roles needed');
    console.log('  3. Add skip logic rules where needed');
    console.log('  4. Upload to AVNI in this order:');
    console.log('     a. concepts.json');
    console.log('     b. subjectTypes.json');
    console.log('     c. programs.json');
    console.log('     d. encounterTypes.json');
    console.log('     e. formMappings.json');
    console.log('     f. Individual form files from forms/');
    console.log('     g. groups.json');
    console.log('     h. groupPrivilege.json');
    console.log('     i. reportCard.json, reportDashboard.json');
    console.log('');
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// MAIN
// ═══════════════════════════════════════════════════════════════════════════

const generator = new AstitvaNourishBundleGenerator();
generator.generate();

// Run SRS completeness check
generator.checkSRSCompleteness();

// Run validation after generation
const validationResult = generator.runValidation();

// Print next steps based on validation result
generator.printNextSteps(validationResult);

// Exit with appropriate code
if (!validationResult.valid) {
  console.log('⚠️  Bundle generated with issues. Please fix errors before uploading.\n');
  process.exit(1);
} else {
  console.log('🎉 Bundle generated and validated successfully!\n');
  process.exit(0);
}

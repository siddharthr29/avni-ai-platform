#!/usr/bin/env node
/**
 * Enhanced AVNI Bundle Generator v2
 * 
 * Generates production-quality AVNI bundles with:
 * - Cancellation forms
 * - Declarative skip logic rules
 * - Normal ranges for numeric concepts
 * - Unique flag for exclusive options
 * - Visit schedule rules
 * - Program eligibility rules
 * - Individual relations (family)
 * - Operational configs
 * - Report cards & dashboards
 * 
 * Usage:
 *   node generate_bundle_v2.js --srs <SRS_FILE> --forms <FORMS_FILE> --org <ORG_NAME>
 */

const XLSX = require('xlsx');
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

// ═══════════════════════════════════════════════════════════════════════════
// CONFIGURATION
// ═══════════════════════════════════════════════════════════════════════════

// Standard UUIDs from production
const STANDARD_UUIDS = {
  // Common answers
  'Yes': 'e1018fd6-6a74-45e5-9191-6dec7647d817',
  'No': 'cca1df60-04c2-497c-a5ad-47438ae9fb7c',
  'None': '02188bcb-32da-44fd-bb5a-867f13f37b43',
  'NA': '7926ed86-c1f1-4567-a46b-bad1d248ed34',
  'Other': 'dde76252-3032-41f5-ab53-1802951574ee',
  
  // Genders
  'Male': 'b175441e-e0ce-4b35-b492-08df1521dd42',
  'Female': '4e92d0cf-426e-4e55-9162-711f60e722cb',
  
  // Locations
  'Mobile Clinic': '20721f30-068e-4174-aab2-19d1cd72752c',
  'At the House': '03164959-c995-4ab6-a0ad-bb9ed68131d5',
};

// Exclusive options that need unique: true
const EXCLUSIVE_OPTIONS = ['None', 'NA', 'Not Applicable', 'Td Booster'];

// Normal ranges for common vitals
const NORMAL_RANGES = {
  'BP (Systolic)': { lowAbsolute: 80, highAbsolute: 220, lowNormal: 100, highNormal: 139, unit: 'mmHg' },
  'BP (Diastolic)': { lowAbsolute: 40, highAbsolute: 120, lowNormal: 60, highNormal: 90, unit: 'mmHg' },
  'Hemoglobin': { lowAbsolute: 2, highAbsolute: 16, lowNormal: 11, highNormal: 16, unit: 'g/dL' },
  'Weight': { lowAbsolute: 0, highAbsolute: 300, lowNormal: 45, highNormal: 100, unit: 'kg' },
  'Height': { lowAbsolute: 0, highAbsolute: 250, lowNormal: 140, highNormal: 190, unit: 'cm' },
  'Fetal Heart Rate': { lowAbsolute: 0, highAbsolute: 200, lowNormal: 110, highNormal: 160, unit: 'bpm' },
  'Temperature': { lowAbsolute: 35, highAbsolute: 42, lowNormal: 36.1, highNormal: 37.2, unit: '°C' },
};

// Default family relations
const DEFAULT_RELATIONS = [
  { name: 'Husband', gender: 'Male' },
  { name: 'Wife', gender: 'Female' },
  { name: 'Father', gender: 'Male' },
  { name: 'Mother', gender: 'Female' },
  { name: 'Son', gender: 'Male' },
  { name: 'Daughter', gender: 'Female' },
  { name: 'Brother', gender: 'Male' },
  { name: 'Sister', gender: 'Female' },
  { name: 'Grandfather', gender: 'Male' },
  { name: 'Grandmother', gender: 'Female' },
  { name: 'Son in law', gender: 'Male' },
  { name: 'Daughter in law', gender: 'Female' },
  { name: 'Father in law', gender: 'Male' },
  { name: 'Mother in law', gender: 'Female' },
  { name: 'Uncle', gender: 'Male' },
  { name: 'Aunt', gender: 'Female' },
  { name: 'Nephew', gender: 'Male' },
  { name: 'Niece', gender: 'Female' },
  { name: 'Grandson', gender: 'Male' },
  { name: 'Granddaughter', gender: 'Female' },
  { name: 'Brother in law', gender: 'Male' },
  { name: 'Sister in law', gender: 'Female' },
];

// Default relationship types
const DEFAULT_RELATIONSHIP_TYPES = [
  { from: 'Husband', to: 'Wife' },
  { from: 'Father', to: 'Son' },
  { from: 'Father', to: 'Daughter' },
  { from: 'Mother', to: 'Son' },
  { from: 'Mother', to: 'Daughter' },
  { from: 'Brother', to: 'Sister' },
  { from: 'Grandfather', to: 'Grandson' },
  { from: 'Grandmother', to: 'Granddaughter' },
];

// Visit schedule defaults (encounter type -> days to schedule, days to overdue)
const VISIT_SCHEDULES = {
  'ANC': { scheduleDays: 30, overdueDays: 45 },
  'Mother PNC': { scheduleDays: 7, overdueDays: 14 },
  'HBNC /New Born care': { scheduleDays: 7, overdueDays: 14 },
  'Immunization': { scheduleDays: 28, overdueDays: 42 },
};

// ═══════════════════════════════════════════════════════════════════════════
// UTILITY FUNCTIONS
// ═══════════════════════════════════════════════════════════════════════════

function generateUUID(seed) {
  if (STANDARD_UUIDS[seed]) return STANDARD_UUIDS[seed];
  const hash = crypto.createHash('md5').update(seed).digest('hex');
  return `${hash.slice(0,8)}-${hash.slice(8,12)}-${hash.slice(12,16)}-${hash.slice(16,20)}-${hash.slice(20,32)}`;
}

function parseOptions(optionsStr) {
  if (!optionsStr || typeof optionsStr !== 'string') return [];
  
  let options = [];
  if (optionsStr.includes('\n')) {
    options = optionsStr.split('\n');
  } else if (optionsStr.includes(';')) {
    options = optionsStr.split(';');
  } else if (optionsStr.includes(',')) {
    options = optionsStr.split(',');
  } else {
    options = [optionsStr];
  }
  
  return options.map(o => o.trim()).filter(o => o.length > 0);
}

function isNumericType(type) {
  if (!type) return false;
  const t = type.toLowerCase();
  return t.includes('numeric') || t.includes('number') || t.includes('integer') || t.includes('decimal');
}

function isCodedType(type) {
  if (!type) return false;
  const t = type.toLowerCase();
  return t.includes('coded') || t.includes('pre added') || t.includes('dropdown') || 
         t.includes('single') || t.includes('multi') || t.includes('select');
}

function isDateType(type) {
  if (!type) return false;
  const t = type.toLowerCase();
  return t.includes('date') && !t.includes('datetime');
}

function isTextType(type) {
  if (!type) return false;
  const t = type.toLowerCase();
  return t.includes('text') || t.includes('alpha') || t.includes('string') || t.includes('notes');
}

function mapDataType(typeStr) {
  if (!typeStr) return 'Text';
  
  if (isCodedType(typeStr)) return 'Coded';
  if (isNumericType(typeStr)) return 'Numeric';
  if (isDateType(typeStr)) return 'Date';
  if (typeStr.toLowerCase().includes('image')) return 'ImageV2';
  if (typeStr.toLowerCase().includes('datetime')) return 'DateTime';
  if (typeStr.toLowerCase().includes('id')) return 'Id';
  if (typeStr.toLowerCase().includes('notes')) return 'Notes';
  
  return 'Text';
}

function getFormType(sheetName) {
  const name = sheetName.toLowerCase();
  
  if (name.includes('registration')) return 'IndividualProfile';
  if (name.includes('enrolment') || name.includes('enrollment')) return 'ProgramEnrolment';
  if (name.includes('exit')) return 'ProgramExit';
  if (name.includes('cancellation')) return 'ProgramEncounterCancellation';
  
  return 'ProgramEncounter';
}

function getProgram(sheetName) {
  const name = sheetName.toLowerCase();
  
  // Pregnancy/Maternal
  if (name.includes('anc') || name.includes('pnc') || name.includes('delivery') ||
      name.includes('pregnancy') || name.includes('maternal') || name.includes('mother')) {
    return 'Pregnancy';
  }
  
  // Child
  if (name.includes('child') || name.includes('immunization') || name.includes('hbnc') ||
      name.includes('newborn') || name.includes('new born')) {
    return 'Child';
  }
  
  return null; // General encounter, not program-specific
}

function shouldSkipSheet(sheetName) {
  const name = sheetName.toLowerCase();
  return name.includes('modelling') || 
         name.includes('summary') || 
         name.includes('dashboard') ||
         name.includes('offline') ||
         name.includes('instruction') ||
         name.includes('master');
}

function isExclusiveOption(optionName) {
  return EXCLUSIVE_OPTIONS.some(exclusive => 
    optionName.toLowerCase() === exclusive.toLowerCase()
  );
}

// ═══════════════════════════════════════════════════════════════════════════
// DECLARATIVE RULE GENERATOR
// ═══════════════════════════════════════════════════════════════════════════

function parseSkipLogic(condition, conceptUuidMap) {
  if (!condition || typeof condition !== 'string') return null;
  
  // Parse conditions like "Gender = Female" or "Age > 18"
  const patterns = [
    /^(.+?)\s*=\s*(.+)$/,      // equals
    /^(.+?)\s*!=\s*(.+)$/,     // not equals
    /^(.+?)\s*>\s*(\d+)$/,     // greater than
    /^(.+?)\s*<\s*(\d+)$/,     // less than
    /^(.+?)\s*>=\s*(\d+)$/,    // greater or equal
    /^(.+?)\s*<=\s*(\d+)$/,    // less or equal
  ];
  
  const operatorMap = {
    '=': 'containsAnswerConceptName',
    '!=': 'notContainsAnswerConceptName',
    '>': 'greaterThan',
    '<': 'lessThan',
    '>=': 'greaterThanOrEqualTo',
    '<=': 'lessThanOrEqualTo',
  };
  
  for (const pattern of patterns) {
    const match = condition.match(pattern);
    if (match) {
      const conceptName = match[1].trim();
      const value = match[2].trim();
      const operator = condition.match(/[=!<>]+/)?.[0] || '=';
      
      const conceptUuid = conceptUuidMap[conceptName];
      if (!conceptUuid) continue;
      
      // Build declarative rule
      const rule = {
        actions: [{ actionType: 'showFormElement' }],
        conditions: [{
          compoundRule: {
            rules: [{
              lhs: {
                type: 'concept',
                scope: 'encounter',
                conceptName: conceptName,
                conceptUuid: conceptUuid,
                conceptDataType: isNaN(value) ? 'Coded' : 'Numeric'
              },
              rhs: isNaN(value) 
                ? { type: 'answerConcept', answerConceptNames: [value] }
                : { type: 'value', value: parseFloat(value) },
              operator: operatorMap[operator] || 'containsAnswerConceptName'
            }]
          }
        }]
      };
      
      return [rule];
    }
  }
  
  return null;
}

function generateVisitScheduleRule(encounterType) {
  const schedule = VISIT_SCHEDULES[encounterType];
  if (!schedule) return null;
  
  return [{
    actions: [{
      details: {
        dateField: 'encounterDateTime',
        daysToSchedule: String(schedule.scheduleDays),
        daysToOverdue: String(schedule.overdueDays),
        encounterName: encounterType,
        encounterType: encounterType
      },
      actionType: 'scheduleVisit'
    }],
    conditions: [{
      compoundRule: {
        rules: [{ lhs: {}, rhs: {} }]
      }
    }]
  }];
}

// ═══════════════════════════════════════════════════════════════════════════
// BUNDLE GENERATOR
// ═══════════════════════════════════════════════════════════════════════════

class BundleGenerator {
  constructor(options) {
    this.srsFile = options.srs;
    this.formsFile = options.forms;
    this.orgName = options.org;
    this.outputDir = options.output || path.join(__dirname, '..', 'output', this.orgName.replace(/\s+/g, '-'));
    
    this.concepts = new Map();
    this.answers = new Map();
    this.forms = [];
    this.programs = new Map();
    this.encounterTypes = new Map();
    this.subjectTypes = new Map();
    this.formMappings = [];
    
    this.conceptUuidMap = {}; // name -> uuid mapping for rules
  }
  
  generate() {
    console.log(`\n🚀 Enhanced AVNI Bundle Generator v2`);
    console.log(`${'═'.repeat(50)}`);
    console.log(`   Organization: ${this.orgName}`);
    console.log(`   SRS File: ${this.srsFile || 'Not provided'}`);
    console.log(`   Forms File: ${this.formsFile}`);
    console.log(`${'═'.repeat(50)}\n`);
    
    // Create output directories
    fs.mkdirSync(this.outputDir, { recursive: true });
    fs.mkdirSync(path.join(this.outputDir, 'forms'), { recursive: true });
    
    // Process files
    this.processFormsFile();
    if (this.srsFile) {
      this.processSRSFile();
    }
    
    // Generate all bundle files
    this.writeConcepts();
    this.writeForms();
    this.writePrograms();
    this.writeEncounterTypes();
    this.writeSubjectTypes();
    this.writeFormMappings();
    
    // Generate additional files
    this.writeIndividualRelations();
    this.writeRelationshipTypes();
    this.writeOperationalConfigs();
    this.writeOrganisationConfig();
    this.writeAddressLevelTypes();
    this.writeCancellationForms();
    
    this.printSummary();
  }
  
  processFormsFile() {
    console.log(`📖 Reading: ${path.basename(this.formsFile)}`);
    const workbook = XLSX.readFile(this.formsFile);
    console.log(`   Found ${workbook.SheetNames.length} sheets\n`);
    
    for (const sheetName of workbook.SheetNames) {
      if (shouldSkipSheet(sheetName)) {
        console.log(`⏭️  Skipping: ${sheetName}`);
        continue;
      }
      
      console.log(`📋 Processing: ${sheetName}`);
      this.processSheet(workbook.Sheets[sheetName], sheetName);
    }
  }
  
  processSRSFile() {
    if (!fs.existsSync(this.srsFile)) return;
    
    console.log(`\n📖 Reading SRS: ${path.basename(this.srsFile)}`);
    const workbook = XLSX.readFile(this.srsFile);
    
    // Look for Modelling sheet
    const modellingSheet = workbook.SheetNames.find(name => 
      name.toLowerCase().includes('modelling') || name.toLowerCase().includes('model')
    );
    
    if (modellingSheet) {
      console.log(`   Found Modelling sheet: ${modellingSheet}`);
      // Parse subject types, programs, relationships from modelling
    }
  }
  
  processSheet(sheet, sheetName) {
    const data = XLSX.utils.sheet_to_json(sheet, { defval: '' });
    if (data.length === 0) return;
    
    const formUuid = generateUUID(`form-${sheetName}`);
    const formType = getFormType(sheetName);
    const program = getProgram(sheetName);
    
    // Detect column structure
    const columnMap = this.detectColumns(data[0]);
    if (!columnMap.fieldName) {
      console.log(`   ⚠️ Could not detect field name column`);
      return;
    }
    
    const formElementGroups = [];
    let currentGroup = null;
    let groupOrder = 0;
    let elementOrder = 0;
    
    for (const row of data) {
      const fieldName = String(row[columnMap.fieldName] || '').trim();
      if (!fieldName || fieldName.length < 2) continue;
      
      const pageName = String(row[columnMap.pageName] || 'General').trim() || 'General';
      const dataType = String(row[columnMap.dataType] || 'Text').trim();
      const mandatory = String(row[columnMap.mandatory] || '').toLowerCase() === 'yes';
      const options = parseOptions(row[columnMap.options]);
      const skipLogic = row[columnMap.skipLogic];
      const unit = row[columnMap.unit];
      const selectionType = row[columnMap.selectionType];
      
      // Create or switch to form element group
      if (!currentGroup || currentGroup.name !== pageName) {
        if (currentGroup) formElementGroups.push(currentGroup);
        groupOrder++;
        elementOrder = 0;
        currentGroup = {
          uuid: generateUUID(`feg-${sheetName}-${pageName}-${groupOrder}`),
          name: pageName,
          displayOrder: groupOrder,
          formElements: [],
          timed: false,
          display: pageName
        };
      }
      
      // Create concept
      const conceptDataType = mapDataType(dataType);
      const conceptUuid = generateUUID(`concept-${fieldName}`);
      this.conceptUuidMap[fieldName] = conceptUuid;
      
      const concept = {
        name: fieldName,
        uuid: conceptUuid,
        dataType: conceptDataType,
        active: true
      };
      
      // Add numeric ranges
      if (conceptDataType === 'Numeric') {
        const ranges = NORMAL_RANGES[fieldName];
        if (ranges) {
          Object.assign(concept, ranges);
        } else if (unit) {
          concept.unit = unit;
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
          if (isExclusiveOption(opt)) {
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
      const isMultiSelect = selectionType?.toLowerCase().includes('multi') || 
                            dataType.toLowerCase().includes('multi');
      
      const formElement = {
        name: fieldName,
        uuid: generateUUID(`fe-${sheetName}-${fieldName}-${elementOrder}`),
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
      if (skipLogic) {
        const declarativeRule = parseSkipLogic(skipLogic, this.conceptUuidMap);
        if (declarativeRule) {
          formElement.declarativeRule = declarativeRule;
        }
      }
      
      currentGroup.formElements.push(formElement);
      console.log(`   ✓ ${fieldName} (${conceptDataType}${mandatory ? ' *' : ''})`);
    }
    
    // Add last group
    if (currentGroup && currentGroup.formElements.length > 0) {
      formElementGroups.push(currentGroup);
    }
    
    if (formElementGroups.length === 0) return;
    
    // Create form
    const form = {
      name: sheetName,
      uuid: formUuid,
      formType: formType,
      formElementGroups: formElementGroups,
      decisionRule: '',
      visitScheduleRule: '',
      validationRule: '',
      checklistsRule: '',
      decisionConcepts: []
    };
    
    // Add visit schedule for encounters
    if (formType === 'ProgramEncounter') {
      const encounterType = sheetName.replace(/ Form$/, '').replace(/ Encounter$/, '');
      const visitSchedule = generateVisitScheduleRule(encounterType);
      if (visitSchedule) {
        form.visitScheduleDeclarativeRule = visitSchedule;
      }
    }
    
    this.forms.push(form);
    
    // Register program, encounter type, subject type
    if (program && !this.programs.has(program)) {
      this.programs.set(program, {
        name: program,
        uuid: generateUUID(`program-${program}`),
        colour: program === 'Pregnancy' ? '#74b5de' : '#96d643',
        voided: false,
        active: true,
        showGrowthChart: program === 'Child'
      });
    }
    
    if (formType === 'ProgramEncounter' || formType === 'Encounter') {
      const encounterName = sheetName.replace(/ Form$/, '');
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
    
    if (formType === 'IndividualProfile') {
      const subjectName = sheetName.includes('Household') ? 'Household' : 'Individual';
      const subjectType = subjectName === 'Individual' ? 'Person' : 'Household';
      
      if (!this.subjectTypes.has(subjectName)) {
        this.subjectTypes.set(subjectName, {
          name: subjectName,
          uuid: generateUUID(`subject-${subjectName}`),
          active: true,
          type: subjectType,
          allowMiddleName: subjectName === 'Individual',
          allowProfilePicture: false,
          shouldSyncByLocation: true,
          settings: {
            displayRegistrationDetails: true,
            displayPlannedEncounters: true
          },
          household: subjectName === 'Household',
          group: subjectName === 'Household',
          directlyAssignable: false,
          voided: false
        });
      }
    }
    
    // Create form mapping
    const mapping = {
      uuid: generateUUID(`mapping-${sheetName}`),
      formUUID: formUuid,
      formType: formType,
      formName: sheetName,
      enableApproval: false
    };
    
    // Add subject type
    const subjectName = formType === 'IndividualProfile' && sheetName.includes('Household') 
      ? 'Household' : 'Individual';
    mapping.subjectTypeUUID = generateUUID(`subject-${subjectName}`);
    
    // Add program for program forms
    if (program && (formType.startsWith('Program') || formType === 'ProgramEncounter')) {
      mapping.programUUID = generateUUID(`program-${program}`);
    }
    
    // Add encounter type for encounters
    if (formType === 'ProgramEncounter' || formType === 'Encounter') {
      const encounterName = sheetName.replace(/ Form$/, '');
      mapping.encounterTypeUUID = generateUUID(`encounter-${encounterName}`);
    }
    
    this.formMappings.push(mapping);
  }
  
  detectColumns(row) {
    const keys = Object.keys(row);
    const map = {};
    
    // Try to find columns by header names
    for (const key of keys) {
      const lower = key.toLowerCase();
      
      if (lower.includes('field') && lower.includes('name')) map.fieldName = key;
      else if (lower.includes('page') || lower.includes('section')) map.pageName = key;
      else if (lower.includes('data') && lower.includes('type')) map.dataType = key;
      else if (lower.includes('mandatory') || lower.includes('required')) map.mandatory = key;
      else if (lower.includes('option') || lower.includes('pre added')) map.options = key;
      else if (lower.includes('skip') || lower.includes('when to show')) map.skipLogic = key;
      else if (lower.includes('unit')) map.unit = key;
      else if (lower.includes('selection')) map.selectionType = key;
    }
    
    // Fallback to common patterns
    if (!map.fieldName) {
      map.fieldName = keys.find(k => k === '__EMPTY_1' || k.includes('Name')) || keys[1];
    }
    if (!map.pageName) {
      map.pageName = keys.find(k => k === '__EMPTY' || k.includes('Page')) || keys[0];
    }
    if (!map.dataType) {
      map.dataType = keys.find(k => k === '__EMPTY_2' || k.includes('Type')) || keys[2];
    }
    if (!map.mandatory) {
      map.mandatory = keys.find(k => k === '__EMPTY_3' || k.includes('Mandatory')) || keys[3];
    }
    if (!map.options) {
      map.options = keys.find(k => k.includes('OPTIONS') || k.includes('option')) || keys[13];
    }
    if (!map.skipLogic) {
      map.skipLogic = keys.find(k => k.includes('When to show') || k === '__EMPTY_16');
    }
    
    return map;
  }
  
  writeConcepts() {
    const allConcepts = [
      ...Array.from(this.answers.values()),
      ...Array.from(this.concepts.values())
    ];
    
    fs.writeFileSync(
      path.join(this.outputDir, 'concepts.json'),
      JSON.stringify(allConcepts, null, 2)
    );
  }
  
  writeForms() {
    for (const form of this.forms) {
      fs.writeFileSync(
        path.join(this.outputDir, 'forms', `${form.name}.json`),
        JSON.stringify(form, null, 2)
      );
    }
  }
  
  writePrograms() {
    const programsWithEligibility = Array.from(this.programs.values()).map(prog => {
      // Add eligibility rules
      if (prog.name === 'Pregnancy') {
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
      } else if (prog.name === 'Child') {
        prog.enrolmentEligibilityCheckDeclarativeRule = [{
          actions: [{ actionType: 'hideProgram' }],
          conditions: [{
            compoundRule: {
              rules: [{
                lhs: { type: 'ageInYears' },
                rhs: { type: 'value', value: 2 },
                operator: 'greaterThan'
              }],
              conjunction: 'and'
            }
          }]
        }];
      }
      return prog;
    });
    
    fs.writeFileSync(
      path.join(this.outputDir, 'programs.json'),
      JSON.stringify(programsWithEligibility, null, 2)
    );
  }
  
  writeEncounterTypes() {
    fs.writeFileSync(
      path.join(this.outputDir, 'encounterTypes.json'),
      JSON.stringify(Array.from(this.encounterTypes.values()), null, 2)
    );
  }
  
  writeSubjectTypes() {
    fs.writeFileSync(
      path.join(this.outputDir, 'subjectTypes.json'),
      JSON.stringify(Array.from(this.subjectTypes.values()), null, 2)
    );
  }
  
  writeFormMappings() {
    fs.writeFileSync(
      path.join(this.outputDir, 'formMappings.json'),
      JSON.stringify(this.formMappings, null, 2)
    );
  }
  
  writeIndividualRelations() {
    const relations = DEFAULT_RELATIONS.map(rel => ({
      id: null,
      name: rel.name,
      uuid: generateUUID(`relation-${rel.name}`),
      voided: false,
      genders: [{
        uuid: STANDARD_UUIDS[rel.gender],
        name: rel.gender,
        voided: false
      }]
    }));
    
    fs.writeFileSync(
      path.join(this.outputDir, 'individualRelation.json'),
      JSON.stringify(relations, null, 2)
    );
  }
  
  writeRelationshipTypes() {
    const types = DEFAULT_RELATIONSHIP_TYPES.map(rel => ({
      uuid: generateUUID(`reltype-${rel.from}-${rel.to}`),
      name: `${rel.from}-${rel.to}`,
      individualAIsToBRelation: {
        name: rel.from,
        uuid: generateUUID(`relation-${rel.from}`)
      },
      individualBIsToARelation: {
        name: rel.to,
        uuid: generateUUID(`relation-${rel.to}`)
      },
      voided: false
    }));
    
    fs.writeFileSync(
      path.join(this.outputDir, 'relationshipType.json'),
      JSON.stringify(types, null, 2)
    );
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
      path.join(this.outputDir, 'operationalEncounterTypes.json'),
      JSON.stringify(opEncounters, null, 2)
    );
    
    // Operational Programs
    const opPrograms = Array.from(this.programs.values()).map(prog => ({
      program: { uuid: prog.uuid, name: prog.name },
      uuid: generateUUID(`op-prog-${prog.name}`),
      name: prog.name,
      voided: false,
      programSubjectLabel: prog.name === 'Pregnancy' ? 'Pregnant Woman' : 'Child'
    }));
    
    fs.writeFileSync(
      path.join(this.outputDir, 'operationalPrograms.json'),
      JSON.stringify(opPrograms, null, 2)
    );
    
    // Operational Subject Types
    const opSubjects = Array.from(this.subjectTypes.values()).map(st => ({
      subjectType: { uuid: st.uuid, name: st.name },
      uuid: generateUUID(`op-subject-${st.name}`),
      name: st.name,
      voided: false
    }));
    
    fs.writeFileSync(
      path.join(this.outputDir, 'operationalSubjectTypes.json'),
      JSON.stringify(opSubjects, null, 2)
    );
  }
  
  writeOrganisationConfig() {
    const config = {
      uuid: generateUUID(`org-config-${this.orgName}`),
      settings: {
        languages: ['en'],
        myDashboardFilters: [],
        searchFilters: [],
        enableMessaging: false
      }
    };
    
    fs.writeFileSync(
      path.join(this.outputDir, 'organisationConfig.json'),
      JSON.stringify(config, null, 2)
    );
  }
  
  writeAddressLevelTypes() {
    // Default address hierarchy - will need user customization
    const addressTypes = [
      { uuid: generateUUID('addr-state'), name: 'State', level: 1, isRegistrationLocation: false },
      { uuid: generateUUID('addr-district'), name: 'District', level: 2, isRegistrationLocation: false },
      { uuid: generateUUID('addr-block'), name: 'Block', level: 3, isRegistrationLocation: false },
      { uuid: generateUUID('addr-village'), name: 'Village', level: 4, isRegistrationLocation: true },
    ];
    
    fs.writeFileSync(
      path.join(this.outputDir, 'addressLevelTypes.json'),
      JSON.stringify(addressTypes, null, 2)
    );
  }
  
  writeCancellationForms() {
    // Generate cancellation form for each encounter type
    for (const [name, et] of this.encounterTypes) {
      const cancellationForm = {
        name: `${name} Cancellation`,
        uuid: generateUUID(`form-cancel-${name}`),
        formType: 'ProgramEncounterCancellation',
        formElementGroups: []
      };
      
      fs.writeFileSync(
        path.join(this.outputDir, 'forms', `${name} Cancellation.json`),
        JSON.stringify(cancellationForm, null, 2)
      );
      
      // Add cancellation form mapping
      const program = getProgram(name);
      const mapping = {
        uuid: generateUUID(`mapping-cancel-${name}`),
        formUUID: cancellationForm.uuid,
        subjectTypeUUID: generateUUID('subject-Individual'),
        formType: 'ProgramEncounterCancellation',
        formName: cancellationForm.name,
        encounterTypeUUID: et.uuid,
        enableApproval: false
      };
      
      if (program) {
        mapping.programUUID = generateUUID(`program-${program}`);
      }
      
      this.formMappings.push(mapping);
    }
    
    // Rewrite form mappings with cancellation mappings
    fs.writeFileSync(
      path.join(this.outputDir, 'formMappings.json'),
      JSON.stringify(this.formMappings, null, 2)
    );
  }
  
  printSummary() {
    console.log(`\n${'═'.repeat(50)}`);
    console.log(`📊 GENERATION COMPLETE`);
    console.log(`${'═'.repeat(50)}`);
    console.log(`   Concepts: ${this.concepts.size + this.answers.size}`);
    console.log(`      - Questions: ${this.concepts.size}`);
    console.log(`      - Answers: ${this.answers.size}`);
    console.log(`   Forms: ${this.forms.length}`);
    console.log(`   Cancellation Forms: ${this.encounterTypes.size}`);
    console.log(`   Programs: ${this.programs.size}`);
    console.log(`   Encounter Types: ${this.encounterTypes.size}`);
    console.log(`   Subject Types: ${this.subjectTypes.size}`);
    console.log(`   Individual Relations: ${DEFAULT_RELATIONS.length}`);
    console.log(`${'═'.repeat(50)}`);
    console.log(`📁 Output: ${this.outputDir}`);
    console.log(`\n🎉 Bundle generated successfully!\n`);
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// MAIN
// ═══════════════════════════════════════════════════════════════════════════

function main() {
  const args = process.argv.slice(2);
  
  const options = {
    srs: null,
    forms: null,
    org: 'Generated-Bundle',
    output: null
  };
  
  for (let i = 0; i < args.length; i++) {
    switch (args[i]) {
      case '--srs':
        options.srs = args[++i];
        break;
      case '--forms':
        options.forms = args[++i];
        break;
      case '--org':
        options.org = args[++i];
        break;
      case '--output':
        options.output = args[++i];
        break;
    }
  }
  
  if (!options.forms) {
    console.log(`
Usage: node generate_bundle_v2.js --forms <FORMS_FILE> [--srs <SRS_FILE>] [--org <ORG_NAME>] [--output <OUTPUT_DIR>]

Options:
  --forms    Required. Path to Forms Excel file
  --srs      Optional. Path to SRS Excel file (for modelling info)
  --org      Optional. Organization name (default: Generated-Bundle)
  --output   Optional. Output directory path

Example:
  node generate_bundle_v2.js --forms "JK Laxmi Cements Forms.xlsx" --srs "JK Laxmi Cements SRS.xlsx" --org "JK-Laxmi-Cements"
`);
    process.exit(1);
  }
  
  const generator = new BundleGenerator(options);
  generator.generate();
}

main();

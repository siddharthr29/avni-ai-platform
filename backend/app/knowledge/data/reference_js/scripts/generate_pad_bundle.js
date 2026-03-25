#!/usr/bin/env node
/**
 * PAD Adolescent Forms Bundle Generator v2
 * Handles the specific Excel format with merged headers
 */

const XLSX = require('xlsx');
const fs = require('fs');
const path = require('path');
const { v4: uuidv4 } = require('uuid');

const INPUT_FILE = '/Users/samanvay/Downloads/All/avni-ai/PAD Adolescent Forms.xlsx';
const OUTPUT_DIR = '/Users/samanvay/Downloads/All/avni-ai/avni-skills/srs-bundle-generator/output/PAD-Adolescent';
const TRAINING_DATA_DIR = path.join(__dirname, '..', 'training_data');

// Load UUID registry
let uuidRegistry = {};
try {
  uuidRegistry = JSON.parse(fs.readFileSync(path.join(TRAINING_DATA_DIR, 'uuid_registry.json'), 'utf8'));
} catch (e) {
  console.log('Warning: Could not load UUID registry');
}

// Generate deterministic UUID
function generateDeterministicUUID(seed) {
  let hash = 0;
  for (let i = 0; i < seed.length; i++) {
    const char = seed.charCodeAt(i);
    hash = ((hash << 5) - hash) + char;
    hash = hash & hash;
  }
  const hex = Math.abs(hash).toString(16).padStart(8, '0');
  return `${hex.substring(0, 8)}-${uuidv4().substring(9)}`;
}

// Get standard UUID for common answers
function getAnswerUUID(answerName) {
  const normalized = answerName.trim();
  if (uuidRegistry[normalized]) return uuidRegistry[normalized];
  if (uuidRegistry[normalized.toUpperCase()]) return uuidRegistry[normalized.toUpperCase()];
  if (uuidRegistry[normalized.toLowerCase()]) return uuidRegistry[normalized.toLowerCase()];
  return generateDeterministicUUID(`answer:${normalized}`);
}

// Column mapping for this specific Excel format
const COLUMN_MAP = {
  pageName: '__EMPTY',
  fieldName: '__EMPTY_1',
  dataType: '__EMPTY_2',
  mandatory: '__EMPTY_3',
  userOrSystem: '__EMPTY_4',
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
  optionValidation: '__EMPTY_12',
  whenToShow: '__EMPTY_13',
  whenNotToShow: '__EMPTY_14'
};

// Map data type from Excel
function mapDataType(typeStr, selectionType) {
  if (!typeStr) return 'Text';
  const type = typeStr.toString().toLowerCase().trim();
  
  if (type.includes('single select') || type.includes('singleselect')) return 'Coded';
  if (type.includes('multi select') || type.includes('multiselect')) return 'Coded';
  if (type.includes('numeric') || type.includes('number')) return 'Numeric';
  if (type.includes('date') && type.includes('time')) return 'DateTime';
  if (type.includes('date')) return 'Date';
  if (type.includes('text') || type.includes('alpha')) return 'Text';
  if (type.includes('notes') || type.includes('paragraph')) return 'Notes';
  if (type.includes('image') || type.includes('photo')) return 'ImageV2';
  if (type.includes('file') || type.includes('document')) return 'File';
  if (type.includes('phone')) return 'PhoneNumber';
  if (type.includes('location') || type.includes('address')) return 'Location';
  if (type.includes('id')) return 'Id';
  
  // Check selection type
  if (selectionType) {
    const sel = selectionType.toString().toLowerCase();
    if (sel.includes('single') || sel.includes('multi')) return 'Coded';
  }
  
  return 'Text';
}

// Parse options from string
function parseOptions(optionsStr) {
  if (!optionsStr) return [];
  const str = optionsStr.toString().trim();
  if (!str) return [];
  
  // Handle different delimiters: newline, semicolon, comma
  let delimiter = ',';
  if (str.includes('\n')) delimiter = '\n';
  else if (str.includes(';')) delimiter = ';';
  
  return str.split(delimiter)
    .map(o => o.trim())
    .filter(o => o.length > 0 && !o.startsWith('(') && o !== 'Yes' && o !== 'No' && o !== '');
}

// Parse min/max from string like "0-100" or "18"
function parseMinMax(str) {
  if (!str) return { min: null, max: null };
  const s = str.toString().trim();
  
  // Range format: "0-100" or "18 - 80"
  const rangeMatch = s.match(/(\d+)\s*[-–to]\s*(\d+)/i);
  if (rangeMatch) {
    return { min: parseFloat(rangeMatch[1]), max: parseFloat(rangeMatch[2]) };
  }
  
  // Single value
  const numMatch = s.match(/(\d+)/);
  if (numMatch) {
    return { min: null, max: parseFloat(numMatch[1]) };
  }
  
  return { min: null, max: null };
}

// Store for all concepts
const allConcepts = [];
const conceptUUIDs = {};
const answerUUIDs = {};

function getConceptUUID(name) {
  if (conceptUUIDs[name]) return conceptUUIDs[name];
  conceptUUIDs[name] = generateDeterministicUUID(`concept:${name}`);
  return conceptUUIDs[name];
}

function createAnswerConcept(answerName) {
  const uuid = getAnswerUUID(answerName);
  if (answerUUIDs[answerName]) return uuid;
  answerUUIDs[answerName] = uuid;
  
  allConcepts.push({
    name: answerName.trim(),
    uuid: uuid,
    dataType: 'NA',
    active: true
  });
  
  return uuid;
}

function createConcept(name, dataType, options, minMax, unit) {
  const conceptUUID = getConceptUUID(name);
  
  // Check if already exists
  if (allConcepts.some(c => c.uuid === conceptUUID)) return conceptUUID;
  
  const concept = {
    name: name,
    uuid: conceptUUID,
    dataType: dataType,
    active: true
  };
  
  if (dataType === 'Coded' && options.length > 0) {
    // Add Yes/No if not in options for single select
    const processedOptions = [...options];
    
    concept.answers = processedOptions.map((opt, idx) => ({
      name: opt.trim(),
      uuid: createAnswerConcept(opt),
      order: idx
    }));
  }
  
  if (dataType === 'Numeric') {
    if (minMax.min !== null) concept.lowAbsolute = minMax.min;
    if (minMax.max !== null) concept.highAbsolute = minMax.max;
    if (unit) concept.unit = unit.toString().trim();
  }
  
  allConcepts.push(concept);
  return conceptUUID;
}

// Parse skip logic conditions
function parseSkipLogic(whenToShow, whenNotToShow) {
  if (!whenToShow && !whenNotToShow) return null;
  
  const conditions = [];
  
  if (whenToShow && whenToShow.trim()) {
    conditions.push({ type: 'show', condition: whenToShow.trim() });
  }
  if (whenNotToShow && whenNotToShow.trim()) {
    conditions.push({ type: 'hide', condition: whenNotToShow.trim() });
  }
  
  return conditions.length > 0 ? conditions : null;
}

// Process a form sheet
function processFormSheet(sheetName, rows) {
  console.log(`\n📋 Processing: ${sheetName}`);
  
  const formElements = [];
  let currentGroup = 'General Information';
  let displayOrder = 1;
  let skippedHeader = false;
  
  for (const row of rows) {
    // Skip header row (where Field Name = "Field Name")
    const fieldName = row[COLUMN_MAP.fieldName];
    if (!fieldName || fieldName === 'Field Name') {
      skippedHeader = true;
      continue;
    }
    
    // Get field info
    const pageName = row[COLUMN_MAP.pageName];
    const dataTypeRaw = row[COLUMN_MAP.dataType];
    const mandatory = ['yes', 'y', 'true', '1'].includes(
      (row[COLUMN_MAP.mandatory] || '').toString().toLowerCase()
    );
    const selectionType = row[COLUMN_MAP.selectionType];
    const optionsRaw = row[COLUMN_MAP.options];
    const minMaxRaw = row[COLUMN_MAP.minMaxLimit];
    const unit = row[COLUMN_MAP.unit];
    const whenToShow = row[COLUMN_MAP.whenToShow];
    const whenNotToShow = row[COLUMN_MAP.whenNotToShow];
    
    // Update current group if page name given
    if (pageName && pageName.trim() && pageName !== 'Page Name') {
      currentGroup = pageName.trim();
    }
    
    // Determine data type
    const options = parseOptions(optionsRaw);
    const dataType = mapDataType(dataTypeRaw, selectionType);
    const minMax = parseMinMax(minMaxRaw);
    
    // Create concept
    const conceptUUID = createConcept(fieldName.trim(), dataType, options, minMax, unit);
    
    // Create form element
    const element = {
      name: fieldName.trim(),
      uuid: generateDeterministicUUID(`element:${sheetName}:${fieldName}:${displayOrder}`),
      keyValues: [],
      concept: {
        name: fieldName.trim(),
        uuid: conceptUUID,
        dataType: dataType,
        active: true
      },
      displayOrder: displayOrder++,
      type: dataType === 'Coded' && (selectionType || '').toLowerCase().includes('multi') ? 'MultiSelect' : 'SingleSelect',
      mandatory: mandatory,
      _group: currentGroup
    };
    
    // Add skip logic info
    const skipLogic = parseSkipLogic(whenToShow, whenNotToShow);
    if (skipLogic) {
      element._skipLogic = skipLogic;
    }
    
    formElements.push(element);
    console.log(`   ✓ ${fieldName.trim()} (${dataType}${mandatory ? ' *' : ''})`);
  }
  
  return formElements;
}

// Group elements
function groupElements(elements) {
  const groups = {};
  elements.forEach(el => {
    const groupName = el._group || 'General Information';
    if (!groups[groupName]) groups[groupName] = [];
    delete el._group;
    groups[groupName].push(el);
  });
  return groups;
}

// Generate form
function generateForm(formName, elements, formType) {
  const formUUID = generateDeterministicUUID(`form:${formName}`);
  const grouped = groupElements(elements);
  
  let groupOrder = 1;
  const formElementGroups = Object.entries(grouped).map(([groupName, groupElements]) => ({
    uuid: generateDeterministicUUID(`group:${formName}:${groupName}`),
    name: groupName,
    displayOrder: groupOrder++,
    formElements: groupElements.map((el, i) => {
      el.displayOrder = i + 1;
      delete el._skipLogic;  // Remove internal data
      return el;
    }),
    timed: false
  }));
  
  return {
    name: formName,
    uuid: formUUID,
    formType: formType,
    formElementGroups: formElementGroups,
    decisionRule: '',
    visitScheduleRule: '',
    validationRule: '',
    checklistsRule: '',
    decisionConcepts: []
  };
}

// Determine form type from sheet name
function getFormType(sheetName) {
  const name = sheetName.toLowerCase();
  if (name.includes('registration') && !name.includes('group') && !name.includes('meeting')) return 'IndividualProfile';
  if (name.includes('enrollment') || name.includes('enrolment')) return 'ProgramEnrolment';
  if (name.includes('exit')) return 'ProgramExit';
  if (name.includes('cancellation')) return 'ProgramEncounterCancellation';
  if (name.includes('group registration') || name.includes('meeting registration')) return 'IndividualProfile';
  return 'ProgramEncounter';
}

// Main
async function main() {
  console.log('🚀 PAD Adolescent Forms Bundle Generator v2');
  console.log('============================================\n');
  
  // Parse Excel
  console.log(`📖 Reading: ${INPUT_FILE}`);
  const workbook = XLSX.readFile(INPUT_FILE);
  console.log(`   Found ${workbook.SheetNames.length} sheets\n`);
  
  // Sheets to skip
  const skipSheets = ['Other Important Document', 'Reports', 'Offline Dashboard Cards'];
  
  const forms = [];
  const encounterTypes = [];
  
  for (const sheetName of workbook.SheetNames) {
    if (skipSheets.includes(sheetName)) {
      console.log(`⏭️  Skipping: ${sheetName}`);
      continue;
    }
    
    const sheet = workbook.Sheets[sheetName];
    const rows = XLSX.utils.sheet_to_json(sheet, { defval: '' });
    
    if (rows.length <= 1) continue;  // Skip empty or header-only
    
    const formType = getFormType(sheetName);
    const elements = processFormSheet(sheetName, rows);
    
    if (elements.length > 0) {
      const form = generateForm(sheetName.trim(), elements, formType);
      forms.push(form);
      
      // Create encounter type for program encounters
      if (formType === 'ProgramEncounter') {
        encounterTypes.push({
          name: sheetName.trim(),
          uuid: generateDeterministicUUID(`encounterType:${sheetName}`),
          active: true,
          programEncounter: true
        });
      }
    }
  }
  
  // Sort concepts
  allConcepts.sort((a, b) => {
    if (a.dataType === 'NA' && b.dataType !== 'NA') return -1;
    if (a.dataType !== 'NA' && b.dataType === 'NA') return 1;
    return a.name.localeCompare(b.name);
  });
  
  // Create output
  if (!fs.existsSync(OUTPUT_DIR)) {
    fs.mkdirSync(OUTPUT_DIR, { recursive: true });
  }
  const formsDir = path.join(OUTPUT_DIR, 'forms');
  if (!fs.existsSync(formsDir)) {
    fs.mkdirSync(formsDir);
  }
  
  // Write concepts
  fs.writeFileSync(path.join(OUTPUT_DIR, 'concepts.json'), JSON.stringify(allConcepts, null, 2));
  
  // Write forms
  forms.forEach(form => {
    fs.writeFileSync(path.join(formsDir, `${form.name}.json`), JSON.stringify(form, null, 2));
  });
  
  // Subject types
  const subjectTypes = [
    { name: 'Adolescent', uuid: generateDeterministicUUID('subjectType:Adolescent'), type: 'Person', active: true },
    { name: 'Adolescent Group', uuid: generateDeterministicUUID('subjectType:Adolescent Group'), type: 'Group', active: true },
    { name: 'Community Support Group', uuid: generateDeterministicUUID('subjectType:Community Support Group'), type: 'Group', active: true },
    { name: 'Meeting', uuid: generateDeterministicUUID('subjectType:Meeting'), type: 'Group', active: true }
  ];
  fs.writeFileSync(path.join(OUTPUT_DIR, 'subjectTypes.json'), JSON.stringify(subjectTypes, null, 2));
  
  // Programs
  const programs = [{
    name: 'PAD Adolescent Program',
    uuid: generateDeterministicUUID('program:PAD Adolescent Program'),
    colour: '#E91E63',
    programSubjectLabel: 'Adolescent',
    active: true
  }];
  fs.writeFileSync(path.join(OUTPUT_DIR, 'programs.json'), JSON.stringify(programs, null, 2));
  
  // Encounter types
  fs.writeFileSync(path.join(OUTPUT_DIR, 'encounterTypes.json'), JSON.stringify(encounterTypes, null, 2));
  
  // Form mappings
  const formMappings = forms.map(form => {
    const mapping = {
      uuid: generateDeterministicUUID(`mapping:${form.name}`),
      formUUID: form.uuid,
      formType: form.formType,
      formName: form.name,
      subjectTypeUUID: subjectTypes[0].uuid,
      enableApproval: false
    };
    
    if (form.formType !== 'IndividualProfile') {
      mapping.programUUID = programs[0].uuid;
    }
    
    if (form.formType === 'ProgramEncounter') {
      const et = encounterTypes.find(e => e.name === form.name);
      if (et) mapping.encounterTypeUUID = et.uuid;
    }
    
    return mapping;
  });
  fs.writeFileSync(path.join(OUTPUT_DIR, 'formMappings.json'), JSON.stringify(formMappings, null, 2));
  
  // Summary
  console.log('\n' + '═'.repeat(50));
  console.log('📊 GENERATION COMPLETE');
  console.log('═'.repeat(50));
  console.log(`   Concepts: ${allConcepts.length}`);
  console.log(`      - NA (Answers): ${allConcepts.filter(c => c.dataType === 'NA').length}`);
  console.log(`      - Coded: ${allConcepts.filter(c => c.dataType === 'Coded').length}`);
  console.log(`      - Numeric: ${allConcepts.filter(c => c.dataType === 'Numeric').length}`);
  console.log(`      - Text: ${allConcepts.filter(c => c.dataType === 'Text').length}`);
  console.log(`      - Date: ${allConcepts.filter(c => c.dataType === 'Date').length}`);
  console.log(`   Forms: ${forms.length}`);
  console.log(`   Encounter Types: ${encounterTypes.length}`);
  console.log(`   Subject Types: ${subjectTypes.length}`);
  console.log(`   Programs: 1`);
  console.log('═'.repeat(50));
  console.log(`📁 Output: ${OUTPUT_DIR}`);
  console.log('\n🎉 Bundle generated successfully!');
}

main().catch(console.error);

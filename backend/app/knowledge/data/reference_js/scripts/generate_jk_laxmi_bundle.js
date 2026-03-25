#!/usr/bin/env node
/**
 * JK Laxmi Cements Bundle Generator
 * Deep analysis of SRS + Forms to generate complete AVNI bundle
 */

const XLSX = require('xlsx');
const fs = require('fs');
const path = require('path');
const { v4: uuidv4 } = require('uuid');

const SRS_FILE = '/Users/samanvay/Downloads/All/avni-ai/srs/JK Laxmi Cements SRS .xlsx';
const FORMS_FILE = '/Users/samanvay/Downloads/All/avni-ai/srs/JK Laxmi Cements Forms.xlsx';
const OUTPUT_DIR = '/Users/samanvay/Downloads/All/avni-ai/avni-skills/srs-bundle-generator/output/JK-Laxmi-Cements';
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

// Column mapping for JK Laxmi format
const COLUMN_MAP = {
  pageName: 0,      // Column A
  fieldName: 1,     // Column B
  dataType: 2,      // Column C
  mandatory: 3,     // Column D
  userOrSystem: 4,  // Column E
  allowNegative: 5, // Column F
  allowDecimal: 6,  // Column G
  minMaxLimit: 7,   // Column H
  unit: 8,          // Column I
  allowCurrentDate: 9,
  allowFutureDate: 10,
  allowPastDate: 11,
  selectionType: 12, // Column M - Single/Multi select
  options: 13,       // Column N
  uniqueOption: 14,
  validation: 15,    // Column P - validation/condition
  showCondition: 16  // Column Q - when to show
};

// Alternate structure (some sheets have different format)
const ALT_COLUMN_MAP = {
  pageName: 0,
  fieldName: 1,
  dataType: 2,
  options: 3,
  mandatory: 4,
  userOrSystem: 5,
  showCondition: 6,
  hideCondition: 7
};

// Map data type
function mapDataType(typeStr, selectionType, options) {
  if (!typeStr) return 'Text';
  const type = typeStr.toString().toLowerCase().trim();
  
  if (type.includes('pre added') || type.includes('single select') || type.includes('multi select')) return 'Coded';
  if (type.includes('numeric') || type.includes('number')) return 'Numeric';
  if (type.includes('date') && !type.includes('time')) return 'Date';
  if (type.includes('datetime')) return 'DateTime';
  if (type.includes('text') || type.includes('alpha')) return 'Text';
  if (type.includes('notes') || type.includes('paragraph')) return 'Notes';
  if (type.includes('media') || type.includes('image') || type.includes('photo')) return 'ImageV2';
  if (type.includes('id')) return 'Id';
  if (type.includes('location')) return 'Location';
  
  // Check selection type
  if (selectionType) {
    const sel = selectionType.toString().toLowerCase();
    if (sel.includes('single') || sel.includes('multi')) return 'Coded';
  }
  
  // Check if has options
  if (options && options.length > 0) return 'Coded';
  
  return 'Text';
}

// Parse options
function parseOptions(optionsStr) {
  if (!optionsStr) return [];
  const str = optionsStr.toString().trim();
  if (!str) return [];
  
  // Handle different delimiters
  let options;
  if (str.includes('\n')) {
    options = str.split('\n');
  } else if (str.includes(';')) {
    options = str.split(';');
  } else if (str.includes(',')) {
    options = str.split(',');
  } else {
    options = [str];
  }
  
  return options
    .map(o => o.trim())
    .filter(o => o.length > 0 && !o.match(/^\d+\.\s*$/));
}

// Parse min/max
function parseMinMax(str) {
  if (!str) return { min: null, max: null };
  const s = str.toString().trim();
  
  const rangeMatch = s.match(/(\d+(?:\.\d+)?)\s*[-–to]\s*(\d+(?:\.\d+)?)/i);
  if (rangeMatch) {
    return { min: parseFloat(rangeMatch[1]), max: parseFloat(rangeMatch[2]) };
  }
  
  return { min: null, max: null };
}

// Detect which column mapping to use
function detectColumnMapping(row) {
  if (!row || row.length < 3) return null;
  
  const col2 = (row[2] || '').toString().toLowerCase();
  const col3 = (row[3] || '').toString().toLowerCase();
  
  // If column 3 has options (like "BCG;OPV0..."), it's alternate format
  if (col3.includes(';') || col3.includes('\n')) {
    return ALT_COLUMN_MAP;
  }
  
  return COLUMN_MAP;
}

// Concept and answer storage
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
  
  if (allConcepts.some(c => c.uuid === conceptUUID)) return conceptUUID;
  
  const concept = {
    name: name,
    uuid: conceptUUID,
    dataType: dataType,
    active: true
  };
  
  if (dataType === 'Coded' && options.length > 0) {
    concept.answers = options.map((opt, idx) => ({
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

// Process form sheet
function processFormSheet(sheetName, data) {
  console.log(`\n📋 Processing: ${sheetName}`);
  
  if (data.length < 2) {
    console.log('   ⏭️ Skipping (too few rows)');
    return null;
  }
  
  const formElements = [];
  let currentGroup = 'General';
  let displayOrder = 1;
  
  // Detect column mapping from first data row
  let colMap = COLUMN_MAP;
  if (data.length > 1) {
    colMap = detectColumnMapping(data[1]) || COLUMN_MAP;
  }
  
  for (let i = 1; i < data.length; i++) {
    const row = data[i];
    if (!row || !Array.isArray(row)) continue;
    
    const fieldName = row[colMap.fieldName];
    if (!fieldName || typeof fieldName !== 'string' || fieldName.trim() === '') continue;
    if (fieldName.toLowerCase().includes('field name')) continue; // Skip header
    
    const pageName = row[colMap.pageName];
    const dataTypeRaw = row[colMap.dataType];
    const selectionType = row[colMap.selectionType];
    const optionsRaw = row[colMap.options];
    const mandatory = ['yes', 'y', 'true', '1'].includes(
      (row[colMap.mandatory] || '').toString().toLowerCase().trim()
    );
    const minMaxRaw = row[colMap.minMaxLimit];
    const unit = row[colMap.unit];
    const showCondition = row[colMap.showCondition];
    
    // Update group
    if (pageName && pageName.trim() && typeof pageName === 'string') {
      currentGroup = pageName.trim();
    }
    
    // Parse and create concept
    const options = parseOptions(optionsRaw);
    const dataType = mapDataType(dataTypeRaw, selectionType, options);
    const minMax = parseMinMax(minMaxRaw);
    
    const conceptUUID = createConcept(fieldName.trim(), dataType, options, minMax, unit);
    
    // Determine element type
    let elementType = 'SingleSelect';
    if (selectionType && selectionType.toString().toLowerCase().includes('multi')) {
      elementType = 'MultiSelect';
    }
    
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
      type: elementType,
      mandatory: mandatory,
      _group: currentGroup
    };
    
    // Store skip logic for later processing
    if (showCondition && showCondition.trim()) {
      element._skipLogic = showCondition.trim();
    }
    
    formElements.push(element);
    console.log(`   ✓ ${fieldName.trim().substring(0, 40)} (${dataType}${mandatory ? ' *' : ''})`);
  }
  
  return formElements;
}

// Group elements
function groupElements(elements) {
  const groups = {};
  elements.forEach(el => {
    const groupName = el._group || 'General';
    if (!groups[groupName]) groups[groupName] = [];
    delete el._group;
    delete el._skipLogic;
    groups[groupName].push(el);
  });
  return groups;
}

// Generate form JSON
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

// Determine form type
function getFormType(sheetName) {
  const name = sheetName.toLowerCase();
  if (name.includes('individual') && name.includes('registration')) return 'IndividualProfile';
  if (name.includes('enrolment') || name.includes('enrollment')) return 'ProgramEnrolment';
  if (name.includes('exit')) return 'ProgramExit';
  if (name.includes('cancellation')) return 'ProgramEncounterCancellation';
  return 'ProgramEncounter';
}

// Determine which program a form belongs to
function getProgram(sheetName) {
  const name = sheetName.toLowerCase();
  if (name.includes('anc') || name.includes('pnc') || name.includes('delivery') || 
      name.includes('pregnancy') || name.includes('family planning')) {
    return 'Maternal Health';
  }
  if (name.includes('child') || name.includes('immunization') || name.includes('hbnc')) {
    return 'Child Health';
  }
  return 'General Health';
}

// Main
async function main() {
  console.log('🚀 JK Laxmi Cements Bundle Generator');
  console.log('=====================================\n');
  
  // Read Forms file (primary source)
  console.log(`📖 Reading Forms: ${path.basename(FORMS_FILE)}`);
  const formsWorkbook = XLSX.readFile(FORMS_FILE);
  console.log(`   Found ${formsWorkbook.SheetNames.length} sheets`);
  
  // Read SRS for modeling info
  console.log(`📖 Reading SRS: ${path.basename(SRS_FILE)}`);
  const srsWorkbook = XLSX.readFile(SRS_FILE);
  
  // Sheets to skip
  const skipSheets = ['Modelling', 'Summary - PW', 'Offline Dashboard', 'Visit Schedule'];
  
  const forms = [];
  const encounterTypes = [];
  const programs = new Map();
  
  // Process forms
  for (const sheetName of formsWorkbook.SheetNames) {
    if (skipSheets.some(s => sheetName.includes(s))) {
      console.log(`⏭️  Skipping: ${sheetName}`);
      continue;
    }
    
    const sheet = formsWorkbook.Sheets[sheetName];
    const data = XLSX.utils.sheet_to_json(sheet, { defval: '', header: 1 });
    
    const formType = getFormType(sheetName);
    const programName = getProgram(sheetName);
    const elements = processFormSheet(sheetName, data);
    
    if (elements && elements.length > 0) {
      const form = generateForm(sheetName.trim(), elements, formType);
      forms.push({ form, programName });
      
      // Track programs
      if (!programs.has(programName)) {
        programs.set(programName, {
          name: programName,
          uuid: generateDeterministicUUID(`program:${programName}`),
          colour: programName === 'Maternal Health' ? '#E91E63' : 
                  programName === 'Child Health' ? '#4CAF50' : '#2196F3',
          active: true
        });
      }
      
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
  
  // Write outputs
  fs.writeFileSync(path.join(OUTPUT_DIR, 'concepts.json'), JSON.stringify(allConcepts, null, 2));
  
  forms.forEach(({ form }) => {
    fs.writeFileSync(path.join(formsDir, `${form.name}.json`), JSON.stringify(form, null, 2));
  });
  
  // Subject types
  const subjectTypes = [
    { name: 'Individual', uuid: generateDeterministicUUID('subjectType:Individual'), type: 'Person', active: true },
    { name: 'Household', uuid: generateDeterministicUUID('subjectType:Household'), type: 'Household', active: true }
  ];
  fs.writeFileSync(path.join(OUTPUT_DIR, 'subjectTypes.json'), JSON.stringify(subjectTypes, null, 2));
  
  // Programs
  const programsList = Array.from(programs.values());
  fs.writeFileSync(path.join(OUTPUT_DIR, 'programs.json'), JSON.stringify(programsList, null, 2));
  
  // Encounter types
  fs.writeFileSync(path.join(OUTPUT_DIR, 'encounterTypes.json'), JSON.stringify(encounterTypes, null, 2));
  
  // Form mappings
  const formMappings = forms.map(({ form, programName }) => {
    const program = programs.get(programName);
    const mapping = {
      uuid: generateDeterministicUUID(`mapping:${form.name}`),
      formUUID: form.uuid,
      formType: form.formType,
      formName: form.name,
      subjectTypeUUID: subjectTypes[0].uuid,
      enableApproval: false
    };
    
    if (form.formType !== 'IndividualProfile') {
      mapping.programUUID = program.uuid;
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
  console.log(`   Programs: ${programsList.length}`);
  console.log(`   Encounter Types: ${encounterTypes.length}`);
  console.log(`   Subject Types: ${subjectTypes.length}`);
  console.log('═'.repeat(50));
  console.log(`📁 Output: ${OUTPUT_DIR}`);
  console.log('\n🎉 Bundle generated successfully!');
}

main().catch(console.error);

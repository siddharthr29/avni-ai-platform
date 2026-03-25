#!/usr/bin/env node
/**
 * Mazi Saheli Charitable Trust Bundle Generator
 *
 * Generates complete AVNI bundle from the SRS Excel file.
 *
 * Subject Types:
 *   - Activity (Individual)
 *   - Participant (Person)
 *
 * Forms:
 *   - Activity Registration
 *   - Participant Registration
 *   - Assessment & Distribution
 *   - Activity Summary
 *
 * Usage:
 *   node scripts/generate_mazi_saheli_bundle.js
 */

const XLSX = require('xlsx');
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

// ═══════════════════════════════════════════════════════════════════════════
// CONFIGURATION
// ═══════════════════════════════════════════════════════════════════════════

const INPUT_FILE = path.join(__dirname, '..', 'Mazi Saheli Charitable Trust Scoping .xlsx');
const OUTPUT_DIR = path.join(__dirname, '..', 'output', 'Mazi-Saheli');

// Column mapping for this SRS format (using array indices)
const COLUMN_MAP = {
  pageName: 0,
  fieldName: 1,
  dataType: 2,
  mandatory: 3,
  userSystem: 4,
  allowNegative: 5,
  allowDecimal: 6,
  minMaxLimit: 7,
  unit: 8,
  allowCurrentDate: 9,
  allowFutureDate: 10,
  allowPastDate: 11,
  selectionType: 12,
  options: 13,
  uniqueOption: 14,
  optionCondition: 15,
  whenToShow: 16,
  whenNotToShow: 17
};

// Sheets to skip (metadata/non-form sheets)
const SKIP_SHEETS = [
  'Other Important links',
  'Project Summary',
  'User Persona',
  'W3H',
  'App Dashboard',
  'Visit Scheduling',
  'Reports',
  'Permissions',
  'Review checklist'
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

  // Community types
  'Rural': 'rural123-4567-89ab-cdef-0123456789ab',
  'Tribal': 'tribal12-3456-789a-bcde-f0123456789a',
  'Urban': 'urban123-4567-89ab-cdef-0123456789ab',
};

// Exclusive options that need unique: true in multi-select
const EXCLUSIVE_OPTIONS = ['None', 'NA', 'N/A', 'Not Applicable'];

// Normal ranges for common vitals/measurements
const NORMAL_RANGES = {
  'Weight': { lowAbsolute: 0, highAbsolute: 300, unit: 'kg' },
  'Height': { lowAbsolute: 0, highAbsolute: 250, unit: 'cm' },
  'Age': { lowAbsolute: 0, highAbsolute: 120, unit: 'years' },
};

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
    .map(o => o.replace(/^\d+\.\s*/, '')) // Remove leading numbers like "1. "
    .map(o => o.replace(/,+$/, ''))       // Strip trailing commas
    .map(o => o.trim())                   // Trim again after comma removal
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
  if (type.includes('auto')) return 'Numeric';

  return 'Text';
}

function getFormType(sheetName) {
  const name = sheetName.toLowerCase();
  
  if (name.includes('registration')) return 'IndividualProfile';
  if (name.includes('enrol')) return 'ProgramEnrolment';
  if (name.includes('exit')) return 'ProgramExit';
  if (name.includes('cancellation')) return 'ProgramEncounterCancellation';
  
  return 'Encounter'; // Default to general encounter
}

function getSubjectType(sheetName) {
  const name = sheetName.toLowerCase();
  
  if (name.includes('activity')) return 'Activity';
  if (name.includes('participant')) return 'Participant';
  
  return 'Participant'; // Default
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

// ═══════════════════════════════════════════════════════════════════════════
// MAIN GENERATOR CLASS
// ═══════════════════════════════════════════════════════════════════════════

class MaziSaheliBundleGenerator {
  constructor() {
    this.concepts = new Map();
    this.answers = new Map();
    this.forms = [];
    this.encounterTypes = new Map();
    this.subjectTypes = new Map();
    this.formMappings = [];
    this.conceptUuidMap = {};
  }

  generate() {
    console.log('\n🌟 Mazi Saheli Charitable Trust Bundle Generator');
    console.log('═'.repeat(60));
    console.log(`   Input: ${path.basename(INPUT_FILE)}`);
    console.log(`   Output: ${OUTPUT_DIR}`);
    console.log('═'.repeat(60) + '\n');

    // Create output directories
    fs.mkdirSync(OUTPUT_DIR, { recursive: true });
    fs.mkdirSync(path.join(OUTPUT_DIR, 'forms'), { recursive: true });

    // Read Excel file
    console.log(`📖 Reading Excel file...`);
    const workbook = XLSX.readFile(INPUT_FILE);
    console.log(`   Found ${workbook.SheetNames.length} sheets\n`);

    // Initialize subject types
    this.initializeSubjectTypes();

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
    // Note: 'activity summary' is a valid form sheet, skip only 'project summary'
    return name.includes('dashboard') ||
           name.includes('report') ||
           name.includes('permission') ||
           name.includes('important') ||
           (name.includes('summary') && !name.includes('activity summary')) ||
           name.includes('persona') ||
           name.includes('w3h') ||
           name.includes('visit scheduling') ||
           name.includes('review');
  }

  resolveSubjectTypeForField(fieldName) {
    // Match field name to a known subject type
    // e.g. field "Activity" → subject type "Activity"
    const directMatch = this.subjectTypes.get(fieldName);
    if (directMatch) return directMatch;

    // Fuzzy: check if field name contains a subject type name
    for (const [stName, st] of this.subjectTypes) {
      if (fieldName.toLowerCase().includes(stName.toLowerCase())) {
        return st;
      }
    }
    return null;
  }

  initializeSubjectTypes() {
    // Activity (Individual type)
    this.subjectTypes.set('Activity', {
      name: 'Activity',
      uuid: generateUUID('subject-Activity'),
      active: true,
      type: 'Individual',
      allowMiddleName: false,
      allowProfilePicture: true,
      shouldSyncByLocation: true,
      settings: {
        displayRegistrationDetails: true,
        displayPlannedEncounters: true
      },
      voided: false
    });

    // Participant (Person type)
    this.subjectTypes.set('Participant', {
      name: 'Participant',
      uuid: generateUUID('subject-Participant'),
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
  }

  processSheet(sheet, sheetName) {
    // Use header: 1 to get array format instead of object format
    const data = XLSX.utils.sheet_to_json(sheet, { header: 1, defval: '' });
    if (data.length <= 2) {
      console.log('   ⚠️ Empty or header-only sheet');
      return;
    }

    // Skip first 2 rows (header rows)
    const rows = data.slice(2);

    const formName = sheetName.trim();
    const formUuid = generateUUID(`form-${formName}`);
    const formType = getFormType(formName);
    const subjectType = getSubjectType(formName);

    console.log(`   Form Type: ${formType}`);
    console.log(`   Subject Type: ${subjectType}`);

    // Detect column shift: some sheets have selection type in col 13 and options
    // in col 14 instead of col 12/13, due to merged header cells in the SRS.
    const firstDataRow = rows.find(r => r && String(r[COLUMN_MAP.fieldName] || '').trim().length >= 2);
    const hasColumnShift = firstDataRow &&
      !String(firstDataRow[COLUMN_MAP.selectionType] || '').trim() &&
      String(firstDataRow[COLUMN_MAP.options] || '').toLowerCase().includes('select');

    const OPTIONS_COL = hasColumnShift ? 14 : COLUMN_MAP.options;
    const SELECTION_COL = hasColumnShift ? 13 : COLUMN_MAP.selectionType;
    const UNIQUE_OPT_COL = hasColumnShift ? 15 : COLUMN_MAP.uniqueOption;
    if (hasColumnShift) {
      console.log('   ℹ️  Detected column shift: selectionType=col13, options=col14');
    }

    const formElementGroups = [];
    let currentGroup = null;
    let groupOrder = 0;
    let elementOrder = 0;

    for (const row of rows) {
      // Skip empty rows
      if (!row || row.length === 0) continue;
      
      const fieldName = String(row[COLUMN_MAP.fieldName] || '').trim();
      if (!fieldName || fieldName.length < 2 || fieldName.toLowerCase() === 'field name') continue;

      const pageName = String(row[COLUMN_MAP.pageName] || 'General').trim() || 'General';
      const dataType = String(row[COLUMN_MAP.dataType] || 'Text').trim();
      const mandatory = String(row[COLUMN_MAP.mandatory] || '').toLowerCase().includes('yes');
      const options = parseOptions(row[OPTIONS_COL]);
      const selectionType = String(row[SELECTION_COL] || '').toLowerCase();
      const unit = row[COLUMN_MAP.unit];
      const minMaxLimit = row[COLUMN_MAP.minMaxLimit];
      const uniqueOption = row[UNIQUE_OPT_COL];

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
      
      // Check if this field name already exists as an answer - reuse that UUID
      let conceptUuid;
      if (this.answers.has(fieldName)) {
        conceptUuid = this.answers.get(fieldName).uuid;
        console.log(`   ℹ️  Reusing answer UUID for question: ${fieldName}`);
      } else {
        conceptUuid = generateUUID(`concept-${fieldName}`);
      }
      this.conceptUuidMap[fieldName] = conceptUuid;

      // Create concept
      const concept = {
        name: fieldName,
        uuid: conceptUuid,
        dataType: conceptDataType,
        active: true
      };

      // Add keyValues for Subject dataType (links to a subject type)
      if (conceptDataType === 'Subject') {
        const referencedSubjectType = this.resolveSubjectTypeForField(fieldName);
        if (referencedSubjectType) {
          concept.keyValues = [{
            key: 'subjectTypeUUID',
            value: referencedSubjectType.uuid
          }];
        }
      }

      // Add numeric properties
      if (conceptDataType === 'Numeric') {
        const normalRange = NORMAL_RANGES[fieldName];
        if (normalRange) {
          Object.assign(concept, normalRange);
        } else {
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

          // Store answer concept (avoid duplicates with question concepts)
          if (!this.answers.has(opt) && !this.concepts.has(opt)) {
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

      // Only add to concepts if not already added as an answer
      if (!this.concepts.has(fieldName) && !this.answers.has(fieldName)) {
        this.concepts.set(fieldName, concept);
      } else if (!this.concepts.has(fieldName)) {
        // If it exists as an answer, update it to be a question concept
        this.answers.delete(fieldName);
        this.concepts.set(fieldName, concept);
      }

      // Create form element
      elementOrder++;
      const isMultiSelect = selectionType.includes('multi');

      // Build concept object for form element
      const formConcept = {
        name: fieldName,
        uuid: conceptUuid,
        dataType: conceptDataType,
        answers: concept.answers || [],
        active: true,
        media: []
      };

      // Carry keyValues (e.g. subjectTypeUUID) into form element concept
      if (concept.keyValues) {
        formConcept.keyValues = concept.keyValues;
      }

      const formElement = {
        name: fieldName,
        uuid: generateUUID(`fe-${formName}-${fieldName}-${elementOrder}`),
        keyValues: [],
        concept: formConcept,
        displayOrder: elementOrder,
        type: isMultiSelect ? 'MultiSelect' : 'SingleSelect',
        mandatory: mandatory
      };

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
    if (formType === 'Encounter') {
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
                              this.subjectTypes.get('Participant').uuid;

    // Add encounter type for encounters
    if (formType === 'Encounter') {
      mapping.encounterTypeUUID = generateUUID(`encounter-${formName}`);
    }

    this.formMappings.push(mapping);
  }

  writeAllFiles() {
    console.log('\n📁 Writing output files...');

    // 1. Write concepts (deduplicate by name)
    const conceptMap = new Map();
    
    // Add answers first (they have priority as NA type)
    for (const [name, concept] of this.answers) {
      conceptMap.set(name, concept);
    }
    
    // Add questions (will override answers if same name)
    for (const [name, concept] of this.concepts) {
      conceptMap.set(name, concept);
    }
    
    const allConcepts = Array.from(conceptMap.values());
    fs.writeFileSync(
      path.join(OUTPUT_DIR, 'concepts.json'),
      JSON.stringify(allConcepts, null, 2)
    );
    console.log(`   ✓ concepts.json (${allConcepts.length} concepts)`);

    // Build set of UUIDs already present in forms dir (from server download)
    const existingFormUuids = new Set();
    const formsDir = path.join(OUTPUT_DIR, 'forms');
    if (fs.existsSync(formsDir)) {
      for (const f of fs.readdirSync(formsDir)) {
        const match = f.match(/_([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{8,12})\.json$/i);
        if (match) existingFormUuids.add(match[1]);
      }
    }

    // 2. Write forms (using {name}_{uuid}.json convention)
    let formsWritten = 0;
    let formsSkipped = 0;
    for (const form of this.forms) {
      if (existingFormUuids.has(form.uuid)) {
        console.log(`   ⏭️  ${form.name} (UUID already in output, skipping)`);
        formsSkipped++;
        continue;
      }
      fs.writeFileSync(
        path.join(OUTPUT_DIR, 'forms', `${form.name}_${form.uuid}.json`),
        JSON.stringify(form, null, 2)
      );
      formsWritten++;
    }
    console.log(`   ✓ forms/ (${formsWritten} written, ${formsSkipped} skipped — already in output)`);

    // 3. Write cancellation forms
    let cancellationCount = 0;
    for (const [name, et] of this.encounterTypes) {
      const cancellationForm = {
        name: `${name} Cancellation`,
        uuid: generateUUID(`form-cancel-${name}`),
        formType: 'IndividualEncounterCancellation',
        formElementGroups: [],
        decisionRule: '',
        visitScheduleRule: '',
        validationRule: '',
        checklistsRule: '',
        decisionConcepts: []
      };
      if (existingFormUuids.has(cancellationForm.uuid)) {
        console.log(`   ⏭️  ${cancellationForm.name} (UUID already in output, skipping)`);
      } else {
        fs.writeFileSync(
          path.join(OUTPUT_DIR, 'forms', `${cancellationForm.name}_${cancellationForm.uuid}.json`),
          JSON.stringify(cancellationForm, null, 2)
        );
      }
      cancellationCount++;

      // Add cancellation form mapping
      const subjectType = getSubjectType(name);
      const mapping = {
        uuid: generateUUID(`mapping-cancel-${name}`),
        formUUID: cancellationForm.uuid,
        subjectTypeUUID: this.subjectTypes.get(subjectType)?.uuid || this.subjectTypes.get('Participant').uuid,
        formType: 'IndividualEncounterCancellation',
        formName: cancellationForm.name,
        encounterTypeUUID: et.uuid,
        enableApproval: false,
        isVoided: false
      };
      this.formMappings.push(mapping);
    }
    console.log(`   ✓ cancellation forms (${cancellationCount} forms)`);

    // 4. Write subject types
    fs.writeFileSync(
      path.join(OUTPUT_DIR, 'subjectTypes.json'),
      JSON.stringify(Array.from(this.subjectTypes.values()), null, 2)
    );
    console.log(`   ✓ subjectTypes.json (${this.subjectTypes.size} types)`);

    // 5. Write programs.json (empty for non-program implementation)
    fs.writeFileSync(
      path.join(OUTPUT_DIR, 'programs.json'),
      JSON.stringify([], null, 2)
    );
    console.log(`   ✓ programs.json (0 programs - non-program implementation)`);

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

    // 10. Write sample locations CSV
    this.writeSampleLocations();

    // 11. Write groups and privileges
    this.writeGroupsAndPrivileges();

    // 12. Write standard report cards
    this.writeReportCards();
  }

  writeOperationalConfigs() {
    // Operational Encounter Types - wrapped in contract object
    const opEncounters = Array.from(this.encounterTypes.values()).map(et => ({
      encounterType: { uuid: et.uuid, name: et.name },
      uuid: generateUUID(`op-enc-${et.name}`),
      name: et.name,
      voided: false
    }));
    const operationalEncounterTypesContract = {
      operationalEncounterTypes: opEncounters
    };
    fs.writeFileSync(
      path.join(OUTPUT_DIR, 'operationalEncounterTypes.json'),
      JSON.stringify(operationalEncounterTypesContract, null, 2)
    );
    console.log(`   ✓ operationalEncounterTypes.json`);

    // Operational Subject Types - wrapped in contract object
    const opSubjects = Array.from(this.subjectTypes.values()).map(st => ({
      subjectType: { uuid: st.uuid, name: st.name },
      uuid: generateUUID(`op-subject-${st.name}`),
      name: st.name,
      voided: false
    }));
    const operationalSubjectTypesContract = {
      operationalSubjectTypes: opSubjects
    };
    fs.writeFileSync(
      path.join(OUTPUT_DIR, 'operationalSubjectTypes.json'),
      JSON.stringify(operationalSubjectTypesContract, null, 2)
    );
    console.log(`   ✓ operationalSubjectTypes.json`);
  }

  writeAddressLevelTypes() {
    const addressTypes = [
      { uuid: generateUUID('addr-state'), name: 'State', level: 4, isRegistrationLocation: false, parent: null },
      { uuid: generateUUID('addr-district'), name: 'District', level: 3, isRegistrationLocation: false, parent: { name: 'State', uuid: generateUUID('addr-state') } },
      { uuid: generateUUID('addr-block'), name: 'Block', level: 2, isRegistrationLocation: false, parent: { name: 'District', uuid: generateUUID('addr-district') } },
      { uuid: generateUUID('addr-pada'), name: 'Pada', level: 1, isRegistrationLocation: true, parent: { name: 'Block', uuid: generateUUID('addr-block') } },
    ];
    fs.writeFileSync(
      path.join(OUTPUT_DIR, 'addressLevelTypes.json'),
      JSON.stringify(addressTypes, null, 2)
    );
    console.log(`   ✓ addressLevelTypes.json`);
  }

  writeSampleLocations() {
    // Generate sample location data for Mazi Saheli (Maharashtra-based organization)
    const locations = [
      // State
      { state: 'Maharashtra', district: '', block: '', pada: '', gps: '' },
      
      // Districts
      { state: 'Maharashtra', district: 'Mumbai', block: '', pada: '', gps: '' },
      { state: 'Maharashtra', district: 'Thane', block: '', pada: '', gps: '' },
      { state: 'Maharashtra', district: 'Pune', block: '', pada: '', gps: '' },
      
      // Mumbai - Blocks
      { state: 'Maharashtra', district: 'Mumbai', block: 'Andheri', pada: '', gps: '' },
      { state: 'Maharashtra', district: 'Mumbai', block: 'Borivali', pada: '', gps: '' },
      { state: 'Maharashtra', district: 'Mumbai', block: 'Kurla', pada: '', gps: '' },
      
      // Thane - Blocks
      { state: 'Maharashtra', district: 'Thane', block: 'Kalyan', pada: '', gps: '' },
      { state: 'Maharashtra', district: 'Thane', block: 'Bhiwandi', pada: '', gps: '' },
      
      // Pune - Blocks
      { state: 'Maharashtra', district: 'Pune', block: 'Hadapsar', pada: '', gps: '' },
      { state: 'Maharashtra', district: 'Pune', block: 'Kothrud', pada: '', gps: '' },
      
      // Andheri - Padas (registration locations)
      { state: 'Maharashtra', district: 'Mumbai', block: 'Andheri', pada: 'Andheri East Pada 1', gps: '19.1136,72.8697' },
      { state: 'Maharashtra', district: 'Mumbai', block: 'Andheri', pada: 'Andheri East Pada 2', gps: '19.1197,72.8464' },
      { state: 'Maharashtra', district: 'Mumbai', block: 'Andheri', pada: 'Andheri West Pada 1', gps: '19.1358,72.8269' },
      
      // Borivali - Padas
      { state: 'Maharashtra', district: 'Mumbai', block: 'Borivali', pada: 'Borivali East Pada 1', gps: '19.2403,72.8567' },
      { state: 'Maharashtra', district: 'Mumbai', block: 'Borivali', pada: 'Borivali West Pada 1', gps: '19.2295,72.8570' },
      
      // Kurla - Padas
      { state: 'Maharashtra', district: 'Mumbai', block: 'Kurla', pada: 'Kurla East Pada 1', gps: '19.0728,72.8826' },
      { state: 'Maharashtra', district: 'Mumbai', block: 'Kurla', pada: 'Kurla West Pada 1', gps: '19.0759,72.8777' },
      
      // Kalyan - Padas
      { state: 'Maharashtra', district: 'Thane', block: 'Kalyan', pada: 'Kalyan East Pada 1', gps: '19.2403,73.1305' },
      { state: 'Maharashtra', district: 'Thane', block: 'Kalyan', pada: 'Kalyan West Pada 1', gps: '19.2403,73.1305' },
      
      // Bhiwandi - Padas
      { state: 'Maharashtra', district: 'Thane', block: 'Bhiwandi', pada: 'Bhiwandi Pada 1', gps: '19.2969,73.0631' },
      { state: 'Maharashtra', district: 'Thane', block: 'Bhiwandi', pada: 'Bhiwandi Pada 2', gps: '19.2969,73.0631' },
      
      // Hadapsar - Padas
      { state: 'Maharashtra', district: 'Pune', block: 'Hadapsar', pada: 'Hadapsar Pada 1', gps: '18.5089,73.9260' },
      { state: 'Maharashtra', district: 'Pune', block: 'Hadapsar', pada: 'Hadapsar Pada 2', gps: '18.5089,73.9260' },
      
      // Kothrud - Padas
      { state: 'Maharashtra', district: 'Pune', block: 'Kothrud', pada: 'Kothrud Pada 1', gps: '18.5074,73.8077' },
      { state: 'Maharashtra', district: 'Pune', block: 'Kothrud', pada: 'Kothrud Pada 2', gps: '18.5074,73.8077' },
    ];

    // Convert to CSV format - State (highest) to Pada (lowest), left to right
    const csvHeader = '"State","District","Block","Pada","GPS coordinates"';
    const csvRows = locations.map(loc => {
      const state = loc.state || '';
      const district = loc.district || '';
      const block = loc.block || '';
      const pada = loc.pada || '';
      const gps = loc.gps || '';
      return `"${state}","${district}","${block}","${pada}","${gps}"`;
    });

    const csvContent = [csvHeader, ...csvRows].join('\n');
    
    fs.writeFileSync(
      path.join(OUTPUT_DIR, 'sample-locations.csv'),
      csvContent
    );
    console.log(`   ✓ sample-locations.csv (${locations.length} locations)`);
  }

  writeGroupsAndPrivileges() {
    // Define user groups based on Mazi Saheli org structure
    const groups = [
      { name: 'Field Executive', uuid: generateUUID('group-Field Executive') },
      { name: 'Operational Head', uuid: generateUUID('group-Operational Head') },
      { name: 'Founder', uuid: generateUUID('group-Founder') },
    ];

    fs.writeFileSync(
      path.join(OUTPUT_DIR, 'groups.json'),
      JSON.stringify(groups, null, 2)
    );
    console.log(`   ✓ groups.json (${groups.length} groups)`);

    // Generate privileges for each group
    const privileges = [];
    const privilegeTypes = [
      'ViewSubject', 'RegisterSubject', 'EditSubject', 'VoidSubject',
      'ViewVisit', 'ScheduleVisit', 'PerformVisit', 'EditVisit', 'CancelVisit',
    ];

    for (const subjectType of this.subjectTypes.values()) {
      for (const privilegeType of privilegeTypes) {
        for (const group of groups) {
          privileges.push({
            uuid: generateUUID(`priv-${group.name}-${privilegeType}-${subjectType.name}`),
            groupUUID: group.uuid,
            privilegeType: privilegeType,
            subjectTypeUUID: subjectType.uuid,
            programUUID: null,
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
        for (const group of groups) {
          const subjectType = getSubjectType(encounterType.name);
          privileges.push({
            uuid: generateUUID(`priv-${group.name}-${privilegeType}-${encounterType.name}`),
            groupUUID: group.uuid,
            privilegeType: privilegeType,
            subjectTypeUUID: this.subjectTypes.get(subjectType)?.uuid || this.subjectTypes.get('Participant').uuid,
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
    const standardCardTypes = {
      total: '1fbcadf3-bf1a-439e-9e13-24adddfbf6c0',
      recentRegistrations: '88a7514c-48c0-4d5d-a421-d074e43bb36c',
      recentVisits: '77b5b3fa-de35-4f24-996b-2842492ea6e0',
    };

    const reportCards = [
      {
        uuid: generateUUID('card-total-activities'),
        name: 'Total Activities',
        description: 'Total registered activities',
        color: '#1976d2',
        nested: false,
        count: 1,
        standardReportCardType: standardCardTypes.total,
        standardReportCardInputSubjectTypes: [this.subjectTypes.get('Activity').uuid],
        standardReportCardInputPrograms: [],
        standardReportCardInputEncounterTypes: [],
        voided: false
      },
      {
        uuid: generateUUID('card-total-participants'),
        name: 'Total Participants',
        description: 'Total registered participants',
        color: '#388e3c',
        nested: false,
        count: 2,
        standardReportCardType: standardCardTypes.total,
        standardReportCardInputSubjectTypes: [this.subjectTypes.get('Participant').uuid],
        standardReportCardInputPrograms: [],
        standardReportCardInputEncounterTypes: [],
        voided: false
      },
      {
        uuid: generateUUID('card-recent-activities'),
        name: 'Recent Activities',
        description: 'Recently registered activities',
        color: '#7b1fa2',
        nested: false,
        count: 3,
        standardReportCardType: standardCardTypes.recentRegistrations,
        standardReportCardInputSubjectTypes: [this.subjectTypes.get('Activity').uuid],
        standardReportCardInputPrograms: [],
        standardReportCardInputEncounterTypes: [],
        voided: false
      },
      {
        uuid: generateUUID('card-recent-participants'),
        name: 'Recent Participants',
        description: 'Recently registered participants',
        color: '#00796b',
        nested: false,
        count: 4,
        standardReportCardType: standardCardTypes.recentRegistrations,
        standardReportCardInputSubjectTypes: [this.subjectTypes.get('Participant').uuid],
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

    // Create dashboard
    const reportDashboard = [
      {
        uuid: generateUUID('dashboard-main'),
        name: 'Main Dashboard',
        description: 'Default dashboard for all users',
        sections: [
          {
            uuid: generateUUID('section-overview'),
            name: 'Overview',
            description: 'Activity and participant statistics',
            displayOrder: 1,
            viewType: 'Default',
            cards: reportCards.map((card, idx) => ({ uuid: card.uuid, displayOrder: idx + 1 }))
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
    console.log('\n' + '═'.repeat(60));
    console.log('📊 GENERATION COMPLETE');
    console.log('═'.repeat(60));
    console.log(`   Concepts: ${this.concepts.size + this.answers.size}`);
    console.log(`      - Questions: ${this.concepts.size}`);
    console.log(`      - Answers: ${this.answers.size}`);
    console.log(`   Forms: ${this.forms.length}`);
    console.log(`   Cancellation Forms: ${this.encounterTypes.size}`);
    console.log(`   Encounter Types: ${this.encounterTypes.size}`);
    console.log(`   Subject Types: ${this.subjectTypes.size}`);
    console.log(`      - Activity (Individual)`);
    console.log(`      - Participant (Person)`);
    console.log(`   Form Mappings: ${this.formMappings.length}`);
    console.log('═'.repeat(60));
    console.log(`📁 Output: ${OUTPUT_DIR}`);
    console.log('═'.repeat(60) + '\n');
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// MAIN
// ═══════════════════════════════════════════════════════════════════════════

const generator = new MaziSaheliBundleGenerator();
generator.generate();

console.log('🎉 Bundle generated successfully!\n');
process.exit(0);

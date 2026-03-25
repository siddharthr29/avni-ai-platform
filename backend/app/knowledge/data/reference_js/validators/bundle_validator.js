#!/usr/bin/env node
/**
 * AVNI Bundle Validator
 *
 * Validates generated bundles before upload to prevent common issues:
 * 1. Duplicate concept UUIDs
 * 2. Duplicate concept names (case-insensitive)
 * 3. Same concept used with different data types
 * 4. Missing answer concept definitions
 * 5. Form elements referencing non-existent concepts
 * 6. Missing required files
 * 7. Invalid JSON structure
 *
 * Usage:
 *   node validators/bundle_validator.js <bundle-directory>
 */

const fs = require('fs');
const path = require('path');

class BundleValidator {
  constructor(bundleDir, options = {}) {
    this.bundleDir = bundleDir;
    this.errors = [];
    this.warnings = [];
    this.concepts = new Map(); // name -> concept
    this.conceptsByUuid = new Map(); // uuid -> concept
    this.answersByUuid = new Map(); // uuid -> answer
    this.forms = [];
    this.quiet = options.quiet || false; // Suppress output when called programmatically
  }

  log(...args) {
    if (!this.quiet) {
      console.log(...args);
    }
  }

  validate() {
    this.log('\n🔍 AVNI Bundle Validator');
    this.log('═'.repeat(55));
    this.log(`   Bundle: ${this.bundleDir}`);
    this.log('═'.repeat(55) + '\n');

    // Check required files
    this.checkRequiredFiles();

    // Load and validate concepts
    this.validateConcepts();

    // Validate concept name hygiene (trailing commas, whitespace)
    this.validateConceptNameHygiene();

    // Load and validate forms
    this.validateForms();

    // Check form-concept references
    this.validateFormConceptReferences();

    // Validate encounter type completeness
    this.validateEncounterTypeCompleteness();

    // Validate address level type ordering
    this.validateAddressLevelTypes();

    // Validate reportCard format
    this.validateReportCardFormat();

    // Validate operational config format
    this.validateOperationalConfigFormat();

    // Check missing files that production bundles have
    this.checkMissingOptionalFiles();

    // Print results
    this.printResults();

    return {
      valid: this.errors.length === 0,
      errors: this.errors,
      warnings: this.warnings
    };
  }

  checkRequiredFiles() {
    this.log('📋 Checking required files...');

    const requiredFiles = [
      'concepts.json',
      'subjectTypes.json',
      'programs.json',
      'encounterTypes.json',
      'formMappings.json'
    ];

    for (const file of requiredFiles) {
      const filePath = path.join(this.bundleDir, file);
      if (!fs.existsSync(filePath)) {
        this.errors.push(`Missing required file: ${file}`);
      } else {
        // Validate JSON
        try {
          JSON.parse(fs.readFileSync(filePath, 'utf8'));
          this.log(`   ✓ ${file}`);
        } catch (e) {
          this.errors.push(`Invalid JSON in ${file}: ${e.message}`);
        }
      }
    }

    // Check forms directory
    const formsDir = path.join(this.bundleDir, 'forms');
    if (!fs.existsSync(formsDir)) {
      this.errors.push('Missing forms/ directory');
    } else {
      const formFiles = fs.readdirSync(formsDir).filter(f => f.endsWith('.json'));
      this.log(`   ✓ forms/ (${formFiles.length} forms)`);
    }
  }

  validateConcepts() {
    this.log('\n📋 Validating concepts...');

    const conceptsFile = path.join(this.bundleDir, 'concepts.json');
    if (!fs.existsSync(conceptsFile)) return;

    const concepts = JSON.parse(fs.readFileSync(conceptsFile, 'utf8'));
    const nameMap = new Map(); // lowercase name -> [concepts with that name]
    const uuidSet = new Set();

    for (const concept of concepts) {
      // Check for duplicate UUIDs
      if (uuidSet.has(concept.uuid)) {
        // For answer concepts (NA type), same UUID for equivalent answers like "Other"/"Others" is OK
        const existingConcept = this.conceptsByUuid.get(concept.uuid);
        if (concept.dataType === 'NA' && existingConcept.dataType === 'NA') {
          // Check if names are equivalent (Other vs Others, etc.)
          const equivalentNames = [
            ['Other', 'Others'],
            ['NA', 'N/A', 'Not Applicable'],
            ['None', 'Nil'],
          ];
          const areEquivalent = equivalentNames.some(group =>
            group.includes(concept.name) && group.includes(existingConcept.name)
          );
          if (!areEquivalent) {
            this.errors.push(`DUPLICATE UUID: "${concept.uuid}" used by different answer concepts: "${existingConcept.name}" and "${concept.name}"`);
          }
        } else {
          this.errors.push(`DUPLICATE UUID: "${concept.uuid}" used by multiple concepts: "${existingConcept.name}" and "${concept.name}"`);
        }
      }
      uuidSet.add(concept.uuid);
      this.conceptsByUuid.set(concept.uuid, concept);

      // Track by name (case-insensitive)
      const lowerName = concept.name.toLowerCase();
      if (!nameMap.has(lowerName)) {
        nameMap.set(lowerName, []);
      }
      nameMap.get(lowerName).push(concept);

      // Store answers separately
      if (concept.dataType === 'NA') {
        this.answersByUuid.set(concept.uuid, concept);
      }

      this.concepts.set(concept.name, concept);
    }

    // Check for duplicate names
    let duplicateCount = 0;
    for (const [lowerName, conceptList] of nameMap) {
      if (conceptList.length > 1) {
        // Check if they have different UUIDs (actual duplicate)
        const uuids = new Set(conceptList.map(c => c.uuid));
        if (uuids.size > 1) {
          this.errors.push(`DUPLICATE CONCEPT NAME: "${conceptList[0].name}" has ${conceptList.length} entries with different UUIDs: ${[...uuids].join(', ')}`);
          duplicateCount++;
        }

        // Check if same name has different data types
        const dataTypes = new Set(conceptList.map(c => c.dataType));
        if (dataTypes.size > 1) {
          this.errors.push(`INCONSISTENT DATA TYPE: "${conceptList[0].name}" has multiple data types: ${[...dataTypes].join(', ')}`);
        }
      }
    }

    // Validate coded concepts have answer definitions
    let missingAnswers = 0;
    for (const concept of concepts) {
      if (concept.dataType === 'Coded' && concept.answers) {
        for (const answer of concept.answers) {
          if (!this.answersByUuid.has(answer.uuid)) {
            // Check if answer is defined in concepts.json
            const answerConcept = concepts.find(c => c.uuid === answer.uuid);
            if (!answerConcept) {
              this.warnings.push(`Missing answer concept definition for "${answer.name}" (UUID: ${answer.uuid}) in question "${concept.name}"`);
              missingAnswers++;
            }
          }
        }
      }
    }

    this.log(`   Total concepts: ${concepts.length}`);
    this.log(`   Duplicate UUIDs: ${duplicateCount > 0 ? '❌ ' + duplicateCount : '✓ 0'}`);
    this.log(`   Missing answer definitions: ${missingAnswers > 0 ? '⚠️ ' + missingAnswers : '✓ 0'}`);
  }

  validateForms() {
    this.log('\n📋 Validating forms...');

    const formsDir = path.join(this.bundleDir, 'forms');
    if (!fs.existsSync(formsDir)) return;

    const formFiles = fs.readdirSync(formsDir).filter(f => f.endsWith('.json'));
    const formUuids = new Set();
    const formElementUuids = new Set();
    let duplicateFormElements = 0;

    for (const formFile of formFiles) {
      try {
        const form = JSON.parse(fs.readFileSync(path.join(formsDir, formFile), 'utf8'));
        this.forms.push(form);

        // Check for duplicate form UUIDs
        if (formUuids.has(form.uuid)) {
          this.errors.push(`DUPLICATE FORM UUID: "${form.uuid}" in ${formFile}`);
        }
        formUuids.add(form.uuid);

        // Check form element UUIDs
        if (form.formElementGroups) {
          for (const group of form.formElementGroups) {
            if (group.formElements) {
              for (const element of group.formElements) {
                if (formElementUuids.has(element.uuid)) {
                  this.warnings.push(`Duplicate form element UUID: "${element.uuid}" for "${element.name}" in ${formFile}`);
                  duplicateFormElements++;
                }
                formElementUuids.add(element.uuid);
              }
            }
          }
        }
      } catch (e) {
        this.errors.push(`Invalid JSON in form ${formFile}: ${e.message}`);
      }
    }

    this.log(`   Total forms: ${formFiles.length}`);
    this.log(`   Duplicate form element UUIDs: ${duplicateFormElements > 0 ? '⚠️ ' + duplicateFormElements : '✓ 0'}`);
  }

  validateFormConceptReferences() {
    this.log('\n📋 Validating form-concept references...');

    let missingConcepts = 0;
    let conceptsInForms = new Set();

    for (const form of this.forms) {
      if (!form.formElementGroups) continue;

      for (const group of form.formElementGroups) {
        if (!group.formElements) continue;

        for (const element of group.formElements) {
          if (element.concept) {
            conceptsInForms.add(element.concept.uuid);

            // Check if concept exists in concepts.json
            if (!this.conceptsByUuid.has(element.concept.uuid)) {
              this.warnings.push(`Form "${form.name}" references concept "${element.concept.name}" (UUID: ${element.concept.uuid}) not found in concepts.json`);
              missingConcepts++;
            } else {
              // Check if data types match
              const masterConcept = this.conceptsByUuid.get(element.concept.uuid);
              if (masterConcept.dataType !== element.concept.dataType) {
                this.warnings.push(`Data type mismatch in form "${form.name}": concept "${element.concept.name}" is ${element.concept.dataType} in form but ${masterConcept.dataType} in concepts.json`);
              }
            }

            // Check embedded answers match master answers
            if (element.concept.answers && element.concept.answers.length > 0) {
              const masterConcept = this.conceptsByUuid.get(element.concept.uuid);
              if (masterConcept && masterConcept.answers) {
                // Verify all answer UUIDs are consistent
                for (const formAnswer of element.concept.answers) {
                  const masterAnswer = masterConcept.answers.find(a => a.name === formAnswer.name);
                  if (masterAnswer && masterAnswer.uuid !== formAnswer.uuid) {
                    this.errors.push(`ANSWER UUID MISMATCH: "${formAnswer.name}" in form "${form.name}" has UUID ${formAnswer.uuid} but master concept has ${masterAnswer.uuid}`);
                  }
                }
              }
            }
          }
        }
      }
    }

    this.log(`   Concepts referenced in forms: ${conceptsInForms.size}`);
    this.log(`   Missing concept definitions: ${missingConcepts > 0 ? '⚠️ ' + missingConcepts : '✓ 0'}`);
  }

  validateConceptNameHygiene() {
    this.log('\n📋 Validating concept name hygiene...');

    const conceptsFile = path.join(this.bundleDir, 'concepts.json');
    if (!fs.existsSync(conceptsFile)) return;

    const concepts = JSON.parse(fs.readFileSync(conceptsFile, 'utf8'));
    let trailingCommas = 0;
    let trailingWhitespace = 0;
    let leadingWhitespace = 0;

    for (const concept of concepts) {
      if (concept.name.endsWith(',')) {
        this.errors.push(`TRAILING COMMA in concept name: "${concept.name}" (UUID: ${concept.uuid})`);
        trailingCommas++;
      }
      if (concept.name !== concept.name.trimEnd()) {
        this.warnings.push(`TRAILING WHITESPACE in concept name: "${concept.name}" (UUID: ${concept.uuid})`);
        trailingWhitespace++;
      }
      if (concept.name !== concept.name.trimStart()) {
        this.warnings.push(`LEADING WHITESPACE in concept name: "${concept.name}" (UUID: ${concept.uuid})`);
        leadingWhitespace++;
      }
      // Also check answer names
      if (concept.answers) {
        for (const answer of concept.answers) {
          if (answer.name.endsWith(',')) {
            this.errors.push(`TRAILING COMMA in answer name: "${answer.name}" in concept "${concept.name}"`);
            trailingCommas++;
          }
        }
      }
    }

    this.log(`   Trailing commas: ${trailingCommas > 0 ? '❌ ' + trailingCommas : '✓ 0'}`);
    this.log(`   Whitespace issues: ${(trailingWhitespace + leadingWhitespace) > 0 ? '⚠️ ' + (trailingWhitespace + leadingWhitespace) : '✓ 0'}`);
  }

  validateEncounterTypeCompleteness() {
    this.log('\n📋 Validating encounter type completeness...');

    const encounterTypesFile = path.join(this.bundleDir, 'encounterTypes.json');
    const formMappingsFile = path.join(this.bundleDir, 'formMappings.json');
    if (!fs.existsSync(encounterTypesFile) || !fs.existsSync(formMappingsFile)) return;

    const encounterTypes = JSON.parse(fs.readFileSync(encounterTypesFile, 'utf8'));
    const formMappings = JSON.parse(fs.readFileSync(formMappingsFile, 'utf8'));

    for (const et of encounterTypes) {
      const encounterMapping = formMappings.find(m =>
        m.encounterTypeUUID === et.uuid && m.formType === 'Encounter' && !m.voided
      );
      const cancellationMapping = formMappings.find(m =>
        m.encounterTypeUUID === et.uuid && m.formType === 'IndividualEncounterCancellation' && !m.voided
      );

      if (!encounterMapping) {
        this.warnings.push(`Encounter type "${et.name}" has no Encounter form mapping`);
      }
      if (!cancellationMapping) {
        this.warnings.push(`Encounter type "${et.name}" has no cancellation form mapping`);
      }
    }

    // Check formMappings reference valid encounter types
    const etUuids = new Set(encounterTypes.map(et => et.uuid));
    for (const mapping of formMappings) {
      if (mapping.encounterTypeUUID && !etUuids.has(mapping.encounterTypeUUID)) {
        this.errors.push(`Form mapping "${mapping.formName}" references encounterTypeUUID ${mapping.encounterTypeUUID} not found in encounterTypes.json`);
      }
    }

    this.log(`   Encounter types: ${encounterTypes.length}`);
    this.log(`   Form mappings: ${formMappings.length}`);
  }

  validateAddressLevelTypes() {
    this.log('\n📋 Validating address level types...');

    const addrFile = path.join(this.bundleDir, 'addressLevelTypes.json');
    if (!fs.existsSync(addrFile)) return;

    const addressTypes = JSON.parse(fs.readFileSync(addrFile, 'utf8'));
    if (addressTypes.length === 0) return;

    // Find root (no parent) and leaf (registration location)
    const root = addressTypes.find(a => !a.parent);
    const leaf = addressTypes.find(a => a.isRegistrationLocation);

    if (root && leaf) {
      if (root.level < leaf.level) {
        this.errors.push(`Address level ordering reversed: root "${root.name}" has level ${root.level} but leaf "${leaf.name}" has level ${leaf.level}. Root should have the HIGHEST level number.`);
      } else {
        this.log(`   ✓ Hierarchy: ${root.name} (level ${root.level}) → ${leaf.name} (level ${leaf.level})`);
      }
    }
  }

  validateReportCardFormat() {
    this.log('\n📋 Validating reportCard format...');

    const rcFile = path.join(this.bundleDir, 'reportCard.json');
    if (!fs.existsSync(rcFile)) return;

    const reportCards = JSON.parse(fs.readFileSync(rcFile, 'utf8'));
    let formatErrors = 0;

    for (const card of reportCards) {
      const fields = [
        'standardReportCardInputSubjectTypes',
        'standardReportCardInputPrograms',
        'standardReportCardInputEncounterTypes'
      ];
      for (const field of fields) {
        if (card[field] && Array.isArray(card[field])) {
          for (const item of card[field]) {
            if (typeof item !== 'string') {
              this.errors.push(`reportCard "${card.name}": ${field} should be array of UUID strings, found object: ${JSON.stringify(item)}`);
              formatErrors++;
            }
          }
        }
      }
    }

    this.log(`   Report cards: ${reportCards.length}`);
    this.log(`   Format errors: ${formatErrors > 0 ? '❌ ' + formatErrors : '✓ 0'}`);
  }

  validateOperationalConfigFormat() {
    this.log('\n📋 Validating operational config format...');

    const opSubFile = path.join(this.bundleDir, 'operationalSubjectTypes.json');
    const opEncFile = path.join(this.bundleDir, 'operationalEncounterTypes.json');

    if (fs.existsSync(opSubFile)) {
      const data = JSON.parse(fs.readFileSync(opSubFile, 'utf8'));
      if (Array.isArray(data)) {
        this.errors.push('operationalSubjectTypes.json is a bare array. Must be wrapped: { operationalSubjectTypes: [...] }');
      } else if (!data.operationalSubjectTypes) {
        this.errors.push('operationalSubjectTypes.json missing "operationalSubjectTypes" wrapper key');
      } else {
        this.log('   ✓ operationalSubjectTypes.json format correct');
      }
    }

    if (fs.existsSync(opEncFile)) {
      const data = JSON.parse(fs.readFileSync(opEncFile, 'utf8'));
      if (Array.isArray(data)) {
        this.errors.push('operationalEncounterTypes.json is a bare array. Must be wrapped: { operationalEncounterTypes: [...] }');
      } else if (!data.operationalEncounterTypes) {
        this.errors.push('operationalEncounterTypes.json missing "operationalEncounterTypes" wrapper key');
      } else {
        this.log('   ✓ operationalEncounterTypes.json format correct');
      }
    }
  }

  checkMissingOptionalFiles() {
    this.log('\n📋 Checking optional but recommended files...');

    const optionalFiles = [
      { file: 'groups.json', importance: 'CRITICAL', reason: 'User groups for permissions' },
      { file: 'groupPrivilege.json', importance: 'CRITICAL', reason: 'User permissions' },
      { file: 'reportCard.json', importance: 'HIGH', reason: 'Dashboard report cards' },
      { file: 'reportDashboard.json', importance: 'HIGH', reason: 'Dashboard configurations' },
      { file: 'groupDashboards.json', importance: 'HIGH', reason: 'Dashboard assignments per group' },
      { file: 'translations/', importance: 'MEDIUM', reason: 'Multi-language support' },
      { file: 'ruleDependency.json', importance: 'LOW', reason: 'Rule dependencies' },
      { file: 'documentations.json', importance: 'LOW', reason: 'Documentation' },
    ];

    for (const item of optionalFiles) {
      const filePath = path.join(this.bundleDir, item.file);
      const exists = fs.existsSync(filePath);
      const symbol = exists ? '✓' : (item.importance === 'CRITICAL' ? '❌' : '⚠️');
      this.log(`   ${symbol} ${item.file} - ${item.reason}`);

      if (!exists && item.importance === 'CRITICAL') {
        this.errors.push(`Missing ${item.importance} file: ${item.file} - ${item.reason}`);
      } else if (!exists && item.importance === 'HIGH') {
        this.warnings.push(`Missing ${item.importance} file: ${item.file} - ${item.reason}`);
      }
    }
  }

  printResults() {
    this.log('\n' + '═'.repeat(55));
    this.log('📊 VALIDATION RESULTS');
    this.log('═'.repeat(55));

    if (this.errors.length === 0 && this.warnings.length === 0) {
      this.log('\n✅ Bundle is valid! No issues found.\n');
      return;
    }

    if (this.errors.length > 0) {
      this.log(`\n❌ ERRORS (${this.errors.length}) - Must fix before upload:`);
      for (const error of this.errors) {
        this.log(`   • ${error}`);
      }
    }

    if (this.warnings.length > 0) {
      this.log(`\n⚠️  WARNINGS (${this.warnings.length}) - Should review:`);
      for (const warning of this.warnings) {
        this.log(`   • ${warning}`);
      }
    }

    this.log('\n' + '═'.repeat(55));
    this.log(`Result: ${this.errors.length === 0 ? '✅ PASS (with warnings)' : '❌ FAIL'}`);
    this.log('═'.repeat(55) + '\n');
  }
}

// Main
if (require.main === module) {
  const bundleDir = process.argv[2];

  if (!bundleDir) {
    console.log('Usage: node validators/bundle_validator.js <bundle-directory>');
    console.log('Example: node validators/bundle_validator.js output/Astitva-Nourish-Program');
    process.exit(1);
  }

  if (!fs.existsSync(bundleDir)) {
    console.error(`Error: Directory not found: ${bundleDir}`);
    process.exit(1);
  }

  const validator = new BundleValidator(bundleDir);
  const result = validator.validate();

  process.exit(result.valid ? 0 : 1);
}

module.exports = { BundleValidator };

/**
 * Main Bundle Generator
 * Orchestrates all generators to create a complete AVNI bundle from SRS
 */

const fs = require('fs');
const path = require('path');
const { parseSRS, parseFormMetadata } = require('../parsers/srs_parser');
const { ConceptGenerator } = require('./concepts');
const { FormGenerator } = require('./forms');
const { ReportCardGenerator } = require('./reportCards');
const { v4: uuidv4 } = require('uuid');

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

class BundleGenerator {
  constructor(orgName) {
    this.orgName = orgName;
    this.conceptGenerator = new ConceptGenerator();
    this.formGenerator = new FormGenerator();
    this.bundle = {
      concepts: [],
      forms: [],
      subjectTypes: [],
      programs: [],
      encounterTypes: [],
      formMappings: [],
      groups: [],
      groupPrivileges: []
    };
    // Lazily initialised when processDashboards is called
    this.reportCardGenerator = null;
    this.validation = [];
    this.confidence = {};
  }
  
  // Process subject types from SRS
  processSubjectTypes(subjectTypesSRS) {
    subjectTypesSRS.forEach(st => {
      this.bundle.subjectTypes.push({
        name: st.name,
        uuid: generateDeterministicUUID(`subjectType:${st.name}`),
        active: true,
        type: st.type || 'Person',
        subjectSummaryRule: '',
        programEligibilityCheckRule: '',
        allowEmptyLocation: false,
        allowMiddleName: false,
        lastNameOptional: true,
        validFirstNameFormat: '[A-Za-z0-9\\s]+',
        iconFileS3Key: null,
        settings: null
      });
    });
  }
  
  // Process programs from SRS
  processPrograms(programsSRS) {
    programsSRS.forEach(prog => {
      this.bundle.programs.push({
        name: prog.name,
        uuid: generateDeterministicUUID(`program:${prog.name}`),
        colour: '#3949AB',
        programSubjectLabel: prog.subjectLabel || prog.name,
        enrolmentSummaryRule: '',
        enrolmentEligibilityCheckRule: '',
        active: true,
        manualEnrolmentEligibilityCheckRule: '',
        manualEligibilityCheckRequired: false,
        allowMultipleEnrolments: false
      });
    });
  }
  
  // Process encounter types from SRS
  processEncounterTypes(encounterTypesSRS) {
    encounterTypesSRS.forEach(et => {
      this.bundle.encounterTypes.push({
        name: et.name,
        uuid: generateDeterministicUUID(`encounterType:${et.name}`),
        encounterEligibilityCheckRule: '',
        active: true,
        immutable: false,
        programEncounter: et.programEncounter !== false
      });
    });
  }
  
  // Process forms from SRS
  processForms(formsSRS) {
    formsSRS.forEach(formSpec => {
      // Parse fields from CSV if provided
      let fields = formSpec.fields || [];
      if (formSpec.fieldsCSV) {
        const parsed = parseSRS(formSpec.fieldsCSV);
        fields = parsed.fields;
      }
      
      // Generate concepts for fields
      const concepts = this.conceptGenerator.generateFromFields(fields);
      
      // Build concept map for form generator
      const conceptMap = {};
      concepts.forEach(c => {
        conceptMap[c.name] = {
          uuid: c.uuid,
          dataType: c.dataType,
          answers: c.answers
        };
      });
      
      // Generate form
      const form = this.formGenerator.generateForm({
        name: formSpec.name,
        formType: formSpec.formType,
        fields: fields,
        concepts: conceptMap
      });
      
      this.bundle.forms.push(form);
      
      // Generate cancellation form for encounters
      if (['ProgramEncounter', 'Encounter'].includes(formSpec.formType)) {
        const cancellationForm = this.formGenerator.generateCancellationForm(
          formSpec.name, 
          formSpec.formType
        );
        this.bundle.forms.push(cancellationForm);
      }
      
      // Generate form mapping
      this.generateFormMapping(formSpec, form.uuid);
    });
    
    // Store concepts
    this.bundle.concepts = this.conceptGenerator.generatedConcepts;
  }
  
  // Generate form mapping
  generateFormMapping(formSpec, formUUID) {
    const subjectType = this.bundle.subjectTypes.find(st => 
      st.name === formSpec.subjectType
    );
    const program = this.bundle.programs.find(p => 
      p.name === formSpec.program
    );
    const encounterType = this.bundle.encounterTypes.find(et => 
      et.name === formSpec.encounterType
    );
    
    const mapping = {
      uuid: generateDeterministicUUID(`mapping:${formSpec.name}`),
      formUUID: formUUID,
      formType: formSpec.formType,
      formName: formSpec.name,
      enableApproval: false
    };
    
    if (subjectType) mapping.subjectTypeUUID = subjectType.uuid;
    if (program) mapping.programUUID = program.uuid;
    if (encounterType) mapping.encounterTypeUUID = encounterType.uuid;
    
    this.bundle.formMappings.push(mapping);
  }
  
  // Process user groups from SRS
  processGroups(groupsSRS) {
    groupsSRS.forEach(group => {
      this.bundle.groups.push({
        name: group.name,
        uuid: generateDeterministicUUID(`group:${group.name}`),
        hasAllPrivileges: group.admin === true
      });
    });
  }
  
  /**
   * Process dashboards, report cards, and group-dashboard links from the SRS spec.
   *
   * Must be called after processSubjectTypes, processEncounterTypes, processPrograms,
   * and processGroups so that name→UUID resolution is available.
   *
   * @param {Array} dashboardsSRS - Array of dashboard specs (see reportCards.js for full input format)
   *
   * Each dashboard spec:
   * {
   *   name, description,
   *   groups: ['GroupName'],           // resolved to UUIDs
   *   primaryDashboard: true,
   *   secondaryDashboard: false,
   *   sections: [
   *     {
   *       name, viewType,
   *       cards: [
   *         // Standard card
   *         { name, type: 'standard', cardType, color, subjectTypes, programs, encounterTypes, recentDays },
   *         // Custom card
   *         { name, type: 'custom', color, query, nestedCount },
   *       ]
   *     }
   *   ]
   * }
   */
  processDashboards(dashboardsSRS) {
    this.reportCardGenerator = new ReportCardGenerator(this.bundle);
    const rcg = this.reportCardGenerator;

    // First pass: collect and register all report cards (across all dashboards/sections)
    // so they can be referenced by name when building sections.
    const allCards = [];
    dashboardsSRS.forEach(dashSpec => {
      (dashSpec.sections || []).forEach(section => {
        (section.cards || []).forEach(card => {
          // Avoid duplicate registration if the same card appears in multiple sections
          if (!allCards.find(c => c.name === card.name)) {
            allCards.push(card);
          }
        });
      });
    });

    allCards.forEach(card => {
      if (card.type === 'standard') {
        rcg.addStandardCard(card);
      } else if (card.type === 'custom') {
        rcg.addCustomCard(card);
      } else {
        throw new Error(`BundleGenerator.processDashboards: unknown card type "${card.type}" for card "${card.name}"`);
      }
    });

    // Second pass: build dashboards and section→card mappings
    dashboardsSRS.forEach(dashSpec => {
      const sections = (dashSpec.sections || []).map(section => ({
        name: section.name,
        description: section.description || '',
        viewType: section.viewType || 'Tile',
        cards: (section.cards || []).map(c => c.name),
      }));

      rcg.addDashboard({
        name: dashSpec.name,
        description: dashSpec.description || '',
        sections,
        filters: dashSpec.filters || [],
      });

      // Link each specified group to this dashboard
      (dashSpec.groups || []).forEach(groupName => {
        rcg.addGroupDashboard({
          groupName,
          dashboardName: dashSpec.name,
          primaryDashboard: dashSpec.primaryDashboard || false,
          secondaryDashboard: dashSpec.secondaryDashboard || false,
          groupOneOfTheDefaultGroups: dashSpec.groupOneOfTheDefaultGroups || false,
        });
      });
    });
  }

  // Validate the generated bundle
  validate() {
    const errors = [];
    const warnings = [];
    
    // Check for missing references
    this.bundle.formMappings.forEach(mapping => {
      if (!mapping.subjectTypeUUID) {
        warnings.push(`Form mapping "${mapping.formName}" missing subject type`);
      }
      if (mapping.formType.includes('Program') && !mapping.programUUID) {
        errors.push(`Form mapping "${mapping.formName}" missing program reference`);
      }
    });
    
    // Check for duplicate concept names
    const conceptNames = new Set();
    this.bundle.concepts.forEach(c => {
      const lower = c.name.toLowerCase();
      if (conceptNames.has(lower)) {
        errors.push(`Duplicate concept name: ${c.name}`);
      }
      conceptNames.add(lower);
    });
    
    // Check for missing answer UUIDs
    this.bundle.concepts.filter(c => c.dataType === 'Coded').forEach(c => {
      c.answers?.forEach(a => {
        if (!a.uuid) {
          errors.push(`Missing UUID for answer "${a.name}" in concept "${c.name}"`);
        }
      });
    });
    
    this.validation = { errors, warnings };
    return errors.length === 0;
  }
  
  // Calculate overall confidence score
  calculateConfidence() {
    const conceptConfidence = parseFloat(this.conceptGenerator.getConfidence());
    
    // Form confidence based on validation
    const formConfidence = this.bundle.forms.length > 0 ? 
      (this.bundle.forms.length - this.validation.errors.length) / this.bundle.forms.length : 0;
    
    // Overall confidence
    this.confidence = {
      concepts: conceptConfidence,
      forms: formConfidence.toFixed(2),
      overall: ((conceptConfidence + formConfidence) / 2).toFixed(2),
      flaggedItems: this.validation.warnings.length + this.validation.errors.length
    };
    
    return this.confidence;
  }
  
  // Generate complete bundle from SRS
  generate(srsData) {
    console.log(`🚀 Generating bundle for: ${this.orgName}`);
    
    // Process each component
    if (srsData.subjectTypes) {
      console.log(`   📋 Processing ${srsData.subjectTypes.length} subject types`);
      this.processSubjectTypes(srsData.subjectTypes);
    }
    
    if (srsData.programs) {
      console.log(`   📋 Processing ${srsData.programs.length} programs`);
      this.processPrograms(srsData.programs);
    }
    
    if (srsData.encounterTypes) {
      console.log(`   📋 Processing ${srsData.encounterTypes.length} encounter types`);
      this.processEncounterTypes(srsData.encounterTypes);
    }
    
    if (srsData.forms) {
      console.log(`   📋 Processing ${srsData.forms.length} forms`);
      this.processForms(srsData.forms);
    }
    
    if (srsData.groups) {
      console.log(`   📋 Processing ${srsData.groups.length} user groups`);
      this.processGroups(srsData.groups);
    }

    if (srsData.dashboards) {
      console.log(`   📋 Processing ${srsData.dashboards.length} dashboards`);
      this.processDashboards(srsData.dashboards);
    }

    // Validate
    console.log(`   🔍 Validating bundle...`);
    this.validate();
    
    // Calculate confidence
    console.log(`   📊 Calculating confidence...`);
    this.calculateConfidence();
    
    return {
      bundle: this.bundle,
      validation: this.validation,
      confidence: this.confidence
    };
  }
  
  // Export bundle to files
  exportToDirectory(outputDir) {
    if (!fs.existsSync(outputDir)) {
      fs.mkdirSync(outputDir, { recursive: true });
    }
    
    // Forms go in subdirectory
    const formsDir = path.join(outputDir, 'forms');
    if (!fs.existsSync(formsDir)) {
      fs.mkdirSync(formsDir);
    }
    
    // Export concepts
    fs.writeFileSync(
      path.join(outputDir, 'concepts.json'),
      JSON.stringify(this.bundle.concepts, null, 2)
    );
    
    // Export forms
    this.bundle.forms.forEach(form => {
      fs.writeFileSync(
        path.join(formsDir, `${form.name}.json`),
        JSON.stringify(form, null, 2)
      );
    });
    
    // Export other files
    ['subjectTypes', 'programs', 'encounterTypes', 'formMappings', 'groups', 'groupPrivileges'].forEach(key => {
      fs.writeFileSync(
        path.join(outputDir, `${key}.json`),
        JSON.stringify(this.bundle[key], null, 2)
      );
    });
    
    // Export report cards, dashboards, and group-dashboard links (if present)
    if (this.reportCardGenerator) {
      this.reportCardGenerator.exportToDirectory(outputDir);
    }

    // Export validation report
    fs.writeFileSync(
      path.join(outputDir, 'validation_report.json'),
      JSON.stringify({
        confidence: this.confidence,
        validation: this.validation,
        summary: {
          concepts: this.bundle.concepts.length,
          forms: this.bundle.forms.length,
          subjectTypes: this.bundle.subjectTypes.length,
          programs: this.bundle.programs.length,
          encounterTypes: this.bundle.encounterTypes.length,
          formMappings: this.bundle.formMappings.length
        }
      }, null, 2)
    );
    
    console.log(`\n✅ Bundle exported to: ${outputDir}`);
    return outputDir;
  }
}

module.exports = { BundleGenerator };

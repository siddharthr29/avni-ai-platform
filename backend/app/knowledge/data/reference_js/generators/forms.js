/**
 * Form Generator
 * Generates AVNI form JSON files from parsed SRS fields
 */

const fs = require('fs');
const path = require('path');
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

class FormGenerator {
  constructor(conceptMap = {}) {
    this.conceptMap = conceptMap;  // name -> {uuid, dataType, answers}
    this.formUUID = null;
    this.groupCounter = 0;
    this.elementCounter = 0;
  }
  
  // Generate declarative rule for skip logic
  generateDeclarativeRule(skipLogic, scope = 'encounter') {
    if (!skipLogic || skipLogic.raw) return null;
    
    const dependsConcept = this.conceptMap[skipLogic.dependsOn];
    if (!dependsConcept) return null;
    
    // Build declarative rule structure
    const rule = {
      actions: [{ actionType: 'showFormElement' }],
      conditions: [{
        compoundRule: {
          rules: [{
            lhs: {
              type: 'concept',
              scope: scope,
              conceptName: skipLogic.dependsOn,
              conceptUuid: dependsConcept.uuid
            },
            rhs: {},
            operator: 'containsAnswerConceptName'
          }]
        }
      }]
    };
    
    // Set RHS based on condition
    if (skipLogic.condition === 'equals' || skipLogic.condition === 'contains') {
      const answerConcept = dependsConcept.answers?.find(a => 
        a.name.toLowerCase() === skipLogic.value.toLowerCase()
      );
      
      rule.conditions[0].compoundRule.rules[0].rhs = {
        type: 'answerConcept',
        answerConceptNames: [skipLogic.value],
        answerConceptUuids: answerConcept ? [answerConcept.uuid] : []
      };
    }
    
    return [rule];
  }
  
  // Generate form element from field
  generateFormElement(field, displayOrder, groupUUID = null) {
    const concept = this.conceptMap[field.name];
    if (!concept) {
      console.warn(`⚠️ Concept not found: ${field.name}`);
      return null;
    }
    
    const elementUUID = generateDeterministicUUID(`element:${this.formUUID}:${field.name}`);
    
    const element = {
      name: field.name,
      uuid: elementUUID,
      keyValues: [],
      concept: {
        name: field.name,
        uuid: concept.uuid,
        dataType: concept.dataType,
        active: true
      },
      displayOrder: displayOrder,
      type: this.getElementType(concept.dataType),
      mandatory: field.mandatory || false
    };
    
    // Add declarative rule for skip logic
    if (field.skipLogic && !field.skipLogic.raw) {
      const scope = this.formType === 'ProgramEnrolment' ? 'enrolment' : 'encounter';
      const declarativeRule = this.generateDeclarativeRule(field.skipLogic, scope);
      if (declarativeRule) {
        element.declarativeRule = declarativeRule;
      }
    }
    
    // Add parent reference for question group children
    if (groupUUID) {
      element.parentFormElementUuid = groupUUID;
    }
    
    return element;
  }
  
  // Get form element type based on data type
  getElementType(dataType) {
    const typeMap = {
      'Coded': 'SingleSelect',
      'Numeric': 'SingleSelect',
      'Text': 'SingleSelect',
      'Date': 'SingleSelect',
      'DateTime': 'SingleSelect',
      'Notes': 'SingleSelect',
      'ImageV2': 'SingleSelect',
      'Image': 'SingleSelect',
      'File': 'SingleSelect',
      'Audio': 'SingleSelect',
      'Video': 'SingleSelect',
      'PhoneNumber': 'SingleSelect',
      'Location': 'SingleSelect',
      'Duration': 'Duration',
      'QuestionGroup': 'SingleSelect'
    };
    return typeMap[dataType] || 'SingleSelect';
  }
  
  // Group fields by section
  groupFieldsBySection(fields) {
    const groups = {};
    const noGroup = [];
    
    fields.forEach(field => {
      if (field.group) {
        if (!groups[field.group]) {
          groups[field.group] = [];
        }
        groups[field.group].push(field);
      } else {
        noGroup.push(field);
      }
    });
    
    // Create default group for ungrouped fields
    if (noGroup.length > 0) {
      groups['General Information'] = noGroup;
    }
    
    return groups;
  }
  
  // Generate form element group
  generateFormElementGroup(groupName, fields, displayOrder) {
    const groupUUID = generateDeterministicUUID(`group:${this.formUUID}:${groupName}`);
    
    const elements = fields.map((field, idx) => 
      this.generateFormElement(field, idx + 1)
    ).filter(e => e !== null);
    
    return {
      uuid: groupUUID,
      name: groupName,
      displayOrder: displayOrder,
      formElements: elements,
      timed: false
    };
  }
  
  // Generate complete form JSON
  generateForm(formSpec) {
    const { name, formType, fields, concepts } = formSpec;
    
    this.formType = formType;
    this.formUUID = generateDeterministicUUID(`form:${name}`);
    this.conceptMap = concepts || {};
    
    // Group fields
    const groupedFields = this.groupFieldsBySection(fields);
    
    // Generate form element groups
    const formElementGroups = Object.entries(groupedFields).map(
      ([groupName, groupFields], idx) => 
        this.generateFormElementGroup(groupName, groupFields, idx + 1)
    );
    
    return {
      name: name,
      uuid: this.formUUID,
      formType: formType,
      formElementGroups: formElementGroups,
      decisionRule: '',
      visitScheduleRule: '',
      validationRule: '',
      checklistsRule: '',
      decisionConcepts: []
    };
  }
  
  // Generate cancellation form for an encounter
  generateCancellationForm(encounterName, formType) {
    const cancellationType = formType === 'ProgramEncounter' 
      ? 'ProgramEncounterCancellation' 
      : 'IndividualEncounterCancellation';
    
    const formName = `${encounterName} Cancellation`;
    this.formUUID = generateDeterministicUUID(`form:${formName}`);
    
    return {
      name: formName,
      uuid: this.formUUID,
      formType: cancellationType,
      formElementGroups: [{
        uuid: generateDeterministicUUID(`group:${this.formUUID}:cancellation`),
        name: 'Cancellation Details',
        displayOrder: 1,
        formElements: [{
          name: 'Cancellation Reason',
          uuid: generateDeterministicUUID(`element:${this.formUUID}:cancellation_reason`),
          keyValues: [],
          concept: {
            name: `${encounterName} cancellation reason`,
            uuid: generateDeterministicUUID(`concept:${encounterName}_cancellation_reason`),
            dataType: 'Text',
            active: true
          },
          displayOrder: 1,
          type: 'SingleSelect',
          mandatory: true
        }],
        timed: false
      }],
      decisionRule: '',
      visitScheduleRule: '',
      validationRule: '',
      checklistsRule: '',
      decisionConcepts: []
    };
  }
  
  // Export form as JSON
  toJSON(form) {
    return JSON.stringify(form, null, 2);
  }
}

module.exports = { FormGenerator };

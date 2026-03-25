/**
 * Concept Generator
 * Generates concepts.json from parsed SRS fields
 */

const fs = require('fs');
const path = require('path');
const { v4: uuidv4 } = require('uuid');

const TRAINING_DATA_DIR = path.join(__dirname, '..', 'training_data');

// Load UUID registry for standard answers
function loadUUIDRegistry() {
  const registryPath = path.join(TRAINING_DATA_DIR, 'uuid_registry.json');
  if (fs.existsSync(registryPath)) {
    return JSON.parse(fs.readFileSync(registryPath, 'utf8'));
  }
  return {};
}

// Load existing concept patterns
function loadConceptPatterns() {
  const patternsPath = path.join(TRAINING_DATA_DIR, 'concept_patterns.json');
  if (fs.existsSync(patternsPath)) {
    return JSON.parse(fs.readFileSync(patternsPath, 'utf8'));
  }
  return {};
}

// Generate deterministic UUID from string (for reproducibility)
function generateDeterministicUUID(seed) {
  // Simple hash-based approach for consistency
  let hash = 0;
  for (let i = 0; i < seed.length; i++) {
    const char = seed.charCodeAt(i);
    hash = ((hash << 5) - hash) + char;
    hash = hash & hash;
  }
  // Convert to UUID-like format
  const hex = Math.abs(hash).toString(16).padStart(8, '0');
  return `${hex.substring(0, 8)}-${uuidv4().substring(9)}`;
}

class ConceptGenerator {
  constructor() {
    this.uuidRegistry = loadUUIDRegistry();
    this.conceptPatterns = loadConceptPatterns();
    this.generatedConcepts = [];
    this.conceptMap = {};  // name -> uuid mapping
  }
  
  // Get or create UUID for an answer
  getAnswerUUID(answerName) {
    // Check registry first (case-insensitive)
    const normalizedName = answerName.trim();
    const lowerName = normalizedName.toLowerCase();
    
    // Exact match
    if (this.uuidRegistry[normalizedName]) {
      return this.uuidRegistry[normalizedName];
    }
    
    // Case-insensitive match
    for (const [key, uuid] of Object.entries(this.uuidRegistry)) {
      if (key.toLowerCase() === lowerName) {
        return uuid;
      }
    }
    
    // Generate new deterministic UUID
    const newUUID = generateDeterministicUUID(`answer:${normalizedName}`);
    this.uuidRegistry[normalizedName] = newUUID;
    return newUUID;
  }
  
  // Get or create UUID for a concept (question)
  getConceptUUID(conceptName) {
    if (this.conceptMap[conceptName]) {
      return this.conceptMap[conceptName];
    }
    
    const newUUID = generateDeterministicUUID(`concept:${conceptName}`);
    this.conceptMap[conceptName] = newUUID;
    return newUUID;
  }
  
  // Find similar concept from training data
  findSimilarConcept(name, dataType) {
    const patterns = this.conceptPatterns[dataType] || [];
    const lowerName = name.toLowerCase();
    
    // Exact match
    const exact = patterns.find(p => p.name.toLowerCase() === lowerName);
    if (exact) return exact;
    
    // Partial match
    const partial = patterns.find(p => 
      p.name.toLowerCase().includes(lowerName) ||
      lowerName.includes(p.name.toLowerCase())
    );
    return partial;
  }
  
  // Generate NA-type answer concept
  generateAnswerConcept(answerName) {
    // Strip trailing commas and whitespace from answer names
    const cleanedName = answerName.trim().replace(/,+$/, '').trim();
    const uuid = this.getAnswerUUID(cleanedName);
    
    // Check if already generated
    if (this.generatedConcepts.some(c => c.uuid === uuid)) {
      return uuid;
    }
    
    this.generatedConcepts.push({
      name: cleanedName,
      uuid: uuid,
      dataType: 'NA',
      active: true
    });
    
    return uuid;
  }
  
  // Generate Coded concept with answers
  generateCodedConcept(field) {
    const conceptUUID = this.getConceptUUID(field.name);
    
    // Generate answer concepts first
    const answers = field.options.map((option, index) => {
      const answerUUID = this.generateAnswerConcept(option);
      return {
        name: option.trim(),
        uuid: answerUUID,
        order: index
      };
    });
    
    this.generatedConcepts.push({
      name: field.name,
      uuid: conceptUUID,
      dataType: 'Coded',
      answers: answers,
      active: true
    });
    
    return conceptUUID;
  }
  
  // Generate Numeric concept
  generateNumericConcept(field) {
    const conceptUUID = this.getConceptUUID(field.name);
    
    // Find similar concept for defaults
    const similar = this.findSimilarConcept(field.name, 'Numeric');
    
    const concept = {
      name: field.name,
      uuid: conceptUUID,
      dataType: 'Numeric',
      active: true
    };
    
    // Apply validation ranges
    if (field.validation) {
      if (field.validation.min !== undefined) concept.lowAbsolute = field.validation.min;
      if (field.validation.max !== undefined) concept.highAbsolute = field.validation.max;
    }
    
    // Inherit from similar concept
    if (similar) {
      if (similar.unit && !concept.unit) concept.unit = similar.unit;
      if (similar.lowNormal && !concept.lowNormal) concept.lowNormal = similar.lowNormal;
      if (similar.highNormal && !concept.highNormal) concept.highNormal = similar.highNormal;
    }
    
    this.generatedConcepts.push(concept);
    return conceptUUID;
  }
  
  // Generate Text concept
  generateTextConcept(field) {
    const conceptUUID = this.getConceptUUID(field.name);
    
    this.generatedConcepts.push({
      name: field.name,
      uuid: conceptUUID,
      dataType: 'Text',
      active: true
    });
    
    return conceptUUID;
  }
  
  // Generate Date concept
  generateDateConcept(field) {
    const conceptUUID = this.getConceptUUID(field.name);
    
    this.generatedConcepts.push({
      name: field.name,
      uuid: conceptUUID,
      dataType: 'Date',
      active: true
    });
    
    return conceptUUID;
  }
  
  // Generate concept based on data type
  generateConcept(field) {
    switch (field.dataType) {
      case 'Coded':
        return this.generateCodedConcept(field);
      case 'Numeric':
        return this.generateNumericConcept(field);
      case 'Date':
      case 'DateTime':
        return this.generateDateConcept(field);
      case 'QuestionGroup':
        return this.generateQuestionGroupConcept(field);
      default:
        return this.generateTextConcept(field);
    }
  }
  
  // Generate QuestionGroup concept
  generateQuestionGroupConcept(field) {
    const conceptUUID = this.getConceptUUID(field.name);
    
    this.generatedConcepts.push({
      name: field.name,
      uuid: conceptUUID,
      dataType: 'QuestionGroup',
      answers: [],
      active: true
    });
    
    return conceptUUID;
  }
  
  // Generate all concepts from parsed fields
  generateFromFields(fields) {
    // Generate concepts for each field
    fields.forEach(field => {
      this.generateConcept(field);
    });
    
    // Sort: NA-type first, then by name
    this.generatedConcepts.sort((a, b) => {
      if (a.dataType === 'NA' && b.dataType !== 'NA') return -1;
      if (a.dataType !== 'NA' && b.dataType === 'NA') return 1;
      return a.name.localeCompare(b.name);
    });
    
    return this.generatedConcepts;
  }
  
  // Get confidence score for generation
  getConfidence() {
    const total = this.generatedConcepts.length;
    if (total === 0) return 0;
    
    let score = 0;
    this.generatedConcepts.forEach(c => {
      // Higher confidence for registry matches
      if (c.dataType === 'NA' && this.uuidRegistry[c.name]) {
        score += 1;  // Perfect match
      } else if (c.dataType === 'Coded') {
        const matchedAnswers = c.answers?.filter(a => this.uuidRegistry[a.name]).length || 0;
        score += 0.8 + (0.2 * matchedAnswers / (c.answers?.length || 1));
      } else {
        score += 0.9;  // Non-coded concepts
      }
    });
    
    return (score / total).toFixed(2);
  }
  
  // Export concepts.json
  toJSON() {
    return JSON.stringify(this.generatedConcepts, null, 2);
  }
}

module.exports = { ConceptGenerator };

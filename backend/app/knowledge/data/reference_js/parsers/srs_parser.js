/**
 * SRS CSV Parser
 * Parses Software Requirements Specification documents into structured format
 */

const fs = require('fs');
const path = require('path');

// Field type mapping from common SRS formats
const DATA_TYPE_MAP = {
  // Direct mappings
  'text': 'Text',
  'string': 'Text',
  'varchar': 'Text',
  'numeric': 'Numeric',
  'number': 'Numeric',
  'integer': 'Numeric',
  'int': 'Numeric',
  'decimal': 'Numeric',
  'float': 'Numeric',
  'date': 'Date',
  'datetime': 'DateTime',
  'boolean': 'Coded',  // Convert to Yes/No
  'bool': 'Coded',
  'image': 'ImageV2',
  'photo': 'ImageV2',
  'file': 'File',
  'audio': 'Audio',
  'video': 'Video',
  'notes': 'Notes',
  'phone': 'PhoneNumber',
  'location': 'Location',
  'duration': 'Duration',
  
  // Inferred mappings
  'single-select': 'Coded',
  'singleselect': 'Coded',
  'single select': 'Coded',
  'dropdown': 'Coded',
  'radio': 'Coded',
  'multi-select': 'Coded',
  'multiselect': 'Coded',
  'multi select': 'Coded',
  'checkbox': 'Coded',
  'coded': 'Coded',
  'questiongroup': 'QuestionGroup',
  'question group': 'QuestionGroup',
  'repeatable': 'QuestionGroup'
};

// Parse CSV content into rows
function parseCSV(content) {
  const lines = content.split('\n').filter(line => line.trim());
  if (lines.length === 0) return [];
  
  // Get headers
  const headers = parseCSVLine(lines[0]);
  
  // Parse data rows
  const rows = [];
  for (let i = 1; i < lines.length; i++) {
    const values = parseCSVLine(lines[i]);
    const row = {};
    headers.forEach((header, idx) => {
      row[normalizeHeader(header)] = values[idx] || '';
    });
    rows.push(row);
  }
  
  return rows;
}

// Parse a single CSV line (handles quoted fields)
function parseCSVLine(line) {
  const result = [];
  let current = '';
  let inQuotes = false;
  
  for (let i = 0; i < line.length; i++) {
    const char = line[i];
    
    if (char === '"') {
      inQuotes = !inQuotes;
    } else if (char === ',' && !inQuotes) {
      result.push(current.trim());
      current = '';
    } else {
      current += char;
    }
  }
  result.push(current.trim());
  
  return result;
}

// Normalize header names for consistent access
function normalizeHeader(header) {
  return header
    .toLowerCase()
    .replace(/[^a-z0-9]/g, '_')
    .replace(/_+/g, '_')
    .replace(/^_|_$/g, '');
}

// Infer data type from field info
function inferDataType(row) {
  // Check explicit type field
  const explicitType = (row.data_type || row.type || row.field_type || '').toLowerCase();
  if (DATA_TYPE_MAP[explicitType]) {
    return DATA_TYPE_MAP[explicitType];
  }
  
  // Check if has options (dropdown/coded)
  const options = row.options || row.answers || row.choices || '';
  if (options.includes(',') || options.includes(';')) {
    return 'Coded';
  }
  
  // Infer from field name
  const fieldName = (row.field || row.name || row.field_name || '').toLowerCase();
  if (fieldName.includes('date') && !fieldName.includes('update')) return 'Date';
  if (fieldName.includes('age') || fieldName.includes('weight') || fieldName.includes('height')) return 'Numeric';
  if (fieldName.includes('phone') || fieldName.includes('mobile')) return 'PhoneNumber';
  if (fieldName.includes('photo') || fieldName.includes('image')) return 'ImageV2';
  
  // Default to Text
  return 'Text';
}

// Parse options string into array
function parseOptions(optionsStr) {
  if (!optionsStr) return [];
  
  // Handle different delimiters
  const delimiter = optionsStr.includes(';') ? ';' : ',';
  return optionsStr
    .split(delimiter)
    .map(o => o.trim())
    .map(o => o.replace(/,+$/, ''))       // Strip trailing commas
    .map(o => o.trim())                   // Trim again after comma removal
    .filter(o => o.length > 0);
}

// Parse skip logic expression
function parseSkipLogic(skipLogic) {
  if (!skipLogic || skipLogic.trim() === '') return null;
  
  // Common patterns: "FieldName = Value", "FieldName == Value", "FieldName contains Value"
  const patterns = [
    /^(.+?)\s*[=]{1,2}\s*(.+)$/,      // equals
    /^(.+?)\s+contains\s+(.+)$/i,     // contains
    /^(.+?)\s*!=\s*(.+)$/,            // not equals
    /^show\s+when\s+(.+?)\s*[=]{1,2}\s*(.+)$/i  // explicit "show when"
  ];
  
  for (const pattern of patterns) {
    const match = skipLogic.match(pattern);
    if (match) {
      return {
        dependsOn: match[1].trim(),
        condition: skipLogic.includes('!=') ? 'notEquals' : 
                   skipLogic.toLowerCase().includes('contains') ? 'contains' : 'equals',
        value: match[2].trim().replace(/^["']|["']$/g, '')
      };
    }
  }
  
  return { raw: skipLogic };  // Unparsed, for manual review
}

// Parse validation rules
function parseValidation(validationStr) {
  if (!validationStr) return null;
  
  const validation = {};
  
  // Range pattern: "18-80" or "min:18,max:80"
  const rangeMatch = validationStr.match(/(\d+)\s*[-,]\s*(\d+)/);
  if (rangeMatch) {
    validation.min = parseInt(rangeMatch[1]);
    validation.max = parseInt(rangeMatch[2]);
  }
  
  // Min only: "min:18" or ">18"
  const minMatch = validationStr.match(/(?:min:|>)\s*(\d+)/i);
  if (minMatch) {
    validation.min = parseInt(minMatch[1]);
  }
  
  // Max only: "max:80" or "<80"
  const maxMatch = validationStr.match(/(?:max:|<)\s*(\d+)/i);
  if (maxMatch) {
    validation.max = parseInt(maxMatch[1]);
  }
  
  return Object.keys(validation).length > 0 ? validation : null;
}

// Main SRS parser function
function parseSRS(content, type = 'csv') {
  const rows = parseCSV(content);
  
  const fields = rows.map((row, index) => {
    const fieldName = row.field || row.name || row.field_name || row.question || `Field_${index + 1}`;
    const dataType = inferDataType(row);
    
    return {
      name: fieldName,
      dataType: dataType,
      options: dataType === 'Coded' ? parseOptions(row.options || row.answers || row.choices) : [],
      mandatory: ['yes', 'true', '1', 'required'].includes(
        (row.mandatory || row.required || '').toLowerCase()
      ),
      skipLogic: parseSkipLogic(row.skip_logic || row.skiplogic || row.conditional || row.show_when),
      validation: parseValidation(row.validation || row.range),
      description: row.description || row.help_text || '',
      group: row.group || row.section || row.form_group || null,
      order: parseInt(row.order || row.display_order) || index + 1
    };
  });
  
  return {
    fields,
    summary: {
      totalFields: fields.length,
      codedFields: fields.filter(f => f.dataType === 'Coded').length,
      numericFields: fields.filter(f => f.dataType === 'Numeric').length,
      mandatoryFields: fields.filter(f => f.mandatory).length,
      conditionalFields: fields.filter(f => f.skipLogic).length,
      groups: [...new Set(fields.map(f => f.group).filter(g => g))]
    }
  };
}

// Parse form metadata from SRS
function parseFormMetadata(content) {
  const rows = parseCSV(content);
  
  return rows.map(row => ({
    name: row.form_name || row.name || row.form,
    formType: mapFormType(row.form_type || row.type),
    program: row.program || null,
    encounterType: row.encounter_type || null,
    subjectType: row.subject_type || 'Individual',
    fields: row.fields_csv || null  // Reference to separate CSV
  }));
}

// Map SRS form type to AVNI form type
function mapFormType(type) {
  const typeMap = {
    'registration': 'IndividualProfile',
    'enrolment': 'ProgramEnrolment',
    'enrollment': 'ProgramEnrolment',
    'exit': 'ProgramExit',
    'encounter': 'ProgramEncounter',
    'visit': 'ProgramEncounter',
    'general encounter': 'Encounter',
    'cancellation': 'ProgramEncounterCancellation'
  };
  
  return typeMap[(type || '').toLowerCase()] || 'ProgramEncounter';
}

module.exports = {
  parseCSV,
  parseSRS,
  parseFormMetadata,
  inferDataType,
  parseOptions,
  parseSkipLogic,
  parseValidation,
  DATA_TYPE_MAP
};

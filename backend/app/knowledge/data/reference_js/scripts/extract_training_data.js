#!/usr/bin/env node
/**
 * Bundle Training Data Extractor
 * 
 * Extracts training data from production AVNI bundles:
 * - JavaScript rules (skip logic, calculations, validations)
 * - Dashboard/Report card patterns
 * - Address hierarchies
 * - Program eligibility rules
 * - Visit schedule rules
 * 
 * Usage:
 *   node extract_training_data.js <bundle_path>
 */

const fs = require('fs');
const path = require('path');

class BundleExtractor {
  constructor(bundlePath) {
    this.bundlePath = bundlePath;
    this.orgName = path.basename(bundlePath);
    this.rules = [];
    this.dashboards = [];
    this.addressHierarchies = [];
    this.programEligibility = [];
    this.visitSchedules = [];
    this.normalRanges = [];
    this.skipLogicPatterns = [];
  }

  extract() {
    console.log(`\n📦 Extracting training data from: ${this.orgName}`);
    console.log('═'.repeat(50));
    
    this.extractAddressHierarchy();
    this.extractProgramRules();
    this.extractFormRules();
    this.extractDashboards();
    
    return {
      org: this.orgName,
      rules: this.rules,
      dashboards: this.dashboards,
      addressHierarchies: this.addressHierarchies,
      programEligibility: this.programEligibility,
      visitSchedules: this.visitSchedules,
      normalRanges: this.normalRanges,
      skipLogicPatterns: this.skipLogicPatterns
    };
  }

  extractAddressHierarchy() {
    const file = path.join(this.bundlePath, 'addressLevelTypes.json');
    if (!fs.existsSync(file)) return;
    
    const data = JSON.parse(fs.readFileSync(file, 'utf8'));
    
    // Sort by level descending (highest level = top of hierarchy)
    const sorted = data.sort((a, b) => (b.level || 0) - (a.level || 0));
    const hierarchy = sorted.map(l => l.name);
    
    this.addressHierarchies.push({
      org: this.orgName,
      hierarchy: hierarchy,
      levels: data.map(l => ({
        name: l.name,
        level: l.level,
        uuid: l.uuid,
        parentUuid: l.parent?.uuid
      }))
    });
    
    console.log(`✓ Address Hierarchy: ${hierarchy.join(' → ')}`);
  }

  extractProgramRules() {
    const file = path.join(this.bundlePath, 'programs.json');
    if (!fs.existsSync(file)) return;
    
    const programs = JSON.parse(fs.readFileSync(file, 'utf8'));
    
    for (const prog of programs) {
      if (prog.voided) continue;
      
      const eligibility = {
        programName: prog.name,
        programUuid: prog.uuid
      };
      
      // Extract JS eligibility rule
      if (prog.enrolmentEligibilityCheckRule) {
        eligibility.jsRule = prog.enrolmentEligibilityCheckRule;
        this.rules.push({
          type: 'programEligibility',
          program: prog.name,
          rule: prog.enrolmentEligibilityCheckRule
        });
      }
      
      // Extract declarative eligibility rule
      if (prog.enrolmentEligibilityCheckDeclarativeRule) {
        eligibility.declarativeRule = prog.enrolmentEligibilityCheckDeclarativeRule;
      }
      
      if (eligibility.jsRule || eligibility.declarativeRule) {
        this.programEligibility.push(eligibility);
        console.log(`✓ Program Eligibility: ${prog.name}`);
      }
    }
  }

  extractFormRules() {
    const formsDir = path.join(this.bundlePath, 'forms');
    if (!fs.existsSync(formsDir)) return;
    
    const formFiles = fs.readdirSync(formsDir).filter(f => f.endsWith('.json'));
    
    for (const file of formFiles) {
      const form = JSON.parse(fs.readFileSync(path.join(formsDir, file), 'utf8'));
      
      // Extract visit schedule rule
      if (form.visitScheduleRule) {
        this.visitSchedules.push({
          formName: form.name,
          formType: form.formType,
          jsRule: form.visitScheduleRule
        });
        
        this.rules.push({
          type: 'visitSchedule',
          form: form.name,
          rule: form.visitScheduleRule
        });
        
        console.log(`✓ Visit Schedule Rule: ${form.name}`);
      }
      
      if (form.visitScheduleDeclarativeRule) {
        this.visitSchedules.push({
          formName: form.name,
          formType: form.formType,
          declarativeRule: form.visitScheduleDeclarativeRule
        });
      }
      
      // Extract form element rules
      if (form.formElementGroups) {
        for (const group of form.formElementGroups) {
          if (!group.formElements) continue;
          
          for (const element of group.formElements) {
            // JS Rule on element
            if (element.rule) {
              this.rules.push({
                type: 'formElement',
                form: form.name,
                group: group.name,
                element: element.name,
                concept: element.concept?.name,
                dataType: element.concept?.dataType,
                rule: element.rule
              });
              
              // Categorize rule type
              const ruleText = element.rule.toLowerCase();
              if (ruleText.includes('visibility')) {
                this.skipLogicPatterns.push({
                  form: form.name,
                  element: element.name,
                  rule: element.rule
                });
              }
            }
            
            // Declarative rule on element
            if (element.declarativeRule) {
              this.skipLogicPatterns.push({
                form: form.name,
                element: element.name,
                declarativeRule: element.declarativeRule
              });
            }
            
            // Extract normal ranges from numeric concepts
            if (element.concept?.dataType === 'Numeric') {
              const concept = element.concept;
              if (concept.lowNormal || concept.highNormal) {
                this.normalRanges.push({
                  conceptName: concept.name,
                  lowAbsolute: concept.lowAbsolute,
                  highAbsolute: concept.highAbsolute,
                  lowNormal: concept.lowNormal,
                  highNormal: concept.highNormal,
                  unit: concept.unit
                });
              }
            }
          }
        }
      }
    }
    
    console.log(`✓ Total Rules Extracted: ${this.rules.length}`);
    console.log(`✓ Skip Logic Patterns: ${this.skipLogicPatterns.length}`);
    console.log(`✓ Normal Ranges: ${this.normalRanges.length}`);
  }

  extractDashboards() {
    // Report Cards
    const cardsFile = path.join(this.bundlePath, 'reportCard.json');
    if (fs.existsSync(cardsFile)) {
      const cards = JSON.parse(fs.readFileSync(cardsFile, 'utf8'));
      
      for (const card of cards) {
        if (card.voided) continue;
        
        this.dashboards.push({
          type: 'reportCard',
          name: card.name,
          color: card.color,
          standardReportCardType: card.standardReportCardType,
          recentDuration: card.standardReportCardInputRecentDuration
        });
      }
      
      console.log(`✓ Report Cards: ${cards.filter(c => !c.voided).length}`);
    }
    
    // Report Dashboard
    const dashboardFile = path.join(this.bundlePath, 'reportDashboard.json');
    if (fs.existsSync(dashboardFile)) {
      const dashboards = JSON.parse(fs.readFileSync(dashboardFile, 'utf8'));
      
      for (const dashboard of dashboards) {
        if (dashboard.voided) continue;
        
        this.dashboards.push({
          type: 'reportDashboard',
          name: dashboard.name,
          sections: dashboard.sections?.filter(s => !s.voided).map(s => ({
            name: s.name,
            viewType: s.viewType,
            displayOrder: s.displayOrder,
            cardCount: s.dashboardSectionCardMappings?.length || 0
          })),
          filters: dashboard.filters?.filter(f => !f.voided).map(f => ({
            name: f.name,
            type: f.filterConfig?.type
          }))
        });
      }
      
      console.log(`✓ Dashboards: ${dashboards.filter(d => !d.voided).length}`);
    }
  }
}

// Main
function main() {
  const bundlePath = process.argv[2];
  
  if (!bundlePath) {
    console.log(`
Usage: node extract_training_data.js <bundle_path>

Example:
  node extract_training_data.js "/Users/samanvay/Downloads/All/avni-ai/JK Lakshmi Cement"
`);
    process.exit(1);
  }
  
  const extractor = new BundleExtractor(bundlePath);
  const data = extractor.extract();
  
  // Save extracted data
  const outputDir = path.join(__dirname, '..', 'training_data', 'extracted');
  fs.mkdirSync(outputDir, { recursive: true });
  
  const orgSlug = data.org.replace(/\s+/g, '-').toLowerCase();
  const outputFile = path.join(outputDir, `${orgSlug}.json`);
  
  fs.writeFileSync(outputFile, JSON.stringify(data, null, 2));
  
  console.log(`\n📁 Saved to: ${outputFile}`);
  console.log('\n═'.repeat(50));
  console.log('📊 EXTRACTION SUMMARY');
  console.log('═'.repeat(50));
  console.log(`   Total Rules: ${data.rules.length}`);
  console.log(`   Program Eligibility: ${data.programEligibility.length}`);
  console.log(`   Visit Schedules: ${data.visitSchedules.length}`);
  console.log(`   Skip Logic Patterns: ${data.skipLogicPatterns.length}`);
  console.log(`   Normal Ranges: ${data.normalRanges.length}`);
  console.log(`   Dashboard Items: ${data.dashboards.length}`);
  console.log('═'.repeat(50));
}

main();

#!/usr/bin/env node
/**
 * Advanced Excel Inspector
 * Displays full structure of Excel files for SRS analysis
 */

const XLSX = require('xlsx');
const path = require('path');

const files = process.argv.slice(2);

if (files.length === 0) {
  console.log('Usage: node inspect_excel_full.js <file1.xlsx> [file2.xlsx] ...');
  process.exit(1);
}

files.forEach(file => {
  console.log('\n' + '═'.repeat(80));
  console.log(`📊 FILE: ${path.basename(file)}`);
  console.log('═'.repeat(80));
  
  try {
    const workbook = XLSX.readFile(file);
    
    console.log(`\n📋 Sheets: ${workbook.SheetNames.length}`);
    console.log('─'.repeat(40));
    
    workbook.SheetNames.forEach((sheetName, idx) => {
      const sheet = workbook.Sheets[sheetName];
      const data = XLSX.utils.sheet_to_json(sheet, { defval: '', header: 1 });
      
      console.log(`\n[${idx + 1}] "${sheetName}" (${data.length} rows)`);
      
      // Show first 5 rows
      if (data.length > 0) {
        console.log('   Headers/First rows:');
        for (let i = 0; i < Math.min(5, data.length); i++) {
          const row = data[i];
          if (Array.isArray(row) && row.length > 0) {
            // Filter out empty cells and truncate long values
            const cells = row
              .map((cell, j) => cell ? `[${j}]${String(cell).substring(0, 30)}` : null)
              .filter(c => c !== null)
              .slice(0, 8);
            if (cells.length > 0) {
              console.log(`   Row ${i}: ${cells.join(' | ')}`);
            }
          }
        }
      }
    });
  } catch (e) {
    console.log(`Error reading file: ${e.message}`);
  }
});

console.log('\n');

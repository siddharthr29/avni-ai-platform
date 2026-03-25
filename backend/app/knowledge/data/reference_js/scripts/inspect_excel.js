#!/usr/bin/env node
/**
 * Inspect Excel structure to understand column names
 */

const XLSX = require('xlsx');
const INPUT_FILE = '/Users/samanvay/Downloads/All/avni-ai/PAD Adolescent Forms.xlsx';

const workbook = XLSX.readFile(INPUT_FILE);

console.log('📊 Excel Structure Analysis');
console.log('===========================\n');

workbook.SheetNames.forEach(sheetName => {
  const sheet = workbook.Sheets[sheetName];
  const data = XLSX.utils.sheet_to_json(sheet, { defval: '' });
  
  if (data.length > 0) {
    console.log(`\n📋 Sheet: "${sheetName}"`);
    console.log(`   Rows: ${data.length}`);
    console.log('   Columns:', Object.keys(data[0]));
    console.log('   First row sample:');
    Object.entries(data[0]).forEach(([key, value]) => {
      const val = String(value).substring(0, 50);
      console.log(`      "${key}": "${val}"`);
    });
  }
});

#!/usr/bin/env node
/**
 * zip_bundle.js
 *
 * Packages an srs-bundle-generator output directory into a ZIP file with files
 * inserted in the exact same order as BundleService.java createBundle(), so that
 * Avni processes them in the correct sequence on upload.
 *
 * Usage:
 *   node scripts/zip_bundle.js <output-dir>
 *
 * Example:
 *   node scripts/zip_bundle.js output/Mazi-Saheli
 *
 * Output:
 *   <output-dir>/<org-name>.zip
 *
 * Reference: BundleService.java createBundle() — files must be inserted into
 * the ZIP in this exact order for correct server-side processing.
 */

const fs = require('fs');
const path = require('path');
const zlib = require('zlib');

// ═══════════════════════════════════════════════════════════════════════════
// CANONICAL FILE ORDER (mirrors BundleService.java createBundle())
// ═══════════════════════════════════════════════════════════════════════════

const CANONICAL_ORDER = [
  // 1. Address hierarchy
  'addressLevelTypes.json',
  // (addressLevels.json and catchments.json are only included when includeLocations=true)

  // 2. Subject types
  'subjectTypes.json',
  'operationalSubjectTypes.json',

  // 3. Encounter types
  'encounterTypes.json',
  'operationalEncounterTypes.json',

  // 4. Programs
  'programs.json',
  'operationalPrograms.json',

  // 5. Concepts
  'concepts.json',

  // 6. Forms — all forms/*.json inserted here (see FORMS_SLOT below)
  '__FORMS__',

  // 7. Form mappings
  'formMappings.json',

  // 8. Organisation config
  'organisationConfig.json',

  // 9. Identity sources (skipped when no locations)
  // 'identifierSource.json',

  // 10. Relations
  'individualRelation.json',
  'relationshipType.json',

  // 11. Checklists
  'checklistDetail.json',

  // 12. Groups & privileges
  'groups.json',
  'groupRole.json',
  'groupPrivilege.json',

  // 13. Media/video
  'video.json',

  // 14. Dashboards
  'reportCard.json',
  'reportDashboard.json',
  'groupDashboards.json',

  // 15. Documentation
  'documentations.json',

  // 16. Task management
  'taskType.json',
  'taskStatus.json',

  // 17. Translations
  'translations.json',

  // 18. Rule dependency
  'ruleDependency.json',
];

// ═══════════════════════════════════════════════════════════════════════════
// ZIP WRITER (preserves insertion order — adm-zip sorts alphabetically)
// Implements the ZIP format spec manually using Node's built-in zlib so that
// central directory entries appear in exactly the order we add them.
// ═══════════════════════════════════════════════════════════════════════════

function uint16LE(n) {
  const b = Buffer.alloc(2);
  b.writeUInt16LE(n, 0);
  return b;
}

function uint32LE(n) {
  const b = Buffer.alloc(4);
  b.writeUInt32LE(n >>> 0, 0);
  return b;
}

function dosDateTime(date) {
  const d = date || new Date();
  const dosDate = ((d.getFullYear() - 1980) << 9) | ((d.getMonth() + 1) << 5) | d.getDate();
  const dosTime = (d.getHours() << 11) | (d.getMinutes() << 5) | Math.floor(d.getSeconds() / 2);
  return { dosDate, dosTime };
}

function crc32(buf) {
  const table = crc32.table || (crc32.table = (() => {
    const t = new Uint32Array(256);
    for (let i = 0; i < 256; i++) {
      let c = i;
      for (let j = 0; j < 8; j++) c = (c & 1) ? (0xEDB88320 ^ (c >>> 1)) : (c >>> 1);
      t[i] = c;
    }
    return t;
  })());
  let c = 0xFFFFFFFF;
  for (let i = 0; i < buf.length; i++) c = table[(c ^ buf[i]) & 0xFF] ^ (c >>> 8);
  return (c ^ 0xFFFFFFFF) >>> 0;
}

/**
 * Creates a ZIP buffer with entries in the exact insertion order provided.
 * @param {Array<{name: string, data: Buffer}>} entries
 * @returns {Buffer}
 */
function createOrderedZip(entries) {
  const localHeaders = [];
  const buffers = [];
  let offset = 0;

  const { dosDate, dosTime } = dosDateTime(new Date());

  for (const { name, data } of entries) {
    const nameBytes = Buffer.from(name, 'utf8');
    const compressed = zlib.deflateRawSync(data, { level: 6 });
    const crc = crc32(data);

    // Local file header signature + version needed + general purpose bit flag
    const localHeader = Buffer.concat([
      Buffer.from([0x50, 0x4B, 0x03, 0x04]), // local file header signature
      uint16LE(20),                           // version needed to extract (2.0)
      uint16LE(0),                            // general purpose bit flag
      uint16LE(8),                            // compression method: deflate
      uint16LE(dosTime),                      // last mod file time
      uint16LE(dosDate),                      // last mod file date
      uint32LE(crc),                          // crc-32
      uint32LE(compressed.length),            // compressed size
      uint32LE(data.length),                  // uncompressed size
      uint16LE(nameBytes.length),             // file name length
      uint16LE(0),                            // extra field length
      nameBytes,                              // file name
      compressed,                             // compressed data
    ]);

    localHeaders.push({
      name: nameBytes,
      crc,
      compressedSize: compressed.length,
      uncompressedSize: data.length,
      dosTime,
      dosDate,
      offset,
    });

    buffers.push(localHeader);
    offset += localHeader.length;
  }

  // Central directory
  const centralDirBuffers = [];
  for (const h of localHeaders) {
    const centralEntry = Buffer.concat([
      Buffer.from([0x50, 0x4B, 0x01, 0x02]), // central directory file header signature
      uint16LE(20),                           // version made by
      uint16LE(20),                           // version needed to extract
      uint16LE(0),                            // general purpose bit flag
      uint16LE(8),                            // compression method: deflate
      uint16LE(h.dosTime),                    // last mod file time
      uint16LE(h.dosDate),                    // last mod file date
      uint32LE(h.crc),                        // crc-32
      uint32LE(h.compressedSize),             // compressed size
      uint32LE(h.uncompressedSize),           // uncompressed size
      uint16LE(h.name.length),                // file name length
      uint16LE(0),                            // extra field length
      uint16LE(0),                            // file comment length
      uint16LE(0),                            // disk number start
      uint16LE(0),                            // internal file attributes
      uint32LE(0),                            // external file attributes
      uint32LE(h.offset),                     // relative offset of local header
      h.name,                                 // file name
    ]);
    centralDirBuffers.push(centralEntry);
  }

  const centralDir = Buffer.concat(centralDirBuffers);
  const centralDirSize = centralDir.length;
  const centralDirOffset = offset;

  // End of central directory record
  const eocd = Buffer.concat([
    Buffer.from([0x50, 0x4B, 0x05, 0x06]), // end of central dir signature
    uint16LE(0),                            // number of this disk
    uint16LE(0),                            // number of the disk with start of central dir
    uint16LE(entries.length),               // total entries on this disk
    uint16LE(entries.length),               // total entries in central dir
    uint32LE(centralDirSize),               // size of central dir
    uint32LE(centralDirOffset),             // offset of start of central dir
    uint16LE(0),                            // comment length
  ]);

  return Buffer.concat([...buffers, centralDir, eocd]);
}

// ═══════════════════════════════════════════════════════════════════════════
// MAIN
// ═══════════════════════════════════════════════════════════════════════════

function main() {
  const args = process.argv.slice(2);
  if (args.length === 0) {
    console.error('Usage: node scripts/zip_bundle.js <output-dir>');
    console.error('Example: node scripts/zip_bundle.js output/Mazi-Saheli');
    process.exit(1);
  }

  const outputDir = path.resolve(args[0]);

  if (!fs.existsSync(outputDir)) {
    console.error(`❌ Directory not found: ${outputDir}`);
    process.exit(1);
  }

  const orgName = path.basename(outputDir);
  const zipPath = path.join(outputDir, `${orgName}.zip`);

  console.log('\n📦 Avni Bundle Zipper');
  console.log('═'.repeat(55));
  console.log(`   Org:    ${orgName}`);
  console.log(`   Source: ${outputDir}`);
  console.log(`   Output: ${zipPath}`);
  console.log('═'.repeat(55) + '\n');

  let addedCount = 0;
  let skippedCount = 0;
  const zipEntries = [];

  // Resolve canonical order, expanding __FORMS__ to all forms/*.json
  const resolvedEntries = [];
  for (const entry of CANONICAL_ORDER) {
    if (entry === '__FORMS__') {
      const formsDir = path.join(outputDir, 'forms');
      if (fs.existsSync(formsDir)) {
        const formFiles = fs.readdirSync(formsDir)
          .filter(f => f.endsWith('.json'))
          .sort();
        for (const formFile of formFiles) {
          resolvedEntries.push({ zipName: `forms/${formFile}`, filePath: path.join(formsDir, formFile) });
        }
      }
    } else {
      resolvedEntries.push({ zipName: entry, filePath: path.join(outputDir, entry) });
    }
  }

  // Read present files in canonical order
  for (const { zipName, filePath } of resolvedEntries) {
    if (fs.existsSync(filePath)) {
      const data = fs.readFileSync(filePath);
      zipEntries.push({ name: zipName, data });
      console.log(`   ✓ ${zipName}`);
      addedCount++;
    } else {
      console.log(`   ⏭  ${zipName} (not present, skipped)`);
      skippedCount++;
    }
  }

  // Build ordered ZIP and write
  const zipBuffer = createOrderedZip(zipEntries);
  fs.writeFileSync(zipPath, zipBuffer);

  const zipSizeKb = (zipBuffer.length / 1024).toFixed(1);

  console.log('\n' + '═'.repeat(55));
  console.log('📊 SUMMARY');
  console.log('═'.repeat(55));
  console.log(`   Files added:   ${addedCount}`);
  console.log(`   Files skipped: ${skippedCount}`);
  console.log(`   ZIP size:      ${zipSizeKb} KB`);
  console.log(`   Output:        ${zipPath}`);
  console.log('═'.repeat(55));
  console.log('\n✅ Bundle ZIP ready for upload to Avni!\n');
}

main();

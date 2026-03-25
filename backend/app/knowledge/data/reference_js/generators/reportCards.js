/**
 * Report Card and Dashboard Generator
 *
 * Generates reportCard.json, reportDashboard.json, and groupDashboards.json
 * from a generic, org-agnostic dashboard specification.
 *
 * ## Custom Query Return Types
 *
 * Custom card queries receive `{ params, imports }` and can return:
 *
 * 1. **List of Subjects** — length shown as count, tap shows list
 *    ```js
 *    'use strict';
 *    ({params, imports}) => {
 *      return params.db.objects('Individual').filtered('voided = false AND subjectType.name = "MyType"');
 *    };
 *    ```
 *
 * 2. **Custom display object** — explicit primary/secondary values with drill-down
 *    ```js
 *    'use strict';
 *    ({params, imports}) => {
 *      return { primaryValue: '20', secondaryValue: '(5%)', lineListFunction: () => [...] };
 *    };
 *    ```
 *
 * 3. **Nested report card** — up to 9 sub-cards from a single query
 *    NOTE: nestedCount on the card spec MUST match the reportCards array length or Avni shows an error.
 *    ```js
 *    'use strict';
 *    ({params, imports}) => {
 *      return { reportCards: [
 *        { cardName: 'Label', cardColor: '#E7F3F8', textColor: '#000',
 *          primaryValue: count, secondaryValue: null,
 *          lineListFunction: () => [...] },
 *      ]};
 *    };
 *    ```
 *
 * ## Dashboard Filter Handling (params.ruleInput)
 *
 * When a dashboard has filters, apply them defensively:
 * ```js
 *   if (params.ruleInput) {
 *     const f = params.ruleInput.filter(r => r.type === 'Gender');
 *     if (f.length) result = result.filter(i => i.gender.name === f[0].filterValue[0].name);
 *   }
 * ```
 *
 * ## Performance Rules (from Avni offlineReports.md)
 *
 * - Prefer `filtered()` (Realm) over `.filter()` (JS) — Realm runs in C++.
 * - Use SUBQUERY for nested entity filtering (enrolments, encounters, observations).
 * - Avoid `findLatestObservationInEntireEnrolment` — scans all encounters.
 *   Use `lastFulfilledEncounter()` targeting specific encounter types instead.
 * - For chronological filtering (first/last of a type): query descendant entity,
 *   sort+Distinct, then `.map(e => e.individual)`.
 * - Coded observation matching: use SUBQUERY with $obs.valueJSON CONTAINS 'answerUUID'.
 * - Place `voided = false` early in the Realm query to reduce data before JS filtering.
 */

'use strict';

const fs = require('fs');
const path = require('path');
const { v4: uuidv4 } = require('uuid');

// Standard report card type UUIDs (Avni built-ins)
const STANDARD_CARD_TYPES = {
  TOTAL:                '1fbcadf3-bf1a-439e-9e13-24adddfbf6c0',
  RECENT_REGISTRATIONS: '88a7514c-48c0-4d5d-a421-d074e43bb36c',
  RECENT_ENROLMENTS:    'a5efc04c-317a-4823-a203-e62603454a65',
  RECENT_VISITS:        '77b5b3fa-de35-4f24-996b-2842492ea6e0',
  SCHEDULED_VISITS:     '27020b32-c21b-43a4-81bd-7b88ad3a6ef0',
  OVERDUE_VISITS:       '9f88bee5-2ab9-4ac4-ae19-d07e9715bdb5',
};

// Approved colour palette
const COLOURS = {
  BLUE:   '#E7F3F8',
  GREEN:  '#EBF8E7',
  YELLOW: '#F8F7E7',
  TEAL:   '#E7F8F6',
  PEACH:  '#F8EFE7',
  PURPLE: '#EBE7F8',
  PINK:   '#F8E7F1',
  GREY:   '#F3F3F4',
  INDIGO: '#E6EEFA',
  CYAN:   '#EBFCFE',
};

// Deterministic UUID from a seed string (mirrors bundle.js implementation)
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

class ReportCardGenerator {
  /**
   * @param {object} bundle - The bundle object from BundleGenerator, used to resolve
   *   subjectType/encounterType/group names → UUIDs.
   *   Expected shape: { subjectTypes, encounterTypes, programs, groups }
   */
  constructor(bundle) {
    this.bundle = bundle;
    this.reportCards = [];
    this.dashboards = [];
    this.groupDashboards = [];
  }

  // ─── Internal helpers ────────────────────────────────────────────────────────

  _resolveColor(colorKey) {
    if (!colorKey) return '#ffffff';
    // Allow passing a raw hex value directly
    if (colorKey.startsWith('#')) return colorKey;
    return COLOURS[colorKey.toUpperCase()] || colorKey;
  }

  _resolveSubjectTypeUUIDs(names) {
    if (!names || !names.length) return [];
    return names.map(name => {
      const found = this.bundle.subjectTypes.find(st => st.name === name);
      if (!found) throw new Error(`ReportCardGenerator: subjectType "${name}" not found in bundle`);
      return found.uuid;
    });
  }

  _resolveEncounterTypeUUIDs(names) {
    if (!names || !names.length) return [];
    return names.map(name => {
      const found = this.bundle.encounterTypes.find(et => et.name === name);
      if (!found) throw new Error(`ReportCardGenerator: encounterType "${name}" not found in bundle`);
      return found.uuid;
    });
  }

  _resolveProgramUUIDs(names) {
    if (!names || !names.length) return [];
    return names.map(name => {
      const found = this.bundle.programs.find(p => p.name === name);
      if (!found) throw new Error(`ReportCardGenerator: program "${name}" not found in bundle`);
      return found.uuid;
    });
  }

  _resolveGroupUUID(name) {
    const found = this.bundle.groups.find(g => g.name === name);
    if (!found) throw new Error(`ReportCardGenerator: group "${name}" not found in bundle`);
    return found.uuid;
  }

  _findCardByName(name) {
    const found = this.reportCards.find(c => c.name === name);
    if (!found) throw new Error(`ReportCardGenerator: report card "${name}" not found — add it before referencing`);
    return found;
  }

  // ─── Public API ──────────────────────────────────────────────────────────────

  /**
   * Add a standard report card.
   * Standard types support SubjectType, Program, EncounterType, and RecentDuration filters.
   *
   * @param {string}   name
   * @param {string}   [description]
   * @param {string}   color       - Key from COLOURS or a raw hex string
   * @param {string}   cardType    - Key from STANDARD_CARD_TYPES (e.g. 'TOTAL', 'RECENT_VISITS')
   * @param {string[]} [subjectTypes]   - Subject type names (resolved to UUIDs)
   * @param {string[]} [programs]       - Program names (resolved to UUIDs)
   * @param {string[]} [encounterTypes] - Encounter type names (resolved to UUIDs)
   * @param {number}   [recentDays]     - For RECENT_* types: number of days
   */
  addStandardCard({ name, description, color, cardType, subjectTypes, programs, encounterTypes, recentDays }) {
    const typeUUID = STANDARD_CARD_TYPES[cardType];
    if (!typeUUID) throw new Error(`ReportCardGenerator: unknown cardType "${cardType}". Valid keys: ${Object.keys(STANDARD_CARD_TYPES).join(', ')}`);

    const card = {
      uuid: generateDeterministicUUID(`reportCard:${name}`),
      name,
      color: this._resolveColor(color),
      nested: false,
      count: 1,
      standardReportCardType: typeUUID,
      standardReportCardInputSubjectTypes: this._resolveSubjectTypeUUIDs(subjectTypes),
      standardReportCardInputPrograms: this._resolveProgramUUIDs(programs),
      standardReportCardInputEncounterTypes: this._resolveEncounterTypeUUIDs(encounterTypes),
      voided: false,
    };

    if (description) card.description = description;

    if (recentDays != null) {
      card.standardReportCardInputRecentDuration = JSON.stringify({ value: String(recentDays), unit: 'days' });
    }

    this.reportCards.push(card);
    return card;
  }

  /**
   * Add a custom query report card.
   *
   * CRITICAL: query strings must use literal \n (not \\n).
   * The query field is written verbatim into JSON — double-escaped newlines
   * cause an "invalid Unicode escape" error on the Avni client.
   *
   * @param {string}  name
   * @param {string}  [description]
   * @param {string}  color       - Key from COLOURS or a raw hex string
   * @param {string}  query       - Inline JS query function (see module JSDoc for return type examples)
   * @param {number}  [nestedCount] - For nested-card queries: number of sub-cards the query returns.
   *                                  Must match the reportCards array length returned at runtime.
   */
  addCustomCard({ name, description, color, query, nestedCount }) {
    const card = {
      uuid: generateDeterministicUUID(`reportCard:${name}`),
      name,
      query,
      color: this._resolveColor(color),
      nested: nestedCount != null && nestedCount > 1,
      count: nestedCount != null ? nestedCount : 1,
      standardReportCardInputSubjectTypes: [],
      standardReportCardInputPrograms: [],
      standardReportCardInputEncounterTypes: [],
      voided: false,
    };

    if (description) card.description = description;

    this.reportCards.push(card);
    return card;
  }

  /**
   * Create a dashboard with sections. Cards in each section are referenced by name
   * (must have been added via addStandardCard/addCustomCard before calling this).
   *
   * @param {string} name
   * @param {string} [description]
   * @param {Array}  sections  - [{ name, description, viewType, cards: [cardName, ...] }]
   *                             viewType: 'Tile' (default) | 'Default'
   * @param {Array}  [filters] - Pre-built filter objects to attach at the dashboard level.
   *                             Filters at card level take precedence over dashboard-level filters
   *                             for the same type — avoid mixing the same type at both levels.
   */
  addDashboard({ name, description, sections = [], filters = [] }) {
    const dashboardUUID = generateDeterministicUUID(`dashboard:${name}`);

    const builtSections = sections.map((section, sectionIdx) => {
      const sectionUUID = generateDeterministicUUID(`dashboardSection:${name}:${section.name}`);

      const cardMappings = (section.cards || []).map((cardName, cardIdx) => {
        const card = this._findCardByName(cardName);
        return {
          uuid: generateDeterministicUUID(`cardMapping:${name}:${section.name}:${cardName}`),
          displayOrder: cardIdx + 1.0,
          dashboardSectionUUID: sectionUUID,
          reportCardUUID: card.uuid,
          voided: false,
        };
      });

      return {
        uuid: sectionUUID,
        name: section.name,
        description: section.description || '',
        viewType: section.viewType || 'Tile',
        displayOrder: sectionIdx + 1.0,
        dashboardUUID,
        dashboardSectionCardMappings: cardMappings,
        voided: false,
      };
    });

    const dashboard = {
      uuid: dashboardUUID,
      name,
      description: description || '',
      sections: builtSections,
      filters,
      voided: false,
    };

    this.dashboards.push(dashboard);
    return dashboard;
  }

  /**
   * Link a dashboard to a user group.
   *
   * @param {string}  groupName         - Resolved via this.bundle.groups
   * @param {string}  dashboardName     - Must have been added via addDashboard
   * @param {boolean} [primaryDashboard=false]   - Show as home dashboard for this group
   * @param {boolean} [secondaryDashboard=false] - Show in bottom drawer (requires Avni ≥ 8.0.0)
   * @param {boolean} [groupOneOfTheDefaultGroups=false]
   *
   * NOTE: If a user belongs to multiple groups with different primary/secondary dashboards
   * the behaviour is non-deterministic — assign at most one primary per user.
   */
  addGroupDashboard({ groupName, dashboardName, primaryDashboard = false, secondaryDashboard = false, groupOneOfTheDefaultGroups = false }) {
    const groupUUID = this._resolveGroupUUID(groupName);
    const dashboard = this.dashboards.find(d => d.name === dashboardName);
    if (!dashboard) throw new Error(`ReportCardGenerator: dashboard "${dashboardName}" not found — call addDashboard first`);

    this.groupDashboards.push({
      uuid: generateDeterministicUUID(`groupDashboard:${groupName}:${dashboardName}`),
      voided: false,
      dashboardUUID: dashboard.uuid,
      groupUUID,
      groupName,
      dashboardName,
      dashboardDescription: dashboard.description || null,
      groupOneOfTheDefaultGroups,
      primaryDashboard,
      secondaryDashboard,
    });
  }

  /**
   * Write reportCard.json, reportDashboard.json, and groupDashboards.json to outputDir.
   */
  exportToDirectory(outputDir) {
    fs.writeFileSync(
      path.join(outputDir, 'reportCard.json'),
      JSON.stringify(this.reportCards, null, 2)
    );
    fs.writeFileSync(
      path.join(outputDir, 'reportDashboard.json'),
      JSON.stringify(this.dashboards, null, 2)
    );
    fs.writeFileSync(
      path.join(outputDir, 'groupDashboards.json'),
      JSON.stringify(this.groupDashboards, null, 2)
    );
  }
}

module.exports = { ReportCardGenerator, STANDARD_CARD_TYPES, COLOURS };

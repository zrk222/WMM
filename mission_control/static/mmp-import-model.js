/* Client-side header suggestions for an owner-supplied MMP export; no provider access. */
const WMMMmpImport = (() => {
  const aliases = {
    install_id: ['install_id', 'customer_user_id', 'app_user_id', 'user_id'],
    state: ['state', 'attribution_status', 'attribution', 'status'],
    occurred_at: ['occurred_at', 'install_time', 'install_date', 'event_time', 'timestamp'],
  };

  function csvLine(line) {
    const values = [];
    let value = '',
      quoted = false;
    for (let index = 0; index < line.length; index++) {
      const char = line[index];
      if (char === '"' && quoted && line[index + 1] === '"') {
        value += '"';
        index++;
      } else if (char === '"') quoted = !quoted;
      else if (char === ',' && !quoted) {
        values.push(value.trim());
        value = '';
      } else value += char;
    }
    values.push(value.trim());
    return values.filter((item, position, list) => item !== '' || position < list.length - 1);
  }

  function parseHeaders(text, format) {
    if (typeof text !== 'string' || !text.trim())
      throw new Error('Choose a non-empty export file.');
    if (format === 'json') {
      let value;
      try {
        value = JSON.parse(text);
      } catch {
        throw new Error('This file is not valid JSON.');
      }
      const rows = Array.isArray(value)
        ? value
        : Array.isArray(value?.rows)
          ? value.rows
          : Array.isArray(value?.installs)
            ? value.installs
            : value && typeof value === 'object'
              ? [value]
              : [];
      if (
        !rows.length ||
        rows[0] === null ||
        typeof rows[0] !== 'object' ||
        Array.isArray(rows[0])
      ) {
        throw new Error('The JSON export must contain objects with column names.');
      }
      return Object.keys(rows[0]);
    }
    return csvLine(text.replace(/^\uFEFF/, '').split(/\r?\n/, 1)[0]);
  }

  function suggest(headers) {
    const normalized = headers.map((header) => ({
      header,
      key: String(header)
        .trim()
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, '_'),
    }));
    const value = {},
      used = new Set();
    for (const [target, names] of Object.entries(aliases)) {
      const match = normalized.find((row) => !used.has(row.header) && names.includes(row.key));
      if (match) {
        value[target] = match.header;
        used.add(match.header);
      }
    }
    return {
      mapping: value,
      unmapped: headers.filter((header) => !used.has(header)),
      confidence:
        Object.keys(value).length === 3
          ? 'ALL_THREE'
          : Object.keys(value).length
            ? 'PARTIAL'
            : 'NONE',
    };
  }

  function templateCsv() {
    return 'install_id,state,occurred_at\nopaque-install-1,ATTRIBUTED,2026-11-01T12:00:00Z\n';
  }

  return { parseHeaders, suggest, templateCsv, aliases };
})();

if (typeof module !== 'undefined') module.exports = WMMMmpImport;

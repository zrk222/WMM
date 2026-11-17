/** @typedef {'pages'|'queries'} ReportMode */
/**
 * @typedef {object} OpenSEOScope
 * @property {string} website
 * @property {string} territory
 * @property {string} release
 * @property {string} locale
 * @property {ReportMode} report_mode
 */

/**
 * Keep the browser's OpenSEO scope explicit; the server revalidates authority.
 * @param {Record<string, FormDataEntryValue>} values
 * @returns {OpenSEOScope}
 */
export function openSEOScope(values) {
  const mode = values.report_mode;
  if (mode !== 'pages' && mode !== 'queries')
    throw new Error('Choose page totals or aggregate queries before connecting.');
  /** @type {OpenSEOScope} */
  const result = {
    website: String(values.website || ''),
    territory: String(values.territory || ''),
    release: String(values.release || ''),
    locale: String(values.locale || ''),
    report_mode: mode,
  };
  if (!result.website || !result.release || !result.locale)
    throw new Error('Set this app’s website, release and locale before connecting.');
  return result;
}

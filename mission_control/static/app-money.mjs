import { CURRENCY_DIGITS } from './currency-profile.mjs';

export function money(value, currency, locale) {
  if (typeof value !== 'number' || !Number.isFinite(value)) return 'Unavailable';
  if (typeof currency !== 'string' || !Object.hasOwn(CURRENCY_DIGITS, currency)) {
    return `${value} minor units (currency unavailable)`;
  }
  const digits = CURRENCY_DIGITS[currency];
  const maximumFractionDigits = Number.isInteger(value) ? digits : Math.min(20, digits + 6);
  if (value !== 0 && Math.abs(value) < 0.5 * 10 ** (digits - maximumFractionDigits)) {
    // Below display precision, retain the supplied estimate in raw units.
    return `${value} minor units (${currency}; fractional estimate)`;
  }
  return new Intl.NumberFormat(locale, {
    style: 'currency',
    currency,
    currencyDisplay: 'code',
    minimumFractionDigits: digits,
    // CAC can be an estimate containing fractional minor units; keep that precision.
    maximumFractionDigits,
  }).format(value / 10 ** digits);
}

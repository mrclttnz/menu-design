// Date, ore e numeri solo con Intl (ADR-0009, ADR-0010): locale come parametro (predefinito
// it-IT) e fuso della famiglia, mai quello del dispositivo. Le date di calendario sono stringhe
// AAAA-MM-GG senza fuso e si formattano in UTC per non scivolare di giorno.
export const FORMAT_LOCALE = "it-IT";

const CALENDAR_DATE = /^(\d{4})-(\d{2})-(\d{2})$/;
// eslint-disable-next-line security/detect-unsafe-regex -- ripetizioni limitate, nessun backtracking
const INSTANT = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2}(?:\.\d{1,9})?)?(?:Z|[+-]\d{2}:\d{2})$/;

function calendarDate(value: string): Date {
  const match = CALENDAR_DATE.exec(value);
  if (!match) throw new RangeError("data di calendario non valida");
  const [year, month, day] = [Number(match[1]), Number(match[2]), Number(match[3])];
  const date = new Date(Date.UTC(year, month - 1, day));
  if (
    date.getUTCFullYear() !== year ||
    date.getUTCMonth() !== month - 1 ||
    date.getUTCDate() !== day
  ) {
    throw new RangeError("data di calendario inesistente");
  }
  return date;
}

function instant(value: Date | string): Date {
  let date: Date;
  if (value instanceof Date) date = value;
  else if (INSTANT.test(value)) date = new Date(value);
  else throw new RangeError("istante non valido (serve data, ora e fuso)");
  if (Number.isNaN(date.getTime())) throw new RangeError("istante non valido");
  return date;
}

const utc = (locale: string, options: Intl.DateTimeFormatOptions): Intl.DateTimeFormat =>
  new Intl.DateTimeFormat(locale, { ...options, timeZone: "UTC" });

export function formatRange(startIso: string, endIso: string, locale = FORMAT_LOCALE): string {
  const start = calendarDate(startIso);
  const end = calendarDate(endIso);
  const full = utc(locale, { day: "numeric", month: "long", year: "numeric" });
  if (start.getTime() === end.getTime()) return full.format(start);
  const sameYear = start.getUTCFullYear() === end.getUTCFullYear();
  if (!sameYear) return `${full.format(start)} - ${full.format(end)}`;
  if (start.getUTCMonth() === end.getUTCMonth()) {
    const day = utc(locale, { day: "numeric" });
    return `${day.format(start)} - ${full.format(end)}`;
  }
  const dayMonth = utc(locale, { day: "numeric", month: "long" });
  return `${dayMonth.format(start)} - ${full.format(end)}`;
}

export function formatDayHeading(isoDate: string, locale = FORMAT_LOCALE): string {
  const date = calendarDate(isoDate);
  const weekday = utc(locale, { weekday: "long" }).format(date);
  const day = utc(locale, { day: "numeric" }).format(date);
  const capitalized = weekday.charAt(0).toLocaleUpperCase(locale) + weekday.slice(1);
  return `${capitalized} ${day}`;
}

export function formatTime(value: Date | string, timeZone: string, locale = FORMAT_LOCALE): string {
  return new Intl.DateTimeFormat(locale, {
    timeZone,
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).format(instant(value));
}

export function formatDateTime(
  value: Date | string,
  timeZone: string,
  locale = FORMAT_LOCALE,
): string {
  const date = instant(value);
  const day = new Intl.DateTimeFormat(locale, {
    timeZone,
    day: "numeric",
    month: "long",
    year: "numeric",
  }).format(date);
  return `${day}, ${formatTime(date, timeZone, locale)}`;
}

export function formatNumber(value: number, locale = FORMAT_LOCALE): string {
  return new Intl.NumberFormat(locale, { useGrouping: "always" }).format(value);
}

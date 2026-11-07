// Date di calendario del piano: stringhe AAAA-MM-GG senza fuso, calcolate in UTC per non
// scivolare di giorno (ADR-0009). Il «oggi» della famiglia lo dà sempre il server.
import type { DateRange } from "../api/plan";

export const MAX_DAYS = 62;
const DAY_MS = 86_400_000;
const ISO = /^(\d{4})-(\d{2})-(\d{2})$/;

/** Millisecondi UTC della mezzanotte di una data valida, altrimenti `null`. */
export function toUtc(iso: unknown): number | null {
  if (typeof iso !== "string") return null;
  const match = ISO.exec(iso);
  if (!match) return null;
  const [year, month, day] = [Number(match[1]), Number(match[2]), Number(match[3])];
  const time = Date.UTC(year, month - 1, day);
  const date = new Date(time);
  const exact =
    date.getUTCFullYear() === year && date.getUTCMonth() === month - 1 && date.getUTCDate() === day;
  return exact && year >= 1 ? time : null;
}

export const isIsoDate = (value: unknown): value is string => toUtc(value) !== null;

function mustUtc(iso: string): number {
  const time = toUtc(iso);
  if (time === null) throw new RangeError("data non valida");
  return time;
}

export function addDays(iso: string, days: number): string {
  const time = mustUtc(iso);
  return new Date(time + days * DAY_MS).toISOString().slice(0, 10);
}

/** Numero di giorni dell'intervallo, estremi compresi. */
export function dayCount(range: DateRange): number {
  return Math.round((mustUtc(range.to) - mustUtc(range.from)) / DAY_MS) + 1;
}

export type RangeProblem = "date" | "order" | "size";

/** Controllo dell'intervallo (D-05): date valide, fine non prima dell'inizio, al massimo 62 giorni. */
export function checkRange(from: string, to: string): RangeProblem | null {
  if (!isIsoDate(from) || !isIsoDate(to)) return "date";
  if (to < from) return "order";
  if (dayCount({ from, to }) > MAX_DAYS) return "size";
  return null;
}

/** Lunedì-domenica della settimana che contiene `iso`. */
export function weekOf(iso: string): DateRange {
  const time = mustUtc(iso);
  const sinceMonday = (new Date(time).getUTCDay() + 6) % 7;
  const from = addDays(iso, -sinceMonday);
  return { from, to: addDays(from, 6) };
}

/** Intervallo dell'indirizzo (`?da=&a=`): vale solo se completo e valido, altrimenti si ignora. */
export function rangeFromSearch(params: URLSearchParams): DateRange | null {
  const from = params.get("da");
  const to = params.get("a");
  if (from === null || to === null) return null;
  return checkRange(from, to) === null ? { from, to } : null;
}

/** Spostamento di «‹» e «›»: la lunghezza dell'intervallo (7 giorni per una settimana). */
export function shifted(range: DateRange, direction: -1 | 1): DateRange {
  const step = dayCount(range) * direction;
  return { from: addDays(range.from, step), to: addDays(range.to, step) };
}

// `pastoId` (ADR-0009): identificativo solo del client, biunivoco con (mealType, slot).
// Slot 0: solo il nome italiano (`cena`); slot 1-4 solo per «altro»: `altro-2`.
export type MealType = "breakfast" | "lunch" | "snack" | "dinner" | "other";

const NAMES: Record<MealType, string> = {
  breakfast: "colazione",
  lunch: "pranzo",
  snack: "merenda",
  dinner: "cena",
  other: "altro",
};
const MAX_OTHER_SLOT = 4;
const BY_NAME: Record<string, MealType> = {
  colazione: "breakfast",
  pranzo: "lunch",
  merenda: "snack",
  cena: "dinner",
  altro: "other",
};
const PATTERN = /^(colazione|pranzo|merenda|cena|altro)(?:-([1-4]))?$/;

export function toPastoId(mealType: MealType, slot: number): string {
  if (!Object.hasOwn(NAMES, mealType)) throw new RangeError("tipo di pasto sconosciuto");
  if (!Number.isInteger(slot) || slot < 0) throw new RangeError("slot non valido");
  if (slot === 0) return NAMES[mealType];
  if (mealType !== "other" || slot > MAX_OTHER_SLOT) throw new RangeError("slot non valido");
  return `${NAMES[mealType]}-${slot}`;
}

export function fromPastoId(input: unknown): { mealType: MealType; slot: number } | null {
  if (typeof input !== "string") return null;
  const match = PATTERN.exec(input);
  if (!match) return null;
  const [, name, suffix] = match;
  const mealType = BY_NAME[name as string] as MealType;
  if (suffix !== undefined && mealType !== "other") return null;
  return { mealType, slot: suffix === undefined ? 0 : Number(suffix) };
}

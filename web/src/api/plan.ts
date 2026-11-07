// Piano e pasti (SL-06a): percorsi, tipi dallo schema generato e chiavi di catalogo. La UI
// (features/plan) usa solo queste funzioni.
import { api, type ApiResult } from "./client";
import type { components } from "./schema.gen";

export type PlanView = components["schemas"]["PlanView"];
export type DayView = components["schemas"]["DayView"];
export type MealView = components["schemas"]["MealView"];
export type MealItemView = components["schemas"]["MealItemView"];
export type MealType = MealView["mealType"];
export type Special = NonNullable<MealView["special"]>;

export const PLAN_KEY = ["plan"] as const;
export const planKey = (range: DateRange | null): readonly unknown[] => [
  ...PLAN_KEY,
  range?.from ?? null,
  range?.to ?? null,
];
export const mealKey = (date: string, type: MealType, slot: number): readonly unknown[] => [
  "meal",
  date,
  type,
  slot,
];

export interface DateRange {
  from: string;
  to: string;
}

/** Ordine in cui i tipi di pasto compaiono in un giorno e nell'elenco di D-07. */
export const MEAL_TYPES: MealType[] = ["breakfast", "lunch", "snack", "dinner", "other"];

export const MEAL_TYPE_KEYS: Record<MealType, string> = {
  breakfast: "meal.type.breakfast",
  lunch: "meal.type.lunch",
  snack: "meal.type.snack",
  dinner: "meal.type.dinner",
  other: "meal.type.other",
};

export const SPECIAL_KEYS: Record<Special, string> = {
  away: "meal.special.out",
  restaurant: "meal.special.restaurant",
  skipped: "meal.special.skipped",
};

export function readPlan(
  range: DateRange | null,
  signal?: AbortSignal,
): Promise<ApiResult<PlanView>> {
  const query = range
    ? `?${new URLSearchParams({ from: range.from, to: range.to }).toString()}`
    : "";
  return api.get<PlanView>(`/api/v1/plan${query}`, signal ? { signal } : {});
}

const mealPath = (date: string, type: MealType, slot: number): string =>
  `/api/v1/meals/${encodeURIComponent(date)}/${encodeURIComponent(type)}/${slot}`;

export const readMeal = (
  date: string,
  type: MealType,
  slot: number,
): Promise<ApiResult<MealView>> => api.get<MealView>(mealPath(date, type, slot));

/** Aggiunge (`true`) o toglie (`false`) il pasto di quel giorno; `version` è quella letta (ADR-0008). */
export function setPresence(
  date: string,
  type: MealType,
  slot: number,
  version: number,
  present: boolean,
): Promise<ApiResult<MealView>> {
  const body: components["schemas"]["PresenceChange"] = { present };
  return api.put<MealView>(`${mealPath(date, type, slot)}/presence`, { body, ifMatch: version });
}

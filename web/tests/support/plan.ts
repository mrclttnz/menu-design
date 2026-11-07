// Dati simulati del piano (SL-06a) con le forme di docs/07-plan.md §4.2 (PlanView, MealView,
// MealItem). Dati sintetici. Il «oggi» della famiglia è venerdì 2026-10-23 (come `authenticated()`).
import { json, type Handler } from "./fake-api";

export const PLAN_ROUTE = "GET /api/v1/plan";
export const mealRoute = (date: string, type: string, slot = 0): string =>
  `GET /api/v1/meals/${date}/${type}/${slot}`;
export const presenceRoute = (date: string, type: string, slot = 0): string =>
  `PUT /api/v1/meals/${date}/${type}/${slot}/presence`;

export type MealType = "breakfast" | "lunch" | "snack" | "dinner" | "other";

export interface MealItemFixture {
  id: string;
  kind: "dish" | "free_text";
  position: number;
  dishId?: string;
  courseId?: string;
  freeText?: string;
  notCooked: boolean;
}

export interface MealFixture {
  date: string;
  mealType: MealType;
  slot: number;
  name: string | null;
  present: boolean;
  special: "away" | "restaurant" | "skipped" | null;
  contentVersion: number;
  items: MealItemFixture[];
  past: boolean;
}

export const TODAY = "2026-10-23";

export function meal(
  date: string,
  mealType: MealType,
  over: Partial<MealFixture> = {},
): MealFixture {
  return {
    date,
    mealType,
    slot: 0,
    name: null,
    present: true,
    special: null,
    contentVersion: 0,
    items: [],
    past: date < TODAY,
    ...over,
  };
}

export function dishItem(
  dishId: string,
  position = 0,
  over: Partial<MealItemFixture> = {},
): MealItemFixture {
  return {
    id: `a0000000-0000-4000-8000-${String(position + 1).padStart(12, "0")}`,
    kind: "dish",
    position,
    dishId,
    courseId: "c0000000-0000-4000-8000-000000000002",
    notCooked: false,
    ...over,
  };
}

export const textItem = (text: string, position = 0): MealItemFixture => ({
  id: `b0000000-0000-4000-8000-${String(position + 1).padStart(12, "0")}`,
  kind: "free_text",
  position,
  freeText: text,
  notCooked: false,
});

export function addDays(date: string, days: number): string {
  const d = new Date(`${date}T12:00:00Z`);
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}

export interface PlanOptions {
  from?: string;
  to?: string;
  /** Pasti per giorno; di default pranzo e cena. */
  meals?: (date: string) => MealFixture[];
  dishes?: Record<string, { name: string; status: "to_try" | "tested"; archived: boolean }>;
}

export function planView(options: PlanOptions = {}): Record<string, unknown> {
  const from = options.from ?? "2026-10-19";
  const to = options.to ?? "2026-10-25";
  const days: Array<{ date: string; meals: MealFixture[] }> = [];
  for (let date = from; date <= to; date = addDays(date, 1)) {
    days.push({
      date,
      meals: options.meals ? options.meals(date) : [meal(date, "lunch"), meal(date, "dinner")],
    });
  }
  return {
    from,
    to,
    today: TODAY,
    timezone: "Europe/Rome",
    days,
    refs: { dishes: options.dishes ?? {}, courses: {} },
  };
}

export const planHandler =
  (options: PlanOptions = {}): Handler =>
  () =>
    json(planView(options));

export function mealResponse(fixture: MealFixture): Response {
  return new Response(JSON.stringify(fixture), {
    status: 200,
    headers: { "Content-Type": "application/json", ETag: `"${fixture.contentVersion}"` },
  });
}

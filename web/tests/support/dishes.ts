// Dati simulati dell'archivio piatti (SL-04) con le forme di docs/07-plan.md §4.2
// (Course, DishSummary, DishDetail, Problem). Dati sintetici, nessun dato reale.
import { json, type Handler } from "./fake-api";
import { problemResponse } from "./problem";

export const COURSES = [
  { id: "c0000000-0000-4000-8000-000000000001", baseCode: "starter", name: null },
  { id: "c0000000-0000-4000-8000-000000000002", baseCode: "first", name: null },
  { id: "c0000000-0000-4000-8000-000000000003", baseCode: "second", name: null },
  { id: "c0000000-0000-4000-8000-000000000004", baseCode: "side", name: null },
  { id: "c0000000-0000-4000-8000-000000000005", baseCode: "one_dish", name: null },
  { id: "c0000000-0000-4000-8000-000000000006", baseCode: "dessert", name: null },
  { id: "c0000000-0000-4000-8000-000000000007", baseCode: "drink", name: null },
  { id: "c0000000-0000-4000-8000-000000000008", baseCode: "other", name: null },
] as const;

export const COURSE_LABEL: Record<string, string> = {
  starter: "Antipasto",
  first: "Primo",
  second: "Secondo",
  side: "Contorno",
  one_dish: "Piatto unico",
  dessert: "Dolce",
  drink: "Bevanda",
  other: "Altro",
};

export const courseId = (code: string): string =>
  COURSES.find((c) => c.baseCode === code)?.id as string;

export interface DishFixture {
  id: string;
  name: string;
  status: "to_try" | "tested";
  courseIds: string[];
  prepTime?: "under_30" | "30_60" | "over_60";
  archived: boolean;
  everPlanned: boolean;
  notes?: string;
  sources?: Array<{ kind: string; reference: string; page?: string; note?: string }>;
  createdBy?: string;
  version?: number;
}

export function dish(over: Partial<DishFixture> & { name: string }): DishFixture {
  return {
    id: over.id ?? `d0000000-0000-4000-8000-${String(Math.abs(hash(over.name))).padStart(12, "0")}`,
    status: "to_try",
    courseIds: [courseId("first")],
    archived: false,
    everPlanned: false,
    createdBy: "0b3a1f0e-6f4e-4b57-8d2c-5a6b7c8d9e0f",
    version: 1,
    ...over,
  };
}

function hash(text: string): number {
  let h = 7;
  for (const ch of text) h = (h * 31 + ch.charCodeAt(0)) % 999_999_999_999;
  return h;
}

export const summary = (d: DishFixture): Record<string, unknown> => ({
  id: d.id,
  name: d.name,
  status: d.status,
  courseIds: d.courseIds,
  archived: d.archived,
  everPlanned: d.everPlanned,
  ...(d.prepTime ? { prepTime: d.prepTime } : {}),
});

export const detail = (d: DishFixture): Record<string, unknown> => ({
  ...summary(d),
  sources: d.sources ?? [],
  createdBy: d.createdBy,
  version: d.version ?? 1,
  ...(d.notes ? { notes: d.notes } : {}),
});

export const COURSES_ROUTE = "GET /api/v1/courses";
export const DISHES_ROUTE = "GET /api/v1/dishes";
export const CREATE_ROUTE = "POST /api/v1/dishes";
export const dishRoute = (id: string): string => `GET /api/v1/dishes/${id}`;
export const updateRoute = (id: string): string => `PUT /api/v1/dishes/${id}`;

export const coursesHandler: Handler = () => json({ items: COURSES });

export function page(items: DishFixture[], nextCursor: string | null = null): Response {
  return json({ items: items.map(summary), nextCursor });
}

export function withEtag(body: Record<string, unknown>, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json", ETag: `"${String(body["version"])}"` },
  });
}

export const validation = (
  errors: Array<{ field: string; code: string; params?: Record<string, unknown> }>,
): Response => problemResponse("validation", { errors });

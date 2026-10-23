// Archivio piatti (SL-04): percorsi, tipi dallo schema generato e controlli sui valori che
// arrivano dal server. La UI (features/dishes) usa solo queste funzioni.
import { api, type ApiResult } from "./client";
import type { components } from "./schema.gen";

export type Course = components["schemas"]["Course"];
export type DishSummary = components["schemas"]["DishSummary"];
export type DishDetail = components["schemas"]["DishDetail"];
export type DishPage = components["schemas"]["DishPage"];
export type DishWrite = components["schemas"]["DishWrite"];
export type DishUpdate = components["schemas"]["DishUpdate"];
export type Source = components["schemas"]["Source"];
export type SourceKind = Source["kind"];
export type DishStatus = DishDetail["status"];
export type PrepTime = NonNullable<DishDetail["prepTime"]>;

/** Chiavi della cache delle query e nomi dei campi (valori tecnici, non testo utente). */
export const KEYS = {
  courses: ["courses"],
  list: ["dishes", "list"],
  detail: (id: string): string[] => ["dishes", "detail", id],
} as const;

export const FIELD = {
  name: "name",
  courses: "courseIds",
  prepTime: "prepTime",
  notes: "notes",
} as const;

/** Nome del campo di una fonte, come lo scrive il server (`sources[1].reference`). */
export const SOURCE_FIELD = { reference: "reference", page: "page", note: "note" } as const;
export const sourceField = (index: number, name: keyof typeof SOURCE_FIELD): string =>
  `sources[${index}].${name}`;

export const STATUS_VALUES: DishStatus[] = ["to_try", "tested"];
export const PREP_VALUES: PrepTime[] = ["under_30", "30_60", "over_60"];
export const DEFAULT_STATUS: DishStatus = "to_try";
export const ARCHIVED_ON = "true";

/** Limiti del server (AC-004.5): il controllo locale è solo per l'utente, il server decide. */
export const LIMITS = {
  name: 120,
  notes: 2000,
  sources: 10,
  reference: 500,
  page: 20,
  sourceNote: 500,
} as const;

export const PAGE_SIZE = 50;

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
export const isUuid = (value: unknown): value is string =>
  typeof value === "string" && UUID.test(value);

export interface DishFilters {
  q: string;
  courseId: string;
  status: "" | DishStatus;
  archived: boolean;
}

export function listDishes(
  filters: DishFilters,
  cursor: string | null,
  signal?: AbortSignal,
): Promise<ApiResult<DishPage>> {
  const query = new URLSearchParams();
  if (filters.q) query.set("q", filters.q);
  if (filters.courseId) query.set("courseId", filters.courseId);
  if (filters.status) query.set("status", filters.status);
  if (filters.archived) query.set("archived", ARCHIVED_ON);
  if (cursor) query.set("cursor", cursor);
  query.set("limit", String(PAGE_SIZE));
  return api.get<DishPage>(`/api/v1/dishes?${query.toString()}`, signal ? { signal } : {});
}

export const listCourses = (): Promise<ApiResult<{ items: Course[] }>> =>
  api.get("/api/v1/courses");

export function readDish(id: string): Promise<ApiResult<DishDetail>> {
  return api.get<DishDetail>(`/api/v1/dishes/${encodeURIComponent(id)}`);
}

export const createDish = (body: DishWrite): Promise<ApiResult<DishDetail>> =>
  api.post<DishDetail>("/api/v1/dishes", { body });

export function updateDish(
  id: string,
  version: number,
  body: DishUpdate,
): Promise<ApiResult<DishDetail>> {
  return api.put<DishDetail>(`/api/v1/dishes/${encodeURIComponent(id)}`, {
    body,
    ifMatch: version,
  });
}

/** Chiave di catalogo dell'etichetta di una portata base. */
export const COURSE_KEYS: Record<string, string> = {
  starter: "dish.course.starter",
  first: "dish.course.first",
  second: "dish.course.second",
  side: "dish.course.side",
  one_dish: "dish.course.single",
  dessert: "dish.course.dessert",
  drink: "dish.course.drink",
  other: "dish.course.other",
};

export const STATUS_KEYS: Record<DishStatus, string> = {
  to_try: "dish.status.toTry",
  tested: "dish.status.tested",
};

export const PREP_KEYS: Record<PrepTime, string> = {
  under_30: "dish.time.under30",
  "30_60": "dish.time.30to60",
  over_60: "dish.time.over60",
};

export const SOURCE_KINDS: SourceKind[] = ["link", "book", "magazine", "other"];
export const SOURCE_TYPE_KEYS: Record<SourceKind, string> = {
  link: "dish.source.type.link",
  book: "dish.source.type.book",
  magazine: "dish.source.type.magazine",
  other: "dish.source.type.other",
};

/** `http(s)://host` senza spazi né credenziali (SR-024); stesso criterio del server. */
export function isHttpUrl(value: string): boolean {
  // eslint-disable-next-line no-control-regex
  if (!/^https?:\/\//i.test(value) || /[\s\u0000-\u001f]/.test(value)) return false;
  try {
    const url = new URL(value);
    return (
      (url.protocol === "http:" || url.protocol === "https:") &&
      url.hostname !== "" &&
      url.username === "" &&
      url.password === ""
    );
  } catch {
    return false;
  }
}

/** Il nome del sito di un indirizzo valido, per mostrarlo accanto al link. */
export function hostOf(value: string): string {
  try {
    return new URL(value).hostname;
  } catch {
    return "";
  }
}

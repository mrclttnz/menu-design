// Modello del modulo piatto (S-07): stato, validazione locale e corpo della richiesta.
// La validazione locale serve all'utente (UX §5.4); il server ripete ogni controllo (SR-024).
import {
  DEFAULT_STATUS,
  FIELD,
  isHttpUrl,
  LIMITS,
  SOURCE_FIELD,
  sourceField,
  type DishDetail,
  type DishUpdate,
  type DishWrite,
  type PrepTime,
  type Source,
  type SourceKind,
} from "../../api/dishes";
import { resolveFieldErrors, type ResolvedMessage } from "../../api/errors";

export interface SourceDraft {
  key: number;
  kind: SourceKind;
  reference: string;
  page: string;
  note: string;
}

export interface FormState {
  name: string;
  courseIds: string[];
  status: "to_try" | "tested";
  prepTime: "" | PrepTime;
  notes: string;
  sources: SourceDraft[];
}

export type FieldErrors = Record<string, ResolvedMessage>;

export const emptyForm = (name = ""): FormState => ({
  name,
  courseIds: [],
  status: DEFAULT_STATUS,
  prepTime: "",
  notes: "",
  sources: [],
});

let nextKey = 1;
export const newSource = (): SourceDraft => ({
  key: nextKey++,
  kind: "link",
  reference: "",
  page: "",
  note: "",
});

export function formFromDish(dish: DishDetail): FormState {
  return {
    name: dish.name,
    courseIds: [...dish.courseIds],
    status: dish.status,
    prepTime: dish.prepTime ?? "",
    notes: dish.notes ?? "",
    sources: dish.sources.map((source) => ({
      key: nextKey++,
      kind: source.kind,
      reference: source.reference,
      page: source.page ?? "",
      note: source.note ?? "",
    })),
  };
}

/** Lunghezza in caratteri (punti di codice), come la conta il server. */
const length = (text: string): number => Array.from(text).length;
const tooLong = (max: number): ResolvedMessage => ({
  id: "validation.string_too_long",
  values: { max },
});
const required: ResolvedMessage = { id: "validation.required", values: {} };
const hasPages = (kind: SourceKind): boolean => kind === "book" || kind === "magazine";

export function validate(state: FormState): FieldErrors {
  const errors: FieldErrors = {};
  const name = state.name.trim();
  if (name === "") errors[FIELD.name] = required;
  else if (length(name) > LIMITS.name) errors[FIELD.name] = tooLong(LIMITS.name);
  if (state.courseIds.length === 0) {
    errors[FIELD.courses] = { id: "validation.course_required", values: {} };
  }
  if (length(state.notes) > LIMITS.notes) errors[FIELD.notes] = tooLong(LIMITS.notes);
  state.sources.forEach((source, index) => {
    const reference = source.reference.trim();
    if (reference === "") errors[sourceField(index, SOURCE_FIELD.reference)] = required;
    else if (length(reference) > LIMITS.reference) {
      errors[sourceField(index, SOURCE_FIELD.reference)] = tooLong(LIMITS.reference);
    } else if (source.kind === "link" && !isHttpUrl(reference)) {
      errors[sourceField(index, SOURCE_FIELD.reference)] = {
        id: "validation.url_invalid",
        values: {},
      };
    }
    if (hasPages(source.kind) && length(source.page) > LIMITS.page) {
      errors[sourceField(index, SOURCE_FIELD.page)] = tooLong(LIMITS.page);
    }
    if (length(source.note) > LIMITS.sourceNote)
      errors[sourceField(index, SOURCE_FIELD.note)] = tooLong(LIMITS.sourceNote);
  });
  return errors;
}

function sourcesBody(state: FormState): Source[] {
  return state.sources.map((source) => {
    const out: Source = { kind: source.kind, reference: source.reference.trim() };
    if (hasPages(source.kind) && source.page.trim() !== "") out.page = source.page.trim();
    if (source.note.trim() !== "") out.note = source.note.trim();
    return out;
  });
}

/** Solo i campi scrivibili: nessun `id`, `version`, `createdBy` (SR-010). */
export function updateBody(state: FormState): DishUpdate {
  return {
    name: state.name.trim(),
    courseIds: state.courseIds,
    notes: state.notes.trim() === "" ? null : state.notes,
    prepTime: state.prepTime === "" ? null : state.prepTime,
    sources: sourcesBody(state),
  };
}

export const createBody = (state: FormState): DishWrite => ({
  ...updateBody(state),
  status: state.status,
});

/** Un 422 del server: ogni errore al suo campo; i nomi dei campi composti si normalizzano. */
export function serverErrors(problem: unknown): FieldErrors {
  const out: FieldErrors = {};
  for (const item of resolveFieldErrors(problem)) {
    const field = item.field.startsWith(FIELD.courses) ? FIELD.courses : item.field;
    if (field !== "" && !(field in out)) out[field] = { id: item.id, values: item.values };
  }
  return out;
}

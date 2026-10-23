import { useLingui } from "@lingui/react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  useEffect,
  useId,
  useRef,
  useState,
  type ReactElement,
  type ReactNode,
  type SyntheticEvent,
} from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router";
import {
  createDish,
  FIELD,
  isUuid,
  KEYS,
  LIMITS,
  PREP_KEYS,
  PREP_VALUES,
  SOURCE_KINDS,
  SOURCE_TYPE_KEYS,
  SOURCE_FIELD,
  sourceField,
  STATUS_KEYS,
  STATUS_VALUES,
  updateDish,
  type Course,
  type DishDetail,
  type PrepTime,
  type SourceKind,
} from "../../api/dishes";
import { resolveProblem, type ResolvedMessage } from "../../api/errors";
import { Dialog } from "../../components/Dialog";
import { ErrorState } from "../../components/ErrorState";
import { Page } from "../../components/Page";
import { Skeleton } from "../../components/Skeleton";
import { TextField } from "../../components/TextField";
import { useToast } from "../../components/Toast";
import { dishQuery } from "./DishPage";
import {
  createBody,
  emptyForm,
  formFromDish,
  newSource,
  serverErrors,
  updateBody,
  validate,
  type FieldErrors,
  type FormState,
  type SourceDraft,
} from "./formModel";
import { NotFoundState } from "./NotFoundState";
import { RequestFailed, useCanWriteDishes, useCourseLabel, useCourses } from "./shared";
import "./dishes.css";

const NOTES_COUNTER_FROM = Math.floor(LIMITS.notes * 0.9);

// S-07 «Modulo del piatto» (nuovo / modifica). In M0 lo usano solo Amministratore e Pianificatore;
// per un Membro il server risponde 403 e qui non si mostra nemmeno il modulo.
export function DishFormPage(): ReactElement {
  const { _ } = useLingui();
  const { dishId } = useParams();
  const editing = dishId !== undefined;
  const valid = !editing || isUuid(dishId);
  const canWrite = useCanWriteDishes();
  const location = useLocation();
  const courses = useCourses();
  const dish = useQuery({ ...dishQuery(String(dishId)), enabled: editing && valid && canWrite });

  if (!canWrite) {
    return (
      <Page title={_("dishes.title")}>
        <ErrorState error={{ code: "forbidden" }} />
        <p>
          <Link to="/piatti">{_("dishes.back")}</Link>
        </p>
      </Page>
    );
  }
  if (!valid) return <NotFoundState />;
  if (editing && dish.isError) {
    const error = dish.error;
    if (error instanceof RequestFailed && error.status === 404) return <NotFoundState />;
    return (
      <Page title={_("dishes.title")}>
        <ErrorState
          error={error instanceof RequestFailed ? error.problem : undefined}
          onRetry={() => void dish.refetch()}
        />
      </Page>
    );
  }
  if (courses.isError) {
    return (
      <Page title={_("dishes.title")}>
        <ErrorState
          error={courses.error instanceof RequestFailed ? courses.error.problem : undefined}
          onRetry={() => void courses.refetch()}
        />
      </Page>
    );
  }
  if (!courses.data || (editing && !dish.data)) return <Skeleton />;

  const prefill = (location.state as { name?: unknown } | null)?.name;
  const initial = dish.data
    ? formFromDish(dish.data)
    : emptyForm(typeof prefill === "string" ? prefill : "");
  return (
    <DishForm
      key={dish.data?.id ?? "new"}
      courses={courses.data}
      initial={initial}
      existing={dish.data}
    />
  );
}

interface DishFormProps {
  courses: Course[];
  initial: FormState;
  existing: DishDetail | undefined;
}

function DishForm({ courses, initial, existing }: DishFormProps): ReactElement {
  const { _ } = useLingui();
  const navigate = useNavigate();
  const client = useQueryClient();
  const toast = useToast();
  const prefix = useId();
  const label = useCourseLabel(courses);
  const [start] = useState(initial);
  const [state, setState] = useState<FormState>(start);
  const [errors, setErrors] = useState<FieldErrors>({});
  const [failure, setFailure] = useState<ResolvedMessage | null>(null);
  const [busy, setBusy] = useState(false);
  const [confirmLeave, setConfirmLeave] = useState(false);
  const [checked, setChecked] = useState(false);
  const [attempt, setAttempt] = useState(0);
  // La versione si fissa all'apertura del modulo: un refetch (es. al ritorno della rete) non deve
  // spostarla, altrimenti If-Match nasconderebbe una modifica concorrente.
  const [openedVersion] = useState(existing?.version);
  const sending = useRef(false);
  const summary = useRef<HTMLDivElement>(null);
  const alertBox = useRef<HTMLDivElement>(null);

  const dirty = JSON.stringify(strip(state)) !== JSON.stringify(strip(start));
  const hasErrors = Object.keys(errors).length > 0;
  const title = existing ? _("common.edit") : _("dishes.new");

  // Il focus va al riepilogo solo dopo un invio, non mentre si correggono i campi.
  useEffect(() => {
    if (attempt > 0) summary.current?.focus();
  }, [attempt]);
  useEffect(() => {
    if (failure) alertBox.current?.focus();
  }, [failure]);

  function change(patch: Partial<FormState>): void {
    const next = { ...state, ...patch };
    setState(next);
    // Dopo il primo invio i messaggi seguono il testo: si correggono man mano.
    if (checked) setErrors(validate(next));
  }

  function patchSource(key: number, patch: Partial<SourceDraft>): void {
    change({ sources: state.sources.map((s) => (s.key === key ? { ...s, ...patch } : s)) });
  }

  async function submit(event: SyntheticEvent): Promise<void> {
    event.preventDefault();
    if (sending.current) return;
    setFailure(null);
    setChecked(true);
    const found = validate(state);
    setErrors(found);
    if (Object.keys(found).length > 0) {
      setAttempt((n) => n + 1);
      return;
    }
    sending.current = true;
    setBusy(true);
    const result = existing
      ? await updateDish(existing.id, openedVersion ?? existing.version, updateBody(state))
      : await createDish(createBody(state));
    if (result.ok) {
      void client.invalidateQueries({ queryKey: KEYS.list });
      toast.show({ message: _("dish.saved.toast") });
      void navigate(`/piatti/${result.data.id}`);
      return;
    }
    const fields = serverErrors(result.problem);
    if (Object.keys(fields).length > 0) {
      setErrors(fields);
      setAttempt((n) => n + 1);
    } else setFailure(resolveProblem(result.problem));
    sending.current = false;
    setBusy(false);
  }

  const leave = (): void => void navigate("/piatti");
  const error = (field: string): ResolvedMessage | undefined => errors[field];
  const id = (name: string): string => `${prefix}-${name}`;
  const sourceId = (key: number): string => id(String(key));

  return (
    <Page title={title} documentTitle={_("app.documentTitle", { title, app: _("app.name") })}>
      <form noValidate onSubmit={(event) => void submit(event)} className="dish-form">
        {hasErrors ? (
          <div ref={summary} role="alert" tabIndex={-1} className="state state-error">
            <p>{_("form.errorSummary")}</p>
          </div>
        ) : null}
        {failure ? (
          <div ref={alertBox} role="alert" tabIndex={-1} className="state state-error">
            <p>{_(failure.id, failure.values)}</p>
          </div>
        ) : null}

        <Field
          id={id("name")}
          label={_("dish.field.name")}
          marker={_("common.required")}
          error={error(FIELD.name)}
        >
          <TextField
            id={id("name")}
            type="text"
            value={state.name}
            aria-required="true"
            aria-invalid={error(FIELD.name) ? "true" : undefined}
            aria-describedby={error(FIELD.name) ? `${id("name")}-error` : undefined}
            onValueChange={(name) => change({ name })}
          />
        </Field>

        <fieldset className="field" aria-describedby={`${id("courses")}-note`}>
          <legend>
            {_("dish.field.courses")} <span className="marker">{_("common.required")}</span>
          </legend>
          <div className="checks">
            {courses.map((course) => (
              <label key={course.id} className="check">
                <input
                  type="checkbox"
                  checked={state.courseIds.includes(course.id)}
                  onChange={(event) =>
                    change({
                      courseIds: event.target.checked
                        ? [...state.courseIds, course.id]
                        : state.courseIds.filter((cid) => cid !== course.id),
                    })
                  }
                />
                {label(course.id)}
              </label>
            ))}
          </div>
          <div id={`${id("courses")}-note`}>
            {error(FIELD.courses) ? (
              <ErrorLine message={error(FIELD.courses) as ResolvedMessage} />
            ) : (
              <p className="hint">{_("dish.field.courses.hint")}</p>
            )}
          </div>
        </fieldset>

        {existing ? null : (
          <fieldset className="field">
            <legend>{_("dish.field.status")}</legend>
            <div className="checks">
              {STATUS_VALUES.map((value) => (
                <label key={value} className="check">
                  <input
                    type="radio"
                    name={id("status")}
                    checked={state.status === value}
                    onChange={() => change({ status: value })}
                  />
                  {_(STATUS_KEYS[value])}
                </label>
              ))}
            </div>
          </fieldset>
        )}

        <Field
          id={id("prep")}
          label={_("dish.time.label")}
          marker={_("common.optional")}
          error={error(FIELD.prepTime)}
        >
          <select
            id={id("prep")}
            value={state.prepTime}
            onChange={(event) => change({ prepTime: event.target.value as "" | PrepTime })}
          >
            <option value="">{_("dish.time.none")}</option>
            {PREP_VALUES.map((value) => (
              <option key={value} value={value}>
                {_(PREP_KEYS[value])}
              </option>
            ))}
          </select>
        </Field>

        <Field
          id={id("notes")}
          label={_("dish.field.notes")}
          marker={_("common.optional")}
          error={error(FIELD.notes)}
        >
          <TextField
            multiline
            id={id("notes")}
            rows={4}
            value={state.notes}
            aria-invalid={error(FIELD.notes) ? "true" : undefined}
            aria-describedby={`${id("notes")}-hint${error(FIELD.notes) ? ` ${id("notes")}-error` : ""}`}
            onValueChange={(notes) => change({ notes })}
          />
          <p id={`${id("notes")}-hint`} className="hint">
            {_("dish.field.notes.hint")}
          </p>
          {Array.from(state.notes).length > NOTES_COUNTER_FROM ? (
            <p className="hint" aria-live="polite">
              {Array.from(state.notes).length} / {LIMITS.notes}
            </p>
          ) : null}
        </Field>

        <section>
          <h2>{_("dish.sources.title")}</h2>
          <ol className="sources-form">
            {state.sources.map((source, index) => (
              <SourceFields
                key={source.key}
                index={index}
                source={source}
                prefix={sourceId(source.key)}
                errors={errors}
                onChange={(patch) => patchSource(source.key, patch)}
                onRemove={() =>
                  change({ sources: state.sources.filter((s) => s.key !== source.key) })
                }
              />
            ))}
          </ol>
          {state.sources.length >= LIMITS.sources ? (
            <p className="hint">{_("dish.source.limit", { max: LIMITS.sources })}</p>
          ) : null}
          <button
            type="button"
            className="btn"
            disabled={state.sources.length >= LIMITS.sources}
            onClick={() => change({ sources: [...state.sources, newSource()] })}
          >
            {_("dish.source.add")}
          </button>
        </section>

        <div className="form-actions">
          <button
            type="button"
            className="btn"
            onClick={() => (dirty ? setConfirmLeave(true) : leave())}
          >
            {_("common.cancel")}
          </button>
          <button
            type="submit"
            className="btn btn-primary"
            aria-disabled={busy ? "true" : undefined}
          >
            {_("common.save")}
          </button>
        </div>
      </form>
      <Dialog
        title={_("form.discard.title")}
        isOpen={confirmLeave}
        onClose={() => setConfirmLeave(false)}
      >
        <p>{_("form.discard.body")}</p>
        <div className="dialog-actions">
          <button type="button" className="btn" onClick={() => setConfirmLeave(false)}>
            {_("form.discard.keep")}
          </button>
          <button type="button" className="btn btn-primary" onClick={leave}>
            {_("form.discard.confirm")}
          </button>
        </div>
      </Dialog>
    </Page>
  );
}

/** Lo stato senza le chiavi interne delle fonti: serve a sapere se c'è qualcosa da perdere. */
const strip = (state: FormState): unknown => ({
  ...state,
  sources: state.sources.map((s) => [s.kind, s.reference, s.page, s.note]),
});

function ErrorLine({ message, id }: { message: ResolvedMessage; id?: string }): ReactElement {
  const { _ } = useLingui();
  return (
    <p className="field-error" id={id}>
      {_(message.id, message.values)}
    </p>
  );
}

function Field({
  id,
  label,
  marker,
  error,
  children,
}: {
  id: string;
  label: string;
  marker: string;
  error: ResolvedMessage | undefined;
  children: ReactNode;
}): ReactElement {
  return (
    <div className="field">
      <div className="field-head">
        <label htmlFor={id}>{label}</label> <span className="marker">{marker}</span>
      </div>
      {children}
      {error ? <ErrorLine message={error} id={`${id}-error`} /> : null}
    </div>
  );
}

function SourceFields({
  index,
  source,
  prefix,
  errors,
  onChange,
  onRemove,
}: {
  index: number;
  source: SourceDraft;
  prefix: string;
  errors: FieldErrors;
  onChange: (patch: Partial<SourceDraft>) => void;
  onRemove: () => void;
}): ReactElement {
  const { _ } = useLingui();
  const isLink = source.kind === "link";
  const printed = source.kind === "book" || source.kind === "magazine";
  const referenceLabel = isLink
    ? _("dish.source.url")
    : printed
      ? _("dish.source.bookTitle")
      : _("dish.source.text");
  const field = (name: keyof typeof SOURCE_FIELD): ResolvedMessage | undefined =>
    errors[sourceField(index, name)];
  const ref = field(SOURCE_FIELD.reference);
  return (
    <li>
      <fieldset className="source">
        <legend>{_("dish.source.n", { n: index + 1 })}</legend>
        <div className="field">
          <label htmlFor={`${prefix}-kind`}>{_("dish.source.type")}</label>
          <select
            id={`${prefix}-kind`}
            value={source.kind}
            onChange={(event) => onChange({ kind: event.target.value as SourceKind })}
          >
            {SOURCE_KINDS.map((kind) => (
              <option key={kind} value={kind}>
                {_(SOURCE_TYPE_KEYS[kind])}
              </option>
            ))}
          </select>
        </div>
        <div className="field">
          <label htmlFor={`${prefix}-ref`}>{referenceLabel}</label>
          <TextField
            id={`${prefix}-ref`}
            type="text"
            url={isLink}
            spellCheck={false}
            value={source.reference}
            aria-invalid={ref ? "true" : undefined}
            aria-describedby={ref ? `${prefix}-ref-error` : undefined}
            onValueChange={(reference) => onChange({ reference })}
          />
          {ref ? <ErrorLine message={ref} id={`${prefix}-ref-error`} /> : null}
        </div>
        {printed ? (
          <div className="field">
            <label htmlFor={`${prefix}-page`}>{_("dish.source.page")}</label>
            <TextField
              id={`${prefix}-page`}
              type="text"
              value={source.page}
              aria-invalid={field(SOURCE_FIELD.page) ? "true" : undefined}
              aria-describedby={field(SOURCE_FIELD.page) ? `${prefix}-page-error` : undefined}
              onValueChange={(page) => onChange({ page })}
            />
            {field(SOURCE_FIELD.page) ? (
              <ErrorLine
                message={field(SOURCE_FIELD.page) as ResolvedMessage}
                id={`${prefix}-page-error`}
              />
            ) : null}
          </div>
        ) : null}
        <div className="field">
          <label htmlFor={`${prefix}-note`}>{_("dish.source.note")}</label>
          <TextField
            id={`${prefix}-note`}
            type="text"
            value={source.note}
            aria-invalid={field(SOURCE_FIELD.note) ? "true" : undefined}
            aria-describedby={field(SOURCE_FIELD.note) ? `${prefix}-note-error` : undefined}
            onValueChange={(note) => onChange({ note })}
          />
          {field(SOURCE_FIELD.note) ? (
            <ErrorLine
              message={field(SOURCE_FIELD.note) as ResolvedMessage}
              id={`${prefix}-note-error`}
            />
          ) : null}
        </div>
        <button type="button" className="btn" onClick={onRemove}>
          {_("dish.source.remove")}
        </button>
      </fieldset>
    </li>
  );
}

import { useLingui } from "@lingui/react";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useEffect, useId, useMemo, useRef, useState, type ReactElement } from "react";
import { Link, useNavigate, useSearchParams } from "react-router";
import { resolveProblem } from "../../api/errors";
import {
  MEAL_TYPES,
  planKey,
  readPlan,
  SPECIAL_KEYS,
  type DateRange,
  type DayView,
  type MealType,
  type MealView,
  type PlanView,
} from "../../api/plan";
import { ActionMenu } from "../../components/ActionMenu";
import { Page } from "../../components/Page";
import { Skeleton } from "../../components/Skeleton";
import { useToast } from "../../components/Toast";
import { formatDayHeading, formatLongDate, formatRange } from "../../i18n/format";
import { toPastoId } from "../../lib/pasto-id";
import { AddMealDialog } from "./AddMealDialog";
import { checkRange, rangeFromSearch, shifted } from "../../lib/dates";
import { RangeDialog } from "./RangeDialog";
import { RequestFailed, unwrap, useCanPlan, useMealLabel } from "./shared";
import "./plan.css";

const byOrder = (a: MealView, b: MealView): number =>
  MEAL_TYPES.indexOf(a.mealType) - MEAL_TYPES.indexOf(b.mealType) || a.slot - b.slot;

function missingTypes(day: DayView): MealType[] {
  const present = new Set(day.meals.map((meal) => meal.mealType));
  // M0/M1: un solo «Altro pasto» al giorno, con il nome fisso (D-07).
  return MEAL_TYPES.filter((type) => !present.has(type));
}

// S-02 «Piano: settimana». Il «oggi» e il fuso sono quelli del server (ADR-0009); l'intervallo
// scelto sta nell'indirizzo (`?da=&a=`). Nessun testo del server arriva all'utente se non per
// codice (SR-021); nomi di piatti e voci libere sono nodi di testo.
export function PlanPage(): ReactElement {
  const { _ } = useLingui();
  const toast = useToast();
  const canPlan = useCanPlan();
  const [params, setParams] = useSearchParams();
  const search = params.toString();
  const range = useMemo(() => rangeFromSearch(new URLSearchParams(search)), [search]);
  const [rangeOpen, setRangeOpen] = useState(false);
  const [adding, setAdding] = useState<string | null>(null);

  const plan = useQuery({
    queryKey: planKey(range),
    queryFn: async ({ signal }) => unwrap(await readPlan(range, signal)),
    retry: false,
    staleTime: 0,
    // Al ritorno in primo piano si rilegge anche il «oggi» (ADR-0009).
    refetchOnWindowFocus: true,
    placeholderData: keepPreviousData,
  });
  const view = plan.data;

  const today = view?.today;
  const seenToday = useRef<string | undefined>(undefined);
  useEffect(() => {
    if (!today) return;
    if (seenToday.current !== undefined && seenToday.current !== today) {
      toast.show({ message: _("plan.dayChanged.toast") });
    }
    seenToday.current = today;
  }, [today, toast, _]);

  const shown: DateRange | null = range ?? (view ? { from: view.from, to: view.to } : null);
  const title = _("plan.title");

  function go(next: DateRange): void {
    if (checkRange(next.from, next.to) === null) setParams({ da: next.from, a: next.to });
  }

  let body: ReactElement;
  if (plan.isError) {
    const error = plan.error instanceof RequestFailed ? plan.error : null;
    const server =
      error?.problem.code === "range_too_large" || error?.problem.code === "validation";
    const message = server ? resolveProblem(error?.problem) : null;
    body = (
      <div role="alert" className="state state-error">
        <p>{message ? _(message.id, message.values) : _("plan.error.load")}</p>
        <button type="button" className="btn" onClick={() => void plan.refetch()}>
          {_("common.retry")}
        </button>
      </div>
    );
  } else if (!view) {
    body = <Skeleton rows={6} />;
  } else {
    body = (
      <PlanBody view={view} canPlan={canPlan} stale={plan.isPlaceholderData} onAdd={setAdding} />
    );
  }

  const addingDay = adding === null ? undefined : view?.days.find((day) => day.date === adding);
  return (
    <Page title={title} documentTitle={_("app.documentTitle", { title, app: _("app.name") })}>
      {shown ? (
        <div className="plan-toolbar">
          <button
            type="button"
            className="btn"
            aria-label={_("plan.nav.prev")}
            onClick={() => go(shifted(shown, -1))}
          >
            <span aria-hidden="true">‹</span>
          </button>
          <span className="plan-range">{formatRange(shown.from, shown.to)}</span>
          <button
            type="button"
            className="btn"
            aria-label={_("plan.nav.next")}
            onClick={() => go(shifted(shown, 1))}
          >
            <span aria-hidden="true">›</span>
          </button>
          <button type="button" className="btn" onClick={() => setParams({})}>
            {_("common.today")}
          </button>
          <ActionMenu
            label={_("plan.menu.week")}
            actions={[
              {
                id: "range",
                label: _("plan.menu.otherRange"),
                onAction: () => setRangeOpen(true),
              },
            ]}
          />
        </div>
      ) : null}
      {body}
      {rangeOpen && shown ? (
        <RangeDialog
          current={shown}
          today={view?.today ?? shown.from}
          onClose={() => setRangeOpen(false)}
          onSubmit={(next) => {
            setRangeOpen(false);
            go(next);
          }}
        />
      ) : null}
      {addingDay ? (
        <AddMealDialog
          date={addingDay.date}
          available={missingTypes(addingDay)}
          onClose={() => setAdding(null)}
        />
      ) : null}
    </Page>
  );
}

interface BodyProps {
  view: PlanView;
  canPlan: boolean;
  stale: boolean;
  onAdd: (date: string) => void;
}

function PlanBody({ view, canPlan, stale, onAdd }: BodyProps): ReactElement {
  const { _ } = useLingui();
  const empty = view.days.every((day) => day.meals.length === 0);
  if (empty && !canPlan) {
    return (
      <section className="state">
        <h2>{_("plan.empty.notReady.title")}</h2>
        <p>{_("plan.empty.notReady.body")}</p>
      </section>
    );
  }
  // Senza pasti di default il pulsante lavora sul giorno di oggi se è nell'intervallo, altrimenti
  // sul primo giorno; i giorni restano sotto, ciascuno con il proprio menu.
  const target = view.days.find((day) => day.date === view.today) ?? view.days[0];
  return (
    <div aria-busy={stale ? "true" : undefined}>
      {empty ? (
        <section className="state plan-empty">
          <h2>{_("plan.empty.noMeals.title")}</h2>
          <p>{_("plan.empty.noMeals.body")}</p>
          <div className="plan-empty-actions">
            {/* S-09 (SL-09): la rotta esiste dalla slice delle impostazioni. */}
            <Link className="btn btn-primary" to="/altro/famiglia">
              {_("plan.empty.noMeals.cta1")}
            </Link>
            {target ? (
              <button type="button" className="btn" onClick={() => onAdd(target.date)}>
                {_("plan.empty.noMeals.cta2")}
              </button>
            ) : null}
          </div>
        </section>
      ) : null}
      {view.days.map((day) => (
        <DaySection key={day.date} day={day} view={view} canPlan={canPlan} onAdd={onAdd} />
      ))}
    </div>
  );
}

function DaySection({
  day,
  view,
  canPlan,
  onAdd,
}: {
  day: DayView;
  view: PlanView;
  canPlan: boolean;
  onAdd: (date: string) => void;
}): ReactElement {
  const { _ } = useLingui();
  const heading = formatDayHeading(day.date);
  const headingId = useId();
  const isToday = day.date === view.today;
  const isPast = day.date < view.today;
  const canAdd = canPlan && missingTypes(day).length > 0;
  return (
    <section className={isPast ? "plan-day plan-day-past" : "plan-day"} aria-labelledby={headingId}>
      <div className="plan-day-head">
        <h2 id={headingId}>{heading}</h2>
        {isToday ? <span className="badge">{_("plan.day.today")}</span> : null}
        {isPast ? <span className="badge">{_("plan.day.past")}</span> : null}
        {canAdd ? (
          <ActionMenu
            label={_("plan.day.menu", { day: heading })}
            actions={[{ id: "add", label: _("plan.day.addMeal"), onAction: () => onAdd(day.date) }]}
          />
        ) : null}
      </div>
      <ul className="meal-list">
        {[...day.meals].sort(byOrder).map((meal) => (
          <MealRow
            key={`${meal.mealType}-${meal.slot}`}
            meal={meal}
            view={view}
            canPlan={canPlan}
            headingId={headingId}
          />
        ))}
      </ul>
    </section>
  );
}

function MealRow({
  meal,
  view,
  canPlan,
  headingId,
}: {
  meal: MealView;
  view: PlanView;
  canPlan: boolean;
  headingId: string;
}): ReactElement {
  const { _ } = useLingui();
  const navigate = useNavigate();
  const label = useMealLabel()(meal);
  const nameId = useId();
  const names = [...meal.items]
    .sort((a, b) => a.position - b.position)
    .map((item) =>
      item.kind === "dish"
        ? (view.refs.dishes[item.dishId ?? ""]?.name ?? "")
        : (item.freeText ?? ""),
    )
    .filter((name) => name !== "");
  const special = meal.special ? _(SPECIAL_KEYS[meal.special]) : null;
  const empty = names.length === 0 && special === null;
  const summary = [names.join(", "), special].filter((part) => part).join(". ");
  const href = `/piano/${meal.date}/${toPastoId(meal.mealType, meal.slot)}`;
  return (
    <li className="meal-row">
      <Link
        to={href}
        className="meal-link"
        aria-label={_("plan.meal.aria", {
          meal: label,
          date: formatLongDate(meal.date),
          summary: empty ? _("plan.meal.nothing") : summary,
        })}
      >
        <span id={nameId} className="meal-name">
          {label}
        </span>
        {names.length > 0 ? <span className="meal-summary">{names.join(", ")}</span> : null}
        {special ? <span className="meal-summary">{special}</span> : null}
        {empty && !canPlan ? (
          <span className="meal-summary meal-nothing">{_("plan.meal.nothing")}</span>
        ) : null}
      </Link>
      {empty && canPlan ? (
        <button
          type="button"
          className="btn meal-add"
          aria-describedby={`${nameId} ${headingId}`}
          onClick={() => navigate(href)}
        >
          <span aria-hidden="true">+ </span>
          {_("plan.meal.add")}
        </button>
      ) : null}
    </li>
  );
}

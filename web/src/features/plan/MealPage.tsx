import { useLingui } from "@lingui/react";
import { useQueries, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState, type ReactElement } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router";
import { COURSE_KEYS, KEYS as DISH_KEYS, listCourses, readDish } from "../../api/dishes";
import type { Course, DishDetail } from "../../api/dishes";
import { resolveProblem, type ResolvedMessage } from "../../api/errors";
import {
  mealKey,
  PLAN_KEY,
  readMeal,
  setPresence,
  SPECIAL_KEYS,
  type MealItemView,
  type MealType,
} from "../../api/plan";
import { ActionMenu } from "../../components/ActionMenu";
import { ErrorState } from "../../components/ErrorState";
import { Page } from "../../components/Page";
import { Skeleton } from "../../components/Skeleton";
import { useToast } from "../../components/Toast";
import { formatLongDate } from "../../i18n/format";
import { fromPastoId } from "../../lib/pasto-id";
import { isIsoDate } from "../../lib/dates";
import { RequestFailed, unwrap, useCanPlan, useMealLabel } from "./shared";
import "./plan.css";

// S-03 «Pasto», in sola lettura più «Togli questo pasto da questo giorno» (SL-06a). L'indirizzo è
// `/piano/:data/:pastoId`; `:pastoId` lo conosce solo il client (ADR-0009). Voci, nomi dei piatti e
// note sono nodi di testo.
export function MealPage(): ReactElement {
  const { data, pastoId } = useParams();
  const target = fromPastoId(pastoId);
  if (!isIsoDate(data) || !target) return <MealNotFound />;
  return <MealScreen date={data} mealType={target.mealType} slot={target.slot} />;
}

function MealNotFound(): ReactElement {
  const { _ } = useLingui();
  return (
    <Page title={_("error.notFound.title")}>
      <ErrorState error={{ code: "not_found" }} />
      <p>
        <Link to="/piano">{_("plan.back")}</Link>
      </p>
    </Page>
  );
}

interface Target {
  date: string;
  mealType: MealType;
  slot: number;
}

function MealScreen({ date, mealType, slot }: Target): ReactElement {
  const { _ } = useLingui();
  const client = useQueryClient();
  const toast = useToast();
  const navigate = useNavigate();
  const location = useLocation();
  const canPlan = useCanPlan();
  const labelOf = useMealLabel();
  const [failure, setFailure] = useState<ResolvedMessage | null>(null);
  const [busy, setBusy] = useState(false);
  const alertBox = useRef<HTMLDivElement>(null);

  const key = mealKey(date, mealType, slot);
  const meal = useQuery({
    queryKey: key,
    // La pagina si rilegge a ogni apertura: la versione serve a `If-Match` (ADR-0008).
    queryFn: async () => unwrap(await readMeal(date, mealType, slot)),
    retry: false,
    staleTime: 0,
    gcTime: 0,
  });
  const data = meal.data;

  useEffect(() => {
    if (failure) alertBox.current?.focus();
  }, [failure]);

  const label = labelOf({ mealType, name: data?.name ?? null });
  const title = _("meal.heading", { meal: label, date: formatLongDate(date) });
  const documentTitle = _("app.documentTitle", { title, app: _("app.name") });

  if (meal.isError) {
    const error = meal.error instanceof RequestFailed ? meal.error : null;
    if (error?.status === 404) return <MealNotFound />;
    return (
      <Page title={title} documentTitle={documentTitle}>
        <ErrorState error={error?.problem} onRetry={() => void meal.refetch()} />
      </Page>
    );
  }
  if (!data) {
    return (
      <Page title={title} documentTitle={documentTitle}>
        <Skeleton />
      </Page>
    );
  }

  async function change(present: boolean): Promise<void> {
    if (busy || !data) return;
    setBusy(true);
    setFailure(null);
    const result = await setPresence(date, mealType, slot, data.contentVersion, present);
    setBusy(false);
    if (result.ok) {
      client.setQueryData(key, result.data);
      void client.invalidateQueries({ queryKey: PLAN_KEY });
      if (!present) {
        toast.show({ message: _("meal.removed.toast", { name: label }) });
        navigate("/piano", { replace: true });
      }
      return;
    }
    if (result.status === 404) {
      void meal.refetch();
      return;
    }
    setFailure(resolveProblem(result.problem));
    if (result.status === 412) void meal.refetch();
  }

  const actions = canPlan
    ? [
        data.present
          ? {
              id: "remove",
              label: _("meal.removeFromDay"),
              onAction: () => void change(false),
            }
          : { id: "add", label: _("meal.add.title"), onAction: () => void change(true) },
      ]
    : [];
  const items = [...data.items].sort((a, b) => a.position - b.position);
  return (
    <Page title={title} documentTitle={documentTitle}>
      <div className="meal-head" aria-busy={busy ? "true" : undefined}>
        <button
          type="button"
          className="btn"
          onClick={() => (location.key === "default" ? navigate("/piano") : navigate(-1))}
        >
          {_("common.back")}
        </button>
        {actions.length > 0 ? <ActionMenu label={_("meal.menu")} actions={actions} /> : null}
      </div>
      {failure ? (
        <div ref={alertBox} role="alert" tabIndex={-1} className="state state-error">
          <p>{_(failure.id, failure.values)}</p>
        </div>
      ) : null}
      {canPlan && data.past ? <p className="state">{_("meal.past.banner")}</p> : null}
      <section>
        <h2>{_("meal.section.items")}</h2>
        {items.length === 0 ? <p>{_("meal.empty")}</p> : <ItemList items={items} />}
      </section>
      <section>
        <h2>{_("meal.section.type")}</h2>
        <p>{_(data.special ? SPECIAL_KEYS[data.special] : "meal.special.normal")}</p>
      </section>
    </Page>
  );
}

function courseLabel(
  courses: Course[] | undefined,
  id: string | null | undefined,
  _: (id: string) => string,
): string {
  const course = id ? courses?.find((c) => c.id === id) : undefined;
  if (!course) return "";
  if (course.baseCode && Object.hasOwn(COURSE_KEYS, course.baseCode)) {
    return _(COURSE_KEYS[course.baseCode] as string);
  }
  return course.name ?? "";
}

function ItemList({ items }: { items: MealItemView[] }): ReactElement {
  const { _ } = useLingui();
  const dishIds = [...new Set(items.flatMap((item) => (item.dishId ? [item.dishId] : [])))];
  const dishes = useQueries({
    queries: dishIds.map((id) => ({
      queryKey: DISH_KEYS.detail(id),
      queryFn: async (): Promise<DishDetail> => unwrap(await readDish(id)),
      retry: false,
      staleTime: 60_000,
    })),
  });
  const byId = new Map(dishIds.map((id, index) => [id, dishes[index]?.data]));
  const needCourses = items.some((item) => item.courseId);
  const courses = useQuery({
    queryKey: DISH_KEYS.courses,
    enabled: needCourses,
    queryFn: async (): Promise<Course[]> => unwrap(await listCourses()).items,
    retry: false,
    staleTime: 5 * 60_000,
  });
  return (
    <ol className="item-list">
      {items.map((item) => {
        const dish = item.dishId ? byId.get(item.dishId) : undefined;
        const course = courseLabel(courses.data, item.courseId, _);
        const notes = [
          item.kind === "free_text" ? _("meal.freeText.label") : "",
          course,
          dish?.archived ? _("meal.item.archived") : "",
          item.notCooked ? _("meal.item.notCooked") : "",
        ].filter((part) => part !== "");
        return (
          <li key={item.id} className="meal-item">
            <span className="meal-item-name">
              {item.kind === "dish" ? (dish?.name ?? "…") : item.freeText}
            </span>
            {notes.map((note) => (
              <span key={note} className="meal-item-meta">
                {note}
              </span>
            ))}
          </li>
        );
      })}
    </ol>
  );
}

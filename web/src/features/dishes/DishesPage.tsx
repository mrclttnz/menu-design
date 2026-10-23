import { useLingui } from "@lingui/react";
import { keepPreviousData, useInfiniteQuery } from "@tanstack/react-query";
import { useEffect, useState, type ReactElement } from "react";
import { Link } from "react-router";
import {
  KEYS,
  listDishes,
  STATUS_VALUES,
  STATUS_KEYS,
  type DishFilters,
  type DishSummary,
  type DishStatus,
} from "../../api/dishes";
import { Page } from "../../components/Page";
import { Skeleton } from "../../components/Skeleton";
import { RequestFailed, useCanWriteDishes, useCourseLabel, useCourses } from "./shared";
import "./dishes.css";

const SEARCH_DELAY_MS = 300;

function useDebounced<T>(value: T, delay: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(timer);
  }, [value, delay]);
  return debounced;
}

// S-05 «Piatti: archivio» (UX): ricerca, filtri, archiviati (solo A e P), pagine con «Mostra altri».
// Ogni testo dell'utente (nomi) è un nodo di testo: nessun markup (THR-070).
export function DishesPage(): ReactElement {
  const { _ } = useLingui();
  const canWrite = useCanWriteDishes();
  const [search, setSearch] = useState("");
  const [courseId, setCourseId] = useState("");
  const [status, setStatus] = useState<"" | DishStatus>("");
  const [archived, setArchived] = useState(false);
  const q = useDebounced(search.trim(), SEARCH_DELAY_MS);
  const filters: DishFilters = { q, courseId, status, archived: canWrite && archived };

  const courses = useCourses();
  const label = useCourseLabel(courses.data);
  const list = useInfiniteQuery({
    queryKey: [...KEYS.list, filters],
    initialPageParam: null as string | null,
    retry: false,
    placeholderData: keepPreviousData,
    queryFn: async ({ pageParam, signal }) => {
      const result = await listDishes(filters, pageParam, signal);
      if (!result.ok) throw new RequestFailed(result.problem, result.status);
      return result.data;
    },
    getNextPageParam: (last) => last.nextCursor,
  });

  const title = _("dishes.title");
  const items = list.data?.pages.flatMap((page) => page.items) ?? [];
  const failed = list.isError || courses.isError;
  const loading = !failed && (list.isPending || courses.isPending);
  const filtered = q !== "" || courseId !== "" || status !== "" || filters.archived;

  function retry(): void {
    if (courses.isError) void courses.refetch();
    if (list.isError) void list.refetch();
  }

  let body: ReactElement;
  if (failed) {
    body = (
      <div role="alert" className="state state-error">
        <p>{_("dishes.error.load")}</p>
        <button type="button" className="btn" onClick={retry}>
          {_("common.retry")}
        </button>
      </div>
    );
  } else if (loading) {
    body = <Skeleton rows={5} />;
  } else if (items.length === 0) {
    body = filtered ? (
      <section className="state">
        <h2>{_("dishes.noResults")}</h2>
        {canWrite && q !== "" ? (
          <Link className="btn" to="/piatti/nuovo" state={{ name: q }}>
            {_("picker.create", { text: q })}
          </Link>
        ) : null}
      </section>
    ) : (
      <section className="state">
        <h2>{_("dishes.empty.title")}</h2>
        <p>{_("dishes.empty.body")}</p>
        {canWrite ? (
          <Link className="btn btn-primary" to="/piatti/nuovo">
            {_("dishes.empty.cta")}
          </Link>
        ) : null}
      </section>
    );
  } else {
    body = (
      <>
        <ul className="dish-list">
          {items.map((dish) => (
            <DishRow key={dish.id} dish={dish} label={label} />
          ))}
        </ul>
        {list.hasNextPage ? (
          <button
            type="button"
            className="btn"
            aria-disabled={list.isFetchingNextPage ? "true" : undefined}
            onClick={() => {
              if (!list.isFetchingNextPage) void list.fetchNextPage();
            }}
          >
            {_("common.showMore")}
          </button>
        ) : null}
      </>
    );
  }

  return (
    <Page title={title} documentTitle={_("app.documentTitle", { title, app: _("app.name") })}>
      {canWrite ? (
        <p>
          <Link className="btn btn-primary" to="/piatti/nuovo">
            {_("dishes.new")}
          </Link>
        </p>
      ) : null}
      <div className="field">
        <label htmlFor="dish-search">{_("dishes.search")}</label>
        <input
          id="dish-search"
          type="text"
          autoComplete="off"
          value={search}
          onChange={(event) => setSearch(event.target.value)}
        />
      </div>
      <div className="filters">
        <div className="field">
          <label htmlFor="dish-course">{_("dish.field.courses")}</label>
          <select
            id="dish-course"
            value={courseId}
            onChange={(event) => setCourseId(event.target.value)}
          >
            <option value="">{_("dishes.filter.allCourses")}</option>
            {(courses.data ?? []).map((course) => (
              <option key={course.id} value={course.id}>
                {label(course.id)}
              </option>
            ))}
          </select>
        </div>
        <div className="field">
          <label htmlFor="dish-status">{_("dishes.filter.status")}</label>
          <select
            id="dish-status"
            value={status}
            onChange={(event) => setStatus(event.target.value as "" | DishStatus)}
          >
            <option value="">{_("dishes.filter.allStatuses")}</option>
            {STATUS_VALUES.map((value) => (
              <option key={value} value={value}>
                {_(STATUS_KEYS[value])}
              </option>
            ))}
          </select>
        </div>
      </div>
      {canWrite ? (
        <label className="check">
          <input
            type="checkbox"
            checked={archived}
            onChange={(event) => setArchived(event.target.checked)}
          />
          {_("dishes.filter.archived")}
        </label>
      ) : null}
      {body}
    </Page>
  );
}

function DishRow({
  dish,
  label,
}: {
  dish: DishSummary;
  label: (id: string) => string;
}): ReactElement {
  const { _ } = useLingui();
  const courses = dish.courseIds.map(label).filter((text) => text !== "");
  return (
    <li>
      <Link to={`/piatti/${dish.id}`} className="dish-row">
        <span className="dish-name">{dish.name}</span>
        {dish.archived ? <span className="badge">{_("dish.status.archived")}</span> : null}
        <span className="dish-meta">{[...courses, _(STATUS_KEYS[dish.status])].join(" · ")}</span>
      </Link>
    </li>
  );
}

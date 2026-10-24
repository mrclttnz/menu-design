import { useLingui } from "@lingui/react";
import { useQuery } from "@tanstack/react-query";
import { useState, type ReactElement } from "react";
import { Link, useParams } from "react-router";
import {
  hostOf,
  isHttpUrl,
  isUuid,
  KEYS,
  PREP_KEYS,
  readDish,
  SOURCE_TYPE_KEYS,
  STATUS_KEYS,
  type DishDetail,
} from "../../api/dishes";
import { ErrorState } from "../../components/ErrorState";
import { Page } from "../../components/Page";
import { Skeleton } from "../../components/Skeleton";
import { StatusCommand } from "./StatusCommand";
import { NotFoundState } from "./NotFoundState";
import { RequestFailed, useCanWriteDishes, useCourseLabel, useCourses } from "./shared";
import "./dishes.css";

export function dishQuery(id: string) {
  return {
    queryKey: KEYS.detail(id),
    // La scheda si rilegge a ogni apertura: la versione serve a `If-Match` (ADR-0008).
    staleTime: 0,
    gcTime: 0,
    retry: false,
    queryFn: async (): Promise<DishDetail> => {
      const result = await readDish(id);
      if (!result.ok) throw new RequestFailed(result.problem, result.status);
      return result.data;
    },
  };
}

// S-06 «Scheda del piatto». Nome, note e fonti sono testo; il link di una fonte esiste solo per
// indirizzi http/https (SR-024, anche se il dato arrivasse manipolato) e si apre in un'altra scheda.
export function DishPage(): ReactElement {
  const { _ } = useLingui();
  const { dishId } = useParams();
  const valid = isUuid(dishId);
  const canWrite = useCanWriteDishes();
  const courses = useCourses();
  const label = useCourseLabel(courses.data);
  const dish = useQuery({ ...dishQuery(String(dishId)), enabled: valid });
  const [gone, setGone] = useState(false);

  if (!valid || gone) return <NotFoundState />;
  if (dish.isError) {
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
  const data = dish.data;
  if (!data) {
    return (
      <Page title={_("dishes.title")}>
        <Skeleton />
      </Page>
    );
  }
  const courseNames = data.courseIds.map(label).filter((text) => text !== "");
  return (
    <Page
      title={data.name}
      documentTitle={_("app.documentTitle", { title: data.name, app: _("app.name") })}
    >
      {data.archived ? <p className="state">{_("dish.archivedBanner")}</p> : null}
      {canWrite ? (
        <p>
          <Link className="btn" to={`/piatti/${data.id}/modifica`}>
            {_("common.edit")}
          </Link>
        </p>
      ) : null}
      <p className="dish-meta">{courseNames.join(", ")}</p>
      <p>
        <span className="badge">{_(STATUS_KEYS[data.status])}</span>
      </p>
      {canWrite ? <StatusCommand dish={data} onGone={() => setGone(true)} /> : null}
      {data.everPlanned ? null : <p>{_("dish.neverCooked")}</p>}
      {data.prepTime && Object.hasOwn(PREP_KEYS, data.prepTime) ? (
        <dl className="facts">
          <dt>{_("dish.time.label")}</dt>
          <dd>{_(PREP_KEYS[data.prepTime])}</dd>
        </dl>
      ) : null}
      {data.notes ? (
        <section>
          <h2>{_("dish.field.notes")}</h2>
          <p className="notes">{data.notes}</p>
        </section>
      ) : null}
      {data.sources.length > 0 ? (
        <section>
          <h2>{_("dish.sources.title")}</h2>
          <ul className="sources">
            {data.sources.map((source, index) => (
              <li key={index}>
                <span className="source-kind">{_(SOURCE_TYPE_KEYS[source.kind])}</span>{" "}
                <SourceBody source={source} />
                {source.note ? <span className="source-note"> {source.note}</span> : null}
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </Page>
  );
}

function SourceBody({ source }: { source: DishDetail["sources"][number] }): ReactElement {
  const { _ } = useLingui();
  if (source.kind === "link" && isHttpUrl(source.reference)) {
    return (
      <>
        <span className="source-ref">{hostOf(source.reference)}</span>{" "}
        <a href={source.reference} target="_blank" rel="noopener noreferrer">
          {_("dish.source.open")}
        </a>
      </>
    );
  }
  return (
    <>
      <span className="source-ref">{source.reference}</span>
      {source.page ? (
        <span>
          {" "}
          {_("dish.source.page")} {source.page}
        </span>
      ) : null}
    </>
  );
}

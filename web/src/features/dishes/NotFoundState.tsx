import { useLingui } from "@lingui/react";
import type { ReactElement } from "react";
import { Link } from "react-router";
import { ErrorState } from "../../components/ErrorState";
import { Page } from "../../components/Page";

/** Piatto inesistente o di un'altra famiglia: stesso messaggio, nessun dettaglio (THR-020). */
export function NotFoundState(): ReactElement {
  const { _ } = useLingui();
  return (
    <Page title={_("dishes.title")}>
      <ErrorState error={{ code: "not_found" }} />
      <p>
        <Link to="/piatti">{_("dishes.back")}</Link>
      </p>
    </Page>
  );
}

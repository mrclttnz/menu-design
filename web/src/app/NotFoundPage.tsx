import { useLingui } from "@lingui/react";
import type { ReactElement } from "react";
import { Link } from "react-router";
import { ErrorState } from "../components/ErrorState";
import { Page } from "../components/Page";

// error.notFound con ritorno alla schermata madre (UX §5.1). Il percorso richiesto non si mostra.
export function NotFoundPage(): ReactElement {
  const { _ } = useLingui();
  const title = _("error.notFound.title");
  return (
    <Page title={title} documentTitle={_("app.documentTitle", { title, app: _("app.name") })}>
      <ErrorState error={{ code: "not_found" }} />
      <p>
        <Link to="/accedi">{_("error.notFound.back")}</Link>
      </p>
    </Page>
  );
}

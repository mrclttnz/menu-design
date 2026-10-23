import { useLingui } from "@lingui/react";
import type { ReactElement } from "react";
import { Page } from "../../components/Page";

// Segnaposto di S-02: il piano della settimana arriva con SL-06a. Qui basta che la rotta esista
// e che sia raggiungibile solo con una sessione (RequireSession).
export function PlanPage(): ReactElement {
  const { _ } = useLingui();
  const title = _("nav.plan");
  return (
    <Page title={title} documentTitle={_("app.documentTitle", { title, app: _("app.name") })} />
  );
}

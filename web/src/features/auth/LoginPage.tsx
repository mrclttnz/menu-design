import { useLingui } from "@lingui/react";
import type { ReactElement } from "react";
import { Page } from "../../components/Page";

// S-01 statica (SL-01). Il comando avvierà il redirect lato server con SL-03a
// (POST /auth/google/start): qui non fa ancora nulla, e non c'è alcuno script di terze parti.
export function LoginPage(): ReactElement {
  const { _ } = useLingui();
  return (
    <Page title={_("auth.login.title")} centered>
      <p className="lead">{_("auth.login.subtitle")}</p>
      <button type="button" className="btn btn-primary btn-block">
        {_("auth.login.google")}
      </button>
    </Page>
  );
}

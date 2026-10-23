import { useLingui } from "@lingui/react";
import { useState, type ReactElement } from "react";
import { Navigate, useLocation } from "react-router";
import {
  isCsrfFailure,
  outcomeMessage,
  safeRedirectUrl,
  safeReturnTo,
  startFailureMessage,
  startLogin,
  type Message,
} from "../../api/session";
import { Page } from "../../components/Page";
import { useSession } from "../../session";

// S-01 (UX): accesso con Google. Il redirect parte dal server (POST /auth/google/start).
export function LoginPage(): ReactElement {
  const { _ } = useLingui();
  const { session, notice, reload } = useSession();
  const location = useLocation();
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<Message | null>(null);

  if (session?.authenticated) return <Navigate to="/piano" replace />;

  const outcome = session?.authOutcome ?? undefined;
  const noFamily = outcome?.code === "not_member";
  // La pagina di partenza viaggia nello stato della navigazione, mai nell'URL.
  const returnTo = safeReturnTo((location.state as { from?: unknown } | null)?.from);

  async function start(): Promise<void> {
    if (busy) return;
    setBusy(true);
    setFailure(null);
    const result = await startLogin(returnTo);
    const target = result.ok ? safeRedirectUrl(result.data.redirectUrl) : undefined;
    if (target) {
      window.location.assign(target);
      return; // la pagina sta per essere sostituita: il comando resta in attesa
    }
    if (!result.ok && isCsrfFailure(result.problem)) void reload(); // nuovo cookie CSRF
    setFailure(startFailureMessage(result.ok ? { code: "invalid_response" } : result.problem));
    setBusy(false);
  }

  let message: Message | null = failure;
  if (!message && notice === "expired") message = { id: "auth.sessionExpired", values: {} };
  if (!message && outcome && !noFamily) message = outcomeMessage(outcome);

  // Il comando resta focalizzabile anche mentre attende (aria-disabled, non `disabled`).
  const button = (label: string, primary: boolean): ReactElement => (
    <button
      type="button"
      className={primary ? "btn btn-primary btn-block" : "btn btn-block"}
      aria-disabled={busy ? "true" : undefined}
      onClick={() => void start()}
    >
      {busy ? _("auth.login.inProgress") : label}
    </button>
  );

  const title = noFamily ? _("auth.noFamily.title") : _("auth.login.title");
  return (
    <Page
      title={title}
      documentTitle={_("app.documentTitle", { title, app: _("app.name") })}
      centered
    >
      <p className="lead">{noFamily ? _("auth.noFamily.body") : _("auth.login.subtitle")}</p>
      {message ? (
        <p role="alert" className="state state-error">
          {_(message.id, message.values)}
        </p>
      ) : null}
      {!failure && notice === "loggedOut" ? (
        <p role="status" className="state">
          {_("auth.loggedOut")}
        </p>
      ) : null}
      {noFamily ? button(_("auth.noFamily.switch"), false) : button(_("auth.login.google"), true)}
    </Page>
  );
}

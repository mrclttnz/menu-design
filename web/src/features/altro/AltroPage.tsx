import { useLingui } from "@lingui/react";
import { useState, type ReactElement } from "react";
import { resolveProblem, type ResolvedMessage } from "../../api/errors";
import { requestLogout } from "../../api/session";
import { Page } from "../../components/Page";
import { useSession } from "../../session";

const ROLE_KEYS: Record<string, string> = {
  admin: "role.admin",
  planner: "role.planner",
  member: "role.member",
};

// S-08 (UX), versione minima di M0: con chi si è collegati e «Esci». Le altre voci arrivano
// con le loro slice. Nome, ruolo e famiglia vengono dalla sessione; mai email né ID.
export function AltroPage(): ReactElement | null {
  const { _ } = useLingui();
  const { session } = useSession();
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<ResolvedMessage | null>(null);

  if (!session?.authenticated) return null; // RequireSession porta già a S-01

  async function logout(): Promise<void> {
    if (busy) return;
    setBusy(true);
    setFailure(null);
    const result = await requestLogout();
    if (result.ok) return; // la sessione è finita: la vista passa a S-01
    setFailure(resolveProblem(result.problem));
    setBusy(false);
  }

  const roleKey = session.person ? ROLE_KEYS[session.person.role] : undefined;
  const title = _("nav.more");
  return (
    <Page title={title} documentTitle={_("app.documentTitle", { title, app: _("app.name") })}>
      <p>{_("account.signedInAs", { name: session.account.displayName })}</p>
      <ul>
        {roleKey ? <li>{_(roleKey)}</li> : null}
        {session.family ? <li>{session.family.name}</li> : null}
      </ul>
      {failure ? (
        <p role="alert" className="state state-error">
          {_(failure.id, failure.values)}
        </p>
      ) : null}
      <button
        type="button"
        className="btn btn-block"
        aria-disabled={busy ? "true" : undefined}
        onClick={() => void logout()}
      >
        {_("account.logout")}
      </button>
    </Page>
  );
}

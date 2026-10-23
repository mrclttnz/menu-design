import type { ReactElement } from "react";
import { Navigate, Outlet, useLocation } from "react-router";
import { useSession } from "../session";

// Le viste che richiedono una sessione portano a S-01 se si è anonimi (UX 5.1, «Sessione scaduta»).
// La pagina di partenza viaggia nello stato della navigazione (in memoria), mai nell'URL.
export function RequireSession(): ReactElement {
  const { session } = useSession();
  const location = useLocation();
  if (!session?.authenticated) {
    return <Navigate to="/accedi" replace state={{ from: location.pathname + location.search }} />;
  }
  return <Outlet />;
}

export function HomeRedirect(): ReactElement {
  const { session } = useSession();
  return <Navigate to={session?.authenticated ? "/piano" : "/accedi"} replace />;
}

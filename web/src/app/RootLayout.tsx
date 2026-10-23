import { useLingui } from "@lingui/react";
import { useEffect, useRef, type ReactElement } from "react";
import { NavLink, Outlet, useLocation } from "react-router";
import { ErrorState } from "../components/ErrorState";
import { Skeleton } from "../components/Skeleton";
import { useSession } from "../session";

export const MAIN_ID = "contenuto";

// Nel modulo del piatto (S-07) la barra si nasconde per dare spazio al contenuto (UX §3).
const hidesNav = (pathname: string): boolean =>
  pathname === "/piatti/nuovo" ||
  (pathname.startsWith("/piatti/") && pathname.endsWith("/modifica"));

export function RootLayout(): ReactElement {
  const { _ } = useLingui();
  const { pathname } = useLocation();
  const { session, loading, failed, error, reload } = useSession();
  const previous = useRef(pathname);

  // WCAG 2.4.3: dopo un cambio di rotta il focus va sul titolo della nuova vista.
  useEffect(() => {
    if (previous.current === pathname) return;
    previous.current = pathname;
    document.querySelector<HTMLElement>("main h1")?.focus();
  }, [pathname]);

  return (
    <>
      <a className="skip-link" href={`#${MAIN_ID}`}>
        {_("nav.skipToContent")}
      </a>
      <main id={MAIN_ID} tabIndex={-1}>
        {loading ? (
          <Skeleton />
        ) : failed ? (
          <ErrorState error={error} onRetry={() => void reload()} />
        ) : (
          <Outlet />
        )}
      </main>
      {session?.authenticated && !hidesNav(pathname) ? (
        <nav className="bottom-nav" aria-label={_("nav.label")}>
          <NavLink to="/piano">{_("nav.plan")}</NavLink>
          <NavLink to="/piatti">{_("nav.dishes")}</NavLink>
          <NavLink to="/altro">{_("nav.more")}</NavLink>
        </nav>
      ) : null}
    </>
  );
}

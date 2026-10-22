import { useLingui } from "@lingui/react";
import { useEffect, useRef, type ReactElement } from "react";
import { Outlet, useLocation } from "react-router";

export const MAIN_ID = "contenuto";

export function RootLayout(): ReactElement {
  const { _ } = useLingui();
  const { pathname } = useLocation();
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
        <Outlet />
      </main>
    </>
  );
}

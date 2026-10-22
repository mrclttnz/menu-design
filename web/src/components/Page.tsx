import { useEffect, type ReactElement, type ReactNode } from "react";

export interface PageProps {
  title: string;
  /** Titolo del documento (WCAG 2.4.2); predefinito: il titolo della vista. */
  documentTitle?: string;
  children?: ReactNode;
  centered?: boolean;
}

/** Contenitore di una vista: l'unico h1 (riceve il focus al cambio di rotta) e il titolo. */
export function Page({ title, documentTitle, children, centered }: PageProps): ReactElement {
  const fullTitle = documentTitle ?? title;
  useEffect(() => {
    document.title = fullTitle;
  }, [fullTitle]);
  return (
    <div className={centered ? "page page-centered" : "page"}>
      <h1 tabIndex={-1}>{title}</h1>
      {children}
    </div>
  );
}

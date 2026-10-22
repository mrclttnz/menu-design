import { createElement, type ReactElement } from "react";

export interface EmptyStateProps {
  title: string;
  description?: string;
  /** Una sola azione consigliata (UX §5.1). */
  action?: { label: string; onPress: () => void };
  headingLevel?: 1 | 2 | 3;
}

export function EmptyState({
  title,
  description,
  action,
  headingLevel = 2,
}: EmptyStateProps): ReactElement {
  return (
    <section className="state">
      {createElement(`h${headingLevel}`, null, title)}
      {description ? <p>{description}</p> : null}
      {action ? (
        <button type="button" className="btn btn-primary" onClick={action.onPress}>
          {action.label}
        </button>
      ) : null}
    </section>
  );
}

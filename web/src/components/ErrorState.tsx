import { useLingui } from "@lingui/react";
import { useRef, type ReactElement } from "react";
import { resolveProblem } from "../api/errors";

export interface ErrorStateProps {
  /** Il `problem` dell'API o qualunque errore: il testo viene sempre dal catalogo. */
  error?: unknown;
  onRetry?: () => void;
}

export function ErrorState({ error, onRetry }: ErrorStateProps): ReactElement {
  const { _ } = useLingui();
  const ref = useRef<HTMLDivElement>(null);
  const { id, values } = resolveProblem(error);
  return (
    <div ref={ref} role="alert" tabIndex={-1} className="state state-error">
      <p>{_(id, values)}</p>
      {onRetry ? (
        <button
          type="button"
          className="btn"
          onClick={() => {
            onRetry();
            ref.current?.focus();
          }}
        >
          {_("common.retry")}
        </button>
      ) : null}
    </div>
  );
}

import { useLingui } from "@lingui/react";
import { useEffect, useState, type ReactElement } from "react";

const SLOW_AFTER_MS = 10_000;

export function Skeleton({ rows = 3 }: { rows?: number }): ReactElement {
  const { _ } = useLingui();
  const [slow, setSlow] = useState(false);
  useEffect(() => {
    const timer = setTimeout(() => setSlow(true), SLOW_AFTER_MS);
    return () => clearTimeout(timer);
  }, []);
  return (
    <div role="status" aria-busy="true">
      <span className="visually-hidden">{_("common.loading")}</span>
      {Array.from({ length: rows }, (_row, index) => (
        <div key={index} className="skeleton-row" aria-hidden="true" />
      ))}
      {slow ? <p>{_("common.loading.slow")}</p> : null}
    </div>
  );
}

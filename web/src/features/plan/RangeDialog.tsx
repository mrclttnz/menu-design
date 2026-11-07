import { useLingui } from "@lingui/react";
import { useState, type ReactElement } from "react";
import type { DateRange } from "../../api/plan";
import { Dialog } from "../../components/Dialog";
import { addDays, checkRange, MAX_DAYS, weekOf, type RangeProblem } from "../../lib/dates";

interface Props {
  current: DateRange;
  /** Il «oggi» della famiglia, dal server. */
  today: string;
  onClose: () => void;
  onSubmit: (range: DateRange) => void;
}

const PROBLEM_KEYS: Record<RangeProblem, string> = {
  date: "validation.date_invalid",
  order: "validation.range_order",
  size: "error.range_too_large",
};

// D-05 «Scegli intervallo»: la validazione del client è per l'utente, il server decide (SR-060).
export function RangeDialog({ current, today, onClose, onSubmit }: Props): ReactElement {
  const { _ } = useLingui();
  const [from, setFrom] = useState(current.from);
  const [to, setTo] = useState(current.to);
  const [problem, setProblem] = useState<RangeProblem | null>(null);

  function fill(range: DateRange): void {
    setFrom(range.from);
    setTo(range.to);
    setProblem(null);
  }

  function submit(event: { preventDefault: () => void }): void {
    event.preventDefault();
    const found = checkRange(from, to);
    setProblem(found);
    if (found === null) onSubmit({ from, to });
  }

  const week = weekOf(today);
  return (
    <Dialog title={_("plan.range.title")} isOpen onClose={onClose}>
      <form onSubmit={submit} noValidate>
        <div className="field">
          <label htmlFor="range-from">{_("plan.range.from")}</label>
          <input
            id="range-from"
            type="date"
            value={from}
            aria-invalid={problem === "date" || problem === "order" ? "true" : undefined}
            aria-describedby={problem ? "range-error" : undefined}
            onChange={(event) => setFrom(event.currentTarget.value)}
          />
        </div>
        <div className="field">
          <label htmlFor="range-to">{_("plan.range.to")}</label>
          <input
            id="range-to"
            type="date"
            value={to}
            aria-invalid={problem ? "true" : undefined}
            aria-describedby={problem ? "range-error" : undefined}
            onChange={(event) => setTo(event.currentTarget.value)}
          />
        </div>
        {problem ? (
          <p id="range-error" role="alert" className="field-error">
            {_(PROBLEM_KEYS[problem], { maxDays: MAX_DAYS })}
          </p>
        ) : null}
        <div className="range-shortcuts">
          <button type="button" className="btn" onClick={() => fill(week)}>
            {_("plan.range.thisWeek")}
          </button>
          <button
            type="button"
            className="btn"
            onClick={() => fill({ from: week.from, to: addDays(week.from, 13) })}
          >
            {_("plan.range.nextTwo")}
          </button>
        </div>
        <div className="dialog-actions">
          <button type="button" className="btn" onClick={onClose}>
            {_("common.cancel")}
          </button>
          <button type="submit" className="btn btn-primary">
            {_("plan.range.show")}
          </button>
        </div>
      </form>
    </Dialog>
  );
}

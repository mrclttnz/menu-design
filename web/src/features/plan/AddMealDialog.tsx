import { useLingui } from "@lingui/react";
import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState, type ReactElement } from "react";
import { resolveProblem, type ResolvedMessage } from "../../api/errors";
import { MEAL_TYPE_KEYS, PLAN_KEY, readMeal, setPresence, type MealType } from "../../api/plan";
import { Dialog } from "../../components/Dialog";
import { useSession } from "../../session";

interface Props {
  date: string;
  /** Tipi di pasto che il giorno non ha (compresi i pasti di default tolti), già ordinati. */
  available: MealType[];
  onClose: () => void;
}

// D-07 «Aggiungi un pasto a un giorno» (M0): riattiva il pasto di quel tipo, vuoto. Si legge prima
// la versione del pasto (`GET`, `ETag`) e la si rimanda in `If-Match` (ADR-0008).
export function AddMealDialog({ date, available, onClose }: Props): ReactElement {
  const { _ } = useLingui();
  const client = useQueryClient();
  const { reload } = useSession();
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<ResolvedMessage | null>(null);
  const sending = useRef(false);
  const alertBox = useRef<HTMLParagraphElement>(null);

  useEffect(() => {
    if (failure) alertBox.current?.focus();
  }, [failure]);

  async function add(type: MealType): Promise<void> {
    if (sending.current) return;
    sending.current = true;
    setBusy(true);
    setFailure(null);
    const read = await readMeal(date, type, 0);
    const result = read.ok
      ? read.data.present
        ? read
        : await setPresence(date, type, 0, read.data.contentVersion, true)
      : read;
    sending.current = false;
    setBusy(false);
    if (result.ok) {
      await client.invalidateQueries({ queryKey: PLAN_KEY });
      onClose();
      return;
    }
    setFailure(resolveProblem(result.problem));
    if (result.status === 403) void reload();
    if (result.status === 412) void client.invalidateQueries({ queryKey: PLAN_KEY });
  }

  return (
    <Dialog title={_("meal.add.title")} isOpen onClose={onClose}>
      <ul className="add-meal-list" aria-busy={busy ? "true" : undefined}>
        {available.map((type) => (
          <li key={type}>
            <button
              type="button"
              className="btn btn-block"
              aria-disabled={busy ? "true" : undefined}
              onClick={() => void add(type)}
            >
              {_(MEAL_TYPE_KEYS[type])}
            </button>
          </li>
        ))}
      </ul>
      {failure ? (
        <p ref={alertBox} role="alert" tabIndex={-1} className="state state-error">
          {_(failure.id, failure.values)}
        </p>
      ) : null}
      <div className="dialog-actions">
        <button type="button" className="btn" onClick={onClose}>
          {_("common.cancel")}
        </button>
      </div>
    </Dialog>
  );
}

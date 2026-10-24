import { useLingui } from "@lingui/react";
import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState, type ReactElement } from "react";
import {
  setDishStatus,
  KEYS,
  NEXT_STATUS,
  STATUS_COMMAND_KEYS,
  STATUS_KEYS,
  type DishDetail,
  type DishStatus,
} from "../../api/dishes";
import { resolveProblem, type ResolvedMessage } from "../../api/errors";
import { useToast } from "../../components/Toast";
import { useSession } from "../../session";

// Se il server non indica i secondi di attesa, il pulsante torna attivo dopo questo tempo.
const DEFAULT_WAIT_S = 30;

interface Props {
  dish: DishDetail;
  /** Il piatto non esiste più (404): la scheda mostra «non trovato». */
  onGone: () => void;
}

// S-06, comando di stato (US-005): un solo pulsante, cambio immediato con avviso e «Annulla».
// Si mostra solo ad A e P (il chiamante decide, DD-04); il server decide comunque (AC-005.4).
export function StatusCommand({ dish, onGone }: Props): ReactElement {
  const { _ } = useLingui();
  const client = useQueryClient();
  const toast = useToast();
  const { reload } = useSession();
  const [failure, setFailure] = useState<ResolvedMessage | null>(null);
  const [busy, setBusy] = useState(false);
  const [waiting, setWaiting] = useState(false);
  const sending = useRef(false);
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const alertBox = useRef<HTMLDivElement>(null);
  const latest = useRef(dish);
  latest.current = dish;

  useEffect(() => () => clearTimeout(timer.current), []);
  useEffect(() => {
    if (failure) alertBox.current?.focus();
  }, [failure]);

  async function change(status: DishStatus, undoTo?: DishStatus): Promise<void> {
    if (sending.current || waiting) return;
    sending.current = true;
    setBusy(true);
    setFailure(null);
    const current = latest.current;
    const result = await setDishStatus(current.id, current.version, status);
    sending.current = false;
    setBusy(false);
    if (result.ok) {
      client.setQueryData(KEYS.detail(current.id), result.data);
      void client.invalidateQueries({ queryKey: KEYS.list });
      toast.show({
        message: _("dish.status.changed.toast", {
          name: result.data.name,
          status: _(STATUS_KEYS[result.data.status]),
        }),
        ...(undoTo === undefined
          ? {
              actionLabel: _("common.undo"),
              onAction: () => void change(current.status, current.status),
            }
          : {}),
      });
      return;
    }
    const { status: http, problem } = result;
    if (http === 404) {
      onGone();
      return;
    }
    setFailure(resolveProblem(problem));
    if (http === 412) void client.invalidateQueries({ queryKey: KEYS.detail(current.id) });
    if (http === 403) void reload();
    if (http === 429) {
      const seconds = problem.params?.["retryAfterSeconds"];
      const wait = typeof seconds === "number" && seconds > 0 ? seconds : DEFAULT_WAIT_S;
      setWaiting(true);
      clearTimeout(timer.current);
      timer.current = setTimeout(() => setWaiting(false), Math.min(wait, 3600) * 1000);
    }
  }

  const target = NEXT_STATUS[dish.status];
  const disabled = busy || waiting;
  return (
    <div className="status-command">
      <button
        type="button"
        className="btn"
        aria-disabled={disabled ? "true" : undefined}
        onClick={() => void change(target)}
      >
        {_(STATUS_COMMAND_KEYS[target])}
      </button>
      {failure ? (
        <div ref={alertBox} role="alert" tabIndex={-1} className="state state-error">
          <p>{_(failure.id, failure.values)}</p>
        </div>
      ) : null}
    </div>
  );
}

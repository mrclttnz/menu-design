import { useLingui } from "@lingui/react";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactElement,
  type ReactNode,
} from "react";
import "./Toast.css";

export interface ToastOptions {
  message: string;
  /** `success` (predefinito): role="status", scompare da solo. `error`: role="alert", persistente. */
  kind?: "success" | "error";
  actionLabel?: string;
  onAction?: () => void;
}

interface ToastApi {
  show(options: ToastOptions): number;
  dismiss(id: number): void;
}

interface ToastItem extends ToastOptions {
  id: number;
}

const ToastContext = createContext<ToastApi | null>(null);

const SUCCESS_MS = 6_000;
// WCAG 2.2.1: con un'azione («Annulla») il tempo per usarla è almeno 10 secondi.
const ACTION_MS = 12_000;

export function ToastProvider({ children }: { children: ReactNode }): ReactElement {
  const { _ } = useLingui();
  const [items, setItems] = useState<ToastItem[]>([]);
  const nextId = useRef(1);
  const timers = useRef(new Map<number, ReturnType<typeof setTimeout>>());

  const dismiss = useCallback((id: number) => {
    const timer = timers.current.get(id);
    if (timer !== undefined) clearTimeout(timer);
    timers.current.delete(id);
    setItems((current) => current.filter((item) => item.id !== id));
  }, []);

  const show = useCallback(
    (options: ToastOptions) => {
      const id = nextId.current++;
      setItems((current) => [...current, { ...options, id }]);
      if (options.kind !== "error") {
        const ms = options.actionLabel ? ACTION_MS : SUCCESS_MS;
        timers.current.set(
          id,
          setTimeout(() => dismiss(id), ms),
        );
      }
      return id;
    },
    [dismiss],
  );

  useEffect(() => {
    const pending = timers.current;
    return () => {
      for (const timer of pending.values()) clearTimeout(timer);
      pending.clear();
    };
  }, []);

  const api = useMemo(() => ({ show, dismiss }), [show, dismiss]);
  const successes = items.filter((item) => item.kind !== "error");
  const errors = items.filter((item) => item.kind === "error");

  const renderAction = (item: ToastItem): ReactElement | null =>
    item.actionLabel ? (
      <button
        type="button"
        className="btn"
        onClick={() => {
          item.onAction?.();
          dismiss(item.id);
        }}
      >
        {item.actionLabel}
      </button>
    ) : null;

  return (
    <ToastContext.Provider value={api}>
      {children}
      <div className="toast-region">
        <div role="status" className="toast-list">
          {successes.map((item) => (
            <div key={item.id} className="toast">
              <span>{item.message}</span>
              {renderAction(item)}
            </div>
          ))}
        </div>
        {errors.map((item) => (
          <div key={item.id} role="alert" className="toast toast-error">
            <span>{item.message}</span>
            {renderAction(item)}
            <button type="button" className="btn" onClick={() => dismiss(item.id)}>
              {_("common.close")}
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast(): ToastApi {
  const api = useContext(ToastContext);
  if (!api) throw new Error("useToast va usato dentro un ToastProvider");
  return api;
}

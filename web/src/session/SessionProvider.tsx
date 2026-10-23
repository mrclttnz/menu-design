import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactElement,
  type ReactNode,
} from "react";
import { configureApi, type ProblemInfo, type ResponseInfo } from "../api/client";
import {
  ANONYMOUS,
  fetchSession,
  isSessionView,
  requestLogout,
  sessionEndOf,
  SESSION_QUERY_KEY as KEY,
  type SessionEnd,
  type SessionView,
} from "../api/session";
import { rememberSession, sessionCsrfToken } from "./csrf";

export interface SessionState {
  /** Prima risposta di `GET /session` ancora attesa. */
  loading: boolean;
  /** Il caricamento è fallito e non c'è una sessione nota. */
  failed: boolean;
  session: SessionView | undefined;
  /** Token CSRF della sessione autenticata; `undefined` se anonimi. */
  csrfToken: string | undefined;
  /** Perché la sessione è finita in questa pagina (una volta). */
  notice: SessionEnd | null;
  /** Errore del caricamento (solo con `failed`). */
  error: ProblemInfo | undefined;
  /** Rilegge la sessione dal server. */
  reload: () => Promise<void>;
  /** Esce: `true` se il server ha invalidato la sessione. */
  logout: () => Promise<boolean>;
}

class SessionLoadError extends Error {
  constructor(readonly problem: ProblemInfo) {
    super();
  }
}

async function loadSession(): Promise<SessionView> {
  const result = await fetchSession();
  if (!result.ok) throw new SessionLoadError(result.problem);
  if (!isSessionView(result.data)) throw new SessionLoadError({ code: "invalid_response" });
  rememberSession(result.data);
  return result.data;
}

const SessionContext = createContext<SessionState | null>(null);

export function SessionProvider({ children }: { children: ReactNode }): ReactElement {
  const client = useQueryClient();
  const [notice, setNotice] = useState<SessionEnd | null>(null);
  const query = useQuery({
    queryKey: KEY,
    queryFn: loadSession,
    retry: false,
    staleTime: Infinity,
    gcTime: Infinity,
    refetchOnMount: false,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
  });
  const { refetch } = query;

  // Una sessione che finisce (401 o uscita): subito anonimi in memoria, poi si rilegge dal server.
  // Se la sessione è già anonima non si fa nulla (più chiamate che falliscono insieme: un solo avviso).
  useEffect(() => {
    const leave = (kind: SessionEnd): void => {
      if (client.getQueryData<SessionView>(KEY)?.authenticated !== true) return;
      client.setQueryData(KEY, ANONYMOUS);
      rememberSession(ANONYMOUS);
      setNotice(kind);
      void client.refetchQueries({ queryKey: KEY });
    };
    const onResponse = (info: ResponseInfo): void => {
      const end = sessionEndOf(info);
      if (end) leave(end);
    };
    return configureApi({ csrfToken: sessionCsrfToken, onResponse });
  }, [client]);

  const reload = useCallback(async (): Promise<void> => {
    await refetch();
  }, [refetch]);

  const logout = useCallback(async (): Promise<boolean> => {
    return (await requestLogout()).ok;
  }, []);

  const session = query.data;
  const failed = !session && query.isError && !query.isFetching;
  const error = query.error instanceof SessionLoadError ? query.error.problem : undefined;
  const value = useMemo<SessionState>(
    () => ({
      loading: !session && !failed,
      failed,
      session,
      csrfToken: session?.authenticated ? session.csrfToken : undefined,
      notice: session?.authenticated ? null : notice,
      error: failed ? (error ?? { code: "unknown" }) : undefined,
      reload,
      logout,
    }),
    [session, failed, notice, error, reload, logout],
  );
  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession(): SessionState {
  const state = useContext(SessionContext);
  if (!state) throw new Error("useSession va usato dentro un SessionProvider");
  return state;
}

// @vitest-environment happy-dom
// Stati comuni (UX §5.1, NFR-013): EmptyState, ErrorState, Skeleton. Testi dal catalogo `it`.
// Contratto assunto (web/src/components, esportazioni con nome):
//   <EmptyState title description? action?={{ label, onPress }} headingLevel?={1|2|3} />
//   <ErrorState error?={unknown} onRetry?={() => void} />   (il messaggio viene da resolveProblem)
//   <Skeleton rows?={number} />
import { act, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { EmptyState } from "../../../src/components/EmptyState";
import { ErrorState } from "../../../src/components/ErrorState";
import { Skeleton } from "../../../src/components/Skeleton";
import { activateLocale } from "../../../src/i18n";
import { renderIt } from "../../support/render";

// Catalogo caricato prima dei timer finti (import dinamico).
beforeAll(async () => {
  await activateLocale("it");
});

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

describe("EmptyState: titolo breve, una frase, una sola azione consigliata", () => {
  it("mostra titolo come intestazione e descrizione", async () => {
    await renderIt(
      <EmptyState
        title="Nessun pasto da pianificare"
        description="Scegli quali pasti compaiono ogni giorno."
      />,
    );
    expect(
      screen.getByRole("heading", { name: "Nessun pasto da pianificare", level: 2 }),
    ).not.toBeNull();
    expect(screen.getByText("Scegli quali pasti compaiono ogni giorno.")).not.toBeNull();
  });

  it("senza azione non mostra pulsanti (mai solo «Nessun dato» con un pulsante finto)", async () => {
    await renderIt(<EmptyState title="Vuoto" />);
    expect(screen.queryAllByRole("button")).toHaveLength(0);
    expect(screen.queryAllByRole("link")).toHaveLength(0);
  });

  it("con azione: un solo pulsante, con il nome dato, che chiama il gestore", async () => {
    const onPress = vi.fn();
    await renderIt(
      <EmptyState title="Vuoto" action={{ label: "Aggiungi un pasto a un giorno", onPress }} />,
    );
    const buttons = screen.getAllByRole("button");
    expect(buttons).toHaveLength(1);
    expect(buttons[0]?.textContent).toBe("Aggiungi un pasto a un giorno");
    await userEvent.setup().click(buttons[0] as HTMLElement);
    expect(onPress).toHaveBeenCalledTimes(1);
  });

  it("il livello dell intestazione è configurabile (un h1 per schermata, UX 8.1)", async () => {
    await renderIt(<EmptyState title="Titolo" headingLevel={1} />);
    expect(screen.getByRole("heading", { level: 1 })).not.toBeNull();
  });

  it("il testo è mostrato come testo, mai interpretato come HTML (THR-070)", async () => {
    await renderIt(
      <EmptyState title={"<img src=x onerror=alert(1)>"} description={"<b>grassetto</b>"} />,
    );
    expect(document.querySelector("img")).toBeNull();
    expect(document.querySelector("b")).toBeNull();
    expect(screen.getByText("<b>grassetto</b>")).not.toBeNull();
  });
});

describe("ErrorState: messaggio dal codice del server, mai title/detail", () => {
  it.each([
    [
      { code: "not_found", title: "Not Found SECRET" },
      "Non troviamo quello che cerchi. Potrebbe essere stato eliminato.",
    ],
    [{ code: "forbidden" }, "Non hai il permesso di fare questa operazione."],
    [{ code: "internal", detail: "SQL SECRET" }, "Qualcosa non ha funzionato. Riprova tra poco."],
    [{ code: "network_error" }, "Non riesco a collegarmi. Controlla la connessione e riprova."],
    [undefined, "Qualcosa non ha funzionato. Riprova tra poco."],
    [{ code: "codice_nuovo_del_futuro" }, "Qualcosa non ha funzionato. Riprova tra poco."],
  ])("errore %j -> «%s»", async (error, text) => {
    await renderIt(<ErrorState error={error} />);
    const alert = screen.getByRole("alert");
    expect(alert.textContent).toContain(text);
    expect(alert.textContent).not.toMatch(/SECRET/);
  });

  it.each([
    [1, "Troppi tentativi. Riprova tra 1 secondo."],
    [2, "Troppi tentativi. Riprova tra 2 secondi."],
    [5, "Troppi tentativi. Riprova tra 5 secondi."],
  ])("rate_limited con %i secondi: plurale ICU italiano", async (seconds, text) => {
    await renderIt(
      <ErrorState error={{ code: "rate_limited", params: { retryAfterSeconds: seconds } }} />,
    );
    expect(screen.getByRole("alert").textContent).toContain(text);
  });

  it("senza onRetry non c è pulsante; con onRetry c è «Riprova» e riporta il focus sull avviso", async () => {
    const { unmount } = await renderIt(<ErrorState error={{ code: "internal" }} />);
    expect(screen.queryAllByRole("button")).toHaveLength(0);
    unmount();

    const onRetry = vi.fn();
    await renderIt(<ErrorState error={{ code: "internal" }} onRetry={onRetry} />);
    const retry = screen.getByRole("button", { name: "Riprova" });
    await userEvent.setup().click(retry);
    expect(onRetry).toHaveBeenCalledTimes(1);
    expect(document.activeElement).toBe(screen.getByRole("alert"));
  });

  it("un valore ostile in params non diventa HTML", async () => {
    await renderIt(
      <ErrorState
        error={{
          code: "reauth_wrong_account",
          params: { expectedEmailMasked: "<img src=x onerror=alert(1)>" },
        }}
      />,
    );
    expect(document.querySelector("img")).toBeNull();
  });
});

describe("Skeleton: caricamento visibile e annunciato (UX 5.1, WCAG 4.1.3)", () => {
  it("la regione è occupata (aria-busy) e ha un nome accessibile dal catalogo", async () => {
    await renderIt(<Skeleton rows={3} />);
    const busy = document.querySelector('[aria-busy="true"]');
    expect(busy).not.toBeNull();
    expect(within(busy as HTMLElement).getByText("Caricamento…")).not.toBeNull();
  });

  it("le forme decorative sono nascoste ai lettori di schermo, una per riga", async () => {
    await renderIt(<Skeleton rows={4} />);
    const busy = document.querySelector('[aria-busy="true"]') as HTMLElement;
    expect(busy.querySelectorAll('[aria-hidden="true"]').length).toBeGreaterThanOrEqual(4);
  });

  it("dopo 10 secondi compare «Ci sta mettendo più del solito…», non prima", async () => {
    vi.useFakeTimers();
    await renderIt(<Skeleton rows={2} />);
    act(() => {
      vi.advanceTimersByTime(9_999);
    });
    expect(screen.queryByText("Ci sta mettendo più del solito…")).toBeNull();
    act(() => {
      vi.advanceTimersByTime(2);
    });
    expect(screen.getByText("Ci sta mettendo più del solito…")).not.toBeNull();
  });

  it("smontato prima dei 10 secondi non lascia timer né avvisi di React", async () => {
    vi.useFakeTimers();
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => undefined);
    const { unmount } = await renderIt(<Skeleton />);
    unmount();
    expect(vi.getTimerCount()).toBe(0);
    act(() => {
      vi.advanceTimersByTime(20_000);
    });
    expect(consoleError).not.toHaveBeenCalled();
  });
});

// @vitest-environment happy-dom
// Toast e Dialog (UX 9.5, 8.1: 2.1.2, 2.2.1, 2.4.3, 4.1.2, 4.1.3).
// Contratto assunto:
//   <ToastProvider>…</ToastProvider>, useToast() -> { show({ message, kind?, actionLabel?, onAction? }) -> id, dismiss(id) }
//     kind 'success' (predefinito): role="status"; kind 'error': role="alert", persistente.
//   <Dialog title isOpen onClose dismissable?={true} kind?={'dialog'|'alert'}>figli</Dialog>
import { act, fireEvent, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState, type ReactElement } from "react";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { Dialog } from "../../../src/components/Dialog";
import { ToastProvider, useToast } from "../../../src/components/Toast";
import { activateLocale } from "../../../src/i18n";
import { renderIt } from "../../support/render";

// Il catalogo si carica con un import dinamico: va fatto prima dei timer finti, che lo bloccherebbero.
beforeAll(async () => {
  await activateLocale("it");
});

afterEach(() => {
  vi.useRealTimers();
});

function ToastButton({
  options,
}: {
  options: Parameters<ReturnType<typeof useToast>["show"]>[0];
}): ReactElement {
  const toast = useToast();
  return (
    <button type="button" onClick={() => toast.show(options)}>
      apri-toast
    </button>
  );
}

// Con timer finti si usa fireEvent: user-event + Testing Library attendono un setTimeout reale
// e restano appesi sotto Vitest (nessuna rilevazione dei timer finti di Vitest).
async function showToast(
  options: Parameters<ReturnType<typeof useToast>["show"]>[0],
): Promise<void> {
  vi.useFakeTimers({
    toFake: ["setTimeout", "clearTimeout", "setInterval", "clearInterval", "Date"],
  });
  await renderIt(
    <ToastProvider>
      <ToastButton options={options} />
    </ToastProvider>,
  );
  fireEvent.click(screen.getByRole("button", { name: "apri-toast" }));
}

const advance = (ms: number): void => {
  act(() => {
    vi.advanceTimersByTime(ms);
  });
};

describe("Toast", () => {
  it('successo: annunciato con role="status" e scompare da solo', async () => {
    await showToast({ message: "Aggiunto Risotto" });
    expect(screen.getByRole("status").textContent).toContain("Aggiunto Risotto");
    advance(1_000);
    expect(screen.queryByText("Aggiunto Risotto")).not.toBeNull();
    advance(15_000);
    expect(screen.queryByText("Aggiunto Risotto")).toBeNull();
  });

  it("con «Annulla» resta almeno 10 secondi (WCAG 2.2.1) e l azione chiama il gestore", async () => {
    const onAction = vi.fn();
    await showToast({ message: "Tolto Risotto", actionLabel: "Annulla", onAction });
    advance(9_900);
    expect(screen.queryByText("Tolto Risotto")).not.toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Annulla" }));
    expect(onAction).toHaveBeenCalledTimes(1);
    expect(screen.queryByText("Tolto Risotto")).toBeNull();
  });

  it('errore: role="alert", persistente finché l utente non lo chiude con «Chiudi»', async () => {
    await showToast({ message: "Non siamo riusciti a salvare.", kind: "error" });
    expect(screen.getByRole("alert").textContent).toContain("Non siamo riusciti a salvare.");
    advance(120_000);
    expect(screen.queryByRole("alert")).not.toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Chiudi" }));
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("il messaggio è testo, mai HTML (THR-070)", async () => {
    await showToast({ message: "<img src=x onerror=alert(1)>" });
    expect(document.querySelector("img")).toBeNull();
  });

  it("useToast fuori dal provider è un errore esplicito, non un toast perso", async () => {
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => undefined);
    await expect(renderIt(<ToastButton options={{ message: "x" }} />)).rejects.toThrow(
      /ToastProvider/,
    );
    consoleError.mockRestore();
  });
});

function DialogHarness({
  dismissable = true,
  kind = "dialog" as const,
}: {
  dismissable?: boolean;
  kind?: "dialog" | "alert";
}): ReactElement {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button type="button" onClick={() => setOpen(true)}>
        Apri
      </button>
      <Dialog
        title="Conferma l operazione"
        isOpen={open}
        onClose={() => setOpen(false)}
        dismissable={dismissable}
        kind={kind}
      >
        <p>Corpo della finestra</p>
        <button type="button" onClick={() => setOpen(false)}>
          Fatto
        </button>
      </Dialog>
    </>
  );
}

describe("Dialog", () => {
  it('chiusa: niente nel DOM; aperta: role="dialog" con nome dal titolo e focus dentro', async () => {
    const user = userEvent.setup();
    await renderIt(<DialogHarness />);
    expect(screen.queryByRole("dialog")).toBeNull();
    await user.click(screen.getByRole("button", { name: "Apri" }));
    const dialog = screen.getByRole("dialog", { name: "Conferma l operazione" });
    expect(dialog.contains(document.activeElement)).toBe(true);
    expect(screen.getByText("Corpo della finestra")).not.toBeNull();
  });

  it("Esc chiude e il focus torna al pulsante che l ha aperta (UX 2.4.3)", async () => {
    const user = userEvent.setup();
    await renderIt(<DialogHarness />);
    const opener = screen.getByRole("button", { name: "Apri" });
    await user.click(opener);
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(document.activeElement).toBe(opener);
  });

  it("il pulsante interno chiude e il focus torna all apertura", async () => {
    const user = userEvent.setup();
    await renderIt(<DialogHarness />);
    const opener = screen.getByRole("button", { name: "Apri" });
    await user.click(opener);
    await user.click(screen.getByRole("button", { name: "Fatto" }));
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(document.activeElement).toBe(opener);
  });

  it("il focus resta intrappolato nella finestra con Tab (modale)", async () => {
    const user = userEvent.setup();
    await renderIt(<DialogHarness />);
    await user.click(screen.getByRole("button", { name: "Apri" }));
    const dialog = screen.getByRole("dialog");
    for (let i = 0; i < 6; i += 1) {
      await user.tab();
      expect(
        dialog.contains(document.activeElement),
        `Tab n. ${i + 1} è uscito dalla finestra`,
      ).toBe(true);
    }
  });

  it("dismissable=false: Esc non chiude (conflitti e conferme irreversibili, UX 2.1.2)", async () => {
    const user = userEvent.setup();
    await renderIt(<DialogHarness dismissable={false} />);
    await user.click(screen.getByRole("button", { name: "Apri" }));
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeNull();
    await user.click(screen.getByRole("button", { name: "Fatto" }));
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it('kind="alert": role="alertdialog"', async () => {
    const user = userEvent.setup();
    await renderIt(<DialogHarness kind="alert" />);
    await user.click(screen.getByRole("button", { name: "Apri" }));
    expect(screen.getByRole("alertdialog", { name: "Conferma l operazione" })).not.toBeNull();
  });

  it("il titolo è testo, mai HTML (THR-070)", async () => {
    function Hostile(): ReactElement {
      return (
        <Dialog title={"<img src=x onerror=alert(1)>"} isOpen onClose={() => undefined}>
          <button type="button">ok</button>
        </Dialog>
      );
    }
    await renderIt(<Hostile />);
    expect(document.querySelector("img")).toBeNull();
  });
});

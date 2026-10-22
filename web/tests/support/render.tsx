// Rendering con i provider reali: catalogo `it` vero (nessun mock dell'i18n), così i test
// verificano anche i testi che l'utente leggerà.
import { I18nProvider } from "@lingui/react";
import { cleanup, render, type RenderResult } from "@testing-library/react";
import type { ReactElement } from "react";
import { afterEach } from "vitest";
import { activateLocale, i18n } from "../../src/i18n";

afterEach(() => {
  cleanup();
});

export async function renderIt(ui: ReactElement): Promise<RenderResult> {
  await activateLocale("it");
  return render(<I18nProvider i18n={i18n}>{ui}</I18nProvider>);
}

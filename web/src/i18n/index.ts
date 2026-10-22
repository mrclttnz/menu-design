// Lingue ricavate dalle cartelle di src/locales (ADR-0010): nessuna lingua scritta nel codice.
import { i18n } from "@lingui/core";
import type { Messages } from "@lingui/core";

export { i18n };
export const DEFAULT_LOCALE = "it";

const loaders = import.meta.glob<{ messages: Messages }>("../locales/*/messages.po");

export const LOCALES: string[] = Object.keys(loaders).flatMap((file) => {
  const locale = /\/locales\/([^/]+)\/messages\.po$/.exec(file)?.[1];
  return locale ? [locale] : [];
});

export async function activateLocale(locale: string = DEFAULT_LOCALE): Promise<void> {
  const chosen = LOCALES.includes(locale) ? locale : DEFAULT_LOCALE;
  const load = loaders[`../locales/${chosen}/messages.po`];
  if (!load) throw new Error("catalogo non trovato");
  const { messages } = await load();
  i18n.loadAndActivate({ locale: chosen, messages });
}

import { defineConfig } from "@lingui/cli";
import { formatter } from "@lingui/format-po";

// ADR-0010: lingua sorgente `it`, cataloghi .po con ID espliciti. Le lingue sono le cartelle
// di src/locales: aggiungerne una richiede solo file nuovi.
export default defineConfig({
  sourceLocale: "it",
  locales: ["it"],
  catalogs: [{ path: "src/locales/{locale}/messages", include: ["src"] }],
  format: formatter({ origins: false, lineNumbers: false }),
});

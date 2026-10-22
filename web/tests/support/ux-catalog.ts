// Estrae da docs/03-ux.md §7.3 le chiavi i18n e i testi italiani (fonte dei testi: la UX).
import fs from "node:fs";
import path from "node:path";
import { DOCS } from "./repo";

export interface UxMessage {
  key: string;
  text: string;
  milestone: "M1" | "M2" | null;
  section: string;
}

const SECTION_RE = /^\*\*(.+?)\*\*\s*$/;
const ROW_RE = /^\|\s*`([^`]+)`\s*(?:\((M[12])\))?\s*\|\s*(.*?)\s*\|(?:\s*[^|]*\|)?\s*$/;

export function uxMessages(): UxMessage[] {
  const text = fs.readFileSync(path.join(DOCS, "03-ux.md"), "utf8");
  const start = text.indexOf("### 7.3 Testi principali");
  const end = text.indexOf("### 7.4 Dipendenze di contenuto");
  if (start < 0 || end < 0) throw new Error("sezione 7.3 di docs/03-ux.md non trovata");
  const out: UxMessage[] = [];
  let section = "";
  for (const line of text.slice(start, end).split("\n")) {
    const heading = SECTION_RE.exec(line);
    if (heading) {
      section = heading[1] as string;
      continue;
    }
    const row = ROW_RE.exec(line);
    if (row && row[1] !== "Chiave") {
      out.push({
        key: row[1] as string,
        milestone: (row[2] as "M1" | "M2" | undefined) ?? null,
        text: (row[3] as string).replace(/\\\|/g, "|"),
        section,
      });
    }
  }
  return out;
}

/** Sezioni del catalogo che SL-01 deve contenere per intero (le altre arrivano con le viste). */
export const SL01_SECTIONS = [
  "Comuni",
  "Accesso (S-01)",
  "Guscio dell'applicazione e pagina non trovata (decisione UX, SL-01)",
  "Errori generali",
  "Errori di validazione",
];
/** Nelle sezioni di errore valgono tutte le milestone: i codici del server esistono già. */
export const ALL_MILESTONE_SECTIONS = ["Errori generali", "Errori di validazione"];

export function requiredForSl01(): UxMessage[] {
  return uxMessages().filter(
    (m) =>
      SL01_SECTIONS.includes(m.section) &&
      (m.milestone === null || ALL_MILESTONE_SECTIONS.includes(m.section)),
  );
}

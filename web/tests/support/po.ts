// Lettore minimo di cataloghi `.po` (formato di Lingui con ID espliciti): msgid -> msgstr.
// Nessuna dipendenza: il catalogo è un file di testo e il test non deve fidarsi del tool
// che lo genera. Riconosce stringhe su più righe, escape, commenti e voci obsolete (`#~`).

const ESCAPES: Record<string, string> = { n: "\n", t: "\t", r: "\r", '"': '"', "\\": "\\" };

function unquote(raw: string): string {
  const trimmed = raw.trim();
  if (!/^".*"$/s.test(trimmed)) throw new Error(`stringa PO non valida: ${raw}`);
  return trimmed.slice(1, -1).replace(/\\(.)/gs, (_match, ch: string) => ESCAPES[ch] ?? `\\${ch}`);
}

export interface PoEntry {
  id: string;
  message: string;
  line: number;
  obsolete: boolean;
}

export function parsePo(source: string): PoEntry[] {
  const entries: PoEntry[] = [];
  let field: "msgctxt" | "msgid" | "msgstr" | null = null;
  let current: { id: string; message: string; line: number; obsolete: boolean } | null = null;
  let obsolete = false;
  const lines = source.split(/\r?\n/);
  const flush = (): void => {
    if (current) entries.push(current);
    current = null;
    field = null;
  };
  lines.forEach((rawLine, index) => {
    let line = rawLine.trim();
    if (line === "") {
      flush();
      obsolete = false;
      return;
    }
    if (line.startsWith("#~")) {
      obsolete = true;
      line = line.slice(2).trim();
    } else if (line.startsWith("#")) {
      return;
    }
    const keyword = /^(msgctxt|msgid_plural|msgid|msgstr(?:\[\d+\])?)\s+(".*")$/s.exec(line);
    if (keyword) {
      const [, name, value] = keyword as unknown as [string, string, string];
      if (name === "msgid") {
        flush();
        current = { id: unquote(value), message: "", line: index + 1, obsolete };
        field = "msgid";
      } else if (name.startsWith("msgstr")) {
        field = "msgstr";
        if (current) current.message += unquote(value);
      } else {
        field = name === "msgctxt" ? "msgctxt" : null;
      }
      return;
    }
    if (line.startsWith('"') && current) {
      if (field === "msgid") current.id += unquote(line);
      else if (field === "msgstr") current.message += unquote(line);
      return;
    }
    throw new Error(`riga ${index + 1} del catalogo non riconosciuta: ${rawLine}`);
  });
  flush();
  return entries.filter((entry) => entry.id !== ""); // l'intestazione ha msgid vuoto
}

export function catalogMap(source: string): Map<string, string> {
  const map = new Map<string, string>();
  for (const entry of parsePo(source)) {
    if (!entry.obsolete) map.set(entry.id, entry.message);
  }
  return map;
}

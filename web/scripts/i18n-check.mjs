// `lingui extract --clean` non deve cambiare il catalogo committato (NFR-011).
import { spawnSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";

const root = path.resolve(import.meta.dirname, "..");
const locales = path.join(root, "src", "locales");
const read = () =>
  Object.fromEntries(
    fs
      .readdirSync(locales, { withFileTypes: true })
      .filter((e) => e.isDirectory())
      .map((e) => {
        const file = path.join(locales, e.name, "messages.po");
        return [file, fs.existsSync(file) ? fs.readFileSync(file, "utf8") : ""];
      }),
  );
const before = read();
const run = spawnSync("pnpm", ["exec", "lingui", "extract", "--clean"], {
  cwd: root,
  encoding: "utf8",
});
process.stdout.write(run.stdout ?? "");
process.stderr.write(run.stderr ?? "");
if (run.status !== 0) process.exit(run.status ?? 2);
// L'intestazione contiene la data di estrazione: non è una differenza di contenuto.
const stamp = (text) => text.replace(/^"POT-Creation-Date:.*\n/m, "");
const after = read();
const changed = Object.keys(after).filter((f) => stamp(after[f]) !== stamp(before[f]));
for (const file of Object.keys(after)) {
  if (!changed.includes(file) && after[file] !== before[file]) fs.writeFileSync(file, before[file]);
}
if (changed.length > 0) {
  console.error(`Il catalogo non coincide con il codice (ora aggiornato): ${changed.join(", ")}`);
  process.exit(1);
}
console.log("Catalogo coerente con il codice.");

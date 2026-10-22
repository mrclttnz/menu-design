// Fallisce se src/api/schema.gen.ts non coincide con ciò che openapi-typescript produce oggi
// da ../openapi.json (08 §2 «Contratto»).
import { spawnSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

const root = path.resolve(import.meta.dirname, "..");
const committed = path.join(root, "src", "api", "schema.gen.ts");
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "api-check-"));
const fresh = path.join(tmp, "schema.gen.ts");
try {
  const run = spawnSync("pnpm", ["exec", "openapi-typescript", "../openapi.json", "-o", fresh], {
    cwd: root,
    encoding: "utf8",
  });
  if (run.status !== 0) {
    console.error(`${run.stdout}${run.stderr}`);
    process.exit(2);
  }
  if (
    !fs.existsSync(committed) ||
    fs.readFileSync(committed, "utf8") !== fs.readFileSync(fresh, "utf8")
  ) {
    console.error("src/api/schema.gen.ts non è aggiornato: eseguire `pnpm run api:generate`.");
    process.exit(1);
  }
  console.log("src/api/schema.gen.ts è aggiornato rispetto a openapi.json.");
} finally {
  fs.rmSync(tmp, { recursive: true, force: true });
}

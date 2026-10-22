// Contratto: il client TypeScript generato (`src/api/schema.gen.ts`) coincide con quello che
// `openapi-typescript` produce oggi da `openapi.json` (08 §2 «Contratto»). Se il backend cambia
// il contratto e nessuno rigenera, `pnpm run api:check` esce con errore e questo test lo vede.
import { spawnSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import { OPENAPI, SRC, WEB_ROOT } from "../support/repo";

describe("client API generato", () => {
  it("esiste ed è marcato come generato (non si modifica a mano)", () => {
    const file = path.join(SRC, "api", "schema.gen.ts");
    expect(fs.existsSync(file), "src/api/schema.gen.ts assente").toBe(true);
    expect(fs.readFileSync(file, "utf8").slice(0, 600).toLowerCase()).toMatch(
      /auto-generated|do not (make direct )?change/,
    );
  });

  it("`pnpm run api:check` conferma che è aggiornato rispetto a openapi.json", () => {
    const result = spawnSync("pnpm", ["run", "--silent", "api:check"], {
      cwd: WEB_ROOT,
      encoding: "utf8",
      timeout: 120_000,
      env: { ...process.env, CI: "true" },
    });
    expect(result.status, `${result.stdout}${result.stderr}`).toBe(0);
  });

  it("il contratto sorgente è quello committato alla radice", () => {
    expect(fs.existsSync(OPENAPI)).toBe(true);
  });
});

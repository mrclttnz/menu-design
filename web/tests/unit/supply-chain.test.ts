// SR-076 / THR-090: catena di fornitura npm. Il piano (§1, §5.6) dice `.npmrc`, ma con pnpm 12
// `minimumReleaseAge` e `onlyBuiltDependencies` si leggono da `pnpm-workspace.yaml`: qui si
// chiede a pnpm stesso quali impostazioni sono EFFICACI, e si controlla il lockfile.
import { execFileSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import { WEB_ROOT } from "../support/repo";

function pnpmConfig(key: string): unknown {
  const out = execFileSync("pnpm", ["config", "get", key], {
    cwd: WEB_ROOT,
    encoding: "utf8",
    timeout: 60_000,
    env: { ...process.env, CI: "true" },
  }).trim();
  if (out === "" || out === "undefined") return undefined;
  try {
    return JSON.parse(out);
  } catch {
    return out;
  }
}

describe("impostazioni efficaci di pnpm", () => {
  it("minimumReleaseAge >= 7 giorni (10080 minuti)", () => {
    const value = pnpmConfig("minimumReleaseAge");
    expect(value, "pnpm non vede minimumReleaseAge: va in pnpm-workspace.yaml").toBeDefined();
    expect(Number(value)).toBeGreaterThanOrEqual(10_080);
  });

  it("nessuna eccezione al cooldown", () => {
    const value = pnpmConfig("minimumReleaseAgeExclude");
    expect(value === undefined || (Array.isArray(value) && value.length === 0)).toBe(true);
  });

  it("gli script di installazione sono ammessi solo per esbuild", () => {
    const value = pnpmConfig("onlyBuiltDependencies");
    expect(value, "pnpm non vede onlyBuiltDependencies").toBeDefined();
    expect((value as string[]).every((name) => name === "esbuild")).toBe(true);
  });
});

describe("pnpm-lock.yaml", () => {
  const lockPath = path.join(WEB_ROOT, "pnpm-lock.yaml");

  function packagesWithBuildScripts(): string[] {
    const names: string[] = [];
    let current: string | null = null;
    let inPackages = false;
    for (const line of fs.readFileSync(lockPath, "utf8").split("\n")) {
      if (/^\S/.test(line)) inPackages = line.startsWith("packages:");
      if (!inPackages) continue;
      const header = /^ {2}'?(@?[^@\s']+)@[^:]+:\s*$/.exec(line);
      if (header) current = header[1] as string;
      else if (current && /^ {4}requiresBuild: true\s*$/.test(line)) names.push(current);
    }
    return [...new Set(names)];
  }

  it("esiste ed è non vuoto", () => {
    expect(fs.statSync(lockPath).size).toBeGreaterThan(1_000);
  });

  it("ogni dipendenza con script di installazione ha una decisione esplicita", () => {
    const allowed = (pnpmConfig("onlyBuiltDependencies") as string[] | undefined) ?? [];
    const ignored = (pnpmConfig("ignoredBuiltDependencies") as string[] | undefined) ?? [];
    const undecided = packagesWithBuildScripts().filter(
      (n) => !allowed.includes(n) && !ignored.includes(n),
    );
    expect(undecided, "script di installazione non rivisti").toEqual([]);
  });

  it("tutti i pacchetti vengono dal registro, con integrità (nessun tarball/git)", () => {
    const text = fs.readFileSync(lockPath, "utf8");
    expect(text).not.toMatch(/resolution:\s*\{\s*(tarball|repo|commit)/);
    expect(text).not.toMatch(/https?:\/\/(?!registry\.npmjs\.org)[^\s'"]+\.tgz/);
    const resolutions = text.match(/resolution: \{integrity: sha(?:512|256)-/g) ?? [];
    expect(resolutions.length).toBeGreaterThan(50);
  });
});

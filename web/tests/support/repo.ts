// Percorsi del repository, calcolati dalla posizione di questo file (mai dalla cwd).
import path from "node:path";
import { fileURLToPath } from "node:url";

export const WEB_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
export const REPO_ROOT = path.resolve(WEB_ROOT, "..");
export const SRC = path.join(WEB_ROOT, "src");
export const DOCS = path.join(REPO_ROOT, "docs");
export const OPENAPI = path.join(REPO_ROOT, "openapi.json");
export const CATALOG_IT = path.join(SRC, "locales", "it", "messages.po");

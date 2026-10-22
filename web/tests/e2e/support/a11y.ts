// 08 §15: axe con i tag WCAG 2.0-2.2 A/AA. Fallisce con violazioni serious o critical;
// moderate e minor vanno nel report come avvisi (annotazioni).
import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

const TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"];

export async function expectNoSeriousA11y(page: Page, context?: string): Promise<void> {
  const results = await new AxeBuilder({ page }).withTags(TAGS).analyze();
  const blocking = results.violations.filter(
    (v) => v.impact === "serious" || v.impact === "critical",
  );
  for (const v of results.violations.filter((x) => !blocking.includes(x))) {
    test
      .info()
      .annotations.push({ type: "a11y-warning", description: `${v.id} (${v.impact}): ${v.help}` });
  }
  const summary = blocking.map(
    (v) =>
      `${v.id} [${v.impact}] ${v.help} -> ${v.nodes.map((n) => n.target.join(" ")).join(" | ")}`,
  );
  expect(summary, `violazioni di accessibilità${context ? ` (${context})` : ""}`).toEqual([]);
}

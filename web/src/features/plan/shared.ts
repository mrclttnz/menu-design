import { useLingui } from "@lingui/react";
import { useCallback } from "react";
import type { ApiResult, ProblemInfo } from "../../api/client";
import { MEAL_TYPE_KEYS, type MealView } from "../../api/plan";
import { useSession } from "../../session";

/** Chi può cambiare il piano in M0 (DD-04); il server decide comunque (SR-009). */
export function useCanPlan(): boolean {
  const { session } = useSession();
  const role = session?.authenticated ? session.person?.role : undefined;
  return role === "admin" || role === "planner";
}

export class RequestFailed extends Error {
  constructor(
    readonly problem: ProblemInfo,
    readonly status: number,
  ) {
    super();
  }
}

/** Il dato di una risposta riuscita; altrimenti lancia l'errore per React Query. */
export function unwrap<T>(result: ApiResult<T>): T {
  if (!result.ok) throw new RequestFailed(result.problem, result.status);
  return result.data;
}

/** Nome del pasto: l'«Altro pasto» con un nome mostra il nome scelto, gli altri il tipo (catalogo). */
export function useMealLabel(): (meal: Pick<MealView, "mealType" | "name">) => string {
  const { _ } = useLingui();
  return useCallback(
    (meal) =>
      meal.mealType === "other" && meal.name ? meal.name : _(MEAL_TYPE_KEYS[meal.mealType]),
    [_],
  );
}

import { useLingui } from "@lingui/react";
import { useQuery } from "@tanstack/react-query";
import { useCallback } from "react";
import { COURSE_KEYS, KEYS, listCourses, type Course } from "../../api/dishes";
import { useSession } from "../../session";

/** Chi può creare e modificare piatti in M0 (DD-04); il server decide comunque (SR-009). */
export function useCanWriteDishes(): boolean {
  const { session } = useSession();
  const role = session?.authenticated ? session.person?.role : undefined;
  return role === "admin" || role === "planner";
}

export class RequestFailed extends Error {
  constructor(
    readonly problem: { code: string; params?: Record<string, unknown> },
    readonly status: number,
  ) {
    super();
  }
}

export function useCourses() {
  return useQuery({
    queryKey: KEYS.courses,
    staleTime: 5 * 60_000,
    retry: false,
    queryFn: async (): Promise<Course[]> => {
      const result = await listCourses();
      if (!result.ok) throw new RequestFailed(result.problem, result.status);
      return result.data.items;
    },
  });
}

/** Etichetta di una portata: base dal catalogo, personalizzata con il suo nome (testo). */
export function useCourseLabel(courses: Course[] | undefined): (id: string) => string {
  const { _ } = useLingui();
  return useCallback(
    (id: string): string => {
      const course = courses?.find((c) => c.id === id);
      if (!course) return "";
      if (course.baseCode && Object.hasOwn(COURSE_KEYS, course.baseCode)) {
        return _(COURSE_KEYS[course.baseCode] as string);
      }
      return course.name ?? "";
    },
    [courses, _],
  );
}

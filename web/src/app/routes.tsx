import { lazy, Suspense, type ReactElement } from "react";
import { type RouteObject } from "react-router";
import { DishesPage, DishFormPage, DishPage } from "../features/dishes";
import { AltroPage } from "../features/altro/AltroPage";
import { LoginPage } from "../features/auth/LoginPage";
import { Skeleton } from "../components/Skeleton";
import { NotFoundPage } from "./NotFoundPage";
import { HomeRedirect, RequireSession } from "./RequireSession";
import { RootLayout } from "./RootLayout";

// Piano e pasto in un chunk a parte: il bundle iniziale resta nel budget (NFR-001).
const PlanPage = lazy(() => import("../features/plan").then((m) => ({ default: m.PlanPage })));
const MealPage = lazy(() => import("../features/plan").then((m) => ({ default: m.MealPage })));
const later = (page: ReactElement): ReactElement => (
  <Suspense fallback={<Skeleton />}>{page}</Suspense>
);

// Rotte della SPA (docs/03-ux.md §3). `/` porta al piano con una sessione, a S-01 senza.
export const routes: RouteObject[] = [
  {
    element: <RootLayout />,
    children: [
      { index: true, element: <HomeRedirect /> },
      { path: "accedi", element: <LoginPage /> },
      {
        element: <RequireSession />,
        children: [
          { path: "piano", element: later(<PlanPage />) },
          { path: "piano/:data/:pastoId", element: later(<MealPage />) },
          { path: "altro", element: <AltroPage /> },
          {
            path: "piatti",
            element: <DishesPage />,
          },
          {
            path: "piatti/nuovo",
            element: <DishFormPage />,
          },
          {
            path: "piatti/:dishId",
            element: <DishPage />,
          },
          {
            path: "piatti/:dishId/modifica",
            element: <DishFormPage />,
          },
        ],
      },
      { path: "*", element: <NotFoundPage /> },
    ],
  },
];

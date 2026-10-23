import { type RouteObject } from "react-router";
import { AltroPage } from "../features/altro/AltroPage";
import { LoginPage } from "../features/auth/LoginPage";
import { PlanPage } from "../features/plan/PlanPage";
import { NotFoundPage } from "./NotFoundPage";
import { HomeRedirect, RequireSession } from "./RequireSession";
import { RootLayout } from "./RootLayout";

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
          { path: "piano", element: <PlanPage /> },
          { path: "altro", element: <AltroPage /> },
        ],
      },
      { path: "*", element: <NotFoundPage /> },
    ],
  },
];

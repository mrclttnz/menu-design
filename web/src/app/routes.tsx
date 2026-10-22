import { Navigate, type RouteObject } from "react-router";
import { LoginPage } from "../features/auth/LoginPage";
import { NotFoundPage } from "./NotFoundPage";
import { RootLayout } from "./RootLayout";

// Rotte della SPA (docs/03-ux.md §3). Senza sessione in questa slice, `/` porta a S-01.
export const routes: RouteObject[] = [
  {
    element: <RootLayout />,
    children: [
      { index: true, element: <Navigate to="/accedi" replace /> },
      { path: "accedi", element: <LoginPage /> },
      { path: "*", element: <NotFoundPage /> },
    ],
  },
];

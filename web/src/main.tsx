import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { createBrowserRouter, RouterProvider } from "react-router";
import { AppProviders } from "./app/providers";
import { routes } from "./app/routes";
import { activateLocale } from "./i18n";
import "./styles/tokens.css";
import "./styles/base.css";

const container = document.getElementById("root");
if (!container) throw new Error("radice mancante");
const root = createRoot(container);
const router = createBrowserRouter(routes);

void activateLocale().then(() => {
  root.render(
    <StrictMode>
      <AppProviders>
        <RouterProvider router={router} />
      </AppProviders>
    </StrictMode>,
  );
});

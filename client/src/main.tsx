import { lazy, Suspense } from "react";
import { createRoot } from "react-dom/client";
import { PlayerProvider } from "./Player";
import { AccountsShell } from "./AccountsShell";
import "./styles.css";
const LegacyTools = lazy(() =>
  import("./LegacyTools").then((m) => ({ default: m.LegacyTools })),
);
createRoot(document.getElementById("root")!).render(
  <PlayerProvider>
    <AccountsShell
      legacyTools={
        <Suspense fallback={<p role="status">Loading system tools…</p>}>
          <LegacyTools />
        </Suspense>
      }
    />
  </PlayerProvider>,
);

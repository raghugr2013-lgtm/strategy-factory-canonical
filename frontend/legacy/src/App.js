/**
 * App.js — Phase U-1 (C-01: wire root to CommandShell)
 * ----------------------------------------------------------------------------
 * The operator's default landing is the command shell (CommandModuleApp).
 * The placeholder Home is preserved at /legacy for parity testing during
 * the U-1 → U-6 migration.
 *
 * Scope:
 *   • Frontend routing only. No backend API additions.
 *   • CommandModuleApp already exists (Phase U.2 infra); U-1 simply makes
 *     it the default landing.
 *   • AuthGate is NOT wired in U-1 (the consolidated review explicitly
 *     keeps U-1 free of auth changes). AuthGate is reachable via legacy
 *     surfaces; integrating it into the command-shell mount lands later.
 */
import { useEffect, useState } from "react";
import "@/App.css";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import axios from "axios";
import { HOME } from "@/constants/testIds";
import CommandModuleApp from "@/command/shell/CommandModuleApp";
import AuthGate, { getStoredUser } from "@/components/AuthGate";
import { bootstrapThemeStore } from "@/stores/themeStore";
import { bootstrapLocaleStore } from "@/stores/localeStore";
import IntlProvider from "@/i18n/providers/IntlProvider";

// Bootstrap the theme SSOT exactly once, before React mounts. Writes
// `<html data-theme="dark" class="dark">` deterministically. U-4.3 — light
// theme is now selectable via Command Palette; dark remains the default.
bootstrapThemeStore();
// U-4.4 — bootstrap the locale SSOT. Writes `<html lang="en">` deterministically.
bootstrapLocaleStore();

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

// Legacy placeholder Home — preserved at /legacy for parity testing during
// the U-1 rollout. Will be removed once operator has signed off on U-1.
const LegacyHome = () => {
  const helloWorldApi = async () => {
    try {
      const response = await axios.get(`${API}/`);
      // eslint-disable-next-line no-console
      console.log(response.data.message);
    } catch (e) {
      // eslint-disable-next-line no-console
      console.error(e, `errored out requesting / api`);
    }
  };

  useEffect(() => {
    helloWorldApi();
  }, []);

  return (
    <div>
      <header className="App-header">
        <a
          data-testid={HOME.emergentLink}
          className="App-link"
          href="https://emergent.sh"
          target="_blank"
          rel="noopener noreferrer"
        >
          <img
            alt="Emergent"
            src="https://avatars.githubusercontent.com/in/1201222?s=120&u=2686cf91179bbafbc7a71bfbc43004cf9ae1acea&v=4"
          />
        </a>
        <p className="mt-5">Legacy placeholder — preserved for U-1 parity testing.</p>
      </header>
    </div>
  );
};

function GatedCommandModuleApp() {
  // RC1 · AUTH-FIX — wrap CommandModuleApp with AuthGate so the operator
  // is required to authenticate before any /c/* module renders. Without
  // this gate, components fired API calls with no JWT and surfaced HTTP
  // 401 chips across the entire dashboard. See AUTH_FIX_VERIFICATION.md.
  const [user, setUser] = useState(() => getStoredUser());
  if (!user) {
    return <AuthGate onAuthed={(u) => setUser(u)} />;
  }
  return <CommandModuleApp user={user} />;
}

function App() {
  return (
    <div className="App" data-testid="asf-app-root">
      <IntlProvider>
        <BrowserRouter>
          <Routes>
            {/* Operator default landing — CommandShell at root. */}
            <Route path="/" element={<GatedCommandModuleApp />} />
            {/* /c/* paths handled by the same shell (router.js parses
                pathname on its own and routes to the correct module). */}
            <Route path="/c/*" element={<GatedCommandModuleApp />} />
            {/* Legacy parity — placeholder Home reachable for U-1 sign-off. */}
            <Route path="/legacy" element={<LegacyHome />} />
          </Routes>
        </BrowserRouter>
      </IntlProvider>
    </div>
  );
}

export default App;

/**
 * Phase U-4.4 · IntlProvider
 * ----------------------------------------------------------------------------
 * Bootstraps the locale store, lazy-loads the active locale's dictionary,
 * and re-registers it on every locale change. Keeps the store agnostic of
 * `react-intl` — `t(key, fallback)` from `localeStore` is the call-site API.
 *
 * Mount once near the app root:
 *
 *   <IntlProvider>
 *     <App />
 *   </IntlProvider>
 */
import React, { useEffect } from 'react';
import {
  SUPPORTED_LOCALES,
  bootstrapLocaleStore,
  registerLocaleDict,
  useLocaleStore,
} from '../../stores/localeStore';

import enUS from '../locales/en-US.json';
import deDE from '../locales/de-DE.json';

const STATIC_DICTS = {
  'en-US': enUS,
  'de-DE': deDE,
};

export default function IntlProvider({ children }) {
  // Register the en-US dictionary once on first mount so `t()` has a
  // baseline to fall back to regardless of which locale is active.
  useEffect(() => {
    bootstrapLocaleStore();
    SUPPORTED_LOCALES.forEach((code) => {
      if (STATIC_DICTS[code]) registerLocaleDict(code, STATIC_DICTS[code]);
    });
  }, []);

  // Subscribe to the active locale so the provider re-renders when the
  // operator cycles the language. The render output doesn't depend on the
  // locale directly — children consume it via `useLocaleStore()` / `t()`.
  useLocaleStore();

  return <>{children}</>;
}

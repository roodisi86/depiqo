/** Whether Manrope is loaded. Until then (or if loading fails) text uses the system font. */
import React, { createContext, useContext } from 'react';

const FontsContext = createContext(false);

export function FontsProvider({ loaded, children }: { loaded: boolean; children: React.ReactNode }) {
  return <FontsContext.Provider value={loaded}>{children}</FontsContext.Provider>;
}

export function useFontsLoaded(): boolean {
  return useContext(FontsContext);
}

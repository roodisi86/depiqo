/**
 * Tokens live only in expo-secure-store (iOS Keychain, Android Keystore-backed storage), readable only
 * while the device is unlocked and never migrated to another device or backup.
 *
 * iOS keeps Keychain items after the app is deleted. A marker file in the app's documents folder (which
 * IS deleted with the app) tells a fresh install apart, so a reinstalled app starts signed out.
 */
import * as FileSystem from 'expo-file-system';
import * as SecureStore from 'expo-secure-store';

import type { TokenSet, TokenStore } from '../api/client';

const SESSION_KEY = 'depiqo.session.v1';
const PREF_PREFIX = 'depiqo.pref.';
const MARKER = `${FileSystem.documentDirectory ?? ''}depiqo-install-marker`;

export const SECURE_OPTIONS: SecureStore.SecureStoreOptions = {
  keychainAccessible: SecureStore.WHEN_UNLOCKED_THIS_DEVICE_ONLY,
};

let freshInstallCheck: Promise<void> | null = null;

/** Clears leftovers from an earlier install (iOS Keychain survives uninstall). Runs once per launch. */
export function ensureFreshInstallCleared(): Promise<void> {
  if (!freshInstallCheck) {
    freshInstallCheck = (async () => {
      try {
        if (!FileSystem.documentDirectory) return;
        const info = await FileSystem.getInfoAsync(MARKER);
        if (info.exists) return;
        await SecureStore.deleteItemAsync(SESSION_KEY, SECURE_OPTIONS);
        for (const k of ['biometric', 'lang']) await SecureStore.deleteItemAsync(PREF_PREFIX + k, SECURE_OPTIONS);
        await FileSystem.writeAsStringAsync(MARKER, '1');
      } catch {
        // Never block the app on this; worst case an old session is offered for biometric unlock.
      }
    })();
  }
  return freshInstallCheck;
}

function isTokenSet(v: unknown): v is TokenSet {
  if (!v || typeof v !== 'object') return false;
  const t = v as Record<string, unknown>;
  return typeof t.accessToken === 'string' && t.accessToken.length > 0 && typeof t.refreshToken === 'string' && t.refreshToken.length > 0;
}

export const secureTokenStore: TokenStore = {
  async load() {
    await ensureFreshInstallCleared();
    try {
      const raw = await SecureStore.getItemAsync(SESSION_KEY, SECURE_OPTIONS);
      if (!raw) return null;
      const parsed: unknown = JSON.parse(raw);
      return isTokenSet(parsed) ? parsed : null;
    } catch {
      return null;
    }
  },
  async save(tokens) {
    await SecureStore.setItemAsync(SESSION_KEY, JSON.stringify(tokens), SECURE_OPTIONS);
  },
  async clear() {
    await SecureStore.deleteItemAsync(SESSION_KEY, SECURE_OPTIONS);
  },
};

/** Small, non-secret preferences (biometric opt-in, language). Kept next to the session on purpose. */
export const prefs = {
  async get(name: 'biometric' | 'lang'): Promise<string | null> {
    await ensureFreshInstallCleared();
    try {
      return await SecureStore.getItemAsync(PREF_PREFIX + name, SECURE_OPTIONS);
    } catch {
      return null;
    }
  },
  async set(name: 'biometric' | 'lang', value: string | null): Promise<void> {
    try {
      if (value === null) await SecureStore.deleteItemAsync(PREF_PREFIX + name, SECURE_OPTIONS);
      else await SecureStore.setItemAsync(PREF_PREFIX + name, value, SECURE_OPTIONS);
    } catch {
      // ignore: a preference is not worth crashing for
    }
  },
};

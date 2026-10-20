/**
 * Session state for the whole app.
 *
 *   booting    reading the stored session from secure storage
 *   signedOut  no session (or it ended: logout, revoked device, reused refresh token)
 *   locked     a session exists but biometric unlock is on and the user has not unlocked yet
 *   signedIn   ready
 *
 * Biometric unlock is opt-in. It guards the stored session on launch and after the app was in the
 * background for LOCK_AFTER_MS. "Use password instead" ends the session and goes to the login screen.
 */
import { useQueryClient } from '@tanstack/react-query';
import * as LocalAuthentication from 'expo-local-authentication';
import React, { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react';
import { AppState, type AppStateStatus } from 'react-native';

import { clearDownloads } from '../api/download';
import { api, apiClient } from '../api/instance';
import type { Session } from '../api/schemas';
import { useI18n } from '../i18n/I18nProvider';
import { clearPendingRoute } from '../lib/pendingRoute';
import { prefs } from './secureTokenStore';

export type AuthStatus = 'booting' | 'signedOut' | 'locked' | 'signedIn';

export const LOCK_AFTER_MS = 60_000;

export interface BiometricSupport {
  available: boolean;
  kind: 'face' | 'fingerprint' | 'other' | null;
}

interface AuthValue {
  status: AuthStatus;
  /** Why the last session ended (an error code), shown once on the login screen. */
  endReason: string | null;
  clearEndReason(): void;
  /** Set on 426 or when /config's minimum version is above this app. */
  updateRequired: boolean;
  markUpdateRequired(): void;
  /** False until the user unlocked once in this launch (the app's screens stay unmounted before that). */
  unlockedOnce: boolean;
  /** True after the user logged out on purpose: the next login starts at home, not where they were. */
  signedOutByUser: boolean;
  biometricEnabled: boolean;
  completeLogin(session: Session): Promise<void>;
  signOut(opts?: { callServer?: boolean; reason?: string | null }): Promise<void>;
  unlock(): Promise<boolean>;
  switchToPassword(): Promise<void>;
  biometricSupport(): Promise<BiometricSupport>;
  setBiometricEnabled(on: boolean): Promise<boolean>;
  /** Run something that leaves the app briefly (camera, share sheet) without triggering the lock. */
  withLockSuspended<T>(fn: () => Promise<T>): Promise<T>;
}

const AuthContext = createContext<AuthValue | null>(null);

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const queryClient = useQueryClient();
  const { t } = useI18n();
  const [status, setStatus] = useState<AuthStatus>('booting');
  const [endReason, setEndReason] = useState<string | null>(null);
  const [updateRequired, setUpdateRequired] = useState(false);
  const [unlockedOnce, setUnlockedOnce] = useState(false);
  const [biometricEnabled, setBioState] = useState(false);
  const [signedOutByUser, setSignedOutByUser] = useState(false);
  const statusRef = useRef<AuthStatus>('booting');
  const bioRef = useRef(false);
  const backgroundAt = useRef<number | null>(null);
  const suspended = useRef(0);

  const go = useCallback((s: AuthStatus) => {
    statusRef.current = s;
    setStatus(s);
  }, []);

  // Boot: read the stored session and the biometric preference.
  useEffect(() => {
    let alive = true;
    void (async () => {
      await clearDownloads();
      const [hasSession, bio] = await Promise.all([apiClient.hasSession(), prefs.get('biometric')]);
      if (!alive) return;
      bioRef.current = bio === '1';
      setBioState(bio === '1');
      if (!hasSession) go('signedOut');
      else if (bio === '1') go('locked');
      else {
        setUnlockedOnce(true);
        go('signedIn');
      }
    })();
    return () => {
      alive = false;
    };
  }, [go]);

  // The API client tells us when the server ended the session or the app is too old.
  useEffect(() => {
    const offSession = apiClient.onSessionEnded((code) => {
      queryClient.clear();
      void clearDownloads();
      setEndReason(code);
      setSignedOutByUser(false);
      go('signedOut');
    });
    const offUpdate = apiClient.onUpdateRequired(() => setUpdateRequired(true));
    return () => {
      offSession();
      offUpdate();
    };
  }, [go, queryClient]);

  // Lock again after some time in the background.
  useEffect(() => {
    const sub = AppState.addEventListener('change', (next: AppStateStatus) => {
      if (next === 'background') {
        backgroundAt.current = Date.now();
        return;
      }
      if (next === 'active') {
        const since = backgroundAt.current;
        backgroundAt.current = null;
        if (since !== null && bioRef.current && suspended.current === 0 && statusRef.current === 'signedIn' && Date.now() - since >= LOCK_AFTER_MS) {
          go('locked');
        }
      }
    });
    return () => sub.remove();
  }, [go]);

  const completeLogin = useCallback(
    async (session: Session) => {
      await apiClient.setSession({
        accessToken: session.access_token,
        accessExpiresAt: session.access_expires_at,
        refreshToken: session.refresh_token,
        refreshExpiresAt: session.refresh_expires_at,
        deviceId: session.device_id,
      });
      queryClient.clear();
      setEndReason(null);
      setSignedOutByUser(false);
      setUnlockedOnce(true);
      go('signedIn');
    },
    [go, queryClient],
  );

  const signOut = useCallback(
    async (opts?: { callServer?: boolean; reason?: string | null }) => {
      if (opts?.callServer !== false && (await apiClient.hasSession())) {
        // Ends the device session on the server (and its push token). Never block sign-out on the network.
        await Promise.race([api.logout().catch(() => undefined), delay(4000)]);
      }
      await apiClient.clearSession();
      queryClient.clear();
      await clearDownloads();
      clearPendingRoute();
      setEndReason(opts?.reason ?? null);
      setSignedOutByUser(true);
      go('signedOut');
    },
    [go, queryClient],
  );

  const unlock = useCallback(async () => {
    try {
      const r = await LocalAuthentication.authenticateAsync({
        promptMessage: t('lock.prompt'),
        cancelLabel: t('common.cancel'),
        fallbackLabel: t('lock.devicePasscode'),
        disableDeviceFallback: false,
      });
      if (r.success) {
        setUnlockedOnce(true);
        go('signedIn');
        return true;
      }
    } catch {
      // fall through: stay locked
    }
    return false;
  }, [go, t]);

  const switchToPassword = useCallback(async () => {
    await signOut({ callServer: true, reason: null });
  }, [signOut]);

  const biometricSupport = useCallback(async (): Promise<BiometricSupport> => {
    try {
      const [hw, enrolled, types] = await Promise.all([
        LocalAuthentication.hasHardwareAsync(),
        LocalAuthentication.isEnrolledAsync(),
        LocalAuthentication.supportedAuthenticationTypesAsync(),
      ]);
      const kind = types.includes(LocalAuthentication.AuthenticationType.FACIAL_RECOGNITION)
        ? 'face'
        : types.includes(LocalAuthentication.AuthenticationType.FINGERPRINT)
          ? 'fingerprint'
          : types.length > 0
            ? 'other'
            : null;
      return { available: hw && enrolled, kind };
    } catch {
      return { available: false, kind: null };
    }
  }, []);

  const setBiometricEnabled = useCallback(
    async (on: boolean) => {
      if (on) {
        const support = await biometricSupport();
        if (!support.available) return false;
        const r = await LocalAuthentication.authenticateAsync({ promptMessage: t('lock.enablePrompt'), cancelLabel: t('common.cancel') });
        if (!r.success) return false;
      }
      await prefs.set('biometric', on ? '1' : null);
      bioRef.current = on;
      setBioState(on);
      return true;
    },
    [biometricSupport, t],
  );

  const withLockSuspended = useCallback(async <T,>(fn: () => Promise<T>): Promise<T> => {
    suspended.current += 1;
    try {
      return await fn();
    } finally {
      suspended.current -= 1;
      backgroundAt.current = null;
    }
  }, []);

  const value = useMemo<AuthValue>(
    () => ({
      status,
      endReason,
      clearEndReason: () => setEndReason(null),
      updateRequired,
      markUpdateRequired: () => setUpdateRequired(true),
      unlockedOnce,
      signedOutByUser,
      biometricEnabled,
      completeLogin,
      signOut,
      unlock,
      switchToPassword,
      biometricSupport,
      setBiometricEnabled,
      withLockSuspended,
    }),
    [status, endReason, updateRequired, unlockedOnce, signedOutByUser, biometricEnabled, completeLogin, signOut, unlock, switchToPassword, biometricSupport, setBiometricEnabled, withLockSuspended],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthValue {
  const v = useContext(AuthContext);
  if (!v) throw new Error('useAuth outside AuthProvider');
  return v;
}

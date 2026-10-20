/**
 * Root: fonts, server state, language, session, environment banner, lock and privacy overlays,
 * notification taps and push registration.
 */
import {
  Manrope_400Regular,
  Manrope_600SemiBold,
  Manrope_700Bold,
  Manrope_800ExtraBold,
  useFonts,
} from '@expo-google-fonts/manrope';
import { focusManager, QueryClient, QueryClientProvider } from '@tanstack/react-query';
import * as Notifications from 'expo-notifications';
import { router, Stack, type Href } from 'expo-router';
import * as SplashScreen from 'expo-splash-screen';
import { StatusBar } from 'expo-status-bar';
import React, { useEffect, useRef, useState } from 'react';
import { AppState, StyleSheet, View } from 'react-native';
import { SafeAreaInsetsContext, SafeAreaProvider, useSafeAreaInsets } from 'react-native-safe-area-context';

import { isApiError } from '../src/api/errors';
import { api } from '../src/api/instance';
import { AuthProvider, useAuth } from '../src/auth/AuthProvider';
import { LockScreen } from '../src/auth/LockScreen';
import { APP_VERSION, PLATFORM } from '../src/config/env';
import { useConfig } from '../src/hooks/useConfig';
import { useMe } from '../src/hooks/useMe';
import { I18nProvider, useI18n } from '../src/i18n/I18nProvider';
import { parseDeepLink, requiresAuth, routeFor } from '../src/lib/deeplink';
import { setPendingRoute } from '../src/lib/pendingRoute';
import { isBelowMinimum } from '../src/lib/version';
import { readNotificationData, registerPushToken } from '../src/notifications/push';
import { EnvBanner, useEnvBannerText } from '../src/ui/EnvBanner';
import { FontsProvider } from '../src/ui/fonts';
import { PrivacyShield } from '../src/ui/PrivacyShield';
import { useTheme } from '../src/ui/theme';
import { UpdateRequired } from '../src/ui/UpdateRequired';

void SplashScreen.preventAutoHideAsync().catch(() => undefined);

function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 30_000,
        gcTime: 5 * 60_000,
        // Retry network trouble once; never retry an answer the server gave on purpose (4xx).
        retry: (count, err) => !(isApiError(err) && err.status >= 400 && err.status < 500) && count < 1,
      },
      mutations: { retry: false },
    },
  });
}

export default function RootLayout() {
  const [fontsLoaded, fontError] = useFonts({ Manrope_400Regular, Manrope_600SemiBold, Manrope_700Bold, Manrope_800ExtraBold });
  const [queryClient] = useState(createQueryClient);
  return (
    <SafeAreaProvider>
      <QueryClientProvider client={queryClient}>
        <I18nProvider onLanguageChanged={() => void queryClient.invalidateQueries()}>
          <FontsProvider loaded={fontsLoaded}>
            <AuthProvider>
              <AppShell fontsReady={fontsLoaded || !!fontError} />
            </AuthProvider>
          </FontsProvider>
        </I18nProvider>
      </QueryClientProvider>
    </SafeAreaProvider>
  );
}

function AppShell({ fontsReady }: { fontsReady: boolean }) {
  const auth = useAuth();
  const { colors, dark } = useTheme();
  const bannerText = useEnvBannerText();
  const insets = useSafeAreaInsets();
  const config = useConfig();

  // Splash stays until fonts and the stored session are read (at most 4 seconds).
  useEffect(() => {
    if (fontsReady && auth.status !== 'booting') void SplashScreen.hideAsync().catch(() => undefined);
  }, [fontsReady, auth.status]);
  useEffect(() => {
    const timer = setTimeout(() => void SplashScreen.hideAsync().catch(() => undefined), 4000);
    return () => clearTimeout(timer);
  }, []);

  // React Query refetches when the app comes back to the foreground.
  useEffect(() => {
    const sub = AppState.addEventListener('change', (s) => focusManager.setFocused(s === 'active'));
    return () => sub.remove();
  }, []);

  // Too old for the server?
  const minimum = config.data?.minimum_app_version[PLATFORM];
  const tooOld = auth.updateRequired || isBelowMinimum(APP_VERSION, minimum);

  useServerLanguage();
  useNotificationTaps();
  usePushRegistration();

  const locked = auth.status === 'locked';
  return (
    <View style={[styles.flex, { backgroundColor: colors.bg }]}>
      <StatusBar style={bannerText ? (dark ? 'dark' : 'light') : 'auto'} />
      {bannerText ? <EnvBanner text={bannerText} /> : null}
      <SafeAreaInsetsContext.Provider value={bannerText ? { ...insets, top: 0 } : insets}>
        <View style={styles.flex} importantForAccessibility={locked ? 'no-hide-descendants' : 'auto'} accessibilityElementsHidden={locked}>
          <Stack screenOptions={{ headerShown: false, contentStyle: { backgroundColor: colors.bg } }} />
        </View>
      </SafeAreaInsetsContext.Provider>
      {locked ? <LockScreen /> : null}
      {tooOld ? <UpdateRequired /> : null}
      <PrivacyShield />
    </View>
  );
}

/** Adopt the language stored on the server, unless the user picked one in this app. */
function useServerLanguage() {
  const me = useMe();
  const { lang, chosenByUser, setLang } = useI18n();
  const serverLang = me.data?.language;
  useEffect(() => {
    if (serverLang && !chosenByUser && serverLang !== lang) setLang(serverLang);
  }, [serverLang, chosenByUser, lang, setLang]);
}

/** A tapped notification opens its deep link, after login or unlock when needed, and is marked read. */
function useNotificationTaps() {
  const { status } = useAuth();
  const response = Notifications.useLastNotificationResponse();
  const handled = useRef<string | null>(null);
  const waiting = useRef<{ route: string; id: number | null; navigate: boolean } | null>(null);

  useEffect(() => {
    if (!response || response.actionIdentifier !== Notifications.DEFAULT_ACTION_IDENTIFIER) return;
    const ident = response.notification.request.identifier;
    if (handled.current === ident) return;
    handled.current = ident;
    const { path, notificationId } = readNotificationData(response);
    const link = parseDeepLink(path);
    const route = link ? routeFor(link) : '/notifications';
    if (link && !requiresAuth(link)) {
      router.push(route as Href);
      return;
    }
    waiting.current = { route, id: notificationId, navigate: true };
  }, [response]);

  useEffect(() => {
    const w = waiting.current;
    if (!w) return;
    if (status === 'signedIn') {
      waiting.current = null;
      if (w.id !== null) void api.markNotificationRead(w.id).catch(() => undefined);
      if (w.navigate) router.push(w.route as Href);
    } else if (status === 'signedOut' && w.navigate) {
      // The login screen takes the user there afterwards; only the "read" mark still waits.
      setPendingRoute(w.route);
      waiting.current = { ...w, navigate: false };
    }
  }, [status, response]);
}

/** Registers the push token once per session when permission was already given. Never asks by itself. */
function usePushRegistration() {
  const { status } = useAuth();
  const done = useRef(false);
  useEffect(() => {
    if (status === 'signedOut') done.current = false;
    if (status !== 'signedIn' || done.current) return;
    done.current = true;
    void registerPushToken();
  }, [status]);
}

const styles = StyleSheet.create({
  flex: { flex: 1 },
});

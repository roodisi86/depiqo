/**
 * Everything behind the login. Signed out: remember where the user was heading and go to /login.
 * Locked on launch: render nothing until the biometric unlock (the lock screen sits on top).
 */
import { Redirect, Stack, usePathname } from 'expo-router';
import React, { useEffect } from 'react';
import { View } from 'react-native';

import { useAuth } from '../../src/auth/AuthProvider';
import { clearPendingRoute, peekPendingRoute, setPendingRoute } from '../../src/lib/pendingRoute';
import { Loading } from '../../src/ui/feedback';
import { useHeaderOptions } from '../../src/ui/header';
import { useTheme } from '../../src/ui/theme';

export default function AppLayout() {
  const { status, unlockedOnce, signedOutByUser } = useAuth();
  const pathname = usePathname();
  const { colors } = useTheme();
  const headerOptions = useHeaderOptions();

  useEffect(() => {
    // Arrived where the deep link pointed (or anywhere after login): the pending route is used up.
    if (status === 'signedIn' && peekPendingRoute() === pathname) clearPendingRoute();
  }, [status, pathname]);

  if (status === 'booting') return <Loading />;
  if (status === 'signedOut') {
    // A deep link (or an ended session) brought the user here: come back after login.
    if (!signedOutByUser) setPendingRoute(pathname);
    return <Redirect href="/login" />;
  }
  if (status === 'locked' && !unlockedOnce) return <View style={{ flex: 1, backgroundColor: colors.bg }} />;

  return (
    <Stack screenOptions={headerOptions}>
      <Stack.Screen name="(tabs)" options={{ headerShown: false }} />
    </Stack>
  );
}

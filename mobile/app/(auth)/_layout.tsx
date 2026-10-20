/** Login and second step. Once signed in, go to where the user was heading (a deep link) or home. */
import { Redirect, Stack, type Href } from 'expo-router';
import React from 'react';

import { useAuth } from '../../src/auth/AuthProvider';
import { peekPendingRoute } from '../../src/lib/pendingRoute';
import { useTheme } from '../../src/ui/theme';

export default function AuthLayout() {
  const { status } = useAuth();
  const { colors } = useTheme();
  if (status === 'signedIn') return <Redirect href={(peekPendingRoute() ?? '/') as Href} />;
  return <Stack screenOptions={{ headerShown: false, contentStyle: { backgroundColor: colors.bg } }} />;
}

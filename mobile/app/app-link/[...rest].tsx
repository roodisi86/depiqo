/** Fallback for /app-link/* when the native intent rewrite did not run: same strict parser. */
import { Redirect, useLocalSearchParams, type Href } from 'expo-router';
import React from 'react';

import { parseDeepLink, routeFor } from '../../src/lib/deeplink';

export default function AppLinkRedirect() {
  const { rest } = useLocalSearchParams<{ rest: string[] }>();
  const parts = Array.isArray(rest) ? rest : rest ? [rest] : [];
  const link = parseDeepLink(`/app-link/${parts.join('/')}`);
  return <Redirect href={(link ? routeFor(link) : '/') as Href} />;
}

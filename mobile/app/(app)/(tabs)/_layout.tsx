/** Bottom tabs: deposits, history, Invest (only when offered and eligible), notifications, profile. */
import { Ionicons } from '@expo/vector-icons';
import { useQuery } from '@tanstack/react-query';
import { Tabs } from 'expo-router';
import React from 'react';

import { api } from '../../../src/api/instance';
import { useInvestGate } from '../../../src/hooks/useMe';
import { useI18n } from '../../../src/i18n/I18nProvider';
import { useFontsLoaded } from '../../../src/ui/fonts';
import { fonts, useTheme } from '../../../src/ui/theme';

type IconName = React.ComponentProps<typeof Ionicons>['name'];

function icon(name: IconName) {
  const TabIcon = ({ color, size }: { color: string; size: number }) => <Ionicons name={name} color={color} size={size} />;
  TabIcon.displayName = `TabIcon(${name})`;
  return TabIcon;
}

export default function TabsLayout() {
  const { t } = useI18n();
  const { colors } = useTheme();
  const loaded = useFontsLoaded();
  const gate = useInvestGate();
  const unread = useQuery({ queryKey: ['notifications', 'unread'], queryFn: () => api.notifications(null, 1), staleTime: 60_000 });
  const count = unread.data?.unread_count ?? 0;

  return (
    <Tabs
      screenOptions={{
        headerStyle: { backgroundColor: colors.bg },
        headerTitleStyle: { color: colors.text, fontFamily: loaded ? fonts.bold : undefined },
        headerShadowVisible: false,
        tabBarActiveTintColor: colors.accentText,
        tabBarInactiveTintColor: colors.textMuted,
        tabBarStyle: { backgroundColor: colors.surface, borderTopColor: colors.line },
        tabBarLabelStyle: { fontFamily: loaded ? fonts.semibold : undefined, fontSize: 12 },
        // Tab labels keep their size with large system text, like the native iOS and Android tab bars; at 1.3x they
        // were cut off ("Geschie…"). Screen content still scales, and each tab keeps its accessibility label.
        tabBarAllowFontScaling: false,
        sceneStyle: { backgroundColor: colors.bg },
      }}
    >
      <Tabs.Screen name="index" options={{ title: t('tabs.deposits'), tabBarIcon: icon('home-outline'), tabBarAccessibilityLabel: t('tabs.deposits'), tabBarButtonTestID: 'tab-deposits' }} />
      <Tabs.Screen name="activity" options={{ title: t('tabs.activity'), tabBarIcon: icon('time-outline'), tabBarAccessibilityLabel: t('tabs.activity'), tabBarButtonTestID: 'tab-activity' }} />
      <Tabs.Screen
        name="invest"
        options={{
          title: t('tabs.invest'),
          tabBarIcon: icon('trending-up-outline'),
          tabBarAccessibilityLabel: t('tabs.invest'),
          tabBarButtonTestID: 'tab-invest',
          href: gate === 'available' ? undefined : null,
        }}
      />
      <Tabs.Screen
        name="notifications"
        options={{
          title: t('tabs.notifications'),
          tabBarIcon: icon('notifications-outline'),
          tabBarBadge: count > 0 ? (count > 99 ? '99+' : count) : undefined,
          tabBarAccessibilityLabel: count > 0 ? t('tabs.notificationsUnread', { count }) : t('tabs.notifications'),
          tabBarButtonTestID: 'tab-notifications',
        }}
      />
      <Tabs.Screen name="profile" options={{ title: t('tabs.profile'), tabBarIcon: icon('person-circle-outline'), tabBarAccessibilityLabel: t('tabs.profile'), tabBarButtonTestID: 'tab-profile' }} />
    </Tabs>
  );
}

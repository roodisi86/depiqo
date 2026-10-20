/** Devices signed in to this account (also on the website under Security). Sign out any of them. */
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Stack } from 'expo-router';
import React from 'react';
import { Alert, View } from 'react-native';

import { api } from '../../../src/api/instance';
import type { Device } from '../../../src/api/schemas';
import { useAuth } from '../../../src/auth/AuthProvider';
import { useSafeMutation } from '../../../src/hooks/mutations';
import { useI18n } from '../../../src/i18n/I18nProvider';
import { formatDateTime } from '../../../src/lib/format';
import { Button } from '../../../src/ui/Button';
import { ErrorState, FormError, Loading } from '../../../src/ui/feedback';
import { Card, Row, Screen } from '../../../src/ui/layout';
import { StatusPill } from '../../../src/ui/StatusPill';
import { AppText } from '../../../src/ui/Text';

export default function Devices() {
  const { t, tk, lang } = useI18n();
  const auth = useAuth();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ['devices'], queryFn: api.devices });
  const revoke = useSafeMutation((d: Device) => api.revokeDevice(d.id), {
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: ['devices'] });
    },
  });

  const confirm = (d: Device) => {
    if (d.current) {
      Alert.alert(t('devices.thisDeviceTitle'), t('devices.thisDeviceBody'), [
        { text: t('common.cancel'), style: 'cancel' },
        { text: t('profile.logout'), style: 'destructive', onPress: () => void auth.signOut() },
      ]);
      return;
    }
    Alert.alert(t('devices.signOutTitle'), t('devices.signOutBody', { name: d.name }), [
      { text: t('common.cancel'), style: 'cancel' },
      { text: t('devices.signOut'), style: 'destructive', onPress: () => revoke.submit(d) },
    ]);
  };

  return (
    <Screen refreshing={q.isRefetching} onRefresh={() => void q.refetch()}>
      <Stack.Screen options={{ title: t('devices.title') }} />
      <AppText muted>{t('devices.intro')}</AppText>
      {q.isLoading ? <Loading /> : null}
      {q.error ? <ErrorState error={q.error} onRetry={() => void q.refetch()} /> : null}
      <FormError error={revoke.error} />
      {(q.data?.items ?? []).map((d) => (
        <Card key={d.id}>
          <View style={{ gap: 4 }}>
            <AppText variant="heading">{d.name}</AppText>
            {d.current ? <StatusPill label={t('devices.current')} tone="ok" /> : null}
          </View>
          <Row label={t('devices.platform')} value={tk('platform', d.platform, d.platform)} />
          <Row label={t('devices.lastSeen')} value={formatDateTime(d.last_seen_at, lang)} />
          <Row label={t('devices.created')} value={formatDateTime(d.created_at, lang)} />
          <Row label={t('devices.secondFactor')} value={d.second_factor ? t('common.yes') : t('common.no')} />
          {d.app_version ? <Row label={t('devices.appVersion')} value={d.app_version} /> : null}
          <Button label={d.current ? t('profile.logout') : t('devices.signOut')} variant="danger" busy={revoke.busy && revoke.variables?.id === d.id} onPress={() => confirm(d)} />
        </Card>
      ))}
    </Screen>
  );
}

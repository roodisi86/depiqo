/**
 * Privacy and data: push preferences per category, download all own data (JSON), the privacy statement
 * and terms (links from /config), and the account deletion request.
 */
import { useQueryClient } from '@tanstack/react-query';
import { router, Stack } from 'expo-router';
import React from 'react';
import { Linking } from 'react-native';

import { shareTextFile } from '../../../src/api/download';
import { clientError } from '../../../src/api/errors';
import { api } from '../../../src/api/instance';
import { DataExportSchema, type NotificationPreferences } from '../../../src/api/schemas';
import { useAuth } from '../../../src/auth/AuthProvider';
import { useSafeMutation } from '../../../src/hooks/mutations';
import { useConfig } from '../../../src/hooks/useConfig';
import { meKey, useMe } from '../../../src/hooks/useMe';
import { useI18n } from '../../../src/i18n/I18nProvider';
import { Button } from '../../../src/ui/Button';
import { ErrorState, FormError, Loading, Notice } from '../../../src/ui/feedback';
import { Checkbox } from '../../../src/ui/form';
import { Card, Screen, SectionTitle } from '../../../src/ui/layout';
import { ListItem } from '../../../src/ui/ListItem';
import { AppText } from '../../../src/ui/Text';

type Category = keyof NotificationPreferences['push'];
const CATEGORIES: Category[] = ['deposit', 'invest', 'security', 'support'];

function prefPatch(c: Category, v: boolean): Partial<NotificationPreferences['push']> {
  const patch: Partial<NotificationPreferences['push']> = {};
  patch[c] = v;
  return patch;
}

export default function Privacy() {
  const { t } = useI18n();
  const auth = useAuth();
  const me = useMe();
  const config = useConfig();
  const qc = useQueryClient();

  const savePrefs = useSafeMutation((push: Partial<NotificationPreferences['push']>) => api.updateMe({ notification_preferences: { push } }), {
    onSuccess: (data) => {
      qc.setQueryData(meKey, data);
    },
  });

  const exportData = useSafeMutation(async () => {
    const text = await api.exportData();
    let parsed: unknown;
    try {
      parsed = JSON.parse(text);
    } catch {
      throw clientError('invalid_response');
    }
    if (!DataExportSchema.safeParse(parsed).success) throw clientError('invalid_response');
    const day = new Date().toISOString().slice(0, 10);
    await auth.withLockSuspended(() => shareTextFile(`depiqo-export-${day}.json`, text, 'application/json', t('privacy.exportTitle')));
  });

  if (me.isLoading) return <Loading />;
  if (me.error || !me.data) {
    return (
      <Screen>
        <ErrorState error={me.error} onRetry={() => void me.refetch()} />
      </Screen>
    );
  }
  const prefs = me.data.notification_preferences.push;
  const links = config.data?.links;

  return (
    <Screen>
      <Stack.Screen options={{ title: t('privacy.title') }} />
      <Card>
        <SectionTitle>{t('privacy.pushTitle')}</SectionTitle>
        <AppText muted>{t('privacy.pushIntro')}</AppText>
        {CATEGORIES.map((c) => (
          <Checkbox key={c} checked={prefs[c]} disabled={savePrefs.busy} label={t(`privacy.pref.${c}`)} onChange={(v) => savePrefs.submit(prefPatch(c, v))} />
        ))}
        <FormError error={savePrefs.error} />
      </Card>

      <Card>
        <SectionTitle>{t('privacy.exportTitle')}</SectionTitle>
        <AppText>{t('privacy.exportBody')}</AppText>
        <Notice tone="wait">{t('privacy.exportWarning')}</Notice>
        <FormError error={exportData.error} />
        <Button label={t('privacy.exportButton')} variant="secondary" busy={exportData.busy} onPress={() => exportData.submit(undefined)} />
      </Card>

      <Card>
        <SectionTitle>{t('privacy.documents')}</SectionTitle>
        {links?.privacy ? <ListItem icon="document-lock-outline" title={t('privacy.statement')} onPress={() => void Linking.openURL(links.privacy as string)} /> : null}
        {links?.terms ? <ListItem icon="reader-outline" title={t('privacy.terms')} onPress={() => void Linking.openURL(links.terms as string)} /> : null}
        {config.data?.support_email ? (
          <ListItem icon="mail-outline" title={t('privacy.contact')} subtitle={config.data.support_email} onPress={() => void Linking.openURL(`mailto:${config.data?.support_email ?? ''}`)} />
        ) : null}
      </Card>

      <Card>
        <SectionTitle>{t('privacy.deleteTitle')}</SectionTitle>
        <AppText>{t('privacy.deleteIntro')}</AppText>
        <ListItem icon="trash-outline" title={t('privacy.deleteLink')} danger onPress={() => router.push('/settings/delete-account')} />
      </Card>
    </Screen>
  );
}

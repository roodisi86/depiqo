/**
 * Profile: name, e-mail, language, two-step verification status (set up on the website), biometric
 * unlock, and links to devices, privacy, help and logout.
 */
import { useQueryClient } from '@tanstack/react-query';
import { router } from 'expo-router';
import React, { useEffect, useState } from 'react';
import { Alert, Linking } from 'react-native';

import { api } from '../../../src/api/instance';
import { useAuth, type BiometricSupport } from '../../../src/auth/AuthProvider';
import { APP_ENV, APP_VERSION } from '../../../src/config/env';
import { useSafeMutation } from '../../../src/hooks/mutations';
import { useConfig } from '../../../src/hooks/useConfig';
import { meKey, useMe } from '../../../src/hooks/useMe';
import { useSensitiveScreen } from '../../../src/hooks/useSensitiveScreen';
import { useI18n, type Lang } from '../../../src/i18n/I18nProvider';
import { Button } from '../../../src/ui/Button';
import { ErrorState, FormError, Loading, Notice } from '../../../src/ui/feedback';
import { Checkbox, Segmented, TextField } from '../../../src/ui/form';
import { Card, Row, Screen, SectionTitle } from '../../../src/ui/layout';
import { ListItem } from '../../../src/ui/ListItem';
import { AppText } from '../../../src/ui/Text';

export default function Profile() {
  useSensitiveScreen();
  const tr = useI18n();
  const { t, lang, setLang } = tr;
  const auth = useAuth();
  const me = useMe();
  const config = useConfig();
  const qc = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState('');
  const [bio, setBio] = useState<BiometricSupport | null>(null);
  const [bioMessage, setBioMessage] = useState<string | null>(null);

  useEffect(() => {
    void auth.biometricSupport().then(setBio);
  }, [auth]);

  const save = useSafeMutation((patch: { name?: string; language?: Lang }) => api.updateMe(patch), {
    onSuccess: (data) => {
      qc.setQueryData(meKey, data);
      setEditing(false);
    },
  });

  const changeLanguage = (next: Lang) => {
    setLang(next, { persist: true });
    save.submit({ language: next });
  };

  if (me.isLoading) return <Loading />;
  if (me.error || !me.data) {
    return (
      <Screen edges={[]}>
        <ErrorState error={me.error} onRetry={() => void me.refetch()} />
        <Button label={t('profile.logout')} variant="secondary" onPress={() => void auth.signOut()} />
      </Screen>
    );
  }
  const m = me.data;
  const securityUrl = config.data?.links.security;
  const bioName = bio?.kind === 'face' ? t('profile.faceId') : bio?.kind === 'fingerprint' ? t('profile.fingerprint') : t('profile.biometrics');

  return (
    <Screen edges={[]} keyboard testID="profile-screen">
      <Card>
        <SectionTitle>{t('profile.account')}</SectionTitle>
        {editing ? (
          <>
            <TextField label={t('profile.name')} value={name} onChangeText={setName} autoComplete="name" maxLength={120} />
            <FormError error={save.error} />
            <Button label={t('common.save')} busy={save.busy} disabled={!name.trim()} onPress={() => save.submit({ name: name.trim() })} />
            <Button label={t('common.cancel')} variant="ghost" onPress={() => setEditing(false)} />
          </>
        ) : (
          <>
            <Row label={t('profile.name')} value={m.name} />
            <Button
              label={t('profile.editName')}
              variant="ghost"
              compact
              onPress={() => {
                setName(m.name);
                setEditing(true);
              }}
            />
          </>
        )}
        <Row label={t('profile.email')} value={m.email} hint={t('profile.emailHint')} />
      </Card>

      <Card>
        <SectionTitle>{t('profile.language')}</SectionTitle>
        <Segmented<Lang>
          label={t('profile.language')}
          testID="language"
          value={lang}
          onChange={changeLanguage}
          options={[
            { value: 'nl', label: 'Nederlands' },
            { value: 'fr', label: 'Français' },
            { value: 'en', label: 'English' },
          ]}
        />
      </Card>

      <Card>
        <SectionTitle>{t('profile.security')}</SectionTitle>
        <Row
          label={t('profile.twoFactor')}
          value={m.two_factor_enabled ? t('profile.twoFactorOn') : t('profile.twoFactorOff')}
          hint={m.two_factor_enabled && m.recovery_codes_left !== null ? t('profile.recoveryLeft', { count: m.recovery_codes_left }) : t('profile.twoFactorHint')}
        />
        {securityUrl ? <Button label={t('profile.twoFactorWeb')} variant="secondary" onPress={() => void Linking.openURL(securityUrl)} /> : null}
        {bio?.available ? (
          <Checkbox
            checked={auth.biometricEnabled}
            label={t('profile.biometricToggle', { method: bioName })}
            onChange={async (on) => {
              const ok = await auth.setBiometricEnabled(on);
              setBioMessage(ok ? null : t('profile.biometricFailed'));
            }}
          />
        ) : (
          <AppText variant="small" muted>
            {t('profile.biometricUnavailable')}
          </AppText>
        )}
        {bioMessage ? <Notice tone="wait">{bioMessage}</Notice> : null}
        <ListItem icon="phone-portrait-outline" title={t('devices.title')} subtitle={t('devices.subtitle')} onPress={() => router.push('/settings/devices')} />
      </Card>

      <Card>
        <ListItem icon="shield-checkmark-outline" title={t('privacy.title')} subtitle={t('privacy.subtitle')} onPress={() => router.push('/settings/privacy')} />
        <ListItem icon="help-buoy-outline" title={t('support.title')} subtitle={t('support.subtitle')} onPress={() => router.push('/support')} />
      </Card>

      <Button
        label={t('profile.logout')}
        variant="secondary"
        testID="profile-logout"
        onPress={() =>
          Alert.alert(t('profile.logoutConfirmTitle'), t('profile.logoutConfirmBody'), [
            { text: t('common.cancel'), style: 'cancel' },
            { text: t('profile.logout'), style: 'destructive', onPress: () => void auth.signOut() },
          ])
        }
      />
      <AppText variant="small" muted center>
        {t('profile.version', { version: APP_VERSION })}
        {APP_ENV !== 'production' ? ` · ${APP_ENV}` : ''}
        {config.data ? ` · API ${config.data.api_version}` : ''}
      </AppText>
    </Screen>
  );
}

/**
 * Invitation from a landlord (https://app.getdepiqo.com/t/<token> or depiqo://t/<token>).
 * Anti-phishing first: landlord, address, amount and reference are shown large, to compare with the
 * lease, before anything else. Then: new account (choose a password) or, for an existing tenant
 * account, log in and accept.
 */
import { useQuery } from '@tanstack/react-query';
import { router, Stack, useLocalSearchParams, type Href } from 'expo-router';
import React, { useEffect, useState } from 'react';
import { Linking, StyleSheet, View } from 'react-native';

import { hasCode, isApiError } from '../../src/api/errors';
import { api } from '../../src/api/instance';
import { useAuth } from '../../src/auth/AuthProvider';
import { deviceInput } from '../../src/auth/device';
import { useSafeMutation } from '../../src/hooks/mutations';
import { useSensitiveScreen } from '../../src/hooks/useSensitiveScreen';
import { useI18n } from '../../src/i18n/I18nProvider';
import { parseDeepLink } from '../../src/lib/deeplink';
import { formatDateTime } from '../../src/lib/format';
import { formatMoney } from '../../src/lib/money';
import { clearPendingRoute, setPendingRoute } from '../../src/lib/pendingRoute';
import { Button } from '../../src/ui/Button';
import { ErrorState, FormError, Loading, Notice } from '../../src/ui/feedback';
import { Checkbox, TextField } from '../../src/ui/form';
import { Card, Row, Screen } from '../../src/ui/layout';
import { AppText } from '../../src/ui/Text';
import { useHeaderOptions } from '../../src/ui/header';
import { space, useTheme } from '../../src/ui/theme';

export default function InviteScreen() {
  useSensitiveScreen();
  const { token: raw } = useLocalSearchParams<{ token: string }>();
  const link = parseDeepLink(`/t/${raw ?? ''}`);
  const token = link?.kind === 'invite' ? link.token : null;
  const { t, tk, lang } = useI18n();
  const { colors } = useTheme();
  const auth = useAuth();
  const [confirmed, setConfirmed] = useState(false);
  const [password, setPassword] = useState('');
  const [repeat, setRepeat] = useState('');
  const [touched, setTouched] = useState(false);

  const invite = useQuery({
    queryKey: ['invite', token],
    queryFn: () => api.invite(token as string),
    enabled: !!token,
    retry: false,
    staleTime: 0,
  });

  useEffect(() => {
    if (auth.status === 'signedIn') clearPendingRoute();
  }, [auth.status]);

  const accept = useSafeMutation((vars: { password?: string }) => api.acceptInvite(token as string, vars.password ? { password: vars.password, device: deviceInput() } : {}), {
    onSuccess: async (res) => {
      if ('access_token' in res) await auth.completeLogin(res);
      router.replace(`/deposit/${encodeURIComponent(res.deposit_pid)}` as Href);
    },
  });

  const headerOptions = useHeaderOptions();
  const header = <Stack.Screen options={{ ...headerOptions, headerShown: true, title: t('invite.title') }} />;

  if (!token) {
    return (
      <Screen>
        {header}
        <Notice tone="alert" title={t('errors.invite_expired')} />
      </Screen>
    );
  }
  if (invite.isLoading) return <Loading />;
  if (invite.error || !invite.data) {
    return (
      <Screen>
        {header}
        <ErrorState error={invite.error} onRetry={hasCode(invite.error, 'invite_expired') ? undefined : () => void invite.refetch()} />
      </Screen>
    );
  }

  const inv = invite.data;
  const signedIn = auth.status === 'signedIn';
  const passwordError = touched && password.length < 12 ? t('validation.passwordLength') : null;
  const repeatError = touched && repeat !== password ? t('validation.passwordMismatch') : null;
  const webUrl = isApiError(accept.error) && accept.error.code === 'use_web' ? accept.error.fieldMessage('url') : null;
  const webLink = webUrl && /^https?:\/\//.test(webUrl) ? webUrl : null;
  const needsLogin = inv.existing_account && !signedIn;

  const submitNew = () => {
    setTouched(true);
    if (!confirmed || password.length < 12 || repeat !== password) return;
    accept.submit({ password });
  };

  return (
    <Screen keyboard testID="invite-screen">
      {header}
      <AppText variant="title" accessibilityRole="header">
        {t('invite.heading')}
      </AppText>
      <AppText muted>{t('invite.intro')}</AppText>

      <Card accent>
        <AppText variant="label" color={colors.accentText}>
          {t('invite.checkTitle')}
        </AppText>
        <Big testID="invite-landlord" label={t('invite.landlord')} value={inv.landlord.name} />
        <Big testID="invite-address" label={t('invite.address')} value={[inv.address.street, [inv.address.postcode, inv.address.city].filter(Boolean).join(' ')].filter(Boolean).join(', ')} />
        <Big testID="invite-amount" label={t('invite.amount')} value={formatMoney(inv.amount, lang)} />
        <Big testID="invite-reference" label={t('invite.reference')} value={inv.reference} />
      </Card>

      <Card>
        <Row label={t('invite.tenant')} value={`${inv.tenant.name}`} hint={inv.tenant.email} />
        <Row label={t('invite.region')} value={tk('region', inv.region, inv.region)} />
        <Row label={t('invite.holding')} value={tk('holding', inv.holding, inv.holding)} />
        <Row label={t('invite.expires')} value={formatDateTime(inv.expires_at, lang)} />
      </Card>

      <Notice tone="wait" title={t('invite.antiPhishingTitle')}>
        {lang === 'nl' ? inv.check : t('invite.antiPhishingBody')}
      </Notice>

      <Checkbox checked={confirmed} onChange={setConfirmed} label={t('invite.confirmDetails')} />
      {touched && !confirmed ? <AppText color={colors.dangerText}>{t('invite.confirmRequired')}</AppText> : null}

      {needsLogin ? (
        <>
          <Notice tone="info" title={t('invite.existingTitle')}>
            {t('invite.existingBody')}
          </Notice>
          <Button
            label={t('invite.loginFirst')}
            disabled={!confirmed}
            onPress={() => {
              setPendingRoute(`/t/${token}`);
              router.push('/login');
            }}
          />
        </>
      ) : signedIn ? (
        <>
          <FormError error={accept.error} />
          <Button
            label={t('invite.acceptSignedIn')}
            busy={accept.busy}
            disabled={!confirmed}
            onPress={() => {
              setTouched(true);
              if (confirmed) accept.submit({});
            }}
          />
        </>
      ) : (
        <View style={styles.form}>
          <AppText variant="heading">{t('invite.createTitle')}</AppText>
          <AppText muted>{t('invite.createBody', { email: inv.tenant.email })}</AppText>
          <TextField
            label={t('invite.password')}
            value={password}
            onChangeText={setPassword}
            secureTextEntry
            autoComplete="new-password"
            textContentType="newPassword"
            hint={t('invite.passwordHint')}
            error={passwordError}
          />
          <TextField
            label={t('invite.passwordRepeat')}
            value={repeat}
            onChangeText={setRepeat}
            secureTextEntry
            autoComplete="new-password"
            textContentType="newPassword"
            error={repeatError}
          />
          <FormError error={accept.error} />
          <Button label={t('invite.create')} onPress={submitNew} busy={accept.busy} disabled={!confirmed} />
        </View>
      )}

      {webLink ? <Button label={t('invite.openWeb')} variant="secondary" onPress={() => void Linking.openURL(webLink)} /> : null}
    </Screen>
  );
}

function Big({ label, value, testID }: { label: string; value: string; testID?: string }) {
  return (
    <View style={styles.big} accessible accessibilityLabel={`${label}: ${value}`} testID={testID}>
      <AppText variant="small" muted>
        {label}
      </AppText>
      <AppText variant="heading" selectable>
        {value}
      </AppText>
    </View>
  );
}

const styles = StyleSheet.create({
  big: { gap: 2 },
  form: { gap: space.m },
});

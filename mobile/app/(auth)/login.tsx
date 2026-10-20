/** Log in with e-mail and password. With two-step verification on, continue on /mfa. */
import { router } from 'expo-router';
import React, { useState } from 'react';
import { Linking, StyleSheet, View } from 'react-native';

import { isApiError } from '../../src/api/errors';
import { api } from '../../src/api/instance';
import { useAuth } from '../../src/auth/AuthProvider';
import { deviceInput } from '../../src/auth/device';
import { setMfaChallenge } from '../../src/auth/mfaChallenge';
import { useConfig } from '../../src/hooks/useConfig';
import { useSafeMutation } from '../../src/hooks/mutations';
import { useI18n } from '../../src/i18n/I18nProvider';
import { Button } from '../../src/ui/Button';
import { DepiqoMark } from '../../src/ui/DepiqoMark';
import { FormError, Notice } from '../../src/ui/feedback';
import { TextField } from '../../src/ui/form';
import { Screen } from '../../src/ui/layout';
import { AppText } from '../../src/ui/Text';
import { space } from '../../src/ui/theme';

export default function Login() {
  const { t } = useI18n();
  const auth = useAuth();
  const config = useConfig();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [touched, setTouched] = useState(false);

  const login = useSafeMutation(
    (vars: { email: string; password: string }) => api.login(vars.email, vars.password, deviceInput()),
    {
      onSuccess: async (res, vars) => {
        if (res.mfa_required === true) {
          setMfaChallenge(res, vars.email);
          setPassword('');
          router.push('/mfa');
          return;
        }
        await auth.completeLogin(res);
      },
    },
  );

  const emailError = touched && !/^\S+@\S+\.\S+$/.test(email.trim()) ? t('validation.email') : null;
  const passwordError = touched && !password ? t('validation.required') : null;
  const submit = () => {
    setTouched(true);
    auth.clearEndReason();
    if (!/^\S+@\S+\.\S+$/.test(email.trim()) || !password) return;
    login.submit({ email: email.trim().toLowerCase(), password });
  };

  const resetUrl = config.data?.links.password_reset;
  const retryAfter = isApiError(login.error) && login.error.retryAfter ? Math.ceil(login.error.retryAfter / 60) : null;

  return (
    <Screen edges={['top', 'bottom']} keyboard>
      <View style={styles.brand}>
        <DepiqoMark size={56} />
        <AppText variant="display" accessibilityRole="header">
          {t('auth.title')}
        </AppText>
        <AppText muted>{t('auth.subtitle')}</AppText>
      </View>

      {auth.endReason ? <Notice tone="wait" title={t(`errors.${auth.endReason}`)}>{t('auth.loginAgain')}</Notice> : null}

      <TextField
        label={t('auth.email')}
        value={email}
        onChangeText={setEmail}
        autoCapitalize="none"
        autoComplete="email"
        textContentType="username"
        keyboardType="email-address"
        returnKeyType="next"
        error={emailError}
        testID="login-email"
      />
      <TextField
        label={t('auth.password')}
        value={password}
        onChangeText={setPassword}
        secureTextEntry
        autoComplete="current-password"
        textContentType="password"
        returnKeyType="go"
        onSubmitEditing={submit}
        error={passwordError}
        testID="login-password"
      />

      <FormError error={login.error} />
      {retryAfter ? <AppText muted>{t('auth.retryAfter', { minutes: retryAfter })}</AppText> : null}

      <Button label={t('auth.submit')} onPress={submit} busy={login.busy} testID="login-submit" />
      {resetUrl ? (
        <Button label={t('auth.forgot')} onPress={() => void Linking.openURL(resetUrl)} variant="ghost" accessibilityHint={t('auth.forgotHint')} />
      ) : null}

      <Notice tone="info" title={t('auth.newHereTitle')}>
        {t('auth.newHereBody')}
      </Notice>
    </Screen>
  );
}

const styles = StyleSheet.create({
  brand: { gap: space.s, marginTop: space.xl, marginBottom: space.m },
});

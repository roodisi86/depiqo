/** Confirm identity so the partner bank can open the deposit account in the tenant's name. */
import { useQueryClient } from '@tanstack/react-query';
import { Stack, useLocalSearchParams } from 'expo-router';
import React, { useState } from 'react';

import { api } from '../../../../src/api/instance';
import { useIdempotentMutation } from '../../../../src/hooks/mutations';
import { useSensitiveScreen } from '../../../../src/hooks/useSensitiveScreen';
import { useI18n } from '../../../../src/i18n/I18nProvider';
import { normalizeBirthDate } from '../../../../src/lib/format';
import { Button } from '../../../../src/ui/Button';
import { FormError, Notice } from '../../../../src/ui/feedback';
import { TextField } from '../../../../src/ui/form';
import { Screen } from '../../../../src/ui/layout';
import { AppText } from '../../../../src/ui/Text';

export default function Identity() {
  useSensitiveScreen();
  const { pid } = useLocalSearchParams<{ pid: string }>();
  const { t, tk, lang } = useI18n();
  const qc = useQueryClient();
  const [name, setName] = useState('');
  const [birth, setBirth] = useState('');
  const [touched, setTouched] = useState(false);
  const verify = useIdempotentMutation((vars: { full_name: string; birth_date: string }, key) => api.verifyIdentity(pid, vars, key), {
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: ['deposit', pid] });
      await qc.invalidateQueries({ queryKey: ['deposits'] });
    },
  });
  const iso = normalizeBirthDate(birth);
  const submit = () => {
    setTouched(true);
    if (name.trim().length < 2 || !iso) return;
    verify.submit({ full_name: name.trim(), birth_date: iso });
  };
  const result = verify.data;
  return (
    <Screen keyboard>
      <Stack.Screen options={{ title: t('identity.title') }} />
      <AppText>{t('identity.intro')}</AppText>
      {result ? (
        <Notice tone={result.result === 'failed' || result.result === 'bank_unavailable' ? 'wait' : 'ok'} title={tk('identityResult', result.result, result.result)}>
          {lang === 'nl' ? result.message : undefined}
        </Notice>
      ) : null}
      <TextField
        label={t('identity.fullName')}
        value={name}
        onChangeText={setName}
        autoComplete="name"
        textContentType="name"
        error={touched && name.trim().length < 2 ? t('validation.required') : null}
      />
      <TextField
        label={t('identity.birthDate')}
        value={birth}
        onChangeText={setBirth}
        hint={t('identity.birthDateHint')}
        keyboardType="numbers-and-punctuation"
        autoComplete="birthdate-full"
        error={touched && !iso ? t('validation.date') : null}
      />
      <FormError error={verify.error} mutation />
      <Button label={t('identity.submit')} onPress={submit} busy={verify.busy} />
      <AppText variant="small" muted>
        {t('identity.privacy')}
      </AppText>
    </Screen>
  );
}

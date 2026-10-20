/** Ask Depiqo support a question: category, message, optionally about one deposit. Never shown to the landlord. */
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { router, Stack, useLocalSearchParams, type Href } from 'expo-router';
import React, { useState } from 'react';

import { api } from '../../../src/api/instance';
import { useIdempotentMutation } from '../../../src/hooks/mutations';
import { useI18n } from '../../../src/i18n/I18nProvider';
import { Button } from '../../../src/ui/Button';
import { FormError, Notice } from '../../../src/ui/feedback';
import { RadioList, TextField } from '../../../src/ui/form';
import { Card, Screen, SectionTitle } from '../../../src/ui/layout';
import { AppText } from '../../../src/ui/Text';

const CATEGORIES = ['deposit', 'invest', 'account', 'app', 'other'] as const;
type Category = (typeof CATEGORIES)[number];
const NO_DEPOSIT = '__none__';

export default function NewTicket() {
  const { t, tk } = useI18n();
  const params = useLocalSearchParams<{ deposit?: string }>();
  const qc = useQueryClient();
  const deposits = useQuery({ queryKey: ['deposits', 'picker'], queryFn: () => api.deposits(null, 50) });
  const [category, setCategory] = useState<Category | null>(params.deposit ? 'deposit' : null);
  const [deposit, setDeposit] = useState<string>(params.deposit ?? NO_DEPOSIT);
  const [subject, setSubject] = useState('');
  const [message, setMessage] = useState('');
  const [touched, setTouched] = useState(false);

  const create = useIdempotentMutation(
    (input: { category: string; message: string; subject?: string; deposit_pid?: string }, key: string) => api.createSupportTicket(input, key),
    {
      onSuccess: async (ticket) => {
        await qc.invalidateQueries({ queryKey: ['support'] });
        router.replace(`/support/${ticket.id}` as Href);
      },
    },
  );

  const messageOk = message.trim().length >= 10 && message.trim().length <= 4000;
  const submit = () => {
    setTouched(true);
    if (!category || !messageOk) return;
    create.submit({
      category,
      message: message.trim(),
      ...(subject.trim() ? { subject: subject.trim().slice(0, 120) } : {}),
      ...(deposit !== NO_DEPOSIT ? { deposit_pid: deposit } : {}),
    });
  };

  return (
    <Screen keyboard>
      <Stack.Screen options={{ title: t('support.new') }} />
      <Notice tone="info">{t('support.privacyNote')}</Notice>
      <Card>
        <SectionTitle>{t('support.category')}</SectionTitle>
        <RadioList<Category> label={t('support.category')} value={category} onChange={setCategory} options={CATEGORIES.map((c) => ({ value: c, label: tk('supportCategory', c, c) }))} />
        {touched && !category ? <AppText variant="small">{t('validation.chooseOne')}</AppText> : null}
      </Card>
      {deposits.data && deposits.data.items.length > 0 ? (
        <Card>
          <SectionTitle>{t('support.deposit')}</SectionTitle>
          <RadioList<string>
            label={t('support.deposit')}
            value={deposit}
            onChange={setDeposit}
            options={[
              { value: NO_DEPOSIT, label: t('support.noDeposit') },
              ...deposits.data.items.map((d) => ({ value: d.pid, label: `${d.address.street} · ${d.reference}` })),
            ]}
          />
        </Card>
      ) : null}
      <TextField label={t('support.subject')} value={subject} onChangeText={setSubject} maxLength={120} hint={t('common.optional')} />
      <TextField
        label={t('support.message')}
        value={message}
        onChangeText={setMessage}
        multiline
        maxLength={4000}
        hint={t('support.messageHint', { count: message.trim().length })}
        error={touched && !messageOk ? t('validation.messageLength') : null}
      />
      <FormError error={create.error} mutation />
      <Button label={t('support.send')} onPress={submit} busy={create.busy} />
    </Screen>
  );
}

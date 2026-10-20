/** A proposed new service fee applies only after explicit consent, and only from that day. */
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Stack } from 'expo-router';
import React, { useState } from 'react';

import { api } from '../../../src/api/instance';
import { useIdempotentMutation } from '../../../src/hooks/mutations';
import { useI18n } from '../../../src/i18n/I18nProvider';
import { formatDateTime } from '../../../src/lib/format';
import { formatBps } from '../../../src/lib/money';
import { Button } from '../../../src/ui/Button';
import { FormError, Notice, NotYetAvailable } from '../../../src/ui/feedback';
import { Checkbox } from '../../../src/ui/form';
import { InvestGuard, InvestQueryState, isPartnerDown } from '../../../src/ui/InvestGuard';
import { Card, Row, Screen } from '../../../src/ui/layout';
import { AppText } from '../../../src/ui/Text';

export default function FeeChangeScreen() {
  const { t } = useI18n();
  return (
    <InvestGuard title={t('feeChange.title')}>
      <FeeChange />
    </InvestGuard>
  );
}

function FeeChange() {
  const { t, lang } = useI18n();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ['invest', 'fee-change'], queryFn: api.feeChange, retry: false });
  const [ok, setOk] = useState(false);
  const accept = useIdempotentMutation((_: 'accept', key: string) => api.acceptFeeChange(key), {
    onSuccess: async () => {
      setOk(false);
      await qc.invalidateQueries({ queryKey: ['invest'] });
    },
  });
  const state = InvestQueryState({ isLoading: q.isLoading, error: q.error, onRetry: () => void q.refetch(), title: t('feeChange.title') });
  if (state) return state;
  if (!q.data) return null;
  if (isPartnerDown(accept.error)) return <NotYetAvailable />;
  const f = q.data;
  return (
    <Screen>
      <Stack.Screen options={{ title: t('feeChange.title') }} />
      {accept.data ? <Notice tone="ok">{lang === 'nl' ? accept.data.message : t('feeChange.accepted')}</Notice> : null}
      <Card>
        <Row label={t('feeChange.current')} value={formatBps(f.current_bps, lang)} />
        {f.pending_bps !== null ? <Row label={t('feeChange.proposed')} value={formatBps(f.pending_bps, lang)} strong hint={f.proposed_at ? formatDateTime(f.proposed_at, lang) : null} /> : null}
      </Card>
      <AppText muted>{lang === 'nl' ? f.note : t('feeChange.note')}</AppText>
      {f.pending_bps === null ? (
        <Notice tone="info">{t('feeChange.none')}</Notice>
      ) : (
        <>
          <Checkbox checked={ok} onChange={setOk} label={lang === 'nl' && f.accept_text ? f.accept_text : t('feeChange.acceptText', { rate: formatBps(f.pending_bps, lang) })} />
          <FormError error={accept.error} mutation />
          <Button label={t('feeChange.accept')} disabled={!ok} busy={accept.busy} onPress={() => accept.submit('accept')} />
        </>
      )}
    </Screen>
  );
}

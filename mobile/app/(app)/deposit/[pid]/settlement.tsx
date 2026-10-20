/**
 * Final settlement: the landlord's lines with evidence, totals, and the tenant's answer: agree, or
 * dispute with a reason (at least 10 characters). Depiqo does not decide disputes. For a deposit held
 * elsewhere, the release form PDF is available after agreement.
 */
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Stack, useLocalSearchParams } from 'expo-router';
import React, { useState } from 'react';
import { Alert, View } from 'react-native';

import { downloadAndShare } from '../../../../src/api/download';
import { api } from '../../../../src/api/instance';
import type { SettlementResult } from '../../../../src/api/schemas';
import { useAuth } from '../../../../src/auth/AuthProvider';
import { useIdempotentMutation, useSafeMutation } from '../../../../src/hooks/mutations';
import { useSensitiveScreen } from '../../../../src/hooks/useSensitiveScreen';
import { useI18n } from '../../../../src/i18n/I18nProvider';
import { formatDateTime } from '../../../../src/lib/format';
import { formatMoney } from '../../../../src/lib/money';
import { Button } from '../../../../src/ui/Button';
import { ErrorState, FormError, Loading, Notice } from '../../../../src/ui/feedback';
import { TextField } from '../../../../src/ui/form';
import { Card, Row, Screen, SectionTitle } from '../../../../src/ui/layout';
import { ListItem } from '../../../../src/ui/ListItem';
import { StatusPill } from '../../../../src/ui/StatusPill';
import { AppText } from '../../../../src/ui/Text';

const REASON_MIN = 10;
const REASON_MAX = 2000;

export default function SettlementScreen() {
  useSensitiveScreen();
  const { pid } = useLocalSearchParams<{ pid: string }>();
  const { t, tk, lang } = useI18n();
  const auth = useAuth();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ['deposit', pid, 'settlement'], queryFn: () => api.settlement(pid), enabled: !!pid });
  const deposit = useQuery({ queryKey: ['deposit', pid], queryFn: () => api.deposit(pid), enabled: !!pid });
  const docs = useQuery({ queryKey: ['deposit', pid, 'documents'], queryFn: () => api.documents(pid), enabled: !!pid });
  const [mode, setMode] = useState<'view' | 'dispute'>('view');
  const [reason, setReason] = useState('');
  const [touched, setTouched] = useState(false);
  const [done, setDone] = useState<string | null>(null);

  const after = async (res: SettlementResult) => {
    qc.setQueryData(['deposit', pid], res.deposit);
    qc.setQueryData(['deposit', pid, 'settlement'], { settlement: res.settlement });
    await qc.invalidateQueries({ queryKey: ['deposits'] });
    await qc.invalidateQueries({ queryKey: ['activity'] });
    setMode('view');
    setDone(lang === 'nl' ? res.message : null);
  };
  const agree = useIdempotentMutation((_: 'agree', key: string) => api.agreeSettlement(pid, key), { onSuccess: after });
  const dispute = useIdempotentMutation((vars: { reason: string }, key: string) => api.disputeSettlement(pid, vars.reason, key), { onSuccess: after });
  const openDoc = useSafeMutation((line: { document_id: number | null; document_path: string }) => {
    // The line only carries the document id; name and type come from the documents list.
    const doc = docs.data?.items.find((x) => x.id === line.document_id);
    const mime = doc?.mime ?? 'application/pdf';
    return auth.withLockSuspended(() => downloadAndShare(line.document_path, doc?.filename ?? `bewijs-${line.document_id ?? ''}`, mime, t('settlement.evidence')));
  });
  const release = useSafeMutation(() =>
    auth.withLockSuspended(() => downloadAndShare(api.releaseFormPath(pid), `vrijgaveformulier-${pid}.pdf`, 'application/pdf', t('releaseForm.title'))),
  );

  const title = <Stack.Screen options={{ title: t('settlement.title') }} />;
  if (q.isLoading) return <Loading />;
  if (q.error || !q.data) {
    return (
      <Screen>
        {title}
        <ErrorState error={q.error} onRetry={() => void q.refetch()} />
      </Screen>
    );
  }
  const s = q.data.settlement;
  if (!s) {
    return (
      <Screen>
        {title}
        <Notice tone="info" title={t('settlement.noneTitle')}>
          {t('settlement.none')}
        </Notice>
      </Screen>
    );
  }

  const reasonError = touched && reason.trim().length < REASON_MIN ? t('validation.reasonLength', { min: REASON_MIN }) : null;
  const confirmAgree = () =>
    Alert.alert(t('settlement.agreeConfirmTitle'), t('settlement.agreeConfirmBody', { amount: formatMoney(s.back_to_tenant, lang) }), [
      { text: t('common.cancel'), style: 'cancel' },
      { text: t('settlement.agree'), onPress: () => agree.submit('agree') },
    ]);

  return (
    <Screen keyboard refreshing={q.isRefetching} onRefresh={() => void q.refetch()} testID="settlement-screen">
      {title}
      {done ? <Notice tone="ok">{done}</Notice> : null}
      <Card>
        <StatusPill label={tk('settlementStatus', s.status, s.status)} tone={s.status === 'agreed' ? 'ok' : s.status === 'disputed' ? 'alert' : 'wait'} />
        {s.proposed_at ? <Row label={t('settlement.proposedAt')} value={formatDateTime(s.proposed_at, lang)} /> : null}
        {s.responded_at ? <Row label={t('settlement.respondedAt')} value={formatDateTime(s.responded_at, lang)} /> : null}
      </Card>

      <Card>
        <SectionTitle>{t('settlement.lines')}</SectionTitle>
        {s.lines.length === 0 ? <AppText muted>{t('settlement.noLines')}</AppText> : null}
        {s.lines.map((l, i) => (
          <View key={`${l.category}-${i}`} style={{ gap: 4 }}>
            <Row label={tk('settlementCategory', l.category, l.category_label)} value={formatMoney(l.amount, lang)} strong hint={l.description} />
            {l.document_path ? (
              <ListItem icon="attach-outline" title={t('settlement.evidence')} subtitle={t('settlement.evidenceHint')} onPress={() => openDoc.submit({ document_id: l.document_id, document_path: l.document_path as string })} />
            ) : (
              <AppText variant="small" muted>
                {t('settlement.noEvidence')}
              </AppText>
            )}
          </View>
        ))}
        <FormError error={openDoc.error} />
      </Card>

      <Card>
        <SectionTitle>{t('settlement.totals')}</SectionTitle>
        <Row label={t('settlement.depositAmount')} value={formatMoney(s.deposit_amount, lang)} />
        <Row label={t('settlement.deductions')} value={formatMoney(s.deductions, lang)} />
        <Row label={t('settlement.backToTenant')} value={formatMoney(s.back_to_tenant, lang)} strong />
        <Row label={t('settlement.interest')} value={formatMoney(s.interest, lang)} hint={s.interest ? t('settlement.interestNote') : t('settlement.interestUnknown')} />
      </Card>

      {s.dispute ? (
        <Notice tone="alert" title={t('settlement.disputeOpen', { date: formatDateTime(s.dispute.opened_at, lang) })}>
          {s.dispute.reason}
        </Notice>
      ) : null}
      {s.tenant_comment && !s.dispute ? <Notice tone="info" title={t('settlement.yourComment')}>{s.tenant_comment}</Notice> : null}
      <Notice tone="info">{lang === 'nl' ? s.note : t('settlement.note')}</Notice>

      {s.can_respond && mode === 'view' ? (
        <>
          <FormError error={agree.error} mutation />
          <Button label={t('settlement.agree')} onPress={confirmAgree} busy={agree.busy} testID="settlement-agree" />
          <Button label={t('settlement.dispute')} variant="secondary" onPress={() => setMode('dispute')} disabled={agree.busy} testID="settlement-dispute" />
        </>
      ) : null}

      {s.can_respond && mode === 'dispute' ? (
        <Card>
          <SectionTitle>{t('settlement.disputeTitle')}</SectionTitle>
          <AppText>{t('settlement.disputeIntro')}</AppText>
          <TextField
            label={t('settlement.disputeReason')}
            value={reason}
            onChangeText={setReason}
            multiline
            maxLength={REASON_MAX}
            hint={t('settlement.disputeHint', { count: reason.trim().length, max: REASON_MAX })}
            error={reasonError}
          />
          <FormError error={dispute.error} mutation />
          <Button
            label={t('settlement.disputeSubmit')}
            busy={dispute.busy}
            onPress={() => {
              setTouched(true);
              if (reason.trim().length >= REASON_MIN) dispute.submit({ reason: reason.trim() });
            }}
          />
          <Button label={t('common.cancel')} variant="ghost" onPress={() => setMode('view')} disabled={dispute.busy} />
        </Card>
      ) : null}

      {deposit.data?.release_form_available ? (
        <Card>
          <SectionTitle>{t('releaseForm.title')}</SectionTitle>
          <AppText>{t('releaseForm.explain')}</AppText>
          <FormError error={release.error} />
          <Button label={t('releaseForm.download')} variant="secondary" onPress={() => release.submit(undefined)} busy={release.busy} />
        </Card>
      ) : null}
    </Screen>
  );
}

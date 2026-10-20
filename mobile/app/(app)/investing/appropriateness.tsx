/**
 * Knowledge and experience test (passendheidstoets). If the result is "niet passend", the user sees the
 * reasons and the risk, must tick an explicit confirmation AND confirm once more before going on.
 */
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { router, Stack } from 'expo-router';
import React, { useState } from 'react';
import { Alert, View } from 'react-native';

import { api } from '../../../src/api/instance';
import type { Appropriateness } from '../../../src/api/schemas';
import { useSafeMutation } from '../../../src/hooks/mutations';
import { useI18n } from '../../../src/i18n/I18nProvider';
import { Button } from '../../../src/ui/Button';
import { FormError, Notice, NotYetAvailable } from '../../../src/ui/feedback';
import { Checkbox, RadioList } from '../../../src/ui/form';
import { InvestGuard, InvestQueryState, isPartnerDown } from '../../../src/ui/InvestGuard';
import { Card, Screen, SectionTitle } from '../../../src/ui/layout';
import { AppText } from '../../../src/ui/Text';

export default function AppropriatenessScreen() {
  const { t } = useI18n();
  return (
    <InvestGuard title={t('appropriateness.title')}>
      <Questionnaire />
    </InvestGuard>
  );
}

function Questionnaire() {
  const { t, lang } = useI18n();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ['invest', 'appropriateness'], queryFn: api.appropriateness, retry: false });
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [touched, setTouched] = useState(false);
  const [result, setResult] = useState<Appropriateness | null>(null);

  const refresh = async () => {
    await qc.invalidateQueries({ queryKey: ['invest'] });
  };
  const answer = useSafeMutation((a: Record<string, string>) => api.answerAppropriateness(a), {
    onSuccess: async (r) => {
      setResult(r);
      await refresh();
    },
  });
  const confirm = useSafeMutation(() => api.confirmAppropriatenessWarning(), {
    onSuccess: async (r) => {
      setResult(r);
      await refresh();
      router.replace('/investing/terms');
    },
  });

  const title = <Stack.Screen options={{ title: t('appropriateness.title') }} />;
  const state = InvestQueryState({ isLoading: q.isLoading, error: q.error, onRetry: () => void q.refetch(), title: t('appropriateness.title') });
  if (state) return state;
  if (!q.data) return null;
  if (isPartnerDown(answer.error) || isPartnerDown(confirm.error)) return <NotYetAvailable />;

  const data = q.data;
  const latest = result ?? data.latest;
  const missing = data.questions.filter((x) => !answers[x.key]);

  if (latest && (latest.requires_confirmation || latest.may_continue || !data.can_answer)) {
    return (
      <Screen>
        {title}
        <ResultView r={latest} onConfirm={() => confirm.submit(undefined)} confirming={confirm.busy} />
        <FormError error={confirm.error} />
        {latest.may_continue && !latest.requires_confirmation && data.can_answer ? (
          <Button label={t('appropriateness.toTerms')} onPress={() => router.replace('/investing/terms')} />
        ) : null}
        {data.can_answer && !latest.requires_confirmation ? (
          <Button label={t('appropriateness.again')} variant="ghost" onPress={() => setResult(null)} />
        ) : null}
      </Screen>
    );
  }

  return (
    <Screen>
      {title}
      <AppText>{t('appropriateness.intro')}</AppText>
      {lang !== 'nl' ? <AppText variant="small" muted>{t('common.dutchOnly')}</AppText> : null}
      {!data.can_answer ? <Notice tone="info">{t('appropriateness.cannotAnswer')}</Notice> : null}
      {data.questions.map((question, i) => (
        <Card key={question.key}>
          <AppText variant="label" muted>
            {t('appropriateness.question', { n: i + 1, total: data.questions.length })}
          </AppText>
          <AppText variant="bodyStrong">{question.text}</AppText>
          <RadioList<string>
            label={question.text}
            value={answers[question.key] ?? null}
            onChange={(v) => setAnswers((prev) => ({ ...prev, [question.key]: v }))}
            options={question.options.map((o) => ({ value: o.value, label: o.label }))}
          />
          {touched && !answers[question.key] ? <AppText variant="small">{t('validation.chooseOne')}</AppText> : null}
        </Card>
      ))}
      <FormError error={answer.error} />
      <Button
        label={t('appropriateness.submit')}
        busy={answer.busy}
        disabled={!data.can_answer}
        onPress={() => {
          setTouched(true);
          if (missing.length === 0) answer.submit(answers);
        }}
      />
    </Screen>
  );
}

function ResultView({ r, onConfirm, confirming }: { r: Appropriateness; onConfirm: () => void; confirming: boolean }) {
  const { t, tk, lang } = useI18n();
  const [ticked, setTicked] = useState(false);
  const passend = r.result === 'passend';
  return (
    <View style={{ gap: 16 }}>
      <Notice tone={passend ? 'ok' : 'alert'} title={tk('appropriatenessResult', r.result, r.result)}>
        {passend ? t('appropriateness.passendBody') : t('appropriateness.nietPassendBody')}
      </Notice>
      {!passend ? (
        <Card>
          <SectionTitle>{t('appropriateness.reasons')}</SectionTitle>
          {r.reason_keys.map((k, i) => (
            <AppText key={`${k}-${i}`}>• {k === 'other' || lang === 'nl' ? r.reasons[i] ?? tk('reason', k, k) : tk('reason', k, r.reasons[i] ?? k)}</AppText>
          ))}
        </Card>
      ) : null}
      {r.risk_text ? (
        <Notice tone="wait" title={t('invest.riskTitle')}>
          {r.risk_text}
        </Notice>
      ) : null}
      {r.requires_confirmation ? (
        <Card>
          <SectionTitle>{t('appropriateness.confirmTitle')}</SectionTitle>
          <Checkbox checked={ticked} onChange={setTicked} label={lang === 'nl' && r.confirmation_text ? r.confirmation_text : t('appropriateness.confirmText')} />
          <Button
            label={t('appropriateness.continueAnyway')}
            variant="danger"
            disabled={!ticked}
            busy={confirming}
            onPress={() =>
              Alert.alert(t('appropriateness.alertTitle'), t('appropriateness.alertBody'), [
                { text: t('appropriateness.stop'), style: 'cancel' },
                { text: t('appropriateness.continueAnyway'), style: 'destructive', onPress: onConfirm },
              ])
            }
          />
          <Button label={t('appropriateness.stop')} variant="ghost" onPress={() => router.replace('/invest')} />
        </Card>
      ) : null}
      {!passend && !r.requires_confirmation && r.warning_confirmed_at ? <Notice tone="info">{t('appropriateness.confirmedBefore')}</Notice> : null}
    </View>
  );
}

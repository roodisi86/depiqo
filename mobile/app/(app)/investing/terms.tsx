/** The partner's terms and the Depiqo Invest terms (versioned). Both must be accepted explicitly. */
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { router, Stack, type Href } from 'expo-router';
import React, { useState } from 'react';

import { hasCode } from '../../../src/api/errors';
import { api } from '../../../src/api/instance';
import { useSafeMutation } from '../../../src/hooks/mutations';
import { useI18n } from '../../../src/i18n/I18nProvider';
import { formatDateTime } from '../../../src/lib/format';
import { Button } from '../../../src/ui/Button';
import { FormError, Notice, NotYetAvailable } from '../../../src/ui/feedback';
import { Checkbox } from '../../../src/ui/form';
import { InvestGuard, InvestQueryState, isPartnerDown } from '../../../src/ui/InvestGuard';
import { Card, Row, Screen, SectionTitle } from '../../../src/ui/layout';
import { AppText } from '../../../src/ui/Text';

export default function TermsScreen() {
  const { t } = useI18n();
  return (
    <InvestGuard title={t('terms.title')}>
      <Terms />
    </InvestGuard>
  );
}

function Terms() {
  const { t, lang } = useI18n();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ['invest', 'terms'], queryFn: api.terms, retry: false });
  const [partner, setPartner] = useState(false);
  const [depiqo, setDepiqo] = useState(false);
  const accept = useSafeMutation((v: { partner: string; depiqo: string }) => api.acceptTerms(v.partner, v.depiqo), {
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: ['invest'] });
      router.replace({ pathname: '/investing/portfolios', params: { mode: 'open' } } as unknown as Href);
    },
  });

  const state = InvestQueryState({ isLoading: q.isLoading, error: q.error, onRetry: () => void q.refetch(), title: t('terms.title') });
  if (state) return state;
  if (!q.data) return null;
  if (isPartnerDown(accept.error)) return <NotYetAvailable />;
  const terms = q.data;
  const outdated = hasCode(accept.error, 'terms_outdated');

  return (
    <Screen>
      <Stack.Screen options={{ title: t('terms.title') }} />
      <AppText>{t('terms.intro')}</AppText>
      {lang !== 'nl' ? <AppText variant="small" muted>{t('common.dutchOnly')}</AppText> : null}
      <Card>
        <SectionTitle>{t('terms.partner', { name: terms.partner.name })}</SectionTitle>
        <Row label={t('terms.version')} value={terms.partner.version} />
        <AppText>{terms.partner.text}</AppText>
        <Checkbox checked={partner} onChange={setPartner} label={t('terms.acceptPartner', { name: terms.partner.name })} />
      </Card>
      <Card>
        <SectionTitle>{t('terms.depiqo')}</SectionTitle>
        <Row label={t('terms.version')} value={terms.depiqo.version} />
        <AppText>{terms.depiqo.text}</AppText>
        <Checkbox checked={depiqo} onChange={setDepiqo} label={t('terms.acceptDepiqo')} />
      </Card>
      <Notice tone="wait" title={t('invest.riskTitle')}>
        {terms.risk_text}
      </Notice>
      {terms.accepted?.partner_at ? <AppText variant="small" muted>{t('terms.acceptedAt', { date: formatDateTime(terms.accepted.partner_at, lang) })}</AppText> : null}
      <FormError error={accept.error} />
      {outdated ? <Button label={t('terms.reload')} variant="secondary" onPress={() => { setPartner(false); setDepiqo(false); void q.refetch(); }} /> : null}
      <Button
        label={t('terms.submit')}
        disabled={!partner || !depiqo}
        busy={accept.busy}
        onPress={() => accept.submit({ partner: terms.partner.version, depiqo: terms.depiqo.version })}
      />
    </Screen>
  );
}

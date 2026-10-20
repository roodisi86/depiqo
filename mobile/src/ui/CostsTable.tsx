/** Ex-ante costs in euro and the example scenarios, as the API computed them (never computed here). */
import React from 'react';
import { View } from 'react-native';

import type { QuoteCosts, Scenarios } from '../api/schemas';
import { useI18n } from '../i18n/I18nProvider';
import { formatBps, formatMoney, formatPercent, formatSignedMoney } from '../lib/money';
import { Row, SectionTitle } from './layout';
import { AppText } from './Text';

export function CostsTable({ costs, title }: { costs: QuoteCosts; title?: string }) {
  const { t, lang } = useI18n();
  return (
    <View style={{ gap: 4 }}>
      <SectionTitle>{title ?? t('costs.title')}</SectionTitle>
      {costs.amount ? <Row label={t('costs.forAmount')} value={formatMoney(costs.amount, lang)} /> : null}
      {costs.service_1y ? <Row label={t('costs.service1y')} value={formatMoney(costs.service_1y, lang)} hint={costs.service_fee_bps !== undefined ? t('costs.perYearRate', { rate: formatBps(costs.service_fee_bps, lang) }) : null} /> : null}
      {costs.fund_1y ? <Row label={t('costs.fund1y')} value={formatMoney(costs.fund_1y, lang)} hint={costs.ongoing_charges_bps !== undefined ? t('costs.perYearRate', { rate: formatBps(costs.ongoing_charges_bps, lang) }) : null} /> : null}
      {costs.transactions ? <Row label={t('costs.transactions')} value={formatMoney(costs.transactions, lang)} hint={costs.transaction_cost_bps !== undefined ? t('costs.rate', { rate: formatBps(costs.transaction_cost_bps, lang) }) : null} /> : null}
      {costs.total_1y ? (
        <Row
          label={t('costs.total1y')}
          value={formatMoney(costs.total_1y, lang)}
          strong
          hint={costs.percent_per_year !== undefined ? t('costs.percentPerYear', { pct: formatPercent(costs.percent_per_year, lang) }) : null}
        />
      ) : null}
      {costs.total_3y ? <Row label={t('costs.total3y')} value={formatMoney(costs.total_3y, lang)} /> : null}
      {costs.note ? (
        <AppText variant="small" muted>
          {lang === 'nl' ? costs.note : t('costs.note')}
        </AppText>
      ) : null}
    </View>
  );
}

export function ScenariosTable({ scenarios }: { scenarios: Scenarios }) {
  const { t, tk, lang } = useI18n();
  return (
    <View style={{ gap: 4 }}>
      <SectionTitle>{t('scenarios.title')}</SectionTitle>
      {scenarios.items.map((s) => (
        <Row
          key={s.key}
          label={`${tk('scenario', s.key, s.label)} (${formatPercent(s.yearly_return * 100, lang, 0)} ${t('scenarios.perYear')})`}
          value={formatMoney(s.value_after_3y, lang)}
          hint={t('scenarios.detail', {
            v1: formatMoney(s.value_after_1y, lang),
            r1: formatSignedMoney(s.result_1y, lang),
            r3: formatSignedMoney(s.result_3y, lang),
          })}
        />
      ))}
      <AppText variant="small" muted>
        {lang === 'nl' ? scenarios.note : t('scenarios.note')}
      </AppText>
    </View>
  );
}

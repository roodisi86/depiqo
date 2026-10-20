/**
 * One deposit: status, next step, the four separate amounts, where the deposit sits, payment details,
 * deadline, progress, payout split and links to documents, settlement, history and support.
 * Nothing on this screen moves money; the app has no endpoint for that.
 */
import { useQuery } from '@tanstack/react-query';
import { router, Stack, useLocalSearchParams, type Href } from 'expo-router';
import React from 'react';
import { StyleSheet, View } from 'react-native';

import { downloadAndShare } from '../../../../src/api/download';
import { api } from '../../../../src/api/instance';
import type { DepositDetail, Location } from '../../../../src/api/schemas';
import { useAuth } from '../../../../src/auth/AuthProvider';
import { useSafeMutation } from '../../../../src/hooks/mutations';
import { useInvestGate } from '../../../../src/hooks/useMe';
import { useSensitiveScreen } from '../../../../src/hooks/useSensitiveScreen';
import { useI18n } from '../../../../src/i18n/I18nProvider';
import { addressLine, depositStatusLabel, providerKindLabel } from '../../../../src/lib/display';
import { eventText } from '../../../../src/lib/eventText';
import { formatDate, formatDateTime } from '../../../../src/lib/format';
import { formatBps, formatMoney } from '../../../../src/lib/money';
import { AmountsBlock } from '../../../../src/ui/AmountsBlock';
import { Button } from '../../../../src/ui/Button';
import { CopyRow } from '../../../../src/ui/CopyRow';
import { ErrorState, FormError, Loading, Notice } from '../../../../src/ui/feedback';
import { Card, Row, Screen, SectionTitle } from '../../../../src/ui/layout';
import { ListItem } from '../../../../src/ui/ListItem';
import { StatusPill } from '../../../../src/ui/StatusPill';
import { AppText } from '../../../../src/ui/Text';
import { space, toneColors, useTheme } from '../../../../src/ui/theme';

const PAYOUT_STATES = new Set(['agreed', 'payout_pending', 'closed']);

export default function DepositScreen() {
  useSensitiveScreen();
  const { pid } = useLocalSearchParams<{ pid: string }>();
  const tr = useI18n();
  const { t } = tr;
  const q = useQuery({ queryKey: ['deposit', pid], queryFn: () => api.deposit(pid), enabled: !!pid });

  if (q.isLoading) return <Loading />;
  if (q.error || !q.data) {
    return (
      <Screen>
        <Stack.Screen options={{ title: t('deposit.title') }} />
        <ErrorState error={q.error} onRetry={() => void q.refetch()} />
      </Screen>
    );
  }
  const d = q.data;
  return (
    <Screen refreshing={q.isRefetching} onRefresh={() => void q.refetch()} testID="deposit-detail">
      <Stack.Screen options={{ title: d.reference }} />
      <Header d={d} />
      <NextAction d={d} />
      <Card>
        <SectionTitle>{t('amount.heading')}</SectionTitle>
        <AppText variant="small" muted>
          {t('amount.explainer')}
        </AppText>
        <AmountsBlock amounts={d.amounts} />
        {d.interest_note ? (
          <AppText variant="small" muted>
            {d.location.interest_rate_bps !== null ? t('deposit.interestRate', { rate: formatBps(d.location.interest_rate_bps, tr.lang) }) : d.interest_note}
          </AppText>
        ) : null}
      </Card>
      <LocationCard d={d} />
      {d.payment_instructions || d.payment_problem ? <PaymentCard d={d} /> : null}
      <DeadlineCard d={d} />
      {d.payout ? (
        <Card>
          <SectionTitle>{t('payout.title')}</SectionTitle>
          <Row label={t('payout.toTenant')} value={formatMoney(d.payout.to_tenant, tr.lang)} strong />
          <Row label={t('payout.toLandlord')} value={formatMoney(d.payout.to_landlord, tr.lang)} />
          <AppText variant="small" muted>
            {t('payout.note')}
          </AppText>
        </Card>
      ) : null}
      <ProgressCard d={d} />
      <PayoutChoiceLink d={d} />
      <LinksCard d={d} />
      <RecentEvents d={d} />
    </Screen>
  );
}

function Header({ d }: { d: DepositDetail }) {
  const tr = useI18n();
  return (
    <View style={styles.header}>
      <AppText variant="title" accessibilityRole="header">
        {addressLine(d.address)}
      </AppText>
      <AppText muted>
        {d.landlord.name} · {tr.tk('region', d.region, d.region)}
      </AppText>
      <StatusPill label={depositStatusLabel(d, tr)} tone={d.tone} />
      {d.location.sandbox ? <Notice tone="wait" title={tr.t('deposit.sandboxTitle')}>{tr.t('deposit.sandboxBody')}</Notice> : null}
    </View>
  );
}

function NextAction({ d }: { d: DepositDetail }) {
  const tr = useI18n();
  const { t, lang } = tr;
  const { colors } = useTheme();
  const auth = useAuth();
  const gate = useInvestGate();
  const release = useSafeMutation(() =>
    auth.withLockSuspended(() => downloadAndShare(api.releaseFormPath(d.pid), `vrijgaveformulier-${d.reference}.pdf`, 'application/pdf', t('releaseForm.title'))),
  );
  const a = d.next_action;
  if (!a) return null;
  if (a.code === 'choose_payout_destination' && gate !== 'available') {
    // Doorbeleggen is not part of this build or not offered: the share goes to the own account (the default).
    return <Notice tone="info" title={t('nextAction.payoutOwn.title')}>{t('nextAction.payoutOwn.description')}</Notice>;
  }
  const title = tr.has(`nextAction.${a.code}.title`) ? t(`nextAction.${a.code}.title`) : a.label;
  // The server's description is Dutch and sometimes specific (e.g. why not to pay). Show it in Dutch;
  // in French and English show our translation, and the Dutch text only for the "wait" cases.
  const description = lang === 'nl' ? a.description : a.code === 'wait' ? a.description : t(`nextAction.${a.code}.description`);
  const c = toneColors(a.code === 'wait' ? 'wait' : 'ok', colors);
  let action: React.ReactNode = null;
  switch (a.code) {
    case 'verify_identity':
      action = <Button label={t('nextAction.verify_identity.cta')} onPress={() => router.push(`/deposit/${encodeURIComponent(d.pid)}/identity` as Href)} />;
      break;
    case 'respond_settlement':
      action = <Button testID="open-settlement" label={t('nextAction.respond_settlement.cta')} onPress={() => router.push(`/deposit/${encodeURIComponent(d.pid)}/settlement` as Href)} />;
      break;
    case 'choose_payout_destination':
      action = <Button label={t('nextAction.choose_payout_destination.cta')} onPress={() => router.push(`/deposit/${encodeURIComponent(d.pid)}/payout-choice` as Href)} />;
      break;
    case 'release_form':
      action = <Button label={t('releaseForm.download')} onPress={() => release.submit(undefined)} busy={release.busy} />;
      break;
    default:
      action = null;
  }
  return (
    <View style={[styles.next, { backgroundColor: c.bg, borderColor: c.fg }]} accessibilityRole="summary">
      <AppText variant="label" color={c.fg}>
        {t('nextAction.label')}
      </AppText>
      <AppText variant="heading">{title}</AppText>
      <AppText>{description}</AppText>
      {a.code === 'pay' ? <AppText variant="small" muted>{t('nextAction.pay.below')}</AppText> : null}
      {action}
      <FormError error={release.error} />
    </View>
  );
}

function LocationCard({ d }: { d: DepositDetail }) {
  const tr = useI18n();
  const { t, tk, lang } = tr;
  const loc: Location = d.location;
  return (
    <Card>
      <SectionTitle>{t('location.title')}</SectionTitle>
      <AppText variant="bodyStrong">{providerKindLabel(d.holding, d.provider_kind, loc.label, tr)}</AppText>
      {lang === 'nl' ? <AppText muted>{loc.label}</AppText> : null}
      {loc.provider_name ? <Row label={t('location.provider')} value={loc.provider_name} /> : null}
      {loc.reference ? <Row label={loc.reference_label && lang === 'nl' ? loc.reference_label : t('location.reference')} value={loc.reference} /> : null}
      {d.holding === 'depiqo' ? (
        <Row label={t('location.account')} value={loc.account_open ? t('location.accountOpen') : t('location.accountNotOpen')} />
      ) : null}
      {loc.evidence ? (
        <Row label={t('location.evidence')} value={tk('evidence', loc.evidence.level, loc.evidence.label)} hint={tk('evidenceTenant', loc.evidence.level, loc.evidence.tenant)} />
      ) : null}
      {loc.assurance ? <Row label={t('location.assurance')} value={tk('assurance', loc.assurance.code, loc.assurance.label)} /> : null}
      {loc.guarantee ? (
        <View style={styles.block}>
          <AppText>{lang === 'nl' ? loc.guarantee.text : t(`guarantee.${loc.guarantee.kind === 'ocmw' ? 'ocmw' : 'third_party'}`)}</AppText>
          <Row
            label={t('location.guaranteeExpires')}
            value={formatDate(loc.guarantee.expires_on, lang)}
            hint={loc.guarantee.days_left !== null && loc.guarantee.days_left >= 0 ? t('common.daysLeft', { days: loc.guarantee.days_left }) : null}
          />
          {loc.guarantee.warning_key ? (
            <Notice tone="alert" title={tk('guaranteeWarning', loc.guarantee.warning_key, loc.guarantee.warning)}>
              {t('guaranteeWarning.action')}
            </Notice>
          ) : null}
        </View>
      ) : null}
      {loc.sandbox ? <AppText variant="small" muted>{t('location.sandbox')}</AppText> : null}
    </Card>
  );
}

function PaymentCard({ d }: { d: DepositDetail }) {
  const { t, lang } = useI18n();
  const p = d.payment_instructions;
  return (
    <Card>
      <SectionTitle>{t('payment.title')}</SectionTitle>
      {d.payment_problem ? <Notice tone="alert" title={t('payment.problemTitle')}>{d.payment_problem}</Notice> : null}
      {p ? (
        <>
          <Notice tone="wait" title={t('payment.warningTitle')}>
            {lang === 'nl' ? p.warning : t('payment.warning')}
          </Notice>
          <Row label={t('payment.amount')} value={formatMoney(p.amount, lang)} strong />
          <Row label={t('payment.beneficiary')} value={p.beneficiary} />
          <CopyRow label={t('payment.iban')} value={p.iban} mono />
          <CopyRow label={t('payment.reference')} value={p.reference} mono />
          {d.location.sandbox ? <Notice tone="wait">{t('payment.sandbox')}</Notice> : null}
        </>
      ) : null}
    </Card>
  );
}

function DeadlineCard({ d }: { d: DepositDetail }) {
  const { t, lang } = useI18n();
  const dl = d.deadline;
  if (!dl && !d.release_rule) return null;
  return (
    <Card>
      <SectionTitle>{t('deadline.title')}</SectionTitle>
      {dl ? (
        <>
          <Row
            label={dl.statutory ? t('deadline.statutory') : t('deadline.target')}
            value={formatDate(dl.date, lang)}
            hint={dl.days_left === null ? null : dl.days_left >= 0 ? t('common.daysLeft', { days: dl.days_left }) : t('deadline.overdue', { days: -dl.days_left })}
          />
          {lang === 'nl' ? <AppText variant="small" muted>{dl.why}</AppText> : null}
        </>
      ) : null}
      {d.release_rule && lang === 'nl' ? <AppText variant="small" muted>{d.release_rule}</AppText> : null}
      {d.lease_start ? <Row label={t('deadline.leaseStart')} value={formatDate(d.lease_start, lang)} /> : null}
      {d.lease_end ? <Row label={t('deadline.leaseEnd')} value={formatDate(d.lease_end, lang)} /> : null}
      {d.move_out_date ? <Row label={t('deadline.moveOut')} value={formatDate(d.move_out_date, lang)} /> : null}
    </Card>
  );
}

function ProgressCard({ d }: { d: DepositDetail }) {
  const { t, tk } = useI18n();
  const { colors } = useTheme();
  return (
    <Card>
      <SectionTitle>{t('progress.title')}</SectionTitle>
      {d.progress.on_hold ? <Notice tone="alert">{t('progress.onHold')}</Notice> : null}
      <View accessibilityRole="list" style={styles.steps}>
        {d.progress.steps.map((s, i) => {
          const color = s.state === 'done' ? colors.okText : s.state === 'current' ? colors.accentText : colors.textMuted;
          const label = tk('step', s.code, s.label);
          return (
            <View key={s.code} style={styles.step} accessible accessibilityLabel={`${i + 1}. ${label}: ${tk('stepState', s.state, s.state)}`}>
              <View style={[styles.dot, { borderColor: color, backgroundColor: s.state === 'done' ? color : 'transparent' }]} />
              <AppText variant={s.state === 'current' ? 'bodyStrong' : 'body'} color={s.state === 'upcoming' ? colors.textMuted : colors.text} style={styles.stepText}>
                {label}
              </AppText>
              <AppText variant="small" color={color}>
                {tk('stepState', s.state, s.state)}
              </AppText>
            </View>
          );
        })}
      </View>
    </Card>
  );
}

/** Doorbeleggen: only when the API offers it for this deposit. */
function PayoutChoiceLink({ d }: { d: DepositDetail }) {
  const { t } = useI18n();
  const gate = useInvestGate();
  const enabled = gate === 'available' && PAYOUT_STATES.has(d.status) && d.holding === 'depiqo' && d.next_action?.code !== 'choose_payout_destination';
  const q = useQuery({ queryKey: ['payout-choice', d.pid], queryFn: () => api.payoutChoice(d.pid), enabled, retry: false });
  if (!enabled || !q.data || (!q.data.available && !q.data.choice)) return null;
  return (
    <Card>
      <ListItem
        icon="swap-horizontal-outline"
        title={t('payoutChoice.title')}
        subtitle={q.data.destination === 'invest' ? t('payoutChoice.toInvest') : t('payoutChoice.toOwn')}
        onPress={() => router.push(`/deposit/${encodeURIComponent(d.pid)}/payout-choice` as Href)}
      />
    </Card>
  );
}

function LinksCard({ d }: { d: DepositDetail }) {
  const { t } = useI18n();
  const auth = useAuth();
  const base = `/deposit/${encodeURIComponent(d.pid)}`;
  const release = useSafeMutation(() =>
    auth.withLockSuspended(() => downloadAndShare(api.releaseFormPath(d.pid), `vrijgaveformulier-${d.reference}.pdf`, 'application/pdf', t('releaseForm.title'))),
  );
  return (
    <Card>
      <ListItem icon="document-text-outline" title={t('documents.title')} subtitle={t('documents.subtitle')} onPress={() => router.push(`${base}/documents` as Href)} />
      <ListItem icon="calculator-outline" title={t('settlement.title')} subtitle={t('settlement.subtitle')} onPress={() => router.push(`${base}/settlement` as Href)} />
      <ListItem icon="time-outline" title={t('events.title')} onPress={() => router.push(`${base}/events` as Href)} />
      {d.release_form_available ? (
        <ListItem icon="download-outline" title={t('releaseForm.title')} subtitle={t('releaseForm.subtitle')} onPress={() => release.submit(undefined)} />
      ) : null}
      <ListItem
        icon="chatbubble-ellipses-outline"
        title={t('support.askAboutDeposit')}
        onPress={() => router.push({ pathname: '/support/new', params: { deposit: d.pid } } as unknown as Href)}
      />
      <FormError error={release.error} />
    </Card>
  );
}

function RecentEvents({ d }: { d: DepositDetail }) {
  const tr = useI18n();
  const { t, lang } = tr;
  if (d.events.length === 0) return null;
  return (
    <Card>
      <SectionTitle>{t('events.recent')}</SectionTitle>
      {d.events.slice(0, 3).map((e) => (
        <Row key={e.id} label={formatDateTime(e.at, lang)} value={eventText(e, tr)} />
      ))}
      <Button label={t('common.seeAll')} variant="ghost" onPress={() => router.push(`/deposit/${encodeURIComponent(d.pid)}/events` as Href)} />
    </Card>
  );
}

const styles = StyleSheet.create({
  header: { gap: space.s },
  next: { borderRadius: 16, borderWidth: 1.5, padding: space.l, gap: space.s },
  block: { gap: space.s },
  steps: { gap: space.s },
  step: { flexDirection: 'row', alignItems: 'center', gap: space.m, minHeight: 32 },
  stepText: { flex: 1 },
  dot: { width: 14, height: 14, borderRadius: 7, borderWidth: 2 },
});

/** Loading, empty, error and notice states. */
import React from 'react';
import { ActivityIndicator, StyleSheet, View } from 'react-native';

import { isApiError } from '../api/errors';
import { useI18n } from '../i18n/I18nProvider';
import type { Translator } from '../i18n/core';
import { Button } from './Button';
import { DepiqoMark } from './DepiqoMark';
import { Card } from './layout';
import { AppText } from './Text';
import { radius, space, toneColors, useTheme } from './theme';

export function Loading({ label }: { label?: string }) {
  const { colors } = useTheme();
  const { t } = useI18n();
  return (
    <View style={styles.center} accessible accessibilityRole="progressbar" accessibilityLabel={label ?? t('common.loading')}>
      <ActivityIndicator size="large" color={colors.primary} />
    </View>
  );
}

export function Empty({ text }: { text: string }) {
  return (
    <Card>
      <AppText muted center>
        {text}
      </AppText>
    </Card>
  );
}

export function Notice({ tone = 'info', title, children }: { tone?: string; title?: string; children?: React.ReactNode }) {
  const { colors } = useTheme();
  const c = toneColors(tone, colors);
  return (
    <View style={[styles.notice, { backgroundColor: c.bg, borderColor: c.fg }]} accessibilityRole={tone === 'alert' ? 'alert' : undefined}>
      {title ? (
        <AppText variant="bodyStrong" color={c.fg}>
          {title}
        </AppText>
      ) : null}
      {typeof children === 'string' ? <AppText color={colors.text}>{children}</AppText> : children}
    </View>
  );
}

/** Title (translated code) and detail (the server's own text when it says more). */
export function errorText(err: unknown, tr: Translator, opts?: { mutation?: boolean }): { title: string; detail: string | null } {
  if (isApiError(err)) {
    if (err.isNetwork && opts?.mutation) return { title: tr.t('errors.network_mutation'), detail: null };
    const key = `errors.${err.code}`;
    const title = tr.has(key) ? tr.t(key) : err.serverMessage || tr.t('errors.unknown');
    const server = err.serverMessage && err.serverMessage !== title ? err.serverMessage : null;
    return { title, detail: server };
  }
  return { title: tr.t('errors.unknown'), detail: null };
}

export function ErrorState({ error, onRetry, mutation }: { error: unknown; onRetry?: () => void; mutation?: boolean }) {
  const tr = useI18n();
  const { title, detail } = errorText(error, tr, { mutation });
  if (isApiError(error) && error.code === 'partner_unavailable') return <NotYetAvailable />;
  return (
    <Notice tone="alert" title={title}>
      {detail ? <AppText>{detail}</AppText> : null}
      {onRetry ? <Button label={tr.t('common.retry')} onPress={onRetry} variant="secondary" compact /> : null}
    </Notice>
  );
}

/** Inline error under a form, announced to screen readers. */
export function FormError({ error, mutation }: { error: unknown; mutation?: boolean }) {
  const tr = useI18n();
  if (!error) return null;
  const { title, detail } = errorText(error, tr, { mutation });
  return (
    <Notice tone="alert" title={title}>
      {detail ? <AppText>{detail}</AppText> : null}
    </Notice>
  );
}

/** What every Invest screen shows on partner_unavailable: this, and nothing else. */
export function NotYetAvailable() {
  const { t } = useI18n();
  return (
    <View style={styles.center} accessible accessibilityRole="text" accessibilityLabel={t('invest.notYetAvailable')}>
      <DepiqoMark size={56} />
      <AppText variant="title" center>
        {t('invest.notYetAvailable')}
      </AppText>
    </View>
  );
}

const styles = StyleSheet.create({
  center: { flex: 1, alignItems: 'center', justifyContent: 'center', padding: space.xl, gap: space.l, minHeight: 240 },
  notice: { borderRadius: radius.s, borderLeftWidth: 4, padding: space.m, gap: space.s },
});

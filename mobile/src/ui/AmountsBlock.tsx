/**
 * The four deposit amounts, each on its own row, never mixed (see src/lib/amounts.ts).
 * "—" plus the backend's explanation when a figure is not known; never the required amount instead.
 */
import React from 'react';
import { StyleSheet, View } from 'react-native';

import type { Amount } from '../api/schemas';
import { useI18n } from '../i18n/I18nProvider';
import { amountViews, type AmountView } from '../lib/amounts';
import { AppText } from './Text';
import { space, useTheme } from './theme';

export function AmountsBlock({ amounts, compact }: { amounts: Amount[]; compact?: boolean }) {
  const { lang } = useI18n();
  const views = amountViews(amounts, lang);
  return (
    <View style={styles.list}>
      {views.map((v) => (
        <AmountLine key={v.key} view={v} compact={compact} />
      ))}
    </View>
  );
}

function AmountLine({ view, compact }: { view: AmountView; compact?: boolean }) {
  const { t, tk } = useI18n();
  const { colors } = useTheme();
  const label = t(`amount.${view.key}`);
  const sub = view.key === 'locked' ? t('amount.lockedSub') : null;
  const note = view.explanationKey ? tk('amountNote', view.explanationKey, view.explanation) : view.explanation;
  const spoken = view.known ? view.display : t('amount.unknownA11y');
  return (
    <View
      style={[styles.line, { borderBottomColor: colors.line }]}
      accessible
      accessibilityLabel={`${label}${sub ? ` (${sub})` : ''}: ${spoken}${note ? `. ${note}` : ''}`}
      testID={`amount-${view.key}`}
    >
      <View style={styles.top}>
        <View style={styles.labelBox}>
          <AppText variant="bodyStrong">{label}</AppText>
          {sub ? (
            <AppText variant="small" muted>
              {sub}
            </AppText>
          ) : null}
        </View>
        <AppText variant="money" color={view.known ? colors.text : colors.textMuted} style={styles.value}>
          {view.display}
        </AppText>
      </View>
      {note && (!compact || !view.known) ? (
        <AppText variant="small" muted>
          {note}
        </AppText>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  list: { gap: 0 },
  line: { paddingVertical: space.s, borderBottomWidth: StyleSheet.hairlineWidth, gap: 2 },
  top: { flexDirection: 'row', flexWrap: 'wrap', alignItems: 'flex-start', justifyContent: 'space-between', gap: space.s },
  labelBox: { flexShrink: 1, minWidth: 140 },
  value: { textAlign: 'right' },
});

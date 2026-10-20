/**
 * A simple line chart of the API series (value in teal, net deposits dashed). It only draws what the
 * API sent; it never fills gaps or projects.
 */
import React, { useState } from 'react';
import { StyleSheet, View, type LayoutChangeEvent } from 'react-native';
import Svg, { Line, Path } from 'react-native-svg';

import { useI18n } from '../i18n/I18nProvider';
import { boundsOf, linePath, type Point } from '../lib/chart';
import { formatDate } from '../lib/format';
import { formatCents } from '../lib/money';
import { AppText } from './Text';
import { space, useTheme } from './theme';

export function LineChart({ points, secondary, height = 180 }: { points: readonly Point[]; secondary?: readonly Point[] | null; height?: number }) {
  const { colors } = useTheme();
  const { t, lang } = useI18n();
  const [width, setWidth] = useState(0);
  const bounds = boundsOf(points, secondary);
  const onLayout = (e: LayoutChangeEvent) => setWidth(Math.round(e.nativeEvent.layout.width));
  if (!bounds || points.length < 2) {
    return (
      <AppText muted variant="small">
        {t('invest.chartEmpty')}
      </AppText>
    );
  }
  const first = points[0];
  const last = points[points.length - 1];
  const summary =
    first && last
      ? t('invest.chartA11y', {
          from: formatDate(first[0], lang),
          to: formatDate(last[0], lang),
          start: formatCents(first[1], lang),
          end: formatCents(last[1], lang),
        })
      : '';
  return (
    <View accessible accessibilityRole="image" accessibilityLabel={summary}>
      <View style={styles.axis}>
        <AppText variant="small" muted>
          {formatCents(Math.round(bounds.max), lang)}
        </AppText>
      </View>
      <View onLayout={onLayout} style={{ height }}>
        {width > 0 ? (
          <Svg width={width} height={height}>
            <Line x1={0} y1={height - 1} x2={width} y2={height - 1} stroke={colors.line} strokeWidth={1} />
            {secondary && secondary.length > 1 ? (
              <Path d={linePath(secondary, width, height, bounds)} stroke={colors.chartSecondary} strokeWidth={1.5} strokeDasharray="4 4" fill="none" />
            ) : null}
            <Path d={linePath(points, width, height, bounds)} stroke={colors.chartLine} strokeWidth={2.5} fill="none" strokeLinejoin="round" />
          </Svg>
        ) : null}
      </View>
      <View style={styles.footer}>
        <AppText variant="small" muted>
          {first ? formatDate(first[0], lang) : ''}
        </AppText>
        <AppText variant="small" muted>
          {formatCents(Math.round(bounds.min), lang)}
        </AppText>
        <AppText variant="small" muted>
          {last ? formatDate(last[0], lang) : ''}
        </AppText>
      </View>
      <View style={styles.legend}>
        <View style={[styles.swatch, { backgroundColor: colors.chartLine }]} />
        <AppText variant="small">{t('invest.legendValue')}</AppText>
        {secondary && secondary.length > 1 ? (
          <>
            <View style={[styles.swatch, styles.dashed, { borderColor: colors.chartSecondary }]} />
            <AppText variant="small">{t('invest.legendNetDeposits')}</AppText>
          </>
        ) : null}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  axis: { alignItems: 'flex-end' },
  footer: { flexDirection: 'row', justifyContent: 'space-between', flexWrap: 'wrap', gap: space.s },
  legend: { flexDirection: 'row', alignItems: 'center', gap: space.s, marginTop: space.s, flexWrap: 'wrap' },
  swatch: { width: 18, height: 3, borderRadius: 2 },
  dashed: { height: 0, borderTopWidth: 2, borderStyle: 'dashed', backgroundColor: 'transparent' },
});

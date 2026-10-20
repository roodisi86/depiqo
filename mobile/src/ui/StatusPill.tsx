/** A coloured status label. Colour is never the only signal: the text always says the status. */
import React from 'react';
import { StyleSheet, View } from 'react-native';

import { AppText } from './Text';
import { radius, space, toneColors, useTheme } from './theme';

export function StatusPill({ label, tone }: { label: string; tone: string }) {
  const { colors } = useTheme();
  const c = toneColors(tone, colors);
  return (
    <View style={[styles.pill, { backgroundColor: c.bg }]}>
      <View style={[styles.dot, { backgroundColor: c.fg }]} />
      <AppText variant="label" color={c.fg} style={styles.text}>
        {label}
      </AppText>
    </View>
  );
}

const styles = StyleSheet.create({
  pill: { flexDirection: 'row', alignItems: 'center', alignSelf: 'flex-start', gap: space.s, paddingHorizontal: space.m, paddingVertical: 6, borderRadius: radius.pill, maxWidth: '100%' },
  dot: { width: 8, height: 8, borderRadius: 4 },
  text: { flexShrink: 1 },
});

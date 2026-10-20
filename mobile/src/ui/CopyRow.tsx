/** A value with a copy button (IBAN, payment reference). Announces "copied" to screen readers. */
import { Ionicons } from '@expo/vector-icons';
import * as Clipboard from 'expo-clipboard';
import React, { useState } from 'react';
import { AccessibilityInfo, Pressable, StyleSheet, View } from 'react-native';

import { useI18n } from '../i18n/I18nProvider';
import { AppText } from './Text';
import { radius, space, TOUCH, useTheme } from './theme';

export function CopyRow({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  const { colors } = useTheme();
  const { t } = useI18n();
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    await Clipboard.setStringAsync(value);
    setCopied(true);
    AccessibilityInfo.announceForAccessibility(t('common.copiedA11y', { label }));
    setTimeout(() => setCopied(false), 2000);
  };
  return (
    <View style={[styles.row, { borderColor: colors.line, backgroundColor: colors.surface }]}>
      <View style={styles.text}>
        <AppText variant="small" muted>
          {label}
        </AppText>
        <AppText variant="bodyStrong" selectable style={mono ? styles.mono : undefined}>
          {value}
        </AppText>
      </View>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel={t('common.copyLabel', { label })}
        onPress={copy}
        style={({ pressed }) => [styles.button, { backgroundColor: pressed ? colors.surfaceAlt : colors.surfaceAccent }]}
      >
        <Ionicons name={copied ? 'checkmark' : 'copy-outline'} size={18} color={colors.accentText} />
        <AppText variant="label" color={colors.accentText}>
          {copied ? t('common.copied') : t('common.copy')}
        </AppText>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: 'row', alignItems: 'center', gap: space.m, borderWidth: 1, borderRadius: radius.s, padding: space.m, flexWrap: 'wrap' },
  text: { flex: 1, minWidth: 160, gap: 2 },
  mono: { letterSpacing: 0.5 },
  button: { flexDirection: 'row', alignItems: 'center', gap: space.xs, minHeight: TOUCH, minWidth: TOUCH, paddingHorizontal: space.m, borderRadius: radius.pill, justifyContent: 'center' },
});

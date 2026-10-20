/**
 * Buttons: at least 48pt high, a clear pressed state, and disabled + busy while an action runs, so a
 * double tap cannot send the same request twice.
 */
import React from 'react';
import { ActivityIndicator, Pressable, StyleSheet, View, type StyleProp, type ViewStyle } from 'react-native';

import { AppText } from './Text';
import { radius, space, TOUCH, useTheme } from './theme';

export type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'danger';

export interface ButtonProps {
  label: string;
  onPress: () => void;
  variant?: ButtonVariant;
  disabled?: boolean;
  busy?: boolean;
  accessibilityHint?: string;
  accessibilityLabel?: string;
  style?: StyleProp<ViewStyle>;
  compact?: boolean;
  testID?: string;
}

export function Button({ label, onPress, variant = 'primary', disabled, busy, accessibilityHint, accessibilityLabel, style, compact, testID }: ButtonProps) {
  const { colors } = useTheme();
  const inactive = !!disabled || !!busy;
  const palette = {
    primary: { bg: colors.primary, pressed: colors.primaryPressed, fg: colors.textOnPrimary, border: colors.primary },
    secondary: { bg: colors.surface, pressed: colors.surfaceAlt, fg: colors.accentText, border: colors.line },
    ghost: { bg: 'transparent', pressed: colors.surfaceAlt, fg: colors.accentText, border: 'transparent' },
    danger: { bg: colors.dangerBg, pressed: colors.surfaceAlt, fg: colors.dangerText, border: colors.dangerText },
  }[variant];
  return (
    <Pressable
      testID={testID}
      accessibilityRole="button"
      accessibilityLabel={accessibilityLabel ?? label}
      accessibilityHint={accessibilityHint}
      accessibilityState={{ disabled: inactive, busy: !!busy }}
      disabled={inactive}
      onPress={() => {
        if (!inactive) onPress();
      }}
      style={({ pressed }) => [
        styles.base,
        compact ? styles.compact : null,
        { backgroundColor: pressed ? palette.pressed : palette.bg, borderColor: palette.border, opacity: disabled && !busy ? 0.5 : 1 },
        style,
      ]}
    >
      <View style={styles.row}>
        {busy ? <ActivityIndicator color={palette.fg} style={styles.spinner} /> : null}
        <AppText variant="bodyStrong" color={palette.fg} center>
          {label}
        </AppText>
      </View>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  base: {
    minHeight: TOUCH,
    borderRadius: radius.pill,
    borderWidth: 1.5,
    paddingHorizontal: space.xl,
    paddingVertical: space.s,
    alignItems: 'center',
    justifyContent: 'center',
  },
  compact: { paddingHorizontal: space.l, alignSelf: 'flex-start' },
  row: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', flexWrap: 'wrap' },
  spinner: { marginRight: space.s },
});

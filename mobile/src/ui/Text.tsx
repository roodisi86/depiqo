/**
 * Text with the Depiqo type scale. Dynamic type stays on (allowFontScaling default), capped at 2x so
 * layouts stay usable; containers never fix a height around text.
 */
import React from 'react';
import { Text as RNText, type TextProps, type TextStyle } from 'react-native';

import { useFontsLoaded } from './fonts';
import { fonts, useTheme } from './theme';

export type TextVariant = 'display' | 'title' | 'heading' | 'body' | 'bodyStrong' | 'small' | 'label' | 'money' | 'moneyLarge';

const SIZES: Record<TextVariant, { size: number; line: number; weight: keyof typeof fonts; system: TextStyle['fontWeight'] }> = {
  display: { size: 30, line: 36, weight: 'extrabold', system: '800' },
  title: { size: 24, line: 30, weight: 'bold', system: '700' },
  heading: { size: 18, line: 24, weight: 'bold', system: '700' },
  body: { size: 16, line: 24, weight: 'regular', system: '400' },
  bodyStrong: { size: 16, line: 24, weight: 'semibold', system: '600' },
  small: { size: 14, line: 20, weight: 'regular', system: '400' },
  label: { size: 13, line: 18, weight: 'semibold', system: '600' },
  money: { size: 17, line: 24, weight: 'bold', system: '700' },
  moneyLarge: { size: 32, line: 38, weight: 'extrabold', system: '800' },
};

export interface AppTextProps extends TextProps {
  variant?: TextVariant;
  color?: string;
  muted?: boolean;
  center?: boolean;
}

export function AppText({ variant = 'body', color, muted, center, style, maxFontSizeMultiplier, ...rest }: AppTextProps) {
  const { colors } = useTheme();
  const loaded = useFontsLoaded();
  const s = SIZES[variant];
  const base: TextStyle = {
    fontSize: s.size,
    lineHeight: s.line,
    color: color ?? (muted ? colors.textMuted : colors.text),
    textAlign: center ? 'center' : undefined,
    ...(loaded ? { fontFamily: fonts[s.weight] } : { fontWeight: s.system }),
    ...(variant === 'money' || variant === 'moneyLarge' ? { fontVariant: ['tabular-nums'] } : {}),
  };
  return <RNText maxFontSizeMultiplier={maxFontSizeMultiplier ?? 2} style={[base, style]} {...rest} />;
}

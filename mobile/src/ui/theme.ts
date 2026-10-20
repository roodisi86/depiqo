/**
 * Design tokens from the Depiqo website (assets/site.css): deep navy, teal, mint, off-white, sand,
 * slate; Manrope; rounded cards and generous spacing. Text colours are chosen for WCAG AA contrast:
 * teal text uses #0D7268 (teal-ink) on light backgrounds and aqua #7FDCCF on dark ones.
 */
import { useColorScheme } from 'react-native';

export const palette = {
  deepNavy: '#102139',
  navy: '#172C43',
  navy2: '#22395A',
  teal: '#138E83',
  tealInk: '#0D7268',
  tealFresh: '#34B7A7',
  aqua: '#7FDCCF',
  mint: '#E7F5F0',
  mint2: '#D3EEE6',
  offWhite: '#FAFAF7',
  sand: '#F4F0E8',
  sand2: '#EAE3D6',
  line: '#E1E6E8',
  lineWarm: '#E6DFD2',
  slate: '#5B6C7E',
  ink: '#182B3D',
  ink2: '#3A4C5F',
  white: '#FFFFFF',
  onDark: '#F3F6F9',
  onDark2: '#B5C2D1',
  amber: '#8A5A00',
  amberBg: '#FFF3DC',
  red: '#A3352B',
  redBg: '#FCE9E6',
} as const;

export interface ThemeColors {
  bg: string;
  surface: string;
  surfaceAlt: string;
  surfaceAccent: string;
  text: string;
  textMuted: string;
  textOnPrimary: string;
  primary: string;
  primaryPressed: string;
  accentText: string;
  line: string;
  warnText: string;
  warnBg: string;
  dangerText: string;
  dangerBg: string;
  okText: string;
  okBg: string;
  infoText: string;
  infoBg: string;
  banner: string;
  bannerText: string;
  chartLine: string;
  chartSecondary: string;
  overlay: string;
}

const light: ThemeColors = {
  bg: palette.offWhite,
  surface: palette.white,
  surfaceAlt: palette.sand,
  surfaceAccent: palette.mint,
  text: palette.ink,
  textMuted: palette.slate,
  textOnPrimary: palette.white,
  primary: palette.tealInk,
  primaryPressed: '#0A5C54',
  accentText: palette.tealInk,
  line: palette.line,
  warnText: palette.amber,
  warnBg: palette.amberBg,
  dangerText: palette.red,
  dangerBg: palette.redBg,
  okText: palette.tealInk,
  okBg: palette.mint,
  infoText: palette.ink2,
  infoBg: '#EEF2F6',
  banner: '#8A5A00',
  bannerText: palette.white,
  chartLine: palette.tealInk,
  chartSecondary: palette.slate,
  overlay: palette.deepNavy,
};

const dark: ThemeColors = {
  bg: '#0B1728',
  surface: palette.deepNavy,
  surfaceAlt: palette.navy,
  surfaceAccent: '#123A3A',
  text: palette.onDark,
  textMuted: palette.onDark2,
  textOnPrimary: palette.deepNavy,
  primary: palette.aqua,
  primaryPressed: '#5FC8B9',
  accentText: palette.aqua,
  line: '#2A4466',
  warnText: '#F5C46B',
  warnBg: '#3A2E12',
  dangerText: '#F2A79F',
  dangerBg: '#3B1D1D',
  okText: palette.aqua,
  okBg: '#123A3A',
  infoText: palette.onDark,
  infoBg: palette.navy2,
  banner: '#F5C46B',
  bannerText: palette.deepNavy,
  chartLine: palette.aqua,
  chartSecondary: palette.onDark2,
  overlay: palette.deepNavy,
};

export const space = { xs: 4, s: 8, m: 12, l: 16, xl: 24, xxl: 32 } as const;
export const radius = { s: 10, m: 16, l: 24, pill: 999 } as const;
/** Minimum touch target (Apple 44pt, Android 48dp: 48 covers both). */
export const TOUCH = 48;

export const fonts = {
  regular: 'Manrope_400Regular',
  semibold: 'Manrope_600SemiBold',
  bold: 'Manrope_700Bold',
  extrabold: 'Manrope_800ExtraBold',
} as const;

export interface Theme {
  dark: boolean;
  colors: ThemeColors;
}

export function useTheme(): Theme {
  const scheme = useColorScheme();
  const isDark = scheme === 'dark';
  return { dark: isDark, colors: isDark ? dark : light };
}

export type Tone = 'ok' | 'wait' | 'info' | 'alert' | 'done' | 'neutral';

export function toneColors(tone: string, c: ThemeColors): { fg: string; bg: string } {
  switch (tone) {
    case 'ok':
      return { fg: c.okText, bg: c.okBg };
    case 'wait':
      return { fg: c.warnText, bg: c.warnBg };
    case 'alert':
      return { fg: c.dangerText, bg: c.dangerBg };
    case 'info':
      return { fg: c.infoText, bg: c.infoBg };
    default:
      return { fg: c.textMuted, bg: c.surfaceAlt };
  }
}

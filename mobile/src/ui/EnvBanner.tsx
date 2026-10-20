/**
 * The test-environment bar. Shown whenever /config says STAGING or SANDBOX (so simulated data is never
 * presented as real), and for non-production builds even before /config has answered.
 * The root layout places it above the navigator and gives the navigator a top inset of 0 below it.
 */
import React from 'react';
import { StyleSheet, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { APP_ENV } from '../config/env';
import { useConfig } from '../hooks/useConfig';
import { useI18n } from '../i18n/I18nProvider';
import { AppText } from './Text';
import { space, useTheme } from './theme';

export function useEnvBannerText(): string | null {
  const { data } = useConfig();
  const { t, tk } = useI18n();
  const banner = data?.banner ?? null;
  if (banner) return tk('env.banner', banner, banner);
  if (APP_ENV !== 'production') return t(`env.build.${APP_ENV}`);
  return null;
}

export function EnvBanner({ text }: { text: string }) {
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  return (
    <View
      style={[styles.bar, { backgroundColor: colors.banner, paddingTop: insets.top + 4 }]}
      accessible
      accessibilityRole="text"
      accessibilityLabel={text}
      testID="env-banner"
    >
      <AppText variant="label" color={colors.bannerText} center>
        {text}
      </AppText>
    </View>
  );
}

const styles = StyleSheet.create({
  bar: { paddingBottom: 6, paddingHorizontal: space.l },
});

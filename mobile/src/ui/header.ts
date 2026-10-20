/** Shared header look for stack navigators. */
import type { NativeStackNavigationOptions } from '@react-navigation/native-stack';

import { useI18n } from '../i18n/I18nProvider';
import { useFontsLoaded } from './fonts';
import { fonts, useTheme } from './theme';

export function useHeaderOptions(): NativeStackNavigationOptions {
  const { colors } = useTheme();
  const { t } = useI18n();
  const loaded = useFontsLoaded();
  return {
    title: '',
    headerStyle: { backgroundColor: colors.bg },
    headerTintColor: colors.accentText,
    headerTitleStyle: { color: colors.text, fontFamily: loaded ? fonts.bold : undefined },
    headerShadowVisible: false,
    headerBackTitle: t('common.back'),
    contentStyle: { backgroundColor: colors.bg },
  };
}

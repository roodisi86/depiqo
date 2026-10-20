import { Link, Stack } from 'expo-router';
import React from 'react';

import { useI18n } from '../src/i18n/I18nProvider';
import { Screen } from '../src/ui/layout';
import { AppText } from '../src/ui/Text';

export default function NotFound() {
  const { t } = useI18n();
  return (
    <Screen edges={['top', 'bottom']}>
      <Stack.Screen options={{ headerShown: false }} />
      <AppText variant="title" accessibilityRole="header">
        {t('notFound.title')}
      </AppText>
      <AppText muted>{t('notFound.body')}</AppText>
      <Link href="/" accessibilityRole="link">
        <AppText variant="bodyStrong">{t('notFound.home')}</AppText>
      </Link>
    </Screen>
  );
}

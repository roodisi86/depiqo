/** Blocks the app when the server says this version is too old (426, or /config minimum_app_version). */
import React from 'react';
import { Linking, StyleSheet, View } from 'react-native';

import { useConfig } from '../hooks/useConfig';
import { useI18n } from '../i18n/I18nProvider';
import { Button } from './Button';
import { DepiqoMark } from './DepiqoMark';
import { AppText } from './Text';
import { space, useTheme } from './theme';

export function UpdateRequired() {
  const { t } = useI18n();
  const { colors } = useTheme();
  const config = useConfig();
  const web = config.data?.links.web;
  return (
    <View style={[styles.root, { backgroundColor: colors.bg }]} accessibilityViewIsModal>
      <DepiqoMark size={64} />
      <AppText variant="title" center accessibilityRole="header">
        {t('update.title')}
      </AppText>
      <AppText center muted>
        {t('update.body')}
      </AppText>
      {web ? <Button label={t('update.web')} onPress={() => void Linking.openURL(web)} variant="secondary" /> : null}
    </View>
  );
}

const styles = StyleSheet.create({
  root: { ...StyleSheet.absoluteFillObject, alignItems: 'center', justifyContent: 'center', padding: space.xl, gap: space.l, zIndex: 950 },
});

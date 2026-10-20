/** Shown over the app while the stored session is locked. Biometric unlock, or log in with the password. */
import React, { useEffect, useRef, useState } from 'react';
import { StyleSheet, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { useI18n } from '../i18n/I18nProvider';
import { Button } from '../ui/Button';
import { DepiqoMark } from '../ui/DepiqoMark';
import { AppText } from '../ui/Text';
import { palette, space } from '../ui/theme';
import { useAuth } from './AuthProvider';

export function LockScreen() {
  const { unlock, switchToPassword } = useAuth();
  const { t } = useI18n();
  const insets = useSafeAreaInsets();
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);
  const tried = useRef(false);

  const tryUnlock = async () => {
    if (busy) return;
    setBusy(true);
    const ok = await unlock();
    setBusy(false);
    setFailed(!ok);
  };

  useEffect(() => {
    if (tried.current) return;
    tried.current = true;
    void tryUnlock();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <View style={[styles.root, { paddingTop: insets.top + space.xxl, paddingBottom: insets.bottom + space.xl }]} accessibilityViewIsModal>
      <View style={styles.center}>
        <DepiqoMark size={72} onDark />
        <AppText variant="title" color={palette.onDark} center accessibilityRole="header">
          {t('lock.title')}
        </AppText>
        <AppText color={palette.onDark2} center>
          {failed ? t('lock.failed') : t('lock.subtitle')}
        </AppText>
      </View>
      <View style={styles.actions}>
        <Button label={t('lock.unlock')} onPress={tryUnlock} busy={busy} />
        <Button label={t('lock.usePassword')} onPress={() => void switchToPassword()} variant="ghost" accessibilityHint={t('lock.usePasswordHint')} />
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { ...StyleSheet.absoluteFillObject, backgroundColor: palette.deepNavy, paddingHorizontal: space.xl, justifyContent: 'space-between', zIndex: 900 },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center', gap: space.l },
  actions: { gap: space.m },
});

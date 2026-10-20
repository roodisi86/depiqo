/**
 * A polite card to turn on push notifications. The system dialog only appears after the user taps
 * "Turn on". If the user said no before, the card points to the phone's settings instead.
 */
import React, { useEffect, useState } from 'react';
import { Linking } from 'react-native';

import { useI18n } from '../i18n/I18nProvider';
import { Button } from '../ui/Button';
import { Card } from '../ui/layout';
import { AppText } from '../ui/Text';
import { getPushPermission, registerPushToken, requestPushPermission, type PushPermission } from './push';

let dismissedThisSession = false;

export function PushPromptCard({ compact }: { compact?: boolean }) {
  const { t } = useI18n();
  const [perm, setPerm] = useState<PushPermission | null>(null);
  const [hidden, setHidden] = useState(dismissedThisSession);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let alive = true;
    void getPushPermission().then((p) => {
      if (alive) setPerm(p);
    });
    return () => {
      alive = false;
    };
  }, []);

  if (hidden || perm === null || perm === 'granted') return null;
  if (compact && perm === 'denied') return null;

  const enable = async () => {
    setBusy(true);
    const p = await requestPushPermission();
    setPerm(p);
    if (p === 'granted') await registerPushToken();
    setBusy(false);
  };

  return (
    <Card accent>
      <AppText variant="bodyStrong">{t('push.cardTitle')}</AppText>
      <AppText>{perm === 'denied' ? t('push.cardDenied') : t('push.cardBody')}</AppText>
      {perm === 'denied' ? (
        <Button label={t('push.openSettings')} variant="secondary" onPress={() => void Linking.openSettings()} />
      ) : (
        <Button label={t('push.enable')} onPress={() => void enable()} busy={busy} />
      )}
      <Button
        label={t('push.notNow')}
        variant="ghost"
        onPress={() => {
          dismissedThisSession = true;
          setHidden(true);
        }}
      />
    </Card>
  );
}

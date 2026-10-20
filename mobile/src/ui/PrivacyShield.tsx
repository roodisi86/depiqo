/**
 * Covers the app with the Depiqo mark whenever it is not in the foreground, so the iOS app switcher
 * snapshot (and Android's recents preview, together with FLAG_SECURE on sensitive screens) shows no
 * amounts or personal data.
 */
import React, { useEffect, useState } from 'react';
import { AppState, StyleSheet, View } from 'react-native';

import { DepiqoMark } from './DepiqoMark';
import { palette } from './theme';

export function PrivacyShield() {
  const [hidden, setHidden] = useState(AppState.currentState !== 'active' && AppState.currentState !== null);
  useEffect(() => {
    const sub = AppState.addEventListener('change', (s) => setHidden(s !== 'active'));
    return () => sub.remove();
  }, []);
  if (!hidden) return null;
  return (
    <View style={styles.shield} accessibilityElementsHidden importantForAccessibility="no-hide-descendants" pointerEvents="none">
      <DepiqoMark size={72} onDark />
    </View>
  );
}

const styles = StyleSheet.create({
  shield: { ...StyleSheet.absoluteFillObject, backgroundColor: palette.deepNavy, alignItems: 'center', justifyContent: 'center', zIndex: 1000 },
});

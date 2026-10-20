/** A tappable row with title, optional subtitle and a chevron. */
import { Ionicons } from '@expo/vector-icons';
import React from 'react';
import { Pressable, StyleSheet, View } from 'react-native';

import { AppText } from './Text';
import { space, TOUCH, useTheme } from './theme';

export function ListItem({
  title,
  subtitle,
  right,
  onPress,
  icon,
  accessibilityHint,
  danger,
}: {
  title: string;
  subtitle?: string | null;
  right?: string | null;
  onPress?: () => void;
  icon?: React.ComponentProps<typeof Ionicons>['name'];
  accessibilityHint?: string;
  danger?: boolean;
}) {
  const { colors } = useTheme();
  const content = (
    <View style={styles.row}>
      {icon ? <Ionicons name={icon} size={22} color={danger ? colors.dangerText : colors.accentText} /> : null}
      <View style={styles.text}>
        <AppText variant="bodyStrong" color={danger ? colors.dangerText : undefined}>
          {title}
        </AppText>
        {subtitle ? (
          <AppText variant="small" muted>
            {subtitle}
          </AppText>
        ) : null}
      </View>
      {right ? <AppText variant="bodyStrong">{right}</AppText> : null}
      {onPress ? <Ionicons name="chevron-forward" size={20} color={colors.textMuted} /> : null}
    </View>
  );
  if (!onPress) return content;
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={[title, subtitle, right].filter(Boolean).join(', ')}
      accessibilityHint={accessibilityHint}
      onPress={onPress}
      style={({ pressed }) => [styles.pressable, { backgroundColor: pressed ? colors.surfaceAlt : 'transparent' }]}
    >
      {content}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  pressable: { borderRadius: 12, marginHorizontal: -space.s, paddingHorizontal: space.s },
  row: { flexDirection: 'row', alignItems: 'center', gap: space.m, minHeight: TOUCH, paddingVertical: space.s },
  text: { flex: 1, gap: 2 },
});

/** Screen scaffolding: scrollable page, cards, section titles, label/value rows. */
import React from 'react';
import {
  KeyboardAvoidingView,
  Platform,
  RefreshControl,
  ScrollView,
  StyleSheet,
  View,
  type StyleProp,
  type ViewStyle,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { AppText } from './Text';
import { usePullRefresh } from './usePullRefresh';
import { radius, space, useTheme } from './theme';

export type Edge = 'top' | 'bottom';

export interface ScreenProps {
  children: React.ReactNode;
  refreshing?: boolean;
  onRefresh?: () => void;
  /** Which safe-area edges this screen pads itself (screens under a header only need 'bottom'). */
  edges?: Edge[];
  keyboard?: boolean;
  contentStyle?: StyleProp<ViewStyle>;
  testID?: string;
}

export function Screen({ children, refreshing, onRefresh, edges = ['bottom'], keyboard, contentStyle, testID }: ScreenProps) {
  const { colors } = useTheme();
  // Insets come from context, so the environment banner can take over the top inset.
  const insets = useSafeAreaInsets();
  const pull = usePullRefresh(refreshing, onRefresh);
  const pad = { paddingTop: edges.includes('top') ? insets.top : 0, paddingBottom: edges.includes('bottom') ? insets.bottom : 0 };
  const body = (
    <ScrollView
      testID={testID}
      contentContainerStyle={[styles.content, contentStyle]}
      keyboardShouldPersistTaps="handled"
      refreshControl={onRefresh ? <RefreshControl refreshing={pull.refreshing} onRefresh={pull.onRefresh} tintColor={colors.primary} /> : undefined}
    >
      {children}
    </ScrollView>
  );
  return (
    <View style={[styles.flex, pad, { backgroundColor: colors.bg }]}>
      {keyboard ? (
        <KeyboardAvoidingView style={styles.flex} behavior={Platform.OS === 'ios' ? 'padding' : undefined} keyboardVerticalOffset={Platform.OS === 'ios' ? 90 : 0}>
          {body}
        </KeyboardAvoidingView>
      ) : (
        body
      )}
    </View>
  );
}

export function Card({ children, style, accent, testID }: { children: React.ReactNode; style?: StyleProp<ViewStyle>; accent?: boolean; testID?: string }) {
  const { colors } = useTheme();
  return (
    <View
      testID={testID}
      style={[
        styles.card,
        { backgroundColor: accent ? colors.surfaceAccent : colors.surface, borderColor: accent ? colors.surfaceAccent : colors.line },
        style,
      ]}
    >
      {children}
    </View>
  );
}

export function SectionTitle({ children, right }: { children: string; right?: React.ReactNode }) {
  return (
    <View style={styles.sectionRow}>
      <AppText variant="heading" accessibilityRole="header" style={styles.flexShrink}>
        {children}
      </AppText>
      {right}
    </View>
  );
}

/** A label above or beside a value; stacks vertically when text is large. */
export function Row({ label, value, strong, valueColor, hint }: { label: string; value: string; strong?: boolean; valueColor?: string; hint?: string | null }) {
  const { colors } = useTheme();
  return (
    <View style={[styles.row, { borderBottomColor: colors.line }]} accessible accessibilityLabel={`${label}: ${value}${hint ? `. ${hint}` : ''}`}>
      <View style={styles.rowTop}>
        <AppText variant="small" muted style={styles.rowLabel}>
          {label}
        </AppText>
        <AppText variant={strong ? 'money' : 'bodyStrong'} color={valueColor} style={styles.rowValue}>
          {value}
        </AppText>
      </View>
      {hint ? (
        <AppText variant="small" muted>
          {hint}
        </AppText>
      ) : null}
    </View>
  );
}

export function Gap({ size = 'l' }: { size?: keyof typeof space }) {
  return <View style={{ height: space[size] }} />;
}

export const styles = StyleSheet.create({
  flex: { flex: 1 },
  flexShrink: { flexShrink: 1 },
  content: { padding: space.l, paddingBottom: space.xxl * 2, gap: space.l },
  card: { borderRadius: radius.m, borderWidth: 1, padding: space.l, gap: space.m },
  sectionRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: space.m, marginTop: space.s },
  row: { paddingVertical: space.s, borderBottomWidth: StyleSheet.hairlineWidth, gap: 2 },
  rowTop: { flexDirection: 'row', flexWrap: 'wrap', justifyContent: 'space-between', alignItems: 'baseline', gap: space.s },
  rowLabel: { flexShrink: 1, minWidth: 120 },
  rowValue: { flexShrink: 1, textAlign: 'right' },
});

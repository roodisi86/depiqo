/** Form controls: text field with label and error, checkbox, segmented choice, radio list. */
import { Ionicons } from '@expo/vector-icons';
import React from 'react';
import { Pressable, StyleSheet, TextInput, View, type TextInputProps } from 'react-native';

import { useFontsLoaded } from './fonts';
import { AppText } from './Text';
import { fonts, radius, space, TOUCH, useTheme } from './theme';

export interface TextFieldProps extends Omit<TextInputProps, 'style'> {
  label: string;
  error?: string | null;
  hint?: string | null;
}

export function TextField({ label, error, hint, multiline, ...rest }: TextFieldProps) {
  const { colors } = useTheme();
  const loaded = useFontsLoaded();
  return (
    <View style={styles.field}>
      <AppText variant="label">{label}</AppText>
      <TextInput
        accessibilityLabel={label}
        accessibilityHint={hint ?? undefined}
        placeholderTextColor={colors.textMuted}
        multiline={multiline}
        maxFontSizeMultiplier={2}
        style={[
          styles.input,
          multiline ? styles.multiline : null,
          {
            color: colors.text,
            backgroundColor: colors.surface,
            borderColor: error ? colors.dangerText : colors.line,
            fontFamily: loaded ? fonts.regular : undefined,
          },
        ]}
        {...rest}
      />
      {hint && !error ? (
        <AppText variant="small" muted>
          {hint}
        </AppText>
      ) : null}
      {error ? (
        <AppText variant="small" color={colors.dangerText} accessibilityLiveRegion="polite" accessibilityRole="alert">
          {error}
        </AppText>
      ) : null}
    </View>
  );
}

export function Checkbox({ checked, onChange, label, disabled }: { checked: boolean; onChange: (v: boolean) => void; label: string; disabled?: boolean }) {
  const { colors } = useTheme();
  return (
    <Pressable
      accessibilityRole="checkbox"
      accessibilityState={{ checked, disabled: !!disabled }}
      accessibilityLabel={label}
      disabled={disabled}
      onPress={() => onChange(!checked)}
      style={styles.checkRow}
      hitSlop={4}
    >
      <View style={[styles.box, { borderColor: checked ? colors.primary : colors.textMuted, backgroundColor: checked ? colors.primary : 'transparent' }]}>
        {checked ? <Ionicons name="checkmark" size={18} color={colors.textOnPrimary} /> : null}
      </View>
      <AppText style={styles.flexShrink}>{label}</AppText>
    </Pressable>
  );
}

export interface Option<T extends string> {
  value: T;
  label: string;
}

export function Segmented<T extends string>({
  options,
  value,
  onChange,
  label,
  testID,
}: {
  options: Option<T>[];
  value: T;
  onChange: (v: T) => void;
  label: string;
  /** E2E (Maestro): each option gets `${testID}-${value}`. */
  testID?: string;
}) {
  const { colors } = useTheme();
  return (
    <View accessibilityRole="tablist" accessibilityLabel={label} style={[styles.segment, { backgroundColor: colors.surfaceAlt, borderColor: colors.line }]}>
      {options.map((o) => {
        const selected = o.value === value;
        return (
          <Pressable
            key={o.value}
            accessibilityRole="tab"
            accessibilityState={{ selected }}
            accessibilityLabel={o.label}
            testID={testID ? `${testID}-${o.value}` : undefined}
            onPress={() => onChange(o.value)}
            style={[styles.segmentItem, selected ? { backgroundColor: colors.surface, borderColor: colors.primary } : { borderColor: 'transparent' }]}
          >
            <AppText variant="label" color={selected ? colors.accentText : colors.textMuted} center>
              {o.label}
            </AppText>
          </Pressable>
        );
      })}
    </View>
  );
}

export function RadioList<T extends string>({ options, value, onChange, label }: { options: Option<T>[]; value: T | null; onChange: (v: T) => void; label: string }) {
  const { colors } = useTheme();
  return (
    <View accessibilityRole="radiogroup" accessibilityLabel={label} style={styles.radioGroup}>
      {options.map((o) => {
        const selected = o.value === value;
        return (
          <Pressable
            key={o.value}
            accessibilityRole="radio"
            accessibilityState={{ checked: selected }}
            accessibilityLabel={o.label}
            onPress={() => onChange(o.value)}
            style={[styles.radioRow, { borderColor: selected ? colors.primary : colors.line, backgroundColor: selected ? colors.surfaceAccent : colors.surface }]}
          >
            <Ionicons name={selected ? 'radio-button-on' : 'radio-button-off'} size={22} color={selected ? colors.primary : colors.textMuted} />
            <AppText style={styles.flexShrink}>{o.label}</AppText>
          </Pressable>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  field: { gap: space.xs },
  input: { minHeight: TOUCH, borderWidth: 1.5, borderRadius: radius.s, paddingHorizontal: space.m, paddingVertical: space.s, fontSize: 16 },
  multiline: { minHeight: 120, textAlignVertical: 'top' },
  checkRow: { flexDirection: 'row', alignItems: 'flex-start', gap: space.m, minHeight: TOUCH, paddingVertical: space.s },
  box: { width: 26, height: 26, borderRadius: 7, borderWidth: 2, alignItems: 'center', justifyContent: 'center', marginTop: 1 },
  flexShrink: { flexShrink: 1 },
  segment: { flexDirection: 'row', borderRadius: radius.pill, borderWidth: 1, padding: 3, gap: 3 },
  segmentItem: { flex: 1, minHeight: 40, borderRadius: radius.pill, borderWidth: 1.5, alignItems: 'center', justifyContent: 'center', paddingHorizontal: space.s },
  radioGroup: { gap: space.s },
  radioRow: { flexDirection: 'row', alignItems: 'center', gap: space.m, minHeight: TOUCH, borderWidth: 1.5, borderRadius: radius.s, padding: space.m },
});

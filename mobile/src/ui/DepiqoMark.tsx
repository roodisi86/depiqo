/** The Depiqo mark, from brand/depiqo-mark.svg (and its dark variant). */
import React from 'react';
import Svg, { Circle, Path } from 'react-native-svg';

import { useTheme } from './theme';

export function DepiqoMark({ size = 40, onDark }: { size?: number; onDark?: boolean }) {
  const { dark } = useTheme();
  const light = onDark ?? dark;
  const stroke = light ? '#FFFFFF' : '#0B1426';
  const dot = light ? '#22B8A8' : '#087F78';
  return (
    <Svg width={size} height={size} viewBox="0 0 64 64" accessibilityRole="image" accessibilityLabel="Depiqo">
      <Circle cx={30} cy={39} r={15} fill="none" stroke={stroke} strokeWidth={8} />
      <Path d="M49 10V54" stroke={stroke} strokeWidth={8} strokeLinecap="round" fill="none" />
      <Circle cx={30} cy={39} r={5.5} fill={dot} />
    </Svg>
  );
}

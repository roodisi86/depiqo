/**
 * Marks a screen as sensitive (amounts, IBANs, personal data). On Android this sets FLAG_SECURE, which
 * blanks the app-switcher preview and blocks screenshots; on iOS expo-screen-capture blocks screen
 * recording/screenshots where the OS allows it. The app-switcher snapshot on iOS is covered by
 * PrivacyShield (an overlay whenever the app is not active). Off in development builds so testers can
 * take screenshots.
 */
import * as ScreenCapture from 'expo-screen-capture';
import { useEffect } from 'react';

import { APP_ENV } from '../config/env';

let counter = 0;

export function useSensitiveScreen(): void {
  useEffect(() => {
    if (APP_ENV === 'development') return undefined;
    counter += 1;
    const key = `depiqo-sensitive-${counter}`;
    ScreenCapture.preventScreenCaptureAsync(key).catch(() => undefined);
    return () => {
      ScreenCapture.allowScreenCaptureAsync(key).catch(() => undefined);
    };
  }, []);
}

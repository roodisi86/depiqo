/**
 * Push notifications via Expo. The backend sends only a short generic title and "Open Depiqo voor de
 * details" (never amounts, addresses or names), plus {notification_id, path, type}. The details load in
 * the app after authentication.
 *
 * Permission is never asked at start-up: the user taps "Zet meldingen aan" on a card that explains
 * what we send. The Expo push token is registered with POST /devices/push-token.
 */
import * as Device from 'expo-device';
import * as Notifications from 'expo-notifications';
import { Platform } from 'react-native';

import { api } from '../api/instance';
import { EAS_PROJECT_ID, PLATFORM } from '../config/env';

Notifications.setNotificationHandler({
  handleNotification: async () => ({
    shouldShowBanner: true,
    shouldShowList: true,
    shouldPlaySound: false,
    shouldSetBadge: false,
  }),
});

export type PushPermission = 'granted' | 'denied' | 'undetermined';

export async function ensureAndroidChannel(): Promise<void> {
  if (Platform.OS !== 'android') return;
  await Notifications.setNotificationChannelAsync('default', {
    name: 'Depiqo',
    importance: Notifications.AndroidImportance.DEFAULT,
    // The payload is generic by design (no amounts or names), so it may show on the lock screen.
    lockscreenVisibility: Notifications.AndroidNotificationVisibility.PUBLIC,
    showBadge: false,
  });
}

export async function getPushPermission(): Promise<PushPermission> {
  try {
    const p = await Notifications.getPermissionsAsync();
    if (p.granted) return 'granted';
    return p.canAskAgain ? 'undetermined' : 'denied';
  } catch {
    return 'denied';
  }
}

export async function requestPushPermission(): Promise<PushPermission> {
  await ensureAndroidChannel();
  const p = await Notifications.requestPermissionsAsync({ ios: { allowAlert: true, allowSound: true, allowBadge: false } });
  if (p.granted) return 'granted';
  return p.canAskAgain ? 'undetermined' : 'denied';
}

export type RegisterResult = 'registered' | 'no_permission' | 'unsupported' | 'failed';

/** Gets the Expo push token and registers it for this device session. Silent when not possible. */
export async function registerPushToken(): Promise<RegisterResult> {
  if (!Device.isDevice || !EAS_PROJECT_ID) return 'unsupported';
  if ((await getPushPermission()) !== 'granted') return 'no_permission';
  try {
    await ensureAndroidChannel();
    const token = await Notifications.getExpoPushTokenAsync({ projectId: EAS_PROJECT_ID });
    await api.registerPushToken(token.data, PLATFORM);
    return 'registered';
  } catch {
    return 'failed';
  }
}

/** The deep link path and notification id from a tapped notification (validated later by the parser). */
export function readNotificationData(response: Notifications.NotificationResponse): { path: string | null; notificationId: number | null } {
  const data = (response.notification.request.content.data ?? {}) as Record<string, unknown>;
  const path = typeof data.path === 'string' ? data.path : null;
  const id = typeof data.notification_id === 'number' && Number.isInteger(data.notification_id) ? data.notification_id : null;
  return { path, notificationId: id };
}

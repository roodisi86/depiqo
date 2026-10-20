/** What the server stores about this device session (shown under "Devices"). */
import * as Device from 'expo-device';

import type { DeviceInput } from '../api/endpoints';
import { APP_VERSION, PLATFORM } from '../config/env';

/** The phone model, not the owner's device name (that often contains a person's name). */
export function deviceInput(): DeviceInput {
  const model = (Device.modelName ?? (PLATFORM === 'ios' ? 'iPhone' : 'Android')).slice(0, 60);
  return { name: `Depiqo app (${model})`, platform: PLATFORM, app_version: APP_VERSION };
}

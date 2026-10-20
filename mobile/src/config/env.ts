/** Values from app.config.ts (extra) at build time. */
import Constants from 'expo-constants';
import { Platform } from 'react-native';

export type AppEnv = 'development' | 'staging' | 'production';

interface Extra {
  appEnv?: string;
  apiUrl?: string;
  investEnabled?: boolean;
  eas?: { projectId?: string };
}

const extra = (Constants.expoConfig?.extra ?? {}) as Extra;

export const APP_ENV: AppEnv = extra.appEnv === 'staging' || extra.appEnv === 'production' ? extra.appEnv : 'development';
export const API_BASE_URL: string = (extra.apiUrl ?? 'http://localhost:5000').replace(/\/+$/, '');
export const APP_VERSION: string = Constants.expoConfig?.version ?? '1.0.0';
export const EAS_PROJECT_ID: string | null = extra.eas?.projectId ?? null;
export const PLATFORM: 'ios' | 'android' = Platform.OS === 'android' ? 'android' : 'ios';
/** Build-time switch for Depiqo Invest (see app.config.ts). Missing means off. */
export const INVEST_BUILD_ENABLED: boolean = extra.investEnabled === true;

if (APP_ENV !== 'development' && !API_BASE_URL.startsWith('https://')) {
  // app.config.ts refuses this already; this is the second lock.
  throw new Error('Non-development builds must use an https API');
}

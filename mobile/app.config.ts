import type { ConfigContext, ExpoConfig } from 'expo/config';
import { withAndroidManifest, type ConfigPlugin } from 'expo/config-plugins';

/**
 * One codebase, three apps. Choose with APP_ENV:
 *   development  "Depiqo Dev"      com.getdepiqo.app.dev      API: EXPO_PUBLIC_API_URL (default http://localhost:5000)
 *   staging      "Depiqo Staging"  com.getdepiqo.app.staging  API: https://staging.getdepiqo.com (or EXPO_PUBLIC_API_URL, https only)
 *   production   "Depiqo"          com.getdepiqo.app          API: https://app.getdepiqo.com
 *
 * On a phone, "localhost" is the phone itself. Point EXPO_PUBLIC_API_URL at the LAN IP of the laptop
 * that runs the backend, e.g. EXPO_PUBLIC_API_URL=http://192.168.1.20:5000 (see README.md).
 */
type AppEnv = 'development' | 'staging' | 'production';

const APP_ENV: AppEnv = (() => {
  const raw = process.env.APP_ENV ?? 'development';
  if (raw === 'development' || raw === 'staging' || raw === 'production') return raw;
  throw new Error(`APP_ENV must be development, staging or production (got "${raw}")`);
})();

const VERSION = '1.0.0';
/**
 * Depiqo Invest in this build at all? Off by default in production: a store build must not contain a
 * feature that can be switched on remotely after review (App Store guideline 2.3.1), and investing apps
 * must be submitted by the licensed institution (3.2.1). Turn on with INVEST_ENABLED=1 only after the
 * partner and legal review (see docs/STORE-CHECKLIST.md). Development and staging have it on.
 */
const INVEST_ENABLED = process.env.INVEST_ENABLED ? process.env.INVEST_ENABLED === '1' : APP_ENV !== 'production';
const EAS_PROJECT_ID = process.env.EAS_PROJECT_ID ?? '';
const NAVY = '#102139';
const TEAL = '#138E83';

const ENVIRONMENTS: Record<AppEnv, { name: string; id: string; apiUrl: string; icon: string; adaptive: string; hosts: string[]; schemes: string[] }> = {
  development: {
    name: 'Depiqo Dev',
    id: 'com.getdepiqo.app.dev',
    apiUrl: process.env.EXPO_PUBLIC_API_URL ?? 'http://localhost:5000',
    icon: './assets/icon-dev.png',
    adaptive: './assets/adaptive-icon-dev.png',
    hosts: ['app.getdepiqo.com'],
    schemes: ['depiqo', 'depiqo-dev'],
  },
  staging: {
    name: 'Depiqo Staging',
    id: 'com.getdepiqo.app.staging',
    // CI (release validation) builds a staging APK against the founder's staging host from the repository variable
    // STAGING_API_URL, passed as EXPO_PUBLIC_API_URL. The https check below still applies.
    apiUrl: process.env.EXPO_PUBLIC_API_URL || 'https://staging.getdepiqo.com',
    icon: './assets/icon-staging.png',
    adaptive: './assets/adaptive-icon-staging.png',
    hosts: ['app.getdepiqo.com', 'staging.getdepiqo.com'],
    schemes: ['depiqo', 'depiqo-staging'],
  },
  production: {
    name: 'Depiqo',
    id: 'com.getdepiqo.app',
    apiUrl: 'https://app.getdepiqo.com',
    icon: './assets/icon.png',
    adaptive: './assets/adaptive-icon.png',
    hosts: ['app.getdepiqo.com'],
    schemes: ['depiqo'],
  },
};

const env = ENVIRONMENTS[APP_ENV];

if (APP_ENV !== 'development' && !env.apiUrl.startsWith('https://')) {
  throw new Error(`The ${APP_ENV} API must use https`);
}

/**
 * Android: plain http only for the development app (a laptop on the LAN, or the CI backend at 10.0.2.2 in the
 * emulator). A release-variant build would otherwise refuse cleartext. Staging and production leave the attribute
 * unset, so Android's default (no cleartext, targetSdk >= 28) applies; CI checks the merged manifest.
 */
const withDevelopmentCleartext: ConfigPlugin = (cfg) =>
  withAndroidManifest(cfg, (c) => {
    const application = c.modResults.manifest.application?.[0];
    if (application) application.$['android:usesCleartextTraffic'] = 'true';
    return c;
  });

/**
 * iOS App Transport Security. Development: local network only (127.0.0.1 in the simulator, the laptop's LAN IP on
 * a phone), never arbitrary loads. Staging and production: both off, written explicitly so a template default
 * cannot switch local networking on in a store build.
 */
const ATS =
  APP_ENV === 'development'
    ? { NSAllowsArbitraryLoads: false, NSAllowsLocalNetworking: true }
    : { NSAllowsArbitraryLoads: false, NSAllowsLocalNetworking: false };

// Dutch usage strings, shown by iOS when the app asks for a permission.
const CAMERA_TEXT = 'Depiqo gebruikt de camera alleen als jij een foto wilt toevoegen aan je borgdossier, bijvoorbeeld van de staat van de woning.';
const PHOTOS_TEXT = 'Depiqo opent je foto’s alleen als jij een foto wilt kiezen voor je borgdossier.';
const FACE_ID_TEXT = 'Met Face ID ontgrendel je Depiqo snel en veilig. Je kunt dit altijd uitzetten in je profiel.';

const buildConfig = ({ config }: ConfigContext): ExpoConfig => ({
  ...config,
  name: env.name,
  slug: 'depiqo-wallet',
  owner: process.env.EXPO_OWNER || undefined,
  version: VERSION,
  orientation: 'portrait',
  icon: env.icon,
  scheme: env.schemes,
  userInterfaceStyle: 'automatic',
  newArchEnabled: true,
  runtimeVersion: { policy: 'appVersion' },
  updates: EAS_PROJECT_ID
    ? { url: `https://u.expo.dev/${EAS_PROJECT_ID}`, fallbackToCacheTimeout: 0, checkAutomatically: 'ON_LOAD' }
    : { enabled: false },
  ios: {
    bundleIdentifier: env.id,
    supportsTablet: false,
    associatedDomains: env.hosts.map((h) => `applinks:${h}`),
    config: { usesNonExemptEncryption: false },
    infoPlist: {
      NSCameraUsageDescription: CAMERA_TEXT,
      NSPhotoLibraryUsageDescription: PHOTOS_TEXT,
      NSFaceIDUsageDescription: FACE_ID_TEXT,
      ITSAppUsesNonExemptEncryption: false,
      CFBundleAllowMixedLocalizations: true,
      CFBundleDevelopmentRegion: 'nl',
      CFBundleLocalizations: ['nl', 'fr', 'en'],
      // Only the development app may talk to a laptop over plain http on the local network (see ATS above).
      NSAppTransportSecurity: ATS,
    },
  },
  android: {
    package: env.id,
    adaptiveIcon: { foregroundImage: env.adaptive, backgroundColor: NAVY },
    allowBackup: false,
    permissions: ['android.permission.CAMERA', 'android.permission.USE_BIOMETRIC', 'android.permission.USE_FINGERPRINT'],
    blockedPermissions: [
      'android.permission.RECORD_AUDIO',
      'android.permission.READ_EXTERNAL_STORAGE',
      'android.permission.WRITE_EXTERNAL_STORAGE',
      'android.permission.READ_MEDIA_IMAGES',
      'android.permission.READ_MEDIA_VIDEO',
      'android.permission.READ_MEDIA_AUDIO',
      'android.permission.ACCESS_FINE_LOCATION',
      'android.permission.ACCESS_COARSE_LOCATION',
    ],
    intentFilters: [
      {
        action: 'VIEW',
        autoVerify: true,
        data: env.hosts.flatMap((host) => [
          { scheme: 'https', host, pathPrefix: '/t/' },
          { scheme: 'https', host, pathPrefix: '/app-link/' },
        ]),
        category: ['BROWSABLE', 'DEFAULT'],
      },
    ],
  },
  plugins: [
    'expo-router',
    ['expo-splash-screen', { image: './assets/splash-icon.png', imageWidth: 160, resizeMode: 'contain', backgroundColor: NAVY }],
    ['expo-secure-store', { configureAndroidBackup: true }],
    ['expo-local-authentication', { faceIDPermission: FACE_ID_TEXT }],
    ['expo-image-picker', { cameraPermission: CAMERA_TEXT, photosPermission: PHOTOS_TEXT, microphonePermission: false }],
    ['expo-notifications', { icon: './assets/notification-icon.png', color: TEAL, defaultChannel: 'default' }],
  ],
  experiments: { typedRoutes: true },
  extra: {
    appEnv: APP_ENV,
    apiUrl: env.apiUrl.replace(/\/+$/, ''),
    investEnabled: INVEST_ENABLED,
    linkHosts: env.hosts,
    eas: EAS_PROJECT_ID ? { projectId: EAS_PROJECT_ID } : {},
  },
});

// Function plugins are not allowed in the typed `plugins` array, so the development-only plugin is applied here.
export default (ctx: ConfigContext): ExpoConfig => {
  const cfg = buildConfig(ctx);
  return APP_ENV === 'development' ? withDevelopmentCleartext(cfg) : cfg;
};

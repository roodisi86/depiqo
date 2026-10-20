/** The one API client of the app, wired to secure storage, the current language and the build config. */
import { secureTokenStore } from '../auth/secureTokenStore';
import { API_BASE_URL, APP_VERSION, PLATFORM } from '../config/env';
import { getCurrentLang } from '../i18n/runtime';
import { ApiClient, type FetchLike } from './client';
import { createApi } from './endpoints';

export const apiClient = new ApiClient({
  baseUrl: API_BASE_URL,
  tokenStore: secureTokenStore,
  fetchImpl: ((url, init) => fetch(url, init as RequestInit)) as FetchLike,
  getLanguage: getCurrentLang,
  platform: PLATFORM,
  appVersion: APP_VERSION,
});

export const api = createApi(apiClient);

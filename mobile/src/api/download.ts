/**
 * Downloads (documents, release form, statements) and the data export, then the system share sheet
 * ("Open in…", "Save to Files"). Files go to the app's cache folder, which is emptied on sign-out and at
 * start-up. Only server paths under /api/v1/ are fetched with the bearer token: a link from elsewhere
 * never gets the token.
 */
import * as FileSystem from 'expo-file-system';
import * as Sharing from 'expo-sharing';

import { clientError, errorFromBody } from './errors';
import { apiClient } from './instance';

const DIR = `${FileSystem.cacheDirectory ?? ''}depiqo-files/`;

function safeName(name: string): string {
  const cleaned = name.replace(/[^A-Za-z0-9._-]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 80);
  return cleaned || 'document';
}

function utiFor(mime: string): string | undefined {
  if (mime === 'application/pdf') return 'com.adobe.pdf';
  if (mime === 'image/jpeg') return 'public.jpeg';
  if (mime === 'image/png') return 'public.png';
  if (mime === 'application/json') return 'public.json';
  return undefined;
}

async function ensureDir(): Promise<void> {
  const info = await FileSystem.getInfoAsync(DIR);
  if (!info.exists) await FileSystem.makeDirectoryAsync(DIR, { intermediates: true });
}

async function share(uri: string, mime: string, title: string): Promise<void> {
  if (!(await Sharing.isAvailableAsync())) throw clientError('unknown');
  await Sharing.shareAsync(uri, { mimeType: mime, UTI: utiFor(mime), dialogTitle: title });
}

export async function downloadAndShare(path: string, filename: string, mime: string, title: string): Promise<void> {
  if (!path.startsWith('/api/v1/') || path.includes('..')) throw clientError('invalid_response');
  await ensureDir();
  const target = DIR + safeName(filename);
  const result = await apiClient.runAuthorized(async (headers) => {
    try {
      return await FileSystem.downloadAsync(apiClient.url(path), target, { headers });
    } catch {
      throw clientError('network_error');
    }
  });
  if (result.status < 200 || result.status >= 300) {
    let body = '';
    try {
      body = await FileSystem.readAsStringAsync(target);
    } catch {
      body = '';
    }
    await FileSystem.deleteAsync(target, { idempotent: true });
    throw errorFromBody(result.status, body, null);
  }
  await share(result.uri, mime, title);
}

/** Saves text (the data export) as a file and opens the share sheet. */
export async function shareTextFile(filename: string, text: string, mime: string, title: string): Promise<void> {
  await ensureDir();
  const target = DIR + safeName(filename);
  await FileSystem.writeAsStringAsync(target, text);
  await share(target, mime, title);
}

/** Removes every downloaded or exported file (sign-out, start-up). */
export async function clearDownloads(): Promise<void> {
  try {
    await FileSystem.deleteAsync(DIR, { idempotent: true });
  } catch {
    // nothing to clean
  }
}

/**
 * Documents of a deposit: open/download any of them, and add a photo from the camera or the photo
 * library, only with the kinds the API allows (upload_kinds) and only while upload_allowed.
 */
import { useQuery, useQueryClient } from '@tanstack/react-query';
import * as FileSystem from 'expo-file-system';
import * as ImagePicker from 'expo-image-picker';
import { Stack, useLocalSearchParams } from 'expo-router';
import React, { useState } from 'react';
import { Alert, View } from 'react-native';

import { downloadAndShare } from '../../../../src/api/download';
import { api } from '../../../../src/api/instance';
import type { DepositDocument } from '../../../../src/api/schemas';
import { useAuth } from '../../../../src/auth/AuthProvider';
import { useIdempotentMutation, useSafeMutation } from '../../../../src/hooks/mutations';
import { useSensitiveScreen } from '../../../../src/hooks/useSensitiveScreen';
import { useI18n } from '../../../../src/i18n/I18nProvider';
import { formatBytes, formatDate } from '../../../../src/lib/format';
import { Button } from '../../../../src/ui/Button';
import { ErrorState, FormError, Loading, Notice } from '../../../../src/ui/feedback';
import { RadioList } from '../../../../src/ui/form';
import { Card, Screen, SectionTitle } from '../../../../src/ui/layout';
import { ListItem } from '../../../../src/ui/ListItem';
import { AppText } from '../../../../src/ui/Text';

interface Picked {
  uri: string;
  mime: string;
  size: number | null;
}

export default function Documents() {
  useSensitiveScreen();
  const { pid } = useLocalSearchParams<{ pid: string }>();
  const tr = useI18n();
  const { t, tk, lang } = tr;
  const auth = useAuth();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ['deposit', pid, 'documents'], queryFn: () => api.documents(pid), enabled: !!pid });
  const [kind, setKind] = useState<string | null>(null);
  const [localError, setLocalError] = useState<string | null>(null);

  const open = useSafeMutation((doc: DepositDocument) =>
    auth.withLockSuspended(() => downloadAndShare(doc.download_path, doc.filename, doc.mime, tk('docKind', doc.kind, doc.kind_label))),
  );

  const upload = useIdempotentMutation(
    (vars: { kind: string; file: Picked }, key: string) => {
      const ext = vars.file.mime === 'image/png' ? 'png' : 'jpg';
      const name = `foto-${new Date().toISOString().slice(0, 10)}.${ext}`;
      return api.uploadDocument(pid, vars.kind, { uri: vars.file.uri, name, type: vars.file.mime }, key);
    },
    {
      fingerprint: (vars) => ({ kind: vars.kind, uri: vars.file.uri }),
      onSuccess: async () => {
        setKind(null);
        await qc.invalidateQueries({ queryKey: ['deposit', pid, 'documents'] });
        Alert.alert(t('documents.uploadedTitle'), t('documents.uploadedBody'));
      },
    },
  );

  if (q.isLoading) return <Loading />;
  if (q.error || !q.data) {
    return (
      <Screen>
        <Stack.Screen options={{ title: t('documents.title') }} />
        <ErrorState error={q.error} onRetry={() => void q.refetch()} />
      </Screen>
    );
  }
  const data = q.data;
  const allowedKinds = data.upload_kinds.map((k) => k.kind);

  const pick = async (source: 'camera' | 'library') => {
    setLocalError(null);
    if (!kind || !allowedKinds.includes(kind)) {
      setLocalError(t('documents.chooseKindFirst'));
      return;
    }
    const result = await auth.withLockSuspended(async () => {
      if (source === 'camera') {
        const perm = await ImagePicker.requestCameraPermissionsAsync();
        if (!perm.granted) {
          setLocalError(t('documents.cameraDenied'));
          return null;
        }
        return ImagePicker.launchCameraAsync({ mediaTypes: ['images'], quality: 0.7, exif: false, allowsEditing: false });
      }
      // The system photo picker needs no library permission on Android 13+ and iOS 14+.
      return ImagePicker.launchImageLibraryAsync({
        mediaTypes: ['images'],
        quality: 0.7,
        exif: false,
        allowsMultipleSelection: false,
        preferredAssetRepresentationMode: ImagePicker.UIImagePickerPreferredAssetRepresentationMode.Compatible,
      });
    });
    if (!result || result.canceled || !result.assets[0]) return;
    const asset = result.assets[0];
    const mime = asset.mimeType ?? (asset.uri.toLowerCase().endsWith('.png') ? 'image/png' : 'image/jpeg');
    if (!data.accepted_types.includes(mime)) {
      setLocalError(t('documents.typeNotAllowed'));
      return;
    }
    let size = asset.fileSize ?? null;
    if (size === null) {
      const info = await FileSystem.getInfoAsync(asset.uri);
      size = info.exists && typeof info.size === 'number' ? info.size : null;
    }
    if (size !== null && size > data.max_bytes) {
      setLocalError(t('documents.tooLarge', { max: formatBytes(data.max_bytes, lang) }));
      return;
    }
    upload.submit({ kind, file: { uri: asset.uri, mime, size } });
  };

  return (
    <Screen refreshing={q.isRefetching} onRefresh={() => void q.refetch()}>
      <Stack.Screen options={{ title: t('documents.title') }} />
      <Card>
        <SectionTitle>{t('documents.list')}</SectionTitle>
        {data.items.length === 0 ? <AppText muted>{t('documents.empty')}</AppText> : null}
        {data.items.map((doc) => (
          <ListItem
            key={doc.id}
            icon={doc.mime === 'application/pdf' ? 'document-outline' : 'image-outline'}
            title={tk('docKind', doc.kind, doc.kind_label)}
            subtitle={`${doc.filename} · ${formatBytes(doc.size_bytes, lang)} · ${formatDate(doc.created_at, lang)} · ${tk('uploadedBy', doc.uploaded_by, doc.uploaded_by)}`}
            accessibilityHint={t('documents.openHint')}
            onPress={() => open.submit(doc)}
          />
        ))}
        <FormError error={open.error} />
      </Card>

      <Card>
        <SectionTitle>{t('documents.add')}</SectionTitle>
        {!data.upload_allowed ? (
          <Notice tone="info">{t('documents.closed')}</Notice>
        ) : (
          <View style={{ gap: 12 }}>
            <AppText>{t('documents.addIntro')}</AppText>
            <RadioList
              label={t('documents.kind')}
              value={kind}
              onChange={(v) => setKind(v)}
              options={data.upload_kinds.map((k) => ({ value: k.kind, label: tk('docKind', k.kind, k.label) }))}
            />
            {localError ? <Notice tone="alert">{localError}</Notice> : null}
            <FormError error={upload.error} mutation />
            <Button label={t('documents.takePhoto')} onPress={() => void pick('camera')} busy={upload.busy} disabled={!kind} />
            <Button label={t('documents.pickPhoto')} variant="secondary" onPress={() => void pick('library')} disabled={!kind || upload.busy} />
            <AppText variant="small" muted>
              {t('documents.limits', { max: formatBytes(data.max_bytes, lang) })}
            </AppText>
          </View>
        )}
      </Card>
    </Screen>
  );
}

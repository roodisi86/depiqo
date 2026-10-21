/** A paged list screen (FlatList) with pull-to-refresh, "load more" on scroll and an empty state. */
import React from 'react';
import { ActivityIndicator, FlatList, RefreshControl, StyleSheet, View, type ListRenderItem } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { Empty } from './feedback';
import { space, useTheme } from './theme';
import { usePullRefresh } from './usePullRefresh';

export interface ListScreenProps<T> {
  data: T[];
  renderItem: ListRenderItem<T>;
  keyExtractor: (item: T) => string;
  header?: React.ReactElement | null;
  emptyText?: string;
  loading?: boolean;
  loadingMore?: boolean;
  hasMore?: boolean;
  onLoadMore?: () => void;
  refreshing?: boolean;
  onRefresh?: () => void;
  bottomInset?: boolean;
}

export function ListScreen<T>({
  data,
  renderItem,
  keyExtractor,
  header,
  emptyText,
  loading,
  loadingMore,
  hasMore,
  onLoadMore,
  refreshing,
  onRefresh,
  bottomInset = true,
}: ListScreenProps<T>) {
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const pull = usePullRefresh(refreshing, onRefresh);
  return (
    <FlatList
      style={{ backgroundColor: colors.bg }}
      contentContainerStyle={[styles.content, { paddingBottom: (bottomInset ? insets.bottom : 0) + space.xxl }]}
      data={data}
      renderItem={renderItem}
      keyExtractor={keyExtractor}
      ListHeaderComponent={header ?? null}
      ListEmptyComponent={!loading && emptyText ? <Empty text={emptyText} /> : null}
      ListFooterComponent={loadingMore || (loading && data.length === 0) ? <ActivityIndicator style={styles.footer} color={colors.primary} /> : null}
      ItemSeparatorComponent={Separator}
      onEndReached={() => {
        if (hasMore && !loadingMore) onLoadMore?.();
      }}
      onEndReachedThreshold={0.4}
      refreshControl={onRefresh ? <RefreshControl refreshing={pull.refreshing} onRefresh={pull.onRefresh} tintColor={colors.primary} /> : undefined}
    />
  );
}

function Separator() {
  return <View style={styles.sep} />;
}

const styles = StyleSheet.create({
  content: { padding: space.l, gap: 0 },
  sep: { height: space.m },
  footer: { marginVertical: space.l },
});

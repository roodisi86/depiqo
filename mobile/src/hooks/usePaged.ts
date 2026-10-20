/** Cursor pagination (limit + next_cursor) on top of useInfiniteQuery. */
import { useInfiniteQuery, type InfiniteData, type QueryKey } from '@tanstack/react-query';

import type { Page } from '../api/schemas';

export function usePaged<T>(queryKey: QueryKey, fetchPage: (cursor: string | null) => Promise<Page<T>>, enabled = true) {
  const q = useInfiniteQuery<Page<T>, unknown, InfiniteData<Page<T>, string | null>, QueryKey, string | null>({
    queryKey,
    queryFn: ({ pageParam }) => fetchPage(pageParam),
    initialPageParam: null,
    getNextPageParam: (last) => last.next_cursor ?? undefined,
    enabled,
  });
  const items: T[] = q.data ? q.data.pages.flatMap((p) => p.items) : [];
  return { ...q, items };
}

// Global mocks for native modules that unit tests may touch indirectly.
// The tests in src/**/__tests__ mostly exercise pure modules (no native code); these mocks keep
// accidental imports from crashing.
jest.mock('expo-secure-store', () => {
  const store = new Map<string, string>();
  return {
    WHEN_UNLOCKED_THIS_DEVICE_ONLY: 'WHEN_UNLOCKED_THIS_DEVICE_ONLY',
    getItemAsync: jest.fn(async (k: string) => (store.has(k) ? store.get(k) : null)),
    setItemAsync: jest.fn(async (k: string, v: string) => {
      store.set(k, v);
    }),
    deleteItemAsync: jest.fn(async (k: string) => {
      store.delete(k);
    }),
  };
});

jest.mock('expo-crypto', () => ({
  randomUUID: () => jest.requireActual<typeof import('crypto')>('crypto').randomUUID(),
}));

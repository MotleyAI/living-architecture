export interface StorageBackend {
  getDataset(name: string): number;
}

export class ModelReadCache {
  constructor(private readonly inner: StorageBackend) {}

  getDataset(name: string): number {
    return this.inner.getDataset(name);
  }
}

export class SubCache extends ModelReadCache {
  override getDataset(name: string): number {
    return name.length;
  }
}

export const literal = {
  getModel(): number {
    return 0;
  },
};

export function cached(inner: StorageBackend): StorageBackend {
  return new ModelReadCache(inner);
}

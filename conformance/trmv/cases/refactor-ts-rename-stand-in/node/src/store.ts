export interface StorageBackend {
  getModel(name: string): number;
}

export class ModelReadCache {
  constructor(private readonly inner: StorageBackend) {}

  getModel(name: string): number {
    return this.inner.getModel(name);
  }
}

export class SubCache extends ModelReadCache {
  override getModel(name: string): number {
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

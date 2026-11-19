interface Db {
  query(): number;
}

export const db = {} as unknown as Db;

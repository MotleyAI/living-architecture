export class Model {
  name = '';
}

export class ModelColumn {
  name = '';
}

export const SCHEMA = 'CREATE NODE TABLE Model(name STRING, PRIMARY KEY(name))';
export const FIND = "MATCH (m:Model) RETURN m.name";

export function find(i: number): string {
  return `MATCH (m:Model) WHERE m.id = ${i}`;
}

export const OTHER = 'MATCH (m:ModelColumn)';
export const PROSE = 'a Model in prose';

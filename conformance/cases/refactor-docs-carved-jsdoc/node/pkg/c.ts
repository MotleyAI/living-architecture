export interface IntrospectedColumn {
  name: string;
}

export class Ds {
  columns: string[] = [];
}

/** Joins `columns`. */
export function censusSql(columns: IntrospectedColumn[]): string {
  return columns.map((c) => c.name).join(', ');
}

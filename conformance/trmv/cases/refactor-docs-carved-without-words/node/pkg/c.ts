export interface IntrospectedColumn {
  name: string;
}

/** Holds `columns`. */
export class Ds {
  columns: string[] = [];
}

// reads `columns`
export function censusSql(columns: IntrospectedColumn[]): string {
  // joins `columns`
  return columns.map((c) => c.name).join(', ');
}

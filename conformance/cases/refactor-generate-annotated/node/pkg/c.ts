export interface IntrospectedColumn {
  name: string;
}

export class Ds {
  columns: string[] = [];
}

export function censusSql(columns: IntrospectedColumn[]): string {
  return columns.map((c) => c.name).join(', ');
}

export function fieldNames(columns: string[]): string[] {
  return columns;
}

export class Query {
  measures: string[] = [];
}

export function addMeasures(q: Query, measures: string[]): void {
  q.measures.push(...measures);
}

export function censusSql(columns: string[]): string {
  return columns.join(', ');
}

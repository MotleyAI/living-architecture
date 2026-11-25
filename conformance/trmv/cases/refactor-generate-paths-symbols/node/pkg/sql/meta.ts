export class Table {
  columns: string[] = [];
}

export function render(columns: string[]): string {
  return columns.join(', ');
}

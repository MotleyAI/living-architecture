export function f(x: any): unknown {
  return [Reflect.get(x, 'columns'), x["columns"]];
}

export function f(x: any): void {
  Reflect.get(x, 'columns');
  Reflect.set(x, 'columns', 1);
  Object.getOwnPropertyDescriptor(x, 'columns');
}

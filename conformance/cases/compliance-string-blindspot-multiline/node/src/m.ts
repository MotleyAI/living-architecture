export function f(x: any): unknown {
  return Reflect.get(
    x[
      0
    ],
    'columns',
  );
}

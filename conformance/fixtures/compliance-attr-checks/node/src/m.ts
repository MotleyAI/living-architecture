export function f(o: any): unknown {
  return Reflect.get(o, 'formula');
}

export function g(o: any): unknown {
  return o.formula;
}

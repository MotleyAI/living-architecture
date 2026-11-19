export function h(o: any): unknown {
  return [o.formula, Reflect.get(o, 'formula'), o.formula];
}

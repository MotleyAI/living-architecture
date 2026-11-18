export class Ds {
  columns: string[] = [];
  name = '';
}

export function parameter(d: Ds, s: string): unknown {
  return Reflect.get(d, s);
}

export function caller(d: Ds): unknown {
  return parameter(d, 'columns');
}

export function branches(d: Ds, flag: boolean): unknown {
  let s;
  if (flag) {
    s = 'columns';
  } else {
    s = 'name';
  }
  return Reflect.get(d, s);
}

export function unpacked(d: Ds): unknown {
  const [s, t] = ['columns', 'name'];
  return [Reflect.get(d, s), Reflect.get(d, t)];
}

export function reassigned(d: Ds): unknown {
  let s = 'name';
  s = 'columns';
  return Reflect.get(d, s);
}

export function called(d: Ds): unknown[] {
  const out: unknown[] = [];
  for (const s of new Set(['columns'])) {
    out.push(Reflect.get(d, s));
  }
  return out;
}

export function augmented(d: Ds): unknown {
  let s = 'columns';
  s += '';
  return Reflect.get(d, s);
}

export function caught(d: Ds): unknown {
  try {
    throw 'columns';
  } catch (s) {
    return typeof s === 'string' ? Reflect.get(d, s) : undefined;
  }
}

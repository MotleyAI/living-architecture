export interface O {
  next: number;
}

function call(kw: { next: number }): void {
  void kw;
}

export const old = 1;

export function use(o: O): number {
  // next is not read here
  call({ next: old });
  return o.next + old;
}

export function unrelated(): number {
  const next = 3;
  return next;
}

export function nested(): number {
  function inner(): number {
    const next = 4;
    return next;
  }
  return inner();
}

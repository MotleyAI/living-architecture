export class Q {
  measures(): number {
    return 1;
  }
  metrics(): number {
    return 2;
  }
}

export function use(q: Q): number {
  return q.measures() + q.metrics();
}

export function g(o: any, t: { id: number }): number {
  return o['id'] + t['id'] + o[`id`];
}

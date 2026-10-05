export function foo(): number {
  return 1;
}

export class Base {
  execute(): number {
    return foo();
  }
}

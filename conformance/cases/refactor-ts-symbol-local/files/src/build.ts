export function inner(): number {
  return 1;
}

export function build(): number {
  function helper(): number {
    return 2;
  }
  const twice = (): number => helper() * 2;
  return helper() + twice();
}

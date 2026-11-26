export function inner(): number {
  return 1;
}

export function build(): number {
  function inner(): number {
    return 2;
  }
  const twice = (): number => inner() * 2;
  return inner() + twice();
}

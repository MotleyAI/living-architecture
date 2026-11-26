it('x', () => {
  expect(a && b).toBe(true);
  expect(() => f(g())).toThrow();
});

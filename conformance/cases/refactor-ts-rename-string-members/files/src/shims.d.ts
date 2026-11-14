declare module 'vitest' {
  export const vi: { spyOn<T, K extends keyof T>(object: T, method: K): unknown };
}

declare const jest: { spyOn<T, K extends keyof T>(object: T, method: K): unknown };

declare module 'virtual:config' {
  export const flag: boolean;
}

declare module '*.css' {
  const classes: Record<string, string>;
  export default classes;
}

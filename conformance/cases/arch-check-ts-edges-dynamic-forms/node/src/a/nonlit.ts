const name = '../skip/m';

export const f = () => import(name);
export const g = () => require(name);
export const h = () => import(`../skip/${name}`);
export const k = (o: { require(s: string): unknown }) => o.require('../skip/m');

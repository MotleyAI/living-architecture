export const x = 1;
import a from './a'; // ALLOW(import-not-top): generated
import b from './b'; //ALLOW(import-not-top):x
import c from './c'; // ALLOW(composite-assert): wrong rule
import d from './d'; // ALLOW(import-not-top):
import e from './e'; // allow(import-not-top): lowercase
import f from './f'; /* # ALLOW(import-not-top): python form */

// The conventions gate and the comment counter for every language; facts come from `lang` or the other twin.
export { countComments } from './comments.js';
export { emit, languageOf } from './facts.js';
export { checkConventions, filesLabel, isTestFile, waived, type GateOptions } from './gate.js';

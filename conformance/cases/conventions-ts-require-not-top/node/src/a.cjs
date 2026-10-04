const a = require('a');
const { b } = require('b');
const c = require('c').c;
module.exports = require('d');
f(require('e'));
const g = cond ? require('g') : null;
require('h');
const k = (require('k'));

function load() {
  return require('fs');
}

const lazy = () => require('l');

if (process.env.X) {
  require('m');
}

const o = { p: require('p') };

function viaModule() {
  return module.require('q');
}

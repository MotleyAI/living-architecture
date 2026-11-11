'use strict';
// Removes the microsoft/pyright#11919 condition from basedpyright's CLI bundle as Node compiles it, in every
// thread; delete this file and its wiring once basedpyright ships the fix.
const fs = require('fs');
const path = require('path');
const Module = require('module');
const { isMainThread } = require('worker_threads');

const CONDITION = '!isGetTypeFromCodeFlowPending(referenceKeyWithSymbolId) &&';
const REPLACEMENT = 'true &&';
const VERSION_MODULE = /"\.\.\/pyright-internal\/src\/version\.json"\(module\) \{\s*"use strict";\s*module\.exports = "([^"]*)"/;

function record(resultPath, outcome, version, count) {
  if (!isMainThread) return;
  const tmp = path.join(path.dirname(resultPath), `.${path.basename(resultPath)}.${process.pid}.tmp`);
  fs.writeFileSync(tmp, JSON.stringify({ outcome, version, count }));
  fs.renameSync(tmp, resultPath);
}

function patch(source, resultPath, versions) {
  const found = VERSION_MODULE.exec(source);
  if (!found) return source;
  const version = found[1];
  const count = source.split(CONDITION).length - 1;
  const outcome = !versions.includes(version) ? 'unverified' : count !== 1 ? 'mismatch' : 'patched';
  record(resultPath, outcome, version, count);
  if (outcome !== 'patched') process.exit(2);
  return source.replace(CONDITION, REPLACEMENT);
}

const resultPath = process.env.LA_PYRIGHT_PATCH_RESULT;
const versionsJson = process.env.LA_PYRIGHT_PATCH_VERSIONS;
if (resultPath && versionsJson) {
  const versions = JSON.parse(versionsJson);
  const compile = Module.prototype._compile;
  Module.prototype._compile = function (content, filename, ...rest) {
    const isBundle = path.basename(filename) === 'pyright.js' && path.basename(path.dirname(filename)) === 'dist';
    return compile.call(this, isBundle ? patch(content, resultPath, versions) : content, filename, ...rest);
  };
}

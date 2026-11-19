'use strict';
// Removes the microsoft/pyright#11919 condition from basedpyright's CLI and language-server bundles as Node compiles them, in every
// thread; delete this file and its wiring once basedpyright ships the fix.
const fs = require('node:fs');
const path = require('node:path');
const Module = require('node:module');
const { isMainThread } = require('node:worker_threads');

const CONDITION = '!isGetTypeFromCodeFlowPending(referenceKeyWithSymbolId) &&';
const REPLACEMENT = 'true &&';
const BUNDLES = new Set(['pyright.js', 'pyright-langserver.js']);
const VERSION_MODULE = /"\.\.\/pyright-internal\/src\/version\.json"\(module\) \{\s*"use strict";\s*module\.exports = "([^"]*)"/;

// A failure overwrites any result; `patched` never replaces one, so a failure in any checker process of the run stands.
function record(resultPath, outcome, version, count) {
  if (!isMainThread) return;
  const tmp = path.join(path.dirname(resultPath), `.${path.basename(resultPath)}.${process.pid}.tmp`);
  fs.writeFileSync(tmp, JSON.stringify({ outcome, version, count }));
  if (outcome !== 'patched') {
    fs.renameSync(tmp, resultPath);
    return;
  }
  try {
    fs.linkSync(tmp, resultPath);
  } catch (err) {
    if (err.code !== 'EEXIST') throw err;
  } finally {
    fs.unlinkSync(tmp);
  }
}

function outcomeOf(version, count, versions) {
  if (!versions.includes(version)) return 'unverified';
  return count === 1 ? 'patched' : 'mismatch';
}

function patch(source, resultPath, versions) {
  const found = VERSION_MODULE.exec(source);
  if (!found) return source;
  const version = found[1];
  const count = source.split(CONDITION).length - 1;
  const outcome = outcomeOf(version, count, versions);
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
    const isBundle = BUNDLES.has(path.basename(filename)) && path.basename(path.dirname(filename)) === 'dist';
    return compile.call(this, isBundle ? patch(content, resultPath, versions) : content, filename, ...rest);
  };
}

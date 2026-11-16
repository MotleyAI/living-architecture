'use strict';
// Adds the `la.exportOccurrences` command to basedpyright's language server as Node compiles its bundle: one request
// answers, from the program in-process, every occurrence of a set of names in a set of files and a batch of position
// facts, each as the definition and hover requests would. Loaded only by dr-refactor's language server.
const fs = require('node:fs');
const path = require('node:path');
const Module = require('node:module');
const { isMainThread } = require('node:worker_threads');

const COMMAND = 'la.exportOccurrences';
const BUNDLE = 'pyright-langserver.js';
const VERSION_MODULE = /"\.\.\/pyright-internal\/src\/version\.json"\(module\) \{\s*"use strict";\s*module\.exports = "([^"]*)"/;
const CONSTRUCTOR = 'constructor(ls) {\n        this._createStub = new createTypeStub_1.CreateTypeStubCommand(ls);';
const DISPATCH = "            default: {\n                return new vscode_languageserver_1.ResponseError(1, 'Unsupported command');";
const ANCHORS = [
  [CONSTRUCTOR, 'constructor(ls) {\n        this.__laServer = ls;\n        this._createStub = new createTypeStub_1.CreateTypeStubCommand(ls);'],
  [DISPATCH, `            case "${COMMAND}": {\n                return globalThis.__laExportOccurrences(this.__laServer, cmdParams, token, __webpack_require__);\n            }\n${DISPATCH}`],
];

const NODE = { Argument: 1, Class: 10, Decorator: 16, ImportAs: 24, ImportFromAs: 26, Index: 27, Function: 31,
  MemberAccess: 35, Module: 36, ModuleName: 37, Name: 38, Parameter: 41, StringList: 48, String: 49, TypeAnnotation: 54 };
const HOVER = /^\([\p{L}\p{N}_ ]+\) [\p{L}\p{N}_.]+: ([\s\S]*)$/u;

// A failure overwrites any result; `patched` never replaces one.
function record(resultPath, outcome, version) {
  if (!isMainThread) return;
  const tmp = path.join(path.dirname(resultPath), `.${path.basename(resultPath)}.${process.pid}.tmp`);
  fs.writeFileSync(tmp, JSON.stringify({ outcome, version }));
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

function patch(source, resultPath, versions) {
  const found = VERSION_MODULE.exec(source);
  if (!found) return source;
  const version = found[1];
  let outcome = 'patched';
  if (!versions.includes(version)) outcome = 'unverified';
  else if (ANCHORS.some(([anchor]) => source.split(anchor).length !== 2)) outcome = 'mismatch';
  record(resultPath, outcome, version);
  if (outcome !== 'patched') process.exit(2);
  return ANCHORS.reduce((text, [anchor, replacement]) => text.replace(anchor, () => replacement), source);
}

// `Unknown` or `Any` when a hover's declared type is, or is a union holding, either.
function hoverType(hover) {
  if (hover == null) return null;
  const m = HOVER.exec(hover.split('\n\n')[0]);
  if (!m) return null;
  const text = m[1];
  const members = [];
  let depth = 0;
  let start = 0;
  for (let i = 0; i < text.length; i++) {
    const char = text[i];
    if (char === '[' || char === '(') depth++;
    else if (char === ']' || char === ')') depth--;
    else if (depth === 0 && text.startsWith(' | ', i)) {
      members.push(text.slice(start, i));
      start = i + 3;
    }
  }
  const all = [...members, text.slice(start)].map((t) => t.trim());
  return ['Unknown', 'Any'].find((kind) => all.includes(kind)) ?? null;
}

class Exporter {
  constructor(ls, workspace, program, req, token) {
    this.ls = ls;
    this.fs = workspace.service.fs;
    this.program = program;
    this.token = token;
    this.nodeInfo = req('../pyright-internal/src/analyzer/analyzerNodeInfo.ts');
    this.walkers = req('../pyright-internal/src/analyzer/parseTreeWalker.ts');
    this.treeUtils = req('../pyright-internal/src/analyzer/parseTreeUtils.ts');
    this.positions = req('../pyright-internal/src/common/positionUtils.ts');
    this.definitionProvider = req('../pyright-internal/src/languageService/definitionProvider.ts');
    this.hoverProvider = req('../pyright-internal/src/languageService/hoverProvider.ts');
    this.reader = this.nodeInfo.getInfoReader(program);
    this.cache = new Map();
    this.followed = new Set();
    this.facts = [];
  }

  memo(key, compute) {
    if (!this.cache.has(key)) this.cache.set(key, compute());
    return this.cache.get(key);
  }

  uri(lsp) {
    return this.ls.convertLspUriStringToUri(lsp);
  }

  parse(uri) {
    return this.memo(`parse ${uri.key}`, () => this.program.getParseResults(uri));
  }

  position(uri, offset) {
    const parsed = this.parse(uri);
    return parsed ? this.positions.convertOffsetToPosition(offset, parsed.tokenizerOutput.lines) : undefined;
  }

  locations(found) {
    return (found ?? [])
      .filter((loc) => this.ls.canNavigateToFile(loc.uri, this.fs))
      .map((loc) => ({ uri: this.ls.convertUriToLspUriString(this.fs, loc.uri), range: loc.range }));
  }

  definition(uri, position) {
    return this.memo(`def ${uri.key} ${position.line}:${position.character}`, () => this.locations(
      new this.definitionProvider.DefinitionProvider(this.program, uri, position,
        this.definitionProvider.DefinitionFilter.All, this.token).getDefinitions()));
  }

  typeDefinition(uri, position) {
    return this.memo(`type ${uri.key} ${position.line}:${position.character}`, () => this.locations(
      new this.definitionProvider.TypeDefinitionProvider(this.program, uri, position, this.token).getDefinitions()));
  }

  hover(uri, position) {
    return this.memo(`hover ${uri.key} ${position.line}:${position.character}`, () => {
      const found = new this.hoverProvider.HoverProvider(this.program, uri, position, this.ls.client.hoverContentFormat,
        this.token).getHover();
      const contents = found?.contents;
      if (contents == null) return null;
      if (typeof contents === 'string') return contents;
      if (Array.isArray(contents)) return contents.map((c) => (typeof c === 'string' ? c : String(c.value ?? ''))).join('\n');
      return String(contents.value ?? '');
    });
  }

  verdict(uri, position) {
    return hoverType(this.hover(uri, position));
  }

  // The receiver verdict of the member access whose member name is `member`: a name or attribute receiver hovered, any
  // other read from the access when no declaration of the member is itself untyped.
  access(uri, member) {
    const receiver = member.parent.d.leftExpr;
    if (receiver.nodeType === NODE.Name || receiver.nodeType === NODE.MemberAccess) {
      const name = receiver.nodeType === NODE.Name ? receiver : receiver.d.member;
      return this.verdict(uri, this.position(uri, name.start));
    }
    const at = this.position(uri, member.start);
    const kind = this.verdict(uri, at);
    if (kind === null) return null;
    const declared = this.definition(uri, at).some((d) => this.verdict(this.uri(d.uri), d.range.start) !== null);
    return declared ? null : kind;
  }

  nodeAt(uri, position) {
    const parsed = this.parse(uri);
    if (!parsed) return undefined;
    const offset = this.positions.convertPositionToOffset(position, parsed.tokenizerOutput.lines);
    if (offset === undefined) return undefined;
    const node = this.treeUtils.findNodeByOffset(parsed.parserOutput.parseTree, offset, this.reader);
    return node?.nodeType === NODE.Name && node.start === offset ? node : undefined;
  }

  kind(node) {
    const parent = node.parent;
    if (parent?.nodeType === NODE.MemberAccess && parent.d.member === node) return 'member';
    if (parent?.nodeType === NODE.Argument && parent.d.name === node) return 'keyword';
    if (parent?.nodeType === NODE.ImportFromAs) return parent.d.alias === node ? 'alias' : 'import';
    if (parent?.nodeType === NODE.ImportAs && parent.d.alias === node) return 'alias';
    if (parent?.nodeType === NODE.ModuleName) return 'module';
    for (let up = parent; up; up = up.parent) {
      if (up.nodeType === NODE.StringList || up.nodeType === NODE.String) return 'forward-reference';
    }
    return 'name';
  }

  occurrences(lsp, names, out) {
    const uri = this.uri(lsp);
    const parsed = this.parse(uri);
    if (!parsed) return;
    const lines = parsed.tokenizerOutput.lines;
    const range = (node) => this.positions.convertTextRangeToRange(node, lines);
    const tree = parsed.parserOutput.parseTree;
    const dunderAll = new Set(this.nodeInfo.getDunderAllInfo(tree, this.reader)?.stringNodes ?? []);
    const exporter = this;
    const names_ = names;
    const walker = new (class extends this.walkers.ParseTreeWalker {
      visitName(node) {
        if (names_.has(node.d.value)) {
          const kind = exporter.kind(node);
          const at = range(node).start;
          out.push({ uri: lsp, range: range(node), name: node.d.value, kind, declarations: exporter.definition(uri, at),
            receiver: kind === 'member' ? exporter.access(uri, node) : null });
        }
        return true;
      }

      visitString(node) {
        if (dunderAll.has(node) && names_.has(node.d.value) && node.d.token.escapedValue === node.d.value) {
          out.push({ uri: lsp, range: range(exporter.treeUtils.getStringNodeValueRange(node)), name: node.d.value, kind: 'all-entry',
            declarations: exporter.moduleDeclarations(tree, node.d.value), receiver: null });
        }
        return true;
      }
    })(this.reader);
    walker.walk(tree);
  }

  moduleDeclarations(tree, name) {
    const scope = this.nodeInfo.getScope(tree, this.reader);
    const symbol = scope?.lookUpSymbol(name);
    const out = [];
    for (const decl of symbol?.getDeclarations() ?? []) {
      const resolved = this.program.evaluator.resolveAliasDeclaration(decl, true);
      if (resolved && resolved.uri && !resolved.uri.isEmpty()) out.push({ uri: resolved.uri, range: resolved.range });
    }
    return this.locations(out);
  }

  // The definitions la's rules ask about next, from a definition landing on a class, function or parameter.
  follow(location) {
    const key = `${location.uri} ${location.range.start.line}:${location.range.start.character}`;
    if (this.followed.has(key)) return;
    this.followed.add(key);
    const uri = this.uri(location.uri);
    const node = this.nodeAt(uri, location.range.start);
    const parent = node?.parent;
    if (!parent) return;
    if (parent.nodeType === NODE.Class && parent.d.name === node) {
      for (const arg of parent.d.arguments) {
        if (!arg.d.name && arg.d.argCategory === 0) this.followName(uri, arg.d.valueExpr);
      }
      for (const statement of parent.d.suite.d.statements) {
        for (const item of statement.d?.statements ?? []) {
          const annotation = item.nodeType === NODE.TypeAnnotation ? item.d.annotation : item.d?.leftExpr?.nodeType === NODE.TypeAnnotation ? item.d.leftExpr.d.annotation : undefined;
          if (annotation) this.followNames(uri, annotation);
        }
      }
    } else if (parent.nodeType === NODE.Function && parent.d.name === node) {
      this.followFunction(uri, parent);
    } else if (parent.nodeType === NODE.Parameter && parent.d.name === node) {
      if (parent.parent?.nodeType === NODE.Function) this.followFunction(uri, parent.parent);
    }
  }

  followFunction(uri, fn) {
    for (const decorator of fn.d.decorators) this.followName(uri, decorator.d.expr);
    for (const param of fn.d.params) {
      const annotation = param.d.annotation ?? param.d.annotationComment;
      if (annotation) this.followNames(uri, annotation);
    }
  }

  followName(uri, expr) {
    const target = expr?.nodeType === NODE.Index ? expr.d.leftExpr : expr;
    const name = target?.nodeType === NODE.Name ? target : target?.nodeType === NODE.MemberAccess ? target.d.member : undefined;
    if (name) this.fact(uri, this.position(uri, name.start), ['definition']);
  }

  followNames(uri, expr) {
    const visit = (node) => {
      if (!node) return;
      if (node.nodeType === NODE.Name) this.fact(uri, this.position(uri, node.start), ['definition']);
      else if (node.nodeType === NODE.MemberAccess) {
        visit(node.d.leftExpr);
        this.fact(uri, this.position(uri, node.d.member.start), ['definition']);
        return;
      }
      if (node.nodeType !== NODE.MemberAccess) {
        for (const child of this.walkers.getChildNodes(node, (n) => this.nodeInfo.getStringAnnotation(n, this.reader))) visit(child);
      }
    };
    visit(expr);
  }

  answer(uri, position, kinds) {
    const lsp = this.ls.convertUriToLspUriString(this.fs, uri);
    const answer = { uri: lsp, position };
    if (kinds.includes('definition')) answer.definition = this.definition(uri, position);
    if (kinds.includes('typeDefinition')) answer.typeDefinition = this.typeDefinition(uri, position);
    if (kinds.includes('verdict')) answer.verdict = this.verdict(uri, position);
    if (kinds.includes('access')) {
      const node = this.nodeAt(uri, position);
      answer.access = node?.parent?.nodeType === NODE.MemberAccess && node.parent.d.member === node ? this.access(uri, node) : null;
    }
    for (const found of [...(answer.definition ?? []), ...(answer.typeDefinition ?? [])]) this.follow(found);
    return answer;
  }

  // A definition fact the export adds on its own, once per position.
  fact(uri, position, kinds) {
    if (!position) return;
    const key = `fact ${uri.key} ${position.line}:${position.character}`;
    if (this.cache.has(key)) return;
    this.cache.set(key, true);
    this.facts.push(this.answer(uri, position, kinds));
  }

  run(request) {
    const names = new Set(request.names ?? []);
    const occurrences = [];
    if (names.size) for (const lsp of request.files ?? []) this.occurrences(lsp, names, occurrences);
    const answers = (request.facts ?? []).map((q) => this.answer(this.uri(q.uri), q.position, q.kinds));
    return { occurrences, answers, followed: this.facts };
  }
}

async function exportOccurrences(ls, params, token, req) {
  const request = (params.arguments ?? [])[0] ?? {};
  const files = [...(request.files ?? []), ...(request.facts ?? []).map((f) => f.uri)];
  if (!files.length) return { occurrences: [], answers: [], followed: [] };
  const workspaces = new Set();
  let workspace;
  for (const lsp of files) {
    workspace = await ls.getWorkspaceForFile(ls.convertLspUriStringToUri(lsp));
    workspaces.add(workspace);
  }
  if (workspaces.size !== 1) throw new Error('the requested files span several workspaces');
  return workspace.service.run((program) => new Exporter(ls, workspace, program, req, token).run(request), token);
}

const resultPath = process.env.LA_PYRIGHT_EXPORT_RESULT;
const versionsJson = process.env.LA_PYRIGHT_EXPORT_VERSIONS;
if (resultPath && versionsJson) {
  const versions = JSON.parse(versionsJson);
  globalThis.__laExportOccurrences = exportOccurrences;
  const compile = Module.prototype._compile;
  Module.prototype._compile = function (content, filename, ...rest) {
    const isBundle = path.basename(filename) === BUNDLE && path.basename(path.dirname(filename)) === 'dist';
    return compile.call(this, isBundle ? patch(content, resultPath, versions) : content, filename, ...rest);
  };
}

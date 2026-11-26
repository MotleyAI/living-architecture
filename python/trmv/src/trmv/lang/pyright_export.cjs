'use strict';
// Adds the `la.exportOccurrences` command to basedpyright's language server as Node compiles its bundle: one request
// answers, from the program in-process, every occurrence of a set of names in a set of files and a batch of position
// facts, each as the definition and hover requests would. Loaded only by trmv-refactor's language server.
const fs = require('node:fs');
const path = require('node:path');
const Module = require('node:module');
const { isMainThread } = require('node:worker_threads');

const COMMAND = 'la.exportOccurrences';
const BUNDLE = 'pyright-langserver.js';
const VERSION_MODULE = /"\.\.\/pyright-internal\/src\/version\.json"\(module\) \{\s*"use strict";\s*module\.exports = "([^"]*)"/;
const CONSTRUCTOR = 'constructor(ls) {\n        this._createStub = new createTypeStub_1.CreateTypeStubCommand(ls);';
const DISPATCH = "            default: {\n                return new vscode_languageserver_1.ResponseError(1, 'Unsupported command');";
const AMBIENT = '    commandLineOptions.languageServerSettings.enableAmbientAnalysis = trackFiles;\n';
const ANCHORS = [
  [AMBIENT, '    commandLineOptions.languageServerSettings.enableAmbientAnalysis = false;\n'],
  [CONSTRUCTOR, 'constructor(ls) {\n        this.__laServer = ls;\n        this._createStub = new createTypeStub_1.CreateTypeStubCommand(ls);'],
  [DISPATCH, `            case "${COMMAND}": {\n                return globalThis.__laExportOccurrences(this.__laServer, cmdParams, token, __webpack_require__);\n            }\n${DISPATCH}`],
];

const NODE = { Argument: 1, Call: 9, Class: 10, Decorator: 16, ImportAs: 24, FormatString: 30, ImportFromAs: 26, Index: 27, Function: 31,
  MemberAccess: 35, Module: 36, ModuleName: 37, Name: 38, Parameter: 41, StringList: 48, String: 49, TypeAnnotation: 54 };
const ALIAS_DECLARATION = 8;
const VERDICTS = ['Unknown', 'Any', 'Never'];
const PARAM_KEYWORD = new Set([1, 2]);
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

// `Unknown`, `Any` or `Never` when a hover's declared type is, or is a union holding, one of them.
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
  const all = new Set([...members, text.slice(start)].map((t) => t.trim()));
  return VERDICTS.find((kind) => all.has(kind)) ?? null;
}

// The annotation of a class-body statement `x: T` or `x: T = v`.
function annotationOf(item) {
  if (item.nodeType === NODE.TypeAnnotation) return item.d.annotation;
  const left = item.d?.leftExpr;
  return left?.nodeType === NODE.TypeAnnotation ? left.d.annotation : undefined;
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
    this.types = req('../pyright-internal/src/analyzer/types.ts');
    this.typeUtils = req('../pyright-internal/src/analyzer/typeUtils.ts');
    this.constructors = req('../pyright-internal/src/analyzer/constructors.ts');
    this.parameters = req('../pyright-internal/src/analyzer/parameterUtils.ts');
    this.reader = this.nodeInfo.getInfoReader(program);
    this.cache = new Map();
    this.followed = new Set();
    this.facts = [];
    this.members = [];
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

  // `Never` only as the checker evaluates it: a class of that name hovers alike, and `NoReturn` is one.
  verdict(uri, position) {
    const hover = this.hover(uri, position);
    const kind = hoverType(hover);
    if (kind !== 'Never' && !(kind === null && hover?.includes('NoReturn'))) return kind;
    const node = this.nodeAt(uri, position);
    return node && this.typeVerdict(node) === 'Never' ? 'Never' : null;
  }

  // The verdict of an expression's type as the checker evaluates it: the first of `Unknown`, `Any` and `Never` it is
  // or, as a union, holds.
  typeVerdict(node) {
    const type = this.program.evaluator.getType(node);
    if (!type) return null;
    const found = new Set();
    this.typeUtils.doForEachSubtype(type, (sub) => {
      if (this.types.isUnknown(sub)) found.add('Unknown');
      else if (this.types.isAny(sub)) found.add('Any');
      else if (this.types.isNever(sub)) found.add('Never');
    });
    return VERDICTS.find((kind) => found.has(kind)) ?? null;
  }

  // The receiver verdict of the member access whose member name is `member`: a name or attribute receiver hovered, any
  // other read from the access when no declaration of the member is itself untyped, else `Never` when its type is.
  access(uri, member) {
    const receiver = member.parent.d.leftExpr;
    if (receiver.nodeType === NODE.Name || receiver.nodeType === NODE.MemberAccess) {
      const name = receiver.nodeType === NODE.Name ? receiver : receiver.d.member;
      return this.verdict(uri, this.position(uri, name.start));
    }
    const at = this.position(uri, member.start);
    const kind = this.verdict(uri, at);
    if (kind === null) return this.typeVerdict(receiver) === 'Never' ? 'Never' : null;
    const declared = this.definition(uri, at).some((d) => this.verdict(this.uri(d.uri), d.range.start) !== null);
    return declared ? null : kind;
  }

  // The call a name belongs to as one of its keywords or as its callee's name.
  callOf(node) {
    const parent = node?.parent;
    if (parent?.nodeType === NODE.Argument && parent.d.name === node) return parent.parent?.nodeType === NODE.Call ? parent.parent : undefined;
    const callee = parent?.nodeType === NODE.MemberAccess && parent.d.member === node ? parent : node;
    return callee?.parent?.nodeType === NODE.Call && callee.parent.d.leftExpr === callee ? callee.parent : undefined;
  }

  // The names each callable alternative of `type` binds by keyword: one list per overload and per union member, a
  // class by its constructors and an instance by its `__call__`.
  alternatives(node, type, depth = 0) {
    const out = [];
    this.typeUtils.doForEachSubtype(this.program.evaluator.makeTopLevelTypeVarsConcrete(type), (sub) => {
      let inner;
      if (this.types.isFunction(sub)) {
        const details = this.parameters.getParamListDetails(sub);
        out.push(details.params.filter((p) => p.param.category === 0 && PARAM_KEYWORD.has(p.kind)).map((p) => p.param.name));
        return;
      }
      if (this.types.isOverloaded(sub)) {
        for (const overload of this.types.OverloadedType.getOverloads(sub)) out.push(...this.alternatives(node, overload, depth + 1));
        return;
      }
      if (depth < 4 && this.types.isInstantiableClass(sub)) {
        inner = this.constructors.createFunctionFromConstructor(this.program.evaluator, sub);
      } else if (depth < 4 && this.types.isClassInstance(sub)) {
        inner = this.constructors.getBoundCallMethod(this.program.evaluator, node, sub)?.type;
      }
      if (inner) out.push(...this.alternatives(node, inner, depth + 1));
      else out.push([]);
    });
    return out;
  }

  // The signature fact of the call a keyword or callee name belongs to.
  signature(uri, position) {
    const call = this.callOf(this.nodeAt(uri, position));
    if (!call) return { alternatives: [], callee: null };
    const type = this.program.evaluator.getType(call.d.leftExpr);
    return { alternatives: type ? this.alternatives(call.d.leftExpr, type) : [], callee: this.typeVerdict(call.d.leftExpr) };
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
      if (up.nodeType === NODE.FormatString) return 'name';
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
    const onName = (node) => {
      if (!names.has(node.d.value)) return;
      const kind = this.kind(node);
      out.push({ uri: lsp, range: range(node), name: node.d.value, kind, declarations: this.definition(uri, range(node).start),
        bindings: this.bindings(this.program.evaluator.getDeclInfoForNameNode(node)?.decls),
        receiver: kind === 'member' ? this.access(uri, node) : null });
    };
    const onString = (node) => {
      if (!dunderAll.has(node) || !names.has(node.d.value) || node.d.token.escapedValue !== node.d.value) return;
      out.push({ uri: lsp, range: range(this.treeUtils.getStringNodeValueRange(node)), name: node.d.value, kind: 'all-entry',
        declarations: this.moduleDeclarations(tree, node.d.value),
        bindings: this.bindings(this.nodeInfo.getScope(tree, this.reader)?.lookUpSymbol(node.d.value)?.getDeclarations()),
        receiver: null });
    };
    const walker = new (class extends this.walkers.ParseTreeWalker {
      visitName(node) {
        onName(node);
        return true;
      }

      visitString(node) {
        onString(node);
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
      if (resolved?.uri && !resolved.uri.isEmpty()) out.push({ uri: resolved.uri, range: resolved.range });
    }
    return this.locations(out);
  }

  // The `from M import X [as Y]` bindings `decls` pass through on the way to their final declarations, in order, each
  // as the span of the name it binds.
  bindings(decls) {
    const out = [];
    const seen = new Set();
    const frontier = [...(decls ?? [])];
    while (frontier.length) {
      const decl = frontier.shift();
      if (decl?.type !== ALIAS_DECLARATION || decl.node?.nodeType !== NODE.ImportFromAs || seen.has(decl)) continue;
      seen.add(decl);
      const file = this.treeUtils.getFileInfoFromNode(decl.node, this.reader)?.fileUri;
      if (file) out.push({ uri: file, range: decl.range });
      if (!decl.loadSymbolsFromPath || decl.uri.isEmpty() || !decl.symbolName) continue;
      const symbol = this.program.lookUpImport(decl.uri)?.symbolTable.get(decl.symbolName);
      frontier.push(...(symbol?.getDeclarations() ?? []));
    }
    return this.locations(out);
  }

  // The definitions la's rules ask about next, from a definition landing on a class, function or parameter in user code.
  follow(location) {
    const key = `${location.uri} ${location.range.start.line}:${location.range.start.character}`;
    if (this.followed.has(key)) return;
    this.followed.add(key);
    const uri = this.uri(location.uri);
    const info = this.program.getSourceFileInfo(uri);
    if (!info || info.isThirdPartyImport || info.isTypeshedFile) return;
    const node = this.nodeAt(uri, location.range.start);
    const parent = node?.parent;
    if (!parent || parent.d?.name !== node) return;
    if (parent.nodeType === NODE.Class) this.followClass(uri, parent);
    else if (parent.nodeType === NODE.Function) this.followFunction(uri, parent);
    else if (parent.nodeType === NODE.Parameter && parent.parent?.nodeType === NODE.Function) {
      this.followFunction(uri, parent.parent);
    }
  }

  followClass(uri, cls) {
    for (const arg of cls.d.arguments) {
      if (!arg.d.name && arg.d.argCategory === 0) this.followName(uri, arg.d.valueExpr);
    }
    for (const statement of cls.d.suite.d.statements) {
      for (const item of statement.d?.statements ?? []) {
        const annotation = annotationOf(item);
        if (annotation) this.followNames(uri, annotation);
      }
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
    let name;
    if (target?.nodeType === NODE.Name) name = target;
    else if (target?.nodeType === NODE.MemberAccess) name = target.d.member;
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

  // A class's MRO as the checker resolves it, each class by its name, and which of the run's new member names a class
  // of it outside the project declares.
  classFacts(uri, position) {
    const node = this.nodeAt(uri, position);
    const cls = node?.parent;
    if (cls?.nodeType !== NODE.Class || cls.d.name !== node) return { mro: [], members: [] };
    const mro = [];
    const members = new Set();
    for (const base of this.program.evaluator.getTypeOfClass(cls)?.classType?.shared.mro.slice(1) ?? []) {
      const decl = base?.shared?.declaration;
      if (!decl?.uri || !decl.range) continue;
      mro.push({ uri: decl.uri, range: decl.range });
      const info = this.program.getSourceFileInfo(decl.uri);
      if (info && !info.isThirdPartyImport && !info.isTypeshedFile) continue;
      for (const name of this.members) if (base.shared.fields?.has(name)) members.add(name);
    }
    return { mro: this.locations(mro), members: [...members] };
  }

  answer(uri, position, kinds) {
    const lsp = this.ls.convertUriToLspUriString(this.fs, uri);
    const answer = { uri: lsp, position };
    if (kinds.includes('definition')) answer.definition = this.definition(uri, position);
    if (kinds.includes('typeDefinition')) answer.typeDefinition = this.typeDefinition(uri, position);
    if (kinds.includes('verdict')) answer.verdict = this.verdict(uri, position);
    if (kinds.includes('class')) answer.class = this.classFacts(uri, position);
    if (kinds.includes('signature')) answer.signature = this.signature(uri, position);
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
    this.members = request.members ?? [];
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
  const workspaces = new Set(await Promise.all(files.map((lsp) => ls.getWorkspaceForFile(ls.convertLspUriStringToUri(lsp)))));
  if (workspaces.size !== 1) throw new Error('the requested files span several workspaces');
  const [workspace] = workspaces;
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

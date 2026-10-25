#!/usr/bin/env node
/**
 * 前端跳转图的静态校验。
 *
 * 做三件事：
 *   1. 从 App.tsx 解出全部路由（含嵌套与 index 路由），得到「点」的集合；
 *   2. 从所有 tsx 里解出 `to="..."` / `to={`...`}` / nav("...") 这类静态跳转，得到「边」的集合；
 *   3. 断言：① 每条静态边都落在某条路由上（无死链）② 每条路由都至少有一条入边（无孤岛）
 *      ③ 报告每页的入/出边数，便于看出跳转是不是单行道。
 *
 * 路由用 AST 解（App.tsx 是嵌套 JSX，正则会把子路由的 relative path 当成绝对路径）。
 * 出边用文本扫描——跳转目标的字面量形式有限，不必上 AST。
 *
 * 用法：node scripts/nav-graph.mjs [--self-test] [--strict]
 *   --self-test  先跑内置用例，验证匹配器本身正确
 *   --strict     孤岛也算失败（默认只警告）
 */
import { readFileSync, readdirSync, statSync, existsSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import ts from "typescript";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
const SRC = join(ROOT, "src");
const ARGS = new Set(process.argv.slice(2));

/** 这些路由不需要入边：应用入口与兜底 */
const ENTRY_ROUTES = new Set(["/"]);
/** 只由重定向/外部进入的路由，允许 0 入边 */
const EXTERNAL_ALLOWED = new Set([
  "/login", "/register", "/forgot-password", "/reset-password", "/verify-email", "/terms", "/privacy",
  // 旧地址兼容：只由外部书签进入，站内已无出口
  "/scenario-challenges/:id",
]);
/**
 * 这些路由真实可达，但目标 URL 由代码拼出来（pathOf(kind, id)），静态扫描看不到。
 * 一旦改成字面量跳转，请把它们从这里删掉，让校验重新覆盖。
 */
const DYNAMIC_ROUTES = new Set([
  "/yiwenlu/characters/:id", // Yiwenlu.tsx 的 pathOf("character", id)
  "/yiwenlu/abilities/:id",  // Yiwenlu.tsx 的 pathOf("ability", id)
]);

// ─────────────────────────── 路由抽取 ───────────────────────────

/** 取 element 表达式里最内层的组件名：<RequireAuth><Yiwenlu /></RequireAuth> → Yiwenlu */
function elementComponentName(node, sf) {
  if (!node) return null;
  if (ts.isJsxElement(node) || ts.isJsxSelfClosingElement(node)) {
    const tag = ts.isJsxElement(node) ? node.openingElement.tagName : node.tagName;
    // 优先看子元素（被守卫包裹的情况）
    if (ts.isJsxElement(node)) {
      const inner = node.children.find((c) => ts.isJsxElement(c) || ts.isJsxSelfClosingElement(c));
      if (inner) {
        const n = elementComponentName(inner, sf);
        if (n && !/^Require|^Navigate/.test(n)) return n;
      }
    }
    return tag.getText(sf);
  }
  return null;
}

/** 拼父子路径。子路由的 relative path 以父路径为前缀 */
function joinPath(parent, child) {
  if (!child) return parent || "/";
  if (child.startsWith("/")) return child;
  const base = parent === "/" ? "" : parent.replace(/\/$/, "");
  return base + "/" + child;
}

function readRoutes() {
  const file = join(SRC, "App.tsx");
  const sf = ts.createSourceFile(file, readFileSync(file, "utf8"), ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
  const routes = [];
  const redirects = [];

  function visit(node, parentPath) {
    if (ts.isJsxElement(node) || ts.isJsxSelfClosingElement(node)) {
      const tag = ts.isJsxElement(node) ? node.openingElement.tagName.getText(sf) : node.tagName.getText(sf);
      const attrs = ts.isJsxElement(node) ? node.openingElement.attributes : node.attributes;

      if (tag === "Route") {
        let pathAttr = null, isIndex = false, elementNode = null;
        for (const a of attrs.properties) {
          if (!ts.isJsxAttribute(a)) continue;
          const name = a.name.getText(sf);
          if (name === "path" && a.initializer) pathAttr = a.initializer.getText(sf).replace(/^["'`]|["'`]$/g, "");
          if (name === "index") isIndex = true;
          if (name === "element" && a.initializer && ts.isJsxExpression(a.initializer)) elementNode = a.initializer.expression;
        }
        const full = isIndex ? (parentPath || "/") : joinPath(parentPath, pathAttr);
        const comp = elementComponentName(elementNode, sf);

        if (comp === "Navigate") {
          const to = elementNode && ts.isJsxElement(elementNode)
            ? elementNode.openingElement.attributes.properties
                .filter((x) => ts.isJsxAttribute(x) && x.name.getText(sf) === "to")
                .map((x) => x.initializer.getText(sf).replace(/^\{|\}$/g, "").replace(/^["'`]|["'`]$/g, ""))[0]
            : null;
          redirects.push({ from: full, to });
        } else {
          routes.push({ path: full, component: comp, file: file.replace(ROOT + "\\", "").replace(/\\/g, "/") });
        }
        // 继续下钻子路由
        if (ts.isJsxElement(node)) {
          for (const child of node.children) visit(child, full);
        }
        return;
      }
    }
    ts.forEachChild(node, (c) => visit(c, parentPath));
  }

  const sfRoutes = [];
  function findRoutes(node) {
    if (ts.isJsxElement(node) || ts.isJsxSelfClosingElement(node)) {
      const tag = ts.isJsxElement(node) ? node.openingElement.tagName.getText(sf) : node.tagName.getText(sf);
      if (tag === "Routes") {
        sfRoutes.push(node);
        return;
      }
    }
    ts.forEachChild(node, findRoutes);
  }
  findRoutes(sf);
  for (const r of sfRoutes) {
    if (ts.isJsxElement(r)) for (const c of r.children) visit(c, "");
  }
  return { routes, redirects };
}

// ─────────────────────────── 出边抽取 ───────────────────────────

function walk(dir, acc = []) {
  for (const e of readdirSync(dir)) {
    const p = join(dir, e);
    if (statSync(p).isDirectory()) walk(p, acc);
    else if (/\.tsx?$/.test(e) && !e.endsWith(".d.ts")) acc.push(p);
  }
  return acc;
}

/** 把含 ${...} 的模板转成模式：/a/${x}/b → /a/{{p}}/b */
function templToPattern(raw) {
  return raw.replace(/\$\{[^}]*\}/g, "{{p}}").replace(/\{\{[^}]*\}\}/g, "{{p}}");
}

function readEdges(files) {
  const edges = [];
  for (const f of files) {
    const text = readFileSync(f, "utf8");
    const rel = f.replace(ROOT + "\\", "").replace(/\\/g, "/");
    text.split("\n").forEach((line, i) => {
      const lineNo = i + 1;
      if (/^\s*(\*|\/\/)/.test(line)) return; // 注释行不算

      // to="..." / to={'...'} / to={`...`}
      for (const m of line.matchAll(/\bto=(?:"([^"]*)"|\{\s*"([^"]*)"\s*\}|\{\s*`([^`]*)`\s*\})/g)) {
        const raw = m[1] ?? m[2] ?? m[3];
        if (raw == null || raw.startsWith("${")) continue; // 纯变量目标，静态不可见
        edges.push({ from: rel, line: lineNo, raw, pattern: templToPattern(raw) });
      }
      // 路由表里的对象字面量：{ to: "/admin/users", label: ... }
      for (const m of line.matchAll(/\bto:\s*"([^"]*)"/g)) {
        edges.push({ from: rel, line: lineNo, raw: m[1], pattern: templToPattern(m[1]) });
      }
      // nav("...") / navigate("/...")  (useNavigate 的返回值)
      // 注意不收 go(...)：那是页面内的语义函数（如 go("character", id)），首参不是路径
      for (const m of line.matchAll(/\b(?:nav|navigate)\(\s*(?:"([^"]*)"|`([^`]*)`)/g)) {
        const raw = m[1] ?? m[2];
        if (raw == null || raw.startsWith("${")) continue;
        edges.push({ from: rel, line: lineNo, raw, pattern: templToPattern(raw) });
      }
    });
  }
  return edges;
}

// ─────────────────────────── 匹配 ───────────────────────────

/** 路由路径 → 正则。:param 匹配一段，{{p}} 同理 */
function routeToRegex(path) {
  const body = path
    .split("/")
    .map((seg) => {
      if (seg.startsWith(":")) return "[^/]+";
      if (seg === "{{p}}") return "[^/]+";
      return seg.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    })
    .join("/");
  return new RegExp("^" + body + "/?$");
}

/** 边模式 → 正则（{{p}} 匹配一段） */
function edgeToRegex(pattern) {
  const clean = pattern.split("?")[0].split("#")[0];
  const body = clean
    .split("/")
    .map((seg) => (seg === "{{p}}" ? "[^/]+" : seg.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")))
    .join("/");
  return new RegExp("^" + body + "/?$");
}

function selfTest() {
  const cases = [
    ["/scenarios/:slug", "/scenarios/abc", true],
    ["/scenarios/:slug", "/scenarios/abc/rosters", false],
    ["/scenarios/:slug/rosters/new", "/scenarios/abc/rosters/new", true],
    ["/scenarios/:slug/rosters/new", "/scenarios/abc/rosters/42", false],
    ["/", "/", true],
    ["/admin", "/admin/users", false],
  ];
  let ok = 0;
  for (const [route, target, want] of cases) {
    const got = routeToRegex(route).test(target);
    if (got !== want) {
      console.error(`  self-test FAIL  ${route} vs ${target} → ${got}，预期 ${want}`);
    } else ok++;
  }
  const edgeCases = [
    ["/scenarios/{{p}}/rosters/new", "/scenarios/abc/rosters/new", true],
    ["/scenarios/{{p}}", "/scenarios/abc", true],
    ["/scenarios", "/scenarios/abc", false],
  ];
  for (const [edge, target, want] of edgeCases) {
    const got = edgeToRegex(edge).test(target);
    if (got !== want) {
      console.error(`  self-test FAIL  边 ${edge} vs ${target} → ${got}，预期 ${want}`);
    } else ok++;
  }
  console.log(`self-test: ${ok}/${cases.length + edgeCases.length} 通过`);
  return ok === cases.length + edgeCases.length;
}

// ─────────────────────────── 主流程 ───────────────────────────

if (ARGS.has("--self-test") && !selfTest()) process.exit(1);

const { routes, redirects } = readRoutes();
const files = walk(SRC);
const edges = readEdges(files);

// 去重（同一 from+pattern 只算一条边）
const seen = new Set();
const uniqEdges = edges.filter((e) => {
  const k = e.from + "|" + e.pattern;
  if (seen.has(k)) return false;
  seen.add(k);
  return true;
});

console.log(`\n路由 ${routes.length} 条，重定向 ${redirects.length} 条，静态跳转 ${uniqEdges.length} 处\n`);

// 每条边归到一条路由
const inbound = new Map(routes.map((r) => [r.path, []]));
const dead = [];
for (const e of uniqEdges) {
  // 剥掉 query 与 hash：?run=xx / ?p=xx 只影响页面状态，不改变命中的路由
  const target = e.pattern.split("?")[0].split("#")[0].replace(/\{\{p\}\}/g, "X");
  const hit = routes.filter((r) => routeToRegex(r.path).test(target));
  if (!hit.length) { dead.push(e); continue; }
  for (const r of hit) inbound.get(r.path).push(e);
}

// ── 断言 1：死链 ──
if (dead.length) {
  console.log(`✗ 死链 ${dead.length} 处（跳转目标没有对应路由）：`);
  for (const d of dead) console.log(`    ${d.from}:${d.line}  → ${d.raw}`);
} else {
  console.log("✓ 无死链");
}

// ── 断言 2：孤岛 ──
const orphan = routes.filter((r) => {
  if (ENTRY_ROUTES.has(r.path)) return false;
  if (inbound.get(r.path).length > 0) return false;
  if (redirects.some((x) => x.to && routeToRegex(r.path).test(x.to))) return false;
  if (EXTERNAL_ALLOWED.has(r.path)) return false;
  if (DYNAMIC_ROUTES.has(r.path)) return false;
  return true;
});
if (orphan.length) {
  console.log(`\n${ARGS.has("--strict") ? "✗" : "!"} 孤岛 ${orphan.length} 条（没有任何站内跳转指向）：`);
  for (const o of orphan) console.log(`    ${o.path}   ${o.component ?? ""}`);
} else {
  console.log("✓ 无孤岛");
}

// ── 报表 ──
console.log("\n路由".padEnd(52) + "入边".padStart(5) + "  组件");
for (const r of routes) {
  console.log(r.path.padEnd(52) + String(inbound.get(r.path).length).padStart(5) + "  " + (r.component ?? "-"));
}

const fail = dead.length > 0 || (ARGS.has("--strict") && orphan.length > 0);
console.log("\n" + (fail ? "校验未通过" : "校验通过"));
process.exit(fail ? 1 : 0);

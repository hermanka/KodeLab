const fs = require("node:fs");
const { parse } = require("@babel/parser");
const en = JSON.parse(fs.readFileSync("web/locales/en.json", "utf8"));
const escape = (x) => x.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
const pattern = new RegExp(
  `(?<![\\p{L}\\p{N}_])(?:${Object.keys(en)
    .sort((a, b) => b.length - a.length)
    .map(escape)
    .join("|")})(?![\\p{L}\\p{N}_])`,
  "gu",
);
for (const file of ["web/app.js", "web/core.js", "web/studio.js"]) {
  let source = fs.readFileSync(file, "utf8");
  const edits = [];
  function walk(node, parent, key) {
    if (!node || typeof node !== "object") return;
    if (
      node.type === "TemplateLiteral" &&
      parent?.type !== "TaggedTemplateExpression"
    )
      edits.push([node.start, "ui"]);
    if (
      node.type === "StringLiteral" &&
      parent?.type !== "ImportDeclaration" &&
      key !== "key" &&
      !node.value.includes("#include") &&
      !(parent?.type === "CallExpression" && parent.callee?.name === "tr")
    ) {
      pattern.lastIndex = 0;
      if (node.value.replace(pattern, (k) => en[k]) !== node.value) {
        edits.push([node.start, "tr("], [node.end, ")"]);
      }
    }
    for (const [k, v] of Object.entries(node)) {
      if (["loc", "extra"].includes(k)) continue;
      if (Array.isArray(v)) v.forEach((child) => walk(child, node, k));
      else if (v && typeof v === "object") walk(v, node, k);
    }
  }
  walk(parse(source, { sourceType: "module" }));
  for (const [position, text] of edits.sort((a, b) => b[0] - a[0]))
    source = source.slice(0, position) + text + source.slice(position);
  if (!source.includes('from "./i18n.js"'))
    source =
      'import {ui, tr, localeControl, getLocale, setLocale} from "./i18n.js";\n' +
      source;
  fs.writeFileSync(file, source);
}

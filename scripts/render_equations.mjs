// JSON batch -> self-contained SVG + MathML + source manifest. Offline after setup.
import fs from 'node:fs/promises';
import path from 'node:path';
import os from 'node:os';
import {createRequire} from 'node:module';

const [inputPath, outputDir, ...options] = process.argv.slice(2);
if (!inputPath || !outputDir) throw new Error('Usage: node render_equations.mjs batch.json output-dir [--tool-dir DIR] [--png]');
const option = flag => options.includes(flag) ? options[options.indexOf(flag) + 1] : undefined;
const toolDir = path.resolve(option('--tool-dir') || process.env.LITERATURE_READER_MATH_DIR || path.join(os.homedir(), '.cache/literature-reader/mathjax'));
const requireMath = createRequire(path.join(toolDir, 'package.json'));
const {mathjax} = requireMath('@mathjax/src/js/mathjax.js');
const {TeX} = requireMath('@mathjax/src/js/input/tex.js');
const {SVG} = requireMath('@mathjax/src/js/output/svg.js');
const {liteAdaptor} = requireMath('@mathjax/src/js/adaptors/liteAdaptor.js');
const {RegisterHTMLHandler} = requireMath('@mathjax/src/js/handlers/html.js');
const {SerializedMmlVisitor} = requireMath('@mathjax/src/js/core/MmlTree/SerializedMmlVisitor.js');
const {STATE} = requireMath('@mathjax/src/js/core/MathItem.js');
requireMath('@mathjax/src/js/util/asyncLoad/node.js');
requireMath('@mathjax/src/js/input/tex/base/BaseConfiguration.js');
requireMath('@mathjax/src/js/input/tex/ams/AmsConfiguration.js');
requireMath('@mathjax/src/js/input/tex/newcommand/NewcommandConfiguration.js');
requireMath('@mathjax/src/js/input/tex/boldsymbol/BoldsymbolConfiguration.js');

const batch = JSON.parse(await fs.readFile(inputPath, 'utf8'));
if (!Array.isArray(batch) || !batch.length) throw new Error('Expected a nonempty array of {id,latex,fontSizePx?,color?,source?}.');
const ids = new Set();
for (const e of batch) {
  if (!/^[a-zA-Z0-9-]+$/.test(e.id) || ids.has(e.id) || typeof e.latex !== 'string' || !e.latex.trim()) throw new Error('Invalid/duplicate equation id or missing LaTeX.');
  ids.add(e.id);
  if (e.color && !/^#[0-9a-f]{6}$/i.test(e.color)) throw new Error('Color must be #RRGGBB.');
  if (e.fontSizePx !== undefined && !(e.fontSizePx > 0 && e.fontSizePx <= 200)) throw new Error('Invalid font size.');
}
const adaptor = liteAdaptor();
RegisterHTMLHandler(adaptor);
const tex = new TeX({packages:['base','ams','newcommand','boldsymbol'], formatError(_jax,error){throw error;}});
const svgJax = new SVG({fontCache:'none'});
const doc = mathjax.document('', {InputJax:tex,OutputJax:svgJax});
const visitor = new SerializedMmlVisitor();
let sharp;
if (options.includes('--png')) {
  const runtimeModules = process.env.RUNTIME_NODE_MODULES;
  sharp = runtimeModules ? createRequire(path.join(runtimeModules, '__equation_runtime__.cjs'))('sharp') : requireMath('sharp');
}
await fs.mkdir(outputDir,{recursive:true});
const manifest=[];
for (const e of batch) {
  const em = e.fontSizePx || 32;
  const config={display:true,em,ex:em/2,containerWidth:1200};
  const node=await doc.convertPromise(e.latex,config);
  const svg=adaptor.tags(node,'svg')[0];
  const viewBox=adaptor.getAttribute(svg,'viewBox').trim().split(/\s+/).map(Number);
  const width=viewBox[2]*em/1000, height=viewBox[3]*em/1000;
  if (!(width>0 && height>0)) throw new Error(`Empty equation: ${e.id}`);
  adaptor.setAttribute(svg,'width',`${width}px`);
  adaptor.setAttribute(svg,'height',`${height}px`);
  adaptor.setAttribute(svg,'style',`color:${e.color||'#000000'};`);
  const serialized=adaptor.outerHTML(svg).replaceAll('currentColor',e.color||'#000000');
  if (/data-mjx-error|<merror|<text(?:\s|>)/.test(serialized)) throw new Error(`Error or font-dependent text in equation ${e.id}; inspect input.`);
  const basename=path.join(outputDir,e.id);
  await fs.writeFile(`${basename}.svg`,serialized);
  const mml=doc.convert(e.latex,{...config,end:STATE.CONVERT});
  await fs.writeFile(`${basename}.mml`,visitor.visitTree(mml,doc));
  if (sharp) await sharp(Buffer.from(serialized),{density:384}).flatten({background:'#ffffff'}).png().toFile(`${basename}.png`);
  manifest.push({...e,widthPx:width,heightPx:height,svg:`${e.id}.svg`,mathml:`${e.id}.mml`,...(sharp?{png:`${e.id}.png`}:{}),renderer:mathjax.version,editableAsEquation:false});
}
await fs.writeFile(path.join(outputDir,'equations-manifest.json'),JSON.stringify(manifest,null,2)+'\n');
console.log(JSON.stringify({rendered:manifest.length,renderer:mathjax.version,outputDir:path.resolve(outputDir)}));

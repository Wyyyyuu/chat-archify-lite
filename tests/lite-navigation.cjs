// Small in-process DOM model for portable Lite behavior checks. This is not a real browser.
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const assert = require('node:assert/strict');

const htmlPath = process.argv[2] && path.resolve(process.argv[2]);
if (!htmlPath || !fs.existsSync(htmlPath)) throw new Error('Usage: node tests/lite-navigation.cjs <packaged-lite.html>');
const page = fs.readFileSync(htmlPath, 'utf8');
const payloadMatch = page.match(/<script type="application\/json" id="lite-data">([\s\S]*?)<\/script>/);
assert.ok(payloadMatch, 'Lite package has a JSON payload');
const payload = JSON.parse(payloadMatch[1]);
assert.equal(payload.edition, 'lite');
assert.equal(page.includes('蓝鲸书签'), false, 'the unembedded fourth attachment body is absent');

let activeDocument = null;
class Element {
  constructor(tag) {
    this.tagName = tag.toLowerCase(); this.children = []; this.parentElement = null; this.dataset = {}; this.attrs = {}; this.listeners = {};
    this.style = {}; this._text = ''; this.className = ''; this.hidden = false; this.scrollTop = 0;
    this.classList = {
      add: (...names) => { for (const name of names) if (!this.classList.contains(name)) this.className = [this.className, name].filter(Boolean).join(' '); },
      remove: (...names) => { this.className = this.className.split(/\s+/).filter(name => name && !names.includes(name)).join(' '); },
      contains: name => this.className.split(/\s+/).includes(name),
      toggle: (name, force) => { const add = force === undefined ? !this.classList.contains(name) : Boolean(force); if (add) this.classList.add(name); else this.classList.remove(name); return add; }
    };
  }
  get id() { return this._id || ''; } set id(value) { this._id = String(value); }
  get childNodes() { return this.children; }
  get textContent() { return this._text + this.children.map(child => child.textContent).join(''); }
  set textContent(value) { for (const child of this.children) child.parentElement = null; this.children = []; this._text = String(value ?? ''); }
  get href() { return this.attrs.href || ''; } set href(value) { this.attrs.href = String(value); }
  get src() { return this.attrs.src || ''; } set src(value) { this.attrs.src = String(value); }
  get srcdoc() { return this.attrs.srcdoc || ''; } set srcdoc(value) { this.attrs.srcdoc = String(value); }
  get value() { return this._value || ''; } set value(value) { this._value = String(value ?? ''); }
  get parentNode() { return this.parentElement; }
  append(...children) { for (const child of children) { child.parentElement = this; this.children.push(child); } }
  replaceChildren(...children) { this.children = []; this._text = ''; this.append(...children); }
  setAttribute(name, value) { this.attrs[name] = String(value); }
  getAttribute(name) { return this.attrs[name] ?? null; }
  removeAttribute(name) { delete this.attrs[name]; }
  addEventListener(type, fn) { (this.listeners[type] ??= []).push(fn); }
  dispatchEvent(event) {
    event.target ??= this;
    for (let node = this; node; node = node.parentElement) {
      event.currentTarget = node;
      for (const fn of node.listeners?.[event.type] || []) fn(event);
      if (event.stopped) break;
    }
    return true;
  }
  click() { this.dispatchEvent({type:'click', target:this, button:0, preventDefault(){this.defaultPrevented=true;}, stopImmediatePropagation(){this.stopped=true;}}); }
  matches(selector) {
    return selector.split(',').some(part => {
      part = part.trim();
      if (part === '[data-node-id]') return Boolean(this.dataset.nodeId);
      if (part === '[data-source-start][data-source-end]') return this.dataset.sourceStart !== undefined && this.dataset.sourceEnd !== undefined;
      if (part === '[data-line]') return this.dataset.line !== undefined;
      if (part.startsWith('#')) return this.id === part.slice(1);
      if (part.startsWith('.')) return this.classList.contains(part.slice(1));
      if (part === 'input[type="search"]') return this.tagName === 'input' && this.attrs.type === 'search';
      return this.tagName === part.toLowerCase();
    });
  }
  querySelectorAll(selector) { return this.children.flatMap(child => [...(child.matches(selector) ? [child] : []), ...child.querySelectorAll(selector)]); }
  querySelector(selector) { return this.querySelectorAll(selector)[0] || null; }
  closest(selector) { for (let node=this; node; node=node.parentElement) if (node.matches(selector)) return node; return null; }
  remove() { if (this.parentElement) this.parentElement.children = this.parentElement.children.filter(child => child !== this); this.parentElement = null; }
  focus() { if (activeDocument) activeDocument.activeElement = this; }
  scrollIntoView() { this.scrolled = true; }
}

const body = new Element('body'), ids = new Map();
const template = fs.readFileSync(path.resolve(__dirname, '..', 'assets', 'lite.html'), 'utf8').split('<script type="application/json"')[0];
for (const match of template.matchAll(/<([a-z][\w-]*)\b[^>]*\bid="([^"]+)"/gi)) {
  const element = new Element(match[1]); element.id = match[2];
  if (match[1].toLowerCase() === 'input') element.setAttribute('type', 'search');
  ids.set(element.id, element); body.append(element);
}
const payloadElement = new Element('script'); payloadElement.id = 'lite-data'; payloadElement.textContent = JSON.stringify(payload); ids.set(payloadElement.id, payloadElement); body.append(payloadElement);
const findId = (node, id) => node.id === id ? node : node.children.map(child => findId(child, id)).find(Boolean) || null;
const doc = {
  body, listeners:{}, createElement: tag => new Element(tag), getElementById: id => ids.get(id) || findId(body, id),
  querySelectorAll: selector => body.querySelectorAll(selector),
  matches:()=>false,
  addEventListener(type, fn) { (this.listeners[type] ??= []).push(fn); }
};
body.parentElement = doc; activeDocument = doc;
const blobs = new Map(); let blobSerial = 0;
class TestURL extends URL { static createObjectURL(blob) { const url = `blob:lite-${++blobSerial}`; blobs.set(url, blob); return url; } static revokeObjectURL() {} }
const context = vm.createContext({
  document:doc, URL:TestURL, CSS:{escape:value=>String(value).replace(/[^a-zA-Z0-9_-]/g,'\\$&')}, TextEncoder, TextDecoder,
  Uint8Array, Blob, atob, Map, Set, console, setTimeout:fn=>{fn();return 1;}, clearTimeout:()=>{},
  requestAnimationFrame:fn=>fn()
});
const skillRoot = path.resolve(__dirname, '..');
const assets = ['vendor/marked.umd.js','markdown.js','lite.js'].map(name => fs.readFileSync(path.join(skillRoot,'assets',name),'utf8')).join('\n;\n');
vm.runInContext(assets, context, {timeout:10000});
const run = source => vm.runInContext(source, context), $ = id => doc.getElementById(id);
(async()=>{
assert.equal($('reader-panel').hidden, true, 'a new Lite page starts with graph-only mode');
assert.ok($('diagram').srcdoc.includes('<svg'), 'the standalone graph iframe is initialized from the embedded viewer');

const chapter = payload.chapter, record = chapter.record;
const frame = $('diagram'), shapes = new Element('svg');
for (const node of record.nodes) { const shape = new Element('g'); shape.dataset.nodeId=node.id; shape.setAttribute('aria-pressed','false'); shapes.append(shape); }
const frameListeners = {};
frame.contentDocument = {
  querySelector: selector => shapes.querySelector(selector), querySelectorAll: selector => shapes.querySelectorAll(selector),
  addEventListener(type, fn) { (frameListeners[type] ??= []).push(fn); }
};
frame.contentWindow = {Archify:{focus:{set(id, options){assert.equal(options.toggle,false);for(const shape of shapes.querySelectorAll('[data-node-id]'))shape.setAttribute('aria-pressed',String(shape.dataset.nodeId===id));}}}};
for (const listener of frame.listeners.load || []) listener({type:'load',target:frame});
assert.equal($('diagram-note').hidden, true, 'graph interaction bridge initialized');
let graphClickHandled=false;
frameListeners.click[0]({type:'click',button:0,target:shapes.querySelectorAll('[data-node-id]').find(node=>node.dataset.nodeId==='daily-option'),preventDefault(){graphClickHandled=true;},stopImmediatePropagation(){}});
assert.equal(graphClickHandled,true,'iframe node click is intercepted for the reading panel');
assert.equal(run('app.node'),'daily-option');
assert.equal($('reader-panel').hidden,false,'clicking an actual iframe node opens the reading panel');

const search = $('title-search'), results = $('search-results');
for (const query of ['蓝鲸书签','晨间便签','连续的小目标']) {
  search.value=query; search.dispatchEvent({type:'input'});
  assert.equal(results.querySelectorAll('.search-result').length,0,`title-only search ignores body/summary phrase ${query}`);
}
search.value='每日短读尝试'; search.dispatchEvent({type:'input'});
const titleResult=results.querySelector('.search-result'); assert.ok(titleResult,'node title is searchable'); titleResult.click();
assert.equal(run('app.node'),'daily-option'); assert.equal($('reader-panel').hidden,false,'choosing a title result opens the reading panel');
const artifactAnchor=$('reader-content').querySelectorAll('a').find(link=>link.href.startsWith('blob:'));
assert.ok(artifactAnchor,'the node retains a real resource link');
artifactAnchor.click();
assert.equal(run('app.view'),'file');
const fileId=run('app.fileId'), file=payload.files[fileId];
assert.equal(file.name,'reading-plan.md');
assert.ok($('reader-content').textContent.includes('晨间便签'),'embedded Markdown renders as readable content');
assert.ok($('reader-content').querySelector('.md-table')===null,'regular Markdown remains safe DOM output');

const download=$('reader-actions').querySelectorAll('button').find(button=>button.textContent==='下载文件');
assert.ok(download,'embedded resource has a download control'); download.click();
const downloaded=[...blobs.values()].find(blob=>blob.type===file.mime);
assert.ok(downloaded,'download generated a blob from the embedded resource');
assert.deepEqual(Buffer.from(await downloaded.arrayBuffer()),Buffer.from(Uint8Array.from(atob(file.data),c=>c.charCodeAt(0))),'download bytes match the original fixture');

const rawToggle=$('reader-actions').querySelectorAll('button').find(button=>button.textContent==='查看原文');
assert.ok(rawToggle,'Markdown can switch to source text'); rawToggle.click();
assert.ok($('reader-content').querySelectorAll('.source-line').length>1,'raw view preserves visible source lines');
console.log(JSON.stringify({status:'passed',kind:'portable fake-DOM smoke test; not real-browser evidence',checks:['graph-first startup and node click opens reader','title search matches node titles only','body-only and summary-only terms do not match','Markdown resource opens with safe readable content','download preserves embedded bytes','raw source view shows line numbers']},null,2));
})().catch(error=>{console.error(error);process.exitCode=1;});

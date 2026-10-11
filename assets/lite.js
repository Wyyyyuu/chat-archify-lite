'use strict';
const E=JSON.parse(document.getElementById('lite-data').textContent);
const chapter=E.chapter,record=chapter.record;
const $=id=>document.getElementById(id);
const STATUS={proposed:'提议',in_progress:'进行中',completed:'已完成',verified:'已验证',failed:'该尝试失败',paused:'暂停／延期',superseded:'被替代',unknown:'待确认'};
const KIND={goal:'目标',milestone:'里程碑',module:'模块',experiment:'尝试',decision:'决策',issue:'问题'};
const REL={continues:'延续',branches:'分叉',adds:'增加',pivots:'转向',merges:'汇合',depends_on:'依赖',chronological:'仅先后'};
const resourceURLs=new Map();
let app={node:null,view:'node',fileId:null,readerNote:'',locator:'',fileRaw:false,returnView:'node'};
function el(tag,text,cls){const node=document.createElement(tag);if(text!==undefined)node.textContent=text;if(cls)node.className=cls;return node;}
function button(text,fn,cls){const b=el('button',text,'button'+(cls?' '+cls:''));b.type='button';b.addEventListener('click',fn);return b;}
function section(parent,title){const s=el('section',undefined,'reader-section');s.append(el('h3',title));parent.append(s);return s;}
function details(parent,title){const d=el('details',undefined,'source-details'),summary=el('summary',title);d.append(summary);parent.append(d);return d;}
function paragraph(parent,text,cls){if(text!==undefined&&text!==null&&String(text)!=='')parent.append(el('p',String(text),cls||''));}
function bytes64(data){return Uint8Array.from(atob(data),c=>c.charCodeAt(0));}
function downloadBytes(bytes,name,mime){const blob=new Blob([bytes],{type:mime||'application/octet-stream'}),url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=name;document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),30000);}
function downloadFile(file){if(file&&file.status==='embedded')downloadBytes(bytes64(file.data),file.name,file.mime);}
function resourceURL(file){if(!resourceURLs.has(file.id)){const type=typeof file.text==='string'?'text/plain;charset=utf-8':(/^image\/(png|jpeg|gif|webp|avif|bmp)$/.test(file.mime)?file.mime:'application/octet-stream');resourceURLs.set(file.id,URL.createObjectURL(new Blob([bytes64(file.data)],{type:type})));}return resourceURLs.get(file.id);}
function isMarkdown(file){return /\.(md|markdown|mdown)$/i.test(file.name)||file.mime==='text/markdown';}
function findNode(id){return record.nodes.find(n=>n.id===id)||null;}
function currentNode(){return findNode(app.node);}
function verifiedHttpsUrl(value,verified){if(verified!==true||typeof value!=='string')return '';try{const url=new URL(value);return url.protocol==='https:'&&url.hostname&&!url.username&&!url.password?url.href:'';}catch{return '';}}
function safeWebUrl(value){if(typeof value!=='string')return '';try{const url=new URL(value);return ['http:','https:'].includes(url.protocol)&&url.hostname&&!url.username&&!url.password?url.href:'';}catch{return '';}}
function setReader(open){$('workspace').classList.toggle('show-reader',Boolean(open));$('workspace').classList.toggle('show-graph',!open);$('reader-panel').hidden=!open;$('graph-toggle').textContent=open?'返回框图':'打开阅读面板';if(open){$('reader-title').focus({preventScroll:true});}else $('graph-toggle').focus({preventScroll:true});}
function selectNode(id,openPanel){const node=findNode(id);if(!node)return;app.node=id;app.view='node';app.fileId=null;app.locator='';app.readerNote='';renderReader();$('node-picker').value=id;if(openPanel)setReader(true);focusNode(id);}
function focusNode(id){try{const frame=$('diagram'),shape=frame.contentDocument.querySelector('[data-node-id=\"'+CSS.escape(id)+'\"]'),focus=frame.contentWindow.Archify&&frame.contentWindow.Archify.focus;if(focus&&typeof focus.set==='function')focus.set(id,{toggle:false,hideChip:true,updateUrl:false});else if(shape)shape.setAttribute('aria-pressed','true');}catch{}}
function showGraph(){setReader(false);}
function openReader(){if(!app.node&&record.nodes.length)app.node=record.nodes[0].id;renderReader();setReader(true);}
function openFile(id,options){const file=E.files[id];if(!file)return;app.returnView=app.view;app.view='file';app.fileId=id;app.locator=(options&&options.locator)||'';app.readerNote=(options&&options.note)||'';app.fileRaw=false;renderReader();}
function backToNode(){app.view='node';app.fileId=null;app.locator='';app.fileRaw=false;renderReader();setReader(true);}
function showSearchResults(){
 const query=$('title-search').value.trim().toLocaleLowerCase(),root=$('search-results');root.replaceChildren();root.hidden=!query;if(!query)return;
 const matches=record.nodes.filter(node=>node.title.toLocaleLowerCase().includes(query));
 if(!matches.length){root.append(el('div','没有匹配的阶段标题。','search-empty'));return;}
 matches.forEach(node=>{const result=button(node.title,()=>{root.hidden=true;selectNode(node.id,true);},'search-result');root.append(result);});
}
function updateCoverage(){
 const root=$('coverage');root.replaceChildren();(record.coverage||[]).forEach(text=>paragraph(root,text));
 (record.open_questions||[]).forEach(text=>paragraph(root,'待确认：'+text));
 paragraph(root,'Lite 限制：仅处理一个对话和一张总览；搜索只匹配阶段标题，不索引摘要、关系或文件正文。最多内嵌 3 个不同的非对话本地文件。超额资源、缺失文件和被排除文件仍保留来源、节点关联、原始路径与限制说明。没有增量更新入口；修改后请重新生成一张图。');
}
function addResourceLink(parent,item){
 const box=el('div',undefined,'resource-line'),title=item.label||item.title||item.uri||'未命名资源';
 if(item.file_id){const file=E.files[item.file_id];if(file&&file.status==='embedded'){
  const a=el('a',title,'resource-link');a.href=resourceURL(file);a.target='_blank';a.rel='noopener noreferrer';a.addEventListener('click',event=>{if(event.button===0&&!event.ctrlKey&&!event.metaKey&&!event.shiftKey&&!event.altKey){event.preventDefault();openFile(file.id,{note:item.note||''});}});box.append(a);
  paragraph(box,'文件快照','note');const actions=el('div',undefined,'actions');actions.append(button('页内阅读',()=>openFile(file.id,{note:item.note||''})),button('下载',()=>downloadFile(file)));box.append(actions);
 }else{box.append(el('strong',title));paragraph(box,file&&file.note||'文件未找到；保留来源路径。','note');if(file&&file.path)paragraph(box,file.path,'note');}}
 else if(safeWebUrl(item.uri)){const a=el('a',title,'resource-link');a.href=safeWebUrl(item.uri);a.target='_blank';a.rel='noopener noreferrer';box.append(a);}
 else{box.append(el('strong',title));}
 if(item.uri&&!item.file_id){const locator=details(box,'来源定位信息');paragraph(locator,'原始位置：'+item.uri,'note');if(item.attachment_note)paragraph(locator,item.attachment_note,'note');}
 if(item.note)paragraph(box,item.note,'note');parent.append(box);
}
function renderNode(){
 const node=currentNode(),root=$('reader-content'),actions=$('reader-actions');root.replaceChildren();actions.replaceChildren();
 $('reader-title').textContent=node?node.title:'选择一个阶段';if(!node){paragraph(root,'请从框图或“定位阶段”菜单中选择一个阶段。','reader-empty');return;}
 actions.append(button('返回框图',showGraph));
 const info=section(root,'阶段信息');paragraph(info,(KIND[node.kind]||node.kind)+' · '+(node.branch||'分支未注明'),'meta');paragraph(info,'阶段时间：'+(node.date||'未注明'),'note');info.append(el('span',STATUS[node.status]||node.status,'status'));
 paragraph(section(root,'发生了什么'),node.summary||'没有提供摘要。');
 if(node.reason)paragraph(section(root,'原因与取舍'),node.reason);
 const sources=new Map((record.sources||[]).map(source=>[source.id,source]));
 const evidence=section(root,'来源与证据 · '+(node.evidence||[]).length);
 for(const ref of node.evidence||[]){
  const source=sources.get(ref.source);if(!source)continue;
  const row=el('div',undefined,'resource-line');
  if(source.file_id&&E.files[source.file_id]&&E.files[source.file_id].status==='embedded')row.append(button('打开来源：'+(source.title||'文件'),()=>openFile(source.file_id,{note:source.note||'',locator:ref.locator||''}),'link-button'));
  else if(verifiedHttpsUrl(source.original_url,source.original_url_verified)){const a=el('a',source.title||'打开验证来源','resource-link');a.href=verifiedHttpsUrl(source.original_url,source.original_url_verified);a.target='_blank';a.rel='noopener noreferrer';row.append(a);}
  else row.append(el('strong',source.title||source.kind||'来源'));
  paragraph(row,'覆盖：'+(source.coverage||'未注明'),'note');
  const attached=source.file_id&&E.files[source.file_id];if(attached&&attached.status!=='embedded'&&attached.note)paragraph(row,attached.note,'note');
  if(source.note)paragraph(row,source.note,'note');if(ref.note)paragraph(row,ref.note,'note');
  if(ref.locator&&source.file_id)row.append(button('定位 '+ref.locator,()=>openFile(source.file_id,{note:source.note||'',locator:ref.locator}),'link-button'));
  const sourceUrl=safeWebUrl(source.uri);
  if(sourceUrl&&!(source.file_id&&E.files[source.file_id]?.status==='embedded')){const link=el('a','打开来源网页','resource-link');link.href=sourceUrl;link.target='_blank';link.rel='noopener noreferrer';row.append(link);}
  const originalUrl=verifiedHttpsUrl(source.original_url,source.original_url_verified);
  if(originalUrl){const link=el('a','打开已验证的原任务','resource-link');link.href=originalUrl;link.target='_blank';link.rel='noopener noreferrer';row.append(link);}
  if(source.locator||ref.locator||source.uri){const technical=details(row,'来源定位信息');if(source.locator)paragraph(technical,source.locator,'note');if(ref.locator&&!source.file_id)paragraph(technical,ref.locator,'note');if(source.uri)paragraph(technical,'原始位置：'+source.uri,'note');}
  evidence.append(row);
 }
 const artifacts=section(root,'相关产物 · '+(node.artifacts||[]).length);
 if(!(node.artifacts||[]).length)paragraph(artifacts,'此阶段没有记录产物。','note');
 for(const item of node.artifacts||[])addResourceLink(artifacts,item);
 const related=(record.edges||[]).filter(edge=>edge.from===node.id||edge.to===node.id);
 const relations=section(root,'连接关系 · '+related.length);
 if(!related.length)paragraph(relations,'没有记录关系。','note');
 for(const edge of related){const incoming=edge.to===node.id,other=findNode(incoming?edge.from:edge.to),row=el('div',undefined,'resource-line');paragraph(row,(incoming?'来自':'通向')+' · '+(REL[edge.type]||edge.type)+(edge.confidence==='inferred'?'（推测）':''),'note');if(other)row.append(button(other.title,()=>selectNode(other.id,true),'link-button'));paragraph(row,edge.reason,'note');relations.append(row);}
}
function parseRanges(value){const ranges=[],pattern=/(?:^|[^\w])L(?:ine\s*)?(\d+)(?:\s*[–—-]\s*L?(\d+))?/gi;let match;while((match=pattern.exec(String(value||'')))){const start=Number(match[1]),end=Number(match[2]||match[1]);if(start>0&&end>=start)ranges.push({start:start,end:end});}return ranges;}
function rawLines(text,container){container.replaceChildren();const pre=el('pre',undefined,'raw-source');String(text||'').replace(/\r\n?/g,'\n').split('\n').forEach((line,index)=>{const span=el('span',line+(index?'':'')+(index+1<(String(text||'').replace(/\r\n?/g,'\n').split('\n').length)?'\n':''),'source-line');span.dataset.line=String(index+1);pre.append(span);});container.append(pre);}
function highlightLocator(container,locator){
 const ranges=parseRanges(locator);container.querySelectorAll('.locator-target').forEach(node=>node.classList.remove('locator-target'));
 if(!ranges.length)return {ok:false,reason:'无法识别为行号定位。'};
 const targets=Array.from(container.querySelectorAll('.source-line,[data-source-start][data-source-end]')).filter(node=>{const start=Number(node.dataset.line||node.dataset.sourceStart),end=Number(node.dataset.line||node.dataset.sourceEnd);return ranges.some(range=>start<=range.end&&end>=range.start);});
 if(!targets.length)return {ok:false,reason:'未能将这些原文行映射到段落。'};
 targets.forEach(node=>node.classList.add('locator-target'));targets[0].scrollIntoView({block:'center'});return {ok:true};
}
function renderFile(){
 const file=E.files[app.fileId],root=$('reader-content'),actions=$('reader-actions');root.replaceChildren();actions.replaceChildren();$('reader-title').textContent=file?file.name:'文件';
 actions.append(button('返回阶段',backToNode));if(file&&file.status==='embedded'){actions.append(button(app.fileRaw?'格式化阅读':'查看原文',()=>{const scroll=root.scrollTop;app.fileRaw=!app.fileRaw;renderFile();root.scrollTop=scroll;}));actions.append(button('下载文件',()=>downloadFile(file),'primary'));}
 if(!file){paragraph(root,'没有找到对应文件记录。','reader-empty');return;}
 const info=section(root,'文件快照');paragraph(info,(file.status==='embedded'?'已内嵌 · '+Math.ceil((file.bytes||0)/1024)+' KB':'正文未内嵌')+' · 快照时间：'+(file.snapshot_at||'未记录'),'note');if(file.note)paragraph(info,file.note,'note');if(app.readerNote)paragraph(info,app.readerNote,'note');if(file.path){const technical=details(info,'来源定位信息');paragraph(technical,'原始路径：'+file.path,'note');}
 if(app.locator){const loc=section(root,'来源定位');paragraph(loc,'原始位置：'+app.locator,'note');loc.append(button('定位到段落',()=>{const result=highlightLocator($('lite-file-render'),app.locator);if(!result.ok)paragraph(loc,result.reason+' 可切换到原文查看行号。','locator-help');}));}
 const article=el('article',undefined,'markdown-body');article.id='lite-file-render';
 if(file.status!=='embedded')paragraph(article,file.note||'只保留资源引用，没有嵌入文件正文。','note');
 else if(/^image\/(png|jpeg|gif|webp|avif|bmp)$/.test(file.mime)){const image=el('img');image.alt=file.name;image.src='data:'+file.mime+';base64,'+file.data;article.append(image);}
 else if(isMarkdown(file)&&!app.fileRaw)renderMarkdown(file.text||'',article,file);
 else if(typeof file.text==='string')rawLines(file.text,article);
 else paragraph(article,'此文件格式可下载后在本地应用中打开。','note');
 root.append(article);
 if(app.locator){const result=highlightLocator(article,app.locator);if(!result.ok)paragraph(root,result.reason+' 可切换到原文查看行号。','locator-help');}
}
function renderReader(){if(app.view==='file')renderFile();else renderNode();}
function bindFrame(){
 const frame=$('diagram'),reader=$('diagram-note');
 frame.addEventListener('load',()=>{
  try{
   const doc=frame.contentDocument;if(!doc||!doc.querySelector('[data-node-id]'))throw new Error('node diagram missing');
   doc.querySelectorAll('input[type=\"search\"]').forEach(input=>input.remove());
   const activate=event=>{if(event.type==='keydown'&&!['Enter',' '].includes(event.key))return;if(event.type==='click'&&event.button!==undefined&&event.button!==0)return;const node=event.target.closest&&event.target.closest('[data-node-id]');if(!node||!findNode(node.dataset.nodeId)||doc.querySelector('[data-just-panned=\"true\"]'))return;event.preventDefault();event.stopImmediatePropagation();selectNode(node.dataset.nodeId,true);};
   doc.addEventListener('click',activate,true);doc.addEventListener('keydown',activate,true);reader.hidden=true;
  }catch{reader.hidden=false;}
 });
 frame.srcdoc=new TextDecoder().decode(bytes64(chapter.viewer));
}
function setup(){
 $('page-title').textContent=E.title;$('graph-meta').textContent=record.nodes.length+' 个阶段 · '+record.edges.length+' 条关系；完整保留记录中的节点与关系。';
 record.nodes.forEach(node=>{const option=el('option',node.title);option.value=node.id;$('node-picker').append(option);});
 $('node-picker').addEventListener('change',()=>{if($('node-picker').value)selectNode($('node-picker').value,true);});
 $('title-search').addEventListener('input',showSearchResults);$('title-search').addEventListener('keydown',event=>{if(event.key==='Escape'){$('search-results').hidden=true;$('title-search').blur();}});
 $('graph-toggle').addEventListener('click',()=>{if($('reader-panel').hidden)openReader();else showGraph();});
 $('reader-close').addEventListener('click',showGraph);
 $('json-download').addEventListener('click',()=>downloadBytes(new TextEncoder().encode(JSON.stringify(E.recordExport,null,2)),(E.title||'conversation')+'.json','application/json;charset=utf-8'));
 document.addEventListener('keydown',event=>{if(event.key==='Escape'&&!$('reader-panel').hidden){if(app.view==='file')backToNode();else showGraph();}});
 document.addEventListener('click',event=>{if(!event.target.closest('.search-box'))$('search-results').hidden=true;});
 updateCoverage();bindFrame();renderReader();setReader(false);
}
setup();

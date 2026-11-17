// Export the existing shelf as a local, read-only assessment copy. No cloud writes.
import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import {marked} from 'marked';
import sanitize from 'sanitize-html';

const root=path.resolve(import.meta.dirname,'../..');
const input=path.join(import.meta.dirname,'base');
const output=path.join(root,'frontend/public/bookshelf');
if(output!==path.resolve(root,'frontend/public/bookshelf'))throw Error('Unexpected export target');
const nav=path.join(root,'docs/文档导航QA');
const esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const hash=b=>crypto.createHash('sha256').update(b).digest('hex');
await fs.rm(output,{recursive:true,force:true});
await fs.mkdir(output,{recursive:true});
for(const name of ['articles','originals','style.css','code.css','source-goals.md']){
  await fs.cp(path.join(input,name),path.join(output,name),{recursive:true,force:true});
}
const data=JSON.parse(await fs.readFile(path.join(input,'data.json'),'utf8'));
if(data.groups.length!==7||data.records.length!==49)throw Error('Expected unchanged seven-direction source shelf');
data.learningGoalCount=49;
data.learningDocumentCount=data.records.filter(r=>r.available).length;
data.records=data.records.map(record=>({...record,kind:'learning',sourcePath:'learning/'+record.filename}));
data.reviewDocuments=[];
data.reviewSection={title:'文档导航QA',kind:'assessment_reference'};
data.assessmentExport={updated:'2026-11-17',scope:'local-read-only',source:'docs/文档导航QA',progress:'not-connected'};
const names=['文档导航QA.md','01-源码依赖迁移配置与资料.md','02-验证测试修正与试用反馈.md','03-主要功能与后台任务进度.md',
  '测试与修复记录/测试与修复记录.md','测试与修复记录/01-固定样例与来源核对.md','测试与修复记录/02-真实模型前后对照.md',
  '测试与修复记录/03-具体问题修正全过程.md','测试与修复记录/04-自动化与后台故障测试.md',
  '测试与修复记录/05-AI代码修复与调用方检查.md','测试与修复记录/06-成功失败演示与真人试用.md'];
const ids=new Map(names.map((name,i)=>[path.join(nav,name),`8-${String(i+1).padStart(2,'0')}`]));
const copied=new Map();
const excluded=[];
const extensions=new Set(['.md','.json','.jsonc','.jsonl','.xml','.log','.txt','.py','.ts','.tsx','.css','.html','.yml','.yaml','.toml','.lock','.ini','.lua','.ps1','.mjs','.sql','.example','.svg','.png']);
const roots=new Set(['docs','evaluations','tests','backend','frontend','migrations','data','rulings','scripts','compose','.github','public-entry','tools']);
function allowed(file){
  const rel=path.relative(root,file),parts=rel.split(path.sep);
  return rel&&!rel.startsWith('..')&&!path.isAbsolute(rel)&&
    !parts.some(p=>['.local','.venv','node_modules','git','.git','__pycache__','dist','public'].includes(p))&&
    !parts.some(p=>p.startsWith('.env')&&p!=='.env.example')&&
    (roots.has(parts[0])||parts.length===1)&&
    (extensions.has(path.extname(file))||['VERSION','Dockerfile','LICENSE'].includes(path.basename(file))||file.endsWith('.Dockerfile')||file.endsWith('.mako'));
}
const codeSuffix=file=>/\.(?:[cm]?js|tsx?|log)$/.test(file)?'.txt':'';
function urlFor(file){return '/bookshelf/review-files/'+path.relative(root,file).split(path.sep).map(encodeURIComponent).join('/')+codeSuffix(file);}
async function copyEvidence(file){
  if(copied.has(file))return copied.get(file);
  if(!allowed(file)){excluded.push(path.relative(root,file));return null;}
  let stat;try{stat=await fs.stat(file);}catch{excluded.push(path.relative(root,file));return null;}
  if(!stat.isFile()||stat.size>3_000_000)return null;
  const bytes=await fs.readFile(file);
  const rel=path.relative(root,file),dest=path.join(output,'review-files',rel)+codeSuffix(file);
  await fs.mkdir(path.dirname(dest),{recursive:true});
  const value={url:urlFor(file),sha256:hash(bytes),bytes:bytes.length};
  copied.set(file,value);
  // Render linked Markdown as readable HTML with recursively resolved evidence links.
  if(path.extname(file)==='.md'){
    const html=await render(bytes.toString('utf8'),file);
    await fs.writeFile(dest+'.html',`<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>${esc(path.basename(file))}</title><link rel="stylesheet" href="/bookshelf/style.css"><body style="padding:24px;max-width:1050px;margin:auto"><a href="/?page=bookshelf&shelf=review">← 文档导航QA</a><article class="article">${html}</article></body></html>`);
  }
  await fs.writeFile(dest,bytes);
  return value;
}
async function resolveLink(href,source){
  if(/^(https?:|mailto:|#)/i.test(href))return href;
  if(/^([a-z]+:|\/\/)/i.test(href))return null;
  let clean;try{clean=decodeURIComponent(href.split('#')[0]);}catch{return null;}
  const file=path.resolve(path.dirname(source),clean.replaceAll('/',path.sep));
  if(ids.has(file))return '/?page=bookshelf&shelf=review&document='+ids.get(file);
  let stat;try{stat=await fs.stat(file);}catch{excluded.push(path.relative(root,file));return null;}
  if(stat.isDirectory()){
    const rel=path.relative(root,file),parts=rel.split(path.sep);
    if(!roots.has(parts[0])||parts.some(p=>['.local','git','.git','node_modules','public','dist'].includes(p)))return null;
    const key=file+path.sep;
    if(copied.has(key))return urlFor(file)+'/index.html';
    copied.set(key,{directory:true});
    const links=[];
    for(const entry of await fs.readdir(file,{withFileTypes:true})){
      if(!entry.isFile())continue;
      const target=path.join(file,entry.name),record=await copyEvidence(target);
      if(record)links.push(`<li><a href="${esc(record.url+(entry.name.endsWith('.md')?'.html':''))}">${esc(entry.name)}</a></li>`);
    }
    const dest=path.join(output,'review-files',rel,'index.html');await fs.mkdir(path.dirname(dest),{recursive:true});
    await fs.writeFile(dest,`<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>${esc(rel)}</title><a href="/?page=bookshelf&shelf=review">← 文档导航QA</a><h1>${esc(rel)}</h1><ul>${links.join('')}</ul></html>`);
    return urlFor(file)+'/index.html';
  }
  const record=await copyEvidence(file);
  return record?record.url+(file.endsWith('.md')?'.html':''):null;
}
async function render(markdown,source){
  let html=marked.parse(markdown,{gfm:true});
  const links=[...html.matchAll(/href="([^"]*)"/g)];
  for(const match of links){const target=await resolveLink(match[1],source);html=html.replace(match[0],target?`href="${esc(target)}"`:'aria-disabled="true" title="该本机资料未随检阅副本导出"');}
  for(const match of [...html.matchAll(/src="([^"]*)"/g)]){const target=await resolveLink(match[1],source);html=html.replace(match[0],target?`src="${esc(target)}"`:'alt="历史图片未导出"');}
  return sanitize(html,{allowedTags:[...sanitize.defaults.allowedTags,'details','summary','img'],allowedAttributes:{...sanitize.defaults.allowedAttributes,a:['href','title','aria-disabled'],'*':['id','class'],img:['src','alt']},allowedSchemes:['http','https','mailto']});
}
for(const name of names){
  const file=path.join(nav,name),id=ids.get(file),markdown=await fs.readFile(file,'utf8');
  let html=await render(markdown,file),n=0;const toc=[];
  html=html.replace(/<h([1-6])>([\s\S]*?)<\/h\1>/g,(_,level,inner)=>{const anchor=`section-${++n}`;if(Number(level)>=2&&Number(level)<=3)toc.push({id:anchor,level:Number(level),text:inner.replace(/<[^>]+>/g,'')});return `<h${level} id="${anchor}">${inner}</h${level}>`;});
  await fs.writeFile(path.join(output,'articles',id+'.html'),html);
  await fs.writeFile(path.join(output,'originals',id+'.md'),markdown);
  const title=markdown.split('\n').find(line=>line.startsWith('# '))?.slice(2).trim()||name;
  data.reviewDocuments.push({id,kind:'assessment_reference',sourcePath:'docs/文档导航QA/'+name,title,available:true,filename:name,characters:markdown.length,hash:hash(markdown),search:markdown.replace(/[#*>`|\[\]]/g,' '),toc});
}
data.evidenceLinks=Object.fromEntries([...copied].map(([file,value])=>[path.relative(root,path.resolve(file)).replaceAll('\\','/'),value.directory?urlFor(path.resolve(file))+'/index.html':value.url+(file.endsWith('.md')?'.html':'')]));
await fs.writeFile(path.join(output,'data.json'),JSON.stringify(data));
await fs.writeFile(path.join(output,'index.html'),'<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta http-equiv="refresh" content="0;url=/?page=bookshelf"><title>轻归 · 知识书架</title><a href="/?page=bookshelf">进入轻归知识书架</a></html>');
await fs.mkdir(path.join(output,'licenses'),{recursive:true});
await fs.cp(path.join(input,'licenses'),path.join(output,'licenses'),{recursive:true,force:true});
await fs.writeFile(path.join(output,'THIRD-PARTY-NOTICES.md'),'# 本地知识书架来源\n\n原书架来自本工作区知识浏览网页，保留7个学习方向、49条目标和49份原文；文档导航QA单列为考核资料，不进入学习目录。轻归原生模块复用既有Markdown适配与Query层提供搜索、阅读目录和字号；导出保留原文和证据链接，不加载独立书架的重复界面。\n\nMarkdown生成使用marked与sanitize-html；已有代码高亮及样式来自highlight.js。许可证见licenses/。本地副本不连接Cloudflare D1、不导出主人管理口令、不修改云端掌握进度。\n');
const manifest={updated:'2026-11-17',sourceShelf:'tools/bookshelf/base',sourceOrigin:'工作区知识浏览网页，2026-11-17本地快照',learningGoals:49,learningDocuments:data.records.filter(r=>r.group<7&&r.available).length,reviewDocuments:names.length,cloudModified:false,files:[...copied].filter(([,v])=>!v.directory).map(([file,value])=>({path:path.relative(root,file).replaceAll('\\','/'),...value})),unexported:[...new Set(excluded)].sort()};
await fs.writeFile(path.join(output,'export-manifest.json'),JSON.stringify(manifest,null,2));
console.log(JSON.stringify({reviewDocuments:names.length,linkedFiles:manifest.files.length,unexported:manifest.unexported.length,output}));

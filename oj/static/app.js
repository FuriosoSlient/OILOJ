// Shared frontend utilities for OIL OJ
const API = {
  async get(url){ const r = await fetch(url); if(!r.ok){ const e = await r.json().catch(()=>({detail:r.statusText})); throw new Error(e.detail||'Error'); } return r.json(); },
  async post(url, data){
    const fd = (data instanceof FormData) ? data : (()=>{
      const f = new FormData();
      for(const k in data) if(data[k]!==undefined && data[k]!==null) f.append(k,data[k]);
      return f;
    })();
    const r = await fetch(url,{method:'POST',body:fd});
    if(!r.ok){ const e = await r.json().catch(()=>({detail:r.statusText})); throw new Error(e.detail||'Error'); }
    return r.json();
  },
  async del(url){
    const r = await fetch(url,{method:'DELETE'});
    if(!r.ok){ const e = await r.json().catch(()=>({detail:r.statusText})); throw new Error(e.detail||'Error'); }
    return r.json();
  }
};

// <head> assets shared by every page (KaTeX/marked are vendored for offline use)
function vendorHead(){
  return `<link rel="stylesheet" href="/static/vendor/katex/katex.min.css">`;
}

// Reverse the entity escaping marked applies inside code blocks.
function unescapeHtml(s){
  return String(s).replace(/&lt;/g,'<').replace(/&gt;/g,'>')
                  .replace(/&quot;/g,'"').replace(/&#39;/g,"'")
                  .replace(/&amp;/g,'&');
}

function esc(s){
  if(s===null||s===undefined) return '';
  return String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}

function statusBadge(status, score){
  if(status==='AC') return `<span class="badge badge-AC">Accepted</span>`;
  if(status==='CE') return `<span class="badge badge-CE">Compilation Error</span>`;
  if(status==='PENDING') return `<span class="badge badge-PENDING">Pending</span>`;
  if(status==='JUDGING') return `<span class="badge badge-PENDING"><span class="live-dot"></span>Judging</span>`;
  const m = {'WA':'Wrong Answer','TLE':'Time Limit Exceeded','MLE':'Memory Limit Exceeded','RE':'Runtime Error','SE':'System Error'};
  const cls = {'WA':'WA','TLE':'TLE','MLE':'MLE','RE':'RE','SE':'SE'}[status]||'WA';
  let label = m[status]||status;
  if(score>0 && status!=='AC') label += ` (${score})`;
  return `<span class="badge badge-${cls}">${esc(label)}</span>`;
}

function hackBadge(s){
  const label={PENDING:'排队中',JUDGING:'判定中',SUCCESS:'Hack 成功',
               FAILURE:'Hack 失败',INVALID:'无效数据',SE:'系统错误'}[s]||s;
  const cls={PENDING:'PENDING',JUDGING:'PENDING',SUCCESS:'SUCCESS',
             FAILURE:'FAILURE',INVALID:'INVALID',SE:'SE'}[s]||'PENDING';
  return `<span class="badge badge-${cls}">${label}</span>`;
}

// Live-follow a hack verdict over SSE (mirrors followSubmission).
function followHack(hid, cb){
  return new Promise(resolve=>{
    let done=false, last=null;
    const finish=h=>{ if(!done){done=true;resolve(h);} };
    let es;
    try{ es=new EventSource(`/api/hack/${hid}/stream`); }
    catch(e){ return pollHack(hid,cb).then(finish); }
    es.onmessage=ev=>{
      try{
        const h=JSON.parse(ev.data); last=h; cb&&cb(h);
        if(h.status!=='PENDING'&&h.status!=='JUDGING'){ es.close(); finish(h); }
      }catch(e){}
    };
    es.addEventListener('done',()=>{ es.close(); finish(last); });
    es.onerror=()=>{ es.close(); if(!done) pollHack(hid,cb).then(finish); };
  });
}
async function pollHack(hid, cb){
  for(let i=0;i<300;i++){
    const h=await API.get(`/api/hack/${hid}`);
    cb&&cb(h);
    if(h.status!=='PENDING'&&h.status!=='JUDGING') return h;
    await new Promise(r=>setTimeout(r,800));
  }
}

// ---- Hack detail report -------------------------------------------------
function fmtMem(kb){
  if(!kb) return '—';
  return kb>=1024 ? (kb/1024).toFixed(1)+' MB' : kb+' KB';
}

function hackRunRow(r){
  const cls={AC:'badge-AC',WA:'badge-WA',TLE:'badge-TLE',MLE:'badge-MLE',
             RE:'badge-RE',CE:'badge-CE',SE:'badge-SE'}[r.status]||'badge-WA';
  return `<tr>
    <td style="text-align:left">${esc(r.label||'')}</td>
    <td><span class="badge ${cls}">${esc(r.status)}</span></td>
    <td class="mono">${r.time_ms!=null?r.time_ms+' ms':'—'}</td>
    <td class="mono">${fmtMem(r.memory_kb)}</td>
    <td style="text-align:left;font-size:12px">${esc(r.checker||'')}</td>
  </tr>`;
}

function renderHackDetail(h){
  const d=h.detail||{};
  const stages=d.stages||[], runs=d.runs||[], per=d.per_member||[];
  if(!stages.length && !runs.length && !per.length){
    return h.restricted
      ? '<div class="muted" style="font-size:12px;margin-top:6px">比赛期间仅公开判定结果，详情对非当事人隐藏。</div>'
      : '';
  }
  const table = rows => `<table class="hack-detail-table">
      <thead><tr><th style="text-align:left">阶段</th><th>结果</th><th>用时</th><th>内存</th>
        <th style="text-align:left">判定</th></tr></thead>
      <tbody>${rows}</tbody></table>`;

  let html='<div class="hack-detail">';
  if(d.checker) html+=`<div class="muted" style="font-size:12px;margin-bottom:6px">判定方式：${esc(d.checker)}</div>`;
  if(stages.length) html+=table(stages.map(hackRunRow).join(''));

  if(runs.length){
    html+=`<div class="hack-sec">被 Hack 程序运行 ${d.runs_executed||runs.length} / ${d.runs_requested||5} 次
      <span class="muted" style="font-weight:400">（任意一次失败即 Hack 成功）</span></div>`;
    html+=table(runs.map(hackRunRow).join(''));
  }
  per.forEach(m=>{
    html+=`<div class="hack-sec">${esc(m.display_name)} 的做法 —
      ${m.verdict==='SUCCESS'?'<span style="color:#d83b3b">已击破</span>':'<span style="color:#52c41a">未击破</span>'}
      <span class="muted" style="font-weight:400">${esc(m.message||'')}</span></div>`;
    if((m.runs||[]).length) html+=table(m.runs.map(hackRunRow).join(''));
  });

  const outs=stages.filter(x=>x.output);
  if(outs.length){
    html+='<div class="hack-sec">各程序输出</div>';
    outs.forEach(x=>{
      html+=`<div style="margin-bottom:6px"><div class="muted" style="font-size:12px">${esc(x.label)}</div>
        <pre class="hack-out">${esc((x.output||'').slice(0,1200))}${x.truncated?'\n…(已截断)':''}</pre></div>`;
    });
  }
  return html+'</div>';
}

// Fetch the full report and render it into `el`.
async function showHackReport(hid, el){
  try{
    const h=await API.get(`/api/hack/${hid}`);
    const cls=h.status==='SUCCESS'?'success':(h.status==='FAILURE'?'failure':'invalid');
    el.innerHTML=`<div class="hack-result ${cls}">
      <div>${hackBadge(h.status)} <strong>#${h.id}</strong>
        <span class="muted">${esc(h.problem_title||'')}</span></div>
      ${h.message?`<div style="margin-top:4px">${esc(h.message)}</div>`:''}
      ${renderHackDetail(h)}
    </div>`;
  }catch(e){
    el.innerHTML=`<div class="alert alert-error">${esc(e.message)}</div>`;
  }
}

function fmtTime(ts){
  if(!ts) return '';
  const d = new Date(ts*1000);
  return d.toLocaleString('zh-CN',{hour12:false});
}

function fmtClock(secs){
  if(secs<0) secs=0;
  const h=Math.floor(secs/3600), m=Math.floor(secs%3600/60), s=secs%60;
  return `${String(h).padStart(2,'0')}:${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}`;
}

function phaseLabel(p){
  return {before:'未开始',solve:'比赛中',hack:'⚔️ 公开 Hack 阶段',after:'已结束'}[p]||p;
}

function toast(msg, type='info'){
  let t = document.getElementById('toast');
  if(!t){ t=document.createElement('div'); t.id='toast'; t.style.cssText='position:fixed;top:20px;right:20px;z-index:9999;'; document.body.appendChild(t); }
  const d=document.createElement('div');
  d.className=`alert alert-${type}`;
  d.textContent=msg;
  d.style.cssText='margin-bottom:8px;min-width:240px;box-shadow:0 4px 12px rgba(0,0,0,.1);';
  t.appendChild(d);
  setTimeout(()=>{d.style.opacity='0';d.style.transition='opacity .3s';setTimeout(()=>d.remove(),300);},3000);
}

async function loadMe(){
  try{ const r = await API.get('/api/me'); return r.user; } catch(e){ return null; }
}

function renderLayout(user, active){
  const sb = document.getElementById('sidebar');
  if(!sb) return;
  const u = user ? `
    <div class="user-box">
      <div><a href="/user/${user.id}" class="uname">${esc(user.display_name)}</a>${
        user.is_admin ? ' <span class="tag tag-admin">管理员</span>'
                      : (user.is_manager ? ' <span class="tag tag-manager">出题负责人</span>'
                      : (user.is_author ? ' <span class="tag tag-author">出题人</span>' : ''))}</div>
      <div style="color:#8aa4bd;font-size:12px;margin:2px 0 6px;">@${esc(user.username)}
        · <a href="/user/${user.id}"><strong>${user.rating!=null?user.rating:1500}</strong></a></div>
      <a href="/logout">退出登录</a>
    </div>` : `
    <div class="user-box">
      <a href="/login">登录</a> · <a href="/register">注册</a>
    </div>`;
  const canManage = user && (user.is_admin || user.is_manager);
  const adminNav = canManage ? `
      <div class="nav-sep">管理</div>
      <a href="/admin" class="${active==='admin'?'active':''}">⚙️ 管理后台</a>` : '';
  sb.innerHTML = `
    <div class="logo">OIL<span>OJ</span></div>
    <nav>
      <a href="/" class="${active==='home'?'active':''}">首页</a>
      <a href="/problems" class="${active==='problems'?'active':''}">题目</a>
      <a href="/contests" class="${active==='contests'?'active':''}">比赛</a>
      <a href="/status" class="${active==='status'?'active':''}">评测状态</a>
      ${adminNav}
    </nav>
    ${u}`;
  renderAdminFab(user, active);
}

// ---------------------------------------------------------------------------
// Floating "管理后台" button, rendered on every page for admins/managers.
function renderAdminFab(user, active){
  if(!user || !(user.is_admin || user.is_manager) || active==='admin') return;
  if(document.getElementById('admin-fab')) return;
  const a=document.createElement('a');
  a.id='admin-fab'; a.href='/admin'; a.className='admin-fab';
  a.title='进入管理后台';
  a.innerHTML='⚙️ <span>管理后台</span>';
  document.body.appendChild(a);
}

// Markdown + LaTeX rendering
// ---------------------------------------------------------------------------
// Math is extracted BEFORE markdown runs (so marked can't mangle backslashes or
// treat _x_ as emphasis), rendered with KaTeX, then re-inserted. The markdown
// output is sanitised with DOMPurify since statements are admin-authored HTML.

function renderStatement(text){
  if(!text) return '';
  if(typeof marked === 'undefined'){          // vendor scripts absent -> plain text
    return '<p>'+esc(text).replace(/\n/g,'<br>')+'</p>';
  }

  const math = [];
  const stash = (tex, display) => {
    math.push({tex, display});
    return `@@MATH${math.length-1}@@`;
  };

  let src = text;
  // Protect fenced code blocks and inline code from math extraction
  const code = [];
  src = src.replace(/```[\s\S]*?```|`[^`\n]*`/g, m => {
    code.push(m); return `@@CODE${code.length-1}@@`;
  });

  // Display math: $$..$$ and \[..\]   |   Inline: $..$ and \(..\)
  src = src.replace(/\$\$([\s\S]+?)\$\$/g, (m,t)=>stash(t,true));
  src = src.replace(/\\\[([\s\S]+?)\\\]/g, (m,t)=>stash(t,true));
  src = src.replace(/\\\(([\s\S]+?)\\\)/g, (m,t)=>stash(t,false));
  src = src.replace(/(?<!\\)\$([^$\n]+?)(?<!\\)\$/g, (m,t)=>stash(t,false));

  src = src.replace(/@@CODE(\d+)@@/g, (m,i)=>code[+i]);

  let html;
  try{
    html = marked.parse(src, {breaks:true, gfm:true});
  }catch(e){
    html = '<p>'+esc(src).replace(/\n/g,'<br>')+'</p>';
  }

  html = html.replace(/@@MATH(\d+)@@/g, (m,i)=>{
    const {tex, display} = math[+i];
    if(typeof katex === 'undefined') return esc((display?'$$':'$')+tex+(display?'$$':'$'));
    try{
      return katex.renderToString(tex, {displayMode:display, throwOnError:false, strict:false});
    }catch(e){
      return `<span class="katex-error" title="${esc(e.message)}">${esc(tex)}</span>`;
    }
  });

  if(typeof DOMPurify !== 'undefined'){
    html = DOMPurify.sanitize(html, {ADD_TAGS:['math','semantics','annotation','mrow','mi','mo','mn','msup','msub','mfrac','msqrt','mspace','mtext','munderover','mover','munder','mtable','mtr','mtd','svg','path','line'], ADD_ATTR:['xmlns','encoding','display','mathvariant','stretchy','viewBox','d','style','aria-hidden']});
  }
  // Syntax-highlight fenced C++ blocks produced by marked. Done after sanitising
  // so the highlighter's own markup survives.
  html = html.replace(/<pre><code class="language-(cpp|c\+\+|cc|cxx|c)">([\s\S]*?)<\/code><\/pre>/gi,
    (m, lang, body) => {
      const txt = unescapeHtml(body);
      return `<pre class="code-body cpp-inline"><code>${highlightCpp(txt)}</code></pre>`;
    });
  return html;
}

// Render any KaTeX left inside an already-built DOM node (e.g. chat messages)
function typesetNode(el){
  if(typeof renderMathInElement === 'undefined' || !el) return;
  try{
    renderMathInElement(el, {
      delimiters:[
        {left:'$$', right:'$$', display:true},
        {left:'$',  right:'$',  display:false},
        {left:'\\[', right:'\\]', display:true},
        {left:'\\(', right:'\\)', display:false}
      ],
      throwOnError:false
    });
  }catch(e){}
}

// Live-follow a submission over SSE; falls back to polling if EventSource dies.
function followSubmission(sid, cb){
  return new Promise((resolve)=>{
    let done = false, last = null;
    const finish = (s)=>{ if(!done){ done = true; resolve(s); } };
    let es;
    try{ es = new EventSource(`/api/submission/${sid}/stream`); }
    catch(e){ return pollSubmission(sid, cb).then(finish); }

    es.onmessage = (ev)=>{
      try{
        const s = JSON.parse(ev.data);
        last = s; cb(s);
        if(s.status!=='PENDING' && s.status!=='JUDGING'){ es.close(); finish(s); }
      }catch(e){}
    };
    es.addEventListener('done', ()=>{ es.close(); finish(last); });
    es.onerror = ()=>{
      es.close();
      if(!done) pollSubmission(sid, cb).then(finish);
    };
  });
}


// ---------------------------------------------------------------------------
// C++ syntax highlighting (dependency-free)
// ---------------------------------------------------------------------------
// Tokenises in ONE pass with a combined regex so that keywords inside strings
// or comments are never highlighted (the classic bug with naive replace chains).

const CPP_KEYWORDS = new Set(('alignas alignof and and_eq asm auto bitand bitor bool break case catch '+
  'char char8_t char16_t char32_t class compl concept const consteval constexpr constinit const_cast '+
  'continue co_await co_return co_yield decltype default delete do double dynamic_cast else enum '+
  'explicit export extern false float for friend goto if inline int long mutable namespace new noexcept '+
  'not not_eq nullptr operator or or_eq private protected public register reinterpret_cast requires '+
  'return short signed sizeof static static_assert static_cast struct switch template this thread_local '+
  'throw true try typedef typeid typename union unsigned using virtual void volatile wchar_t while '+
  'xor xor_eq').split(' '));

const CPP_TYPES = new Set(('string vector map set unordered_map unordered_set pair queue deque stack '+
  'priority_queue array tuple size_t ssize_t int8_t int16_t int32_t int64_t uint8_t uint16_t uint32_t '+
  'uint64_t ptrdiff_t istream ostream stringstream ifstream ofstream').split(' '));

function highlightCpp(code){
  const src = String(code == null ? '' : code);
  // order matters: comments and strings first so their contents stay literal
  const re = /(\/\/[^\n]*|\/\*[\s\S]*?\*\/)|(^[ \t]*#[^\n]*)|("(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*')|(\b\d+(?:\.\d+)?(?:[eE][+-]?\d+)?[uUlLfF]*\b|\b0[xX][0-9a-fA-F]+\b)|([A-Za-z_]\w*)/gm;
  let out = '', last = 0, m;
  while((m = re.exec(src)) !== null){
    out += esc(src.slice(last, m.index));
    last = re.lastIndex;
    const [tok, comment, pre, str, num, word] = m;
    if(comment)      out += `<span class="c-cmt">${esc(tok)}</span>`;
    else if(pre)     out += `<span class="c-pre">${esc(tok)}</span>`;
    else if(str)     out += `<span class="c-str">${esc(tok)}</span>`;
    else if(num)     out += `<span class="c-num">${esc(tok)}</span>`;
    else if(word){
      if(CPP_KEYWORDS.has(word))   out += `<span class="c-kw">${esc(tok)}</span>`;
      else if(CPP_TYPES.has(word)) out += `<span class="c-typ">${esc(tok)}</span>`;
      // a name directly followed by '(' is a call/definition
      else if(src[re.lastIndex] === '(') out += `<span class="c-fn">${esc(tok)}</span>`;
      else out += esc(tok);
    }
    else out += esc(tok);
  }
  out += esc(src.slice(last));
  return out;
}

// Render a highlighted, copyable C++ block.
function cppBlock(code, label){
  return `<div class="code-block">
    <div class="code-bar"><span>${esc(label||'C++')}</span>
      <button class="copy-btn" onclick="copyFrom(this)">复制</button></div>
    <pre class="code-body"><code>${highlightCpp(code)}</code></pre>
    <textarea class="copy-src" hidden>${esc(code)}</textarea>
  </div>`;
}

// A copyable block for plain text (test data, logs) — no syntax colouring.
function textBlock(text, label){
  return `<div class="code-block">
    <div class="code-bar"><span>${esc(label||'文本')}</span>
      <button class="copy-btn" onclick="copyFrom(this)">复制</button></div>
    <pre class="code-body">${esc(text == null ? '' : text)}</pre>
    <textarea class="copy-src" hidden>${esc(text == null ? '' : text)}</textarea>
  </div>`;
}

// ---------------------------------------------------------------------------
// Copy helper
// ---------------------------------------------------------------------------
function copyText(text, btn){
  const done = ()=>{
    if(!btn) return;
    const old = btn.textContent;
    btn.textContent = '已复制';
    btn.classList.add('copied');
    setTimeout(()=>{ btn.textContent = old; btn.classList.remove('copied'); }, 1200);
  };
  if(navigator.clipboard && window.isSecureContext){
    navigator.clipboard.writeText(text).then(done).catch(()=>fallbackCopy(text, done));
  } else {
    fallbackCopy(text, done);
  }
}
function fallbackCopy(text, done){
  // clipboard API needs HTTPS; plain-HTTP deployments fall back to execCommand
  const ta = document.createElement('textarea');
  ta.value = text;
  ta.style.cssText = 'position:fixed;top:-1000px;opacity:0;';
  document.body.appendChild(ta);
  ta.select();
  try{ document.execCommand('copy'); done && done(); }catch(e){}
  ta.remove();
}
// Copy the sibling .copy-src of a button.
function copyFrom(btn){
  const box = btn.closest('.code-block, .sample-box');
  const src = box && box.querySelector('.copy-src');
  if(src) copyText(src.value, btn);
}

// ---------------------------------------------------------------------------
// Sample groups
// ---------------------------------------------------------------------------
// Accepts the structured list [{input, output, note}]. Falls back to the legacy
// free-text `samples` field so old problems keep rendering.
function renderSampleGroups(groups, legacy){
  const list = (groups || []).filter(g => (g.input || '').trim() || (g.output || '').trim());
  if(!list.length){
    if(!legacy || !legacy.trim()) return '';
    return `<h2>样例</h2><pre>${esc(legacy)}</pre>`;
  }
  return '<h2>样例</h2>' + list.map((g, i) => `
    <div class="sample-group">
      <div class="sample-title">样例 ${i + 1}</div>
      <div class="sample-grid">
        <div class="sample-box">
          <div class="code-bar"><span>输入</span>
            <button class="copy-btn" onclick="copyFrom(this)">复制</button></div>
          <pre class="sample-body">${esc(g.input || '')}</pre>
          <textarea class="copy-src" hidden>${esc(g.input || '')}</textarea>
        </div>
        <div class="sample-box">
          <div class="code-bar"><span>输出</span>
            <button class="copy-btn" onclick="copyFrom(this)">复制</button></div>
          <pre class="sample-body">${esc(g.output || '')}</pre>
          <textarea class="copy-src" hidden>${esc(g.output || '')}</textarea>
        </div>
      </div>
      ${g.note && g.note.trim() ? `<div class="sample-note">${renderStatement(g.note)}</div>` : ''}
    </div>`).join('');
}

// Poll a submission until judged (fallback path)
async function pollSubmission(sid, cb){
  while(true){
    const s = await API.get(`/api/submission/${sid}`);
    cb(s);
    if(s.status!=='PENDING' && s.status!=='JUDGING') return s;
    await new Promise(r=>setTimeout(r,800));
  }
}

// Difficulty chip (hidden during a running contest)
function difficultyBadge(d, hidden){
  if(hidden) return '<span class="difficulty diff-hidden" title="比赛期间隐藏难度">???</span>';
  if(!d) return '';
  const cls = {'入门':'diff-gray','普及-':'diff-red2','普及':'diff-orange','普及+':'diff-orange',
               '提高':'diff-green','提高+':'diff-blue','省选':'diff-blue','NOI-':'diff-purple',
               'NOI':'diff-purple','NOI+':'diff-black'}[d]||'diff-gray';
  return `<span class="difficulty ${cls}">${esc(d)}</span>`;
}

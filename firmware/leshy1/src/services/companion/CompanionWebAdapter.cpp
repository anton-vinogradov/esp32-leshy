#include "CompanionWebAdapter.h"

#include <array>
#include <cstdio>
#include <cstring>

namespace leshy1::services::companion {
namespace {

bool exact(const char* value, std::size_t length, const char* expected) {
    return value != nullptr && expected != nullptr &&
        length == std::strlen(expected) &&
        std::memcmp(value, expected, length) == 0;
}

constexpr char kIndexHtml[] = R"LESHYHTML(<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Leshy local</title><style>
:root{color-scheme:dark;--bg:#081019;--panel:#101c28;--line:#26394a;--text:#eef6ff;--muted:#91a7b9;--cyan:#3fe0d0;--amber:#ffc15a;--bad:#ff6b74}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:15px system-ui,sans-serif}header{height:52px;display:flex;align-items:center;gap:12px;padding:0 16px;border-bottom:1px solid var(--line);background:#0c1722;position:sticky;top:0}h1{font-size:18px;margin:0;flex:1}.status{color:var(--muted)}.status.ok{color:var(--cyan)}.status.bad{color:var(--bad)}
nav,.tools{display:flex;gap:8px;padding:12px 16px 0;flex-wrap:wrap}button,input{min-height:42px;border:1px solid var(--line);border-radius:8px;background:#152536;color:var(--text);padding:8px 14px;font:inherit}input{flex:1;min-width:180px}button:hover,button:focus,input:focus{border-color:var(--cyan)}button.active{background:#17413f;border-color:var(--cyan)}button.warn{border-color:var(--amber)}main{padding:12px 16px 24px}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:10px}.card{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:12px;min-height:92px}.card h2{font-size:16px;margin:0 0 8px}.meta{color:var(--muted);font-size:13px;word-break:break-all}.favorite{color:var(--amber)}pre{white-space:pre-wrap;word-break:break-word;margin:8px 0 0;color:#cfe5f5}.empty{color:var(--muted);padding:28px 4px}.actions{display:flex;gap:8px;margin-top:10px;flex-wrap:wrap}summary{color:var(--cyan);cursor:pointer;margin-top:10px}@media(max-width:520px){header{padding:0 10px}nav,.tools,main{padding-left:10px;padding-right:10px}nav button{flex:1;padding:6px}.grid{grid-template-columns:1fr}}
</style></head><body><header><h1>LESHY · LOCAL</h1><span id="status" class="status">connecting</span></header>
<nav><button data-view="sessions" class="active">Sessions</button><button data-view="targets">Targets</button><button data-view="compare">Compare</button></nav>
<section class="tools"><input id="search" type="search" placeholder="Find a target by name, note, tag or radio ID" aria-label="Find a target"><button id="export">Export snapshot</button></section>
<main><div id="content" class="empty">Opening the device session…</div></main>
<script src="/app.js"></script>
</body></html>)LESHYHTML";

constexpr char kAppJavascript[] = R"LESHYJS(
const API='/api/v1/companion',SCHEMA='leshy.companion.request.v1',OFFLINE='leshy.companion.offline.v1';let seq=0,sessions=[],targets=[],fullTargets=null,current='sessions',searchTimer;
const id=()=>`web-${++seq}`,hex=h=>{try{return decodeURIComponent((h.match(/../g)||[]).map(x=>'%'+x).join(''))}catch{return h}},esc=v=>String(v).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])),el=document.querySelector('#content'),status=document.querySelector('#status'),search=document.querySelector('#search');
async function call(message){const response=await fetch(API,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({schema:SCHEMA,request_id:id(),...message})});const value=await response.json();if(!response.ok||value.status==='error'||value.status==='denied')throw Error(value.reason||`HTTP ${response.status}`);return value}
function card(title,meta,extra='',leading=''){return `<article class="card"><h2>${leading}${esc(title)}</h2><div class="meta">${esc(meta).replaceAll('\n','<br>')}</div>${extra}</article>`}
async function connect(){await call({kind:'connect',protocol:1,scopes:['session.read','target.read','target.compare','target.mutate']});status.textContent='local · ready';status.className='status ok';await show('sessions')}
async function pages(kind,extra={}){let items=[],offset=0,last;for(let n=0;n<16;n++){last=await call({kind,offset,...extra});items.push(...(last.items||[]));if(last.next_offset===null)return{items,last};if(!Number.isInteger(last.next_offset)||last.next_offset<=offset)break;offset=last.next_offset}throw Error('pagination_limit')}
async function loadSessions(force=false){if(!sessions.length||force)sessions=(await pages('session.list')).items;return sessions}
async function loadTargets(force=false){if(!targets.length||force){targets=(await pages('target.list')).items;fullTargets=null}return targets}
async function notesOf(target_id){let value='',offset=0;for(let n=0;n<4;n++){const page=await call({kind:'target.detail',target_id,section:'notes',offset});value+=page.value||'';if(page.next_offset===null)return value;offset=page.next_offset}throw Error('notes_pagination_limit')}
async function targetDetails(t){const target_id=t.target_id,summary=await call({kind:'target.detail',target_id,section:'summary',offset:0}),notes_hex=await notesOf(target_id),tags_hex=(await pages('target.detail',{target_id,section:'tags'})).items,identities=(await pages('target.detail',{target_id,section:'identities'})).items,evidence=(await pages('target.detail',{target_id,section:'evidence'})).items;return{target_id,revision:summary.revision,favorite:summary.favorite,name_hex:summary.name_hex,notes_hex,tags_hex,identities,evidence}}
async function loadFullTargets(){if(fullTargets)return fullTargets;await loadTargets();status.textContent='collecting details…';fullTargets=[];for(const t of targets)fullTargets.push(await targetDetails(t));status.textContent='local · ready';status.className='status ok';return fullTargets}
async function comparison(){await loadSessions();if(sessions.length!==2)throw Error('comparison_requires_two_sessions');const baseline={source_id:sessions[0].source_id,generation:sessions[0].generation},current={source_id:sessions[1].source_id,generation:sessions[1].generation},page=await pages('target.compare',{baseline_source_id:baseline.source_id,baseline_generation:baseline.generation,current_source_id:current.source_id,current_generation:current.generation});return{baseline,current,counts:page.last.counts||{},items:page.items}}
function renderTargets(list){el.innerHTML=list.length?list.map(t=>card(hex(t.name_hex)||'Unnamed target',`revision ${t.revision} · ${(t.identities||[]).length||t.identity_count} identities · ${(t.evidence||[]).length||t.evidence_count} evidence\n${t.target_id}`,`<div class="actions"><button onclick="detailsId('${t.target_id}')">Details</button><button class="warn" onclick="favoriteId('${t.target_id}')">${t.favorite?'Remove favorite':'Favorite'}</button></div>`,t.favorite?'<span class="favorite">★</span> ':'')).join(''):'<div class="empty">No matching targets</div>'}
function targetMatches(t,q){const compact=q.replace(/[^0-9a-f]/g,''),values=[hex(t.name_hex),hex(t.notes_hex),...(t.tags_hex||[]).map(hex),...(t.identities||[]).flatMap(i=>[i.kind,i.value,i.value.replace(/[^0-9a-f]/gi,'')])].map(v=>String(v).toLocaleLowerCase());return values.some(v=>v.includes(q)||(compact&&v.includes(compact)))}
async function show(view){current=view;document.querySelectorAll('nav button').forEach(b=>b.classList.toggle('active',b.dataset.view===view));el.className='grid';if(view==='sessions'){await loadSessions();el.innerHTML=sessions.length?sessions.map(s=>card(s.session_id,`${s.observations} observations · generation ${s.generation}\n${s.source_id}`)).join(''):'<div class="empty">No stopped sessions</div>'}else if(view==='targets'){await loadTargets();const q=search.value.trim().toLocaleLowerCase();renderTargets(q?(await loadFullTargets()).filter(t=>targetMatches(t,q)):targets)}else{const c=await comparison();el.innerHTML=card('Summary',`${c.counts.added||0} new · ${c.counts.removed||0} gone · ${c.counts.changed||0} changed · ${c.counts.unchanged||0} unchanged`)+c.items.map(r=>card(r.class,`changes ${r.changes} · evidence ${r.baseline_evidence}/${r.current_evidence}\n${r.target_id}`)).join('')}}
async function detailsId(target_id){const all=await loadFullTargets(),t=all.find(x=>x.target_id===target_id);if(!t)throw Error('target_not_found');const identities=t.identities.map(i=>`${i.kind}: ${i.value}`).join('\n')||'No radio identities',tags=t.tags_hex.map(hex).join(', ')||'No tags',notes=hex(t.notes_hex)||'No notes';el.innerHTML=card(hex(t.name_hex)||'Unnamed target',`revision ${t.revision} · ${t.favorite?'favorite · ':''}${tags}\n${notes}`,`<pre>${esc(identities)}</pre><details><summary>Technical evidence</summary><pre>${esc(JSON.stringify(t.evidence,null,2))}</pre></details><div class="actions"><button onclick="show('targets')">Targets</button></div>`)}
async function favoriteId(target_id){const t=targets.find(x=>x.target_id===target_id);if(!t)throw Error('target_not_found');const preview=await call({kind:'target.mutation.preview',action:'target.favorite.set',target_id,expected_revision:t.revision,favorite:!t.favorite});if(!confirm(`${t.favorite?'Remove from':'Add to'} favorites?\nRevision ${t.revision} → ${preview.target_revision}`))return;await call({kind:'target.mutation.confirm',mutation_id:preview.mutation_id});for(let n=0;n<30;n++){await new Promise(r=>setTimeout(r,100));const state=await call({kind:'target.mutation.status',mutation_id:preview.mutation_id});if(state.state==='saved'){targets=[];fullTargets=null;await show('targets');return}if(state.state==='failed')throw Error(state.reason)}throw Error('mutation_timeout')}
const K=[],H=[],R=(x,n)=>(x>>>n)|(x<<(32-n));for(let n=2,p=0;p<64;n++){let prime=true;for(let d=2;d*d<=n;d++)if(n%d===0){prime=false;break}if(prime){if(p<8)H[p]=(Math.sqrt(n)%1*4294967296)>>>0;K[p++]=(Math.cbrt(n)%1*4294967296)>>>0}}
function sha256(text){const b=[...new TextEncoder().encode(text)],bits=b.length*8;b.push(128);while(b.length%64!==56)b.push(0);const hi=Math.floor(bits/4294967296),lo=bits>>>0;for(let n=3;n>=0;n--)b.push((hi>>>(n*8))&255);for(let n=3;n>=0;n--)b.push((lo>>>(n*8))&255);const h=H.slice(),w=new Uint32Array(64);for(let o=0;o<b.length;o+=64){for(let i=0;i<16;i++)w[i]=((b[o+4*i]<<24)|(b[o+4*i+1]<<16)|(b[o+4*i+2]<<8)|b[o+4*i+3])>>>0;for(let i=16;i<64;i++){const x=w[i-15],y=w[i-2],s0=R(x,7)^R(x,18)^(x>>>3),s1=R(y,17)^R(y,19)^(y>>>10);w[i]=(w[i-16]+s0+w[i-7]+s1)>>>0}let[a,c,d,e,f,g,j,k]=h;for(let i=0;i<64;i++){const s1=R(f,6)^R(f,11)^R(f,25),ch=(f&g)^(~f&j),t1=(k+s1+ch+K[i]+w[i])>>>0,s0=R(a,2)^R(a,13)^R(a,22),maj=(a&c)^(a&d)^(c&d),t2=(s0+maj)>>>0;k=j;j=g;g=f;f=(e+t1)>>>0;e=d;d=c;c=a;a=(t1+t2)>>>0}h[0]=(h[0]+a)>>>0;h[1]=(h[1]+c)>>>0;h[2]=(h[2]+d)>>>0;h[3]=(h[3]+e)>>>0;h[4]=(h[4]+f)>>>0;h[5]=(h[5]+g)>>>0;h[6]=(h[6]+j)>>>0;h[7]=(h[7]+k)>>>0}return h.map(x=>x.toString(16).padStart(8,'0')).join('')}
if(sha256('abc')!=='ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad')throw Error('snapshot_integrity_unavailable');
const stable=v=>Array.isArray(v)?v.map(stable):v&&typeof v==='object'?Object.fromEntries(Object.keys(v).sort().map(k=>[k,stable(v[k])])):v;
async function exportSnapshot(){status.textContent='building snapshot…';await loadSessions(true);const sessionDetails=[];for(const s of sessions){const d=await call({kind:'session.detail',source_id:s.source_id,generation:s.generation});sessionDetails.push({session_id:d.session_id,source_id:d.source_id,generation:d.generation,state:d.state,started_us:d.started_us,stopped_us:d.stopped_us,observations:d.observations,dropped:d.dropped})}const all=await loadFullTargets(),compare=await comparison(),snapshot={schema:OFFLINE,kind:'snapshot',protocol:1,source_transport:'local_web_json',complete:true,snapshot_id:'',counts:{sessions:sessionDetails.length,targets:all.length,comparison_items:compare.items.length},sessions:sessionDetails,targets:all,comparison:compare};const unsigned={...snapshot};delete unsigned.snapshot_id;snapshot.snapshot_id=sha256(JSON.stringify(stable(unsigned)));const payload=JSON.stringify(stable(snapshot))+'\n',url=URL.createObjectURL(new Blob([payload],{type:'application/json'})),a=document.createElement('a');a.href=url;a.download=`leshy-${snapshot.snapshot_id.slice(0,12)}.json`;a.click();URL.revokeObjectURL(url);status.textContent='snapshot saved';status.className='status ok';setTimeout(()=>status.textContent='local · ready',1500)}
document.querySelectorAll('nav button').forEach(b=>b.onclick=()=>show(b.dataset.view).catch(fail));search.oninput=()=>{clearTimeout(searchTimer);searchTimer=setTimeout(()=>show('targets').catch(fail),250)};document.querySelector('#export').onclick=()=>exportSnapshot().catch(fail);function fail(error){status.textContent=error.message;status.className='status bad';el.className='empty';el.textContent='Unavailable: '+error.message}connect().catch(fail);
)LESHYJS";

#include "CompanionWebIndexGzip.inc"
#include "CompanionWebAppGzip.inc"

}  // namespace

const char* companionWebReason(CompanionWebStatus status) {
    switch (status) {
        case CompanionWebStatus::Ready: return "none";
        case CompanionWebStatus::InvalidArgument: return "invalid_argument";
        case CompanionWebStatus::SessionUnavailable:
            return "device_session_unavailable";
        case CompanionWebStatus::NotFound: return "not_found";
        case CompanionWebStatus::MethodNotAllowed: return "method_not_allowed";
        case CompanionWebStatus::UnsupportedMediaType:
            return "unsupported_media_type";
        case CompanionWebStatus::ChunkedUnsupported:
            return "chunked_body_unsupported";
        case CompanionWebStatus::UnexpectedBody: return "unexpected_body";
        case CompanionWebStatus::EmptyBody: return "empty_body";
        case CompanionWebStatus::LengthMismatch: return "length_mismatch";
        case CompanionWebStatus::BodyTooLarge: return "frame_too_large";
    }
    return "invalid_status";
}

std::uint16_t companionWebHttpStatus(CompanionWebStatus status) {
    switch (status) {
        case CompanionWebStatus::Ready: return 200;
        case CompanionWebStatus::InvalidArgument:
        case CompanionWebStatus::UnexpectedBody:
        case CompanionWebStatus::EmptyBody:
        case CompanionWebStatus::LengthMismatch:
            return 400;
        case CompanionWebStatus::SessionUnavailable: return 403;
        case CompanionWebStatus::NotFound: return 404;
        case CompanionWebStatus::MethodNotAllowed: return 405;
        case CompanionWebStatus::BodyTooLarge: return 413;
        case CompanionWebStatus::UnsupportedMediaType: return 415;
        case CompanionWebStatus::ChunkedUnsupported: return 411;
    }
    return 500;
}

CompanionWebStatus validateCompanionWebRequest(
    const CompanionWebRequestMetadata& metadata,
    const char* body, std::size_t bodyLength,
    CompanionWebRequest* output) {
    if (output == nullptr || metadata.path == nullptr ||
        metadata.pathLength == 0 || (body == nullptr && bodyLength != 0)) {
        return CompanionWebStatus::InvalidArgument;
    }
    if (!metadata.deviceSessionAuthorized) {
        return CompanionWebStatus::SessionUnavailable;
    }

    CompanionWebRequest candidate{};
    const bool index = exact(metadata.path, metadata.pathLength,
                             kCompanionWebIndexPath);
    const bool app = exact(metadata.path, metadata.pathLength,
                           kCompanionWebAppPath);
    const bool api = exact(metadata.path, metadata.pathLength,
                           kCompanionWebApiPath);
    if (!index && !app && !api) return CompanionWebStatus::NotFound;
    if (((index || app) && metadata.method != CompanionWebMethod::Get) ||
        (api && metadata.method != CompanionWebMethod::Post)) {
        return CompanionWebStatus::MethodNotAllowed;
    }
    if (metadata.chunked) return CompanionWebStatus::ChunkedUnsupported;

    if (index || app) {
        if (metadata.declaredContentLength != 0 || bodyLength != 0) {
            return CompanionWebStatus::UnexpectedBody;
        }
        candidate.route = index ? CompanionWebRoute::Index
                                : CompanionWebRoute::App;
        *output = candidate;
        return CompanionWebStatus::Ready;
    }

    if (!exact(metadata.contentType, metadata.contentTypeLength,
               kCompanionWebJsonContentType)) {
        return CompanionWebStatus::UnsupportedMediaType;
    }
    if (metadata.declaredContentLength == 0 || bodyLength == 0) {
        return CompanionWebStatus::EmptyBody;
    }
    if (metadata.declaredContentLength > kCompanionMaxFrameBytes ||
        bodyLength > kCompanionMaxFrameBytes) {
        return CompanionWebStatus::BodyTooLarge;
    }
    if (metadata.declaredContentLength != bodyLength) {
        return CompanionWebStatus::LengthMismatch;
    }
    candidate.route = CompanionWebRoute::CompanionApi;
    candidate.body = body;
    candidate.bodyLength = bodyLength;
    *output = candidate;
    return CompanionWebStatus::Ready;
}

bool encodeCompanionWebError(
    CompanionWebStatus status, char* output, std::size_t capacity,
    std::size_t* outputLength) {
    if (outputLength != nullptr) *outputLength = 0;
    if (output == nullptr || outputLength == nullptr ||
        status == CompanionWebStatus::Ready) {
        return false;
    }
    std::array<char, 192> scratch{};
    const int written = std::snprintf(
        scratch.data(), scratch.size(),
        "{\"schema\":\"%s\",\"kind\":\"error\","
        "\"request_id\":\"\",\"status\":\"error\",\"reason\":\"%s\"}\n",
        kCompanionResponseSchema, companionWebReason(status));
    if (written <= 0 || static_cast<std::size_t>(written) >= scratch.size() ||
        static_cast<std::size_t>(written) >= capacity) {
        return false;
    }
    std::memcpy(output, scratch.data(), static_cast<std::size_t>(written) + 1U);
    *outputLength = static_cast<std::size_t>(written);
    return true;
}

const char* companionWebIndexHtml(std::size_t* length) {
    if (length != nullptr) *length = sizeof(kIndexHtml) - 1U;
    return kIndexHtml;
}

const std::uint8_t* companionWebIndexGzip(std::size_t* length) {
    if (length != nullptr) *length = sizeof(kIndexHtmlGzip);
    return kIndexHtmlGzip;
}

const char* companionWebAppJavascript(std::size_t* length) {
    if (length != nullptr) *length = sizeof(kAppJavascript) - 1U;
    return kAppJavascript;
}

const std::uint8_t* companionWebAppGzip(std::size_t* length) {
    if (length != nullptr) *length = sizeof(kAppJavascriptGzip);
    return kAppJavascriptGzip;
}

}  // namespace leshy1::services::companion

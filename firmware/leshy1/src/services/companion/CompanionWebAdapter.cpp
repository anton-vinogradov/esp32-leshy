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
nav{display:flex;gap:8px;padding:12px 16px 0}button{min-height:42px;border:1px solid var(--line);border-radius:8px;background:#152536;color:var(--text);padding:8px 14px;font:inherit}button:hover,button:focus{border-color:var(--cyan)}button.active{background:#17413f;border-color:var(--cyan)}button.warn{border-color:var(--amber)}main{padding:12px 16px 24px}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:10px}.card{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:12px;min-height:92px}.card h2{font-size:16px;margin:0 0 8px}.meta{color:var(--muted);font-size:13px;word-break:break-all}.favorite{color:var(--amber)}pre{white-space:pre-wrap;word-break:break-word;margin:8px 0 0;color:#cfe5f5}.empty{color:var(--muted);padding:28px 4px}.actions{display:flex;gap:8px;margin-top:10px;flex-wrap:wrap}@media(max-width:520px){header{padding:0 10px}nav,main{padding-left:10px;padding-right:10px}nav button{flex:1;padding:6px}.grid{grid-template-columns:1fr}}
</style></head><body><header><h1>LESHY · LOCAL</h1><span id="status" class="status">connecting</span></header>
<nav><button data-view="sessions" class="active">Sessions</button><button data-view="targets">Targets</button><button data-view="compare">Compare</button></nav>
<main><div id="content" class="empty">Opening the device session…</div></main>
<script>
const API='/api/v1/companion',SCHEMA='leshy.companion.request.v1';let seq=0,sessions=[],targets=[];
const id=()=>`web-${++seq}`,hex=h=>{try{return decodeURIComponent((h.match(/../g)||[]).map(x=>'%'+x).join(''))}catch{return h}},esc=v=>String(v).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])),el=document.querySelector('#content'),status=document.querySelector('#status');
async function call(message){const response=await fetch(API,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({schema:SCHEMA,request_id:id(),...message})});const value=await response.json();if(!response.ok||value.status==='error'||value.status==='denied')throw Error(value.reason||`HTTP ${response.status}`);return value}
function card(title,meta,extra='',leading=''){return `<article class="card"><h2>${leading}${esc(title)}</h2><div class="meta">${esc(meta).replaceAll('\n','<br>')}</div>${extra}</article>`}
async function connect(){await call({kind:'connect',protocol:1,scopes:['session.read','target.read','target.compare','target.mutate']});status.textContent='local · ready';status.className='status ok';await show('sessions')}
async function loadSessions(){sessions=(await call({kind:'session.list',offset:0})).items||[];return sessions}
async function loadTargets(){targets=[];let offset=0;do{const page=await call({kind:'target.list',offset});targets.push(...(page.items||[]));offset=page.next_offset}while(offset!==null);return targets}
async function show(view){document.querySelectorAll('nav button').forEach(b=>b.classList.toggle('active',b.dataset.view===view));el.className='grid';if(view==='sessions'){await loadSessions();el.innerHTML=sessions.length?sessions.map(s=>card(s.session_id,`${s.observations} observations · generation ${s.generation}\n${s.source_id}`)).join(''):'<div class="empty">No stopped sessions</div>'}else if(view==='targets'){await loadTargets();el.innerHTML=targets.length?targets.map((t,i)=>card(hex(t.name_hex)||'Unnamed target',`revision ${t.revision} · ${t.identity_count} identities · ${t.evidence_count} evidence\n${t.target_id}`,`<div class="actions"><button onclick="details(${i})">Details</button><button class="warn" onclick="favorite(${i})">${t.favorite?'Remove favorite':'Favorite'}</button></div>`,t.favorite?'<span class="favorite">★</span> ':'')).join(''):'<div class="empty">No targets</div>'}else{await loadSessions();if(sessions.length!==2){el.innerHTML='<div class="empty">Comparison requires the exact two-session snapshot</div>';return}let rows=[],offset=0,last;do{last=await call({kind:'target.compare',baseline_source_id:sessions[0].source_id,baseline_generation:sessions[0].generation,current_source_id:sessions[1].source_id,current_generation:sessions[1].generation,offset});rows.push(...(last.items||[]));offset=last.next_offset}while(offset!==null);const c=last.counts||{};el.innerHTML=card('Summary',`${c.added||0} new · ${c.removed||0} gone · ${c.changed||0} changed · ${c.unchanged||0} unchanged`)+rows.map(r=>card(r.class,`changes ${r.changes} · evidence ${r.baseline_evidence}/${r.current_evidence}\n${r.target_id}`)).join('')}}
async function details(index){const t=targets[index],d=await call({kind:'target.detail',target_id:t.target_id,section:'summary',offset:0});el.innerHTML=card(hex(d.name_hex)||'Unnamed target',`revision ${d.revision} · favorite ${d.favorite}\n${d.target_id}`,`<pre>${esc(JSON.stringify(d,null,2))}</pre><div class="actions"><button onclick="show('targets')">Targets</button></div>`)}
async function favorite(index){const t=targets[index],preview=await call({kind:'target.mutation.preview',action:'target.favorite.set',target_id:t.target_id,expected_revision:t.revision,favorite:!t.favorite});if(!confirm(`${t.favorite?'Remove from':'Add to'} favorites?\nRevision ${t.revision} → ${preview.target_revision}`))return;await call({kind:'target.mutation.confirm',mutation_id:preview.mutation_id});for(let n=0;n<30;n++){await new Promise(r=>setTimeout(r,100));const state=await call({kind:'target.mutation.status',mutation_id:preview.mutation_id});if(state.state==='saved'){await show('targets');return}if(state.state==='failed')throw Error(state.reason)}throw Error('mutation_timeout')}
document.querySelectorAll('nav button').forEach(b=>b.onclick=()=>show(b.dataset.view).catch(fail));function fail(error){status.textContent=error.message;status.className='status bad';el.className='empty';el.textContent='Unavailable: '+error.message}connect().catch(fail);
</script></body></html>)LESHYHTML";

#include "CompanionWebIndexGzip.inc"

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
    const bool api = exact(metadata.path, metadata.pathLength,
                           kCompanionWebApiPath);
    if (!index && !api) return CompanionWebStatus::NotFound;
    if ((index && metadata.method != CompanionWebMethod::Get) ||
        (api && metadata.method != CompanionWebMethod::Post)) {
        return CompanionWebStatus::MethodNotAllowed;
    }
    if (metadata.chunked) return CompanionWebStatus::ChunkedUnsupported;

    if (index) {
        if (metadata.declaredContentLength != 0 || bodyLength != 0) {
            return CompanionWebStatus::UnexpectedBody;
        }
        candidate.route = CompanionWebRoute::Index;
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

}  // namespace leshy1::services::companion

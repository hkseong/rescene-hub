"use strict";
const CFG = window.HUB_CONFIG;
const MEMBERS = ["원이", "리브", "미나미", "메이", "제나"];
const FILES = ["chart", "videos", "albums", "events", "votes", "members", "theme", "status", "news", "alerts", "usage"];
const TYPE_LABEL = { broadcast: "방송", event: "행사", popup: "팝업", collab: "콜라보", goods: "굿즈", ad: "광고", award: "1위·수상", vote: "투표", release: "발매" };
const JOB_LABEL = { youtube: "유튜브 공식", appearances: "출연 영상", melon_chart: "멜론 차트", melon_albums: "앨범", melon_vote: "주간 인기상", events: "일정·뉴스", archive: "지난 이력", profile: "프로필", theme: "테마" };
const RT_CATS = [
  ["broadcast", "오늘 방송·행사 (1~2시간 전)"], ["vote", "투표 순위 변동·마감 임박"], ["award", "음방 1위·수상"],
  ["video", "공식 채널 새 영상·조회수 돌파"], ["appearance", "타 채널 출연·무대 영상"], ["chart", "멜론 차트 진입·TOP10·1위"],
  ["popup", "팝업·콜라보·광고 새 소식"], ["app", "앱 업데이트 (새 기능 안내)"],
];
const RT_DEFAULT_ON = new Set(["app"]);

const D = {};
const ui = {
  member: store("member") || "전체",
  vgroup: "all", vsort: "new", vshorts: false, vlimit: 30,
  calMonth: null, calDay: null, albumType: "all",
};

// ---------- utils ----------
function store(k, v) {
  try {
    if (v === undefined) return JSON.parse(localStorage.getItem("hub:" + k));
    localStorage.setItem("hub:" + k, JSON.stringify(v));
  } catch (e) { return null; }
}
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const $ = (sel, el = document) => el.querySelector(sel);
const kstNow = () => new Date(Date.now() + 9 * 3600e3);
const todayStr = () => kstNow().toISOString().slice(0, 10);
const addDays = (s, n) => { const d = new Date(s + "T00:00:00Z"); d.setUTCDate(d.getUTCDate() + n); return d.toISOString().slice(0, 10); };
const daysBetween = (a, b) => Math.round((new Date(b + "T00:00:00Z") - new Date(a + "T00:00:00Z")) / 864e5);
function fmtCount(n) {
  if (n == null) return "";
  if (n >= 1e8) return (n / 1e8).toFixed(n >= 1e9 ? 0 : 1).replace(/\.0$/, "") + "억";
  if (n >= 1e4) return (n / 1e4).toFixed(n >= 1e6 ? 0 : 1).replace(/\.0$/, "") + "만";
  return n.toLocaleString("ko-KR");
}
function ago(iso) {
  const s = (Date.now() - new Date(iso)) / 1000;
  if (s < 60) return "방금";
  if (s < 3600) return Math.floor(s / 60) + "분 전";
  if (s < 86400) return Math.floor(s / 3600) + "시간 전";
  if (s < 86400 * 30) return Math.floor(s / 86400) + "일 전";
  return new Date(iso).toLocaleDateString("ko-KR", { year: "2-digit", month: "numeric", day: "numeric" });
}
const md = (s) => s ? `${+s.slice(5, 7)}/${+s.slice(8, 10)}` : "";
const dow = (s) => "일월화수목금토"[new Date(s + "T00:00:00Z").getUTCDay()];
function span(e) {
  let t = md(e.date) + `(${dow(e.date)})`;
  if (e.end_date && e.end_date !== e.date) t += " ~ " + md(e.end_date);
  if (e.time) t += " " + e.time;
  return t;
}
const memberMatch = (list, strict) => ui.member === "전체" || (list || []).includes(ui.member) || (!strict && (!list || !list.length));

// ---------- data ----------
// 큰 파일(videos)은 따로 기다릴 수 있게 Promise를 돌려준다.
function loadAll() {
  const bucket = Math.floor(Date.now() / 120000);
  const jobs = Object.fromEntries(FILES.map((f) => [f, (async () => {
    try {
      const r = await fetch(`${CFG.dataBase}${f}.json?v=${bucket}`, { cache: "no-cache" });
      D[f] = r.ok ? await r.json() : null;
    } catch (e) { D[f] = null; }
  })()]));
  const small = Promise.all(FILES.filter((f) => f !== "videos").map((f) => jobs[f]));
  return { small, all: Promise.all(Object.values(jobs)) };
}

function applyTheme() {
  const t = D.theme;
  if (!t || !t.colors) return;
  const map = { bg: "--bg", surface: "--surface", text: "--text", muted: "--muted", primary: "--primary", on_primary: "--on-primary", accent: "--accent", grad_from: "--grad-from", grad_to: "--grad-to" };
  for (const [k, v] of Object.entries(map)) if (t.colors[k]) document.documentElement.style.setProperty(v, t.colors[k]);
  $('meta[name="theme-color"]').content = t.colors.grad_from || t.colors.bg;
  $("#mood").textContent = t.album && t.album !== "default" ? `${t.album} · ${t.mood}` : "리센느 활동 정보 자동 모아보기";
}

function staleJobs(jobs) {
  const st = D.status?.jobs || {};
  return jobs.filter((j) => {
    const s = st[j];
    if (!s) return false;
    if (!s.last_success) return true;
    return (Date.now() - new Date(s.last_success)) / 60000 > Math.max(3 * s.interval_min, 90);
  });
}
function staleBanner(jobs) {
  const bad = staleJobs(jobs);
  if (!bad.length) return "";
  const last = bad.map((j) => `${JOB_LABEL[j] || j} (마지막 갱신 ${D.status.jobs[j].last_success ? ago(D.status.jobs[j].last_success) : "없음"})`).join(", ");
  return `<div class="card stale">⚠️ 업데이트 지연: ${esc(last)}. 자동 복구를 진행 중이에요.</div>`;
}

// ---------- derived ----------
function events() { return (D.events?.events || []).filter((e) => memberMatch(e.members, false)); }
function anniversaries(from, days) {
  const out = [];
  const base = [[CFG.debut, "리센느 데뷔 {n}주년"]];
  for (const [name, m] of Object.entries(D.members?.members || {})) if (m.birthday && memberMatch([name], true)) base.push([m.birthday, `${name} 생일`, true]);
  for (const a of D.albums?.albums || []) if (["EP", "정규", "싱글"].includes(a.type) && ui.member === "전체") base.push([a.date, `'${a.title}' 발매 {n}주년`]);
  const y0 = +from.slice(0, 4);
  for (const [src, label] of base) {
    for (const y of [y0 - 1, y0, y0 + 1]) {
      const occ = `${y}${src.slice(4)}`;
      const n = y - +src.slice(0, 4);
      const diff = daysBetween(from, occ);
      if (n >= 1 && diff >= 0 && diff <= days) out.push({ date: occ, title: label.replace("{n}", n), days: diff, anniv: true });
    }
  }
  return out.sort((a, b) => a.days - b.days);
}
function sparkline(points) {
  if (!points || points.length < 2) return "";
  const pts = points.slice(-24).map((p) => p[1]);
  const max = Math.max(...pts, 10), min = Math.min(...pts, 1);
  const w = 72, h = 28, n = pts.length;
  const d = pts.map((r, i) => `${i ? "L" : "M"}${(i / (n - 1)) * (w - 4) + 2},${2 + ((r - min) / Math.max(1, max - min)) * (h - 4)}`).join("");
  return `<svg class="spark" viewBox="0 0 ${w} ${h}" aria-hidden="true"><path d="${d}"/></svg>`;
}
function rankDelta(songId) {
  const pts = D.chart?.history?.[songId]?.points || [];
  if (pts.length < 2) return `<span class="delta same">NEW</span>`;
  const d = pts[pts.length - 2][1] - pts[pts.length - 1][1];
  if (d > 0) return `<span class="delta up">▲${d}</span>`;
  if (d < 0) return `<span class="delta down">▼${-d}</span>`;
  return `<span class="delta same">-</span>`;
}
function sourcesHtml(e) {
  if (!e.sources?.length) return "";
  return `<div class="src">출처: ${e.sources.slice(0, 4).map((s) => `<a href="${esc(s.url)}" target="_blank" rel="noopener">${esc(s.publisher)}</a>`).join(", ")}</div>`;
}
function eventRow(e) {
  const who = e.members?.length && e.members.length < 5 ? ` · ${e.members.join(", ")}` : "";
  return `<div class="row ev" data-ev="${esc(e.id)}" role="button" tabindex="0"><div class="main">
    <div><span class="tag">${esc(TYPE_LABEL[e.type] || e.type)}</span><span class="s">${esc(span(e))}${esc(e.place ? " · " + e.place : "")}${esc(who)}</span></div>
    <div class="t">${esc(e.title)}</div>
    ${e.summary ? `<div class="s">${esc(e.summary)}</div>` : ""}${e.perk ? `<div class="perk">🎁 ${esc(e.perk)}</div>` : ""}</div><span class="chev" aria-hidden="true">›</span></div>`;
}
const isPast = (e, t) => (e.end_date || e.date) < t;
// 진행 중: 기간이 있으면 기간 안, 시작일만 있으면 30일간
function ongoing(evs, t, types) {
  return evs.filter((e) => types.includes(e.type) && e.date <= t && (e.end_date ? e.end_date >= t : daysBetween(e.date, t) <= 30));
}
function pastToggle(list, label) {
  if (!list.length) return "";
  let h = `<details class="past"><summary>${esc(label)} ${list.length}개</summary>`;
  let month = "";
  for (const e of list) {
    const m = e.date.slice(0, 7);
    if (m !== month) { month = m; h += `<div class="month">${+m.slice(0, 4)}년 ${+m.slice(5)}월</div>`; }
    h += eventRow(e);
  }
  return h + `</details>`;
}
const byDateDesc = (a, b) => b.date.localeCompare(a.date);

// ---------- 상세 시트: 일정 하나와 관련된 뉴스·영상 ----------
const STOP = new Set(["리센느", "rescene", "출연", "발매", "공개", "방송", "행사", "콜라보", "팝업", "미니", "앨범", "신곡", "컴백", "기념", "오픈", "진행", "예정", "스페셜", "with", "pulse", "그룹", "걸그룹", "멤버", "참석", "출시", "광고", "모델", "캠페인", "이벤트"]);
const keywords = (text) => [...new Set((text.match(/[0-9A-Za-z가-힣]{2,}/g) || []).map((w) => w.toLowerCase()).filter((w) => !STOP.has(w)))];
function related(e) {
  const kws = keywords(`${e.title} ${e.place || ""}`);
  const arts = (D.news?.articles || []).filter((a) => !a.dup);
  const df = (k) => arts.filter((a) => a.title.toLowerCase().includes(k)).length;
  const w = Object.fromEntries(kws.map((k) => [k, Math.log((arts.length + 1) / (df(k) + 1))]));
  const score = (title) => kws.reduce((s, k) => s + (title.toLowerCase().includes(k) ? w[k] : 0), 0);
  const refs = new Set((e.sources || []).map((s) => s.ref));
  const rank = (list, get) => list.map((x) => [x, get(x)]).filter(([, s]) => s >= 2).sort((a, b) => b[1] - a[1]).map(([x]) => x);
  return {
    news: rank(arts, (a) => (refs.has(a.id) ? 99 : score(a.title))).slice(0, 8),
    videos: rank(D.videos?.items || [], (v) => score(v.title)).slice(0, 6),
  };
}
function openEvent(id) {
  const e = (D.events?.events || []).find((x) => x.id === id);
  if (!e) return;
  const rel = related(e);
  const link = e.link || e.sources?.[0]?.url;
  const who = e.members?.length ? (e.members.length === 5 ? "리센느 전원" : e.members.join(", ")) : "";
  $("#detail-title").textContent = TYPE_LABEL[e.type] || "일정";
  $("#detail-body").innerHTML = `<section class="card">
      <h2>${esc(e.title)}</h2>
      <div class="s">${esc(span(e))}${esc(e.place ? " · " + e.place : "")}${esc(who ? " · " + who : "")}</div>
      ${e.summary ? `<p>${esc(e.summary)}</p>` : ""}
      ${e.perk ? `<p class="perk">🎁 ${esc(e.perk)}</p>` : ""}
      ${link ? `<p><a class="btn" href="${esc(link)}" target="_blank" rel="noopener">원문 보기 →</a></p>` : ""}
      <p><button class="chip" data-goto-day="${esc(e.date)}">📅 일정 탭 달력에서 보기</button>
      ${e.members?.length && e.members.length < 5 ? e.members.map((m) => `<button class="chip" data-goto-member="${esc(m)}">${esc(m)} 소식 모아보기</button>`).join("") : ""}</p>
      ${sourcesHtml(e)}</section>
    <div class="section-title">관련 뉴스</div><section class="card">${rel.news.length ? rel.news.map(newsLink).join("") : `<div class="empty">관련 기사를 찾지 못했어요</div>`}</section>
    <div class="section-title">관련 영상</div>${rel.videos.length ? `<div class="vlist">${rel.videos.map((v) => vcard(v)).join("")}</div>` : `<section class="card"><div class="empty">관련 영상을 찾지 못했어요</div></section>`}`;
  $("#detail").showModal();
  $("#detail-body").scrollTop = 0;
}
const newsLink = (a) => `<a class="row" href="${esc(a.link)}" target="_blank" rel="noopener"><div class="main"><div class="t">${esc(a.title)}</div><div class="s">${esc(a.publisher)} · ${ago(a.published_at)}</div></div></a>`;
// 같은 소식(story)끼리 묶어 한 줄, 나머지는 펼쳐 보기
function newsGroups(limit) {
  const g = new Map();
  for (const a of (D.news?.articles || []).filter((x) => !x.dup)) {
    const k = a.story || a.id;
    if (!g.has(k)) g.set(k, []);
    g.get(k).push(a);
  }
  return [...g.values()].slice(0, limit);
}
function newsGroupRow([a, ...rest]) {
  return `<div class="row"><div class="main"><a class="t" href="${esc(a.link)}" target="_blank" rel="noopener">${esc(a.title)}</a>
    <div class="s">${esc(a.publisher)} · ${ago(a.published_at)}</div>
    ${rest.length ? `<details><summary>같은 소식 ${rest.length}건 더</summary>${rest.map((x) => `<a class="sub" href="${esc(x.link)}" target="_blank" rel="noopener">${esc(x.publisher)} · ${esc(x.title)}</a>`).join("")}</details>` : ""}</div></div>`;
}
const more = (hash, label = "전체 보기") => `<a class="more-link" href="#${hash}">${label} ›</a>`;
function vcard(v, horizontal) {
  const ms = v.milestone ? `<span class="tag alt">${fmtCount(v.milestone.target)}까지 D-${Math.ceil(v.milestone.eta_days)}</span>` : "";
  const grp = { official: "공식", wonee: "원이 채널", appearance: "출연", stage: "무대" }[v.group];
  if (horizontal) return `<a class="hcard" href="https://youtu.be/${esc(v.id)}" target="_blank" rel="noopener">
    <img loading="lazy" src="${esc(v.thumb)}" alt=""><div class="t">${esc(v.title)}</div><div class="s">${esc(grp)} · ${ago(v.published_at)}</div></a>`;
  return `<a class="vcard" href="https://youtu.be/${esc(v.id)}" target="_blank" rel="noopener">
    <img loading="lazy" src="${esc(v.thumb)}" alt="">
    <div class="main"><div class="t">${esc(v.title)}</div>
    <div class="s">${esc(v.channel)} · ${ago(v.published_at)} · 조회수 ${fmtCount(v.views)}</div>
    <div><span class="tag">${esc(grp)}</span>${ms}</div></div></a>`;
}

// ---------- views ----------
function viewToday() {
  const t = todayStr();
  const evs = events();
  const todays = evs.filter((e) => e.date <= t && t <= (e.end_date || e.date) && !["popup", "collab", "goods"].includes(e.type));
  const ann = anniversaries(t, 30);
  const now_on = ongoing(evs, t, ["popup", "collab", "goods", "vote"]).concat(evs.filter((e) => e.type === "ad" && e.perk && e.date <= t && e.end_date >= t));
  const upcoming = evs.filter((e) => e.date > t && e.date <= addDays(t, 14));
  const rt = D.chart?.realtime;
  const vids = (D.videos?.items || []).filter((v) => !v.short && memberMatch(v.members, true) && Date.now() - new Date(v.published_at) < 3 * 864e5).slice(0, 12);
  const news = newsGroups(5);
  const recent = (D.alerts?.items || []).filter((a) => Date.now() - new Date(a.at) < 864e5).slice(0, 6);

  let h = staleBanner(["melon_chart", "youtube", "events"]);
  h += `<section class="card"><h2>오늘 ${md(t)}(${dow(t)}) <small>${ann.filter((a) => !a.days).map((a) => "🎂 " + esc(a.title)).join(" ")}</small></h2>
    ${todays.length ? todays.map(eventRow).join("") : `<div class="empty">오늘 확정된 일정이 없어요</div>`}</section>`;
  if (rt?.entries?.length) {
    h += `<section class="card"><h2>멜론 실시간 ${more("chart", "차트")}<small>${esc(rt.chart_date || "")} ${esc(rt.chart_hour || "")} · TOP100에 ${rt.entries.length}곡</small></h2>
      ${rt.entries.slice(0, 3).map((e) => `<a class="row" href="#chart"><div class="rank">${e.rank}${rankDelta(e.song_id)}</div><div class="main"><div class="t">${esc(e.title)}</div><div class="s">${esc(e.album)}</div></div>${sparkline(D.chart.history?.[e.song_id]?.points)}</a>`).join("")}</section>`;
  } else if (rt) {
    h += `<section class="card"><h2>멜론 실시간</h2><div class="empty">지금은 TOP100 밖이에요</div></section>`;
  }
  if (recent.length) {
    const evIds = new Set((D.events?.events || []).map((e) => e.id));
    h += `<section class="card"><h2>새 소식 <small>24시간</small></h2>${recent.map((a) => {
      const id = (a.key || "").startsWith("event:") ? a.key.slice(6) : null;
      const inner = `<div class="main"><div class="t">${esc(a.title)}</div><div class="s">${esc(a.body)} · ${ago(a.at)}</div></div>`;
      return id && evIds.has(id) ? `<div class="row ev" data-ev="${esc(id)}" role="button" tabindex="0">${inner}<span class="chev" aria-hidden="true">›</span></div>`
        : `<a class="row" href="${esc(a.url)}" target="_blank" rel="noopener">${inner}</a>`;
    }).join("")}</section>`;
  }
  if (vids.length) h += `<div class="section-title">새 영상 ${more("videos")}</div><div class="hscroll">${vids.map((v) => vcard(v, true)).join("")}</div>`;
  if (now_on.length) h += `<div class="section-title">진행 중 · 팝업·콜라보·투표 ${more("schedule", "지난 것까지")}</div><section class="card">${now_on.map(eventRow).join("")}</section>`;
  if (upcoming.length || ann.some((a) => a.days)) {
    h += `<div class="section-title">다가오는 일정 ${more("schedule", "달력")}</div><section class="card">
      ${upcoming.map(eventRow).join("")}
      ${ann.filter((a) => a.days).slice(0, 5).map((a) => `<div class="row"><div class="main"><span class="tag alt">D-${a.days}</span> ${esc(a.title)} <span class="s">${md(a.date)}</span></div></div>`).join("")}</section>`;
  }
  if (news.length) h += `<div class="section-title">최신 뉴스 <small>같은 소식은 묶어서</small></div><section class="card">${news.map(newsGroupRow).join("")}</section>`;
  return h;
}

function viewVideos() {
  let list = (D.videos?.items || []).filter((v) => memberMatch(v.members, true));
  if (ui.vgroup !== "all") list = list.filter((v) => v.group === ui.vgroup);
  if (!ui.vshorts) list = list.filter((v) => !v.short);
  if (ui.vsort === "views") list = [...list].sort((a, b) => b.views - a.views);
  const groups = [["all", "전체"], ["official", "공식"], ["wonee", "원이 채널"], ["appearance", "출연"], ["stage", "무대·직캠"]];
  let h = staleBanner(["youtube", "appearances"]);
  h += `<div class="seg">${groups.map(([k, l]) => `<button class="chip" data-vgroup="${k}" aria-pressed="${ui.vgroup === k}">${l}</button>`).join("")}</div>
    <div class="toolbar"><span>${list.length.toLocaleString()}개</span>
    <span><label><input type="checkbox" id="vshorts" ${ui.vshorts ? "checked" : ""}> 쇼츠</label></span>
    <span><button class="chip" id="vsort" aria-pressed="${ui.vsort === "views"}">${ui.vsort === "views" ? "조회수순" : "최신순"}</button></span></div>`;
  h += list.length ? `<div class="vlist">${list.slice(0, ui.vlimit).map((v) => vcard(v)).join("")}</div>` : `<div class="empty">조건에 맞는 영상이 없어요</div>`;
  if (list.length > ui.vlimit) h += `<button class="more" id="vmore">더 보기 (${list.length - ui.vlimit})</button>`;
  return h;
}

function chartList(c, withSpark) {
  if (!c) return `<div class="empty">데이터 없음</div>`;
  if (!c.entries.length) return `<div class="empty">TOP100 밖이에요</div>`;
  return c.entries.map((e) => `<a class="row" href="https://www.melon.com/song/detail.htm?songId=${esc(e.song_id)}" target="_blank" rel="noopener">
    <div class="rank">${e.rank}${withSpark ? rankDelta(e.song_id) : ""}</div><div class="main"><div class="t">${esc(e.title)}</div><div class="s">${esc(e.album)}</div></div>
    ${withSpark ? sparkline(D.chart.history?.[e.song_id]?.points) : ""}</a>`).join("");
}
function viewChart() {
  const c = D.chart || {};
  const t = todayStr();
  const awards = (D.events?.events || []).filter((e) => e.type === "award").sort((a, b) => b.date.localeCompare(a.date));
  const votes = (D.events?.events || []).filter((e) => e.type === "vote" && (e.end_date || e.date) >= t);
  const week = D.votes?.melon_week;
  const best = Object.values(c.best || {}).sort((a, b) => (a.realtime?.rank ?? 999) - (b.realtime?.rank ?? 999));
  let h = staleBanner(["melon_chart", "melon_vote"]);
  h += `<section class="card"><h2>멜론 TOP100 실시간 <small>${esc(c.realtime?.chart_date || "")} ${esc(c.realtime?.chart_hour || "")}</small></h2>${chartList(c.realtime, true)}</section>`;
  h += `<section class="card"><h2>일간 <small>${esc(c.day?.chart_date || "")}</small></h2>${chartList(c.day)}</section>`;
  h += `<section class="card"><h2>주간 <small>${esc(c.week?.chart_date || "")}</small></h2>${chartList(c.week)}</section>`;
  if (best.length) {
    h += `<section class="card"><h2>최고 순위 <small>수집 시작 이후</small></h2><table class="best"><tr><th>곡</th><th>실시간</th><th>일간</th><th>주간</th></tr>
      ${best.map((b) => `<tr><td>${esc(b.title)}</td>${["realtime", "day", "week"].map((k) => `<td class="n">${b[k] ? b[k].rank : "-"}</td>`).join("")}</tr>`).join("")}</table></section>`;
  }
  h += `<div class="section-title">투표</div><section class="card">`;
  if (week) {
    h += `<div class="row"><div class="main"><div class="t"><a href="${esc(week.url)}" target="_blank" rel="noopener">멜론 주간 인기상</a></div>
      <div class="s">${week.rescene.length ? week.rescene.map((r) => `'${esc(r.song)}' ${r.rank}위`).join(", ") : "이번 주 후보에 리센느 곡이 없어요"} · 후보 ${week.total}곡 · 1위 ${esc(week.top[0]?.artist)} '${esc(week.top[0]?.song)}'</div></div></div>`;
  }
  h += votes.map(eventRow).join("") + (week || votes.length ? "" : `<div class="empty">진행 중인 투표 정보가 없어요</div>`) + `</section>`;
  h += `<div class="section-title">1위·수상 기록</div><section class="card">${awards.length ? awards.map(eventRow).join("") : `<div class="empty">아직 수집된 기록이 없어요</div>`}</section>`;
  return h;
}

function viewSchedule() {
  const t = todayStr();
  ui.calMonth = ui.calMonth || t.slice(0, 7);
  ui.calDay = ui.calDay || t;
  const [y, m] = ui.calMonth.split("-").map(Number);
  const first = `${ui.calMonth}-01`;
  const startDow = new Date(first + "T00:00:00Z").getUTCDay();
  const gridStart = addDays(first, -startDow);
  const evs = events();
  const ann = anniversaries(gridStart, 42);
  const on = (d) => evs.filter((e) => e.date <= d && d <= (e.end_date || e.date) && (e.end_date || ["broadcast", "event", "award", "release", "vote"].includes(e.type) || e.date === d));
  let cells = "";
  for (let i = 0; i < 42; i++) {
    const d = addDays(gridStart, i);
    const kinds = [...new Set(on(d).map((e) => e.type))].slice(0, 3);
    if (ann.some((a) => a.date === d)) kinds.push("anniv");
    cells += `<button data-day="${d}" class="${d.slice(0, 7) !== ui.calMonth ? "other" : ""} ${d === t ? "today" : ""}" aria-pressed="${d === ui.calDay}">${+d.slice(8)}<div class="dots">${kinds.map((k) => `<i class="k-${k}"></i>`).join("")}</div></button>`;
  }
  const dayEvents = on(ui.calDay);
  const dayAnn = ann.filter((a) => a.date === ui.calDay);
  const upcoming = evs.filter((e) => (e.end_date || e.date) >= t && e.type !== "ad").sort((a, b) => a.date.localeCompare(b.date));
  const SHOP = ["popup", "collab", "goods"];
  const shopNow = ongoing(evs, t, SHOP);
  const shopPast = evs.filter((e) => SHOP.includes(e.type) && !shopNow.includes(e) && e.date <= t).sort(byDateDesc);
  const ads = evs.filter((e) => e.type === "ad").sort(byDateDesc);
  const adsNow = ads.filter((e) => (e.end_date ? e.end_date >= t : daysBetween(e.date, t) <= 180));
  const others = evs.filter((e) => !SHOP.includes(e.type) && e.type !== "ad" && isPast(e, t)).sort(byDateDesc);
  let h = staleBanner(["events", "archive"]);
  h += `<div class="section-title">진행 중 · 팝업·콜라보·굿즈</div><section class="card">
    ${shopNow.length ? shopNow.map(eventRow).join("") : `<div class="empty">지금 진행 중인 팝업·콜라보가 없어요</div>`}
    ${pastToggle(shopPast, "지난 팝업·콜라보·굿즈")}</section>`;
  h += `<div class="section-title">광고 모델 · 구매 혜택</div><section class="card">
    ${adsNow.length ? adsNow.map(eventRow).join("") : `<div class="empty">최근 광고 소식이 없어요</div>`}
    ${pastToggle(ads.filter((e) => !adsNow.includes(e)), "지난 광고")}</section>`;
  h += `<section class="card"><div class="cal-head"><button data-cal="-1" aria-label="이전 달">‹</button><b>${y}년 ${m}월</b><button data-cal="1" aria-label="다음 달">›</button></div>
    <div class="cal">${"일월화수목금토".split("").map((d) => `<div class="dow">${d}</div>`).join("")}${cells}</div></section>`;
  h += `<section class="card"><h2>${md(ui.calDay)}(${dow(ui.calDay)})</h2>
    ${dayAnn.map((a) => `<div class="row"><div class="main">🎂 ${esc(a.title)}</div></div>`).join("")}
    ${dayEvents.length ? dayEvents.map(eventRow).join("") : dayAnn.length ? "" : `<div class="empty">이 날의 일정이 없어요</div>`}</section>`;
  h += `<div class="section-title">앞으로의 일정 (확인된 것만)</div><section class="card">${upcoming.length ? upcoming.map(eventRow).join("") : `<div class="empty">예정된 일정이 없어요</div>`}
    ${pastToggle(others, "지난 방송·행사·수상")}</section>`;
  h += `<p class="note">출처가 공식이거나 서로 다른 언론사 2곳 이상에서 확인된 정보만 보여드려요.</p>`;
  return h;
}

function viewAlbums() {
  const groups = [["all", "전체"], ["main", "정규·EP"], ["싱글", "싱글"], ["OST", "OST"]];
  let list = D.albums?.albums || [];
  if (ui.albumType === "main") list = list.filter((a) => ["정규", "EP"].includes(a.type));
  else if (ui.albumType !== "all") list = list.filter((a) => a.type === ui.albumType);
  let h = staleBanner(["melon_albums"]);
  h += `<div class="seg">${groups.map(([k, l]) => `<button class="chip" data-atype="${k}" aria-pressed="${ui.albumType === k}">${l}</button>`).join("")}</div>`;
  h += `<div class="agrid">${list.map((a) => `<button class="acard" data-album="${esc(a.id)}"><img loading="lazy" src="${esc(a.art)}" alt="">
    <div class="info"><div class="t">${esc(a.title)}</div><div class="s">${esc(a.type)} · ${esc(a.date)}</div></div></button>`).join("")}</div>`;
  h += `<section class="card" id="album-detail" hidden></section>`;
  return h;
}
function albumDetail(id) {
  const a = (D.albums?.albums || []).find((x) => x.id === id);
  const el = $("#album-detail");
  if (!a || !el) return;
  el.hidden = false;
  el.innerHTML = `<h2>${esc(a.title)} <small>${esc(a.type)} · ${esc(a.date)}</small></h2>
    <ol class="tracks">${(a.tracks || []).map((t) => `<li class="${t.is_title ? "title-track" : ""}">${esc(t.title)}${t.is_title ? " (타이틀)" : ""}</li>`).join("")}</ol>
    <p><a href="${esc(a.url)}" target="_blank" rel="noopener">멜론에서 보기 →</a></p>`;
  el.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

const VIEWS = { today: viewToday, videos: viewVideos, chart: viewChart, schedule: viewSchedule, albums: viewAlbums };
function tab() { const h = location.hash.slice(1); return VIEWS[h] ? h : "today"; }
function render() {
  const t = tab();
  document.querySelectorAll(".tabs a").forEach((a) => a.setAttribute("aria-current", a.dataset.tab === t ? "page" : "false"));
  $("#members").innerHTML = ["전체", ...MEMBERS].map((m) => `<button class="chip" data-member="${m}" aria-pressed="${ui.member === m}">${m}</button>`).join("");
  $("#members").hidden = t === "chart" || t === "albums";
  $("#view").innerHTML = VIEWS[t]();
}

// ---------- events ----------
document.addEventListener("click", (ev) => {
  const row = ev.target.closest("[data-ev]");
  if (row && !ev.target.closest("a, button")) { openEvent(row.dataset.ev); return; }
  const b = ev.target.closest("button, a");
  if (!b) return;
  const ds = b.dataset;
  if (ds.member) { ui.member = ds.member; store("member", ui.member); render(); }
  else if (ds.vgroup) { ui.vgroup = ds.vgroup; ui.vlimit = 30; render(); }
  else if (b.id === "vsort") { ui.vsort = ui.vsort === "new" ? "views" : "new"; render(); }
  else if (b.id === "vmore") { ui.vlimit += 30; render(); }
  else if (ds.cal) {
    const [y, m] = ui.calMonth.split("-").map(Number);
    const d = new Date(Date.UTC(y, m - 1 + Number(ds.cal), 1));
    ui.calMonth = d.toISOString().slice(0, 7); ui.calDay = ui.calMonth + "-01"; render();
  } else if (ds.day) { ui.calDay = ds.day; if (ds.day.slice(0, 7) !== ui.calMonth) ui.calMonth = ds.day.slice(0, 7); render(); }
  else if (ds.atype) { ui.albumType = ds.atype; render(); }
  else if (ds.album) albumDetail(ds.album);
  else if (ds.gotoDay) {
    ui.calDay = ds.gotoDay; ui.calMonth = ds.gotoDay.slice(0, 7);
    $("#detail").close();
    if (location.hash === "#schedule") { render(); window.scrollTo(0, 0); } else location.hash = "#schedule";
  } else if (ds.gotoMember) {
    ui.member = ds.gotoMember; store("member", ui.member);
    $("#detail").close(); render(); window.scrollTo(0, 0);
  }
});
document.addEventListener("keydown", (ev) => {
  const row = ev.target.closest?.("[data-ev]");
  if (row && (ev.key === "Enter" || ev.key === " ")) { ev.preventDefault(); openEvent(row.dataset.ev); }
});
$("#detail").addEventListener("click", (ev) => { if (ev.target === $("#detail")) $("#detail").close(); });
document.addEventListener("change", (ev) => {
  if (ev.target.id === "vshorts") { ui.vshorts = ev.target.checked; render(); }
});
window.addEventListener("hashchange", () => { render(); window.scrollTo(0, 0); });

// ---------- push & settings ----------
const isIOS = /iPad|iPhone|iPod/.test(navigator.userAgent) || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
const standalone = window.matchMedia("(display-mode: standalone)").matches || navigator.standalone;
function defaultPrefs() { return { digest_morning: true, digest_evening: true, realtime: {} }; }
const prefs = () => store("prefs") || defaultPrefs();

function b64ToUint8(b64) {
  const pad = "=".repeat((4 - (b64.length % 4)) % 4);
  const raw = atob((b64 + pad).replace(/-/g, "+").replace(/_/g, "/"));
  return Uint8Array.from(raw, (c) => c.charCodeAt(0));
}
async function currentSub() {
  if (!("serviceWorker" in navigator) || !("PushManager" in window)) return null;
  const reg = await navigator.serviceWorker.ready;
  return reg.pushManager.getSubscription();
}
async function api(path, body) {
  const r = await fetch(CFG.workerUrl + path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}
async function subscribe(adminCode) {
  const perm = await Notification.requestPermission();
  if (perm !== "granted") throw new Error("알림 권한이 거부되었어요. 브라우저 설정에서 허용해 주세요.");
  const reg = await navigator.serviceWorker.ready;
  const sub = (await reg.pushManager.getSubscription()) || await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: b64ToUint8(CFG.vapidPublicKey) });
  const res = await api("/api/subscribe", { subscription: sub.toJSON(), prefs: prefs(), admin_code: adminCode || store("adminCode") || undefined });
  store("admin", !!res.admin);
  return res;
}
async function savePrefs() {
  const sub = await currentSub();
  if (sub) await api("/api/prefs", { endpoint: sub.endpoint, prefs: prefs() });
}

const changeHtml = (c) => `<div class="row"><div class="main"><div class="t">${esc(c.title)} <span class="s">${esc(c.date)}</span></div>
  <ul class="notes">${c.notes.map((n) => `<li>${esc(n)}</li>`).join("")}</ul></div></div>`;
async function renderSettings() {
  const body = $("#settings-body");
  const supported = "serviceWorker" in navigator && "PushManager" in window && "Notification" in window;
  const sub = supported ? await currentSub() : null;
  const p = prefs();
  let h = `<section class="card"><h2>알림</h2>`;
  if (!CFG.workerUrl) h += `<p class="note">알림 서버가 아직 연결되지 않았어요.</p>`;
  else if (isIOS && !standalone) {
    h += `<p class="note">아이폰은 <b>홈 화면에 추가</b>해야 알림을 받을 수 있어요.<br>① 사파리 하단 <b>공유 버튼(□↑)</b> → ② <b>홈 화면에 추가</b> → ③ 홈 화면의 아이콘으로 열고 여기서 알림 켜기</p>`;
  } else if (!supported) h += `<p class="note">이 브라우저는 웹 푸시를 지원하지 않아요.</p>`;
  else if (sub) h += `<p class="note ok">✓ 알림을 받고 있어요${store("admin") ? " (관리자)" : ""}</p><button class="btn ghost" id="push-off">알림 끄기</button>`;
  else h += `<p class="note">아침·저녁 요약과 원하는 실시간 소식을 보내드려요.</p><button class="btn" id="push-on">알림 켜기</button>`;
  h += `<p class="note" id="push-msg"></p></section>`;

  h += `<section class="card"><h2>요약 알림 <small>기본</small></h2>
    <label class="switch"><span>☀️ 아침 9시 · 오늘의 리센느</span><input type="checkbox" data-pref="digest_morning" ${p.digest_morning ? "checked" : ""}></label>
    <label class="switch"><span>🌙 저녁 9시 · 오늘 있었던 일</span><input type="checkbox" data-pref="digest_evening" ${p.digest_evening ? "checked" : ""}></label></section>`;
  h += `<section class="card"><h2>실시간 알림 <small>원하는 것만</small></h2>
    ${RT_CATS.map(([k, l]) => `<label class="switch"><span>${l}</span><input type="checkbox" data-rt="${k}" ${(p.realtime?.[k] ?? RT_DEFAULT_ON.has(k)) ? "checked" : ""}></label>`).join("")}</section>`;

  const jobs = D.status?.jobs || {};
  const stale = new Set(staleJobs(Object.keys(jobs)));
  h += `<section class="card"><h2>데이터 상태</h2><div class="status-list">
    ${Object.entries(jobs).map(([k, s]) => `<div><span>${esc(JOB_LABEL[k] || k)}</span><span class="${stale.has(k) ? "warn" : "ok"}">${s.last_success ? ago(s.last_success) : "실패"}</span></div>`).join("")}</div>
    <p class="note">모든 정보는 자동으로 수집돼요. 일정·팝업은 공식 출처 또는 서로 다른 언론사 2곳 이상에서 확인된 것만 보여드려요.</p></section>`;
  const month = Object.keys(D.usage || {}).sort().pop();
  try {
    const log = await (await fetch("changelog.json", { cache: "no-cache" })).json();
    h += `<section class="card"><h2>업데이트 내역</h2>${log.slice(0, 1).map(changeHtml).join("")}
      ${log.length > 1 ? `<details class="past"><summary>이전 업데이트 ${log.length - 1}개</summary>${log.slice(1).map(changeHtml).join("")}</details>` : ""}</section>`;
  } catch (e) { /* 내역을 못 받아도 설정은 연다 */ }
  h += `<details><summary>관리자</summary><section class="card">
    ${month ? `<p class="note">이번 달 AI 사용료: $${(D.usage[month].usd || 0).toFixed(2)}</p>` : ""}
    <p class="note">관리자 코드를 입력하고 알림을 켜면 수집기 고장 알림과 수리 요청을 받아요.</p>
    <div class="field"><input id="admin-code" type="password" placeholder="관리자 코드" value="${esc(store("adminCode") || "")}"><button class="btn" id="admin-save">등록</button></div>
  </section></details>`;
  body.innerHTML = h;
}

$("#open-settings").addEventListener("click", async () => { await renderSettings(); $("#settings").showModal(); });
$("#settings").addEventListener("click", async (ev) => {
  const msg = (t) => { const el = $("#push-msg"); if (el) el.textContent = t; };
  const id = ev.target.id;
  try {
    if (id === "push-on") { msg("설정 중…"); await subscribe(); await renderSettings(); }
    else if (id === "push-off") {
      const sub = await currentSub();
      if (sub) { await api("/api/unsubscribe", { endpoint: sub.endpoint }).catch(() => {}); await sub.unsubscribe(); }
      await renderSettings();
    } else if (id === "admin-save") {
      store("adminCode", $("#admin-code").value.trim());
      const r = await subscribe($("#admin-code").value.trim());
      await renderSettings();
      msg(r.admin ? "관리자로 등록됐어요" : "코드가 맞지 않아요");
    }
  } catch (e) { msg(e.message); }
});
$("#settings").addEventListener("change", async (ev) => {
  const p = prefs();
  if (ev.target.dataset.pref) p[ev.target.dataset.pref] = ev.target.checked;
  if (ev.target.dataset.rt) p.realtime = { ...p.realtime, [ev.target.dataset.rt]: ev.target.checked };
  store("prefs", p);
  try { await savePrefs(); } catch (e) { /* 다음 구독 때 반영 */ }
});
$("#settings").addEventListener("click", (ev) => { if (ev.target === $("#settings")) $("#settings").close(); });

// ---------- boot ----------
(async function boot() {
  if ("serviceWorker" in navigator) navigator.serviceWorker.register("sw.js").catch(() => {});
  const first = loadAll();
  await first.small;
  D.videos = D.videos || { items: [] };
  applyTheme();
  render();
  await first.all;
  render();
  // 데이터가 바뀌었을 때만 다시 그린다 (스크롤 위치 유지)
  const stamp = () => FILES.map((f) => D[f]?.updated || "").join("|");
  setInterval(async () => {
    if (document.visibilityState !== "visible" || $("#settings").open) return;
    const before = stamp();
    await loadAll().all;
    if (stamp() !== before) { const y = window.scrollY; applyTheme(); render(); window.scrollTo(0, y); }
  }, 5 * 60 * 1000);
})();

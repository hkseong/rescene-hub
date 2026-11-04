// rescene-hub push-subscription store (+ Kakao i Open Builder skill endpoint).
// KV "SUBS": sub:<id> -> { id, subscription, prefs, admin, created, updated }
// Secrets: ADMIN_TOKEN (GitHub Actions ↔ worker), ADMIN_CODE (owner types this in the site)
// Vars: ALLOWED_ORIGIN, DATA_BASE

const json = (obj, status = 200, headers = {}) =>
  new Response(JSON.stringify(obj), { status, headers: { "Content-Type": "application/json; charset=utf-8", ...headers } });

async function idFor(endpoint) {
  const buf = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(endpoint));
  return [...new Uint8Array(buf)].slice(0, 16).map((b) => b.toString(16).padStart(2, "0")).join("");
}

function cleanPrefs(p = {}) {
  const cats = ["broadcast", "vote", "award", "video", "appearance", "chart", "popup"];
  const realtime = {};
  for (const c of cats) realtime[c] = !!(p.realtime && p.realtime[c]);
  return { digest_morning: p.digest_morning !== false, digest_evening: p.digest_evening !== false, realtime };
}

function validSubscription(s) {
  return s && typeof s.endpoint === "string" && /^https:\/\//.test(s.endpoint) && s.endpoint.length < 1000 &&
    s.keys && typeof s.keys.p256dh === "string" && typeof s.keys.auth === "string";
}

async function listAll(env) {
  const out = [];
  let cursor;
  do {
    const page = await env.SUBS.list({ prefix: "sub:", cursor });
    for (const k of page.keys) {
      const v = await env.SUBS.get(k.name, "json");
      if (v) out.push(v);
    }
    cursor = page.list_complete ? null : page.cursor;
  } while (cursor);
  return out;
}

const isAdmin = (req, env) => req.headers.get("Authorization") === `Bearer ${env.ADMIN_TOKEN}`;

export default {
  async fetch(req, env) {
    const url = new URL(req.url);
    const origin = req.headers.get("Origin") || "";
    const cors = {
      "Access-Control-Allow-Origin": origin === env.ALLOWED_ORIGIN ? origin : env.ALLOWED_ORIGIN,
      "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
      "Access-Control-Allow-Headers": "Content-Type",
      Vary: "Origin",
    };
    if (req.method === "OPTIONS") return new Response(null, { headers: cors });

    try {
      if (url.pathname === "/" || url.pathname === "/health") return json({ ok: true, service: "rescene-hub" }, 200, cors);

      if (req.method === "POST" && url.pathname === "/api/subscribe") {
        const body = await req.json();
        if (!validSubscription(body.subscription)) return json({ error: "invalid subscription" }, 400, cors);
        const id = await idFor(body.subscription.endpoint);
        const prev = await env.SUBS.get("sub:" + id, "json");
        const admin = (body.admin_code && env.ADMIN_CODE && body.admin_code === env.ADMIN_CODE) || !!(prev && prev.admin);
        const rec = { id, subscription: body.subscription, prefs: cleanPrefs(body.prefs), admin,
          created: prev ? prev.created : new Date().toISOString(), updated: new Date().toISOString() };
        await env.SUBS.put("sub:" + id, JSON.stringify(rec));
        return json({ ok: true, id, admin }, 200, cors);
      }

      if (req.method === "POST" && url.pathname === "/api/prefs") {
        const body = await req.json();
        const id = await idFor(String(body.endpoint || ""));
        const rec = await env.SUBS.get("sub:" + id, "json");
        if (!rec) return json({ error: "not subscribed" }, 404, cors);
        rec.prefs = cleanPrefs(body.prefs);
        rec.updated = new Date().toISOString();
        await env.SUBS.put("sub:" + id, JSON.stringify(rec));
        return json({ ok: true }, 200, cors);
      }

      if (req.method === "POST" && url.pathname === "/api/unsubscribe") {
        const body = await req.json();
        await env.SUBS.delete("sub:" + (await idFor(String(body.endpoint || ""))));
        return json({ ok: true }, 200, cors);
      }

      if (url.pathname === "/api/admin/subscribers") {
        if (!isAdmin(req, env)) return json({ error: "unauthorized" }, 401);
        return json({ subscribers: await listAll(env) });
      }

      if (req.method === "POST" && url.pathname === "/api/admin/remove") {
        if (!isAdmin(req, env)) return json({ error: "unauthorized" }, 401);
        const { ids = [] } = await req.json();
        await Promise.all(ids.map((id) => env.SUBS.delete("sub:" + id)));
        return json({ ok: true, removed: ids.length });
      }

      if (req.method === "POST" && url.pathname === "/kakao/skill") return kakao(req, env);

      return json({ error: "not found" }, 404, cors);
    } catch (e) {
      return json({ error: String(e && e.message || e) }, 500, cors);
    }
  },

  // GitHub cron이 불안정해서 Cloudflare Cron이 15분마다 collect를 대신 실행시킨다.
  async scheduled(event, env, ctx) {
    const r = await fetch(`https://api.github.com/repos/${env.GH_REPO}/actions/workflows/collect.yml/dispatches`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${env.GH_TOKEN}`,
        Accept: "application/vnd.github+json",
        "User-Agent": "rescene-hub-worker",
      },
      body: JSON.stringify({ ref: "main" }),
    });
    if (r.status !== 204) throw new Error(`dispatch failed: ${r.status} ${await r.text()}`);
  },
};

// ---------- Kakao i Open Builder (1.5차) ----------
// 오픈빌더 블록의 스킬 URL을 https://<worker>/kakao/skill 로, 블록 이름(또는 발화)을 아래 키 중 하나로 두면 된다.
const KAKAO_MENU = ["오늘", "차트", "영상", "일정", "앨범"];

async function data(env, name) {
  const r = await fetch(`${env.DATA_BASE}${name}.json`, { cf: { cacheTtl: 120 } });
  return r.ok ? r.json() : null;
}

function kakaoText(text) {
  return json({
    version: "2.0",
    template: {
      outputs: [{ simpleText: { text: text.slice(0, 990) } }],
      quickReplies: KAKAO_MENU.map((m) => ({ label: m, action: "message", messageText: m })),
    },
  });
}

async function kakao(req, env) {
  const body = await req.json().catch(() => ({}));
  const said = ((body.userRequest && body.userRequest.utterance) || (body.intent && body.intent.name) || "").trim();
  const key = KAKAO_MENU.find((m) => said.includes(m)) || "오늘";
  const today = new Date(Date.now() + 9 * 3600e3).toISOString().slice(0, 10);
  let text = "";
  if (key === "차트") {
    const c = await data(env, "chart");
    const e = (c && c.realtime && c.realtime.entries) || [];
    text = `📈 멜론 실시간 ${c?.realtime?.chart_hour || ""}\n` + (e.length ? e.slice(0, 10).map((x) => `${x.rank}위 ${x.title}`).join("\n") : "TOP100 밖이에요");
  } else if (key === "영상") {
    const v = await data(env, "videos");
    const list = ((v && v.items) || []).filter((x) => !x.short).slice(0, 5);
    text = "🎬 최신 영상\n" + list.map((x) => `• ${x.title}\nhttps://youtu.be/${x.id}`).join("\n");
  } else if (key === "일정") {
    const ev = await data(env, "events");
    const up = ((ev && ev.events) || []).filter((e) => (e.end_date || e.date) >= today).slice(0, 8);
    text = "📅 다가오는 일정\n" + (up.length ? up.map((e) => `• ${e.date.slice(5)}${e.time ? " " + e.time : ""} ${e.title}`).join("\n") : "확인된 일정이 없어요");
  } else if (key === "앨범") {
    const a = await data(env, "albums");
    text = "💿 최근 앨범\n" + (((a && a.albums) || []).slice(0, 5).map((x) => `• ${x.title} (${x.type}, ${x.date})`).join("\n"));
  } else {
    const [ev, c] = await Promise.all([data(env, "events"), data(env, "chart")]);
    const todays = ((ev && ev.events) || []).filter((e) => e.date <= today && today <= (e.end_date || e.date));
    const top = ((c && c.realtime && c.realtime.entries) || [])[0];
    text = `☀️ 오늘의 리센느 (${today.slice(5)})\n` +
      (todays.length ? todays.map((e) => `• ${e.time ? e.time + " " : ""}${e.title}`).join("\n") : "• 오늘 확정된 일정 없음") +
      (top ? `\n• 멜론 실시간 최고 ${top.rank}위 '${top.title}'` : "");
  }
  return kakaoText(text + `\n\n더 보기: ${env.SITE_URL}`);
}

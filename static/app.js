/* 高德 POI 预估与爬取工具 —— 前端逻辑 */
"use strict";

const $ = (id) => document.getElementById(id);
const api = {
  regions: "/api/regions/tree",
  categories: "/api/categories",
  keys: "/api/keys",
  estimate: "/api/estimate",
  crawl: "/api/crawl",
};

/* ---------------- 全局状态 ---------------- */
const state = {
  regions: [],           // 省市区树
  cats: [],              // 一级分类
  selectedRegions: new Set(), // 勾选代码(2/4/6位)
  selCat: new Map(),     // firstCode -> {first, name, seconds:Set}
  manualTypes: new Set(),
  keys: [],
  crawling: false,
};

/* ---------------- 工具 ---------------- */
const fmt = (n) => (n == null ? "—" : Number(n).toLocaleString("zh-CN"));
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

async function jpost(url, body) {
  const r = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.error || ("HTTP " + r.status));
  if (data.error) throw new Error(data.error);
  return data;
}

/* ================= 行政区划 ================= */
function regionChips() {
  // 统计已选 省/市/区县
  const provs = new Set(), cities = new Set(), areas = new Set();
  for (const code of state.selectedRegions) {
    const found = findRegion(code);
    if (!found) continue;
    provs.add(found.province.code);
    if (found.city) cities.add(found.city.code);
    if (found.area) areas.add(found.area.code);
  }
  return { provs, cities, areas };
}
function findRegion(code) {
  for (const p of state.regions) {
    if (p.code === code) return { province: p, city: null, area: null };
    for (const c of p.children || []) {
      if (c.code === code) return { province: p, city: c, area: null };
      for (const a of c.children || []) {
        if (a.code === code) return { province: p, city: c, area: a };
      }
    }
  }
  return null;
}
function findProvince(code) { return state.regions.find((p) => p.code === code); }
function findCity(p, code) { return (p.children || []).find((c) => c.code === code); }

function provinceDistricts(p) { return (p.children || []).reduce((n, c) => n + (c.children || []).length, 0); }

// 勾选/取消一个省级（连带其下所有市/区县）
function toggleProvince(p) {
  const add = !state.selectedRegions.has(p.code);
  const codes = [p.code];
  for (const c of p.children || []) { codes.push(c.code); for (const a of c.children || []) codes.push(a.code); }
  for (const c of codes) add ? state.selectedRegions.add(c) : state.selectedRegions.delete(c);
}
function toggleCity(p, c) {
  const add = !state.selectedRegions.has(c.code);
  const codes = [c.code];
  for (const a of c.children || []) codes.push(a.code);
  for (const code of codes) add ? state.selectedRegions.add(code) : state.selectedRegions.delete(code);
}
function toggleArea(a) {
  state.selectedRegions.has(a.code) ? state.selectedRegions.delete(a.code) : state.selectedRegions.add(a.code);
}

function renderRegions() {
  // ---- 省份列 ----
  const qp = $("qProv").value.trim();
  const provs = state.regions.filter((p) => !qp || p.name.includes(qp));
  const provSel = regionChips().provs;
  $("cProv").textContent = provSel.size;
  $("lProv").innerHTML = provs.length
    ? provs.map((p) => {
        const on = state.selectedRegions.has(p.code) || provSel.has(p.code);
        return `<div class="rrow ${on ? "checked" : ""}" data-code="${p.code}" data-kind="p"><input type="checkbox" ${on ? "checked" : ""}><span>${esc(p.name)}</span><span class="meta">${provinceDistricts(p)} 区县</span></div>`;
      }).join("")
    : `<div class="empty-tip">无匹配</div>`;

  // ---- 城市列（所选省的城市） ----
  const qc = $("qCity").value.trim();
  const activeProvs = provSel;
  const cities = [];
  for (const p of state.regions) {
    if (activeProvs.has(p.code)) for (const c of p.children || []) cities.push({ p, c });
  }
  const citySel = regionChips().cities;
  $("cCity").textContent = citySel.size;
  const cList = cities.filter(({ c }) => !qc || c.name.includes(qc));
  $("lCity").innerHTML = cList.length
    ? cList.map(({ p, c }) => {
        const on = state.selectedRegions.has(c.code) || citySel.has(c.code);
        return `<div class="rrow ${on ? "checked" : ""}" data-code="${c.code}" data-kind="c" data-p="${p.code}"><input type="checkbox" ${on ? "checked" : ""}><span>${esc(c.name)}</span><span class="meta">${(c.children || []).length} 区县</span></div>`;
      }).join("")
    : `<div class="empty-tip">${activeProvs.size ? "无匹配" : "请先选择省份"}</div>`;

  // ---- 区县列（所选城市的区县） ----
  const qa = $("qArea").value.trim();
  const activeCities = citySel;
  const areas = [];
  for (const p of state.regions) {
    for (const c of p.children || []) {
      if (activeCities.has(c.code)) for (const a of c.children || []) areas.push({ c, a });
    }
  }
  const areaSel = regionChips().areas;
  $("cArea").textContent = areaSel.size;
  const aList = areas.filter(({ a }) => !qa || a.name.includes(qa));
  $("lArea").innerHTML = aList.length
    ? aList.map(({ c, a }) => {
        const on = state.selectedRegions.has(a.code) || areaSel.has(a.code);
        return `<div class="rrow ${on ? "checked" : ""}" data-code="${a.code}" data-kind="a"><input type="checkbox" ${on ? "checked" : ""}><span>${esc(a.name)}</span><span class="meta">${esc(c.name)}</span></div>`;
      }).join("")
    : `<div class="empty-tip">${activeCities.size ? "无匹配" : "请先选择城市"}</div>`;

  // ---- 已选 chips ----
  const cp = regionChips();
  const provNames = [...cp.provs].map((code) => findProvince(code)).filter(Boolean).map((p) => p.name);
  const bar = $("selBar");
  bar.innerHTML = provNames.map((n) => `<span class="chip">${esc(n)}</span>`).join("") +
    `<span class="chip ghost">已选 ${cp.provs.size} 省 · ${cp.cities.size} 市 · ${cp.areas.size} 区县</span>`;
  const st = $("regionStat");
  st.textContent = cp.provs.size ? `已选 ${cp.provs.size} 省 / ${cp.cities.size} 市 / ${cp.areas.size} 区县` : "未选择任何区域";
}

// 列表点击委托
$("lProv").addEventListener("click", (e) => {
  const row = e.target.closest(".rrow"); if (!row) return;
  toggleProvince(findProvince(row.dataset.code));
  renderRegions();
});
$("lCity").addEventListener("click", (e) => {
  const row = e.target.closest(".rrow"); if (!row) return;
  const p = findProvince(row.dataset.p); const c = findCity(p, row.dataset.code);
  toggleCity(p, c); renderRegions();
});
$("lArea").addEventListener("click", (e) => {
  const row = e.target.closest(".rrow"); if (!row) return;
  toggleArea(findRegion(row.dataset.code).area); renderRegions();
});
["qProv", "qCity", "qArea"].forEach((id) => $(id).addEventListener("input", renderRegions));

$("allProv").addEventListener("click", () => {
  const all = state.regions.every((p) => state.selectedRegions.has(p.code));
  for (const p of state.regions) { const add = !all; const codes = [p.code]; for (const c of p.children || []) { codes.push(c.code); for (const a of c.children || []) codes.push(a.code); } for (const code of codes) add ? state.selectedRegions.add(code) : state.selectedRegions.delete(code); }
  renderRegions();
});
$("allCity").addEventListener("click", () => {
  const cp = regionChips().provs;
  for (const p of state.regions) if (cp.has(p.code)) for (const c of p.children || []) { const add = !state.selectedRegions.has(c.code); const codes = [c.code, ...(c.children || []).map((a) => a.code)]; for (const code of codes) add ? state.selectedRegions.add(code) : state.selectedRegions.delete(code); }
  renderRegions();
});
$("allArea").addEventListener("click", () => {
  const cc = regionChips().cities;
  for (const p of state.regions) for (const c of p.children || []) if (cc.has(c.code)) for (const a of c.children || []) state.selectedRegions.add(a.code);
  renderRegions();
});
$("clearRegions").addEventListener("click", () => { state.selectedRegions.clear(); renderRegions(); });

/* ================= POI 分类 ================= */
function renderCats() {
  $("catGrid").innerHTML = state.cats.map((c) => {
    const on = state.selCat.has(c.code);
    return `<div class="cat-item ${on ? "checked" : ""}" data-code="${c.code}"><input type="checkbox" ${on ? "checked" : ""}><span>${esc(c.name)}</span><span class="code">${c.code}</span></div>`;
  }).join("");
  renderSubCats();
  renderCatBar();
}
function renderSubCats() {
  const box = document.querySelector(".sub-box");
  if (box) box.remove();
  const checked = [...state.selCat.values()];
  if (!checked.length) return;
  const el = document.createElement("div");
  el.className = "sub-box";
  const html = checked.map((s) => {
    const cat = state.cats.find((c) => c.code === s.first);
    const children = (cat && cat.children) || [];
    if (!children.length) return "";
    return `<h4>${esc(cat.name)} — 二级分类</h4>
      <div class="sub-chips" data-first="${cat.code}">
        ${children.map((ch) => `<span class="schip ${s.seconds.has(ch) ? "checked" : ""}" data-sub="${esc(ch)}">${esc(ch)}</span>`).join("")}
        <span class="empty-tip" style="margin-left:4px">不选二级 = 全部</span>
      </div>`;
  }).join("");
  el.innerHTML = html || "";
  $("catGrid").insertAdjacentElement("afterend", el);
}
document.addEventListener("click", (e) => {
  const schip = e.target.closest(".schip"); if (!schip) return;
  const first = schip.closest(".sub-chips").dataset.first;
  const sub = schip.dataset.sub;
  const s = state.selCat.get(first); if (!s) return;
  s.seconds.has(sub) ? s.seconds.delete(sub) : s.seconds.add(sub);
  renderSubCats(); renderCatBar();
});
$("catGrid").addEventListener("click", (e) => {
  const item = e.target.closest(".cat-item"); if (!item) return;
  const code = item.dataset.code;
  const cat = state.cats.find((c) => c.code === code);
  if (state.selCat.has(code)) state.selCat.delete(code);
  else state.selCat.set(code, { first: cat.code, name: cat.name, seconds: new Set() });
  renderCats();
});
$("addManual").addEventListener("click", () => {
  const v = $("manualType").value.trim(); if (!v) return;
  v.split("|").map((s) => s.trim()).filter(Boolean).forEach((s) => state.manualTypes.add(s));
  $("manualType").value = ""; renderCatBar();
});
function renderCatBar() {
  const bar = $("catSelBar");
  const cats = [...state.selCat.values()];
  const catChips = cats.map((s) => {
    const sec = [...s.seconds];
    const label = sec.length ? `${s.name}(${sec.length}个二级)` : s.name;
    return `<span class="chip" data-rm="${s.first}">${esc(label)} <span class="x">×</span></span>`;
  }).join("");
  const manual = [...state.manualTypes].map((t) => `<span class="chip" data-rmm="${esc(t)}">${esc(t)} <span class="x">×</span></span>`).join("");
  bar.innerHTML =
    `<button class="btn ghost2 sm" id="allCats">全选一级</button>` +
    `<button class="btn ghost2 sm" id="clearCats">清空</button>` +
    catChips + manual +
    `<span class="chip ghost">${cats.length} 个一级分类 · ${[...state.manualTypes].length} 个自定义</span>`;
  bar.querySelector("#allCats").onclick = () => { state.cats.forEach((c) => state.selCat.set(c.code, { first: c.code, name: c.name, seconds: new Set() })); renderCats(); };
  bar.querySelector("#clearCats").onclick = () => { state.selCat.clear(); state.manualTypes.clear(); renderCats(); };
  bar.querySelectorAll(".chip[data-rm]").forEach((el) => el.querySelector(".x").onclick = () => { state.selCat.delete(el.dataset.rm); renderCats(); });
  bar.querySelectorAll(".chip[data-rmm]").forEach((el) => el.querySelector(".x").onclick = () => { state.manualTypes.delete(el.dataset.rmm); renderCatBar(); });
}
function categoryPayload() {
  const items = [...state.selCat.values()].map((s) => ({ first: s.first, second: [...s.seconds] }));
  [...state.manualTypes].forEach((t) => items.push({ first: t, second: [] }));
  return items;
}

/* ================= Key 管理 ================= */
function renderKeys() {
  $("keyCount").textContent = state.keys.length;
  const totalQuota = state.keys.reduce((n, k) => n + (k.daily_quota_calls || 0), 0);
  $("keyHint").textContent = state.keys.length ? `合计免费配额 ${fmt(totalQuota)} 次/日` : "默认按「个人认证 · 搜索类 · 日配额 5000 次」预估";
  $("keyList").innerHTML = state.keys.length
    ? state.keys.map((k) => `
      <div class="key-row" data-key="${esc(k.key)}">
        <span class="k">${esc(k.key)}</span>
        ${k.note ? `<span class="tag">${esc(k.note)}</span>` : ""}
        <div class="kmeta">
          <span class="tag">日配额 <input type="number" class="quota" value="${k.daily_quota_calls || 5000}" min="0" title="当日免费调用次数"></span>
          <span class="tag">QPS <input type="number" class="qps" value="${k.qps || 3}" min="1" max="20" title="每秒调用上限"></span>
          <button class="btn danger sm rm">删除</button>
        </div>
      </div>`).join("")
    : `<div class="empty-tip">尚未添加任何 Key —— 预估与爬取都需要至少 1 个有效 Key</div>`;
  // 编辑事件
  $("keyList").querySelectorAll(".key-row").forEach((row) => {
    const key = row.dataset.key;
    row.querySelector(".quota").addEventListener("change", (e) => updateKey(key, { daily_quota_calls: +e.target.value }));
    row.querySelector(".qps").addEventListener("change", (e) => updateKey(key, { qps: +e.target.value }));
    row.querySelector(".rm").addEventListener("click", () => keyAction("remove", { key }));
  });
}
async function updateKey(key, patch) {
  await jpost(api.keys, { action: "update", key, ...patch });
  const k = state.keys.find((x) => x.key === key); if (k) Object.assign(k, patch);
  renderKeys();
}
async function keyAction(action, extra) {
  await jpost(api.keys, { action, ...extra });
  await loadKeys();
}
async function loadKeys() { state.keys = (await (await fetch(api.keys)).json()).keys || []; renderKeys(); }

$("addKey").addEventListener("click", async () => {
  const key = $("keyInput").value.trim(), note = $("keyNote").value.trim();
  if (!key) return;
  await keyAction("add", { key, note, qps: +$("defQps").value, daily_quota_calls: +$("defQuota").value });
  $("keyInput").value = ""; $("keyNote").value = "";
});
$("importKeys").addEventListener("click", async () => {
  const text = $("keyImport").value;
  if (!text.trim()) return;
  const r = await jpost(api.keys, { action: "import", text, qps: +$("defQps").value, daily_quota_calls: +$("defQuota").value });
  alert(`成功导入 ${r.added} 个 Key`);
  $("keyImport").value = ""; await loadKeys();
});
$("clearKeys").addEventListener("click", async () => { if (confirm("确认清空全部 Key？")) { await keyAction("clear", {}); } });

/* ================= 参数 ================= */
function params() {
  return {
    per_request: Math.min(25, Math.max(1, +$("perRequest").value || 20)),
    max_per_combo: Math.max(25, +$("maxPerCombo").value || 200),
  };
}
function mode() {
  const m = document.querySelector('input[name="mode"]:checked').value;
  return { mode: m, sample_size: Math.max(1, +$("sampleSize").value || 50) };
}

/* ================= 预估 ================= */
$("btnEstimate").addEventListener("click", async () => {
  const btn = $("btnEstimate"); btn.disabled = true;
  try {
    if (!state.selectedRegions.size) throw new Error("请先选择行政范围");
    if (!categoryPayload().length) throw new Error("请先选择 POI 分类");
    if (!state.keys.length) throw new Error("请先添加至少一个 API Key");
    const data = await jpost(api.estimate, {
      region_codes: [...state.selectedRegions],
      categories: categoryPayload(),
      params: params(),
      ...mode(),
    });
    renderEstimate(data);
  } catch (e) {
    showMsg($("warnBox"), e.message, "red");
  } finally { btn.disabled = false; }
});

function showMsg(box, text, tone) {
  box.innerHTML = `<div class="warn ${tone}"><div class="ico">${tone === "red" ? "⚠️" : tone === "amber" ? "⚠️" : "✔️"}</div><div><h4>${esc(text)}</h4></div></div>`;
}

function renderEstimate(data) {
  const q = data.quota, e = data.estimate, sel = data.selection;
  $("estCard").style.display = "block";
  $("estStamp").textContent = `估算调用 ${fmt(e.estimate_calls)} 次` + (e.sampling ? "（抽样）" : "（全量）");
  $("estSel").textContent = `${sel.provinces} 省 / ${sel.cities} 市 / ${sel.districts} 区县`;
  $("estCombo").textContent = `${fmt(data.district_count)} 区县 × ${data.type_count} 分类 = ${fmt(data.district_count * data.type_count)} 组合`;
  $("estCalls").textContent = `${fmt(q.required_calls)} 次调用`;
  $("estSingle").textContent = q.per_key_max_poi.length ? `约 ${fmt(q.per_key_max_poi[0].max_poi)} 条/Key/日` : "—";
  $("estAllKey").textContent = `约 ${fmt(q.all_key_max_poi)} 条/日`;
  $("estTime").textContent = `${fmt(Math.round(q.crawl_seconds))} 秒（按合计 QPS ${q.total_qps}）`;
  $("estShard").textContent = `${q.need_shard_combos} 个组合超上限需分片`;

  $("statGrid").innerHTML = `
    <div class="stat"><div class="v amber">${fmt(e.total_poi)}</div><div class="l">预估 POI 总数</div></div>
    <div class="stat"><div class="v">${fmt(q.required_calls)}</div><div class="l">抓取所需调用次数</div></div>
    <div class="stat"><div class="v green">${fmt(q.all_key_max_poi)}</div><div class="l">全部Key免费上限(条/日)</div></div>
    <div class="stat"><div class="v ${q.over ? "red" : "green"}">${q.over ? "超额" : "充足"}</div><div class="l">配额状态</div></div>
    <div class="stat"><div class="v">${q.days_needed ?? "—"}</div><div class="l">所需天数</div></div>`;

  // 预警
  const warn = $("warnBox"); warn.innerHTML = "";
  if (e.error_count > 0) {
    const first = e.errors[0];
    showMsg(warn, `预估中有 ${e.error_count} 个组合失败（示例：${esc(first.region)}/${esc(first.category)} → ${esc(first.info)}，infocode ${esc(first.infocode)}）。请检查 API Key 是否有效、当日配额是否足够。`, "amber");
  } else if (q.over) {
    showMsg(warn, `超额预警：所需 ${fmt(q.required_calls)} 次调用 > 全部 Key 免费配额 ${fmt(q.total_quota_calls)} 次/日，单日无法完成，需约 ${q.days_needed} 天。持续超配额会被系统判定限号（错误码 10003/10004），建议补充 Key、分批跨天或缩小范围。`, "red");
  } else if (q.over_poi_capacity) {
    showMsg(warn, `POI 总量 ${fmt(e.total_poi)} 已接近全部 Key 免费可获取上限 ${fmt(q.all_key_max_poi)} 条，存在限号风险，请谨慎执行。`, "amber");
  } else {
    showMsg(warn, `配额充足：所需调用 ${fmt(q.required_calls)} 次 ≤ 免费配额 ${fmt(q.total_quota_calls)} 次/日，可安全执行。`, "green");
  }

  // 分布（按分类聚合 top）
  const byCat = {};
  e.combos.forEach((c) => { byCat[c.category] = (byCat[c.category] || 0) + c.scaled; });
  const top = Object.entries(byCat).sort((a, b) => b[1] - a[1]).slice(0, 12);
  const max = Math.max(1, ...top.map(([, v]) => v));
  $("distBlock").innerHTML = `<h4 style="margin:0 0 8px;font-size:12.5px;color:var(--ink-2)">按分类分布（预估）</h4>` +
    top.map(([k, v]) => `<div class="dist-row"><span class="nm">${esc(k)}</span><div class="bar"><i style="width:${(v / max * 100).toFixed(1)}%"></i></div><span style="width:90px;text-align:right;font-family:var(--mono);font-size:11px">${fmt(v)}</span></div>`).join("");
}

/* ================= 爬取（SSE） ================= */
$("btnCrawl").addEventListener("click", async () => {
  if (state.crawling) return;
  try {
    if (!state.selectedRegions.size) throw new Error("请先选择行政范围");
    if (!categoryPayload().length) throw new Error("请先选择 POI 分类");
    if (!state.keys.length) throw new Error("请先添加至少一个 API Key");
  } catch (e) { alert(e.message); return; }

  state.crawling = true;
  const btn = $("btnCrawl"); btn.disabled = true; btn.textContent = "爬取中…";
  $("crawlCard").style.display = "block";
  $("crawlBar").classList.add("moving");
  $("crawlLog").innerHTML = `<span class="ln">· 建立连接，启动爬取…</span>`;
  logln("· 请求 /api/crawl 建立 SSE 连接");
  const bar = $("crawlBar").querySelector("i");
  bar.style.width = "0%";

  const body = {
    region_codes: [...state.selectedRegions],
    categories: categoryPayload(),
    params: params(),
  };
  try {
    const resp = await fetch(api.crawl, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    if (!resp.ok || !resp.body) throw new Error("SSE 连接失败");
    const reader = resp.body.getReader();
    const dec = new TextDecoder();
    let buf = "";
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += dec.decode(value, { stream: true });
      const parts = buf.split("\n\n");
      buf = parts.pop();
      for (const part of parts) {
        const line = part.split("\n").find((l) => l.startsWith("data: "));
        if (!line) continue;
        const msg = JSON.parse(line.slice(6));
        handleCrawlMsg(msg);
      }
    }
  } catch (e) {
    logln("✗ " + e.message, "err");
  } finally {
    state.crawling = false;
    btn.disabled = false; btn.textContent = "② 开始爬取";
    $("crawlBar").classList.remove("moving");
    logln("· 连接结束");
  }
});

function handleCrawlMsg(msg) {
  if (msg.phase === "summary") { onCrawlSummary(msg.summary); return; }
  if (msg.phase === "error") { logln("✗ " + (msg.error || ""), "err"); return; }
  if (msg.phase === "end") return;
  const total = msg.total || 1, processed = msg.processed || 0;
  const pct = Math.min(100, (processed / total) * 100);
  $("crawlBar").querySelector("i").style.width = pct + "%";
  $("crawlPct").textContent = pct.toFixed(0) + "%";
  $("crawlMeta").textContent = `${processed}/${total} 组合 · 已抓取 ${fmt(msg.collected || 0)} 条 POI`;
  if (msg.current) logln(msg.current);
}
function onCrawlSummary(s) {
  $("crawlBar").querySelector("i").style.width = "100%";
  $("crawlPct").textContent = "100%";
  $("crawlMeta").textContent = `完成：共抓取 ${fmt(s.total_poi)} 条 POI`;
  $("crawlResult").innerHTML = `
    <div class="warn green" style="margin-top:12px"><div class="ico">✔️</div><div>
      <h4>爬取完成 — 共 ${fmt(s.total_poi)} 条 POI</h4>
      <p>结果已写入：<code class="inline">${esc(s.csv)}</code>　·　去重后条数（按 POI id）</p>
      <p style="margin-top:6px">Key 用量：${s.keys_usage.map((k) => `${esc(String(k.key).slice(0, 8))}… ${k.used}/${k.quota}${k.blocked ? "（已封禁）" : ""}`).join("　")}</p>
    </div></div>`;
  logln(`✔ 完成：${s.total_poi} 条 → ${s.csv}`, "ok");
}
function logln(text, cls = "") {
  const box = $("crawlLog");
  const d = document.createElement("span");
  d.className = "ln " + cls; d.textContent = text;
  box.appendChild(d);
  box.scrollTop = box.scrollHeight;
}

/* ================= 初始化 ================= */
(async function init() {
  state.regions = (await (await fetch(api.regions)).json()).regions || [];
  state.cats = (await (await fetch(api.categories)).json()).categories || [];
  state.cats = state.cats.map((c) => ({ ...c, children: c.children || [] }));
  await loadKeys();
  renderRegions();
  renderCats();
  // 默认勾选示例：湖北省 → 咸宁市（通城所在）方便试跑
  const hubei = state.regions.find((p) => p.name.includes("湖北"));
  if (hubei) toggleProvince(hubei);
  renderRegions();
})();

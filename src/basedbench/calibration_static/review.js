"use strict";
const $ = s => document.querySelector(s);
const node = (tag, text, cls) => { const n = document.createElement(tag); if (text !== undefined) n.textContent = text; if (cls) n.className = cls; return n; };
let data, index = 0, busy = false;
const drafts = new Map(), contexts = new Map(), retries = new Map();
const active = () => data.cases[index];
const key = c => `basedbench-calibration:${data.packet_id}:${c.post_id}`;
const saved = c => ({fields: {...(c.latest?.fields || {})}, notes: c.latest?.notes || "", base_revision: c.latest?.event_id || null});
const draft = c => drafts.get(c.post_id) || saved(c);
const dirty = c => JSON.stringify(draft(c)) !== JSON.stringify(saved(c));
const complete = c => c.answers.every((_, i) => c.latest?.fields[`quality_${"ab"[i]}`]);
const status = (text, error = false) => { $("#status").textContent = text; $("#status").classList.toggle("error", error); };
function persist() {
  const c = active(), d = draft(c); d.notes = $("#notes").value; drafts.set(c.post_id, d);
  try { localStorage.setItem(key(c), JSON.stringify(d)); status("Unsaved draft · kept in this browser. Press Save to record it."); }
  catch { status("Browser draft storage unavailable. Press Save before leaving.", true); }
  $("#discard").hidden = !dirty(c); progress();
}
function progress() {
  $("#progress").textContent = `${data.cases.filter(complete).length} / ${data.cases.length}`;
  const count = data.cases.filter(dirty).length;
  $("#draft-count").textContent = count ? `${count} unsaved draft${count === 1 ? "" : "s"}` : "Feedback saves on this computer.";
  $("#case-list").replaceChildren();
  data.cases.forEach((c, i) => {
    const b = node("button", `${i + 1}${dirty(c) ? "*" : ""}`, complete(c) ? "saved" : "");
    b.setAttribute("aria-label", `Case ${i + 1}${complete(c) ? ", reviewed" : ""}`);
    b.setAttribute("aria-pressed", i === index); b.disabled = busy;
    b.addEventListener("click", () => open(i)); $("#case-list").append(b);
  });
}
function choices(field, container, optional = false) {
  const spec = data.rubric.fields[field], f = node("fieldset"); f.append(node("legend", spec.label));
  const row = node("div", undefined, "choices");
  for (const [value, label] of Object.entries(spec.options)) {
    const b = node("button", label); b.type = "button"; b.dataset.field = field; b.dataset.value = value;
    b.setAttribute("aria-pressed", draft(active()).fields[field] === value);
    b.addEventListener("click", () => {
      const d = draft(active()); if (d.fields[field] === value) delete d.fields[field]; else d.fields[field] = value;
      drafts.set(active().post_id, d);
      row.querySelectorAll("button").forEach(n => n.setAttribute("aria-pressed", d.fields[field] === n.dataset.value));
      persist();
    }); row.append(b);
  }
  f.append(row);
  if (optional) { const details = node("details", undefined, "reason"); details.append(node("summary", "Add a reason (optional)"), f); details.open = Boolean(draft(active()).fields[field]); container.append(details); }
  else container.append(f);
}
function open(i) {
  index = i; const c = active();
  $("#position").textContent = `Case ${i + 1} of ${data.cases.length}`;
  $("#meme").src = c.image_url; $("#notes").value = draft(c).notes;
  $("#answers").replaceChildren();
  c.answers.forEach((text, a) => {
    const box = node("article", undefined, "answer");
    box.append(node("h2", c.answers.length === 1 ? "Explanation" : `Answer ${"AB"[a]}`), node("p", text, "answer-text"));
    choices(`quality_${"ab"[a]}`, box); choices(`reason_${"ab"[a]}`, box, true); $("#answers").append(box);
  });
  $("#pair-options").hidden = c.answers.length < 2; $("#preference").replaceChildren();
  if (c.answers.length === 2) choices("preference", $("#preference"));
  $("#comments").hidden = !contexts.has(c.post_id); $("#comments").textContent = contexts.get(c.post_id) || "";
  $("#exposure").textContent = c.revealed.length ? "Source comments were previously revealed for this case." : "";
  $("#discard").hidden = !dirty(c);
  status(dirty(c) ? "Unsaved draft restored from this browser." : c.latest ? `Saved ${new Date(c.latest.recorded_at).toLocaleString()} · ${c.save_count} revision(s) preserved.` : "Choose what you can judge. Uncertain and partial feedback are welcome.");
  if (draft(c).base_revision !== (c.latest?.event_id || null)) status("A newer save exists. Copy your note before discarding this draft to load the latest save.", true);
  setBusy(false); progress();
}
function setBusy(value) {
  busy = value;
  document.querySelectorAll("main button,textarea").forEach(b => b.disabled = value);
  if (!value) {
    $("#previous").disabled = index === 0;
    $("#next").disabled = $("#save-next").disabled = index === data.cases.length - 1;
    $("#reveal").disabled = contexts.has(active().post_id);
    $("#reveal").textContent = contexts.has(active().post_id) ? "Source comments revealed" : "Reveal source comments";
  }
}
async function record(kind) {
  const c = active(), body = {post_id: c.post_id, packet_id: data.packet_id, input_sha256: c.input_sha256,
    ...draft(c), kind, reveal: kind === "reveal" ? "comments" : null};
  const signature = JSON.stringify(body);
  if (!retries.has(signature)) retries.set(signature, crypto.randomUUID());
  body.request_id = retries.get(signature);
  const response = await fetch("/api/events", {method: "POST", headers: {"Content-Type": "application/json", "X-Review-Token": data.token}, body: JSON.stringify(body)});
  const result = await response.json();
  if (response.status === 409) {
    const fresh = await fetch("/api/cases");
    if (fresh.ok) { const current = await fresh.json(); Object.assign(c, current.cases.find(x => x.post_id === c.post_id)); data.token = current.token; $("#discard").hidden = false; }
  }
  if (!response.ok) throw new Error(result.error || "Could not confirm save; your draft is kept here. Retry.");
  retries.delete(signature); Object.assign(c, result.state); return result;
}
async function save(next) {
  if (busy) return; setBusy(true); status("Saving…");
  try {
    await record("feedback"); drafts.delete(active().post_id);
    try { localStorage.removeItem(key(active())); } catch { /* Disk save succeeded. */ }
    open(next ? Math.min(index + 1, data.cases.length - 1) : index);
  } catch (error) { status(error.message, true); }
  finally { setBusy(false); progress(); }
}
$("#feedback").addEventListener("submit", e => { e.preventDefault(); save(false); });
$("#save-next").addEventListener("click", () => save(true));
$("#notes").addEventListener("input", persist);
$("#previous").addEventListener("click", () => open(index - 1));
$("#next").addEventListener("click", () => open(index + 1));
$("#next-unreviewed").addEventListener("click", () => {
  for (let n = 1; n <= data.cases.length; n++) { const i = (index + n) % data.cases.length; if (!complete(data.cases[i])) { open(i); return; } }
  status("All cases have saved judgments. You can still revise any case.");
});
$("#both").addEventListener("click", () => {
  const d = draft(active()); d.fields.quality_a = d.fields.quality_b = "ready"; drafts.set(active().post_id, d); persist(); open(index);
});
$("#discard").addEventListener("click", () => { drafts.delete(active().post_id); try { localStorage.removeItem(key(active())); } catch { /* In-memory reset works. */ } open(index); });
$("#reveal").addEventListener("click", async () => {
  if (busy) return; setBusy(true);
  try { const result = await record("reveal"); contexts.set(active().post_id, result.context.comments); open(index); status("Draft checkpoint recorded before revealing comments. Save when your judgment is ready."); }
  catch (error) { status(error.message, true); } finally { setBusy(false); }
});
$("#enlarge").addEventListener("click", () => { $("#zoom-image").src = active().image_url; $("#zoom").showModal(); });
$("#close-zoom").addEventListener("click", () => $("#zoom").close());
window.addEventListener("beforeunload", e => { if (data && data.cases.some(dirty)) { e.preventDefault(); e.returnValue = ""; } });
(async () => {
  try {
    const response = await fetch("/api/cases"); data = await response.json(); if (!response.ok) throw new Error(data.error);
    for (const p of data.rubric.principles) $("#principles").append(node("p", p));
    for (const c of data.cases) { try { const d = JSON.parse(localStorage.getItem(key(c))); if (d?.fields && typeof d.notes === "string") drafts.set(c.post_id, d); } catch { /* Saved feedback still loads. */ } }
    open(Math.max(0, data.cases.findIndex(c => !complete(c))));
  } catch (e) { $("#load-error").hidden = false; $("#load-error").textContent = `Could not load review: ${e.message}. Keep the local server running and reload.`; }
})();

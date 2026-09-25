"use strict";
const $ = (selector) => document.querySelector(selector);
const make = (tag, text, className) => {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (className) node.className = className;
  return node;
};
let data, active, collection = "fresh", busy = false;
const drafts = new Map(), contexts = new Map(), retries = new Map();
const dialog = $("#review-dialog");
const fieldOrder = ["content", "ground_truth", "value", "admission", "familiarity", "difficulty"];
const optionOrder = {
  content: ["pass", "fail", "boundary", "uncertain"], ground_truth: ["ready", "repair", "uncertain"],
  value: ["yes", "no", "unsure"], admission: ["accept", "reject", "repair", "undecided"],
  familiarity: ["familiar", "needed_context", "unclear"], difficulty: ["easy", "medium", "hard", "unsure"]
};
const storageKey = (c) => `basedbench-review:${data.packet_id}:${c.post_id}`;
const savedDraft = (c) => ({fields: {...(c.latest?.fields || {})}, notes: c.latest?.notes || "", base_revision: c.latest?.event_id || null});
const currentDraft = (c) => drafts.get(c.post_id) || savedDraft(c);
const dirty = (c) => JSON.stringify(currentDraft(c)) !== JSON.stringify(savedDraft(c));
const fieldSpec = (key) => ({...data.rubric.fields[key], ...(data.question_copy?.fields[key] || {})});
function persistDraft() {
  if (!active) return;
  const draft = currentDraft(active);
  draft.notes = $("#notes").value;
  drafts.set(active.post_id, draft);
  try {
    localStorage.setItem(storageKey(active), JSON.stringify(draft));
    setStatus(dirty(active) ? "Unsaved draft · kept in this browser. Press Save to record it." : savedMessage(active));
  } catch {
    setStatus("Browser draft storage is unavailable. Press Save before leaving.", true);
  }
  $("#restore-saved").hidden = !dirty(active);
  renderGallery();
}
function savedMessage(c) {
  if (!c.latest) return "Choose any fields you can judge; leave the others blank.";
  return `Saved ${new Date(c.latest.recorded_at).toLocaleString()} · ${c.save_count} revision${c.save_count === 1 ? "" : "s"}`;
}
function setStatus(message, error = false) {
  $("#save-status").textContent = message;
  $("#save-status").classList.toggle("error", error);
}
function renderGallery() {
  const fresh = data.cases.filter(c => c.collection === "fresh");
  const done = fresh.filter(c => c.latest).length;
  $("#progress-number").textContent = `${done} / ${fresh.length}`;
  $("#progress-bar").style.width = `${done / fresh.length * 100}%`;
  const draftCount = data.cases.filter(dirty).length;
  $("#draft-count").textContent = draftCount ? `${draftCount} unsaved draft${draftCount === 1 ? "" : "s"} in this browser.` : "Feedback saves on this computer.";
  const filter = $("#status-filter").value;
  const cases = data.cases.filter(c => c.collection === collection);
  const shown = cases.filter(c => filter === "all" || (filter === "todo" && !c.latest) || (filter === "saved" && c.latest) || (filter === "draft" && dirty(c)));
  $("#gallery-count").textContent = `${shown.length} of ${cases.length} cases · ${collection === "fresh" ? "New review round" : "Previously discussed"}`;
  const gallery = $("#gallery");
  gallery.replaceChildren();
  for (const c of shown) {
    const article = make("article", undefined, "card");
    const index = cases.indexOf(c) + 1;
    const button = make("button", undefined, "card-image");
    button.setAttribute("aria-label", `Review ${collection === "fresh" ? "new" : "previous"} case ${index}`);
    const img = make("img");
    img.src = c.image_url;
    img.alt = `Meme ${index}`;
    img.loading = "lazy";
    button.append(img);
    button.addEventListener("click", () => openCase(c));
    const bottom = make("div", undefined, "card-bottom");
    const label = make("p", `Case ${String(index).padStart(2, "0")}`);
    label.append(make("small", c.post_id));
    const state = dirty(c) ? "Draft" : c.latest ? "Saved" : "Ready to review";
    bottom.append(label, make("span", state, `status ${dirty(c) ? "draft" : c.latest ? "saved" : ""}`));
    article.append(button, bottom);
    gallery.append(article);
  }
}
function setCollection(value) {
  collection = value;
  $("#fresh-tab").setAttribute("aria-pressed", value === "fresh");
  $("#previous-tab").setAttribute("aria-pressed", value === "previous");
  renderGallery();
}
function openCase(c) {
  active = c;
  const cases = data.cases.filter(item => item.collection === c.collection);
  const index = cases.indexOf(c);
  $("#case-number").textContent = `${c.collection === "fresh" ? "New round" : "Previous discussion"} · ${index + 1} of ${cases.length}`;
  $("#case-heading").textContent = `Case ${String(index + 1).padStart(2, "0")} · ${c.post_id}`;
  $("#case-image").src = c.image_url;
  $("#case-answer").textContent = c.explanation;
  $("#notes").value = currentDraft(c).notes;
  $("#prev-case").disabled = index === 0;
  $("#next-case").disabled = index === cases.length - 1;
  $("#save-next").disabled = index === cases.length - 1;
  $("#fields").replaceChildren();
  for (const key of fieldOrder) {
    const spec = fieldSpec(key);
    const fieldset = make("fieldset", undefined, "question");
    fieldset.append(make("legend", spec.label), make("p", spec.hint, "help"));
    const options = make("div", undefined, "choices");
    for (const value of optionOrder[key]) {
      const label = spec.options[value];
      const button = make("button", label);
      button.type = "button";
      button.dataset.field = key;
      button.dataset.value = value;
      button.setAttribute("aria-pressed", currentDraft(c).fields[key] === value);
      button.addEventListener("click", () => {
        const draft = currentDraft(c);
        if (draft.fields[key] === value) delete draft.fields[key];
        else draft.fields[key] = value;
        drafts.set(c.post_id, draft);
        options.querySelectorAll("button").forEach(b => b.setAttribute("aria-pressed", draft.fields[key] === b.dataset.value));
        persistDraft();
      });
      options.append(button);
    }
    fieldset.append(options);
    $("#fields").append(fieldset);
  }
  showContext(c);
  setStatus(dirty(c) ? "Unsaved draft restored from this browser." : savedMessage(c));
  $("#restore-saved").hidden = !dirty(c);
  if (currentDraft(c).base_revision !== (c.latest?.event_id || null)) {
    setStatus("This draft predates a saved revision. Copy any note you want to keep, then use ‘Discard draft; load latest save’ to compare and revise.", true);
  }
  $("#history-block").hidden = !c.latest;
  $("#history").replaceChildren();
  if (c.latest) {
    $("#history").append(make("p", `${c.save_count} revision(s) preserved. Latest saved judgment:`));
    for (const [key, value] of Object.entries(c.latest.fields)) {
      $("#history").append(make("p", `${fieldSpec(key).label} ${fieldSpec(key).options[value]}`));
    }
    if (c.latest.notes) $("#history").append(make("p", c.latest.notes));
  }
  if (!dialog.open) dialog.showModal();
  dialog.scrollTop = 0;
}
function showContext(c) {
  const cached = contexts.get(c.post_id) || {};
  $("#comments").hidden = !cached.comments;
  $("#comments").textContent = cached.comments?.comments || "";
  $("#opinions").hidden = !cached.opinions;
  $("#opinions").replaceChildren();
  $("#show-comments").textContent = cached.comments ? "Source comments revealed" : "Reveal source comments";
  $("#show-opinions").textContent = cached.opinions ? "Past decisions & model opinions revealed" : "Reveal past decisions & model opinions";
  $("#show-comments").disabled = Boolean(cached.comments);
  $("#show-opinions").disabled = Boolean(cached.opinions);
  const exposure = [];
  if (c.previously_discussed) exposure.push("This case was already discussed in the earlier round.");
  if (c.revealed.length) exposure.push(`Already revealed in this gallery: ${c.revealed.join(" and ")}.`);
  $("#exposure-note").textContent = exposure.join(" ");
  if (!cached.opinions) return;
  const opinion = cached.opinions;
  const block = (heading, paragraphs) => {
    const section = make("section", undefined, "opinion");
    section.append(make("h4", heading));
    for (const text of paragraphs) section.append(make("p", text));
    $("#opinions").append(section);
  };
  block("Original review", [`${opinion.historical_label} · ${opinion.reviewed_at}`, `Selection: ${opinion.stratum.replaceAll("_", " ")}. Historical choices are not definitive new labels.`]);
  for (const previous of opinion.previous_feedback) {
    const item = previous.item;
    const paragraphs = [item.assessment_summary || `Overall: ${item.current_decision || "not decided"}`, item.reason];
    if (previous.difficulty) paragraphs.push("Top Gear may be easy: a tentative curator impression, not measured difficulty. It remains accepted.");
    for (const [key, value] of Object.entries(item.dimensions || {})) paragraphs.push(`${key.replaceAll("_", " ")}: ${value.verdict} (${value.certainty || "not specified"})`);
    block(`Previous feedback · ${new Date(previous.recorded_at).toLocaleDateString()}`, paragraphs);
  }
  for (const decision of opinion.decisions) block(decision.model, [`Overall: ${decision.decision}`]);
  for (const component of opinion.components) {
    if (!component.checks) continue;
    const paragraphs = Object.entries(component.checks).map(([key, value]) => `${key.replaceAll("_", " ")}: ${value.verdict}${value.reason ? " — " + value.reason : ""}`);
    block(`${component.arm} · saved component checks`, paragraphs);
  }
  if (!opinion.decisions.length) block("Model opinions", ["This case was not a target in the saved API comparison. No new model call was made."]);
}
async function record(kind, reveal = null) {
  const c = active;
  const draft = currentDraft(c);
  const body = {post_id: c.post_id, input_sha256: c.input_sha256, packet_id: data.packet_id, ...draft, kind, reveal};
  if (data.question_copy) body.question_copy_sha256 = data.question_copy.sha256;
  const signature = JSON.stringify(body);
  if (!retries.has(signature)) retries.set(signature, crypto.randomUUID());
  body.request_id = retries.get(signature);
  const response = await fetch("/api/events", {method: "POST", headers: {"Content-Type": "application/json", "X-Review-Token": data.token}, body: JSON.stringify(body)});
  const result = await response.json();
  if (response.status === 409) {
    // Keep the local draft while making the recovery button load the real latest save.
    const refreshed = await fetch("/api/cases");
    if (refreshed.ok) {
      const catalog = await refreshed.json();
      const latest = catalog.cases.find(item => item.post_id === c.post_id);
      if (latest) Object.assign(c, latest);
      data.token = catalog.token;
      $("#restore-saved").hidden = false;
    }
  }
  if (!response.ok) throw new Error(result.error || "Could not save feedback. Your draft is still here.");
  retries.delete(signature);
  Object.assign(c, result.state);
  return result;
}
function setBusy(value) {
  busy = value;
  $("#feedback-form").querySelectorAll("button,textarea").forEach(node => node.disabled = value);
  for (const id of ["#close-review", "#prev-case", "#next-case", "#show-comments", "#show-opinions"]) $(id).disabled = value;
  if (!value && active) {
    const cases = data.cases.filter(c => c.collection === active.collection), index = cases.indexOf(active);
    $("#prev-case").disabled = index === 0;
    $("#next-case").disabled = $("#save-next").disabled = index === cases.length - 1;
    showContext(active);
  }
}
async function revealContext(type) {
  if (busy) return;
  setBusy(true);
  try {
    const result = await record("reveal", type);
    const cached = contexts.get(active.post_id) || {};
    cached[type] = result.context;
    contexts.set(active.post_id, cached);
    setStatus("Draft checkpoint recorded before this reveal. Save when your judgment is ready.");
  } catch (error) { setStatus(error.message, true); }
  finally { setBusy(false); }
}
async function save(next = false) {
  if (busy) return;
  setBusy(true);
  setStatus("Saving to this computer…");
  try {
    await record("feedback");
    drafts.delete(active.post_id);
    try { localStorage.removeItem(storageKey(active)); } catch { /* Disk save already succeeded. */ }
    renderGallery();
    const position = dialog.scrollTop;
    openCase(active);
    if (next) navigate(1);
    else dialog.scrollTop = position;
  } catch (error) { setStatus(error.message, true); }
  finally { setBusy(false); }
}
function navigate(offset) {
  const cases = data.cases.filter(c => c.collection === active.collection);
  const next = cases[cases.indexOf(active) + offset];
  if (next) openCase(next);
}
$("#fresh-tab").addEventListener("click", () => setCollection("fresh"));
$("#previous-tab").addEventListener("click", () => setCollection("previous"));
$("#status-filter").addEventListener("change", renderGallery);
$("#notes").addEventListener("input", persistDraft);
$("#feedback-form").addEventListener("submit", event => { event.preventDefault(); save(); });
$("#save-next").addEventListener("click", () => save(true));
$("#restore-saved").addEventListener("click", () => {
  drafts.delete(active.post_id);
  try { localStorage.removeItem(storageKey(active)); } catch { /* In-memory reset still works. */ }
  openCase(active);
  renderGallery();
});
$("#show-comments").addEventListener("click", () => revealContext("comments"));
$("#show-opinions").addEventListener("click", () => revealContext("opinions"));
$("#prev-case").addEventListener("click", () => navigate(-1));
$("#next-case").addEventListener("click", () => navigate(1));
$("#close-review").addEventListener("click", () => dialog.close());
dialog.addEventListener("cancel", event => { if (busy) event.preventDefault(); });
$("#enlarge-image").addEventListener("click", () => { $("#zoom-image").src = active.image_url; $("#image-dialog").showModal(); });
$("#close-image").addEventListener("click", () => $("#image-dialog").close());
window.addEventListener("beforeunload", event => { if (data && data.cases.some(dirty)) { event.preventDefault(); event.returnValue = ""; } });
async function init() {
  try {
    const response = await fetch("/api/cases");
    data = await response.json();
    if (!response.ok) throw new Error(data.error);
    for (const principle of data.rubric.principles) $("#rubric-principles").append(make("p", principle));
    for (const c of data.cases) {
      try {
        const stored = JSON.parse(localStorage.getItem(storageKey(c)));
        if (stored && stored.fields && typeof stored.notes === "string") drafts.set(c.post_id, stored);
      } catch { /* A broken local draft does not prevent loading saved feedback. */ }
    }
    $("#previous-count").textContent = data.cases.filter(c => c.collection === "previous").length;
    renderGallery();
  } catch (error) {
    $("#load-error").hidden = false;
    $("#load-error").textContent = `Could not load the gallery: ${error.message}. Keep the local server running and reload.`;
  }
}
init();

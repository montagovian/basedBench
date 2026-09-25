"use strict";
let packet, current = 0, dirty = false, busy = false;
const $ = id => document.getElementById(id);
const choices = ["A", "B"];
const el = (name, value, className) => { const node = document.createElement(name); if (value !== undefined) node.textContent = value; if (className) node.className = className; return node; };
function radioGroup(name, question, options, selected) {
  const field = el("fieldset"), legend = el("legend", question), row = el("div", undefined, "choices"); field.append(legend, row);
  for (const [value, title] of options) { const input = el("input"); input.type = "radio"; input.name = name; input.value = value; input.checked = selected === value; const label = el("label"); label.append(input, el("span", title)); row.append(label); }
  return field;
}
const checked = name => document.querySelector(`input[name="${name}"]:checked`)?.value;
const status = message => { $("status").textContent = message; };
function setBusy(value) {
  busy = value;
  document.querySelectorAll("#case-nav button, #case input, #case textarea, #case button").forEach(node => { node.disabled = value; });
}
function renderNav() {
  const nav = $("case-nav"); nav.replaceChildren();
  packet.cases.forEach((item, index) => { const button = el("button", String(index + 1)); button.type = "button"; button.title = item.state.saved_at ? `Case ${index + 1}, saved` : `Case ${index + 1}, unsaved`; button.classList.toggle("saved", !!item.state.saved_at); button.setAttribute("aria-current", String(index === current)); button.onclick = () => { if (busy || index === current) return; if (dirty && !window.confirm("Discard unsaved answers or note for this case?")) return; current = index; render(); }; nav.append(button); });
  $("progress").textContent = `${packet.cases.filter(c => c.state.saved_at).length} of ${packet.cases.length} saved`;
}
function excerptNode(excerpt) { const block = el("div", undefined, "excerpt"); block.append(el("div", excerpt.comment_id, "source-id"), el("div", excerpt.text)); return block; }
function listCard(item, choice) {
  const pack = item.packs[choice], card = el("section", undefined, "pack" + (pack.status === "unavailable" ? " unavailable" : "")); card.append(el("h3", `List ${choice}`));
  if (pack.status === "unavailable") { card.append(el("p", "This list is unavailable for this case.")); return card; }
  card.append(el("p", `${pack.word_count} words initially · ${pack.total_word_count} words in the full list`, "meta"));
  for (const excerpt of pack.excerpts) card.append(excerptNode(excerpt));
  if (!pack.excerpts.length) card.append(el("p", "No comments selected."));
  if (pack.extra_excerpts.length) { const more = el("details"); more.append(el("summary", `More selected comments (${pack.extra_excerpts.length})`)); for (const excerpt of pack.extra_excerpts) more.append(excerptNode(excerpt)); card.append(more); }
  const saved = item.state.ratings?.[choice];
  card.append(radioGroup(`${choice}-first`, "Does the first comment help you get the joke?", [["yes","Yes"],["partly","Partly"],["no","No"],["unsure","Unsure"]], saved?.first_helps));
  card.append(radioGroup(`${choice}-extras`, "Do the initial comments include irrelevant extras?", [["yes","Yes"],["no","No"],["unsure","Unsure"]], saved?.irrelevant_extras));
  return card;
}
function button(text, action, primary = false) { const node = el("button", text, primary ? "primary" : ""); node.type = "button"; node.onclick = action; return node; }
async function post(path, body) { const response = await fetch(path, {method:"POST", headers:{"Content-Type":"application/json", "X-Review-Token":packet.token}, body:JSON.stringify(body)}); const data = await response.json(); if (!response.ok) throw new Error(data.error || "Request failed"); return data; }
const base = item => ({packet_id:packet.packet_id, review_id:item.review_id, request_id:crypto.randomUUID(), base_revision:item.state.revision});
async function reveal(item) {
  if (busy || (dirty && !window.confirm("Discard unsaved answers or note before revealing methods?"))) return;
  setBusy(true);
  try { const result = await post("/api/reveal", base(item)); item.state = result.state; item.methods = result.methods; render(); status("Method reveal recorded. Later answer changes are marked as after reveal."); }
  catch (error) { status(error.message); }
  finally { setBusy(false); }
}
async function save(item) {
  if (busy) return;
  const ratings = {};
  for (const choice of choices) if (item.packs[choice].status === "completed") { const first_helps = checked(`${choice}-first`), irrelevant_extras = checked(`${choice}-extras`); if (!first_helps || !irrelevant_extras) { status(`Answer both questions for List ${choice}.`); return; } ratings[choice] = {first_helps, irrelevant_extras}; }
  const preference = checked("preference"); if (!preference) { status("Choose A, B, tie, neither, or unsure."); return; }
  const request = {...base(item), ratings, preference, note:$("note").value};
  setBusy(true);
  try { const result = await post("/api/feedback", request); item.state = result.state; render(); status("Saved to the local review journal."); }
  catch (error) { status(error.message); }
  finally { setBusy(false); }
}
function render() {
  dirty = false; renderNav(); const item = packet.cases[current], root = $("case"); root.replaceChildren(); status("");
  const head = el("div", undefined, "case-head"); head.append(el("h2", `Case ${current + 1} of ${packet.cases.length}`), el("span", item.state.saved_at ? "Saved" : "Not saved", item.state.saved_at ? "saved-note" : "meta")); root.append(head);
  root.append(el("p", item.sample_kind === "development" ? "Seen in an earlier review" : "Not reviewed before", "meta"));
  const imageBox = el("div", undefined, "image-wrap"), img = el("img"); img.src = item.image_url; img.alt = "Meme for this review case"; imageBox.append(img); root.append(imageBox);
  if (item.identical_initial_lists) root.append(el("p", "Lists A and B have identical initial comments in the same order.", "same-list"));
  const grid = el("div", undefined, "packs"); choices.forEach(choice => grid.append(listCard(item, choice))); root.append(grid);
  root.append(radioGroup("preference", "Which list helps you get the joke sooner?", [["A","List A"],["B","List B"],["tie","Tie"],["neither","Neither"],["unsure","Unsure"]], item.state.preference));
  root.append(el("p", "Irrelevant extras and factual concerns are separate: a useful clue can still raise a factual concern. Put any factual concern in the note below.", "meta"));
  const noteLabel = el("label", "Optional note (including factual concerns)"); noteLabel.htmlFor = "note"; const note = el("textarea"); note.id = "note"; note.maxLength = 4000; note.value = item.state.note; root.append(noteLabel, note);
  const actions = el("div", undefined, "actions"); actions.append(button("Save answers", () => save(item), true)); if (item.state.saved_at) actions.append(button("Reveal methods", () => reveal(item))); root.append(actions);
  if (item.state.methods_revealed && item.methods) root.append(el("p", `Methods: A = ${item.methods.A}; B = ${item.methods.B}.`, "meta"));
  else if (item.state.methods_revealed) root.append(el("p", "Methods were revealed in this case. Select Reveal methods to see them again.", "meta"));
  root.oninput = event => { if (event.target.matches("input,textarea")) dirty = true; };
  root.onchange = event => { if (event.target.matches("input,textarea")) dirty = true; };
}
window.addEventListener("beforeunload", event => { if (dirty) { event.preventDefault(); event.returnValue = ""; } });
fetch("/api/cases").then(r => { if (!r.ok) throw new Error("Could not load review"); return r.json(); }).then(data => { packet = data; render(); }).catch(error => status(error.message));

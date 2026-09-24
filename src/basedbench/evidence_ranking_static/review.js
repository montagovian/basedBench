"use strict";
let packet, current = 0, dirty = false;
const $ = id => document.getElementById(id);
const el = (name, text, className) => { const node = document.createElement(name); if (text !== undefined) node.textContent = text; if (className) node.className = className; return node; };
const choices = ["A", "B", "C"];
const label = (text, input) => { const node = el("label"); node.append(input, el("span", text)); return node; };
function radioGroup(name, question, options, selected) {
  const field = el("fieldset"), legend = el("legend", question), row = el("div", undefined, "choices"); field.append(legend, row);
  for (const [value, title] of options) { const input = document.createElement("input"); input.type = "radio"; input.name = name; input.value = value; input.checked = selected === value; row.append(label(title, input)); }
  return field;
}
function checked(name) { return document.querySelector(`input[name="${name}"]:checked`)?.value; }
function status(message) { $("status").textContent = message; }
function renderNav() {
  const nav = $("case-nav"); nav.replaceChildren();
  packet.cases.forEach((item, index) => { const button = el("button", String(index + 1)); button.type = "button"; button.title = item.state.saved_at ? `Case ${index + 1}, saved` : `Case ${index + 1}, unsaved`; button.classList.toggle("saved", !!item.state.saved_at); button.setAttribute("aria-current", String(index === current)); button.onclick = () => { if (index === current) return; if (dirty && !window.confirm("Discard unsaved ratings or note for this case?")) return; current = index; render(); }; nav.append(button); });
  $("progress").textContent = `${packet.cases.filter(c => c.state.saved_at).length} of ${packet.cases.length} saved`;
}
function packCard(item, choice) {
  const pack = item.packs[choice], card = el("section", undefined, "pack" + (pack.status === "unavailable" ? " unavailable" : ""));
  card.append(el("h3", `Pack ${choice}`));
  if (pack.status === "unavailable") { card.append(el("p", "Unavailable for this case. No rating needed.")); return card; }
  card.append(el("p", `${pack.word_count} of ${pack.budget_words} available words`, "meta"));
  for (const excerpt of pack.excerpts) { const block = el("div", undefined, "excerpt"); block.append(el("div", `${excerpt.comment_id}${excerpt.partial ? " · partial comment" : ""}`, "source-id"), el("div", excerpt.text || "")); card.append(block); }
  if (!pack.excerpts.length) card.append(el("p", "No excerpts in this pack."));
  const saved = item.state.ratings?.[choice];
  card.append(radioGroup(`${choice}-clue`, "Needed clue preserved?", [["yes", "Yes"], ["partly", "Partly"], ["no", "No"], ["unsure", "Unsure"]], saved?.clue));
  card.append(radioGroup(`${choice}-misleading`, "Misleading material?", [["yes", "Yes"], ["no", "No"], ["unsure", "Unsure"]], saved?.misleading));
  return card;
}
function makeButton(text, action, primary = false) { const button = el("button", text, primary ? "primary" : ""); button.type = "button"; button.onclick = action; return button; }
async function post(path, body) {
  const response = await fetch(path, {method:"POST", headers:{"Content-Type":"application/json", "X-Review-Token":packet.token}, body:JSON.stringify(body)});
  const data = await response.json(); if (!response.ok) throw new Error(data.error || "Request failed"); return data;
}
function base(item) { return {packet_id:packet.packet_id, review_id:item.review_id, request_id:crypto.randomUUID(), base_revision:item.state.revision}; }
async function openContext(item, source) {
  try { const result = await post("/api/context", {...base(item), source}); item.state = result.state; if (packet.cases[current] !== item) return; const pane = $("context"); pane.replaceChildren();
    if (source === "comments") { pane.append(el("h3", "All saved comments (partial thread)")); for (const comment of result.context.comments) pane.append(el("p", `${comment.id ?? comment.comment_id ?? "Comment"}: ${comment.text ?? ""}`)); }
    else { pane.append(el("h3", "Matched prior explanation"), el("p", result.context.reference_explanation || "No matched prior-ready explanation is available.")); }
    pane.hidden = false; status("Source opened; this exposure was recorded.");
  } catch (error) { status(error.message); }
}
async function reveal(item) { try { const data = await post("/api/reveal", base(item)); item.state = data.state; if (packet.cases[current] !== item) return; $("reveal").textContent = choices.map(c => `${c}: ${data.methods[c]}`).join(" · "); const details = $("inspection"); details.replaceChildren(el("summary", "Model inspection · all saved comments"), el("p", "These model suggestions cover all saved comments. Some IDs fall outside the displayed pack and its word limit."));
    for (const choice of choices) { const inspection = data.inspection[choice] || {}; if (!Object.keys(inspection).length) continue;
      const group = el("section"); group.append(el("h3", `Pack ${choice} · ${data.methods[choice]}`));
      const duplicates = (inspection.groups || []).filter(g => (g.duplicate_ids || []).length);
      group.append(el("p", duplicates.length ? "Suggested duplicate groups: " + duplicates.map(g => `${g.representative_id} → ${g.member_ids.join(", ")}`).join("; ") : "No suggested duplicate groups."));
      const sections = inspection.sections || {};
      group.append(el("p", `Source pointers (unverified): ${(sections.source_pointers || []).join(", ") || "none"}`));
      group.append(el("p", `Alternative readings: ${(sections.alternative_readings || []).join(", ") || "none"}`));
      if (inspection.ranking) group.append(el("p", `Full-pool ranking: ${inspection.ranking.map(row => row.comment_id).join(" → ")}`));
      if (inspection.pairs) group.append(el("p", `${inspection.pairs.length} pair comparisons saved for local inspection.`));
      details.append(group);
    }
    details.hidden = !details.querySelector("section"); status("Method reveal recorded. Later rating revisions will be marked post-reveal.");
  } catch(error) { status(error.message); } }
async function save(item) {
  const ratings = {};
  for (const choice of choices) if (item.packs[choice].status === "completed") {
    const clue = checked(`${choice}-clue`), misleading = checked(`${choice}-misleading`);
    if (!clue || !misleading) { status(`Rate both questions for Pack ${choice}.`); return; }
    ratings[choice] = {clue, misleading};
  }
  const most_useful = checked("most-useful"); if (!most_useful) { status("Choose the most useful pack, tie, or unsure."); return; }
  try { const result = await post("/api/feedback", {...base(item), ratings, most_useful, note:$("note").value}); item.state = result.state; if (packet.cases[current] !== item) { renderNav(); return; } render(); status("Saved to the local feedback journal."); }
  catch(error) { status(error.message); }
}
function render() {
  dirty = false; renderNav(); const item = packet.cases[current], root = $("case"); root.replaceChildren(); status("");
  const heading = el("div", undefined, "case-head"); heading.append(el("h2", `Case ${current + 1} of ${packet.cases.length}`), el("span", item.state.saved_at ? "Saved" : "Not saved", item.state.saved_at ? "saved-note" : "meta")); root.append(heading);
  const imageBox = el("div", undefined, "image-wrap"), img = document.createElement("img"); img.src = item.image_url; img.alt = "Meme for this review case"; imageBox.append(img); root.append(imageBox);
  const packGrid = el("div", undefined, "packs"); choices.forEach(c => packGrid.append(packCard(item,c))); root.append(packGrid);
  root.append(radioGroup("most-useful", "Which pack is most useful for getting the joke?", [...choices.filter(c => item.packs[c].status === "completed").map(c => [c, `Pack ${c}`]), ["tie", "Tie"], ["unsure", "Unsure"]], item.state.most_useful));
  const noteLabel = el("label", "Optional note"); noteLabel.htmlFor = "note"; const note = el("textarea"); note.id = "note"; note.maxLength = 4000; note.value = item.state.note; root.append(noteLabel,note);
  const actions = el("div", undefined, "actions"); actions.append(makeButton("Open all saved comments", () => openContext(item,"comments")), makeButton("Open matched explanation", () => openContext(item,"reference")), makeButton("Save ratings", () => save(item), true)); root.append(actions);
  const context = el("section", undefined, "context"); context.id = "context"; context.hidden = true; root.append(context);
  const revealBox = el("div", undefined, "actions"); revealBox.append(makeButton("Reveal methods", () => reveal(item))); const revealText = el("p", "", "meta"); revealText.id = "reveal"; revealBox.append(revealText); revealBox.hidden = !item.state.saved_at; root.append(revealBox);
  const inspection = el("details", undefined, "context"); inspection.id = "inspection"; inspection.hidden = true; inspection.append(el("summary", "Model inspection")); root.append(inspection);
  root.oninput = event => { if (event.target.matches("input,textarea")) dirty = true; };
  root.onchange = event => { if (event.target.matches("input,textarea")) dirty = true; };
}
fetch("/api/cases").then(r => {if (!r.ok) throw new Error("Could not load review"); return r.json();}).then(data => {packet = data; render();}).catch(error => status(error.message));

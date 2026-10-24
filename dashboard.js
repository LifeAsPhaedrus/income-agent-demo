let token = "",
  data = null,
  view = "new",
  busy = false;
const drafts = new Map();
const labels = {
  new: "New leads",
  saved: "Pursue",
  reviewed: "Reviewed",
  dismissed: "Passed",
};
function el(tag, text, cls) {
  const n = document.createElement(tag);
  if (text !== undefined) n.textContent = text;
  if (cls) n.className = cls;
  return n;
}
function message(text) {
  document.getElementById("message").textContent = text;
}
async function api(request) {
  const response = await fetch("/api", {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Review-Token": token },
    body: JSON.stringify(request),
  });
  const result = await response.json();
  if (!response.ok || result.error)
    throw Error(result.error || "Request failed");
  return result;
}
async function load() {
  if (busy) return;
  busy = true;
  message("Loading fictional demo results…");
  document.getElementById("refresh").disabled = true;
  try {
    data = await api({ action: "snapshot" });
    draw();
    message("Results updated.");
  } catch (e) {
    message(e.message);
  } finally {
    busy = false;
    document.getElementById("refresh").disabled = false;
  }
}
async function decide(id, status, note) {
  if (busy) return;
  busy = true;
  document.querySelectorAll("button").forEach((b) => (b.disabled = true));
  message("Saving your demo decision locally…");
  try {
    data = await api({ action: "review", id, status, note });
    drafts.delete(id);
    draw();
    message(data.database_status || "Saved in the local demo.");
  } catch (e) {
    message(e.message);
  } finally {
    busy = false;
    document.querySelectorAll("button").forEach((b) => (b.disabled = false));
  }
}
function draw() {
  document.getElementById("db-status").textContent =
    (data.database_status || "") +
    " · " +
    Object.entries(data.sources || {})
      .map(([k, v]) => k + ": " + v)
      .join(" · ");
  const all = new Map(data.ranked.map((p) => [p.id, p]));
  for (const h of data.history) {
    if (all.has(h.id)) Object.assign(all.get(h.id), h);
    else if (h.url)
      all.set(h.id, {
        ...h,
        url:
          h.url || "https://www.freelancer.com/projects/" + h.id.split(":")[1],
      });
  }
  const rows = [...all.values()];
  const tabs = document.getElementById("tabs");
  tabs.replaceChildren();
  for (const [key, label] of Object.entries(labels)) {
    const button = el(
      "button",
      label + " (" + rows.filter((p) => p.status === key).length + ")",
      view === key ? "active" : "",
    );
    button.onclick = () => {
      view = key;
      draw();
    };
    tabs.append(button);
  }
  const age = (Date.now() - Date.parse(data.source_fetched)) / 3600000;
  document.getElementById("summary").textContent =
    "SYNTHETIC DEMO · Sample data generated " +
    new Date(data.source_fetched).toLocaleString() +
    " · Fictional profile target $60/hour. " +
    (age > 24
      ? "This batch is over 24 hours old. Recheck availability."
      : "Saved research results; listing availability still needs checking.");
  const cards = document.getElementById("cards");
  cards.replaceChildren();
  const filtered = rows.filter((p) => p.status === view);
  if (!filtered.length) {
    cards.append(
      el(
        "p",
        "Nothing here yet. Use Pursue, Pass, or Reviewed on a gig.",
        "empty",
      ),
    );
    return;
  }
  for (const p of filtered) {
    const card = el("article", undefined, "card");
    card.append(
      el("span", (p.source || "Freelancer") + " · " + labels[p.status], "tag"),
      el("h2", p.title),
    );
    const link = el(
      "a",
      "Open listing on " + (p.source || "Freelancer") + " ↗",
    );
    link.href =
      p.url || "https://www.freelancer.com/projects/" + p.id.split(":")[1];
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    card.append(link);
    if (p.status === "saved" && p.id.startsWith("freelancer:")) {
      const draftLink = el("a", "Proposal & bid status");
      draftLink.href = "/proposal.html?id=" + encodeURIComponent(p.id);
      draftLink.target = "_blank";
      draftLink.style.marginLeft = "24px";
      card.append(draftLink);
    }
    if (p.earnings) {
      const e = p.earnings;
      card.append(
        el(
          "p",
          e.net_amount === null
            ? "Estimated take-home: unknown. " + e.fee_policy
            : e.gross_basis +
                ": " +
                e.currency +
                " " +
                e.gross_amount +
                " / " +
                e.unit +
                " − fee " +
                e.fee_amount +
                " = " +
                e.net_amount +
                " before taxes and other costs",
        ),
      );
      card.append(el("p", e.note, "muted"));
    }
    if (p.salary_text)
      card.append(
        el(
          "p",
          "Source salary: " +
            p.salary_text +
            " · Location: " +
            (p.location || "Check listing"),
        ),
      );
    if (p.source_notice) card.append(el("p", p.source_notice, "muted"));
    if (p.budget) {
      card.append(
        el(
          "p",
          `${p.budget.currency} ${p.budget.minimum ?? "?"}–${p.budget.maximum ?? "?"} · ${p.budget.type}`,
          "budget",
        ),
        el("p", p.pay),
      );
      const matches = el("ul");
      for (const m of p.matches || [])
        matches.append(el("li", m.skill + ": " + m.quote));
      const why = el("details");
      why.append(el("summary", "Why this matches your experience"), matches);
      card.append(why);
      const checks = el("ul");
      for (const g of p.gaps || []) checks.append(el("li", g));
      card.append(el("h3", "Check before pursuing"), checks);
      const model = el("details");
      model.append(
        el("summary", "Qwen’s findings"),
        el("p", p.model?.status || "Not available"),
      );
      const qs = el("ul");
      for (const q of p.model?.requirements || []) qs.append(el("li", q));
      model.append(qs);
      card.append(model);
      const desc = el("details");
      desc.append(
        el("summary", "Available project description"),
        el("p", p.description),
      );
      card.append(desc);
    } else
      card.append(
        el(
          "p",
          "Saved from an earlier batch. Open the source to check the current budget and scope.",
          "muted",
        ),
      );
    const label = el("label", "Your notes");
    const note = el("textarea");
    note.value = drafts.has(p.id) ? drafts.get(p.id) : p.note || "";
    note.oninput = () => drafts.set(p.id, note.value);
    note.maxLength = 2000;
    note.rows = 2;
    note.placeholder = "Questions, effort estimate, next step…";
    label.append(note);
    card.append(label);
    const actions = el("div", undefined, "actions");
    for (const [status, label] of [
      ["saved", "Pursue"],
      ["dismissed", "Pass"],
      ["reviewed", "Reviewed"],
      ["new", "Restore to new"],
    ]) {
      if (status === p.status) continue;
      const b = el("button", label, status === "saved" ? "primary" : "");
      b.onclick = () => decide(p.id, status, note.value);
      actions.append(b);
    }
    const save = el("button", "Save notes");
    save.onclick = () => decide(p.id, p.status, note.value);
    actions.append(save);
    card.append(actions);
    cards.append(card);
  }
}
document.getElementById("refresh").onclick = load;
fetch("/session")
  .then((r) => r.json())
  .then((r) => {
    token = r.token;
    load();
  })
  .catch(() => message("Could not start the local app. Reopen its launcher."));

let wasRunning = false;
async function progress() {
  try {
    const job = await api({ action: "progress" });
    document.getElementById("search").disabled = job.running;
    document.getElementById("run-status").textContent = job.status;
    const box = document.getElementById("progress");
    if (box.textContent !== job.log) {
      box.textContent = job.log;
      box.scrollTop = box.scrollHeight;
    }
    if (wasRunning && !job.running) await load();
    wasRunning = job.running;
  } catch (e) {
  } finally {
    setTimeout(progress, 1500);
  }
}
document.getElementById("search").onclick = async () => {
  try {
    await api({
      action: "start",
      query: document.getElementById("query").value.trim(),
    });
    wasRunning = true;
    document.getElementById("progress-panel").open = true;
    document.getElementById("search").disabled = true;
    message("Reloading fictional examples. See demo activity below.");
  } catch (e) {
    message(e.message);
  }
};
function csvCell(value) {
  let s = String(value ?? "");
  if (/^[\s]*[=+@-]/.test(s) || /^[\t\r\n]/.test(s)) s = "'" + s;
  return '"' + s.replaceAll('"', '""') + '"';
}
document.getElementById("export").onclick = async () => {
  try {
    message("Reading local sample selections…");
    const r = await api({ action: "export" });
    const rows = [
      [
        "ID",
        "Title",
        "URL",
        "Currency",
        "Minimum budget",
        "Maximum budget",
        "Type",
        "Hourly assessment",
        "Notes",
        "Description",
      ],
      ...r.rows.map((p) => [
        p.id,
        p.title,
        p.url || "https://www.freelancer.com/projects/" + p.id.split(":")[1],
        p.budget?.currency,
        p.budget?.minimum,
        p.budget?.maximum,
        p.budget?.type,
        p.pay,
        p.note,
        p.description,
      ]),
    ];
    const blob = new Blob(
      ["\ufeff" + rows.map((r) => r.map(csvCell).join(",")).join("\r\n")],
      { type: "text/csv;charset=utf-8" },
    );
    const url = URL.createObjectURL(blob);
    const a = el("a");
    a.href = url;
    a.download = "Pursue-gigs.csv";
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    message("Sample export downloaded: " + r.rows.length + " selected gigs.");
  } catch (e) {
    message(e.message);
  }
};
setTimeout(progress, 1500);

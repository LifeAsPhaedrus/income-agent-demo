let token = "",
  state = null,
  dirty = false,
  wasRunning = false;
const id = new URLSearchParams(location.search).get("id");
const $ = (id) => document.getElementById(id),
  say = (text) => ($("status").textContent = text);
async function api(r) {
  const x = await fetch("/api", {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Review-Token": token },
    body: JSON.stringify(r),
  });
  const d = await x.json();
  if (!x.ok || d.error) throw Error(d.error || "Request failed");
  return d;
}
function show(s) {
  state = s;
  $("days").value = s.draft.terms?.days ?? "";
  $("revisions").value = s.draft.terms?.revision_rounds ?? 1;
  $("delivery").textContent = "Delivery: " + s.delivery;
  $("title").textContent = s.listing.title + " — proposal";
  $("listing").href = "https://www.freelancer.com/projects/" + id.split(":")[1];
  $("body").value = s.draft.body;
  $("amount").value = s.draft.amount ?? "";
  $("currency").textContent = s.draft.currency || "";
  $("version").textContent =
    "Version " +
    s.draft.version +
    " · " +
    s.draft.origin +
    " · " +
    (s.submission?.state || "Draft");
  $("versions").replaceChildren();
  for (const v of s.versions) {
    const o = document.createElement("option");
    o.value = v.version;
    o.textContent = "Version " + v.version + " — " + v.origin;
    $("versions").append(o);
  }
  dirty = false;
  if (s.submission) {
    $("bid-status").textContent =
      (s.submission.state || "Draft") +
      ": " +
      (s.submission.message || "") +
      (s.submission.bid_id ? " · Bid " + s.submission.bid_id : "");
  }
}
async function load() {
  show(await api({ action: "proposal_get", id }));
}
$("days").oninput =
  $("revisions").oninput =
  $("body").oninput =
  $("amount").oninput =
    () => (dirty = true);
$("save").onclick = async () => {
  try {
    show(
      await api({
        action: "proposal_save",
        id,
        body: $("body").value,
        amount: Number($("amount").value),
        version: state.draft.version,
        ...($("days").value
          ? {
              terms: {
                days: Number($("days").value),
                revision_rounds: Number($("revisions").value),
              },
            }
          : {}),
      }),
    );
    say("Revised draft saved on Ubuntu. Nothing submitted.");
  } catch (e) {
    say(e.message);
  }
};
$("draft").onclick = async () => {
  if (dirty)
    return say("Save your edits before asking Qwen for another version.");
  try {
    await api({ action: "proposal_start", id, version: state.draft.version });
    wasRunning = true;
    $("draft").disabled = true;
    say("Qwen is drafting locally. Your earlier versions are retained.");
  } catch (e) {
    say(e.message);
  }
};
$("copy").onclick = async () => {
  try {
    await navigator.clipboard.writeText($("body").value);
    say("Proposal copied.");
  } catch (e) {
    say("Select the proposal text and copy it manually.");
  }
};
async function packet() {
  if (dirty) throw Error("Save your edits before exporting.");
  return (await api({ action: "proposal_export", id })).text;
}
$("preview").onclick = async () => {
  try {
    $("export-preview").textContent = await packet();
  } catch (e) {
    say(e.message);
  }
};
$("export").onclick = async () => {
  try {
    const text = await packet();
    const u = URL.createObjectURL(
      new Blob([text], { type: "text/plain;charset=utf-8" }),
    );
    const a = document.createElement("a");
    a.href = u;
    a.download = "ChatGPT-proposal-" + id.split(":")[1] + ".txt";
    a.click();
    setTimeout(() => URL.revokeObjectURL(u), 1000);
    say(
      "Editing packet downloaded. Paste ChatGPT’s revised proposal above and save.",
    );
  } catch (e) {
    say(e.message);
  }
};
$("restore").onclick = () => {
  if (dirty) return say("Save your current edits first.");
  const v = state.versions.find(
    (v) => String(v.version) === $("versions").value,
  );
  if (v) {
    $("body").value = v.body;
    $("amount").value = v.amount;
    dirty = true;
    say("Earlier version loaded for review. Save to create a new version.");
  }
};
async function poll() {
  try {
    const j = await api({ action: "progress" });
    $("progress").textContent = j.log;
    $("draft").disabled = j.running;
    if (wasRunning && !j.running) {
      if (!dirty) await load();
      say(
        j.status +
          (dirty
            ? " — save or copy your edits before reloading the new version."
            : ". Review the saved draft before using it."),
      );
    }
    wasRunning = j.running;
  } catch (e) {
  } finally {
    setTimeout(poll, 2000);
  }
}
fetch("/session")
  .then((r) => r.json())
  .then(async (r) => {
    token = r.token;
    await load();
    poll();
  })
  .catch((e) => say(e.message));

let prepared = null;
$("prepare-bid").onclick = async () => {
  try {
    if (dirty) throw Error("Save your edits first.");
    prepared = await api({
      action: "bid_prepare",
      id,
      version: state.draft.version,
      milestone_percentage: 100,
    });
    $("bid-preview").textContent =
      "Account: " +
      prepared.account +
      "\nBid: " +
      prepared.payload.amount +
      " " +
      prepared.currency +
      "\nDelivery: " +
      prepared.delivery +
      "\nMilestone: 100% for completed deliverable\n\n" +
      prepared.payload.description;
    $("submit-bid").disabled =
      !!prepared.status.state && prepared.status.state !== "rejected";
    $("submit-bid").textContent =
      prepared.status.state === "rejected"
        ? "Retry rejected bid after resolving the issue"
        : "Submit this bid to Freelancer";
    $("bid-status").textContent =
      prepared.status.message || "Review the exact bid above, then submit.";
  } catch (e) {
    say(e.message);
  }
};
$("submit-bid").onclick = async () => {
  try {
    if (dirty || !prepared) throw Error("Save and review the bid first.");
    $("submit-bid").disabled = true;
    $("bid-status").textContent = "Submitting once. Please wait…";
    const r = await api({
      action: "bid_submit",
      id,
      version: prepared.version,
      milestone_percentage: 100,
      fingerprint: prepared.fingerprint,
      confirm: true,
      retry_rejected: prepared.status.state === "rejected",
    });
    $("bid-status").textContent =
      r.submission.state +
      ": " +
      (r.submission.message || "") +
      (r.submission.bid_id ? " · Bid " + r.submission.bid_id : "");
    await load();
  } catch (e) {
    $("bid-status").textContent =
      e.message + " Check status before trying again.";
  }
};

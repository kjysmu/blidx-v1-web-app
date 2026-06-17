const app = document.querySelector("#app");

const ui = {
  tab: "chat",
  state: null,
  integrations: null,
  selectedCategory: "insights",
  notice: "",
  modal: null,
  toast: "",
  loading: false,
};

const api = async (path, options = {}) => {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  if (!response.ok) throw new Error((await response.json()).detail || "Request failed");
  return response.json();
};

const escapeHtml = (value = "") =>
  value.replace(/[&<>"']/g, (char) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;",
  }[char]));

const navItems = [
  ["chat", "✦", "Chat"],
  ["bank", "▦", "Bank"],
  ["library", "▤", "Library"],
  ["calendar", "□", "Calendar"],
  ["settings", "⚙", "Settings"],
];

function layout(content) {
  const nav = navItems.map(([id, icon, label]) => `
    <button data-tab="${id}" class="${ui.tab === id ? "active" : ""}">
      <span class="nav-icon">${icon}</span>${label}
    </button>`).join("");
  const mobileNav = navItems.map(([id, icon, label]) => `
    <button data-tab="${id}" class="${ui.tab === id ? "active" : ""}">
      <span>${icon}</span>${label}
    </button>`).join("");

  app.innerHTML = `
    <div class="shell">
      <aside class="sidebar">
        <div class="brand"><span class="brand-mark">B</span> Blidx</div>
        <nav class="nav">${nav}</nav>
        <div class="side-note"><strong>Staging MVP</strong>${integrationSummary()}</div>
      </aside>
      <main class="main">
        <header class="topbar">
          <div class="mira-id"><div class="avatar">M</div><div><div class="mira-name">Mira</div><div class="online">● Online · content lead</div></div></div>
          <div class="top-actions"><button class="icon-button" data-action="new-draft">＋ Draft</button></div>
        </header>
        ${content}
      </main>
    </div>
    <nav class="mobile-nav">${mobileNav}</nav>
    ${ui.modal || ""}
    ${ui.toast ? `<div class="toast">${escapeHtml(ui.toast)}</div>` : ""}
  `;
  bindGlobal();
}

function bindGlobal() {
  document.querySelectorAll("[data-tab]").forEach((button) => {
    button.onclick = () => { ui.tab = button.dataset.tab; ui.modal = null; render(); };
  });
  document.querySelectorAll('[data-action="new-draft"]').forEach((button) => {
    button.onclick = () => { ui.tab = "chat"; render(); setTimeout(() => document.querySelector("#draft-topic")?.focus(), 0); };
  });
}

function render() {
  if (!ui.state) return layout('<div class="page"><div class="empty">Loading Blidx…</div></div>');
  const views = { chat: renderChat, bank: renderBank, library: renderLibrary, calendar: renderCalendar, settings: renderSettings };
  layout(views[ui.tab]());
  bindView();
}

function renderChat() {
  const profile = ui.state.profile;
  const activeDraft = ui.state.posts.find((post) => post.status === "pending");
  const published = ui.state.posts.filter((post) => post.status === "published").length;
  const goal = profile.posting_frequency === "5+_per_week" ? 5 : profile.posting_frequency === "3-4x_per_week" ? 3 : 1;
  return `
    <section class="page">
      <div class="eyebrow">Your content workdesk</div>
      <h1>Good ${new Date().getHours() < 12 ? "morning" : "afternoon"}, ${escapeHtml(profile.first_name)}.</h1>
      <p class="lead">I’m keeping your LinkedIn pipeline moving. Add something from your week or give me a topic and I’ll turn it into a review-ready post.</p>
      <div class="grid">
        <div class="card"><div class="card-head"><h3>This week</h3><span class="badge ${published >= goal ? "published" : "pending"}">${published}/${goal} posts</span></div><div class="metric">${Math.min(Math.round((published / goal) * 100), 100)}%</div><div class="progress"><span style="width:${Math.min((published / goal) * 100, 100)}%"></span></div><div class="muted small">Based on your ${escapeHtml(profile.posting_frequency.replaceAll("_", " "))} goal.</div></div>
        <div class="card"><div class="card-head"><h3>Content Bank</h3><span class="badge published">${ui.state.content_bank.length} entries</span></div><p class="muted">Your latest real-world context makes every draft more personal.</p><button class="button secondary" data-tab="bank">Add today’s insight</button></div>
      </div>
      <div class="chat-stream" style="margin-top:18px">
        <div class="bubble mira"><strong>Mira</strong><br>${activeDraft ? "You have a draft waiting for review. I kept the angle focused on your founder audience." : "Your pipeline is clear. What should we turn into your next post?"}</div>
        ${activeDraft ? draftCard(activeDraft) : ""}
      </div>
      <div class="composer">
        <form class="composer-box" id="draft-form">
          <input class="input" id="draft-topic" placeholder="Draft a post about…" required minlength="3" />
          <button class="button" ${ui.loading ? "disabled" : ""}>${ui.loading ? "Working…" : "Draft"}</button>
        </form>
      </div>
    </section>`;
}

function draftCard(post) {
  const provider = post.generation_provider || "template";
  return `<article class="draft-card" data-post="${post.id}">
    <div class="draft-meta"><span>Draft v${post.version} · ${post.source.replace("_", " ")} · ${escapeHtml(provider)}</span><span>${post.char_count} / 3,000</span></div>
    <div class="draft-content">${escapeHtml(post.content)}</div>
    <div class="draft-actions">
      <button class="button" data-draft-action="approve" data-id="${post.id}">Approve</button>
      <button class="button secondary" data-draft-action="linkedin" data-id="${post.id}">Copy & open LinkedIn</button>
      <button class="button secondary" data-draft-action="edit" data-id="${post.id}">Edit</button>
      <button class="button ghost" data-draft-action="save" data-id="${post.id}">Save draft</button>
      <button class="button danger" data-draft-action="delete" data-id="${post.id}">Delete</button>
    </div>
  </article>`;
}

function renderBank() {
  const templates = [
    ["people", "🤝", "Met someone"], ["events", "🎤", "Attended event"],
    ["insights", "💡", "Key insight"], ["milestones", "🏆", "Hit milestone"],
    ["reading", "📖", "Read something"], ["solutions", "🔥", "Solved a problem"],
  ];
  return `<section class="page">
    <div class="eyebrow">Personal memory</div><h1>Content Bank</h1>
    <p class="lead">Capture one useful moment in under a minute. Mira will use the freshest entries first.</p>
    ${ui.notice ? `<div class="notice">${escapeHtml(ui.notice)}</div>` : ""}
    <div class="card">
      <h3>What happened today?</h3>
      <div class="template-grid">${templates.map(([id, icon, label]) => `<button class="template ${ui.selectedCategory === id ? "active" : ""}" data-category="${id}"><span>${icon}</span>${label}</button>`).join("")}</div>
      <form id="bank-form"><textarea id="bank-text" placeholder="Example: We launched our first founder test today. The biggest lesson was that workflow ownership matters more than another writing prompt." required minlength="3"></textarea><button class="button" style="margin-top:10px">Save to Content Bank</button></form>
    </div>
    <div class="list" style="margin-top:18px">
      ${ui.state.content_bank.length ? ui.state.content_bank.map((entry) => `<div class="list-item"><div class="list-top"><strong>${escapeHtml(entry.category)}</strong><span class="badge published">${entry.freshness}</span></div><p>${escapeHtml(entry.raw_text)}</p><div class="small muted" style="margin-top:8px">Content potential: ${entry.content_potential}</div></div>`).join("") : '<div class="empty">Your Content Bank is empty. Add the first moment above.</div>'}
    </div>
  </section>`;
}

function renderLibrary() {
  const posts = ui.state.posts.filter((post) => post.status !== "deleted");
  return `<section class="page"><div class="eyebrow">Content pipeline</div><h1>Library</h1><p class="lead">Every draft, scheduled post, and published post stays visible here.</p>
    <div class="list">${posts.length ? posts.map((post) => `<div class="list-item"><div class="list-top"><div><strong>${escapeHtml(post.title)}</strong><p>${escapeHtml(post.content.slice(0, 180))}${post.content.length > 180 ? "…" : ""}</p></div><span class="badge ${post.status}">${post.status}</span></div><div class="small muted" style="margin-top:10px">${post.char_count} characters · v${post.version}</div></div>`).join("") : '<div class="empty">No posts yet. Draft one with Mira.</div>'}</div>
  </section>`;
}

function renderCalendar() {
  const scheduled = ui.state.posts.filter((post) => ["scheduled", "published"].includes(post.status));
  const now = new Date();
  const year = now.getFullYear(), month = now.getMonth();
  const firstDay = new Date(year, month, 1).getDay();
  const days = new Date(year, month + 1, 0).getDate();
  const cells = Array(firstDay).fill('<div class="day"></div>');
  for (let day = 1; day <= days; day++) {
    const matches = scheduled.filter((post) => {
      const date = new Date(post.scheduled_at || post.published_at);
      return date.getFullYear() === year && date.getMonth() === month && date.getDate() === day;
    });
    cells.push(`<div class="day ${matches.length ? "has-post" : ""}"><strong>${day}</strong>${matches.map((post) => `<div class="small" style="margin-top:8px"><span class="dot ${post.status}"></span>${post.status}</div>`).join("")}</div>`);
  }
  return `<section class="page"><div class="eyebrow">Schedule</div><h1>${now.toLocaleString("en", { month: "long" })} ${year}</h1><p class="lead">Green marks published content. Purple marks posts Mira has scheduled.</p>
    <div class="card"><div class="calendar">${["Sun","Mon","Tue","Wed","Thu","Fri","Sat"].map((day) => `<div class="day-label">${day}</div>`).join("")}${cells.join("")}</div></div>
    <div class="list" style="margin-top:18px">${scheduled.length ? scheduled.map((post) => `<div class="list-item"><div class="list-top"><strong>${escapeHtml(post.title)}</strong><span class="badge ${post.status}">${post.status}</span></div><p>${new Date(post.scheduled_at || post.published_at).toLocaleString()}</p></div>`).join("") : '<div class="empty">Nothing scheduled yet. Approve a draft to place it here.</div>'}</div>
  </section>`;
}

function renderSettings() {
  const p = ui.state.profile;
  const anthropic = ui.integrations?.anthropic;
  const linkedin = ui.integrations?.linkedin;
  const payloadcms = ui.integrations?.payloadcms;
  return `<section class="page"><div class="eyebrow">Personalization</div><h1>Settings</h1><p class="lead">These details are loaded fresh whenever Mira creates a draft.</p>
    ${ui.notice ? `<div class="notice">${escapeHtml(ui.notice)}</div>` : ""}
    <form class="card form-grid" id="profile-form">
      ${field("First name", "first_name", p.first_name)}
      ${field("Role", "role", p.role)}
      ${field("Company", "company_name", p.company_name)}
      ${field("Industry", "industry", p.industry)}
      ${field("Company description", "company_description", p.company_description, true)}
      ${field("Audience (comma separated)", "audience", p.audience.join(", "), true)}
      ${field("Expertise (comma separated)", "expertise", p.expertise.join(", "), true)}
      <div class="field"><label>Posting frequency</label><select name="posting_frequency"><option value="1-2x_per_week" ${p.posting_frequency === "1-2x_per_week" ? "selected" : ""}>1–2× per week</option><option value="3-4x_per_week" ${p.posting_frequency === "3-4x_per_week" ? "selected" : ""}>3–4× per week</option><option value="5+_per_week" ${p.posting_frequency === "5+_per_week" ? "selected" : ""}>5+ per week</option></select></div>
      ${field("Tone", "tone", p.tone)}
      <div class="field full"><button class="button">Save profile</button> <button type="button" class="button ghost" id="reset-demo">Reset demo data</button></div>
    </form>
    <div class="card" style="margin-top:16px"><div class="card-head"><h3>AI generation</h3><span class="badge ${anthropic?.configured ? "published" : "draft"}">${anthropic?.configured ? "Claude ready" : "Template fallback"}</span></div><p class="muted">${anthropic?.configured ? `Mira drafts use ${escapeHtml(anthropic.model)} with profile, writing samples, and Content Bank context.` : "Add ANTHROPIC_API_KEY in Render to enable real Claude drafts."}</p></div>
    <div class="card" style="margin-top:16px"><div class="card-head"><h3>LinkedIn</h3><span class="badge ${linkedin?.configured ? "published" : "draft"}">${linkedin?.configured ? "OAuth configured" : "Fallback ready"}</span></div><p class="muted">${linkedin?.configured ? "OAuth URL generation is available. Token storage comes after production auth." : "Use Copy & open LinkedIn on any draft. For full OAuth on staging, add the Render URL to LinkedIn redirect URLs or route app.blidx.com to this service."}</p></div>
    <div class="card" style="margin-top:16px"><div class="card-head"><h3>PayloadCMS review</h3><span class="badge draft">${escapeHtml(payloadcms?.recommendation || "defer")}</span></div><p class="muted">${escapeHtml(payloadcms?.reason || "PayloadCMS review pending.")}</p></div>
  </section>`;
}

function field(label, name, value, full = false) {
  return `<div class="field ${full ? "full" : ""}"><label>${label}</label><input class="input" name="${name}" value="${escapeHtml(value || "")}" /></div>`;
}

function bindView() {
  bindGlobal();
  document.querySelector("#draft-form")?.addEventListener("submit", createDraft);
  document.querySelector("#bank-form")?.addEventListener("submit", addMemory);
  document.querySelector("#profile-form")?.addEventListener("submit", saveProfile);
  document.querySelector("#reset-demo")?.addEventListener("click", resetDemo);
  document.querySelectorAll("[data-category]").forEach((button) => {
    button.onclick = () => { ui.selectedCategory = button.dataset.category; render(); };
  });
  document.querySelectorAll("[data-draft-action]").forEach((button) => {
    button.onclick = () => handleDraftAction(button.dataset.draftAction, button.dataset.id);
  });
}

async function refresh() {
  const [state, integrations] = await Promise.all([
    api("/api/state"),
    api("/api/integrations/status").catch(() => null),
  ]);
  ui.state = state;
  ui.integrations = integrations;
  render();
}

async function createDraft(event) {
  event.preventDefault();
  const topic = document.querySelector("#draft-topic").value;
  ui.loading = true; render();
  try {
    await api("/api/drafts", { method: "POST", body: JSON.stringify({ topic }) });
    ui.loading = false;
    await refresh();
  } catch (error) {
    ui.loading = false;
    showToast(error.message);
  }
}

async function addMemory(event) {
  event.preventDefault();
  const raw_text = document.querySelector("#bank-text").value;
  const entry = await api("/api/content-bank", { method: "POST", body: JSON.stringify({ raw_text, category: ui.selectedCategory }) });
  ui.notice = `Saved to Content Bank · ${entry.category} · Fresh`;
  await refresh();
  ui.notice = `Saved to Content Bank · ${entry.category} · Fresh`; render();
}

async function saveProfile(event) {
  event.preventDefault();
  const form = new FormData(event.currentTarget);
  const payload = Object.fromEntries(form.entries());
  payload.audience = payload.audience.split(",").map((v) => v.trim()).filter(Boolean);
  payload.expertise = payload.expertise.split(",").map((v) => v.trim()).filter(Boolean);
  await api("/api/profile", { method: "PUT", body: JSON.stringify(payload) });
  ui.notice = "Profile updated. Mira will use it on the next draft.";
  await refresh(); ui.notice = "Profile updated. Mira will use it on the next draft."; render();
}

function handleDraftAction(action, id) {
  if (action === "approve") {
    ui.modal = `<div class="modal-backdrop"><div class="modal"><h3>When should Mira publish?</h3><p class="muted">Use “Copy & open LinkedIn” for the real tester workflow today. Scheduling still keeps Library and Calendar state organized.</p><div class="modal-actions"><button class="button ghost" data-schedule="now">Mark posted</button><button class="button" data-schedule="best_time">Best time</button></div></div></div>`;
    render();
    document.querySelectorAll("[data-schedule]").forEach((button) => button.onclick = () => approveDraft(id, button.dataset.schedule));
  } else if (action === "linkedin") {
    copyAndOpenLinkedIn(id);
  } else if (action === "edit") {
    ui.modal = `<div class="modal-backdrop"><div class="modal"><h3>Tell Mira what to change</h3><textarea id="edit-instructions" placeholder="Try: Make it shorter, bolder, or more personal."></textarea><div class="modal-actions"><button class="button ghost" id="cancel-modal">Cancel</button><button class="button" id="submit-edit">Revise draft</button></div></div></div>`;
    render();
    document.querySelector("#cancel-modal").onclick = () => { ui.modal = null; render(); };
    document.querySelector("#submit-edit").onclick = () => editDraft(id);
  } else {
    api(`/api/drafts/${id}/${action}`, { method: "POST" }).then(() => refresh()).then(() => showToast(action === "save" ? "Saved to Library" : "Draft deleted"));
  }
}

async function editDraft(id) {
  const instructions = document.querySelector("#edit-instructions").value;
  if (instructions.length < 2) return;
  await api(`/api/drafts/${id}/edit`, { method: "POST", body: JSON.stringify({ instructions }) });
  ui.modal = null; await refresh(); showToast("Mira revised the draft");
}

async function approveDraft(id, schedule_type) {
  await api(`/api/drafts/${id}/approve`, { method: "POST", body: JSON.stringify({ schedule_type }) });
  ui.modal = null; await refresh();
  showToast(schedule_type === "now" ? "Published locally" : "Scheduled for Mira’s recommended time");
}

async function copyAndOpenLinkedIn(id) {
  const post = ui.state.posts.find((item) => item.id === id);
  if (!post) return;
  try {
    await navigator.clipboard.writeText(post.content);
    showToast("Draft copied. Opening LinkedIn…");
  } catch (error) {
    showToast("Opening LinkedIn. Copy the draft manually if clipboard is blocked.");
  }
  window.open(ui.integrations?.linkedin?.fallback_url || "https://www.linkedin.com/feed/", "_blank", "noopener,noreferrer");
  await api(`/api/drafts/${id}/approve`, { method: "POST", body: JSON.stringify({ schedule_type: "now" }) });
  await refresh();
}

async function resetDemo() {
  await api("/api/reset", { method: "POST" });
  ui.notice = ""; ui.tab = "chat"; await refresh(); showToast("Demo data reset");
}

function showToast(message) {
  ui.toast = message; render();
  setTimeout(() => { ui.toast = ""; render(); }, 2200);
}

refresh().catch((error) => layout(`<div class="page"><div class="notice">Could not load the app: ${escapeHtml(error.message)}</div></div>`));

function integrationSummary() {
  if (!ui.integrations) return "Loading integration status…";
  const ai = ui.integrations.anthropic?.configured ? "Claude enabled" : "Claude fallback";
  const linkedin = ui.integrations.linkedin?.configured ? "LinkedIn OAuth ready" : "LinkedIn copy fallback";
  return `${ai}. ${linkedin}.`;
}

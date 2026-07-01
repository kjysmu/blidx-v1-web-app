const app = document.querySelector("#app");

const ui = {
  tab: "chat",
  state: null,
  integrations: null,
  auth: JSON.parse(localStorage.getItem("blidx_auth") || "null"),
  demoMode: localStorage.getItem("blidx_demo") === "true",
  authMode: "login",
  selectedCategory: "insights",
  notice: "",
  modal: null,
  toast: "",
  loading: false,
};

const api = async (path, options = {}) => {
  const authHeaders = ui.auth?.access_token ? { Authorization: `Bearer ${ui.auth.access_token}` } : {};
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json", ...authHeaders, ...(options.headers || {}) },
    ...options,
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload.detail || payload.message || "Request failed");
  return payload;
};

const escapeHtml = (value = "") =>
  value.replace(/[&<>"']/g, (char) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;",
  }[char]));

function renderMarkdown(value = "") {
  let html = escapeHtml(String(value)).replace(/\r\n/g, "\n");
  html = html.replace(/`([^`\n]+)`/g, "<code>$1</code>");
  html = html.replace(/\*\*([\s\S]+?)\*\*/g, "<strong>$1</strong>");
  html = html.replace(/(^|[\s(])\*([^*\n]+?)\*/g, "$1<em>$2</em>");
  html = html.replace(
    /\[([^\]\n]+)\]\((https?:\/\/[^\s)]+)\)/g,
    '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>',
  );
  html = html.replace(/\s+---\s+/g, "\n\n");
  html = html.replace(/\s+(<strong>\d+[.)]\s)/g, "\n\n$1");
  return html
    .split(/\n{2,}/)
    .map((paragraph) => paragraph.trim())
    .filter(Boolean)
    .map((paragraph) => `<p>${paragraph.replace(/\n/g, "<br>")}</p>`)
    .join("");
}

function stripMarkdown(value = "") {
  return String(value)
    .replace(/\*\*([^*]+)\*\*/g, "$1")
    .replace(/\*([^*]+)\*/g, "$1")
    .replace(/`([^`]+)`/g, "$1")
    .replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, "$1");
}

const navItems = [
  ["chat", "✦", "Chat"],
  ["bank", "▦", "Bank"],
  ["library", "▤", "Library"],
  ["calendar", "□", "Calendar"],
  ["analytics", "⌁", "Analytics"],
  ["settings", "⚙", "Settings"],
];

function layout(content) {
  if (!ui.auth && !ui.demoMode) {
    app.innerHTML = renderAuth();
    bindAuth();
    return;
  }

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
          <div class="top-actions"><span class="account-pill">${accountLabel()}</span><button class="icon-button" data-action="new-draft">＋ Draft</button><button class="icon-button" data-action="logout">${ui.auth ? "Log out" : "Exit demo"}</button></div>
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

function renderAuth() {
  const isSignup = ui.authMode === "signup";
  return `<main class="auth-page">
    <section class="auth-hero">
      <div class="brand auth-brand"><span class="brand-mark">B</span> Blidx</div>
      <div class="eyebrow">Mira · first GTM agent</div>
      <h1>${isSignup ? "Create your Blidx workspace." : "Welcome back to Blidx."}</h1>
      <p class="lead">Sign in to keep your own profile, Content Bank, drafts, and LinkedIn workflow separate from the public demo.</p>
      <div class="auth-points">
        <div><strong>1/ Private workspace</strong><span>Your drafts and memories stay under your account.</span></div>
        <div><strong>2/ Claude-backed Mira</strong><span>Chat, angle selection, and draft generation use your context.</span></div>
        <div><strong>3/ LinkedIn workflow</strong><span>Prepare posts for OAuth publishing or manual posting.</span></div>
      </div>
    </section>
    <section class="auth-card">
      <h2>${isSignup ? "Sign up" : "Log in"}</h2>
      <p class="muted">${isSignup ? "Use at least 8 characters for the password." : "Use the email and password you registered with."}</p>
      <form id="auth-form">
        ${isSignup ? '<div class="field"><label>Name</label><input class="input" name="user_name" placeholder="Jae" /></div>' : ""}
        <div class="field"><label>Email</label><input class="input" name="email" type="email" required placeholder="you@example.com" /></div>
        <div class="field"><label>Password</label><input class="input" name="password" type="password" required minlength="${isSignup ? 8 : 1}" placeholder="••••••••" /></div>
        <button class="button" style="width:100%">${isSignup ? "Create account" : "Log in"}</button>
      </form>
      <button class="button ghost auth-switch" id="toggle-auth">${isSignup ? "Already have an account? Log in" : "New here? Create account"}</button>
      <button class="button secondary auth-switch" id="continue-demo">Continue with public demo</button>
    </section>
  </main>`;
}

function bindAuth() {
  document.querySelector("#auth-form")?.addEventListener("submit", submitAuth);
  document.querySelector("#toggle-auth")?.addEventListener("click", () => {
    ui.authMode = ui.authMode === "login" ? "signup" : "login";
    render();
  });
  document.querySelector("#continue-demo")?.addEventListener("click", async () => {
    ui.demoMode = true;
    localStorage.setItem("blidx_demo", "true");
    await refresh();
  });
}

function accountLabel() {
  if (ui.auth) return escapeHtml(ui.auth.user_name || ui.auth.email || "Account");
  return "Public demo";
}

function bindGlobal() {
  document.querySelectorAll("[data-tab]").forEach((button) => {
    button.onclick = () => { ui.tab = button.dataset.tab; ui.modal = null; render(); };
  });
  document.querySelectorAll('[data-action="new-draft"]').forEach((button) => {
    button.onclick = () => {
      ui.tab = "chat";
      render();
      setTimeout(() => {
        const input = document.querySelector("#chat-message");
        if (input) {
          input.value = "Draft a post about ";
          input.focus();
        }
      }, 0);
    };
  });
  document.querySelectorAll('[data-action="logout"]').forEach((button) => {
    button.onclick = logout;
  });
  document.querySelectorAll('[data-action="sample-draft"]').forEach((button) => {
    button.onclick = createSampleDraft;
  });
}

function render() {
  if (!ui.state) return layout('<div class="page"><div class="empty">Loading Blidx…</div></div>');
  if (ui.auth && ui.state.onboarding_completed === false) {
    layout(renderOnboarding());
    bindOnboarding();
    return;
  }
  const views = { chat: renderChat, bank: renderBank, library: renderLibrary, calendar: renderCalendar, analytics: renderAnalytics, settings: renderSettings };
  layout(views[ui.tab]());
  bindView();
}

function renderOnboarding() {
  const p = ui.state.profile || {};
  return `<section class="page onboarding-page">
    <div class="eyebrow">Workspace setup</div>
    <h1>Set up Mira’s context.</h1>
    <p class="lead">This takes one minute. Mira will use these details for chat, Content Bank decisions, and LinkedIn drafts.</p>
    <form class="card form-grid onboarding-form" id="onboarding-form">
      ${field("First name", "first_name", p.first_name || accountLabel())}
      ${field("Role", "role", p.role || "Founder")}
      ${field("Company", "company_name", p.company_name || "")}
      ${field("Website", "company_website", p.company_website || "")}
      ${field("Industry", "industry", p.industry || "")}
      ${field("Company description", "company_description", p.company_description || "", true)}
      ${field("Audience (comma separated)", "audience", (p.audience || ["Founders", "Industry Peers"]).join(", "), true)}
      ${field("Expertise (comma separated)", "expertise", (p.expertise || []).join(", "), true)}
      <div class="field"><label>Posting frequency</label><select name="posting_frequency"><option value="1-2x_per_week">1–2× per week</option><option value="3-4x_per_week" selected>3–4× per week</option><option value="5+_per_week">5+ per week</option></select></div>
      <div class="field"><label>Tone</label><select name="tone"><option>Insightful & measured</option><option>Bold & opinionated</option><option>Warm & personal</option><option>Data-driven & practical</option></select></div>
      ${field("Writing style notes", "writing_style", p.writing_style || "Reflective, specific, founder-led, and practical.", true)}
      <div class="field full"><label>First Content Bank memory</label><textarea name="first_memory" placeholder="Example: This week I spoke with a founder who said content feels hard because the real work is scattered across notes, calls, and decisions."></textarea></div>
      <div class="field full onboarding-actions"><button class="button">Complete setup</button><button type="button" class="button ghost" id="skip-onboarding">Skip for now</button></div>
    </form>
  </section>`;
}

function bindOnboarding() {
  document.querySelector("#onboarding-form")?.addEventListener("submit", completeOnboarding);
  document.querySelector("#skip-onboarding")?.addEventListener("click", async () => {
    const p = ui.state.profile;
    await api("/api/onboarding/complete", {
      method: "POST",
      body: JSON.stringify({
        first_name: p.first_name || "User",
        role: p.role || "Founder",
        company_name: p.company_name || "My company",
        company_website: p.company_website || "",
        industry: p.industry || "Startup",
        company_description: p.company_description || "A founder-led company building toward product-market fit.",
        audience: p.audience || ["Founders"],
        expertise: p.expertise || [],
        content_types: p.content_types || ["Industry insights"],
        posting_frequency: p.posting_frequency || "3-4x_per_week",
        tone: p.tone || "Insightful & measured",
        writing_style: p.writing_style || "",
      }),
    });
    await refresh();
    showToast("Setup skipped. You can edit Settings anytime.");
  });
}

function renderChat() {
  const profile = ui.state.profile;
  const activeDrafts = ui.state.posts.filter((post) => post.status === "pending");
  const published = ui.state.posts.filter((post) => post.status === "published").length;
  const goal = profile.posting_frequency === "5+_per_week" ? 5 : profile.posting_frequency === "3-4x_per_week" ? 3 : 1;
  const messages = ui.state.messages?.length ? ui.state.messages : [{
    role: "mira",
    content: "Your pipeline is clear. What should we turn into your next post?",
  }];
  return `
    <section class="page">
      <div class="eyebrow">Your content workdesk</div>
      <h1>Good ${new Date().getHours() < 12 ? "morning" : "afternoon"}, ${escapeHtml(profile.first_name)}.</h1>
      <p class="lead">Chat with Mira like a content partner. Share a moment, ask for an angle, or say “Draft a post about…” and I’ll create a review-ready LinkedIn draft.</p>
      ${workflowGuide()}
      <div class="grid">
        <div class="card"><div class="card-head"><h3>This week</h3><span class="badge ${published >= goal ? "published" : "pending"}">${published}/${goal} posts</span></div><div class="metric">${Math.min(Math.round((published / goal) * 100), 100)}%</div><div class="progress"><span style="width:${Math.min((published / goal) * 100, 100)}%"></span></div><div class="muted small">Based on your ${escapeHtml(profile.posting_frequency.replaceAll("_", " "))} goal.</div></div>
        <div class="card"><div class="card-head"><h3>Content Bank</h3><span class="badge published">${ui.state.content_bank.length} entries</span></div><p class="muted">Your latest real-world context makes every draft more personal.</p><button class="button secondary" data-tab="bank">Add today’s insight</button></div>
      </div>
      <div class="chat-stream" style="margin-top:18px">
        ${messages.map(messageBubble).join("")}
        ${ui.loading ? '<div class="bubble mira typing"><strong>Mira</strong><br>Thinking through the angle…</div>' : ""}
        ${activeDrafts.map(draftCard).join("")}
      </div>
      <div class="composer">
        <form class="composer-box" id="chat-form">
          <input class="input" id="chat-message" placeholder="Message Mira… try: Draft a post about human connection versus AI in mental health" required minlength="2" />
          <button class="button" ${ui.loading ? "disabled" : ""}>${ui.loading ? "Working…" : "Send"}</button>
        </form>
        <div class="prompt-row">
          ${quickPrompt("What should I post about today?")}
          ${quickPrompt("Give me 3 angles from my Content Bank")}
          ${quickPrompt("Draft a post from my latest memory")}
        </div>
      </div>
    </section>`;
}

function quickPrompt(text) {
  return `<button class="prompt-chip" data-prompt="${escapeHtml(text)}">${escapeHtml(text)}</button>`;
}

function messageBubble(message) {
  const role = message.role === "user" ? "user" : "mira";
  const label = role === "user" ? "You" : "Mira";
  return `<div class="bubble ${role}"><strong>${label}</strong><div class="markdown">${renderMarkdown(message.content || "")}</div></div>`;
}

function draftCard(post) {
  const provider = post.generation_provider || "template";
  const publishLabel = ui.integrations?.linkedin?.connected ? "Publish to LinkedIn" : "Copy & open LinkedIn";
  return `<article class="draft-card" data-post="${post.id}">
    <div class="draft-meta"><span>Draft v${post.version} · ${post.source.replace("_", " ")} · ${escapeHtml(provider)}</span><span>${post.char_count} / 3,000</span></div>
    <div class="draft-content markdown">${renderMarkdown(post.content)}</div>
    ${variantRail(post)}
    <div class="draft-actions">
      <button class="button" data-draft-action="approve" data-id="${post.id}">Approve</button>
      <button class="button secondary" data-draft-action="linkedin" data-id="${post.id}">${publishLabel}</button>
      <button class="button secondary" data-draft-action="edit" data-id="${post.id}">Edit</button>
      <button class="button ghost" data-draft-action="copy" data-id="${post.id}">Copy</button>
      <button class="button ghost" data-draft-action="save" data-id="${post.id}">Save draft</button>
      <button class="button danger" data-draft-action="delete" data-id="${post.id}">Skip</button>
    </div>
  </article>`;
}

function variantRail(post) {
  const variants = post.variants || [];
  if (!variants.length) return "";
  return `<div class="variant-rail">
    <div class="variant-heading"><strong>Try another direction</strong><span>${variants.length} variants</span></div>
    <div class="variant-grid">
      ${variants.map((variant) => `<div class="variant-card ${post.selected_variant_id === variant.id ? "active" : ""}">
        <div class="variant-card-head"><strong>${escapeHtml(variant.label)}</strong><span>${variant.char_count || variant.content.length} chars</span></div>
        <p>${escapeHtml(variant.positioning || "")}</p>
        <div class="variant-preview">${escapeHtml(stripMarkdown(variant.content).slice(0, 180))}${variant.content.length > 180 ? "…" : ""}</div>
        <button class="button secondary" data-draft-action="variant" data-id="${post.id}" data-variant-id="${variant.id}">${post.selected_variant_id === variant.id ? "Using this" : "Use this variant"}</button>
      </div>`).join("")}
    </div>
  </div>`;
}

function workflowGuide() {
  const hasMemory = ui.state.content_bank.length > 0;
  const hasDraft = ui.state.posts.some((post) => post.status === "pending");
  const hasLibrary = ui.state.posts.some((post) => post.status !== "deleted");
  const hasScheduled = ui.state.posts.some((post) => ["scheduled", "published"].includes(post.status));
  const items = [
    ["Save one real moment to Content Bank", hasMemory],
    ["Generate one review-ready draft", hasDraft || hasLibrary],
    ["Edit, copy, save, approve, or skip the draft", hasLibrary],
    ["Check Library, Calendar, and Analytics states", hasScheduled],
  ];
  return `<div class="card workflow-card">
    <div class="card-head"><div><h3>Recommended test path</h3><p class="muted small">This uses your real workspace data. No preloaded scenario required.</p></div><span class="badge ${hasMemory ? "published" : "draft"}">${hasMemory ? "in progress" : "start here"}</span></div>
    <div class="checklist">${items.map(([label, done]) => `<div class="check ${done ? "done" : ""}"><span>${done ? "✓" : "○"}</span>${label}</div>`).join("")}</div>
    <div class="workflow-actions">
      <button class="button" data-tab="bank">${hasMemory ? "Add another memory" : "Add first memory"}</button>
      <button class="button secondary" data-action="sample-draft" ${hasMemory ? "" : "disabled"}>Draft from latest memory</button>
      <button class="button ghost" data-tab="bank">Open Content Bank</button>
    </div>
    <p class="muted small">Mira can chat, suggest angles, draft, revise, and move posts into Library/Calendar. LinkedIn has a manual copy/open fallback until OAuth is fully connected.</p>
  </div>`;
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
    <div class="list">${posts.length ? posts.map(libraryItem).join("") : '<div class="empty">No posts yet. Draft one with Mira.</div>'}</div>
  </section>`;
}

function libraryItem(post) {
  const excerpt = stripMarkdown(post.content).slice(0, 220);
  return `<div class="list-item">
    <div class="list-top"><div><strong>${escapeHtml(post.title)}</strong><p>${escapeHtml(excerpt)}${post.content.length > 220 ? "…" : ""}</p></div><span class="badge ${post.status}">${post.status}</span></div>
    <div class="small muted" style="margin-top:10px">${post.char_count} characters · v${post.version} · ${escapeHtml(post.generation_provider || "template")}</div>
    <div class="inline-actions">
      ${post.status === "pending" || post.status === "draft" ? `<button class="button secondary" data-draft-action="edit" data-id="${post.id}">Edit</button><button class="button" data-draft-action="approve" data-id="${post.id}">Approve</button>` : ""}
      <button class="button ghost" data-draft-action="copy" data-id="${post.id}">Copy</button>
      ${post.status !== "published" ? `<button class="button secondary" data-draft-action="linkedin" data-id="${post.id}">${ui.integrations?.linkedin?.connected ? "Publish to LinkedIn" : "Copy & open LinkedIn"}</button>` : ""}
    </div>
  </div>`;
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

function renderAnalytics() {
  const posts = ui.state.posts.filter((post) => post.status !== "deleted");
  const published = posts.filter((post) => post.status === "published").length;
  const scheduled = posts.filter((post) => post.status === "scheduled").length;
  const pending = posts.filter((post) => ["pending", "draft"].includes(post.status)).length;
  const bank = ui.state.content_bank;
  const highPotential = bank.filter((entry) => entry.content_potential === "high").length;
  const avgChars = posts.length ? Math.round(posts.reduce((sum, post) => sum + (post.char_count || 0), 0) / posts.length) : 0;
  const categoryCounts = bank.reduce((acc, entry) => {
    acc[entry.category] = (acc[entry.category] || 0) + 1;
    return acc;
  }, {});
  const categories = Object.entries(categoryCounts).sort((a, b) => b[1] - a[1]);
  return `<section class="page"><div class="eyebrow">Progress</div><h1>Analytics</h1><p class="lead">A lightweight MVP view of whether the content workflow is moving: memories captured, drafts created, and posts moved toward LinkedIn.</p>
    <div class="stats-grid">
      ${statCard("Content Bank", bank.length, `${highPotential} high-potential entries`)}
      ${statCard("Drafts", pending, "Ready for review or revision")}
      ${statCard("Scheduled", scheduled, "Placed on the calendar")}
      ${statCard("Published", published, "Marked as posted")}
    </div>
    <div class="grid" style="margin-top:18px">
      <div class="card"><div class="card-head"><h3>Pipeline health</h3><span class="badge ${posts.length ? "published" : "draft"}">${posts.length ? "active" : "empty"}</span></div><p class="muted">${posts.length ? `Average draft length is ${avgChars} characters. The next improvement is to keep moving pending drafts into either scheduled, published, or skipped states.` : "Create a draft from Chat to start measuring the workflow."}</p></div>
      <div class="card"><div class="card-head"><h3>Memory mix</h3><span class="badge draft">${categories.length || 0} categories</span></div>${categories.length ? categories.map(([name, count]) => `<div class="bar-row"><span>${escapeHtml(name)}</span><strong>${count}</strong></div>`).join("") : '<p class="muted">No Content Bank entries yet.</p>'}</div>
    </div>
  </section>`;
}

function statCard(label, value, helper) {
  return `<div class="card stat-card"><div class="muted small">${label}</div><div class="metric">${value}</div><p class="muted small">${escapeHtml(helper)}</p></div>`;
}

function renderSettings() {
  const p = ui.state.profile;
  const anthropic = ui.integrations?.anthropic;
  const linkedin = ui.integrations?.linkedin;
  const payloadcms = ui.integrations?.payloadcms;
  const linkedinBadge = linkedin?.connected ? "Connected" : linkedin?.configured ? "OAuth configured" : "Fallback ready";
  const linkedinClass = linkedin?.connected ? "published" : linkedin?.configured ? "scheduled" : "draft";
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
      ${textAreaField("Writing style notes", "writing_style", p.writing_style || "", "Example: Reflective, direct, specific, no hype. I like numbered points and founder lessons.", true)}
      ${textAreaField("Writing samples", "writing_samples", (p.writing_samples || []).join("\n\n---\n\n"), "Paste 1-3 LinkedIn posts or writing examples. Separate samples with ---.", true)}
      ${field("Preferred structure", "preferred_structure", p.preferred_structure || "Hook, context, lesson, reflective question", true)}
      ${field("Phrases to avoid (comma separated)", "avoided_phrases", (p.avoided_phrases || []).join(", "), true)}
      ${field("CTA style", "cta_style", p.cta_style || "Reflective question", true)}
      <div class="field full"><button class="button">Save profile</button> <button type="button" class="button ghost" id="reset-demo">Reset workspace data</button></div>
    </form>
    <div class="card" style="margin-top:16px"><div class="card-head"><h3>AI generation</h3><span class="badge ${anthropic?.configured ? "published" : "draft"}">${anthropic?.configured ? "Claude ready" : "Local fallback"}</span></div><p class="muted">${anthropic?.configured ? `Mira drafts use ${escapeHtml(anthropic.model)} with profile, writing samples, voice controls, and Content Bank context.` : "Add ANTHROPIC_API_KEY in Render to enable live Claude generation. The local fallback still uses your CTA style and avoids generic repeated templates."}</p></div>
    <div class="card" style="margin-top:16px"><div class="card-head"><h3>LinkedIn</h3><span class="badge ${linkedinClass}">${linkedinBadge}</span></div><p class="muted">${linkedin?.connected ? "LinkedIn is connected for this staging session. Draft cards can publish directly." : linkedin?.configured ? "OAuth URL generation is available. The redirect URL must exactly match the LinkedIn app settings; otherwise use the manual fallback." : "Use Copy & open LinkedIn on any draft. For full OAuth on staging, add the Render URL to LinkedIn redirect URLs or route app.blidx.com to this service."}</p>${linkedin?.connected ? "" : '<button class="button secondary" id="connect-linkedin">Connect LinkedIn</button>'}</div>
    <div class="card" style="margin-top:16px"><div class="card-head"><h3>PayloadCMS review</h3><span class="badge draft">${escapeHtml(payloadcms?.recommendation || "defer")}</span></div><p class="muted">${escapeHtml(payloadcms?.reason || "PayloadCMS review pending.")}</p></div>
  </section>`;
}

function field(label, name, value, full = false) {
  return `<div class="field ${full ? "full" : ""}"><label>${label}</label><input class="input" name="${name}" value="${escapeHtml(value || "")}" /></div>`;
}

function textAreaField(label, name, value, placeholder = "", full = false) {
  return `<div class="field ${full ? "full" : ""}"><label>${label}</label><textarea name="${name}" placeholder="${escapeHtml(placeholder)}">${escapeHtml(value || "")}</textarea></div>`;
}

function bindView() {
  bindGlobal();
  document.querySelector("#chat-form")?.addEventListener("submit", sendChatMessage);
  document.querySelector("#bank-form")?.addEventListener("submit", addMemory);
  document.querySelector("#profile-form")?.addEventListener("submit", saveProfile);
  document.querySelector("#reset-demo")?.addEventListener("click", resetDemo);
  document.querySelector("#connect-linkedin")?.addEventListener("click", connectLinkedIn);
  document.querySelectorAll("[data-prompt]").forEach((button) => {
    button.onclick = () => submitPrompt(button.dataset.prompt);
  });
  document.querySelectorAll("[data-category]").forEach((button) => {
    button.onclick = () => { ui.selectedCategory = button.dataset.category; render(); };
  });
  document.querySelectorAll("[data-draft-action]").forEach((button) => {
    button.onclick = () => handleDraftAction(button.dataset.draftAction, button.dataset.id, button.dataset.variantId);
  });
}

async function refresh() {
  const [state, integrations] = await Promise.all([
    api("/api/state"),
    api("/api/integrations/status").catch(() => null),
  ]);
  if (ui.auth && state.auth && !state.auth.authenticated) {
    localStorage.removeItem("blidx_auth");
    ui.auth = null;
    ui.demoMode = false;
    localStorage.removeItem("blidx_demo");
    showToast("Session expired. Please log in again.");
    render();
    return;
  }
  ui.state = state;
  ui.integrations = integrations;
  render();
}

async function submitAuth(event) {
  event.preventDefault();
  const form = new FormData(event.currentTarget);
  const payload = Object.fromEntries(form.entries());
  const path = ui.authMode === "signup" ? "/auth/register" : "/auth/login";
  try {
    const auth = await api(path, { method: "POST", body: JSON.stringify(payload) });
    ui.auth = auth;
    ui.demoMode = false;
    localStorage.setItem("blidx_auth", JSON.stringify(auth));
    localStorage.removeItem("blidx_demo");
    await refresh();
    showToast(ui.authMode === "signup" ? "Workspace created" : "Logged in");
  } catch (error) {
    showToast(error.message);
  }
}

async function completeOnboarding(event) {
  event.preventDefault();
  const form = new FormData(event.currentTarget);
  const payload = Object.fromEntries(form.entries());
  payload.audience = payload.audience.split(",").map((v) => v.trim()).filter(Boolean);
  payload.expertise = payload.expertise.split(",").map((v) => v.trim()).filter(Boolean);
  payload.content_types = ["Industry insights", "Personal stories", "Lessons learned"];
  try {
    ui.loading = true;
    await api("/api/onboarding/complete", { method: "POST", body: JSON.stringify(payload) });
    ui.loading = false;
    await refresh();
    showToast("Workspace setup complete");
  } catch (error) {
    ui.loading = false;
    showToast(error.message);
  }
}

async function sendChatMessage(event) {
  event.preventDefault();
  const input = document.querySelector("#chat-message");
  const message = input.value.trim();
  input.value = "";
  await submitPrompt(message);
}

async function submitPrompt(message) {
  if (!message) return;
  ui.loading = true; render();
  try {
    const result = await api("/api/chat/message", { method: "POST", body: JSON.stringify({ message }) });
    ui.state = result.state;
    ui.loading = false;
    await refresh();
  } catch (error) {
    ui.loading = false;
    showToast(error.message);
  }
}

async function createSampleDraft() {
  ui.tab = "chat";
  ui.loading = true; render();
  try {
    const latest = ui.state.content_bank[0]?.raw_text;
    const topic = latest || `${ui.state.profile.company_name || "my company"} founder insight from this week`;
    await api("/api/chat/message", {
      method: "POST",
      body: JSON.stringify({ message: `Draft a post about ${topic}` }),
    });
    ui.loading = false;
    await refresh();
    showToast("Sample draft generated");
  } catch (error) {
    ui.loading = false;
    showToast(error.message);
  }
}

async function addMemory(event) {
  event.preventDefault();
  const raw_text = document.querySelector("#bank-text").value;
  try {
    const entry = await api("/api/content-bank", { method: "POST", body: JSON.stringify({ raw_text, category: ui.selectedCategory }) });
    ui.notice = `Saved to Content Bank · ${entry.category} · Fresh`;
    await refresh();
    ui.notice = `Saved to Content Bank · ${entry.category} · Fresh`; render();
  } catch (error) {
    showToast(error.message);
  }
}

async function saveProfile(event) {
  event.preventDefault();
  const form = new FormData(event.currentTarget);
  const payload = Object.fromEntries(form.entries());
  payload.audience = payload.audience.split(",").map((v) => v.trim()).filter(Boolean);
  payload.expertise = payload.expertise.split(",").map((v) => v.trim()).filter(Boolean);
  payload.avoided_phrases = (payload.avoided_phrases || "").split(",").map((v) => v.trim()).filter(Boolean);
  payload.writing_samples = (payload.writing_samples || "").split(/\n\s*---\s*\n/).map((v) => v.trim()).filter(Boolean);
  await api("/api/profile", { method: "PUT", body: JSON.stringify(payload) });
  ui.notice = "Profile updated. Mira will use it on the next draft.";
  await refresh(); ui.notice = "Profile updated. Mira will use it on the next draft."; render();
}

function handleDraftAction(action, id, variantId = null) {
  if (action === "approve") {
    ui.modal = `<div class="modal-backdrop"><div class="modal"><h3>When should Mira publish?</h3><p class="muted">Use “Copy & open LinkedIn” for the safest live workflow today. Scheduling still keeps Library and Calendar state organized.</p><div class="modal-actions"><button class="button ghost" data-schedule="now">Mark posted</button><button class="button" data-schedule="best_time">Best time</button></div></div></div>`;
    render();
    document.querySelectorAll("[data-schedule]").forEach((button) => button.onclick = () => approveDraft(id, button.dataset.schedule));
  } else if (action === "linkedin") {
    copyAndOpenLinkedIn(id);
  } else if (action === "copy") {
    copyDraft(id);
  } else if (action === "edit") {
    ui.modal = `<div class="modal-backdrop"><div class="modal"><h3>Tell Mira what to change</h3><p class="muted">Use a quick edit or type your own instructions.</p><div class="quick-edit-row">${quickEditButton("Make it shorter")} ${quickEditButton("Make the hook stronger")} ${quickEditButton("Make it more personal")} ${quickEditButton("Add a clearer CTA")} ${quickEditButton("Make it more like my voice")}</div><textarea id="edit-instructions" placeholder="Try: Make it shorter, bolder, or more personal."></textarea><div class="modal-actions"><button class="button ghost" id="cancel-modal">Cancel</button><button class="button" id="submit-edit">Revise draft</button></div></div></div>`;
    render();
    document.querySelector("#cancel-modal").onclick = () => { ui.modal = null; render(); };
    document.querySelector("#submit-edit").onclick = () => editDraft(id);
    document.querySelectorAll("[data-quick-edit]").forEach((button) => {
      button.onclick = () => {
        const textarea = document.querySelector("#edit-instructions");
        textarea.value = button.dataset.quickEdit;
        textarea.focus();
      };
    });
  } else if (action === "variant") {
    useVariant(id, variantId);
  } else {
    api(`/api/drafts/${id}/${action}`, { method: "POST" }).then(() => refresh()).then(() => showToast(action === "save" ? "Saved to Library" : "Draft skipped"));
  }
}

function quickEditButton(label) {
  return `<button class="prompt-chip" type="button" data-quick-edit="${escapeHtml(label)}">${escapeHtml(label)}</button>`;
}

async function copyDraft(id) {
  const post = ui.state.posts.find((item) => item.id === id);
  if (!post) return;
  try {
    await navigator.clipboard.writeText(post.content);
    showToast("Draft copied");
  } catch (error) {
    ui.modal = `<div class="modal-backdrop"><div class="modal"><h3>Copy draft</h3><p class="muted">Clipboard access was blocked. Select and copy the text below.</p><textarea readonly>${escapeHtml(post.content)}</textarea><div class="modal-actions"><button class="button" id="cancel-modal">Done</button></div></div></div>`;
    render();
    document.querySelector("#cancel-modal").onclick = () => { ui.modal = null; render(); };
  }
}

async function editDraft(id) {
  const instructions = document.querySelector("#edit-instructions").value;
  if (instructions.length < 2) return;
  await api(`/api/drafts/${id}/edit`, { method: "POST", body: JSON.stringify({ instructions }) });
  ui.modal = null; await refresh(); showToast("Mira revised the draft");
}

async function useVariant(id, variantId) {
  if (!variantId) return;
  await api(`/api/drafts/${id}/use-variant`, {
    method: "POST",
    body: JSON.stringify({ variant_id: variantId }),
  });
  await refresh();
  showToast("Variant applied");
}

async function approveDraft(id, schedule_type) {
  await api(`/api/drafts/${id}/approve`, { method: "POST", body: JSON.stringify({ schedule_type }) });
  ui.modal = null; await refresh();
  showToast(schedule_type === "now" ? "Published locally" : "Scheduled for Mira’s recommended time");
}

async function copyAndOpenLinkedIn(id) {
  const post = ui.state.posts.find((item) => item.id === id);
  if (!post) return;
  const publishResult = await api(`/api/drafts/${id}/publish`, { method: "POST" });
  if (publishResult.published) {
    await refresh();
    showToast("Published to LinkedIn");
    return;
  }
  try {
    await navigator.clipboard.writeText(post.content);
    showToast("Draft copied. Opening LinkedIn…");
  } catch (error) {
    showToast("Opening LinkedIn. Copy the draft manually if clipboard is blocked.");
  }
  window.open(publishResult.fallback_url || ui.integrations?.linkedin?.fallback_url || "https://www.linkedin.com/feed/", "_blank", "noopener,noreferrer");
  showLinkedInTrackingModal(id);
}

function showLinkedInTrackingModal(id) {
  ui.modal = `<div class="modal-backdrop"><div class="modal"><h3>Did you post it on LinkedIn?</h3><p class="muted">After you paste and publish the draft on LinkedIn, add the post URL here so Blidx can mark it as published. You can also mark it posted without a URL for testing.</p><input class="input" id="linkedin-url" placeholder="https://www.linkedin.com/feed/update/..." /><div class="modal-actions"><button class="button ghost" id="cancel-modal">Not yet</button><button class="button" id="save-linkedin-url">Mark posted</button></div></div></div>`;
  render();
  document.querySelector("#cancel-modal").onclick = () => { ui.modal = null; render(); };
  document.querySelector("#save-linkedin-url").onclick = () => trackLinkedInUrl(id);
}

async function trackLinkedInUrl(id) {
  const url = document.querySelector("#linkedin-url")?.value || "";
  await api(`/api/drafts/${id}/track-linkedin-url`, { method: "POST", body: JSON.stringify({ url }) });
  ui.modal = null;
  await refresh();
  showToast("Marked as posted");
}

async function connectLinkedIn() {
  try {
    const result = await api("/api/integrations/linkedin/connect");
    if (result.authorization_url) {
      window.location.href = result.authorization_url;
      return;
    }
    showToast(result.message || "LinkedIn OAuth is not configured yet");
  } catch (error) {
    showToast(error.message);
  }
}

async function resetDemo() {
  await api("/api/reset", { method: "POST" });
  ui.notice = ""; ui.tab = "chat"; await refresh(); showToast(ui.auth ? "Workspace reset" : "Demo data reset");
}

async function seedDemo() {
  await api("/api/seed-test-scenario", { method: "POST" });
  ui.notice = "";
  ui.tab = "chat";
  await refresh();
  showToast("Tester scenario loaded");
}

function showToast(message) {
  ui.toast = message; render();
  setTimeout(() => { ui.toast = ""; render(); }, 2200);
}

function logout() {
  ui.auth = null;
  ui.demoMode = false;
  ui.state = null;
  ui.integrations = null;
  localStorage.removeItem("blidx_auth");
  localStorage.removeItem("blidx_demo");
  render();
}

refresh().catch((error) => layout(`<div class="page"><div class="notice">Could not load the app: ${escapeHtml(error.message)}</div></div>`));

function integrationSummary() {
  if (!ui.integrations) return "Loading integration status…";
  const ai = ui.integrations.anthropic?.configured ? "Claude enabled" : "Claude fallback";
  const linkedin = ui.integrations.linkedin?.configured ? "LinkedIn OAuth ready" : "LinkedIn copy fallback";
  return `${ai}. ${linkedin}.`;
}

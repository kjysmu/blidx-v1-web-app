const app = document.querySelector("#app");

const ui = {
  tab: "chat",
  state: null,
  integrations: null,
  auth: JSON.parse(localStorage.getItem("blidx_auth") || "null"),
  demoMode: localStorage.getItem("blidx_demo") === "true",
  authMode: "login",
  authError: "",
  authSubmitting: false,
  selectedCategory: "insights",
  libraryFilter: "all",
  librarySearch: "",
  notice: "",
  modal: null,
  toast: "",
  loading: false,
  scrollChatAfterRender: false,
  quickActionsOpen: false,
  pendingMessages: [],
  reviewDraftId: null,
  expandedLibraryPosts: new Set(),
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

function cleanAngleText(value = "") {
  return stripMarkdown(value)
    .replace(/[“”]/g, '"')
    .replace(/[‘’]/g, "'")
    .replace(/\s+/g, " ")
    .trim();
}

function extractAnglesFromMessage(content = "") {
  const raw = String(content || "");
  const angles = [];
  const pushAngle = (title, detail) => {
    const cleanTitle = cleanAngleText(title).replace(/^[\s:.-]+|[\s:.-]+$/g, "");
    const cleanDetail = cleanAngleText(detail).replace(/^[\s:.-]+|[\s:.-]+$/g, "");
    if (!cleanTitle || cleanTitle.length < 4) return;
    if (angles.some((angle) => angle.title.toLowerCase() === cleanTitle.toLowerCase())) return;
    const context = cleanDetail ? `${cleanTitle}: ${cleanDetail}` : cleanTitle;
    angles.push({
      title: cleanTitle,
      detail: cleanDetail,
      prompt: `Draft a LinkedIn post from this angle: ${context}`,
    });
  };

  const numberedPattern = /(?:^|\n)\s*(\d{1,2})\s*[\/.)]\s*([^:\n*]{4,90}):\s*([\s\S]*?)(?=\n\s*\d{1,2}\s*[\/.)]\s*[^:\n*]{4,90}:|\n\s*(?:The strongest|Recommended|Which|Want|Quick|One question)\b|$)/gi;
  for (const match of raw.matchAll(numberedPattern)) pushAngle(match[2], match[3]);

  if (angles.length < 2) {
    const boldPattern = /\*\*\s*(\d{1,2})\s*[\/.)]\s*([^*]{4,90}?)\s*\*\*\s*([\s\S]*?)(?=\*\*\s*\d{1,2}\s*[\/.)]|\n\s*(?:The strongest|Recommended|Which|Want|Quick|One question)\b|$)/gi;
    for (const match of raw.matchAll(boldPattern)) pushAngle(match[2], match[3]);
  }

  return angles.slice(0, 3);
}

const navItems = [
  ["chat", "✦", "Chat"],
  ["bank", "▦", "Bank"],
  ["library", "▤", "Library"],
  ["calendar", "□", "Calendar"],
  ["settings", "⚙", "Settings"],
];

const memoryTemplates = [
  ["people", "🤝", "Met someone"], ["events", "🎤", "Attended event"],
  ["insights", "💡", "Key insight"], ["milestones", "🏆", "Hit milestone"],
  ["reading", "📖", "Read something"], ["solutions", "🔥", "Solved a problem"],
];

const freshnessOptions = [["fresh", "Fresh"], ["used", "Used"], ["archived", "Archived"]];
const potentialOptions = [["high", "High"], ["medium", "Medium"], ["low", "Low"]];

function sectionLabel() {
  return {
    chat: "Content workspace",
    bank: "Content Bank",
    library: "Library",
    calendar: "Calendar",
    analytics: "Progress",
    settings: "Settings",
  }[ui.tab] || "Content workspace";
}

function quickActionsMenu() {
  if (!ui.quickActionsOpen) return "";
  return `<div class="quick-actions-menu">
    <button data-action="qa-draft"><span>Draft</span><strong>Draft a post</strong><small>Start a Mira draft from any idea.</small></button>
    <button data-action="qa-checkin"><span>Check-in</span><strong>Daily check-in</strong><small>Capture a fresh Content Bank moment.</small></button>
    <button data-action="qa-progress"><span>Progress</span><strong>Performance & progress</strong><small>Open the lightweight Analytics view.</small></button>
  </div>`;
}

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
          <div class="mira-id"><div class="avatar">M</div><div><div class="mira-name">Mira</div><div class="online">● ${sectionLabel()}</div></div></div>
          <div class="top-actions">
            <span class="account-pill">${accountLabel()}</span>
            <div class="quick-actions-wrap">
              <button class="icon-button primary-quick" data-action="quick-actions" aria-label="Open quick actions">＋</button>
              ${quickActionsMenu()}
            </div>
            <button class="icon-button" data-action="logout">${ui.auth ? "Log out" : "Exit demo"}</button>
          </div>
        </header>
        ${content}
      </main>
    </div>
    <nav class="mobile-nav">${mobileNav}</nav>
    ${draftReviewModal()}
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
      ${ui.authError ? `<div class="notice error">${escapeHtml(ui.authError)}</div>` : ""}
      <form id="auth-form">
        ${isSignup ? '<div class="field"><label>Name</label><input class="input" name="user_name" placeholder="Jae" /></div>' : ""}
        <div class="field"><label>Email</label><input class="input" name="email" type="email" required placeholder="you@example.com" /></div>
        <div class="field"><label>Password</label><input class="input" name="password" type="password" required minlength="${isSignup ? 8 : 1}" placeholder="••••••••" /></div>
        <button class="button" style="width:100%" ${ui.authSubmitting ? "disabled" : ""}>${ui.authSubmitting ? "Checking..." : isSignup ? "Create account" : "Log in"}</button>
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
    ui.authError = "";
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
    button.onclick = () => {
      ui.tab = button.dataset.tab;
      ui.modal = null;
      ui.quickActionsOpen = false;
      render();
    };
  });
  document.querySelectorAll('[data-action="new-draft"]').forEach((button) => {
    button.onclick = startDraft;
  });
  document.querySelectorAll('[data-action="quick-actions"]').forEach((button) => {
    button.onclick = () => {
      ui.quickActionsOpen = !ui.quickActionsOpen;
      render();
    };
  });
  document.querySelectorAll('[data-action="qa-draft"]').forEach((button) => {
    button.onclick = startDraft;
  });
  document.querySelectorAll('[data-action="qa-checkin"]').forEach((button) => {
    button.onclick = () => {
      ui.quickActionsOpen = false;
      ui.tab = "bank";
      render();
      setTimeout(() => document.querySelector("#bank-text")?.focus(), 0);
    };
  });
  document.querySelectorAll('[data-action="qa-progress"]').forEach((button) => {
    button.onclick = () => {
      ui.quickActionsOpen = false;
      ui.tab = "analytics";
      render();
    };
  });
  document.querySelectorAll('[data-action="logout"]').forEach((button) => {
    button.onclick = logout;
  });
  document.querySelectorAll('[data-action="sample-draft"]').forEach((button) => {
    button.onclick = createSampleDraft;
  });
}

function startDraft() {
  ui.quickActionsOpen = false;
  ui.tab = "chat";
  render();
  setTimeout(() => {
    const input = document.querySelector("#chat-message");
    if (input) {
      input.value = "Draft a post about ";
      input.focus();
    }
  }, 0);
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
  scrollChatIfRequested();
}

function requestChatScroll() {
  ui.scrollChatAfterRender = true;
}

function scrollChatIfRequested() {
  if (!ui.scrollChatAfterRender || ui.tab !== "chat") return;
  ui.scrollChatAfterRender = false;
  requestAnimationFrame(() => {
    const stream = document.querySelector(".chat-stream");
    const target = stream?.lastElementChild;
    if (!target) return;
    target.scrollIntoView({ behavior: "smooth", block: "end" });
    requestAnimationFrame(() => {
      const composer = document.querySelector(".composer");
      if (!composer) return;
      const targetRect = target.getBoundingClientRect();
      const composerRect = composer.getBoundingClientRect();
      const overlap = targetRect.bottom - composerRect.top + 28;
      if (overlap > 0) window.scrollBy({ top: overlap, behavior: "smooth" });
    });
  });
}

function renderOnboarding() {
  const p = ui.state.profile || {};
  const selectedContentTypes = p.content_types?.length ? p.content_types : ["Industry insights", "Personal stories", "Lessons learned"];
  return `<section class="page onboarding-page">
    <div class="onboarding-hero">
      <div>
        <div class="eyebrow">Mira setup questionnaire</div>
        <h1>Teach Mira who you are before she drafts.</h1>
        <p class="lead">This setup mirrors the product flow more closely: profile, audience, voice, goals, and one real work moment. The better this context is, the less Mira sounds like a generic chatbot.</p>
      </div>
      <div class="onboarding-score-card">
        <strong>Mira readiness</strong>
        <span>Profile</span>
        <span>Audience</span>
        <span>Voice</span>
        <span>First memory</span>
      </div>
    </div>
    <div class="onboarding-steps">
      <div><strong>1</strong><span>Founder identity</span></div>
      <div><strong>2</strong><span>Company context</span></div>
      <div><strong>3</strong><span>Audience + goals</span></div>
      <div><strong>4</strong><span>Voice training</span></div>
      <div><strong>5</strong><span>First memory</span></div>
    </div>
    <form class="onboarding-form" id="onboarding-form">
      <section class="card onboarding-section">
        <div class="onboarding-section-head"><span>01</span><div><h3>Founder identity</h3><p>How Mira should understand and address you.</p></div></div>
        <div class="form-grid">
          ${field("First name", "first_name", p.first_name || accountLabel())}
          ${field("Role", "role", p.role || "Founder")}
        </div>
      </section>
      <section class="card onboarding-section">
        <div class="onboarding-section-head"><span>02</span><div><h3>Company context</h3><p>This replaces generic topic prompts with your actual world.</p></div></div>
        <div class="form-grid">
          ${field("Company", "company_name", p.company_name || "")}
          ${field("Website", "company_website", p.company_website || "")}
          ${field("Industry", "industry", p.industry || "")}
          ${field("Expertise (comma separated)", "expertise", (p.expertise || []).join(", "))}
          ${textAreaField("What are you building?", "company_description", p.company_description || "", "Example: We help founders turn scattered work moments into credible LinkedIn content.", true)}
        </div>
      </section>
      <section class="card onboarding-section">
        <div class="onboarding-section-head"><span>03</span><div><h3>Audience + content goals</h3><p>Choose who the content is for and what rhythm Mira should support.</p></div></div>
        <div class="field full">
          <label>Primary audience (max 3, comma separated)</label>
          <input class="input" name="audience" id="onboarding-audience" value="${escapeHtml((p.audience || ["Founders", "Industry Peers"]).join(", "))}" />
          <div class="choice-row">
            ${choiceChip("audience", "Investors / VCs")}
            ${choiceChip("audience", "Industry Peers")}
            ${choiceChip("audience", "Customers")}
            ${choiceChip("audience", "Talent / Future Hires")}
          </div>
        </div>
        <div class="form-grid">
          <div class="field"><label>Posting frequency</label><select name="posting_frequency"><option value="1-2x_per_week" ${(p.posting_frequency || "3-4x_per_week") === "1-2x_per_week" ? "selected" : ""}>1-2x per week</option><option value="3-4x_per_week" ${(p.posting_frequency || "3-4x_per_week") === "3-4x_per_week" ? "selected" : ""}>3-4x per week</option><option value="5+_per_week" ${(p.posting_frequency || "3-4x_per_week") === "5+_per_week" ? "selected" : ""}>5+ per week</option></select></div>
          <div class="field"><label>Tone</label><select name="tone"><option ${(p.tone || "Insightful & measured") === "Insightful & measured" ? "selected" : ""}>Insightful & measured</option><option ${(p.tone || "") === "Bold & opinionated" ? "selected" : ""}>Bold & opinionated</option><option ${(p.tone || "") === "Warm & personal" ? "selected" : ""}>Warm & personal</option><option ${(p.tone || "") === "Data-driven & practical" ? "selected" : ""}>Data-driven & practical</option></select></div>
        </div>
        <input type="hidden" name="content_types" id="onboarding-content-types" value="${escapeHtml(selectedContentTypes.join(", "))}" />
        <div class="choice-row content-type-row">
          ${choiceChip("content", "Industry insights", selectedContentTypes.includes("Industry insights"))}
          ${choiceChip("content", "Personal stories", selectedContentTypes.includes("Personal stories"))}
          ${choiceChip("content", "Lessons learned", selectedContentTypes.includes("Lessons learned"))}
          ${choiceChip("content", "Case studies", selectedContentTypes.includes("Case studies"))}
        </div>
      </section>
      <section class="card onboarding-section">
        <div class="onboarding-section-head"><span>04</span><div><h3>Voice training</h3><p>Writing samples are the strongest signal for making Mira sound less AI-generated.</p></div></div>
        <div class="form-grid">
          ${textAreaField("LinkedIn About / voice notes", "writing_style", p.writing_style || "Reflective, specific, founder-led, and practical.", "Paste your LinkedIn About section or describe your writing voice.", true)}
          ${textAreaField("Writing samples", "writing_samples", (p.writing_samples || []).join("\n\n---\n\n"), "Paste 1-3 LinkedIn posts you wrote or admire. Separate samples with ---.", true)}
          ${field("Preferred structure", "preferred_structure", p.preferred_structure || "Hook, real moment, lesson, reflective question", true)}
          ${field("Phrases to avoid", "avoided_phrases", (p.avoided_phrases || []).join(", "), true)}
          ${field("CTA style", "cta_style", p.cta_style || "Reflective question", true)}
        </div>
      </section>
      <section class="card onboarding-section">
        <div class="onboarding-section-head"><span>05</span><div><h3>First Content Bank memory</h3><p>Mira should start from one real moment, not an empty shell.</p></div></div>
        <div class="memory-prompts">
          <div><strong>What happened?</strong><span>A call, event, decision, launch, or lesson.</span></div>
          <div><strong>Why did it matter?</strong><span>What changed in your thinking?</span></div>
          <div><strong>Who should hear it?</strong><span>Which audience would care?</span></div>
        </div>
        <div class="field full"><label>First memory</label><textarea name="first_memory" placeholder="Example: This week I spoke with a founder who said content feels hard because the real work is scattered across notes, calls, and decisions." required minlength="3"></textarea><p class="field-help">This becomes the first Content Bank entry and gives Mira something real to reference immediately.</p></div>
      </section>
      <div class="card onboarding-submit">
        <div><strong>Ready to enter the workspace?</strong><p class="muted small">You can edit all of this later in Settings. For now, this gives Mira enough context to start behaving like a content partner.</p></div>
        <div class="onboarding-actions"><button class="button">Complete setup</button><button type="button" class="button ghost" id="skip-onboarding">Use starter context for now</button></div>
      </div>
    </form>
  </section>`;
}

function choiceChip(type, value, active = false) {
  return `<button class="choice-chip ${active ? "active" : ""}" type="button" data-onboarding-chip="${type}" data-value="${escapeHtml(value)}">${escapeHtml(value)}</button>`;
}

function bindOnboarding() {
  document.querySelector("#onboarding-form")?.addEventListener("submit", completeOnboarding);
  document.querySelectorAll("[data-onboarding-chip]").forEach((button) => {
    button.onclick = () => handleOnboardingChip(button.dataset.onboardingChip, button.dataset.value, button);
  });
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
        writing_samples: p.writing_samples || [],
        preferred_structure: p.preferred_structure || "Hook, real moment, lesson, question",
        avoided_phrases: p.avoided_phrases || ["game changer", "unlock", "10x"],
        cta_style: p.cta_style || "Reflective question",
        first_memory: "I am setting up my Blidx workspace and want Mira to help turn real work moments into LinkedIn posts.",
      }),
    });
    await refresh();
    showToast("Setup skipped. You can edit Settings anytime.");
  });
}

function handleOnboardingChip(type, value, button) {
  if (!value) return;
  if (type === "audience") {
    const input = document.querySelector("#onboarding-audience");
    if (!input) return;
    const values = input.value.split(",").map((item) => item.trim()).filter(Boolean);
    if (!values.some((item) => item.toLowerCase() === value.toLowerCase()) && values.length < 3) {
      values.push(value);
    }
    input.value = values.slice(0, 3).join(", ");
    input.focus();
    return;
  }
  if (type === "content") {
    const input = document.querySelector("#onboarding-content-types");
    if (!input) return;
    const values = input.value.split(",").map((item) => item.trim()).filter(Boolean);
    const index = values.findIndex((item) => item.toLowerCase() === value.toLowerCase());
    if (index >= 0) {
      values.splice(index, 1);
      button.classList.remove("active");
    } else {
      values.push(value);
      button.classList.add("active");
    }
    input.value = values.join(", ");
  }
}

function renderChat() {
  const profile = ui.state.profile;
  const activeDrafts = ui.state.posts.filter((post) => post.status === "pending");
  const published = ui.state.posts.filter((post) => post.status === "published").length;
  const goal = profile.posting_frequency === "5+_per_week" ? 5 : profile.posting_frequency === "3-4x_per_week" ? 3 : 1;
  const savedMessages = ui.state.messages?.length ? ui.state.messages : [{
    role: "mira",
    content: "Your pipeline is clear. What should we turn into your next post?",
  }];
  const messages = [...savedMessages, ...ui.pendingMessages];
  const timeline = chatTimeline(messages, activeDrafts);
  return `
    <section class="page">
      <div class="eyebrow">Your content workdesk</div>
      <h1>Good ${new Date().getHours() < 12 ? "morning" : "afternoon"}, ${escapeHtml(profile.first_name)}.</h1>
      <p class="lead">Mira now follows a clearer content workflow: capture a real moment, choose an angle, then create a review-ready LinkedIn draft.</p>
      ${workflowProgress()}
      ${miraBrief()}
      ${workflowGuide()}
      <div class="grid">
        <div class="card"><div class="card-head"><h3>This week</h3><span class="badge ${published >= goal ? "published" : "pending"}">${published}/${goal} posts</span></div><div class="metric">${Math.min(Math.round((published / goal) * 100), 100)}%</div><div class="progress"><span style="width:${Math.min((published / goal) * 100, 100)}%"></span></div><div class="muted small">Based on your ${escapeHtml(profile.posting_frequency.replaceAll("_", " "))} goal.</div></div>
        <div class="card"><div class="card-head"><h3>Content Bank</h3><span class="badge published">${ui.state.content_bank.length} entries</span></div><p class="muted">Your latest real-world context makes every draft more personal.</p><button class="button secondary" data-tab="bank">Add today’s insight</button></div>
      </div>
      <div class="chat-stream" style="margin-top:18px">
        ${timeline}
        ${ui.loading ? '<div class="bubble mira typing"><strong>Mira</strong><br>Thinking through the angle…</div>' : ""}
      </div>
      <div class="composer">
        <form class="composer-box" id="chat-form">
          <input class="input" id="chat-message" placeholder="Try: This week I noticed..." required minlength="2" />
          <button class="button" ${ui.loading ? "disabled" : ""}>${ui.loading ? "Working…" : "Send"}</button>
        </form>
        ${currentDraftShortcut(activeDrafts)}
        <div class="prompt-row">
          ${quickPrompt("What should I post about today?")}
          ${quickPrompt("Give me 3 angles from my Content Bank")}
          ${quickPrompt("Draft from my latest memory")}
          <button class="prompt-chip" type="button" data-action="qa-checkin">Daily check-in</button>
          <button class="prompt-chip" type="button" data-action="qa-progress">Progress</button>
        </div>
      </div>
    </section>`;
}

function workflowProgress() {
  const hasMemory = ui.state.content_bank.length > 0;
  const hasDraft = ui.state.posts.some((post) => post.status === "pending");
  const hasReviewed = ui.state.posts.some((post) => ["saved", "scheduled", "published"].includes(post.status));
  const hasMoved = ui.state.posts.some((post) => ["scheduled", "published"].includes(post.status));
  const steps = [
    ["Capture", "Real moment", hasMemory],
    ["Angle", "Choose POV", hasMemory && (hasDraft || hasReviewed)],
    ["Draft", "Review card", hasDraft || hasReviewed],
    ["Move", "Library/LinkedIn", hasMoved],
  ];
  return `<div class="flow-strip" aria-label="Blidx workflow progress">
    ${steps.map(([label, detail, done], index) => `<div class="flow-step ${done ? "done" : ""}">
      <span>${done ? "✓" : index + 1}</span>
      <strong>${label}</strong>
      <small>${detail}</small>
    </div>`).join("")}
  </div>`;
}

function miraBrief() {
  return `<div class="mira-brief">
    <div>
      <strong>Mira’s role in this MVP</strong>
      <p>Capture real founder context, shape it into sharper angles, then help move one draft through review.</p>
    </div>
    <div class="brief-grid">
      <button data-action="qa-checkin"><span>1</span><strong>Capture</strong><small>Save today’s real moment.</small></button>
      <button data-action="qa-draft"><span>2</span><strong>Draft</strong><small>Turn context into a post.</small></button>
      <button data-tab="library"><span>3</span><strong>Review</strong><small>Edit, approve, copy, or skip.</small></button>
    </div>
  </div>`;
}

function currentDraftShortcut(activeDrafts) {
  if (!activeDrafts.length) return "";
  const latest = activeDrafts[0];
  return `<div class="current-draft-shortcut">
    <span>Current draft: <strong>${escapeHtml(latest.title || "Untitled draft")}</strong></span>
    <button class="read-more" data-draft-review="${latest.id}">Review draft</button>
  </div>`;
}

function chatTimeline(messages, drafts) {
  const draftById = new Map(drafts.map((draft) => [draft.id, draft]));
  const renderedDraftIds = new Set();
  const items = [];
  let order = 0;

  messages.forEach((message) => {
    const messageTime = timeValue(message.created_at);
    items.push({ type: "message", time: messageTime, order: order++, html: messageBubble(message) });
    const linkedDraft = message.post_id ? draftById.get(message.post_id) : null;
    if (linkedDraft) {
      renderedDraftIds.add(linkedDraft.id);
      items.push({
        type: "draft",
        time: messageTime,
        order: order++,
        html: draftCard(linkedDraft, true),
      });
    }
  });

  drafts.forEach((draft) => {
    if (renderedDraftIds.has(draft.id)) return;
    items.push({ type: "draft", time: timeValue(draft.created_at), order: order++, html: draftCard(draft, true) });
  });

  return items
    .sort((a, b) => a.time - b.time || a.order - b.order)
    .map((item) => item.html)
    .join("");
}

function timeValue(value) {
  if (!value) return Number.POSITIVE_INFINITY;
  const parsed = new Date(value).getTime();
  return Number.isFinite(parsed) ? parsed : Number.POSITIVE_INFINITY;
}

function quickPrompt(text) {
  return `<button class="prompt-chip" data-prompt="${escapeHtml(text)}">${escapeHtml(text)}</button>`;
}

function messageBubble(message) {
  const role = message.role === "user" ? "user" : "mira";
  const label = role === "user" ? "You" : "Mira";
  return `<div class="bubble ${role}"><strong>${label}</strong><div class="markdown">${renderMarkdown(message.content || "")}</div>${role === "mira" ? angleActions(message.content) : ""}</div>`;
}

function angleActions(content = "") {
  const angles = extractAnglesFromMessage(content);
  if (!angles.length) return "";
  return `<div class="angle-actions">
    <div class="angle-actions-label">Turn an angle into a draft</div>
    ${angles.map((angle, index) => `<button class="angle-action" data-angle-prompt="${escapeHtml(angle.prompt)}">
      <span>Draft angle ${index + 1}</span>
      <strong>${escapeHtml(angle.title)}</strong>
    </button>`).join("")}
  </div>`;
}

function draftCard(post, compact = true) {
  const provider = post.generation_provider || "template";
  const publishLabel = ui.integrations?.linkedin?.connected ? "Publish to LinkedIn" : "Copy & open LinkedIn";
  const content = post.content || "";
  const excerpt = escapeHtml(stripMarkdown(content).slice(0, 220));
  return `<article class="draft-card compact" data-post="${post.id}">
    <div class="draft-meta"><span>Draft v${post.version} · ${post.source.replace("_", " ")} · ${escapeHtml(provider)}</span><span>${post.char_count} / 3,000</span></div>
    <div class="draft-summary"><div><strong>Draft ready: ${escapeHtml(post.title || "Untitled draft")}</strong><p>${excerpt}${content.length > 220 ? "…" : ""}</p><button class="read-more" data-draft-review="${post.id}">Open draft workspace</button></div><span class="badge draft">pending review</span></div>
    <div class="draft-actions">
      <button class="button" data-draft-review="${post.id}">Review draft</button>
      <button class="button" data-draft-action="approve" data-id="${post.id}">Approve</button>
      <button class="button secondary" data-draft-action="linkedin" data-id="${post.id}">${publishLabel}</button>
      <button class="button secondary" data-draft-action="edit" data-id="${post.id}">Edit</button>
      <button class="button ghost" data-draft-action="copy" data-id="${post.id}">Copy</button>
      <button class="button ghost" data-draft-action="save" data-id="${post.id}">Save draft</button>
      <button class="button danger" data-draft-action="delete" data-id="${post.id}">Skip</button>
    </div>
  </article>`;
}

function draftReviewModal() {
  if (!ui.reviewDraftId || !ui.state) return "";
  const post = ui.state.posts.find((item) => item.id === ui.reviewDraftId);
  if (!post) return "";
  const provider = post.generation_provider || "template";
  const publishLabel = ui.integrations?.linkedin?.connected ? "Publish to LinkedIn" : "Copy & open LinkedIn";
  return `<div class="modal-backdrop draft-review-backdrop">
    <div class="modal draft-review-modal">
      <div class="draft-review-header">
        <div>
          <div class="eyebrow">Draft workspace</div>
          <h3>${escapeHtml(post.title || "Untitled draft")}</h3>
          <p class="muted small">Draft v${post.version} · ${escapeHtml(post.source?.replace("_", " ") || "chat")} · ${escapeHtml(provider)} · ${post.char_count} / 3,000</p>
        </div>
        <button class="icon-button" id="close-draft-review">Close</button>
      </div>
      <div class="draft-review-body">
        <div class="draft-content markdown">${renderMarkdown(post.content || "")}</div>
        ${qualityReviewPanel(post)}
        ${variantRail(post)}
      </div>
      <div class="draft-actions draft-review-actions">
        <button class="button" data-draft-action="approve" data-id="${post.id}">Approve</button>
        <button class="button secondary" data-draft-action="linkedin" data-id="${post.id}">${publishLabel}</button>
        <button class="button secondary" data-draft-action="edit" data-id="${post.id}">Edit</button>
        <button class="button ghost" data-draft-action="copy" data-id="${post.id}">Copy</button>
        <button class="button ghost" data-draft-action="save" data-id="${post.id}">Save draft</button>
        <button class="button danger" data-draft-action="delete" data-id="${post.id}">Skip</button>
      </div>
    </div>
  </div>`;
}

function qualityReviewPanel(post, compact = false) {
  const review = post.quality_review || buildClientQualityReview(post);
  const checks = review.checks || [];
  const needs = review.needs || checks.filter((check) => !check.passed).map((check) => check.label);
  return `<div class="quality-review ${compact ? "compact" : ""}">
    <div class="quality-head">
      <strong>${escapeHtml(review.label || `Draft readiness: ${review.score || 0}/${review.max_score || checks.length || 5}`)}</strong>
      <span class="badge ${needs.length ? "draft" : "published"}">${needs.length ? "Needs review" : "Ready"}</span>
    </div>
    <div class="quality-checks">
      ${checks.map((check) => `<div class="quality-check ${check.passed ? "passed" : "missing"}"><span>${check.passed ? "✓" : "○"}</span><strong>${escapeHtml(check.label)}</strong>${compact ? "" : `<small>${escapeHtml(check.detail || "")}</small>`}</div>`).join("")}
    </div>
    ${needs.length ? `<div class="quality-needs">Needs improvement: ${escapeHtml(needs.join(", "))}</div>` : `<div class="quality-needs ready">Looks ready for human review.</div>`}
  </div>`;
}

function buildClientQualityReview(post) {
  const content = post.content || "";
  const plain = stripMarkdown(content).toLowerCase();
  const checks = [
    ["Real moment", Boolean((post.sources || []).length), "Uses a Content Bank memory or specific source."],
    ["Clear POV", /i think|i believe|my working principle|the question is|that tension matters|1\//.test(plain), "Has a point of view or useful structure."],
    ["Founder voice", /founder|building|at |i keep|my /.test(plain), "Connects to founder perspective."],
    ["Good CTA", content.includes("?") || /comment|connect|share/.test(plain), "Ends with a question or invitation."],
    ["LinkedIn length", content.length >= 300 && content.length <= 2200, "Readable LinkedIn length."],
  ].map(([label, passed, detail], index) => ({ id: `client_${index}`, label, passed, detail }));
  const score = checks.filter((check) => check.passed).length;
  return {
    score,
    max_score: checks.length,
    label: `Draft readiness: ${score}/${checks.length}`,
    needs: checks.filter((check) => !check.passed).map((check) => check.label),
    checks,
  };
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
  const completedCount = [hasMemory, hasDraft || hasLibrary, hasLibrary, hasScheduled].filter(Boolean).length;
  const nextAction = !hasMemory
    ? "Start by adding one real memory."
    : !(hasDraft || hasLibrary)
      ? "Ask Mira to draft from the latest memory."
      : !hasScheduled
        ? "Open the draft workspace and approve, save, copy, or skip."
        : "Check Library, Calendar, and Progress for the final state.";
  const items = [
    ["Save one real moment to Content Bank", hasMemory],
    ["Generate one review-ready draft", hasDraft || hasLibrary],
    ["Edit, copy, save, approve, or skip the draft", hasLibrary],
    ["Check Library, Calendar, and Progress states", hasScheduled],
  ];
  return `<div class="card workflow-card">
    <div class="card-head"><div><h3>Golden path test</h3><p class="muted small">Use this as the main QA path: onboarding → Content Bank → Mira → draft → review → Library/Calendar.</p></div><span class="badge ${completedCount === items.length ? "published" : hasMemory ? "scheduled" : "draft"}">${completedCount}/${items.length} done</span></div>
    <div class="golden-progress"><span style="width:${Math.round((completedCount / items.length) * 100)}%"></span></div>
    <div class="checklist">${items.map(([label, done]) => `<div class="check ${done ? "done" : ""}"><span>${done ? "✓" : "○"}</span>${label}</div>`).join("")}</div>
    <div class="next-action"><strong>Next best action</strong><span>${escapeHtml(nextAction)}</span></div>
    <div class="workflow-actions">
      <button class="button" data-tab="bank">${hasMemory ? "Add another memory" : "Add first memory"}</button>
      <button class="button secondary" data-action="sample-draft" ${hasMemory ? "" : "disabled"}>Draft from latest memory</button>
      <button class="button ghost" data-tab="bank">Open Content Bank</button>
    </div>
    <p class="muted small">Mira can chat, suggest angles, draft, revise, and move posts into Library/Calendar. Progress is available from the plus menu. LinkedIn has a manual copy/open fallback until OAuth is fully connected.</p>
  </div>`;
}

function renderBank() {
  return `<section class="page">
    <div class="eyebrow">Personal memory</div><h1>Content Bank</h1>
    <p class="lead">Capture one useful moment in under a minute. Then keep it useful: edit, mark used, raise priority, or turn it into a draft.</p>
    ${ui.notice ? `<div class="notice">${escapeHtml(ui.notice)}</div>` : ""}
    ${bankSummary()}
    ${dailyCheckinPrompts()}
    <div class="card">
      <h3>What happened today?</h3>
      <p class="muted small">Good entries are concrete: who/what happened, why it mattered, and what it changed in your thinking.</p>
      <div class="template-grid">${memoryTemplates.map(([id, icon, label]) => `<button class="template ${ui.selectedCategory === id ? "active" : ""}" data-category="${id}"><span>${icon}</span>${label}</button>`).join("")}</div>
      <form id="bank-form"><textarea id="bank-text" placeholder="Example: We launched our first founder test today. The biggest lesson was that workflow ownership matters more than another writing prompt." required minlength="3"></textarea><button class="button" style="margin-top:10px">Save to Content Bank</button></form>
    </div>
    <div class="list" style="margin-top:18px">
      ${ui.state.content_bank.length ? ui.state.content_bank.map(memoryCard).join("") : '<div class="empty">Your Content Bank is empty. Add the first moment above.</div>'}
    </div>
  </section>`;
}

function dailyCheckinPrompts() {
  return `<div class="checkin-prompts">
    <div class="checkin-prompt"><span>01</span><strong>What happened?</strong><p>Name the real meeting, decision, event, or constraint.</p></div>
    <div class="checkin-prompt"><span>02</span><strong>Why did it matter?</strong><p>Capture the founder lesson, tension, or change in thinking.</p></div>
    <div class="checkin-prompt"><span>03</span><strong>Could this be a post?</strong><p>Mark strong entries high-potential and draft from them later.</p></div>
  </div>`;
}

function bankSummary() {
  const bank = ui.state.content_bank || [];
  const fresh = bank.filter((entry) => entry.freshness === "fresh").length;
  const used = bank.filter((entry) => entry.freshness === "used").length;
  const high = bank.filter((entry) => entry.content_potential === "high").length;
  return `<div class="memory-summary">
    <div><strong>${bank.length}</strong><span>Total entries</span></div>
    <div><strong>${fresh}</strong><span>Fresh</span></div>
    <div><strong>${used}</strong><span>Used</span></div>
    <div><strong>${high}</strong><span>High potential</span></div>
  </div>`;
}

function memoryCard(entry) {
  const category = entry.category || "insights";
  const freshness = entry.freshness || "fresh";
  const potential = entry.content_potential || "medium";
  const freshnessAction = freshness === "used" ? ["fresh", "Mark fresh"] : ["used", "Mark used"];
  return `<div class="list-item memory-card" data-memory-id="${escapeHtml(entry.id)}">
    <div class="list-top">
      <div><strong>${escapeHtml(memoryCategoryLabel(category))}</strong><div class="small muted">${escapeHtml(category)} · ${entry.created_at ? escapeHtml(new Date(entry.created_at).toLocaleDateString()) : "Saved memory"}</div></div>
      <div class="badge-row"><span class="badge ${freshness === "used" ? "scheduled" : freshness === "archived" ? "deleted" : "published"}">${escapeHtml(freshness)}</span><span class="badge ${potential === "high" ? "published" : "draft"}">${escapeHtml(potential)} potential</span></div>
    </div>
    <p>${escapeHtml(entry.raw_text)}</p>
    <div class="inline-actions">
      <button class="button secondary" data-prompt="Draft a LinkedIn post from this Content Bank memory: ${escapeHtml(entry.raw_text)}">Draft from this memory</button>
      <button class="button ghost" data-memory-status="${escapeHtml(freshnessAction[0])}" data-id="${escapeHtml(entry.id)}">${freshnessAction[1]}</button>
      ${potential === "high" ? "" : `<button class="button ghost" data-memory-potential="high" data-id="${escapeHtml(entry.id)}">Mark high potential</button>`}
      <button class="button danger" data-memory-delete="${escapeHtml(entry.id)}">Delete</button>
    </div>
    <details class="memory-edit">
      <summary>Edit memory</summary>
      <form data-memory-edit="${escapeHtml(entry.id)}" class="memory-edit-form">
        <textarea name="raw_text" required minlength="3">${escapeHtml(entry.raw_text)}</textarea>
        <div class="form-grid compact">
          <div class="field"><label>Category</label><select name="category">${selectOptions(memoryTemplates.map(([id, _icon, label]) => [id, label]), category)}</select></div>
          <div class="field"><label>Status</label><select name="freshness">${selectOptions(freshnessOptions, freshness)}</select></div>
          <div class="field"><label>Potential</label><select name="content_potential">${selectOptions(potentialOptions, potential)}</select></div>
          <div class="field memory-save"><button class="button">Save changes</button></div>
        </div>
      </form>
    </details>
  </div>`;
}

function memoryCategoryLabel(category) {
  return memoryTemplates.find(([id]) => id === category)?.[2] || category;
}

function selectOptions(options, selected) {
  return options.map(([value, label]) => `<option value="${escapeHtml(value)}" ${value === selected ? "selected" : ""}>${escapeHtml(label)}</option>`).join("");
}

function formatPostDate(value) {
  return value ? new Date(value).toLocaleString() : "No time set";
}

function scheduleSummary(post) {
  if (post.status === "published") return post.published_at ? `Posted ${formatPostDate(post.published_at)}` : "Marked as posted";
  if (post.status === "scheduled") return `${post.schedule_label || "Scheduled"} · ${formatPostDate(post.scheduled_at)}`;
  return "Not scheduled yet";
}

function defaultCustomScheduleValue() {
  const date = new Date();
  date.setDate(date.getDate() + 1);
  date.setHours(9, 0, 0, 0);
  const pad = (value) => String(value).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

function renderLibrary() {
  const posts = filteredLibraryPosts();
  return `<section class="page"><div class="eyebrow">Content pipeline</div><h1>Library</h1><p class="lead">Every draft, scheduled post, and published post stays visible here.</p>
    ${libraryControls()}
    <div class="list">${posts.length ? posts.map(libraryItem).join("") : libraryEmptyState()}</div>
  </section>`;
}

function libraryControls() {
  const filters = [
    ["all", "All"], ["draft", "Drafts"], ["saved", "Saved"], ["scheduled", "Scheduled"],
    ["published", "Published"], ["skipped", "Skipped"],
  ];
  return `<div class="library-tools">
    <div class="library-filters">
      ${filters.map(([id, label]) => `<button class="filter-chip ${ui.libraryFilter === id ? "active" : ""}" data-library-filter="${id}">${label}<span>${libraryFilterCount(id)}</span></button>`).join("")}
    </div>
    <input class="input library-search" id="library-search" value="${escapeHtml(ui.librarySearch)}" placeholder="Search title or draft text…" />
  </div>`;
}

function libraryFilterCount(filter) {
  return libraryPostsForFilter(filter).length;
}

function libraryPostsForFilter(filter) {
  const posts = ui.state.posts || [];
  if (filter === "all") return posts.filter((post) => post.status !== "deleted");
  if (filter === "draft") return posts.filter((post) => post.status === "pending");
  if (filter === "saved") return posts.filter((post) => ["saved", "draft"].includes(post.status));
  if (filter === "scheduled") return posts.filter((post) => post.status === "scheduled");
  if (filter === "published") return posts.filter((post) => post.status === "published");
  if (filter === "skipped") return posts.filter((post) => post.status === "deleted");
  return posts.filter((post) => post.status !== "deleted");
}

function filteredLibraryPosts() {
  const query = ui.librarySearch.trim().toLowerCase();
  return libraryPostsForFilter(ui.libraryFilter).filter((post) => {
    if (!query) return true;
    return [post.title, post.content, post.status, post.schedule_label]
      .filter(Boolean)
      .some((value) => String(value).toLowerCase().includes(query));
  });
}

function libraryEmptyState() {
  if (ui.librarySearch.trim()) return '<div class="empty">No Library items match that search.</div>';
  if (ui.libraryFilter !== "all") return '<div class="empty">No posts in this status yet.</div>';
  return '<div class="empty">No posts yet. Draft one with Mira.</div>';
}

function libraryItem(post) {
  const excerpt = stripMarkdown(post.content).slice(0, 220);
  const expanded = ui.expandedLibraryPosts.has(post.id);
  return `<div class="list-item">
    <div class="list-top"><div><strong>${escapeHtml(post.title)}</strong><p>${escapeHtml(excerpt)}${post.content.length > 220 ? "…" : ""}</p><button class="read-more" data-library-expand="${post.id}">${expanded ? "Hide full draft" : "Show full draft"}</button></div><span class="badge ${post.status}">${post.status}</span></div>
    <div class="small muted" style="margin-top:10px">${post.char_count} characters · v${post.version} · ${escapeHtml(post.generation_provider || "template")} · ${escapeHtml(scheduleSummary(post))}</div>
    ${expanded ? `<div class="library-full-draft draft-content markdown">${renderMarkdown(post.content || "")}</div>` : ""}
    ${qualityReviewPanel(post, true)}
    <div class="inline-actions">
      <button class="button" data-draft-review="${post.id}">Open draft workspace</button>
      ${["pending", "draft", "saved"].includes(post.status) ? `<button class="button secondary" data-draft-action="edit" data-id="${post.id}">Edit</button><button class="button" data-draft-action="approve" data-id="${post.id}">Approve</button>` : ""}
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
    cells.push(`<div class="day ${matches.length ? "has-post" : ""}"><strong>${day}</strong>${matches.map((post) => `<div class="small" style="margin-top:8px"><span class="dot ${post.status}"></span>${escapeHtml(post.schedule_label || post.status)}</div>`).join("")}</div>`);
  }
  return `<section class="page"><div class="eyebrow">Schedule</div><h1>${now.toLocaleString("en", { month: "long" })} ${year}</h1><p class="lead">Green marks published content. Purple marks posts Mira has scheduled.</p>
    <div class="card calendar-card"><div class="calendar">${["Sun","Mon","Tue","Wed","Thu","Fri","Sat"].map((day) => `<div class="day-label">${day}</div>`).join("")}${cells.join("")}</div></div>
    <div class="list" style="margin-top:18px">${scheduled.length ? scheduled.map((post) => `<div class="list-item"><div class="list-top"><strong>${escapeHtml(post.title)}</strong><span class="badge ${post.status}">${post.status}</span></div><p>${escapeHtml(scheduleSummary(post))}</p></div>`).join("") : '<div class="empty">Nothing scheduled yet. Approve a draft to place it here.</div>'}</div>
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

function productReadinessPanel() {
  const hasProfile = Boolean(ui.state.profile?.company_name && ui.state.profile?.company_description);
  const hasMemory = (ui.state.content_bank || []).length > 0;
  const hasDraft = (ui.state.posts || []).some((post) => post.status !== "deleted");
  const linkedin = ui.integrations?.linkedin;
  const checks = [
    ["Authentication", ui.state.auth?.authenticated || ui.demoMode, ui.state.auth?.authenticated ? "Signed in workspace" : "Public demo mode"],
    ["Onboarding", ui.state.onboarding_completed, ui.state.onboarding_completed ? "Completed" : "Needs setup"],
    ["Profile context", hasProfile, hasProfile ? "Company context saved" : "Add company description"],
    ["Content Bank", hasMemory, hasMemory ? `${ui.state.content_bank.length} entries` : "Add first memory"],
    ["Draft workflow", hasDraft, hasDraft ? "Library has drafts/posts" : "Create first draft"],
    ["LinkedIn", linkedin?.connected || linkedin?.configured, linkedin?.connected ? "Connected" : linkedin?.configured ? "OAuth configured, needs redirect/app access" : "Manual fallback only"],
  ];
  const readyCount = checks.filter(([, done]) => done).length;
  return `<div class="card readiness-card">
    <div class="card-head"><div><h3>MVP readiness checklist</h3><p class="muted small">This is the honest staging status testers should expect.</p></div><span class="badge ${readyCount >= 5 ? "published" : "draft"}">${readyCount}/${checks.length}</span></div>
    <div class="readiness-grid">
      ${checks.map(([label, done, detail]) => `<div class="readiness-item ${done ? "done" : ""}"><strong>${done ? "✓" : "○"} ${escapeHtml(label)}</strong><span>${escapeHtml(detail)}</span></div>`).join("")}
    </div>
  </div>`;
}

function renderSettings() {
  const p = ui.state.profile;
  const anthropic = ui.integrations?.anthropic;
  const linkedin = ui.integrations?.linkedin;
  const payloadcms = ui.integrations?.payloadcms;
  const database = ui.integrations?.database;
  const linkedinBadge = linkedin?.connected ? "Connected" : linkedin?.configured ? "OAuth configured" : "Fallback ready";
  const linkedinClass = linkedin?.connected ? "published" : linkedin?.configured ? "scheduled" : "draft";
  const databaseIsPostgres = database?.storage === "postgres";
  return `<section class="page"><div class="eyebrow">Personalization</div><h1>Settings</h1><p class="lead">These details are loaded fresh whenever Mira creates a draft.</p>
    ${productReadinessPanel()}
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
    <div class="card" style="margin-top:16px"><div class="card-head"><h3>Database storage</h3><span class="badge ${databaseIsPostgres ? "published" : "draft"}">${databaseIsPostgres ? "Postgres active" : "File storage"}</span></div><p class="muted">${databaseIsPostgres ? "Signup, login, and workspace state are using the configured Render Postgres database." : "This staging app is still using MVP file-backed storage. Set USE_DATABASE_STORAGE=true and DATABASE_URL in Render to switch to Postgres."}</p></div>
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
  document.querySelectorAll("[data-angle-prompt]").forEach((button) => {
    button.onclick = () => submitPrompt(button.dataset.anglePrompt);
  });
  document.querySelectorAll("[data-category]").forEach((button) => {
    button.onclick = () => { ui.selectedCategory = button.dataset.category; render(); };
  });
  document.querySelectorAll("[data-library-filter]").forEach((button) => {
    button.onclick = () => { ui.libraryFilter = button.dataset.libraryFilter; render(); };
  });
  document.querySelector("#library-search")?.addEventListener("input", (event) => {
    ui.librarySearch = event.target.value;
    render();
    document.querySelector("#library-search")?.focus();
  });
  document.querySelectorAll("[data-draft-action]").forEach((button) => {
    button.onclick = () => handleDraftAction(button.dataset.draftAction, button.dataset.id, button.dataset.variantId);
  });
  document.querySelectorAll("[data-draft-review]").forEach((button) => {
    button.onclick = () => reviewDraft(button.dataset.draftReview);
  });
  document.querySelectorAll("[data-library-expand]").forEach((button) => {
    button.onclick = () => toggleLibraryPost(button.dataset.libraryExpand);
  });
  document.querySelectorAll("[data-modal-close]").forEach((button) => {
    button.onclick = () => { ui.modal = null; render(); };
  });
  document.querySelectorAll("[data-linkedin-defer]").forEach((button) => {
    button.onclick = deferLinkedInTracking;
  });
  document.querySelectorAll("[data-linkedin-track]").forEach((button) => {
    button.onclick = () => trackLinkedInUrl(button.dataset.linkedinTrack);
  });
  document.querySelector("#close-draft-review")?.addEventListener("click", () => {
    ui.reviewDraftId = null;
    render();
  });
  document.querySelectorAll("[data-memory-status]").forEach((button) => {
    button.onclick = () => updateMemory(button.dataset.id, { freshness: button.dataset.memoryStatus });
  });
  document.querySelectorAll("[data-memory-potential]").forEach((button) => {
    button.onclick = () => updateMemory(button.dataset.id, { content_potential: button.dataset.memoryPotential });
  });
  document.querySelectorAll("[data-memory-delete]").forEach((button) => {
    button.onclick = () => deleteMemory(button.dataset.memoryDelete);
  });
  document.querySelectorAll("[data-memory-edit]").forEach((form) => {
    form.onsubmit = saveMemory;
  });
}

function reviewDraft(id) {
  ui.reviewDraftId = id;
  render();
}

function toggleLibraryPost(id) {
  if (ui.expandedLibraryPosts.has(id)) {
    ui.expandedLibraryPosts.delete(id);
  } else {
    ui.expandedLibraryPosts.add(id);
  }
  render();
}

async function refresh() {
  const [state, integrations] = await Promise.all([
    api("/api/state"),
    api("/api/integrations/status").catch(() => null),
  ]);
  if (ui.auth && state.auth && !state.auth.authenticated) {
    const sessionStillValid = await validateSession();
    if (!sessionStillValid) {
      localStorage.removeItem("blidx_auth");
      ui.auth = null;
      ui.demoMode = false;
      localStorage.removeItem("blidx_demo");
      showToast("Session expired. Please log in again.");
      render();
      return;
    }
    state.auth = { authenticated: true, user_id: ui.auth.user_id };
  }
  ui.state = state;
  ui.integrations = integrations;
  render();
}

async function validateSession() {
  try {
    await api("/auth/me");
    return true;
  } catch (error) {
    return false;
  }
}

async function submitAuth(event) {
  event.preventDefault();
  const form = new FormData(event.currentTarget);
  const payload = Object.fromEntries(form.entries());
  const path = ui.authMode === "signup" ? "/auth/register" : "/auth/login";
  try {
    ui.authError = "";
    ui.authSubmitting = true;
    render();
    const auth = await api(path, { method: "POST", body: JSON.stringify(payload) });
    ui.auth = auth;
    ui.demoMode = false;
    localStorage.setItem("blidx_auth", JSON.stringify(auth));
    localStorage.removeItem("blidx_demo");
    await refresh();
    showToast(ui.authMode === "signup" ? "Workspace created" : "Logged in");
  } catch (error) {
    ui.authError = error.message;
    showToast(error.message);
  } finally {
    ui.authSubmitting = false;
    render();
  }
}

async function completeOnboarding(event) {
  event.preventDefault();
  const form = new FormData(event.currentTarget);
  const payload = Object.fromEntries(form.entries());
  payload.audience = payload.audience.split(",").map((v) => v.trim()).filter(Boolean);
  payload.expertise = payload.expertise.split(",").map((v) => v.trim()).filter(Boolean);
  payload.content_types = (payload.content_types || "").split(",").map((v) => v.trim()).filter(Boolean);
  payload.writing_samples = (payload.writing_samples || "").split(/\n\s*---\s*\n/).map((v) => v.trim()).filter(Boolean);
  payload.avoided_phrases = (payload.avoided_phrases || "").split(",").map((v) => v.trim()).filter(Boolean);
  if (!payload.content_types.length) payload.content_types = ["Industry insights", "Personal stories", "Lessons learned"];
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
  ui.pendingMessages = [{
    id: `pending-${Date.now()}`,
    role: "user",
    content: message,
    created_at: new Date().toISOString(),
    kind: "pending",
  }];
  requestChatScroll();
  ui.loading = true; render();
  try {
    const result = await api("/api/chat/message", { method: "POST", body: JSON.stringify({ message }) });
    ui.state = result.state;
    ui.pendingMessages = [];
    ui.loading = false;
    requestChatScroll();
    await refresh();
  } catch (error) {
    ui.pendingMessages = [];
    ui.loading = false;
    showToast(error.message);
  }
}

async function createSampleDraft() {
  ui.tab = "chat";
  requestChatScroll();
  ui.loading = true; render();
  try {
    const latest = ui.state.content_bank[0]?.raw_text;
    const topic = latest || `${ui.state.profile.company_name || "my company"} founder insight from this week`;
    await api("/api/chat/message", {
      method: "POST",
      body: JSON.stringify({ message: `Draft a post about ${topic}` }),
    });
    ui.loading = false;
    requestChatScroll();
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

async function updateMemory(id, updates) {
  try {
    await api(`/api/content-bank/${id}`, { method: "PUT", body: JSON.stringify(updates) });
    ui.notice = "Content Bank entry updated.";
    await refresh();
    ui.notice = "Content Bank entry updated."; render();
  } catch (error) {
    showToast(error.message);
  }
}

async function saveMemory(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const payload = Object.fromEntries(new FormData(form).entries());
  await updateMemory(form.dataset.memoryEdit, payload);
}

async function deleteMemory(id) {
  if (!window.confirm("Delete this Content Bank entry?")) return;
  try {
    await api(`/api/content-bank/${id}`, { method: "DELETE" });
    ui.notice = "Content Bank entry deleted.";
    await refresh();
    ui.notice = "Content Bank entry deleted."; render();
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
    showScheduleModal(id);
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
    api(`/api/drafts/${id}/${action}`, { method: "POST" })
      .then(() => { ui.reviewDraftId = null; return refresh(); })
      .then(() => showToast(action === "save" ? "Saved to Library" : "Draft skipped"));
  }
}

function quickEditButton(label) {
  return `<button class="prompt-chip" type="button" data-quick-edit="${escapeHtml(label)}">${escapeHtml(label)}</button>`;
}

function showScheduleModal(id) {
  ui.modal = `<div class="modal-backdrop"><div class="modal"><h3>When should this post move forward?</h3><p class="muted">Choose a testable scheduling state. For real LinkedIn publishing today, keep using Copy & open LinkedIn.</p>
    <div class="schedule-options">
      ${scheduleButton("now", "Post now", "Mark it as published inside Blidx.")}
      ${scheduleButton("later_today", "Later today", "Schedule for 5:30 PM in the profile timezone.")}
      ${scheduleButton("tomorrow_morning", "Tomorrow morning", "Schedule for 9:00 AM tomorrow.")}
      ${scheduleButton("best_time", "Best time this week", "Mira chooses the next Tue/Thu 10:30 AM slot.")}
    </div>
    <div class="custom-schedule">
      <label>Pick date/time</label>
      <input class="input" id="custom-scheduled-at" type="datetime-local" value="${defaultCustomScheduleValue()}" />
      <button class="button secondary" id="custom-schedule">Schedule custom time</button>
    </div>
    <div class="modal-actions"><button class="button ghost" id="cancel-modal">Cancel</button></div>
  </div></div>`;
  render();
  document.querySelector("#cancel-modal").onclick = () => { ui.modal = null; render(); };
  document.querySelectorAll("[data-schedule]").forEach((button) => {
    button.onclick = () => approveDraft(id, button.dataset.schedule);
  });
  document.querySelector("#custom-schedule").onclick = () => {
    const value = document.querySelector("#custom-scheduled-at")?.value;
    approveDraft(id, "custom", value ? new Date(value).toISOString() : null);
  };
}

function scheduleButton(type, title, description) {
  return `<button class="schedule-option" data-schedule="${type}">
    <strong>${title}</strong>
    <span>${description}</span>
  </button>`;
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

async function approveDraft(id, schedule_type, scheduled_at = null) {
  await api(`/api/drafts/${id}/approve`, { method: "POST", body: JSON.stringify({ schedule_type, scheduled_at }) });
  ui.modal = null;
  ui.reviewDraftId = null;
  await refresh();
  showToast(schedule_type === "now" ? "Published locally" : "Scheduled and added to Calendar");
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
  ui.modal = `<div class="modal-backdrop"><div class="modal"><h3>Did you post it on LinkedIn?</h3><p class="muted">After you paste and publish the draft on LinkedIn, add the post URL here so Blidx can mark it as published. If you have not posted it yet, choose Not yet and the draft will stay available in Blidx.</p><input class="input" id="linkedin-url" placeholder="https://www.linkedin.com/feed/update/..." /><div class="modal-actions"><button class="button ghost" data-linkedin-defer="true">Not yet</button><button class="button" data-linkedin-track="${escapeHtml(id)}">Mark posted</button></div></div></div>`;
  render();
}

function deferLinkedInTracking() {
  ui.modal = null;
  render();
  showToast("No problem. Draft kept in Blidx for later.");
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

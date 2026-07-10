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
  toastAction: null,
  toastTimer: null,
  loading: false,
  scrollChatAfterRender: false,
  quickActionsOpen: false,
  chatGuideOpen: false,
  calendarOffset: 0,
  proactiveDismissed: false,
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
    qa: "QA status",
    settings: "Settings",
  }[ui.tab] || "Content workspace";
}

function quickActionsMenu() {
  if (!ui.quickActionsOpen) return "";
  return `<div class="quick-actions-menu">
    <button data-action="qa-draft"><span>Draft</span><strong>Draft a post</strong><small>Start a Mira draft from any idea.</small></button>
    <button data-action="qa-checkin"><span>Check-in</span><strong>Daily check-in</strong><small>Capture a fresh Content Bank moment.</small></button>
    <button data-action="qa-progress"><span>Progress</span><strong>Performance & progress</strong><small>Open the lightweight Analytics view.</small></button>
    <button data-action="qa-status"><span>QA</span><strong>Test checklist</strong><small>See what is testable and what is still limited.</small></button>
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
    ${ui.toast ? `<div class="toast" role="status" aria-live="polite">${escapeHtml(ui.toast)}${ui.toastAction ? `<button class="toast-action" id="toast-action">${escapeHtml(ui.toastAction.label)}</button>` : ""}</div>` : ""}
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
      <form id="auth-form" data-testid="auth-form">
        ${isSignup ? '<div class="field"><label>Name</label><input class="input" name="user_name" placeholder="Jae" /></div>' : ""}
        <div class="field"><label>Email</label><input class="input" name="email" type="email" required placeholder="you@example.com" /></div>
        <div class="field"><label>Password</label><input class="input" name="password" type="password" required minlength="${isSignup ? 8 : 1}" placeholder="••••••••" /></div>
        <button class="button" data-testid="auth-submit" style="width:100%" ${ui.authSubmitting ? "disabled" : ""}>${ui.authSubmitting ? "Checking..." : isSignup ? "Create account" : "Log in"}</button>
      </form>
      <button class="button ghost auth-switch" id="toggle-auth" data-testid="auth-toggle">${isSignup ? "Already have an account? Log in" : "New here? Create account"}</button>
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
      const changed = ui.tab !== button.dataset.tab;
      ui.tab = button.dataset.tab;
      ui.modal = null;
      ui.quickActionsOpen = false;
      render();
      if (changed) window.scrollTo(0, 0);
    };
  });
  document.querySelectorAll('[data-action="new-draft"]').forEach((button) => {
    button.onclick = startDraft;
  });
  document.querySelectorAll('[data-action="quick-actions"]').forEach((button) => {
    button.onclick = (event) => {
      event.stopPropagation();
      ui.quickActionsOpen = !ui.quickActionsOpen;
      render();
    };
  });
  if (ui.quickActionsOpen) {
    document.addEventListener("click", closeQuickActionsOnOutsideClick);
    document.addEventListener("keydown", closeQuickActionsOnEscape);
  }
  document.querySelectorAll('[data-action="qa-draft"]').forEach((button) => {
    button.onclick = startDraft;
  });
  document.querySelectorAll('[data-action="qa-checkin"]').forEach((button) => {
    button.onclick = () => {
      ui.quickActionsOpen = false;
      ui.tab = "bank";
      render();
      window.scrollTo(0, 0);
      setTimeout(() => document.querySelector("#bank-text")?.focus(), 0);
    };
  });
  document.querySelectorAll('[data-action="qa-progress"]').forEach((button) => {
    button.onclick = () => {
      ui.quickActionsOpen = false;
      ui.tab = "analytics";
      render();
      window.scrollTo(0, 0);
    };
  });
  document.querySelectorAll('[data-action="qa-status"]').forEach((button) => {
    button.onclick = () => {
      ui.quickActionsOpen = false;
      ui.tab = "qa";
      render();
      window.scrollTo(0, 0);
    };
  });
  document.querySelectorAll('[data-action="logout"]').forEach((button) => {
    button.onclick = logout;
  });
  document.querySelectorAll('[data-action="sample-draft"]').forEach((button) => {
    button.onclick = createSampleDraft;
  });
  const toastAction = document.querySelector("#toast-action");
  if (toastAction) {
    toastAction.onclick = () => {
      const run = ui.toastAction?.onAction;
      clearTimeout(ui.toastTimer);
      ui.toast = "";
      ui.toastAction = null;
      render();
      run?.();
    };
  }
  bindModalDismissal();
}

function bindModalDismissal() {
  const backdrops = document.querySelectorAll(".modal-backdrop");
  if (!backdrops.length) {
    document.removeEventListener("keydown", closeModalOnEscape);
    return;
  }
  document.addEventListener("keydown", closeModalOnEscape);
  backdrops.forEach((backdrop) => {
    backdrop.addEventListener("mousedown", (event) => {
      if (event.target === backdrop) closeAnyModal();
    });
  });
  const top = backdrops[backdrops.length - 1];
  if (!top.contains(document.activeElement)) {
    const target = top.querySelector("textarea, input, select")
      || top.querySelector("button:not([data-modal-close])")
      || top.querySelector("button");
    target?.focus();
  }
}

function closeModalOnEscape(event) {
  if (event.key === "Escape") closeAnyModal();
}

function closeAnyModal() {
  if (ui.modal) ui.modal = null;
  else if (ui.reviewDraftId) ui.reviewDraftId = null;
  else return;
  render();
}

function closeQuickActionsOnOutsideClick(event) {
  if (event.target.closest(".quick-actions-wrap")) return;
  closeQuickActions();
}

function closeQuickActionsOnEscape(event) {
  if (event.key === "Escape") closeQuickActions();
}

function closeQuickActions() {
  document.removeEventListener("click", closeQuickActionsOnOutsideClick);
  document.removeEventListener("keydown", closeQuickActionsOnEscape);
  if (!ui.quickActionsOpen) return;
  ui.quickActionsOpen = false;
  render();
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
  const views = { chat: renderChat, bank: renderBank, library: renderLibrary, calendar: renderCalendar, analytics: renderAnalytics, qa: renderQA, settings: renderSettings };
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
    <form class="onboarding-form" id="onboarding-form" data-testid="onboarding-form">
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
        <div class="onboarding-actions"><button class="button" data-testid="complete-onboarding">Complete setup</button><button type="button" class="button ghost" id="skip-onboarding">Use starter context for now</button></div>
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
  const hasActivity = ui.state.content_bank.length > 0
    || ui.state.posts.some((post) => post.status !== "deleted")
    || (ui.state.messages?.length || 0) > 0;
  const weekCards = `<div class="grid">
        <div class="card"><div class="card-head"><h3>This week</h3><span class="badge ${published >= goal ? "published" : "pending"}">${published}/${goal} posts</span></div><div class="metric">${Math.min(Math.round((published / goal) * 100), 100)}%</div><div class="progress"><span style="width:${Math.min((published / goal) * 100, 100)}%"></span></div><div class="muted small">Based on your ${escapeHtml(profile.posting_frequency.replaceAll("_", " "))} goal.</div></div>
        <div class="card"><div class="card-head"><h3>Content Bank</h3><span class="badge published">${ui.state.content_bank.length} entries</span></div><p class="muted">Your latest real-world context makes every draft more personal.</p><button class="button secondary" data-tab="bank">Add today’s insight</button></div>
      </div>`;
  const { completedCount, total } = goldenPathStats();
  const intro = hasActivity
    ? `${workflowProgress()}
      <details class="chat-guide" id="chat-guide" ${ui.chatGuideOpen ? "open" : ""}>
        <summary>Workflow guide · ${completedCount}/${total} steps done · ${published}/${goal} posts this week</summary>
        <div class="chat-guide-body">${miraBrief()}${workflowGuide()}${weekCards}</div>
      </details>`
    : `<p class="lead">Mira now follows a clearer content workflow: capture a real moment, choose an angle, then create a review-ready LinkedIn draft.</p>
      ${workflowProgress()}
      ${miraBrief()}
      ${workflowGuide()}
      ${weekCards}`;
  return `
    <section class="page">
      <div class="eyebrow">Your content workdesk</div>
      <h1>Good ${new Date().getHours() < 12 ? "morning" : "afternoon"}, ${escapeHtml(profile.first_name)}.</h1>
      ${intro}
      <div class="chat-stream" data-testid="chat-stream" style="margin-top:18px">
        ${timeline}
        ${proactiveBubble()}
        ${ui.loading ? '<div class="bubble mira typing"><strong>Mira</strong><br>Thinking through the angle…</div>' : ""}
      </div>
      <div class="composer">
        <form class="composer-box" id="chat-form">
          <input class="input" id="chat-message" data-testid="chat-message" placeholder="Try: This week I noticed..." required minlength="2" />
          <button class="button" data-testid="chat-send" ${ui.loading ? "disabled" : ""}>${ui.loading ? "Working…" : "Send"}</button>
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

function proactiveBubble() {
  const brief = ui.state.proactive_brief;
  if (!brief || ui.proactiveDismissed || ui.loading) return "";
  const action = brief.action === "review_draft"
    ? `<button class="button" data-testid="proactive-action" data-draft-review="${brief.post_id}">Open draft workspace</button>`
    : brief.action === "draft_latest_memory"
      ? '<button class="button" data-testid="proactive-action" data-prompt="Draft from my latest memory">Draft it</button>'
      : brief.action === "draft_repurpose"
        ? `<button class="button" data-testid="proactive-action" data-prompt="${escapeHtml(`Draft a fresh take on "${brief.topic}"`)}">Draft a fresh take</button>`
        : "";
  return `<div class="bubble mira proactive" data-testid="proactive-brief"><strong>Mira</strong><br>${escapeHtml(brief.message)}
    <div class="proactive-actions">${action}<button class="button ghost" data-proactive-dismiss>Not now</button></div>
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
    ${angles.map((angle, index) => `<button class="angle-action" data-testid="angle-action" data-angle-prompt="${escapeHtml(angle.prompt)}">
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
  return `<article class="draft-card compact" data-testid="draft-card" data-post="${post.id}">
    <div class="draft-meta"><span>Draft v${post.version} · ${post.source.replace("_", " ")} · ${escapeHtml(provider)}</span><span>${post.char_count} / 3,000</span></div>
    <div class="draft-summary"><div><strong>Draft ready: ${escapeHtml(post.title || "Untitled draft")}</strong><p>${excerpt}${content.length > 220 ? "…" : ""}</p><button class="read-more" data-testid="open-draft-workspace" data-draft-review="${post.id}">Open draft workspace</button></div><span class="badge draft">pending review</span></div>
    <div class="draft-actions">
      <button class="button" data-testid="review-draft" data-draft-review="${post.id}">Review & edit</button>
      <button class="button" data-testid="approve-draft" data-draft-action="approve" data-id="${post.id}">Approve</button>
      <button class="button secondary" data-testid="linkedin-handoff" data-draft-action="linkedin" data-id="${post.id}">${publishLabel}</button>
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
    <div class="modal draft-review-modal" data-testid="draft-review-modal">
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
        <button class="button" data-testid="approve-draft" data-draft-action="approve" data-id="${post.id}">Approve</button>
        <button class="button secondary" data-testid="linkedin-handoff" data-draft-action="linkedin" data-id="${post.id}">${publishLabel}</button>
        <button class="button secondary" data-draft-action="edit" data-id="${post.id}">Edit</button>
        <button class="button ghost" data-draft-action="copy" data-id="${post.id}">Copy</button>
        <button class="button ghost" data-testid="save-draft" data-draft-action="save" data-id="${post.id}">Save draft</button>
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
  const robotic = [
    "in today's fast-paced",
    "game changer",
    "unlock",
    "not just",
    "delve into",
    "revolutionize",
    "transform the way",
    "leverage ai",
  ].some((phrase) => plain.includes(phrase));
  const checks = [
    ["Real moment", Boolean((post.sources || []).length), "Uses a Content Bank memory or specific source."],
    ["Clear POV", /i think|i believe|my working principle|the question is|that tension matters|1\//.test(plain), "Has a point of view or useful structure."],
    ["Founder voice", /founder|building|at |i keep|my /.test(plain), "Connects to founder perspective."],
    ["Good CTA", content.includes("?") || /comment|connect|share/.test(plain), "Ends with a question or invitation."],
    ["LinkedIn length", content.length >= 300 && content.length <= 2200, "Readable LinkedIn length."],
    ["Human voice", !robotic && !content.startsWith("I keep thinking about"), "Avoids common AI phrasing and repeated openings."],
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

function goldenPathStats() {
  const hasMemory = ui.state.content_bank.length > 0;
  const hasDraft = ui.state.posts.some((post) => post.status === "pending");
  const hasLibrary = ui.state.posts.some((post) => post.status !== "deleted");
  const hasScheduled = ui.state.posts.some((post) => ["scheduled", "published"].includes(post.status));
  const completedCount = [hasMemory, hasDraft || hasLibrary, hasLibrary, hasScheduled].filter(Boolean).length;
  return { hasMemory, hasDraft, hasLibrary, hasScheduled, completedCount, total: 4 };
}

function workflowGuide() {
  const { hasMemory, hasDraft, hasLibrary, hasScheduled, completedCount } = goldenPathStats();
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
      <form id="bank-form"><textarea id="bank-text" data-testid="bank-text" placeholder="Example: We launched our first founder test today. The biggest lesson was that workflow ownership matters more than another writing prompt." required minlength="3"></textarea><button class="button" data-testid="bank-save" style="margin-top:10px">Save to Content Bank</button></form>
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
  return `<section class="page" data-testid="library-page"><div class="eyebrow">Content pipeline</div><h1>Library</h1><p class="lead">Every draft, scheduled post, and published post stays visible here.</p>
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
  return '<div class="empty"><span>No posts yet. Your drafts, scheduled, and published posts will live here.</span><button class="button" data-tab="chat">Draft one with Mira</button></div>';
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
      <button class="button" data-testid="open-draft-workspace" data-draft-review="${post.id}">Open draft workspace</button>
      ${["pending", "draft", "saved"].includes(post.status) ? `<button class="button secondary" data-draft-action="edit" data-id="${post.id}">Edit</button><button class="button" data-draft-action="approve" data-id="${post.id}">Approve</button>` : ""}
      <button class="button ghost" data-draft-action="copy" data-id="${post.id}">Copy</button>
      ${post.status !== "published" ? `<button class="button secondary" data-testid="linkedin-handoff" data-draft-action="linkedin" data-id="${post.id}">${ui.integrations?.linkedin?.connected ? "Publish to LinkedIn" : "Copy & open LinkedIn"}</button>` : ""}
    </div>
  </div>`;
}

function postsOnDay(year, month, day) {
  return ui.state.posts.filter((post) => {
    if (!["scheduled", "published"].includes(post.status)) return false;
    const date = new Date(post.scheduled_at || post.published_at);
    return date.getFullYear() === year && date.getMonth() === month && date.getDate() === day;
  });
}

function renderCalendar() {
  const scheduled = ui.state.posts.filter((post) => ["scheduled", "published"].includes(post.status));
  const hasPending = ui.state.posts.some((post) => post.status === "pending");
  const now = new Date();
  const viewed = new Date(now.getFullYear(), now.getMonth() + ui.calendarOffset, 1);
  const year = viewed.getFullYear(), month = viewed.getMonth();
  const firstDay = new Date(year, month, 1).getDay();
  const days = new Date(year, month + 1, 0).getDate();
  const cells = Array(firstDay).fill('<div class="day is-empty"></div>');
  for (let day = 1; day <= days; day++) {
    const matches = postsOnDay(year, month, day);
    const isToday = ui.calendarOffset === 0 && day === now.getDate();
    const dayDate = new Date(year, month, day);
    const isPast = dayDate < new Date(now.getFullYear(), now.getMonth(), now.getDate());
    const clickable = matches.length > 0 || (hasPending && !isPast);
    cells.push(`<${clickable ? "button" : "div"} class="day ${matches.length ? "has-post" : ""} ${isToday ? "today" : ""}" ${clickable ? `data-calendar-day="${day}" aria-label="Open ${viewed.toLocaleString("en", { month: "long" })} ${day}"` : ""}><strong>${day}</strong>${matches.map((post) => `<div class="small day-post"><span class="dot ${post.status}"></span>${escapeHtml(post.schedule_label || post.status)}</div>`).join("")}</${clickable ? "button" : "div"}>`);
  }
  return `<section class="page" data-testid="calendar-page"><div class="eyebrow">Schedule</div>
    <div class="calendar-head">
      <h1>${viewed.toLocaleString("en", { month: "long" })} ${year}</h1>
      <div class="calendar-nav">
        <button class="icon-button" data-calendar-nav="-1" aria-label="Previous month">‹</button>
        ${ui.calendarOffset !== 0 ? '<button class="icon-button calendar-today" data-calendar-nav="0">Today</button>' : ""}
        <button class="icon-button" data-calendar-nav="1" aria-label="Next month">›</button>
      </div>
    </div>
    <p class="lead"><span class="dot published"></span>Published · <span class="dot scheduled"></span>Scheduled${hasPending ? " · Tap a day to schedule a pending draft." : ""}</p>
    <div class="card calendar-card"><div class="calendar">${["Sun","Mon","Tue","Wed","Thu","Fri","Sat"].map((day) => `<div class="day-label">${day}</div>`).join("")}${cells.join("")}</div></div>
    <div class="list" style="margin-top:18px">${scheduled.length ? scheduled.map((post) => `<div class="list-item"><div class="list-top"><strong>${escapeHtml(post.title)}</strong><span class="badge ${post.status}">${post.status}</span></div><p>${escapeHtml(scheduleSummary(post))}</p></div>`).join("") : '<div class="empty"><span>Nothing scheduled yet. Approve a draft to place it here.</span><button class="button secondary" data-tab="library">Open Library</button></div>'}</div>
  </section>`;
}

function showDayModal(day) {
  const now = new Date();
  const viewed = new Date(now.getFullYear(), now.getMonth() + ui.calendarOffset, 1);
  const year = viewed.getFullYear(), month = viewed.getMonth();
  const posts = postsOnDay(year, month, day);
  const pending = ui.state.posts.filter((post) => post.status === "pending");
  const dayDate = new Date(year, month, day);
  const isPast = dayDate < new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const title = dayDate.toLocaleDateString("en", { weekday: "long", month: "long", day: "numeric" });
  const pad = (value) => String(value).padStart(2, "0");
  const defaultTime = `${year}-${pad(month + 1)}-${pad(day)}T09:00`;
  ui.modal = `<div class="modal-backdrop"><div class="modal" data-testid="day-modal">
    <div class="modal-head"><h3>${escapeHtml(title)}</h3><button class="icon-button" data-modal-close="true" aria-label="Close day view">Close</button></div>
    ${posts.length ? `<div class="list">${posts.map((post) => `<div class="list-item"><div class="list-top"><strong>${escapeHtml(post.title)}</strong><span class="badge ${post.status}">${post.status}</span></div><p>${escapeHtml(scheduleSummary(post))}</p><div class="inline-actions"><button class="button secondary" data-day-open-draft="${post.id}">Open draft workspace</button></div></div>`).join("")}</div>` : '<p class="muted">Nothing on this day yet.</p>'}
    ${!isPast && pending.length ? `<div class="custom-schedule" style="margin-top:14px">
      <label>Schedule a pending draft on this day</label>
      <select class="input" id="day-schedule-draft">${pending.map((post) => `<option value="${post.id}">${escapeHtml(post.title)}</option>`).join("")}</select>
      <input class="input" id="day-scheduled-at" type="datetime-local" value="${defaultTime}" style="grid-column: 1 / -1" />
      <button class="button" id="day-schedule-confirm" style="grid-column: 1 / -1">Schedule here</button>
    </div>` : ""}
    <div class="modal-status" data-modal-status></div>
    <div class="modal-actions"><button class="button ghost" id="cancel-modal">Done</button></div>
  </div></div>`;
  render();
  const close = () => { ui.modal = null; render(); };
  document.querySelector("#cancel-modal").onclick = close;
  document.querySelector("[data-modal-close]")?.addEventListener("click", close);
  document.querySelectorAll("[data-day-open-draft]").forEach((button) => {
    button.onclick = () => { ui.modal = null; reviewDraft(button.dataset.dayOpenDraft); };
  });
  const confirm = document.querySelector("#day-schedule-confirm");
  if (confirm) {
    confirm.onclick = () => {
      const draftId = document.querySelector("#day-schedule-draft")?.value;
      const value = document.querySelector("#day-scheduled-at")?.value;
      if (!draftId || !value) return;
      approveDraft(draftId, "custom", new Date(value).toISOString());
    };
  }
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
    ${progressRing()}
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

function progressRing() {
  const profile = ui.state.profile || {};
  const goalMap = { "1-2x_per_week": 1, "3-4x_per_week": 3, "5+_per_week": 5 };
  const goal = goalMap[profile.posting_frequency] || 3;
  const monday = new Date();
  monday.setDate(monday.getDate() - ((monday.getDay() + 6) % 7));
  monday.setHours(0, 0, 0, 0);
  const publishedThisWeek = ui.state.posts.filter((post) =>
    post.status === "published" && post.published_at && new Date(post.published_at) >= monday
  ).length;
  const progress = Math.min(publishedThisWeek / goal, 1);
  const radius = 52;
  const circumference = 2 * Math.PI * radius;
  const complete = progress >= 1;
  const remaining = goal - publishedThisWeek;
  return `<div class="card ring-card ${complete ? "complete" : ""}">
    <div class="ring-wrap">
      <svg viewBox="0 0 128 128" class="ring" role="img" aria-label="Weekly goal progress: ${publishedThisWeek} of ${goal} posts published">
        <circle cx="64" cy="64" r="${radius}" class="ring-track" />
        <circle cx="64" cy="64" r="${radius}" class="ring-fill" stroke-dasharray="${circumference.toFixed(1)}" stroke-dashoffset="${(circumference * (1 - progress)).toFixed(1)}" transform="rotate(-90 64 64)" />
      </svg>
      <div class="ring-center"><strong>${publishedThisWeek}<span>/${goal}</span></strong></div>
    </div>
    <div class="ring-copy">
      <h3>${complete ? "Weekly goal complete" : "This week's goal"}</h3>
      <p class="muted">${complete
        ? "You published everything you aimed for this week. Anything extra is a head start on next week."
        : `${remaining} more ${remaining === 1 ? "post" : "posts"} to hit your ${escapeHtml((profile.posting_frequency || "3-4x_per_week").replaceAll("_", " "))} goal. Publishing from the Library moves this ring.`}</p>
      ${complete ? '<span class="ring-badge">🎉 Goal hit</span>' : `<button class="button secondary" data-tab="${ui.state.posts.some((post) => post.status === "pending") ? "library" : "chat"}">${ui.state.posts.some((post) => post.status === "pending") ? "Review pending drafts" : "Draft with Mira"}</button>`}
    </div>
  </div>`;
}

function statCard(label, value, helper) {
  return `<div class="card stat-card"><div class="muted small">${label}</div><div class="metric">${value}</div><p class="muted small">${escapeHtml(helper)}</p></div>`;
}

function qaChecks() {
  const posts = ui.state.posts || [];
  const bank = ui.state.content_bank || [];
  const linkedin = ui.integrations?.linkedin;
  const hasPending = posts.some((post) => post.status === "pending");
  const hasLibrary = posts.some((post) => post.status !== "deleted");
  const hasScheduled = posts.some((post) => post.status === "scheduled" || post.status === "published");
  const database = ui.integrations?.database;
  return [
    {
      flow: "Auth / workspace",
      status: ui.state.auth?.authenticated ? "Testable" : ui.demoMode ? "Demo mode" : "Needs login",
      done: Boolean(ui.state.auth?.authenticated || ui.demoMode),
      detail: ui.state.auth?.authenticated ? "Signed-in workspace is active." : "Public demo mode is available; production auth hardening is still separate.",
      next: "Create account, log out, then log back in.",
      tab: "settings",
    },
    {
      flow: "Onboarding",
      status: ui.state.onboarding_completed ? "Testable" : "Needs setup",
      done: Boolean(ui.state.onboarding_completed),
      detail: ui.state.onboarding_completed ? "Founder/company/audience/voice context exists." : "Complete the setup questionnaire first.",
      next: "Check whether the questions match the intended founder onboarding.",
      tab: "settings",
    },
    {
      flow: "Content Bank",
      status: bank.length ? "Testable" : "Needs memory",
      done: bank.length > 0,
      detail: bank.length ? `${bank.length} entries available for Mira.` : "Add one real work moment before testing drafts.",
      next: "Add, edit, mark used/high potential, then draft from a memory.",
      tab: "bank",
    },
    {
      flow: "Mira strategy",
      status: bank.length ? "Testable" : "Needs memory",
      done: bank.length > 0,
      detail: "Mira can suggest angles, recommend a draft framework, and ask for missing detail before drafting.",
      next: "Ask: Give me 3 angles from my Content Bank.",
      tab: "chat",
    },
    {
      flow: "Draft workspace",
      status: hasPending || hasLibrary ? "Testable" : "Needs draft",
      done: hasPending || hasLibrary,
      detail: hasPending ? "A pending draft is ready for review." : hasLibrary ? "Drafts exist in Library." : "Generate one draft from Mira.",
      next: "Open draft workspace, read full draft, edit, save, approve, or skip.",
      tab: hasLibrary ? "library" : "chat",
    },
    {
      flow: "Library",
      status: hasLibrary ? "Testable" : "Needs draft",
      done: hasLibrary,
      detail: hasLibrary ? "Drafts/scheduled/published items should remain visible." : "Library is empty until a draft exists.",
      next: "Use filters, expand full draft, approve from Library.",
      tab: "library",
    },
    {
      flow: "Calendar",
      status: hasScheduled ? "Testable" : "Needs scheduled post",
      done: hasScheduled,
      detail: hasScheduled ? "Scheduled/published posts are visible." : "Approve a draft for best time or custom time first.",
      next: "Approve a draft, then confirm it appears in Calendar.",
      tab: "calendar",
    },
    {
      flow: "LinkedIn",
      status: linkedin?.connected ? "Connected" : linkedin?.configured ? "OAuth pending" : "Fallback only",
      done: Boolean(linkedin?.connected || linkedin?.configured),
      detail: linkedin?.connected
        ? "OAuth connection is active for this session."
        : linkedin?.configured
          ? "Credentials exist; redirect/app access still controls final OAuth posting."
          : "Manual copy/open fallback is the safe test path.",
      next: "Use Copy & open LinkedIn, then choose Not yet or Mark posted.",
      tab: hasLibrary ? "library" : "chat",
    },
    {
      flow: "Storage",
      status: database?.storage === "postgres" ? "Postgres" : "File-backed",
      done: database?.storage === "postgres",
      detail: database?.storage === "postgres" ? "Render Postgres-backed storage is active." : "MVP file-backed storage is active in this environment.",
      next: "Confirm Render DATABASE_URL and USE_DATABASE_STORAGE before production-like testing.",
      tab: "settings",
    },
  ];
}

function qaFlowCard(item) {
  const badgeClass = item.done ? "published" : item.status === "OAuth pending" || item.status === "Demo mode" ? "scheduled" : "draft";
  return `<div class="qa-item ${item.done ? "done" : ""}">
    <div class="qa-item-head"><strong>${escapeHtml(item.flow)}</strong><span class="badge ${badgeClass}">${escapeHtml(item.status)}</span></div>
    <p>${escapeHtml(item.detail)}</p>
    <div class="qa-next"><span>Next test</span>${escapeHtml(item.next)}</div>
    <button class="button secondary" data-tab="${escapeHtml(item.tab)}">Open ${escapeHtml(sectionNameForTab(item.tab))}</button>
  </div>`;
}

function sectionNameForTab(tab) {
  return {
    chat: "Chat",
    bank: "Content Bank",
    library: "Library",
    calendar: "Calendar",
    settings: "Settings",
  }[tab] || "Flow";
}

function renderQA() {
  const checks = qaChecks();
  const readyCount = checks.filter((item) => item.done).length;
  const posts = ui.state.posts || [];
  const bank = ui.state.content_bank || [];
  const mockupChecks = [
    ["Flow 1 · Onboarding", "Partly aligned", "Questionnaire exists; payment and pre-signup localStorage handoff are still deferred."],
    ["Flow 2 · Draft", "Partly aligned", "Mira chat, angle choice, draft card, edit/save/approve exist; upload document and SSE activity stream are still deferred."],
    ["Flow 3 · LinkedIn", "Partly aligned", "OAuth helpers and manual fallback exist; final auto-posting depends on LinkedIn Developer redirect/app access."],
    ["Flow 4 · Check-in / Bank", "Partly aligned", "Daily check-in categories and Content Bank management exist; document/link capture is still MVP-level."],
    ["Flow 5 · Settings", "Partly aligned", "Settings now follows the handoff section order; exact bottom-sheet edit panels are still deferred."],
    ["Flows 6-8 · Library/Calendar/Progress", "Partly aligned", "Library, Calendar, Analytics exist; detailed post-performance analytics are still limited."],
    ["Navigation", "Aligned", "Bottom tabs are Chat, Bank, Library, Calendar, Settings. Plus menu contains Draft, Daily check-in, Progress, and QA."],
  ];
  const knownLimitations = [
    "LinkedIn auto-posting still depends on LinkedIn Developer redirect/app access. Manual fallback is the reliable test path for now.",
    "Auth is staging-level. Password reset, email verification, account recovery, and production security hardening are not complete yet.",
    "Mira has stronger strategy and framework behavior now, but still needs deeper voice learning from more writing samples.",
    "The UI is more responsive and the navigation now matches the handoff structure, but exact screen-by-screen visual parity is still in progress.",
  ];
  return `<section class="page qa-page" data-testid="qa-page">
    <div class="eyebrow">Test mode</div>
    <h1>QA status</h1>
    <p class="lead">Use this page to test Blidx like a product flow instead of guessing what should work. It reflects the current staging MVP state, not a production release.</p>
    <div class="qa-summary card">
      <div>
        <span class="eyebrow">Current readiness</span>
        <div class="metric">${readyCount}/${checks.length}</div>
        <p class="muted">Content Bank: ${bank.length} · Posts: ${posts.length} · Auth: ${ui.state.auth?.authenticated ? "signed in" : ui.demoMode ? "demo" : "not signed in"}</p>
      </div>
      <div class="qa-actions">
        <button class="button" data-tab="bank">Start with Content Bank</button>
        <button class="button secondary" data-tab="chat">Test Mira</button>
        <button class="button ghost" data-tab="library">Review Library</button>
      </div>
    </div>
    <div class="qa-script card">
      <div class="card-head"><h3>Recommended QA script</h3><span class="badge draft">Golden path</span></div>
      <div class="checklist">
        ${[
          "Sign up or log in.",
          "Complete onboarding with real founder/company/voice context.",
          "Add one real memory to Content Bank.",
          "Ask Mira for 3 angles from the Content Bank.",
          "Choose one angle and generate a draft.",
          "Open draft workspace, edit/save/approve/copy.",
          "Confirm Library and Calendar reflect the state change.",
          "Use LinkedIn fallback and choose Not yet or Mark posted.",
        ].map((item, index) => `<div class="check done"><span>${index + 1}</span>${escapeHtml(item)}</div>`).join("")}
      </div>
    </div>
    <div class="qa-grid">
      ${checks.map(qaFlowCard).join("")}
    </div>
    <div class="card qa-mockups">
      <div class="card-head"><h3>Mockup alignment</h3><span class="badge scheduled">handoff files</span></div>
      <div class="mockup-list">
        ${mockupChecks.map(([flow, status, detail]) => `<div class="mockup-row"><div><strong>${escapeHtml(flow)}</strong><p>${escapeHtml(detail)}</p></div><span class="badge ${status === "Aligned" ? "published" : "scheduled"}">${escapeHtml(status)}</span></div>`).join("")}
      </div>
    </div>
    <div class="card qa-limitations">
      <div class="card-head"><h3>Known limitations</h3><span class="badge scheduled">staging</span></div>
      ${knownLimitations.map((item) => `<p><strong>•</strong> ${escapeHtml(item)}</p>`).join("")}
    </div>
    <div class="card qa-feedback">
      <div class="card-head"><h3>How to send feedback</h3><span class="badge draft">structured</span></div>
      <p class="muted">Best format for Malia/testing feedback:</p>
      <div class="feedback-template">
        <code>Flow:</code> Auth / Onboarding / Content Bank / Mira / Draft / Library / Calendar / LinkedIn<br>
        <code>What I tried:</code> ...<br>
        <code>Expected:</code> ...<br>
        <code>Actual:</code> ...<br>
        <code>Screenshot:</code> optional
      </div>
    </div>
  </section>`;
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

function settingsSection(title, rows) {
  return `<div class="settings-section">
    <div class="settings-header">${escapeHtml(title)}</div>
    <div class="settings-group">${rows.join("")}</div>
  </div>`;
}

function settingsRow(icon, tone, label, value, action = "") {
  return `<div class="settings-row">
    <div class="settings-row-icon ${escapeHtml(tone)}">${escapeHtml(icon)}</div>
    <div class="settings-row-body">
      <div class="settings-row-label">${escapeHtml(label)}</div>
      ${value ? `<div class="settings-row-value">${escapeHtml(value)}</div>` : ""}
    </div>
    ${action ? `<div class="settings-row-action">${escapeHtml(action)}</div>` : ""}
  </div>`;
}

function toggleRow(icon, label, value, active = true) {
  return `<div class="settings-row">
    <div class="settings-row-icon green">${escapeHtml(icon)}</div>
    <div class="settings-row-body">
      <div class="settings-row-label">${escapeHtml(label)}</div>
      <div class="settings-row-value">${escapeHtml(value)}</div>
    </div>
    <div class="toggle ${active ? "on" : ""}" aria-hidden="true"></div>
  </div>`;
}

function settingsProfileForm(p) {
  return `<div class="settings-section">
    <div class="settings-header">Your Profile</div>
    <div class="card settings-profile-card">
      <div class="settings-profile-intro">
        <div>
          <h3>Mira profile details</h3>
          <p class="muted small">This is the source of truth Mira uses for drafting, tone, audience, and founder context.</p>
        </div>
        <span class="badge ${ui.state.onboarding_completed ? "published" : "draft"}">${ui.state.onboarding_completed ? "Saved" : "Needs setup"}</span>
      </div>
      <form class="form-grid" id="profile-form">
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
        <div class="field full"><button class="button">Save profile</button></div>
      </form>
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
  const databaseIsPostgres = database?.storage === "postgres";
  const linkedinDetail = linkedin?.connected
    ? "Connected for this staging session"
    : linkedin?.configured
      ? "OAuth configured · redirect/app access still required"
      : "Not connected · manual fallback ready";
  return `<section class="page settings-page" data-testid="settings-page"><div class="eyebrow">Settings</div><h1>Settings</h1><p class="lead">Your profile, LinkedIn connection, notification preferences, and staging status live here.</p>
    ${ui.notice ? `<div class="notice">${escapeHtml(ui.notice)}</div>` : ""}
    ${settingsProfileForm(p)}
    <div class="settings-section">
      <div class="settings-header">LinkedIn</div>
      <div class="linkedin-status-card">
        <div class="li-dot ${linkedin?.connected ? "connected" : "disconnected"}"></div>
        <div class="li-info">
          <div class="li-label">${escapeHtml(linkedinBadge)}</div>
          <div class="li-sub">${escapeHtml(linkedinDetail)}</div>
        </div>
        ${linkedin?.connected ? '<button class="li-action disconnect" type="button">Connected</button>' : '<button class="li-action connect" type="button" id="connect-linkedin">Connect</button>'}
      </div>
    </div>
    ${settingsSection("Notifications", [
      toggleRow("🔔", "Push notifications", "Drafts ready, performance updates, reminders", true),
      toggleRow("✉", "Email nudges", "When you have not opened Blidx in a while", true),
      settingsRow("⏰", "green", "Daily check-in time", "6:00 PM"),
    ])}
    ${settingsSection("Timezone", [
      settingsRow("🌏", "blue", "Timezone", "Asia/Singapore (GMT+8) · Auto-detected"),
    ])}
    <div class="settings-section">
      <div class="settings-header">Account</div>
      <div class="settings-group">
        ${settingsRow("🔒", "gray", "Change password", "Password reset is not enabled in staging")}
        <div class="settings-row settings-action-row">
          <div class="settings-row-icon red">🗑</div>
          <div class="settings-row-body">
            <div class="settings-row-label">Reset workspace data</div>
            <div class="settings-row-value">Clears local/demo memories, drafts, and chat state</div>
          </div>
          <button type="button" class="button danger settings-inline-button" id="reset-demo">Reset</button>
        </div>
      </div>
    </div>
    <div class="settings-system">
      <div class="eyebrow">System / staging</div>
      ${productReadinessPanel()}
      <div class="grid">
        <div class="card"><div class="card-head"><h3>AI generation</h3><span class="badge ${anthropic?.configured ? "published" : "draft"}">${anthropic?.configured ? "Claude ready" : "Local fallback"}</span></div><p class="muted">${anthropic?.configured ? `Mira drafts use ${escapeHtml(anthropic.model)} with profile, writing samples, voice controls, and Content Bank context.` : "Add ANTHROPIC_API_KEY in Render to enable live Claude generation. The local fallback still uses your CTA style and avoids generic repeated templates."}</p></div>
        <div class="card"><div class="card-head"><h3>Database storage</h3><span class="badge ${databaseIsPostgres ? "published" : "draft"}">${databaseIsPostgres ? "Postgres active" : "File storage"}</span></div><p class="muted">${databaseIsPostgres ? "Signup, login, and workspace state are using the configured Render Postgres database." : "This staging app is still using MVP file-backed storage. Set USE_DATABASE_STORAGE=true and DATABASE_URL in Render to switch to Postgres."}</p></div>
      </div>
      <div class="card" style="margin-top:16px"><div class="card-head"><h3>PayloadCMS review</h3><span class="badge draft">${escapeHtml(payloadcms?.recommendation || "defer")}</span></div><p class="muted">${escapeHtml(payloadcms?.reason || "PayloadCMS review pending.")}</p></div>
    </div>
    <div class="settings-version">Blidx staging MVP · Flow 5 alignment pass</div>
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
  const chatGuide = document.querySelector("#chat-guide");
  if (chatGuide) chatGuide.addEventListener("toggle", () => { ui.chatGuideOpen = chatGuide.open; });
  document.querySelectorAll("[data-calendar-nav]").forEach((button) => {
    button.onclick = () => {
      const step = Number(button.dataset.calendarNav);
      ui.calendarOffset = step === 0 ? 0 : ui.calendarOffset + step;
      render();
    };
  });
  document.querySelectorAll("[data-calendar-day]").forEach((button) => {
    button.onclick = () => showDayModal(Number(button.dataset.calendarDay));
  });
  document.querySelectorAll("[data-proactive-dismiss]").forEach((button) => {
    button.onclick = () => { ui.proactiveDismissed = true; render(); };
  });
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
  document.querySelectorAll("[data-copy-draft]").forEach((button) => {
    button.onclick = () => copyDraft(button.dataset.copyDraft);
  });
  document.querySelector("#linkedin-url")?.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      const id = document.querySelector("[data-linkedin-track]")?.dataset.linkedinTrack;
      if (id) trackLinkedInUrl(id);
    }
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
  const entry = ui.state.content_bank.find((item) => item.id === id);
  try {
    await api(`/api/content-bank/${id}`, { method: "DELETE" });
    await refresh();
    showToast(
      "Memory deleted",
      entry ? { label: "Undo", onAction: () => restoreMemory(entry) } : null,
    );
  } catch (error) {
    showToast(error.message);
  }
}

async function restoreMemory(entry) {
  try {
    await api("/api/content-bank", {
      method: "POST",
      body: JSON.stringify({ raw_text: entry.raw_text, category: entry.category }),
    });
    await refresh();
    showToast("Memory restored");
  } catch (error) {
    showToast(error.message || "Could not restore the memory");
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
      .then(() => {
        if (action === "save") showToast("Saved to Library");
        else showToast("Draft skipped", { label: "Undo", onAction: () => restoreDraft(id) });
      });
  }
}

async function restoreDraft(id) {
  try {
    await api(`/api/drafts/${id}/restore`, { method: "POST" });
    await refresh();
    showToast("Draft restored to review");
  } catch (error) {
    showToast(error.message || "Could not restore the draft");
  }
}

function quickEditButton(label) {
  return `<button class="prompt-chip" type="button" data-quick-edit="${escapeHtml(label)}">${escapeHtml(label)}</button>`;
}

function setModalBusy(isBusy, label = "Working…") {
  document.querySelectorAll(".modal button, .modal input, .modal textarea").forEach((element) => {
    element.disabled = isBusy;
  });
  const status = document.querySelector("[data-modal-status]");
  if (status) status.textContent = isBusy ? label : "";
}

function showModalError(message) {
  const status = document.querySelector("[data-modal-status]");
  if (status) {
    status.textContent = message;
    status.classList.add("error");
    return;
  }
  showToast(message);
}

function showScheduleModal(id) {
  ui.modal = `<div class="modal-backdrop"><div class="modal" data-testid="schedule-modal"><div class="modal-head"><h3>When should this post move forward?</h3><button class="icon-button" data-modal-close="true" aria-label="Close schedule modal">Close</button></div><p class="muted">Choose a testable scheduling state. For real LinkedIn publishing today, keep using Copy & open LinkedIn.</p>
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
    <div class="modal-status" data-modal-status></div>
    <div class="modal-actions"><button class="button ghost" id="cancel-modal">Cancel</button></div>
  </div></div>`;
  render();
  const close = () => { ui.modal = null; render(); };
  document.querySelector("#cancel-modal").onclick = close;
  document.querySelector("[data-modal-close]")?.addEventListener("click", close);
  document.querySelectorAll("[data-schedule]").forEach((button) => {
    button.onclick = () => approveDraft(id, button.dataset.schedule);
  });
  document.querySelector("#custom-schedule").onclick = () => {
    const value = document.querySelector("#custom-scheduled-at")?.value;
    approveDraft(id, "custom", value ? new Date(value).toISOString() : null);
  };
}

function scheduleButton(type, title, description) {
  return `<button class="schedule-option" data-testid="schedule-option" data-schedule="${type}">
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
  try {
    setModalBusy(true, schedule_type === "now" ? "Marking as published…" : "Scheduling draft…");
    await api(`/api/drafts/${id}/approve`, { method: "POST", body: JSON.stringify({ schedule_type, scheduled_at }) });
    ui.modal = null;
    ui.reviewDraftId = null;
    await refresh();
    showToast(schedule_type === "now" ? "Published locally" : "Scheduled and added to Calendar");
  } catch (error) {
    setModalBusy(false);
    showModalError(error.message || "Could not update this draft. Please try again.");
  }
}

async function copyAndOpenLinkedIn(id) {
  const post = ui.state.posts.find((item) => item.id === id);
  if (!post) return;
  try {
    showToast("Preparing LinkedIn handoff…");
    const publishResult = await api(`/api/drafts/${id}/publish`, { method: "POST" });
    if (publishResult.published) {
      await refresh();
      showToast("Published to LinkedIn");
      return;
    }
    let copied = false;
    try {
      await navigator.clipboard.writeText(post.content);
      copied = true;
    } catch (error) {
      copied = false;
    }
    const opened = window.open(
      publishResult.fallback_url || ui.integrations?.linkedin?.fallback_url || "https://www.linkedin.com/feed/",
      "_blank",
      "noopener,noreferrer"
    );
    showLinkedInTrackingModal(id, { copied, opened: Boolean(opened), content: post.content });
  } catch (error) {
    showToast(error.message || "Could not prepare the LinkedIn handoff.");
  }
}

function showLinkedInTrackingModal(id, handoff = {}) {
  const copyStatus = handoff.copied
    ? "The draft has been copied to your clipboard."
    : "Clipboard access was blocked. Copy the draft manually below before posting.";
  const openStatus = handoff.opened
    ? "LinkedIn opened in a new tab."
    : "If LinkedIn did not open, use the button below.";
  ui.modal = `<div class="modal-backdrop"><div class="modal" data-testid="linkedin-modal"><div class="modal-head"><h3>Did you post it on LinkedIn?</h3><button class="icon-button" data-modal-close="true" aria-label="Close LinkedIn modal">Close</button></div>
    <p class="muted">${copyStatus} ${openStatus}</p>
    ${handoff.copied ? "" : `<textarea class="handoff-copy" readonly>${escapeHtml(handoff.content || "")}</textarea>`}
    <div class="linkedin-handoff-actions">
      <a class="button secondary" href="https://www.linkedin.com/feed/" target="_blank" rel="noopener noreferrer">Open LinkedIn</a>
      <button class="button ghost" data-copy-draft="${escapeHtml(id)}">Copy draft again</button>
    </div>
    <p class="muted small">After publishing on LinkedIn, paste the post URL here. If you have not posted yet, choose Not yet and the draft stays available in Blidx.</p>
    <input class="input" id="linkedin-url" placeholder="https://www.linkedin.com/feed/update/..." />
    <div class="modal-status" data-modal-status></div>
    <div class="modal-actions"><button class="button ghost" data-testid="linkedin-not-yet" data-linkedin-defer="true">Not yet</button><button class="button" data-testid="linkedin-mark-posted" data-linkedin-track="${escapeHtml(id)}">Mark posted</button></div>
  </div></div>`;
  render();
}

function deferLinkedInTracking() {
  ui.modal = null;
  render();
  showToast("No problem. Draft kept in Blidx for later.");
}

async function trackLinkedInUrl(id) {
  const url = document.querySelector("#linkedin-url")?.value.trim() || "";
  if (url && !/^https:\/\/([a-z]+\.)?linkedin\.com\//i.test(url)) {
    showModalError("Please paste a LinkedIn post URL, or choose Not yet.");
    return;
  }
  try {
    setModalBusy(true, "Marking as posted…");
    await api(`/api/drafts/${id}/track-linkedin-url`, { method: "POST", body: JSON.stringify({ url }) });
    ui.modal = null;
    ui.reviewDraftId = null;
    await refresh();
    showToast(url ? "Marked as posted with LinkedIn URL" : "Marked as posted");
  } catch (error) {
    setModalBusy(false);
    showModalError(error.message || "Could not mark this post as published.");
  }
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

function showToast(message, action = null) {
  ui.toast = message;
  ui.toastAction = action;
  render();
  clearTimeout(ui.toastTimer);
  // Leave undo-style toasts up long enough to actually reach.
  ui.toastTimer = setTimeout(() => { ui.toast = ""; ui.toastAction = null; render(); }, action ? 6000 : 2200);
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

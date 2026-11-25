const storageKey = "luri.portal.access-token";
const organizationKey = "luri.portal.organization-id";

const state = {
  activeOrganization: null,
  organizations: [],
  user: null,
  permissions: [],
  token: sessionStorage.getItem(storageKey),
  view: "overview",
  configurationBot: null,
  configurationSourcesPage: 1,
};

const loginScreen = document.querySelector("#login-screen");
const appShell = document.querySelector("#app-shell");
const content = document.querySelector("#portal-content");
const picker = document.querySelector("#organization-picker");
const organizationName = document.querySelector("#organization-name");
const notice = document.querySelector("#portal-notice");
const createOrganizationButton = document.querySelector("#create-organization");
const organizationModal = document.querySelector("#organization-modal");
const organizationForm = document.querySelector("#organization-form");

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>'"]/g, (character) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    "'": "&#039;",
    '"': "&quot;",
  })[character]);
}

function formatDate(value) {
  if (!value) return "—";
  return new Intl.DateTimeFormat("es-PE", { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));
}

function showNotice(message) {
  notice.textContent = message;
  notice.hidden = false;
}

function clearNotice() {
  notice.hidden = true;
  notice.textContent = "";
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: {
      Accept: "application/json",
      ...(options.body ? { "Content-Type": "application/json" } : {}),
      ...(state.token ? { Authorization: `Bearer ${state.token}` } : {}),
      ...(options.headers || {}),
    },
  });
  if (response.status === 401) {
    signOut();
    throw new Error("Tu sesión venció. Ingresa nuevamente.");
  }
  if (!response.ok) {
    const detail = await response.json().catch(() => null);
    const message = typeof detail?.detail === "string" ? detail.detail : response.status === 422 ? "Revisa los campos del formulario." : response.status === 403 ? "No tienes permiso para esta acción." : "No se pudo completar la solicitud. Intenta nuevamente.";
    const error = new Error(message);
    error.status = response.status;
    throw error;
  }
  return response.json();
}

async function login(event) {
  event.preventDefault();
  const error = document.querySelector("#login-error");
  error.textContent = "";
  const email = document.querySelector("#email").value;
  const password = document.querySelector("#password").value;
  try {
    const result = await api("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    });
    state.token = result.access_token;
    sessionStorage.setItem(storageKey, result.access_token);
    await startWorkspace();
  } catch (_error) {
    error.textContent = "No se pudo ingresar. Revisa tu correo y contraseña.";
  }
}

function signOut() {
  window.LuriConversations.reset();
  window.LuriCRM.reset();
  renderGeneration++;
  content.innerHTML = "";
  sessionStorage.removeItem(storageKey);
  sessionStorage.removeItem(organizationKey);
  state.token = null;
  state.activeOrganization = null;
  state.user = null;
  state.permissions = [];
  loginScreen.hidden = false;
  appShell.hidden = true;
}

function selectedOrganization() {
  return state.organizations.find((organization) => organization.id === state.activeOrganization);
}

function renderOrganizationPicker() {
  picker.innerHTML = state.organizations.map((organization) => (
    `<option value="${escapeHtml(organization.id)}">${escapeHtml(organization.name)}</option>`
  )).join("");
  picker.value = state.activeOrganization;
  picker.hidden = state.organizations.length <= 1;
  const organization = selectedOrganization();
  organizationName.textContent = organization?.name || "Empresa";
}

async function startWorkspace() {
  clearNotice();
  const [result, currentUser, access] = await Promise.all([api("/organizations"), api("/auth/me"), api("/permissions/me")]);
  state.user = currentUser.user;
  state.permissions = access.permissions;
  state.organizations = result.organizations || [];
  if (!state.organizations.length) {
    throw new Error("No tienes una empresa asignada todavía.");
  }
  const saved = sessionStorage.getItem(organizationKey);
  const query = new URLSearchParams(window.location.search);
  const linkedOrganization = query.get("org");
  const linkedConversation = query.get("conversation");
  const canOpenLink = /^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i.test(linkedConversation || "")
    && state.organizations.some((item) => item.id === linkedOrganization);
  const preferred = canOpenLink ? linkedOrganization : saved;
  state.activeOrganization = state.organizations.some((item) => item.id === preferred)
    ? preferred : state.organizations[0].id;
  if (canOpenLink) {
    state.view = "conversations";
    document.querySelectorAll(".nav-item").forEach((item) => item.classList.toggle("active", item.dataset.view === state.view));
  }
  renderOrganizationPicker();
  createOrganizationButton.hidden = state.user?.role !== "platform_admin";
  loginScreen.hidden = true;
  appShell.hidden = false;
  await renderView(canOpenLink ? linkedConversation : null);
}

function openOrganizationModal() {
  if (state.user?.role !== "platform_admin") return;
  document.querySelector("#organization-form-error").textContent = "";
  organizationForm.reset();
  organizationModal.hidden = false;
  document.querySelector("#new-organization-name").focus();
}

function closeOrganizationModal() {
  organizationModal.hidden = true;
  organizationForm.reset();
}

function slugify(value) {
  return value.toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "")
    .replace(/[^a-z0-9]+/g, "-").replace(/(^-|-$)/g, "");
}

async function createOrganization(event) {
  event.preventDefault();
  const error = document.querySelector("#organization-form-error");
  error.textContent = "";
  const name = document.querySelector("#new-organization-name").value.trim();
  const slug = slugify(document.querySelector("#new-organization-slug").value);
  const email = document.querySelector("#new-owner-email").value.trim();
  const firstName = document.querySelector("#new-owner-first-name").value.trim();
  const password = document.querySelector("#new-owner-password").value;
  if (password.length < 12) {
    error.textContent = "La contraseña temporal debe tener al menos 12 caracteres.";
    return;
  }
  try {
    const created = await api("/platform/organizations", {
      method: "POST",
      body: JSON.stringify({ name, slug, settings: { locale: "es", timezone: "America/Lima" } }),
    });
    try {
      await api("/users", {
        method: "POST",
        body: JSON.stringify({ organization_id: created.organization.id, email, first_name: firstName || null, password, role: "organization_owner" }),
      });
    } catch (_ownerError) {
      error.textContent = "La empresa se creó, pero no se pudo crear su propietario. No crees otra empresa: solicita soporte para completar el acceso.";
      return;
    }
    const result = await api("/organizations");
    state.organizations = result.organizations || [];
    state.activeOrganization = created.organization.id;
    sessionStorage.setItem(organizationKey, state.activeOrganization);
    renderOrganizationPicker();
    closeOrganizationModal();
    showNotice("Empresa y acceso de propietario creados correctamente.");
    await renderView();
  } catch (_error) {
    error.textContent = "No se pudo crear la empresa. Revisa que el identificador y el correo no estén en uso.";
  }
}

async function loadSafe(path) {
  try {
    return await api(path);
  } catch (error) {
    return { error: error.message };
  }
}

function header(title, description) {
  return `<div class="view-heading"><div><h3>${escapeHtml(title)}</h3><p class="muted">${escapeHtml(description)}</p></div></div>`;
}

function table(headers, rows) {
  if (!rows.length) return '<p class="empty">Aún no hay información para mostrar.</p>';
  return `<div class="table-wrap"><table><thead><tr>${headers.map((item) => `<th>${escapeHtml(item)}</th>`).join("")}</tr></thead><tbody>${rows.join("")}</tbody></table></div>`;
}

async function renderOverview(organizationId) {
  const [dashboard, conversations, contacts] = await Promise.all([
    loadSafe(`/organizations/${organizationId}/dashboard?period=last_7_days`),
    loadSafe(`/organizations/${organizationId}/conversations?page_size=5`),
    loadSafe(`/organizations/${organizationId}/contacts?page_size=5`),
  ]);
  if (dashboard.error) showNotice("Algunas métricas no están disponibles para tu rol.");
  const metrics = dashboard.error ? {} : dashboard;
  const conversationItems = conversations.items || [];
  const contactItems = contacts.items || [];
  return `${header("Inicio", "Resumen operativo de los últimos 7 días.")}
    <div class="metric-grid">
      <article class="metric-card"><span>Conversaciones abiertas</span><strong>${metrics.conversations?.open ?? "—"}</strong></article>
      <article class="metric-card"><span>Clientes registrados</span><strong>${metrics.contacts?.total ?? "—"}</strong></article>
      <article class="metric-card"><span>Atenciones humanas</span><strong>${metrics.handoffs?.active ?? "—"}</strong></article>
      <article class="metric-card"><span>Automatizaciones activas</span><strong>${metrics.automations?.running ?? "—"}</strong></article>
    </div>
    <div class="two-columns">
      <article class="panel"><h4>Conversaciones recientes</h4>${table(["Cliente", "Estado", "Último mensaje"], conversationItems.map((item) => `<tr><td>${escapeHtml(item.masked_customer_identifier)}</td><td><span class="status ${escapeHtml(item.status)}">${escapeHtml(item.status)}</span></td><td>${escapeHtml(item.last_message_preview || (item.message_count > 0 ? "Vista previa no disponible" : "Sin mensajes"))}</td></tr>`))}</article>
      <article class="panel"><h4>Clientes recientes</h4>${table(["Cliente", "Canal", "Estado"], contactItems.map((item) => `<tr><td>${escapeHtml(item.display_name || "Sin nombre")}</td><td>${escapeHtml(item.channel_type)}</td><td><span class="status ${escapeHtml(item.status)}">${escapeHtml(item.status)}</span></td></tr>`))}</article>
    </div>`;
}

async function renderConversations(organizationId) {
  return window.LuriConversations.render(organizationId, api, state.user, state.permissions);
}

async function renderContacts(organizationId) {
  return window.LuriCRM.render(organizationId, api, renderView);
}

async function renderTeam() {
  const result = await loadSafe("/users");
  if (result.error) return `${header("Equipo", "Usuarios con acceso a tu espacio.")}<p class="empty">No tienes permiso para ver usuarios.</p>`;
  return `${header("Equipo", `${result.total} usuarios con acceso.`)}<article class="panel">${table(["Nombre", "Correo", "Rol", "Estado"], result.users.map((item) => {
    const name = [item.first_name, item.last_name].filter(Boolean).join(" ");
    return `<tr><td>${escapeHtml(name || "Sin nombre")}</td><td>${escapeHtml(item.email)}</td><td>${escapeHtml(item.role)}</td><td><span class="status ${item.status === "active" ? "active" : "archived"}">${escapeHtml(item.status)}</span></td></tr>`;
  }))}</article>`;
}

const aiModelLabels = {
  "": "Predeterminado de la plataforma",
  "gpt-6-luna": "Luna",
  "gpt-6.1-terra": "Terra",
};
const sourceStatusLabels = { draft: "Borrador", published: "Publicada", archived: "Archivada" };

async function renderConfiguration(organizationId) {
  const botsResult = await loadSafe("/bots");
  const bots = (botsResult.bots || []).filter((bot) => bot.organization_id === organizationId);
  const bot = bots.find((item) => item.id === state.configurationBot) || bots[0];
  const heading = header("Configuración de IA", "Modelo, perfil y fuentes de cada asistente.");
  if (!bot) return heading + '<p class="empty">' + (botsResult.error ? "No se pudo cargar la lista de asistentes." : "Esta empresa aún no tiene un asistente.") + "</p>";

  const botPath = "/bots/" + encodeURIComponent(bot.id);
  const sourcesPath = "/organizations/" + encodeURIComponent(organizationId) + botPath + "/knowledge";
  const page = state.configurationBot === bot.id ? state.configurationSourcesPage : 1;
  const [profileResult, sources] = await Promise.all([
    loadSafe(botPath + "/business-configuration"),
    loadSafe(sourcesPath + "?page=" + page + "&page_size=12"),
  ]);
  const profile = profileResult.business_configuration;
  const ai = bot.settings?.generative_ai || {};
  const selectedModel = ai.model || "";
  const permissions = state.permissions;
  const picker = bots.length > 1 ? '<label class="ai-bot-picker">Asistente<select id="ai-config-bot">' + bots.map((item) =>
    '<option value="' + escapeHtml(item.id) + '"' + (item.id === bot.id ? " selected" : "") + ">" + escapeHtml(item.name) + "</option>"
  ).join("") + "</select></label>" : "";

  const model = permissions.includes("bots.update")
    ? '<form id="ai-model-form"><label>Modelo<select name="model">' + Object.entries(aiModelLabels).map(([id, label]) =>
        '<option value="' + escapeHtml(id) + '"' + (id === selectedModel ? " selected" : "") + ">" + escapeHtml(label) + "</option>"
      ).join("") + '</select></label><p class="field-hint">Cambiar de modelo puede afectar el consumo de IA e interrumpir respuestas en curso.</p>' +
      '<p class="form-error" role="alert"></p><button class="primary-button compact-button">Guardar modelo</button></form>'
    : '<p class="ai-value">' + escapeHtml(aiModelLabels[selectedModel] || selectedModel) + "</p>";

  const profileFields = profile ? '<form id="ai-profile-form">' +
    '<label>Nombre comercial<input name="business_name" required maxlength="200" value="' + escapeHtml(profile.business_name) + '"></label>' +
    '<label>Descripción<textarea name="description" required maxlength="1000" rows="3">' + escapeHtml(profile.description) + "</textarea></label>" +
    '<label>Instrucciones de atención<textarea name="service_instructions" required maxlength="4000" rows="5">' + escapeHtml(profile.service_instructions) + "</textarea></label>" +
    '<p class="form-error" role="alert"></p><button class="primary-button compact-button">Guardar perfil</button></form>' : "";
  const profileMarkup = !profile
    ? '<p class="empty">El perfil comercial todavía no está disponible.</p>'
    : permissions.includes("business_configuration.update") ? profileFields
      : '<p class="ai-value">' + escapeHtml(profile.business_name) + '</p><p class="ai-source-text">' + escapeHtml(profile.description) + "</p>";
  const profileDetails = profile ? '<p class="field-hint">' + escapeHtml(profile.timezone) + ' · ' +
    (profile.services?.length ?? 0) + ' servicios · ' + (profile.payment_methods?.length ?? 0) + ' métodos de pago</p>' : "";

  const knowledgeItems = (sources.items || []).map((item) => {
    const publish = item.status === "draft" && permissions.includes("knowledge.publish")
      ? '<button type="button" class="secondary-button" data-ai-publish="' + escapeHtml(item.id) + '">Publicar fuente</button>' : "";
    const edit = item.status !== "archived" && permissions.includes("knowledge.update")
      ? '<details class="ai-source-edit"><summary>Editar fuente</summary><form data-ai-source-id="' + escapeHtml(item.id) + '">' +
        '<label>Título<input name="title" required maxlength="200" value="' + escapeHtml(item.title) + '"></label>' +
        '<label>Información para el asistente<textarea name="content" required maxlength="20000" rows="5">' +
        escapeHtml(item.content) + '</textarea></label><p class="field-hint">' +
        (item.status === "published" ? 'Al guardar, la información actualizada seguirá publicada.' : 'El borrador estará disponible para el asistente cuando lo publiques.') +
        '</p><p class="form-error" role="alert"></p><button class="primary-button compact-button">Guardar cambios</button></form></details>' : "";
    return '<details class="ai-source"><summary><span>' + escapeHtml(item.title) + '</span><span class="ai-source-status">' +
      escapeHtml(sourceStatusLabels[item.status] || item.status) + '</span></summary><p class="ai-source-text">' +
      escapeHtml(item.content) + "</p>" + publish + edit + "</details>";
  }).join("");
  const canAdd = !sources.error && permissions.includes("knowledge.create");
  const pages = Math.max(1, Math.ceil((sources.total || 0) / 12));
  const pagination = pages > 1 ? '<nav class="ai-pagination" aria-label="Páginas de fuentes">' +
    '<button type="button" class="secondary-button" data-ai-page="' + (page - 1) + '"' + (page <= 1 ? " disabled" : "") + '>Anterior</button>' +
    '<span>Página ' + page + ' de ' + pages + '</span><button type="button" class="secondary-button" data-ai-page="' +
    (page + 1) + '"' + (page >= pages ? " disabled" : "") + '>Siguiente</button></nav>' : "";
  const create = canAdd ? '<details class="ai-source-create"><summary>Añadir fuente</summary><form id="ai-source-form">' +
    '<label>Título<input name="title" required maxlength="200" placeholder="Ej. Qué incluye la landing"></label>' +
    '<label>Información para el asistente<textarea name="content" required maxlength="800" rows="5" placeholder="Incluye los datos y condiciones aprobados."></textarea></label>' +
    '<p class="form-error" role="alert"></p><button class="primary-button compact-button">Guardar borrador</button></form></details>' : "";

  return heading + '<div id="ai-settings" class="ai-settings" data-org="' + escapeHtml(organizationId) + '" data-bot="' + escapeHtml(bot.id) +
    '" data-model="' + escapeHtml(selectedModel) + '">' + picker +
    '<div class="ai-settings-grid"><section class="panel ai-panel" aria-label="Modelo"><h4>Modelo de IA</h4>' +
    '<p class="field-hint">' + (ai.enabled ? "IA habilitada en este asistente." : "IA desactivada en este asistente.") +
    '</p>' + model + '</section><section class="panel ai-panel" aria-label="Perfil"><h4>Perfil del negocio</h4>' + profileDetails + profileMarkup +
    '</section></div><section class="panel ai-panel" aria-label="Conocimiento"><h4>Fuentes de conocimiento</h4>' +
    '<p class="field-hint">Las fuentes publicadas pueden usarse en las respuestas del asistente.</p>' +
    '<p class="form-error" id="ai-publish-error" role="alert"></p>' +
    (sources.error ? '<p class="empty">Las fuentes no están disponibles.</p>' : knowledgeItems || '<p class="empty">Aún no hay fuentes en este asistente.</p>') +
    pagination + create + '</section></div>';
}

function mountConfiguration() {
  const root = content.querySelector("#ai-settings");
  if (!root) return;
  const { org, bot, model } = root.dataset;
  const botPath = "/bots/" + encodeURIComponent(bot);
  const sourcesPath = "/organizations/" + encodeURIComponent(org) + botPath + "/knowledge";
  const isCurrent = () => root.isConnected && state.activeOrganization === org && state.view === "configuration";
  const save = async (button, error, operation, confirmation) => {
    if (!isCurrent()) return;
    button.disabled = true;
    error.textContent = "";
    try {
      await operation();
      if (!isCurrent()) return;
      await renderView();
      if (state.activeOrganization === org && state.view === "configuration") showNotice(confirmation);
    } catch (failure) {
      if (isCurrent()) error.textContent = failure.message;
    } finally {
      if (isCurrent()) button.disabled = false;
    }
  };
  const bind = (form, operation, confirmation) => {
    form?.addEventListener("submit", (event) => {
      event.preventDefault();
      const data = new FormData(form);
      void save(form.querySelector("button"), form.querySelector(".form-error"), () => operation(data), confirmation);
    });
  };
  const write = (path, method, data) => api(path, { method, body: JSON.stringify(data) });

  root.querySelector("#ai-config-bot")?.addEventListener("change", (event) => {
    state.configurationBot = event.target.value;
    state.configurationSourcesPage = 1;
    void renderView();
  });
  bind(root.querySelector("#ai-model-form"), (data) => write(botPath + "/ai-model", "PATCH", {
    model: data.get("model") || null,
    expected_model: model || null,
  }), "Modelo guardado.");
  bind(root.querySelector("#ai-profile-form"), (data) => write(botPath + "/business-configuration", "PATCH", {
    business_name: data.get("business_name").trim(),
    description: data.get("description").trim(),
    service_instructions: data.get("service_instructions").trim(),
  }), "Perfil guardado.");
  const sourceFields = (data) => ({
    title: data.get("title").trim(),
    content: data.get("content").trim(),
  });
  bind(root.querySelector("#ai-source-form"), (data) => write(sourcesPath, "POST", sourceFields(data)), "Borrador de conocimiento guardado.");
  root.querySelectorAll("[data-ai-source-id]").forEach((form) => {
    const path = sourcesPath + "/" + encodeURIComponent(form.dataset.aiSourceId);
    bind(form, (data) => write(path, "PATCH", sourceFields(data)), "Fuente actualizada.");
  });
  root.querySelectorAll("[data-ai-publish]").forEach((button) => button.addEventListener("click", () => {
    const path = sourcesPath + "/" + encodeURIComponent(button.dataset.aiPublish) + "/publish";
    void save(button, root.querySelector("#ai-publish-error"), () => api(path, { method: "POST" }), "Fuente publicada.");
  }));
  root.querySelectorAll("[data-ai-page]").forEach((button) => button.addEventListener("click", () => {
    state.configurationBot = bot;
    state.configurationSourcesPage = Number(button.dataset.aiPage);
    void renderView();
  }));
}

let renderGeneration = 0;
async function renderView(initialConversation = null) {
  const ticket = ++renderGeneration;
  window.LuriCRM.close();
  window.LuriConversations.reset();
  const organizationId = state.activeOrganization;
  if (!organizationId) return;
  clearNotice();
  content.innerHTML = '<p class="loading">Cargando información…</p>';
  const renderers = {
    overview: () => renderOverview(organizationId),
    conversations: () => renderConversations(organizationId),
    contacts: () => renderContacts(organizationId),
    team: () => renderTeam(),
    configuration: () => renderConfiguration(organizationId),
  };
  try {
    const markup = await renderers[state.view]();
    if (ticket !== renderGeneration || !state.token || state.activeOrganization !== organizationId) return;
    content.innerHTML = markup;
    if (state.view === "configuration") mountConfiguration();
    if (state.view === "contacts") window.LuriCRM.mount(content);
    if (state.view === "conversations") window.LuriConversations.mount(content, initialConversation);
  } catch (error) {
    if (ticket !== renderGeneration || !state.token) return;
    content.innerHTML = '<p class="empty">No se pudo cargar esta vista. Vuelve a seleccionar la sección para reintentar.</p>';
    showNotice(error.message || "Ocurrió un error inesperado.");
  }
}

document.querySelector("#login-form").addEventListener("submit", login);
document.querySelector("#logout").addEventListener("click", signOut);
createOrganizationButton.addEventListener("click", openOrganizationModal);
document.querySelector("#close-organization-modal").addEventListener("click", closeOrganizationModal);
document.querySelector("#cancel-organization").addEventListener("click", closeOrganizationModal);
document.querySelector("#new-organization-name").addEventListener("input", (event) => {
  const slug = document.querySelector("#new-organization-slug");
  if (!slug.value) slug.value = slugify(event.target.value);
});
organizationForm.addEventListener("submit", createOrganization);
picker.addEventListener("change", async (event) => {
  window.LuriCRM.reset();
  state.activeOrganization = event.target.value;
  sessionStorage.setItem(organizationKey, state.activeOrganization);
  renderOrganizationPicker();
  await renderView();
});
document.querySelectorAll(".nav-item").forEach((button) => button.addEventListener("click", async () => {
  state.view = button.dataset.view;
  document.querySelectorAll(".nav-item").forEach((item) => item.classList.toggle("active", item === button));
  await renderView();
}));

if (state.token) {
  startWorkspace().catch((error) => {
    signOut();
    document.querySelector("#login-error").textContent = error.message;
  });
}

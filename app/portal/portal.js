const storageKey = "luri.portal.access-token";
const organizationKey = "luri.portal.organization-id";

const state = {
  activeOrganization: null,
  organizations: [],
  user: null,
  token: sessionStorage.getItem(storageKey),
  view: "overview",
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
    throw new Error(detail?.detail?.code || detail?.detail || "No se pudo cargar la información.");
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
  sessionStorage.removeItem(storageKey);
  sessionStorage.removeItem(organizationKey);
  state.token = null;
  state.activeOrganization = null;
  state.user = null;
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
  const [result, currentUser] = await Promise.all([api("/organizations"), api("/auth/me")]);
  state.user = currentUser.user;
  state.organizations = result.organizations || [];
  if (!state.organizations.length) {
    throw new Error("No tienes una empresa asignada todavía.");
  }
  const saved = sessionStorage.getItem(organizationKey);
  state.activeOrganization = state.organizations.some((item) => item.id === saved)
    ? saved
    : state.organizations[0].id;
  renderOrganizationPicker();
  createOrganizationButton.hidden = state.user?.role !== "platform_admin";
  loginScreen.hidden = true;
  appShell.hidden = false;
  await renderView();
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
      <article class="panel"><h4>Conversaciones recientes</h4>${table(["Cliente", "Estado", "Último mensaje"], conversationItems.map((item) => `<tr><td>${escapeHtml(item.masked_customer_identifier)}</td><td><span class="status ${escapeHtml(item.status)}">${escapeHtml(item.status)}</span></td><td>${escapeHtml(item.last_message_preview || "Sin mensajes")}</td></tr>`))}</article>
      <article class="panel"><h4>Clientes recientes</h4>${table(["Cliente", "Canal", "Estado"], contactItems.map((item) => `<tr><td>${escapeHtml(item.display_name || "Sin nombre")}</td><td>${escapeHtml(item.channel_type)}</td><td><span class="status ${escapeHtml(item.status)}">${escapeHtml(item.status)}</span></td></tr>`))}</article>
    </div>`;
}

async function renderConversations(organizationId) {
  const result = await loadSafe(`/organizations/${organizationId}/conversations?page_size=50`);
  if (result.error) return `${header("Conversaciones", "Historial de WhatsApp de tu empresa.")}<p class="empty">No tienes permiso para ver conversaciones.</p>`;
  return `${header("Conversaciones", `${result.total} conversaciones de tu empresa.`)}<article class="panel">${table(["Cliente", "Canal", "Estado", "Mensajes", "Última actividad"], result.items.map((item) => `<tr><td>${escapeHtml(item.masked_customer_identifier)}</td><td>${escapeHtml(item.channel_type)}</td><td><span class="status ${escapeHtml(item.status)}">${escapeHtml(item.status)}</span></td><td>${escapeHtml(item.message_count)}</td><td>${escapeHtml(formatDate(item.last_message_at))}</td></tr>`))}</article>`;
}

async function renderContacts(organizationId) {
  const result = await loadSafe(`/organizations/${organizationId}/contacts?page_size=50`);
  if (result.error) return `${header("Clientes", "Contactos que escribieron a tu empresa.")}<p class="empty">No tienes permiso para ver clientes.</p>`;
  return `${header("Clientes", `${result.total} contactos registrados.`)}<article class="panel">${table(["Nombre", "Canal", "Estado", "Creado"], result.items.map((item) => `<tr><td>${escapeHtml(item.display_name || "Sin nombre")}</td><td>${escapeHtml(item.channel_type)}</td><td><span class="status ${escapeHtml(item.status)}">${escapeHtml(item.status)}</span></td><td>${escapeHtml(formatDate(item.created_at))}</td></tr>`))}</article>`;
}

async function renderTeam() {
  const result = await loadSafe("/users");
  if (result.error) return `${header("Equipo", "Usuarios con acceso a tu espacio.")}<p class="empty">No tienes permiso para ver usuarios.</p>`;
  return `${header("Equipo", `${result.total} usuarios con acceso.`)}<article class="panel">${table(["Nombre", "Correo", "Rol", "Estado"], result.users.map((item) => {
    const name = [item.first_name, item.last_name].filter(Boolean).join(" ");
    return `<tr><td>${escapeHtml(name || "Sin nombre")}</td><td>${escapeHtml(item.email)}</td><td>${escapeHtml(item.role)}</td><td><span class="status ${item.status === "active" ? "active" : "archived"}">${escapeHtml(item.status)}</span></td></tr>`;
  }))}</article>`;
}

async function renderConfiguration() {
  const botsResult = await loadSafe("/bots");
  const organization = selectedOrganization();
  const bot = (botsResult.bots || []).find((item) => item.organization_id === organization?.id);
  if (!bot) return `${header("Configuración", "Datos base de tu empresa.")}<p class="empty">Aún no hay un bot configurado para esta empresa.</p>`;
  const result = await loadSafe(`/bots/${bot.id}/business-configuration`);
  const configuration = result.business_configuration;
  if (!configuration) return `${header("Configuración", "Datos base de tu empresa.")}<p class="empty">Completa la configuración comercial del bot para habilitar esta vista.</p>`;
  return `${header("Configuración", "Perfil y operación de tu empresa.")}<article class="panel"><div class="configuration-list"><div><span>Nombre comercial</span><strong>${escapeHtml(configuration.business_name)}</strong></div><div><span>Zona horaria</span><strong>${escapeHtml(configuration.timezone)}</strong></div><div><span>Servicios configurados</span><strong>${escapeHtml(configuration.services?.length ?? 0)}</strong></div><div><span>Métodos de pago</span><strong>${escapeHtml(configuration.payment_methods?.length ?? 0)}</strong></div></div></article>`;
}

async function renderView() {
  const organizationId = state.activeOrganization;
  if (!organizationId) return;
  clearNotice();
  content.innerHTML = '<p class="loading">Cargando información…</p>';
  const renderers = {
    overview: () => renderOverview(organizationId),
    conversations: () => renderConversations(organizationId),
    contacts: () => renderContacts(organizationId),
    team: () => renderTeam(),
    configuration: () => renderConfiguration(),
  };
  try {
    content.innerHTML = await renderers[state.view]();
  } catch (error) {
    content.innerHTML = '<p class="empty">No se pudo cargar esta vista.</p>';
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

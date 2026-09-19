// app.js — MediSync Frontend Controller
// Pure vanilla JS with no build step required.
// Talks to the FastAPI backend defined in /backend.

const API_BASE = window.MEDISYNC_API_BASE || `http://${window.location.hostname || "localhost"}:8000`;

const state = {
  token: localStorage.getItem("medisync_token") || null,
  user: JSON.parse(localStorage.getItem("medisync_user") || "null"),
  notifications: [],
  activeConsultationId: null,
  activeConsultation: null,
  mediaStream: null,
  isCameraOn: true,
  isMicOn: true,
  callTimerInterval: null,
  callSeconds: 0,
  patients: [],
  selectedPatientId: null,
};

// ---------------------------------------------------------------
// API Helper
// ---------------------------------------------------------------
async function api(path, { method = "GET", body, isForm = false } = {}) {
  const headers = {};
  if (state.token) headers["Authorization"] = `Bearer ${state.token}`;
  if (body && !isForm) headers["Content-Type"] = "application/json";

  const res = await fetch(`${API_BASE}${path}`, {
    method,
    headers,
    body: isForm ? body : body ? JSON.stringify(body) : undefined,
  });

  if (res.status === 204) return null;

  let data;
  try {
    data = await res.json();
  } catch {
    data = null;
  }

  if (!res.ok) {
    const message = (data && data.detail) || `Request failed (${res.status})`;
    throw new Error(typeof message === "string" ? message : JSON.stringify(message));
  }
  return data;
}

async function apiLoginForm(email, password) {
  const body = new URLSearchParams();
  body.set("username", email);
  body.set("password", password);
  const res = await fetch(`${API_BASE}/api/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body,
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || "Login failed");
  return data;
}

// ---------------------------------------------------------------
// Toast & Notifications
// ---------------------------------------------------------------
let toastTimer = null;
function showToast(message, type = "normal") {
  const el = document.getElementById("toast");
  el.textContent = message;
  el.className = "toast";
  if (type === "error") el.classList.add("toast-error");
  if (type === "success") el.classList.add("toast-success");
  el.classList.remove("hidden");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.add("hidden"), 3500);
}

async function loadNotifications() {
  if (!state.token) return;
  try {
    const notifs = await api("/api/notifications");
    state.notifications = notifs;
    renderNotifications();
  } catch (err) {
    console.warn("Notifications error:", err);
  }
}

function renderNotifications() {
  const listEl = document.getElementById("notif-list");
  const badgeEl = document.getElementById("notif-badge");
  const unread = state.notifications.filter((n) => !n.is_read);

  if (unread.length > 0) {
    badgeEl.textContent = unread.length;
    badgeEl.classList.remove("hidden");
  } else {
    badgeEl.classList.add("hidden");
  }

  if (state.notifications.length === 0) {
    listEl.innerHTML = `<p class="muted" style="padding: 1rem; text-align: center;">${I18N.t("noNotifications")}</p>`;
    return;
  }

  listEl.innerHTML = "";
  for (const n of state.notifications) {
    const item = document.createElement("div");
    item.className = `notif-item ${n.is_read ? "" : "unread"}`;
    const timeStr = new Date(n.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    item.innerHTML = `
      <div class="notif-item-title">${escapeHtml(n.title)}</div>
      <div class="notif-item-msg">${escapeHtml(n.message)}</div>
      <div class="notif-item-time">${timeStr} · ${n.category.toUpperCase()}</div>
    `;
    item.addEventListener("click", async () => {
      if (!n.is_read) {
        await api(`/api/notifications/${n.id}/read`, { method: "POST" });
        n.is_read = true;
        renderNotifications();
      }
    });
    listEl.appendChild(item);
  }
}

// ---------------------------------------------------------------
// Auth & Session
// ---------------------------------------------------------------
function setSession(token, user) {
  state.token = token;
  state.user = user;
  localStorage.setItem("medisync_token", token);
  localStorage.setItem("medisync_user", JSON.stringify(user));
}

function clearSession() {
  state.token = null;
  state.user = null;
  localStorage.removeItem("medisync_token");
  localStorage.removeItem("medisync_user");
}

function showAuth() {
  document.getElementById("main-app").classList.add("hidden");
  document.getElementById("user-header-info").classList.add("hidden");
  document.getElementById("notif-wrapper").classList.add("hidden");
  document.getElementById("ai-chatbot-widget")?.classList.add("hidden");
  document.getElementById("auth-screen").classList.remove("hidden");
}

function showApp() {
  document.getElementById("auth-screen").classList.add("hidden");
  document.getElementById("main-app").classList.remove("hidden");
  document.getElementById("user-header-info").classList.remove("hidden");
  document.getElementById("notif-wrapper").classList.remove("hidden");

  // User details in header
  document.getElementById("user-name").textContent = state.user.full_name;
  const roleBadge = document.getElementById("user-role-badge");
  roleBadge.textContent = capitalize(state.user.role);
  roleBadge.className = `user-role-pill role-${state.user.role}`;

  // Route to role view
  document.getElementById("patient-view").classList.add("hidden");
  document.getElementById("doctor-view").classList.add("hidden");
  document.getElementById("admin-view").classList.add("hidden");

  if (state.user.role === "doctor" || state.user.role === "clinician") {
    document.getElementById("doctor-view").classList.remove("hidden");
    loadDoctorDashboard();
  } else if (state.user.role === "admin") {
    document.getElementById("admin-view").classList.remove("hidden");
    loadAdminDashboard();
  } else {
    document.getElementById("patient-view").classList.remove("hidden");
    loadPatientDashboard();
  }

  loadNotifications();
  initAiChatbot();
}

// Quick 1-Click Demo Logins
document.getElementById("demo-doctor-btn").addEventListener("click", async () => {
  document.getElementById("login-email").value = "doctor@medisync.local";
  document.getElementById("login-password").value = "DoctorPass123!";
  await executeLogin("doctor@medisync.local", "DoctorPass123!");
});

document.getElementById("demo-patient-btn").addEventListener("click", async () => {
  document.getElementById("login-email").value = "patient@medisync.local";
  document.getElementById("login-password").value = "PatientPass123!";
  await executeLogin("patient@medisync.local", "PatientPass123!");
});

document.getElementById("demo-admin-btn").addEventListener("click", async () => {
  document.getElementById("login-email").value = "admin@medisync.local";
  document.getElementById("login-password").value = "AdminPass123!";
  await executeLogin("admin@medisync.local", "AdminPass123!");
});

async function executeLogin(email, password) {
  const errorEl = document.getElementById("auth-error");
  errorEl.classList.add("hidden");
  try {
    const data = await apiLoginForm(email, password);
    setSession(data.access_token, data.user);
    showToast(`Welcome back, ${data.user.full_name}!`, "success");
    showApp();
  } catch (err) {
    errorEl.textContent = err.message;
    errorEl.classList.remove("hidden");
  }
}

// Auth Forms
document.getElementById("login-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const email = document.getElementById("login-email").value.trim();
  const password = document.getElementById("login-password").value;
  await executeLogin(email, password);
});

document.getElementById("register-patient-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const full_name = document.getElementById("reg-pat-name").value.trim();
  const phone = document.getElementById("reg-pat-phone").value.trim();
  const email = document.getElementById("reg-pat-email").value.trim();
  const password = document.getElementById("reg-pat-password").value;
  const preferred_language = document.getElementById("reg-pat-lang") ? document.getElementById("reg-pat-lang").value : "English";
  const errorEl = document.getElementById("auth-error");
  errorEl.classList.add("hidden");
  try {
    const data = await api("/api/auth/register", {
      method: "POST",
      body: { full_name, phone, email, password, role: "patient", preferred_language },
    });
    setSession(data.access_token, data.user);
    showToast("Patient account created successfully!", "success");
    showApp();
  } catch (err) {
    errorEl.textContent = err.message;
    errorEl.classList.remove("hidden");
  }
});

// Doctor Registration with UIDAI E-KYC
document.getElementById("register-doctor-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const full_name = document.getElementById("reg-doc-name").value.trim();
  const phone = document.getElementById("reg-doc-phone").value.trim();
  const email = document.getElementById("reg-doc-email").value.trim();
  const password = document.getElementById("reg-doc-password").value;
  const registration_number = document.getElementById("reg-doc-regno").value.trim();
  const medical_council = document.getElementById("reg-doc-council").value.trim();
  const specialization = document.getElementById("reg-doc-spec").value;
  const experience_years = parseInt(document.getElementById("reg-doc-exp").value) || 1;
  const clinic_name = document.getElementById("reg-doc-clinic").value.trim();
  const aadhaar_masked = document.getElementById("reg-doc-aadhaar").value.trim();

  // Selected languages
  const checkedBoxes = document.querySelectorAll("#doc-languages-selection input[type='checkbox']:checked");
  const languages = Array.from(checkedBoxes).map((c) => c.value);

  const errorEl = document.getElementById("auth-error");
  errorEl.classList.add("hidden");

  try {
    const data = await api("/api/doctors/register", {
      method: "POST",
      body: {
        email,
        full_name,
        phone,
        password,
        registration_number,
        medical_council,
        specialization,
        experience_years,
        languages,
        clinic_name,
        aadhaar_masked,
        uidai_doc_name: "UIDAI_Aadhaar_Submission.xml",
        degree_doc_name: "Medical_Registration_Cert.pdf",
      },
    });

    setSession(data.access_token, data.user);
    showToast("Doctor application submitted! Verification pending by Admin.", "success");
    showApp();
  } catch (err) {
    errorEl.textContent = err.message;
    errorEl.classList.remove("hidden");
  }
});

document.getElementById("logout-btn").addEventListener("click", () => {
  clearSession();
  showAuth();
});

// Auth Tabs Switcher
document.querySelectorAll(".auth-tab").forEach((tab) => {
  tab.addEventListener("click", () => {
    document.querySelectorAll(".auth-tab").forEach((t) => t.classList.remove("active"));
    tab.classList.add("active");
    const target = tab.dataset.tab;
    document.getElementById("login-form").classList.toggle("hidden", target !== "login");
    document.getElementById("register-patient-form").classList.toggle("hidden", target !== "register-patient");
    document.getElementById("register-doctor-form").classList.toggle("hidden", target !== "register-doctor");
    document.getElementById("auth-error").classList.add("hidden");
  });
});

// Language Switcher Selector (11 Languages)
const langSelect = document.getElementById("lang-select");
langSelect.value = I18N.currentLang;
langSelect.addEventListener("change", (e) => {
  I18N.setLanguage(e.target.value);
  showToast(`Language: ${e.target.options[e.target.selectedIndex].text}`, "normal");
  // Live re-render of currently active views
  if (state.user) {
    if (state.user.role === "patient") {
      searchMatchingDoctors();
      loadPatientPrescriptions();
    } else if (state.user.role === "doctor" || state.user.role === "clinician") {
      loadDoctorDashboard();
    } else if (state.user.role === "admin") {
      loadAdminDashboard();
    }
    renderNotifications();
  }
});

// Notification Bell Click
document.getElementById("notif-bell-btn").addEventListener("click", () => {
  const drawer = document.getElementById("notif-drawer");
  drawer.classList.toggle("hidden");
});

document.getElementById("mark-read-btn").addEventListener("click", async () => {
  await api("/api/notifications/read-all", { method: "POST" });
  for (const n of state.notifications) n.is_read = true;
  renderNotifications();
});

// ---------------------------------------------------------------
// PATIENT VIEW & LANGUAGE MATCHMAKING
// ---------------------------------------------------------------
async function loadPatientDashboard() {
  await searchMatchingDoctors();
  await loadPatientPrescriptions();
  await loadPatientDoctorRequests();
  initAiPatientHero();
}

// Subtab switcher for Patient
document.querySelectorAll("[data-ptab]").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll("[data-ptab]").forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
    const target = btn.dataset.ptab;
    document.getElementById("patient-matchmaker-tab").classList.toggle("hidden", target !== "matchmaker");
    document.getElementById("patient-prescriptions-tab").classList.toggle("hidden", target !== "prescriptions");
    document.getElementById("patient-doctor-requests-tab").classList.toggle("hidden", target !== "doctor-requests");
  });
});

document.getElementById("match-lang-select").addEventListener("change", () => searchMatchingDoctors());
document.getElementById("match-spec-select").addEventListener("change", () => searchMatchingDoctors());

async function searchMatchingDoctors() {
  const lang = document.getElementById("match-lang-select").value;
  const spec = document.getElementById("match-spec-select").value;
  const container = document.getElementById("matched-doctors-list");
  container.innerHTML = `<div class="muted" style="padding: 2rem;">${I18N.t("searchDoctors")}...</div>`;

  try {
    const params = new URLSearchParams();
    if (lang) params.set("language", lang);
    if (spec) params.set("specialization", spec);

    const doctors = await api(`/api/doctors/match?${params.toString()}`);
    container.innerHTML = "";

    if (doctors.length === 0) {
      container.innerHTML = `<div class="muted" style="grid-column: 1 / -1; padding: 2rem; text-align: center;">No verified doctors found matching criteria. Try choosing 'Any Language'.</div>`;
      return;
    }

    for (const doc of doctors) {
      const card = document.createElement("div");
      card.className = "doctor-card";
      const daysStr = (doc.availability_days || ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]).slice(0, 3).join(", ");
      const timeStr = doc.availability_time || "09:00 AM - 05:00 PM";

      card.innerHTML = `
        <div class="doc-header">
          <div>
            <div class="doc-name">${escapeHtml(doc.full_name)}</div>
            <div class="doc-spec">${escapeHtml(doc.specialization)} · ${doc.experience_years} ${I18N.t("experience")}</div>
            <div class="doc-clinic">${escapeHtml(doc.clinic_name || "Telehealth Partner Clinic")}</div>
          </div>
          <span class="match-score-badge">★ ${doc.match_score}% ${I18N.t("matchScore")}</span>
        </div>

        <div>
          <div style="font-size: 0.78rem; font-weight: 700; color: var(--text-muted); margin-bottom: 0.35rem;">
            ${I18N.t("speaks")}:
          </div>
          <div class="tag-cloud">
            ${doc.languages.map((l) => `<span class="tag-lang ${doc.matched_languages.includes(l) ? "highlight" : ""}">${escapeHtml(l)}</span>`).join("")}
          </div>
        </div>

        <div style="font-size: 0.8rem; color: var(--text-body); margin: 0.35rem 0;">
          🕒 <strong>${I18N.t("availability")}:</strong> ${escapeHtml(daysStr)} · ${escapeHtml(timeStr)}
        </div>

        <div style="display: flex; align-items: center; justify-content: space-between; margin-top: 0.5rem; padding-top: 0.75rem; border-top: 1px solid var(--border-light);">
          <span style="font-size: 0.78rem; color: var(--success); font-weight: 600;">✓ ${I18N.t("kycVerified")}</span>
          <button class="btn btn-primary btn-small start-call-btn">
            📹 ${I18N.t("startVideoCall")}
          </button>
        </div>
      `;

      card.querySelector(".start-call-btn").addEventListener("click", () => {
        initiateVideoConsultation({
          doctorId: doc.user_id,
          doctorName: doc.full_name,
          specialization: doc.specialization,
          language: lang || doc.languages[0] || "English",
        });
      });

      container.appendChild(card);
    }
  } catch (err) {
    container.innerHTML = `<div class="error-text">${err.message}</div>`;
  }
}

async function loadPatientPrescriptions() {
  const container = document.getElementById("patient-rx-list");
  container.innerHTML = `<div class="muted" style="padding: 1rem;">Loading your prescriptions...</div>`;
  try {
    const consultations = await api("/api/consultations");
    container.innerHTML = "";

    // Show any pending document requests from doctors
    const pendingDocConsultations = consultations.filter((c) => c.documents_required && !c.documents_verified);
    for (const c of pendingDocConsultations) {
      const alertCard = document.createElement("div");
      alertCard.className = "notice-banner pending";
      alertCard.style.marginBottom = "1rem";
      alertCard.style.display = "flex";
      alertCard.style.alignItems = "center";
      alertCard.style.justifyContent = "space-between";
      alertCard.innerHTML = `
        <div>
          <strong>⚠️ ${I18N.t("documentsRequiredAlert")}</strong>
          <div style="font-size: 0.85rem; margin-top: 0.25rem;">${escapeHtml(c.documents_request_note || "")} (${I18N.t("doctorRole")}: ${escapeHtml(c.doctor_name)})</div>
        </div>
        <button type="button" class="btn btn-primary btn-small upload-doc-btn">
          📤 ${I18N.t("uploadScanLabBtn")}
        </button>
      `;
      alertCard.querySelector(".upload-doc-btn").addEventListener("click", () => {
        window.activeConsultationUploadId = c.id;
        document.getElementById("consult-upload-note").textContent = `Doctor: ${c.doctor_name} — ${c.documents_request_note || "Please upload requested diagnostic scan or lab reports."}`;
        document.getElementById("consultation-upload-modal").classList.remove("hidden");
      });
      container.appendChild(alertCard);
    }

    const rxConsultations = consultations.filter((c) => c.prescription);

    if (rxConsultations.length === 0 && pendingDocConsultations.length === 0) {
      container.innerHTML = `<div class="muted" style="padding: 2rem; text-align: center;">${I18N.t("noPrescriptions")}</div>`;
      return;
    }

    for (const c of rxConsultations) {
      const rx = c.prescription;
      const card = document.createElement("div");
      card.className = "rx-card";
      const dateFormatted = new Date(rx.created_at).toLocaleDateString([], { dateStyle: "long" });

      card.innerHTML = `
        <div class="rx-header">
          <div>
            <h3 style="color: var(--primary); font-size: 1.15rem;">${escapeHtml(rx.doctor_name)}</h3>
            <p class="muted" style="font-size: 0.85rem;">Consultation Date: ${dateFormatted} · Language: ${escapeHtml(c.language_used)}</p>
          </div>
          <div class="rx-symbol">℞</div>
        </div>

        <div style="margin-bottom: 1rem;">
          <h4 style="font-size: 0.82rem; text-transform: uppercase; color: var(--text-muted); margin-bottom: 0.25rem;">
            ${I18N.t("problemTitle")}
          </h4>
          <p style="font-size: 0.92rem; color: var(--text-main);">${escapeHtml(c.problem_description || "Not recorded")}</p>
        </div>

        <div style="margin-bottom: 1.25rem;">
          <h4 style="font-size: 0.82rem; text-transform: uppercase; color: var(--text-muted); margin-bottom: 0.25rem;">
            ${I18N.t("diagnosisCureTitle")}
          </h4>
          <p style="font-size: 0.92rem; color: var(--text-main); font-weight: 500; background: var(--bg-subtle); padding: 0.65rem 0.85rem; border-radius: 6px;">
            ${escapeHtml(c.diagnosis_cure || "Under observation")}
          </p>
        </div>

        <h4 style="font-size: 0.82rem; text-transform: uppercase; color: var(--text-muted); margin-bottom: 0.4rem;">
          ${I18N.t("prescribeMedications")}
        </h4>
        <table class="rx-table">
          <thead>
            <tr>
              <th>${I18N.t("medicineName")}</th>
              <th>${I18N.t("dosage")}</th>
              <th>${I18N.t("frequency")}</th>
              <th>${I18N.t("duration")}</th>
              <th>${I18N.t("foodInstructions")}</th>
            </tr>
          </thead>
          <tbody>
            ${rx.medications.map((m) => `
              <tr>
                <td style="font-weight: 600;">${escapeHtml(m.name)}</td>
                <td>${escapeHtml(m.dosage)}</td>
                <td><span class="tag-lang">${escapeHtml(m.frequency)}</span></td>
                <td>${escapeHtml(m.duration)}</td>
                <td style="font-style: italic;">${escapeHtml(m.instructions)}</td>
              </tr>
            `).join("")}
          </tbody>
        </table>

        ${rx.general_advice ? `
          <div style="margin-top: 1rem; font-size: 0.88rem; color: var(--text-muted);">
            <strong>${I18N.t("generalAdvice")}:</strong> ${escapeHtml(rx.general_advice)}
          </div>
        ` : ""}

        ${c.follow_up_date ? `
          <div style="margin-top: 0.5rem; font-size: 0.85rem; font-weight: 600; color: var(--primary);">
            ${I18N.t("followUpDate")}: ${escapeHtml(c.follow_up_date)}
          </div>
        ` : ""}

        <div style="display: flex; justify-content: flex-end; margin-top: 1.25rem;">
          <button class="btn btn-ghost btn-small" onclick="window.print()">
            🖨️ ${I18N.t("printRx")}
          </button>
        </div>
      `;
      container.appendChild(card);
    }
  } catch (err) {
    container.innerHTML = `<div class="error-text">${err.message}</div>`;
  }
}

async function loadPatientDoctorRequests() {
  const container = document.getElementById("patient-requests-list");
  if (!container) return;
  container.innerHTML = `<div class="muted" style="padding: 1rem;">Loading requested documents...</div>`;
  try {
    const consultations = await api("/api/consultations");
    const requestedConsults = (consultations || []).filter((c) => c.documents_required);

    if (requestedConsults.length === 0) {
      container.innerHTML = `
        <div style="text-align: center; padding: 2.5rem; background: var(--bg-surface); border: 1px solid var(--border-light); border-radius: var(--radius-md);">
          <span style="font-size: 2.5rem; display: block; margin-bottom: 0.75rem;">📑</span>
          <h3 style="font-size: 1.1rem; margin-bottom: 0.4rem; color: var(--text-main);">No Document Requests from Doctors</h3>
          <p class="muted" style="font-size: 0.88rem; max-width: 420px; margin: 0 auto;">
            When a doctor requests diagnostic scans, blood tests, or lab reports before issuing a prescription, they will appear here for you to upload.
          </p>
        </div>
      `;
      return;
    }

    container.innerHTML = "";
    for (const c of requestedConsults) {
      const card = document.createElement("div");
      card.className = "request-doc-card";

      const isVerified = c.documents_verified;
      const statusBadge = isVerified
        ? `<span class="doc-tag verified">✓ ${I18N.t("documentsVerifiedBadge")}</span>`
        : `<span class="doc-tag pending">⏳ ${I18N.t("documentsPendingBadge")}</span>`;

      let uploadedHtml = "";
      if (c.uploaded_documents && c.uploaded_documents.length > 0) {
        uploadedHtml = `
          <div style="margin-top: 0.5rem;">
            <div style="font-weight: 600; font-size: 0.84rem; margin-bottom: 0.35rem; color: var(--text-main);">${I18N.t("uploadedFilesLabel")}:</div>
            <div class="request-doc-uploaded-list">
              ${c.uploaded_documents.map(d => `
                <div class="request-doc-item">
                  <span>📄 <strong>${escapeHtml(d.name || d.doc_type)}</strong> <small class="muted">(${escapeHtml(d.doc_type)})</small></span>
                  ${d.url ? `<a href="${d.url}" target="_blank" class="btn btn-ghost btn-small" style="font-size: 0.76rem;">View / Download</a>` : ''}
                </div>
              `).join("")}
            </div>
          </div>
        `;
      }

      card.innerHTML = `
        <div class="request-doc-header">
          <div class="request-doc-doctor">
            <span>🩺</span>
            <div>
              <div>${escapeHtml(c.doctor_name || "Consulting Doctor")}</div>
              <small class="muted" style="font-size: 0.8rem;">Consultation #${c.id} · ${escapeHtml(c.status || "Scheduled")}</small>
            </div>
          </div>
          <div>${statusBadge}</div>
        </div>

        <div class="request-doc-note-box">
          <strong>Doctor's Request:</strong> ${escapeHtml(c.documents_request_note || "Please upload required diagnostic scan or lab test report.")}
        </div>

        ${uploadedHtml}

        <div style="display: flex; justify-content: flex-end; gap: 0.5rem; margin-top: 0.5rem;">
          <button type="button" class="btn btn-primary btn-small btn-upload-doc-req" data-cid="${c.id}">
            <span>📤</span> ${I18N.t("uploadScanLabBtn")}
          </button>
        </div>
      `;

      card.querySelector(".btn-upload-doc-req").addEventListener("click", () => {
        window.activeConsultationUploadId = c.id;
        document.getElementById("consult-upload-note").textContent = c.documents_request_note
          ? `Doctor's instructions: "${c.documents_request_note}"`
          : "Please attach your diagnostic report file.";
        document.getElementById("consultation-upload-modal").classList.remove("hidden");
      });

      container.appendChild(card);
    }
  } catch (err) {
    container.innerHTML = `<div class="error-text">${escapeHtml(err.message)}</div>`;
  }
}

// ---------------------------------------------------------------
// AI CLINICAL SYMPTOM & SPECIALIZATION CLASSIFIER
// ---------------------------------------------------------------
function classifySymptomToSpecialty(text) {
  const lower = (text || "").toLowerCase();
  if (lower.includes("chest") || lower.includes("heart") || lower.includes("angina") || lower.includes("palpitation") || lower.includes("bp") || lower.includes("hypertension") || lower.includes("cardiac") || lower.includes("cholesterol")) {
    return "Cardiology";
  }
  if (lower.includes("breath") || lower.includes("asthma") || lower.includes("wheez") || lower.includes("lungs") || lower.includes("bronchitis") || lower.includes("pneumonia") || lower.includes("cough")) {
    return "Pulmonology";
  }
  if (lower.includes("rash") || lower.includes("skin") || lower.includes("itch") || lower.includes("acne") || lower.includes("eczema") || lower.includes("psoriasis") || lower.includes("allergy") || lower.includes("dermat")) {
    return "Dermatology";
  }
  if (lower.includes("joint") || lower.includes("bone") || lower.includes("knee") || lower.includes("spine") || lower.includes("back pain") || lower.includes("arthritis") || lower.includes("fracture") || lower.includes("ortho") || lower.includes("shoulder") || lower.includes("sprain")) {
    return "Orthopedics";
  }
  if (lower.includes("child") || lower.includes("kid") || lower.includes("baby") || lower.includes("infant") || lower.includes("newborn") || lower.includes("toddler") || lower.includes("pediatric")) {
    return "Pediatrics";
  }
  if (lower.includes("headache") || lower.includes("migraine") || lower.includes("brain") || lower.includes("neuro") || lower.includes("dizz") || lower.includes("stroke") || lower.includes("numbness") || lower.includes("seizure") || lower.includes("paralysis")) {
    return "Neurology";
  }
  if (lower.includes("period") || lower.includes("menstrual") || lower.includes("pregnancy") || lower.includes("pregnant") || lower.includes("pcos") || lower.includes("pcod") || lower.includes("gynec") || lower.includes("uterus") || lower.includes("fertility")) {
    return "Gynecology";
  }
  if (lower.includes("ear") || lower.includes("throat") || lower.includes("nose") || lower.includes("sinus") || lower.includes("hearing") || lower.includes("tonsil") || lower.includes("ent")) {
    return "ENT";
  }
  return "General Medicine";
}

// ---------------------------------------------------------------
// EMBEDDED AI PATIENT HERO GUIDE (Available from start)
// ---------------------------------------------------------------
let aiHeroInitialized = false;
function initAiPatientHero() {
  if (aiHeroInitialized) return;
  aiHeroInitialized = true;

  const searchInput = document.getElementById("ai-hero-search-input");
  const searchBtn = document.getElementById("ai-hero-search-btn");
  const resultCard = document.getElementById("ai-hero-result-card");
  const chips = document.querySelectorAll("#ai-hero-quick-chips .hero-chip");

  async function performHeroSearch(query, forcedSpec = null) {
    if (!query || !query.trim()) return;
    const spec = forcedSpec || classifySymptomToSpecialty(query);
    const patLang = (state.user && state.user.preferred_language) || document.getElementById("match-lang-select")?.value || "English";

    resultCard.classList.remove("hidden");
    resultCard.innerHTML = `
      <div style="display: flex; align-items: center; gap: 0.5rem; color: var(--primary);">
        <span class="spinner-small" style="display: inline-block; width: 18px; height: 18px; border: 2px solid var(--primary-border); border-top-color: var(--primary); border-radius: 50%; animation: spin 0.8s linear infinite;"></span>
        <span>${I18N.t("aiAnalyzing")} (Matching <strong>${escapeHtml(spec)}</strong> with fluent <strong>${escapeHtml(patLang)}</strong>)</span>
      </div>
    `;

    try {
      const params = new URLSearchParams();
      if (patLang) params.set("language", patLang);
      if (spec) params.set("specialization", spec);

      const doctors = await api(`/api/doctors/match?${params.toString()}`);
      if (!doctors || doctors.length === 0) {
        resultCard.innerHTML = `
          <div style="color: var(--text-muted); font-size: 0.9rem;">
            No doctor directly matching <strong>${escapeHtml(spec)}</strong> in <strong>${escapeHtml(patLang)}</strong> right now. 
            <button type="button" class="btn btn-ghost btn-small" id="btn-hero-fallback-all" style="margin-left: 0.5rem; text-decoration: underline;">
              Show All Available Doctors
            </button>
          </div>
        `;
        document.getElementById("btn-hero-fallback-all")?.addEventListener("click", () => {
          document.getElementById("match-spec-select").value = "";
          document.getElementById("match-lang-select").value = "";
          searchMatchingDoctors();
        });
        return;
      }

      const topDoc = doctors[0];
      const matchScore = topDoc.match_score || 95;
      const isLangMatch = (topDoc.languages || []).some(l => l.toLowerCase() === patLang.toLowerCase());

      resultCard.innerHTML = `
        <div style="display: flex; justify-content: space-between; align-items: flex-start; flex-wrap: wrap; gap: 0.75rem;">
          <div>
            <div style="display: flex; align-items: center; gap: 0.5rem;">
              <span style="font-size: 1.25rem;">🩺</span>
              <span style="font-weight: 800; font-size: 1.05rem; color: var(--text-main);">${escapeHtml(topDoc.full_name)}</span>
              <span class="user-role-pill" style="background: var(--success-bg); color: var(--success); font-size: 0.72rem; padding: 0.15rem 0.45rem;">
                ✓ ${matchScore}% Accurate Match
              </span>
            </div>
            <div style="font-size: 0.86rem; color: var(--text-muted); margin-top: 0.2rem;">
              ${escapeHtml(topDoc.specialization)} · ${topDoc.experience_years} Years Experience · ${escapeHtml(topDoc.clinic_name || "MediSync Care Hub")}
            </div>
            <div style="font-size: 0.82rem; margin-top: 0.35rem;">
              🌐 <strong>Speaks:</strong> ${topDoc.languages.map(l => l.toLowerCase() === patLang.toLowerCase() ? `<span style="background: #e0f2fe; color: #0284c7; padding: 0.1rem 0.4rem; border-radius: 4px; font-weight: 700;">${escapeHtml(l)} (Your Language)</span>` : escapeHtml(l)).join(", ")}
            </div>
            <div style="font-size: 0.82rem; color: var(--text-body); margin-top: 0.25rem;">
              🕒 <strong>Availability:</strong> ${(topDoc.availability_days || []).slice(0, 4).join(", ")} · ${escapeHtml(topDoc.availability_time || "09:00 AM - 05:00 PM")}
            </div>
          </div>

          <div style="display: flex; flex-direction: column; gap: 0.4rem; min-width: 220px;">
            <button type="button" id="hero-instant-connect-btn" class="btn btn-primary" style="font-size: 0.88rem; padding: 0.6rem 1rem;">
              ⚡ ${I18N.t("aiAutoAssign")}
            </button>
            <div style="font-size: 0.74rem; color: var(--text-muted); text-align: center;">
              Auto-registers you to ${escapeHtml(topDoc.full_name)}'s queue
            </div>
          </div>
        </div>
      `;

      document.getElementById("hero-instant-connect-btn")?.addEventListener("click", async () => {
        try {
          const newConsult = await api("/api/consultations", {
            method: "POST",
            body: {
              patient_id: state.user.id,
              doctor_id: topDoc.user_id,
              language_used: isLangMatch ? patLang : (topDoc.languages[0] || "English"),
              problem_description: query,
            },
          });
          resultCard.innerHTML = `
            <div style="display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 0.75rem;">
              <div>
                <div style="color: var(--success); font-weight: 700; font-size: 0.95rem;">
                  ✓ Consultation Confirmed! You are added to ${escapeHtml(topDoc.full_name)}'s queue.
                </div>
                <div class="muted" style="font-size: 0.82rem; margin-top: 0.2rem;">
                  Doctor has received your clinical condition: "${escapeHtml(query)}"
                </div>
              </div>
              <button type="button" id="hero-start-call-btn" class="btn btn-primary">
                📹 ${I18N.t("startVideoCall")}
              </button>
            </div>
          `;
          document.getElementById("hero-start-call-btn")?.addEventListener("click", () => {
            openVideoRoom({
              consultationId: newConsult.id,
              patientId: state.user.id,
              doctorId: topDoc.user_id,
              participantName: topDoc.full_name,
              subtitle: `${topDoc.specialization} · Verified Clinician`,
              avatar: "👨‍⚕️",
            });
          });
          await loadPatientPrescriptions();
        } catch (err) {
          showToast(err.message, "error");
        }
      });
    } catch (err) {
      resultCard.innerHTML = `<div class="error-text">${escapeHtml(err.message)}</div>`;
    }
  }

  if (searchBtn) {
    searchBtn.addEventListener("click", () => {
      const q = searchInput ? searchInput.value.trim() : "";
      performHeroSearch(q);
    });
  }

  if (searchInput) {
    searchInput.addEventListener("keypress", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        performHeroSearch(searchInput.value.trim());
      }
    });
  }

  chips.forEach((chip) => {
    chip.addEventListener("click", () => {
      const disease = chip.dataset.disease;
      const spec = chip.dataset.spec;
      if (searchInput) searchInput.value = disease;
      performHeroSearch(disease, spec);
    });
  });
}

// ---------------------------------------------------------------
// DOCTOR VIEW & AVAILABILITY
// ---------------------------------------------------------------
async function loadDoctorDashboard() {
  await checkDoctorKycStatus();
  await loadDoctorAvailability();
  await loadDoctorConsultationsQueue();
  await loadDoctorPatientList();
}

// Doctor Subtab switcher
document.querySelectorAll("[data-dtab]").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll("[data-dtab]").forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
    const target = btn.dataset.dtab;
    document.getElementById("doc-queue-tab").classList.toggle("hidden", target !== "queue");
    document.getElementById("doc-records-tab").classList.toggle("hidden", target !== "records");
  });
});

async function checkDoctorKycStatus() {
  const banner = document.getElementById("doctor-kyc-banner");
  const bannerText = document.getElementById("doctor-kyc-banner-text");
  try {
    const doctors = await api("/api/doctors");
    const myDoc = doctors.find((d) => d.user_id === state.user.id);
    if (myDoc) {
      if (myDoc.kyc_status === "verified") {
        banner.className = "notice-banner verified";
        bannerText.textContent = I18N.t("kycVerifiedBanner");
      } else if (myDoc.kyc_status === "rejected") {
        banner.className = "notice-banner danger";
        bannerText.textContent = `UIDAI E-KYC Rejected. Reason: ${myDoc.verification_notes || "Please re-upload credentials."}`;
      } else {
        banner.className = "notice-banner pending";
        bannerText.textContent = I18N.t("kycPendingBanner");
      }
    }
  } catch (err) {
    console.warn("KYC status error:", err);
  }
}

async function loadDoctorAvailability() {
  try {
    const doctors = await api("/api/doctors");
    const myDoc = doctors.find((d) => d.user_id === state.user.id);
    if (myDoc) {
      const days = (myDoc.availability_days || ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]).join(", ");
      const hours = myDoc.availability_time || "09:00 AM - 05:00 PM";
      const display = document.getElementById("doctor-schedule-display");
      if (display) display.textContent = `${days} · ${hours}`;
    }
  } catch (err) {
    console.warn("Doctor availability load error:", err);
  }
}

// Doctor Availability Modal Handling
document.getElementById("btn-edit-doctor-schedule")?.addEventListener("click", () => {
  document.getElementById("doctor-schedule-modal").classList.remove("hidden");
});

document.getElementById("close-schedule-modal-btn")?.addEventListener("click", () => {
  document.getElementById("doctor-schedule-modal").classList.add("hidden");
});

document.getElementById("doc-schedule-form")?.addEventListener("submit", async (e) => {
  e.preventDefault();
  const checkedDays = Array.from(document.querySelectorAll("input[name='sched-day']:checked")).map((i) => i.value);
  const start = document.getElementById("sched-start-time").value.trim() || "09:00 AM";
  const end = document.getElementById("sched-end-time").value.trim() || "05:00 PM";
  const availability_time = `${start} - ${end}`;
  try {
    await api("/api/doctors/me/availability", {
      method: "PUT",
      body: { availability_days: checkedDays, availability_time },
    });
    showToast(I18N.t("scheduleUpdated"), "success");
    document.getElementById("doctor-schedule-modal").classList.add("hidden");
    await loadDoctorAvailability();
  } catch (err) {
    showToast(err.message, "error");
  }
});

async function loadDoctorConsultationsQueue() {
  const container = document.getElementById("doc-consultations-list");
  container.innerHTML = `<div class="muted" style="padding: 1rem;">${I18N.t("consultationQueue")}...</div>`;
  try {
    const consultations = await api("/api/consultations");
    container.innerHTML = "";

    if (consultations.length === 0) {
      container.innerHTML = `<div class="muted" style="padding: 2rem; text-align: center;">${I18N.t("noConsultations")}</div>`;
      return;
    }

    for (const c of consultations) {
      const card = document.createElement("div");
      card.className = "rx-card";
      card.innerHTML = `
        <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 0.75rem;">
          <div>
            <h3 style="font-size: 1.1rem; color: var(--text-main);">${I18N.t("rolePatient")}: ${escapeHtml(c.patient_name)}</h3>
            <p class="muted" style="font-size: 0.82rem;">Language: ${escapeHtml(c.language_used)} · Status: ${I18N.t("status" + capitalize(c.status)) || c.status.toUpperCase()}</p>
          </div>
          <div style="display: flex; gap: 0.5rem; align-items: center;">
            ${c.documents_required ? `
              <span class="doc-tag ${c.documents_verified ? 'verified' : 'pending'}">
                ${c.documents_verified ? '✓ ' + I18N.t('documentsVerifiedBadge') : '⏳ ' + I18N.t('documentsPendingBadge')}
              </span>
            ` : ""}
            <span class="user-role-pill ${c.status === 'completed' ? 'role-doctor' : 'role-patient'}">
              ${c.status.toUpperCase()}
            </span>
          </div>
        </div>

        ${c.problem_description ? `
          <div style="font-size: 0.9rem; margin-bottom: 0.5rem;">
            <strong>${I18N.t("problemTitle")}:</strong> ${escapeHtml(c.problem_description)}
          </div>
        ` : ""}

        ${c.diagnosis_cure ? `
          <div style="font-size: 0.9rem; margin-bottom: 0.75rem;">
            <strong>${I18N.t("diagnosisCureTitle")}:</strong> ${escapeHtml(c.diagnosis_cure)}
          </div>
        ` : ""}

        ${c.uploaded_documents && c.uploaded_documents.length > 0 ? `
          <div style="margin: 0.5rem 0; font-size: 0.82rem; background: var(--bg-subtle); padding: 0.5rem 0.75rem; border-radius: 6px;">
            <strong>📄 ${I18N.t("uploadedFilesLabel")}:</strong>
            <div style="margin-top: 0.35rem; display: flex; gap: 0.5rem; flex-wrap: wrap;">
              ${c.uploaded_documents.map((d) => `<span class="doc-tag verified">📎 ${escapeHtml(d.name)} (${d.type})</span>`).join("")}
            </div>
          </div>
        ` : ""}

        <div style="display: flex; gap: 0.75rem; margin-top: 1rem; flex-wrap: wrap;">
          <button class="btn btn-primary btn-small launch-doc-call-btn">
            📹 ${I18N.t("startVideoCall")}
          </button>
          <button class="btn btn-ghost btn-small write-doc-rx-btn">
            📝 ${I18N.t("clinicalNotesDrawer")}
          </button>
          ${!c.documents_required ? `
            <button class="btn btn-ghost btn-small request-doc-btn">
              📑 ${I18N.t("requestScanLab")}
            </button>
          ` : ""}
          ${c.documents_required && c.uploaded_documents && c.uploaded_documents.length > 0 && !c.documents_verified ? `
            <button class="btn btn-success btn-small verify-doc-btn">
              ✅ ${I18N.t("verifyDocumentsBtn")}
            </button>
          ` : ""}
        </div>
      `;

      card.querySelector(".launch-doc-call-btn").addEventListener("click", () => {
        openVideoRoom({
          consultationId: c.id,
          patientId: c.patient_id,
          participantName: c.patient_name,
          subtitle: `Patient · Preferred Language: ${c.language_used}`,
          avatar: "👤",
        });
      });

      card.querySelector(".write-doc-rx-btn").addEventListener("click", () => {
        openVideoRoom({
          consultationId: c.id,
          patientId: c.patient_id,
          participantName: c.patient_name,
          subtitle: `Patient · Preferred Language: ${c.language_used}`,
          avatar: "👤",
        });
      });

      const reqBtn = card.querySelector(".request-doc-btn");
      if (reqBtn) {
        reqBtn.addEventListener("click", async () => {
          try {
            await api(`/api/consultations/${c.id}/request-docs`, {
              method: "POST",
              body: { note: "Please upload required diagnostic scan or blood test reports." },
            });
            showToast("Scan / Lab reports requested from patient!", "success");
            await loadDoctorConsultationsQueue();
          } catch (err) {
            showToast(err.message, "error");
          }
        });
      }

      const verBtn = card.querySelector(".verify-doc-btn");
      if (verBtn) {
        verBtn.addEventListener("click", async () => {
          try {
            await api(`/api/consultations/${c.id}/verify-docs`, {
              method: "POST",
              body: { verified: true, notes: "Doctor verified diagnostic reports." },
            });
            showToast("Diagnostic documents verified and approved!", "success");
            await loadDoctorConsultationsQueue();
          } catch (err) {
            showToast(err.message, "error");
          }
        });
      }

      container.appendChild(card);
    }
  } catch (err) {
    container.innerHTML = `<div class="error-text">${err.message}</div>`;
  }
}

async function loadDoctorPatientList() {
  const container = document.getElementById("doc-patients-grid");
  try {
    const patients = await api("/api/patients");
    container.innerHTML = "";
    if (patients.length === 0) {
      container.innerHTML = `<div class="muted" style="grid-column: 1/-1; padding: 2rem; text-align: center;">${I18N.t("noPatients")}</div>`;
      return;
    }
    for (const p of patients) {
      const card = document.createElement("div");
      card.className = "doctor-card";
      card.innerHTML = `
        <div>
          <h3 style="font-size: 1.05rem;">${escapeHtml(p.full_name)}</h3>
          <p class="muted" style="font-size: 0.82rem;">MRN: ${escapeHtml(p.mrn)} · ${p.gender || "Patient"} · ${p.document_count} records</p>
          ${p.known_allergies && p.known_allergies.length > 0 ? `
            <div style="color: var(--danger); font-size: 0.8rem; font-weight: 600; margin-top: 0.35rem;">
              ⚠️ ${I18N.t("allergiesLabel")}: ${p.known_allergies.join(", ")}
            </div>
          ` : ""}
          ${p.notes ? `
            <p style="font-size: 0.82rem; margin-top: 0.35rem; color: var(--text-body);">${escapeHtml(p.notes)}</p>
          ` : ""}
        </div>
        <div style="display: flex; justify-content: flex-end; margin-top: 0.75rem;">
          <button class="btn btn-primary btn-small doc-call-patient-btn">
            📹 ${I18N.t("startConsultation")}
          </button>
        </div>
      `;
      card.querySelector(".doc-call-patient-btn").addEventListener("click", () => {
        initiateVideoConsultation({
          doctorId: state.user.id,
          doctorName: state.user.full_name,
          patientId: p.id,
          language: "English",
        });
      });
      container.appendChild(card);
    }
  } catch (err) {
    console.warn("Doctor patient list error:", err);
  }
}

// Doctor "Add Patient" Modal Handling
document.getElementById("doc-add-patient-btn")?.addEventListener("click", () => {
  const rnd = Math.floor(1000 + Math.random() * 9000);
  document.getElementById("add-pat-mrn").value = `MRN-${rnd}`;
  document.getElementById("add-pat-name").value = "";
  if (document.getElementById("add-pat-email")) document.getElementById("add-pat-email").value = "";
  if (document.getElementById("add-pat-phone")) document.getElementById("add-pat-phone").value = "";
  if (document.getElementById("add-pat-problem")) document.getElementById("add-pat-problem").value = "";
  document.getElementById("add-pat-dob").value = "1990-01-01";
  document.getElementById("add-pat-allergies").value = "";
  document.getElementById("add-pat-notes").value = "";
  document.getElementById("add-patient-modal").classList.remove("hidden");
});

document.getElementById("close-add-patient-btn")?.addEventListener("click", () => {
  document.getElementById("add-patient-modal").classList.add("hidden");
});

document.getElementById("add-patient-form")?.addEventListener("submit", async (e) => {
  e.preventDefault();
  const mrn = document.getElementById("add-pat-mrn").value.trim();
  const full_name = document.getElementById("add-pat-name").value.trim();
  const email = document.getElementById("add-pat-email") ? document.getElementById("add-pat-email").value.trim() : "";
  const phone = document.getElementById("add-pat-phone") ? document.getElementById("add-pat-phone").value.trim() : "";
  const date_of_birth = document.getElementById("add-pat-dob").value;
  const gender = document.getElementById("add-pat-gender").value;
  const blood_group = document.getElementById("add-pat-blood").value;
  const preferred_language = document.getElementById("add-pat-lang") ? document.getElementById("add-pat-lang").value : "English";
  const allergiesStr = document.getElementById("add-pat-allergies").value.trim();
  const known_allergies = allergiesStr ? allergiesStr.split(",").map((s) => s.trim()) : [];
  const notes = document.getElementById("add-pat-notes").value.trim();
  const initial_problem = document.getElementById("add-pat-problem") ? document.getElementById("add-pat-problem").value.trim() : "";

  try {
    await api("/api/patients", {
      method: "POST",
      body: {
        mrn,
        full_name,
        email,
        phone,
        date_of_birth,
        gender,
        blood_group,
        preferred_language,
        known_allergies,
        notes,
        initial_problem,
      },
    });
    showToast(I18N.t("patientAddedSuccess") + " Synced to Doctor charts & Patient portal.", "success");
    document.getElementById("add-patient-modal").classList.add("hidden");
    await loadDoctorPatientList();
    await loadDoctorConsultationsQueue();
  } catch (err) {
    showToast(err.message, "error");
  }
});

// Doctor Instant Call
document.getElementById("doc-start-instant-call-btn")?.addEventListener("click", async () => {
  const patients = await api("/api/patients");
  if (patients.length > 0) {
    initiateVideoConsultation({
      doctorId: state.user.id,
      patientId: patients[0].id,
      doctorName: state.user.full_name,
      language: "English",
    });
  } else {
    showToast("No patient record available to consult.", "error");
  }
});

// ---------------------------------------------------------------
// ADMIN VIEW & VERIFICATION
// ---------------------------------------------------------------
async function loadAdminDashboard() {
  await loadAdminStats();
  await loadAdminPendingKyc();
  await loadAdminAuditLogs();
  await loadAdminConsultations();
}

// Admin Subtab switcher
document.querySelectorAll("[data-atab]").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll("[data-atab]").forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
    const target = btn.dataset.atab;
    document.getElementById("admin-kyc-tab").classList.toggle("hidden", target !== "kyc");
    document.getElementById("admin-audit-tab").classList.toggle("hidden", target !== "audit");
    document.getElementById("admin-consultations-tab").classList.toggle("hidden", target !== "consultations");
  });
});

async function loadAdminStats() {
  try {
    const stats = await api("/api/admin/stats");
    document.getElementById("stat-total-patients").textContent = stats.total_patients;
    document.getElementById("stat-total-doctors").textContent = stats.total_doctors;
    document.getElementById("stat-pending-kyc").textContent = stats.pending_kyc_count;
    document.getElementById("stat-total-consultations").textContent = stats.total_consultations;
  } catch (err) {
    console.warn("Admin stats error:", err);
  }
}

async function loadAdminPendingKyc() {
  const tbody = document.getElementById("admin-kyc-tbody");
  tbody.innerHTML = `<tr><td colspan="8" class="muted" style="text-align: center;">Loading pending KYC queue...</td></tr>`;
  try {
    const doctors = await api("/api/doctors");
    tbody.innerHTML = "";

    if (doctors.length === 0) {
      tbody.innerHTML = `<tr><td colspan="8" class="muted" style="text-align: center;">No doctors in system.</td></tr>`;
      return;
    }

    for (const doc of doctors) {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td><strong>Dr. ${escapeHtml(doc.full_name)}</strong><br><span class="muted" style="font-size: 0.78rem;">${escapeHtml(doc.email)}</span></td>
        <td><code>${escapeHtml(doc.registration_number)}</code></td>
        <td>${escapeHtml(doc.medical_council)}</td>
        <td>${escapeHtml(doc.specialization)}</td>
        <td>${doc.languages.map((l) => `<span class="tag-lang">${escapeHtml(l)}</span>`).join(" ")}</td>
        <td><code>${escapeHtml(doc.aadhaar_masked || "XXXX-XXXX-0000")}</code></td>
        <td>
          <span style="font-size: 0.8rem; color: var(--primary); font-weight: 600;">📄 Aadhaar XML</span><br>
          <span style="font-size: 0.8rem; color: #2563eb; font-weight: 600;">📜 Council Cert</span>
        </td>
        <td>
          ${doc.kyc_status === "pending" ? `
            <div style="display: flex; gap: 0.4rem;">
              <button class="btn btn-success btn-small kyc-approve-btn">${I18N.t("approveDoctor")}</button>
              <button class="btn btn-danger btn-small kyc-reject-btn">${I18N.t("rejectDoctor")}</button>
            </div>
          ` : `
            <span class="user-role-pill ${doc.kyc_status === 'verified' ? 'role-doctor' : 'role-admin'}">
              ${doc.kyc_status.toUpperCase()}
            </span>
          `}
        </td>
      `;

      const approveBtn = tr.querySelector(".kyc-approve-btn");
      if (approveBtn) {
        approveBtn.addEventListener("click", async () => {
          await api("/api/admin/doctors/verify", {
            method: "POST",
            body: { doctor_id: doc.id, action: "approve", verification_notes: "Aadhaar UIDAI and Medical Council License Verified." },
          });
          showToast(`Dr. ${doc.full_name} verified and approved!`, "success");
          await loadAdminDashboard();
        });
      }

      const rejectBtn = tr.querySelector(".kyc-reject-btn");
      if (rejectBtn) {
        rejectBtn.addEventListener("click", async () => {
          await api("/api/admin/doctors/verify", {
            method: "POST",
            body: { doctor_id: doc.id, action: "reject", verification_notes: "Aadhaar document name mismatch with medical license." },
          });
          showToast(`Dr. ${doc.full_name} KYC rejected.`, "error");
          await loadAdminDashboard();
        });
      }

      tbody.appendChild(tr);
    }
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="8" class="error-text">${err.message}</td></tr>`;
  }
}

async function loadAdminAuditLogs() {
  const tbody = document.getElementById("admin-audit-tbody");
  try {
    const logs = await api("/api/admin/audit-logs");
    tbody.innerHTML = "";
    for (const log of logs) {
      const tr = document.createElement("tr");
      const timeStr = new Date(log.created_at).toLocaleString();
      tr.innerHTML = `
        <td style="white-space: nowrap; font-size: 0.82rem;">${timeStr}</td>
        <td><strong>${escapeHtml(log.actor_name || "System")}</strong></td>
        <td><span class="tag-lang">${escapeHtml(log.action)}</span></td>
        <td>${escapeHtml(log.target_type || "-")}</td>
        <td style="font-size: 0.8rem; color: var(--text-muted);"><code>${JSON.stringify(log.details)}</code></td>
      `;
      tbody.appendChild(tr);
    }
  } catch (err) {
    console.warn("Audit logs error:", err);
  }
}

async function loadAdminConsultations() {
  const container = document.getElementById("admin-consultations-list");
  try {
    const consultations = await api("/api/consultations");
    container.innerHTML = "";
    for (const c of consultations) {
      const card = document.createElement("div");
      card.className = "rx-card";
      card.innerHTML = `
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem;">
          <h4 style="font-size: 1rem;">${escapeHtml(c.patient_name)} ↔ ${escapeHtml(c.doctor_name)}</h4>
          <span class="user-role-pill role-patient">${c.status.toUpperCase()}</span>
        </div>
        <p class="muted" style="font-size: 0.82rem;">Scheduled: ${new Date(c.created_at).toLocaleString()} · Language: ${escapeHtml(c.language_used)}</p>
        ${c.problem_description ? `<p style="font-size: 0.88rem; margin-top: 0.5rem;"><strong>Problem:</strong> ${escapeHtml(c.problem_description)}</p>` : ""}
        ${c.diagnosis_cure ? `<p style="font-size: 0.88rem; margin-top: 0.25rem;"><strong>Diagnosis/Cure:</strong> ${escapeHtml(c.diagnosis_cure)}</p>` : ""}
      `;
      container.appendChild(card);
    }
  } catch (err) {
    console.warn("Admin consultations error:", err);
  }
}

// ---------------------------------------------------------------
// VIDEO CALL & CAMERA ACCESS (WebRTC / getUserMedia)
// ---------------------------------------------------------------
async function initiateVideoConsultation({ doctorId, doctorName, patientId, specialization, language }) {
  try {
    const consultation = await api("/api/consultations", {
      method: "POST",
      body: {
        doctor_id: doctorId,
        patient_id: patientId || state.user.id,
        language_used: language || "English",
        status: "in_progress",
      },
    });

    openVideoRoom({
      consultationId: consultation.id,
      patientId: consultation.patient_id,
      participantName: doctorName || `Dr. ${consultation.doctor_name}`,
      subtitle: `${specialization || "Clinician"} · Telemedicine`,
      avatar: "👨‍⚕️",
    });
  } catch (err) {
    showToast(err.message, "error");
  }
}

async function openVideoRoom({ consultationId, patientId, participantName, subtitle, avatar }) {
  state.activeConsultationId = consultationId;
  try {
    const consultData = await api(`/api/consultations/${consultationId}`);
    state.activeConsultation = consultData;
  } catch {
    state.activeConsultation = null;
  }

  const modal = document.getElementById("video-modal");
  modal.classList.remove("hidden");

  document.getElementById("remote-participant-name").textContent = participantName || "Consulting Doctor";
  document.getElementById("remote-participant-subtitle").textContent = subtitle || "Verified Healthcare Provider";
  document.getElementById("remote-avatar-icon").textContent = avatar || "👨‍⚕️";

  // Pre-fill initial drug row
  const medsList = document.getElementById("incall-medications-list");
  medsList.innerHTML = "";
  addMedicationRow("Paracetamol 650mg", "1 Tablet", "1-0-1 (Morning & Night)", "3 days", "After food");

  // Start Call Elapsed Timer
  state.callSeconds = 0;
  clearInterval(state.callTimerInterval);
  state.callTimerInterval = setInterval(() => {
    state.callSeconds++;
    const mins = String(Math.floor(state.callSeconds / 60)).padStart(2, "0");
    const secs = String(state.callSeconds % 60).padStart(2, "0");
    document.getElementById("call-timer").textContent = `${mins}:${secs}`;
  }, 1000);

  // Acquire Real Camera & Microphone Access via WebRTC getUserMedia
  await startLocalCameraStream();
}

async function startLocalCameraStream() {
  const localVideo = document.getElementById("local-video");
  const camOffBox = document.getElementById("cam-off-placeholder");

  try {
    if (navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {
      state.mediaStream = await navigator.mediaDevices.getUserMedia({
        video: { width: { ideal: 640 }, height: { ideal: 480 } },
        audio: true,
      });
      localVideo.srcObject = state.mediaStream;
      localVideo.classList.remove("hidden");
      camOffBox.classList.add("hidden");
      state.isCameraOn = true;
      state.isMicOn = true;
      showToast(I18N.t("cameraActive"), "success");
    } else {
      throw new Error("getUserMedia not supported in this environment");
    }
  } catch (err) {
    console.warn("Camera access fallback:", err.message);
    localVideo.classList.add("hidden");
    camOffBox.classList.remove("hidden");
    camOffBox.innerHTML = `<span>📷 Virtual Camera Mode (Live Preview)</span>`;
    showToast(I18N.t("cameraError"), "normal");
  }
}

function stopLocalCameraStream() {
  if (state.mediaStream) {
    state.mediaStream.getTracks().forEach((track) => track.stop());
    state.mediaStream = null;
  }
  clearInterval(state.callTimerInterval);
}

// Video Controls
document.getElementById("btn-toggle-cam")?.addEventListener("click", () => {
  if (state.mediaStream) {
    const videoTrack = state.mediaStream.getVideoTracks()[0];
    if (videoTrack) {
      videoTrack.enabled = !videoTrack.enabled;
      state.isCameraOn = videoTrack.enabled;
      document.getElementById("btn-toggle-cam").style.background = state.isCameraOn ? "" : "rgba(220, 38, 38, 0.7)";
      document.getElementById("cam-off-placeholder").classList.toggle("hidden", state.isCameraOn);
    }
  }
});

document.getElementById("btn-toggle-mic")?.addEventListener("click", () => {
  if (state.mediaStream) {
    const audioTrack = state.mediaStream.getAudioTracks()[0];
    if (audioTrack) {
      audioTrack.enabled = !audioTrack.enabled;
      state.isMicOn = audioTrack.enabled;
      document.getElementById("btn-toggle-mic").style.background = state.isMicOn ? "" : "rgba(220, 38, 38, 0.7)";
      showToast(state.isMicOn ? "Microphone Unmuted" : "Microphone Muted", "normal");
    }
  }
});

document.getElementById("btn-end-call")?.addEventListener("click", () => {
  stopLocalCameraStream();
  document.getElementById("video-modal").classList.add("hidden");
  showToast("Consultation Call Ended.", "normal");
});

document.getElementById("close-video-modal-btn")?.addEventListener("click", () => {
  stopLocalCameraStream();
  document.getElementById("video-modal").classList.add("hidden");
});

// Prescription Dynamic Medication Rows
document.getElementById("btn-add-medication-row")?.addEventListener("click", () => {
  addMedicationRow();
});

function addMedicationRow(name = "", dose = "", freq = "", dur = "", inst = "") {
  const container = document.getElementById("incall-medications-list");
  const row = document.createElement("div");
  row.className = "medication-entry-row";
  row.style.display = "flex";
  row.style.flexDirection = "column";
  row.style.gap = "0.4rem";
  row.style.marginBottom = "0.75rem";
  row.style.background = "var(--bg-subtle)";
  row.style.padding = "0.6rem";
  row.style.borderRadius = "6px";

  row.innerHTML = `
    <div style="display: flex; justify-content: space-between; align-items: center;">
      <input type="text" class="med-name" placeholder="Drug Name (e.g. Amoxicillin 500mg)" value="${escapeHtml(name)}" required style="flex: 1; padding: 0.4rem;" />
      <button type="button" class="btn btn-ghost btn-small remove-med-btn" style="color: var(--danger); margin-left: 0.5rem;">✕</button>
    </div>
    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 0.4rem;">
      <input type="text" class="med-dose" placeholder="Dose (1 tab)" value="${escapeHtml(dose)}" style="padding: 0.4rem;" />
      <input type="text" class="med-freq" placeholder="Freq (1-0-1)" value="${escapeHtml(freq)}" style="padding: 0.4rem;" />
    </div>
    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 0.4rem;">
      <input type="text" class="med-dur" placeholder="Duration (5 days)" value="${escapeHtml(dur)}" style="padding: 0.4rem;" />
      <input type="text" class="med-inst" placeholder="Timing (After food)" value="${escapeHtml(inst)}" style="padding: 0.4rem;" />
    </div>
  `;
  row.querySelector(".remove-med-btn").addEventListener("click", () => row.remove());
  container.appendChild(row);
}

// Doctor submits Clinical Diagnosis, Cure Plan & Prescription
document.getElementById("incall-rx-form")?.addEventListener("submit", async (e) => {
  e.preventDefault();
  if (!state.activeConsultationId) {
    showToast("No active consultation session found.", "error");
    return;
  }

  // Verification Gate: Check if documents were required and not verified
  if (state.activeConsultation && state.activeConsultation.documents_required && !state.activeConsultation.documents_verified) {
    showToast(I18N.t("docVerificationBlocked"), "error");
    return;
  }

  const problem_description = document.getElementById("incall-problem").value.trim();
  const diagnosis_cure = document.getElementById("incall-cure").value.trim();
  const general_advice = document.getElementById("incall-advice").value.trim();
  const follow_up_date = document.getElementById("incall-followup").value;

  const rows = document.querySelectorAll("#incall-medications-list .medication-entry-row");
  const medications = [];
  rows.forEach((r) => {
    const name = r.querySelector(".med-name").value.trim();
    const dosage = r.querySelector(".med-dose").value.trim();
    const frequency = r.querySelector(".med-freq").value.trim();
    const duration = r.querySelector(".med-dur").value.trim();
    const instructions = r.querySelector(".med-inst").value.trim();
    if (name) {
      medications.push({ name, dosage, frequency, duration, instructions });
    }
  });

  try {
    await api("/api/consultations/prescribe", {
      method: "POST",
      body: {
        consultation_id: state.activeConsultationId,
        patient_id: state.user.id,
        problem_description,
        diagnosis_cure,
        medications,
        general_advice,
        follow_up_date,
      },
    });

    showToast("Prescription and cure plan issued successfully!", "success");
    if (state.user.role === "doctor") loadDoctorConsultationsQueue();
  } catch (err) {
    showToast(err.message, "error");
  }
});

// ---------------------------------------------------------------
// CONSULTATION DIAGNOSTIC DOCUMENT UPLOAD (Patient)
// ---------------------------------------------------------------
document.getElementById("close-consultation-upload-btn")?.addEventListener("click", () => {
  document.getElementById("consultation-upload-modal").classList.add("hidden");
});

document.getElementById("consultation-upload-form")?.addEventListener("submit", async (e) => {
  e.preventDefault();
  const fileInput = document.getElementById("consult-doc-file");
  const docType = document.getElementById("consult-doc-type").value;
  if (!fileInput.files || fileInput.files.length === 0 || !window.activeConsultationUploadId) return;

  const formData = new FormData();
  formData.append("file", fileInput.files[0]);
  formData.append("doc_type", docType);

  try {
    await api(`/api/consultations/${window.activeConsultationUploadId}/upload-docs`, {
      method: "POST",
      body: formData,
      isForm: true,
    });
    showToast("Diagnostic report uploaded! Doctor will verify before proceeding.", "success");
    document.getElementById("consultation-upload-modal").classList.add("hidden");
    await loadPatientPrescriptions();
    await loadPatientDoctorRequests();
  } catch (err) {
    showToast(err.message, "error");
  }
});

// ---------------------------------------------------------------
// GENERAL DOCUMENT UPLOAD (Patient OCR Timeline)
// ---------------------------------------------------------------
const uploadBtn = document.getElementById("patient-upload-doc-btn");
if (uploadBtn) {
  uploadBtn.addEventListener("click", () => {
    document.getElementById("upload-modal").classList.remove("hidden");
  });
}

document.getElementById("close-upload-modal-btn")?.addEventListener("click", () => {
  document.getElementById("upload-modal").classList.add("hidden");
});

document.getElementById("upload-doc-form")?.addEventListener("submit", async (e) => {
  e.preventDefault();
  const docType = document.getElementById("up-doc-type").value;
  const docDate = document.getElementById("up-doc-date").value;
  const fileInput = document.getElementById("up-doc-file");
  if (!fileInput.files || fileInput.files.length === 0) return;

  const patients = await api("/api/patients");
  if (patients.length === 0) {
    showToast("No patient profile found.", "error");
    return;
  }

  const formData = new FormData();
  formData.append("file", fileInput.files[0]);
  formData.append("doc_type", docType);
  if (docDate) formData.append("document_date", docDate);

  try {
    await api(`/api/documents/upload?patient_id=${patients[0].id}`, {
      method: "POST",
      body: formData,
      isForm: true,
    });
    showToast("Medical file uploaded & processed by OCR engine!", "success");
    document.getElementById("upload-modal").classList.add("hidden");
    await loadPatientDoctorRequests();
  } catch (err) {
    showToast(err.message, "error");
  }
});

// ---------------------------------------------------------------
// AI CLINICAL CHATBOT (Patient & Doctor)
// ---------------------------------------------------------------
function initAiChatbot() {
  const widget = document.getElementById("ai-chatbot-widget");
  const fabBtn = document.getElementById("ai-fab-btn");
  const chatWin = document.getElementById("ai-chat-window");
  const closeBtn = document.getElementById("ai-chat-close-btn");
  const chipsContainer = document.getElementById("ai-quick-chips");
  const messagesContainer = document.getElementById("ai-chat-messages");
  const form = document.getElementById("ai-chat-form");
  const input = document.getElementById("ai-chat-input");

  if (!widget) return;
  widget.classList.remove("hidden");

  fabBtn.onclick = () => {
    chatWin.classList.toggle("hidden");
    if (!chatWin.classList.contains("hidden") && messagesContainer.children.length === 0) {
      renderChatbotWelcome();
    }
  };

  closeBtn.onclick = () => {
    chatWin.classList.add("hidden");
  };

  function renderChatbotWelcome() {
    messagesContainer.innerHTML = "";
    chipsContainer.innerHTML = "";
    const isDoc = state.user && (state.user.role === "doctor" || state.user.role === "clinician");

    const welcomeMsg = isDoc ? I18N.t("aiChatbotWelcomeDoctor") : I18N.t("aiChatbotWelcomePatient");
    appendChatBubble(welcomeMsg, "bot");

    const chips = isDoc
      ? [
          "Set hours: Mon to Fri 9 AM to 5 PM",
          "Available Mon, Wed, Fri 10 AM to 4 PM",
          "Available weekends only 10 AM to 2 PM",
        ]
      : [
          "Fever, cough & cold",
          "Severe chest pain",
          "Child skin rash",
          "Knee & joint pain",
          "Headache & dizziness",
        ];

    chips.forEach((chipText) => {
      const chip = document.createElement("button");
      chip.type = "button";
      chip.className = "ai-chip";
      chip.textContent = chipText;
      chip.onclick = () => {
        input.value = chipText;
        handleChatSubmit(chipText);
      };
      chipsContainer.appendChild(chip);
    });
  }

  function appendChatBubble(text, sender = "bot", extraNode = null) {
    const bubble = document.createElement("div");
    bubble.className = `ai-bubble ${sender === "bot" ? "ai-bubble-bot" : "ai-bubble-user"}`;
    bubble.innerHTML = `<div>${escapeHtml(text)}</div>`;
    if (extraNode) bubble.appendChild(extraNode);
    messagesContainer.appendChild(bubble);
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
    return bubble;
  }

  async function handleChatSubmit(userText) {
    if (!userText || !userText.trim()) return;
    input.value = "";
    appendChatBubble(userText, "user");

    const isDoc = state.user && (state.user.role === "doctor" || state.user.role === "clinician");

    if (isDoc) {
      // Doctor availability schedule parser
      const thinkingBubble = appendChatBubble("Updating your schedule...", "bot");
      setTimeout(async () => {
        let days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"];
        let time = "09:00 AM - 05:00 PM";
        const lower = userText.toLowerCase();

        if (lower.includes("weekend")) {
          days = ["Saturday", "Sunday"];
        } else if (lower.includes("mon, wed, fri") || (lower.includes("mon") && lower.includes("wed"))) {
          days = ["Monday", "Wednesday", "Friday"];
        }

        if (lower.includes("10") && lower.includes("4")) {
          time = "10:00 AM - 04:00 PM";
        } else if (lower.includes("10") && lower.includes("2")) {
          time = "10:00 AM - 02:00 PM";
        }

        try {
          await api("/api/doctors/me/availability", {
            method: "PUT",
            body: { availability_days: days, availability_time: time },
          });
          thinkingBubble.remove();
          appendChatBubble(`${I18N.t("aiScheduleUpdated")} (${days.join(", ")} · ${time})`, "bot");
          await loadDoctorAvailability();
        } catch (err) {
          thinkingBubble.remove();
          appendChatBubble(`Error updating schedule: ${err.message}`, "bot");
        }
      }, 500);
      return;
    }

    // Patient clinical symptom matchmaking
    const thinkingBubble = appendChatBubble(I18N.t("aiAnalyzing"), "bot");

    try {
      const spec = classifySymptomToSpecialty(userText);
      const prefLang = (state.user && state.user.preferred_language) || document.getElementById("match-lang-select")?.value || "English";
      const params = new URLSearchParams();
      if (prefLang) params.set("language", prefLang);
      if (spec) params.set("specialization", spec);

      const doctors = await api(`/api/doctors/match?${params.toString()}`);
      thinkingBubble.remove();

      if (!doctors || doctors.length === 0) {
        appendChatBubble(`No verified specialists currently available for ${spec}. Try choosing 'Any Language' in the matchmaker.`, "bot");
        return;
      }

      const topDoc = doctors[0];
      const matchCard = document.createElement("div");
      matchCard.className = "ai-match-card";
      matchCard.innerHTML = `
        <div style="font-weight: 700; font-size: 0.95rem; color: var(--primary);">${escapeHtml(topDoc.full_name)}</div>
        <div style="font-size: 0.8rem; color: var(--text-muted);">${escapeHtml(topDoc.specialization)} · ${topDoc.experience_years} ${I18N.t("experience")}</div>
        <div style="font-size: 0.78rem; margin: 0.35rem 0;">
          <strong>${I18N.t("speaks")}:</strong> ${topDoc.languages.join(", ")}
        </div>
        <div style="font-size: 0.78rem; margin-bottom: 0.5rem;">
          🕒 <strong>${I18N.t("availability")}:</strong> ${(topDoc.availability_days || []).slice(0, 3).join(", ")} · ${escapeHtml(topDoc.availability_time || "09:00 AM - 05:00 PM")}
        </div>
        <button type="button" class="btn btn-primary btn-small ai-auto-connect-btn" style="width: 100%;">
          ⚡ ${I18N.t("aiAutoAssign")}
        </button>
      `;

      matchCard.querySelector(".ai-auto-connect-btn").addEventListener("click", async () => {
        try {
          const newConsult = await api("/api/consultations", {
            method: "POST",
            body: {
              patient_id: state.user.id,
              doctor_id: topDoc.user_id,
              language_used: topDoc.languages[0] || "English",
              problem_description: userText,
            },
          });
          matchCard.innerHTML = `
            <div style="color: var(--success); font-weight: 700; font-size: 0.88rem; margin-bottom: 0.5rem;">
              ✓ ${I18N.t("aiAutoAssignSuccess")}
            </div>
            <button type="button" class="btn btn-primary btn-small ai-join-now-btn" style="width: 100%;">
              📹 ${I18N.t("startVideoCall")}
            </button>
          `;
          matchCard.querySelector(".ai-join-now-btn").addEventListener("click", () => {
            chatWin.classList.add("hidden");
            openVideoRoom({
              consultationId: newConsult.id,
              patientId: state.user.id,
              doctorId: topDoc.user_id,
              participantName: topDoc.full_name,
              subtitle: `${topDoc.specialization} · Verified Clinician`,
              avatar: "👨‍⚕️",
            });
          });
        } catch (err) {
          showToast(err.message, "error");
        }
      });

      appendChatBubble(`${I18N.t("aiMatchFound")}`, "bot", matchCard);
    } catch (err) {
      thinkingBubble.remove();
      appendChatBubble(`Matchmaking error: ${err.message}`, "bot");
    }
  }

  form.onsubmit = (e) => {
    e.preventDefault();
    handleChatSubmit(input.value.trim());
  };
}

// ---------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------
function escapeHtml(str) {
  if (str == null) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function capitalize(str) {
  if (!str) return "";
  return str.charAt(0).toUpperCase() + str.slice(1);
}

// ---------------------------------------------------------------
// App Initialization
// ---------------------------------------------------------------
window.addEventListener("DOMContentLoaded", () => {
  I18N.applyTranslations();
  if (state.token && state.user) {
    showApp();
  } else {
    showAuth();
  }
});

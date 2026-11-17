// Typed console API client. Types come from src/api/schema.ts, generated from contracts/openapi.yaml.
import type { components } from "./schema";

export type Schemas = components["schemas"];
export type LiveSnapshot = Schemas["LiveSnapshot"];
export type TicketDetail = Schemas["TicketDetail"];
export type EventSummary = Schemas["EventSummary"];
export type Me = Schemas["MeResponse"];
export type LoginResult = Schemas["LoginResponse"];
export type SimPhone = Schemas["SimPhone"];
export type SimMessage = Schemas["SimMessage"];
export type Role = Schemas["RoleEnum"];
export type ValetWork = Schemas["ValetWork"];
export type ValetTask = Schemas["ValetTask"];
export type Dashboard = Schemas["Dashboard"];

/** Rank used only to decide which links to show; the server enforces every permission itself. */
export const ROLE_RANK: Record<Role, number> = { VALET: 0, SUPERVISOR: 1, ADMIN: 2 };
export const atLeast = (me: Me, role: Role) => ROLE_RANK[me.role] >= ROLE_RANK[role];
export const isAdmin = (me: Me) => me.role === "ADMIN";

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    public fields?: Record<string, string[]>,
  ) {
    super(code);
  }
}

function cookie(name: string): string {
  const match = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`));
  return match ? decodeURIComponent(match[1]) : "";
}

let csrfReady: Promise<void> | null = null;
function ensureCsrf(): Promise<void> {
  if (cookie("csrftoken")) return Promise.resolve();
  csrfReady ??= fetch("/api/auth/csrf", { credentials: "same-origin" }).then(() => undefined);
  return csrfReady;
}

async function call<T>(method: string, url: string, body?: unknown, idempotencyKey?: string): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json" };
  if (method !== "GET") {
    await ensureCsrf();
    headers["Content-Type"] = "application/json";
    headers["X-CSRFToken"] = cookie("csrftoken");
    if (idempotencyKey) headers["Idempotency-Key"] = idempotencyKey;
  }
  let response: Response;
  try {
    response = await fetch(url, {
      method,
      headers,
      credentials: "same-origin",
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ApiError(0, "offline");
  }
  const data = response.headers.get("content-type")?.includes("json") ? await response.json() : null;
  if (!response.ok) {
    throw new ApiError(response.status, data?.code ?? (response.status === 404 ? "not_found" : "generic"), data?.fields);
  }
  return data as T;
}

/** Multipart command (file upload): same CSRF and idempotency rules as call(), without a JSON body. */
async function callForm<T>(url: string, form: FormData, idempotencyKey: string): Promise<T> {
  await ensureCsrf();
  let response: Response;
  try {
    response = await fetch(url, { method: "POST", credentials: "same-origin", body: form,
      headers: { Accept: "application/json", "X-CSRFToken": cookie("csrftoken"), "Idempotency-Key": idempotencyKey } });
  } catch {
    throw new ApiError(0, "offline");
  }
  const data = response.headers.get("content-type")?.includes("json") ? await response.json() : null;
  if (!response.ok) throw new ApiError(response.status, data?.code ?? "generic", data?.fields);
  return data as T;
}

export const newKey = () => crypto.randomUUID();

const valetTask = (taskId: number, action: string, key: string, body: unknown = {}) =>
  call<Schemas["OutcomeResponse"]>("POST", `/api/valet/tasks/${taskId}/${action}`, body, key);

export const api = {
  login: (body: Schemas["LoginRequestRequest"]) => call<LoginResult>("POST", "/api/auth/login", body),
  setup: (body: Schemas["SetupRequestRequest"]) => call<LoginResult>("POST", "/api/auth/setup", body),
  // --- valet app: every command needs a key, so a double tap or a retry never repeats an action ---
  valet: {
    work: () => call<ValetWork>("GET", "/api/valet/work"),
    availability: (available: boolean, key: string) =>
      call<Schemas["AvailabilityResponse"]>("POST", "/api/valet/availability", { available }, key),
    intake: (body: Schemas["ValetIntakeRequestRequest"], key: string) =>
      call<Schemas["ValetIntakeResponse"]>("POST", "/api/valet/intake", body, key),
    photo: (ticketId: number, photo: Blob, key: string) => {
      const form = new FormData();
      form.append("photo", photo, "car.jpg");
      return callForm<Schemas["PhotoCountResponse"]>(`/api/valet/tickets/${ticketId}/photo`, form, key);
    },
    receipt: (ticketId: number, received: boolean, key: string) =>
      call<Schemas["ContactStateResponse"]>("POST", `/api/valet/tickets/${ticketId}/receipt`, { received }, key),
    startParking: (ticketId: number, key: string) =>
      call<Schemas["OkResponse"]>("POST", `/api/valet/tickets/${ticketId}/start-parking`, {}, key),
    park: (ticketId: number, body: Schemas["ParkRequestRequest"], key: string) =>
      call<Schemas["TicketStateResponse"]>("POST", `/api/valet/tickets/${ticketId}/park`, body, key),
    offerShown: (taskId: number, key: string) =>
      call<Schemas["OfferShownResponse"]>("POST", `/api/valet/tasks/${taskId}/shown`, {}, key),
    accept: (taskId: number, key: string) => valetTask(taskId, "accept", key),
    decline: (taskId: number, key: string) => valetTask(taskId, "decline", key),
    ready: (taskId: number, key: string) => valetTask(taskId, "ready", key),
    deliver: (taskId: number, key: string) => valetTask(taskId, "deliver", key),
    custodyAck: (taskId: number, key: string) =>
      call<Schemas["OkResponse"]>("POST", `/api/valet/tasks/${taskId}/custody-ack`, {}, key),
    code: (taskId: number, code: string, key: string) =>
      call<Schemas["CodeResponse"]>("POST", `/api/valet/tasks/${taskId}/code`, { code }, key),
    moved: (taskId: number, body: Schemas["ParkRequestRequest"], key: string) =>
      call<Schemas["TicketStateResponse"]>("POST", `/api/valet/tasks/${taskId}/moved`, body, key),
  },
  dashboard: (eventId?: number) => call<Dashboard>("GET", `/api/dashboard${eventId ? `?event=${eventId}` : ""}`),
  // Not replay-stored on the server: the number and the setup code are shown once and kept nowhere else.
  contactCustomer: (ticketId: number) => call<Schemas["ContactResponse"]>("POST", `/api/tickets/${ticketId}/contact`),
  issueSetupCode: (staffId: number) => call<Schemas["SetupCodeResponse"]>("POST", `/api/staff/${staffId}/setup-code`),
  setTeam: (staffId: number, eventId: number, member: boolean, key: string) =>
    call<Schemas["IdResponse"]>("POST", `/api/staff/${staffId}/team`, { event_id: eventId, member }, key),
  assistShift: (shiftId: number, on: boolean, reason: string, key: string) =>
    call<Schemas["ShiftResponse"]>("POST", `/api/shifts/${shiftId}/assist`, { on, reason }, key),
  logout: () => call<Schemas["OkResponse"]>("POST", "/api/auth/logout"),
  me: () => call<Me>("GET", "/api/auth/me"),
  events: () => call<EventSummary[]>("GET", "/api/events/"),
  live: (eventId: number) => call<LiveSnapshot>("GET", `/api/events/${eventId}/live`),
  ticket: (ticketId: number) => call<TicketDetail>("GET", `/api/tickets/${ticketId}`),
  ackAlert: (alertId: number, key: string) =>
    call<Schemas["AlertAckResponse"]>("POST", `/api/alerts/${alertId}/ack`, {}, key),
  startShift: (eventId: number, staffId: number, key: string) =>
    call<Schemas["ShiftResponse"]>("POST", `/api/events/${eventId}/shifts`, { staff_id: staffId }, key),
  endShift: (shiftId: number, key: string) =>
    call<Schemas["ShiftResponse"]>("POST", `/api/shifts/${shiftId}/end`, {}, key),
  ticketAction: (ticketId: number, action: string, body: Record<string, unknown>, key: string) =>
    call<Record<string, unknown>>("POST", `/api/tickets/${ticketId}/${action}`, body, key),
  searchTickets: (eventId: number, q: string) =>
    call<Schemas["TicketSearchRow"][]>("GET", `/api/events/${eventId}/tickets?q=${encodeURIComponent(q)}`),
  outages: () => call<Schemas["OutageStatus"]>("GET", "/api/outages"),
  declareOutage: (reason: string, key: string) =>
    call<Schemas["IdResponse"]>("POST", "/api/outages/whatsapp/declare", { reason }, key),
  relayPhoto: (ticketId: number, photo: File, confirmedVia: string, key: string) => {
    const form = new FormData();
    form.append("photo", photo);
    form.append("confirmed_via", confirmedVia);
    return callForm<Schemas["OkResponse"]>(`/api/tickets/${ticketId}/relay-intake-photo`, form, key);
  },
  reportOutage: (eventId: number, reason: string, key: string) =>
    call<Schemas["OkResponse"]>("POST", `/api/events/${eventId}/outages/report`, { reason }, key),
  endOutage: (reason: string, key: string) =>
    call<Schemas["IdResponse"]>("POST", "/api/outages/whatsapp/end", { reason }, key),
  recordSystemOutage: (eventId: number, body: Schemas["SystemOutageRequestRequest"], key: string) =>
    call<Schemas["IdResponse"]>("POST", `/api/events/${eventId}/outages/system`, body, key),
  people: (eventId: number) => call<Schemas["PersonRow"][]>("GET", `/api/events/${eventId}/people`),
  intakeOnBehalf: (eventId: number, body: Schemas["IntakeOnBehalfRequestRequest"], key: string) =>
    call<Schemas["IdResponse"]>("POST", `/api/events/${eventId}/intake-on-behalf`, body, key),
  reconcileIntake: (eventId: number, body: Schemas["ReconcileIntakeRequestRequest"], key: string) =>
    call<Schemas["IdResponse"]>("POST", `/api/events/${eventId}/reconcile-intake`, body, key),
  incidents: (eventId: number) => call<Schemas["IncidentSummary"][]>("GET", `/api/events/${eventId}/incidents`),
  incident: (id: number) => call<Schemas["IncidentDetail"]>("GET", `/api/incidents/${id}`),
  incidentNote: (id: number, text: string, key: string) =>
    call<Schemas["IdResponse"]>("POST", `/api/incidents/${id}/notes`, { text }, key),
  incidentResolve: (id: number, outcome: string, key: string) =>
    call<Schemas["IdResponse"]>("POST", `/api/incidents/${id}/resolve`, { outcome }, key),
  staff: () => call<Schemas["StaffRow"][]>("GET", "/api/staff"),
  createStaff: (body: Schemas["CreateStaffRequestRequest"], key: string) =>
    call<Schemas["IdResponse"]>("POST", "/api/staff", body, key),
  staffAction: (id: number, action: "role" | "deactivate" | "reactivate", body: Record<string, unknown>, key: string) =>
    call<Schemas["IdResponse"]>("POST", `/api/staff/${id}/${action}`, body, key),
  // Not replay-stored on the server: the URI is a secret shown once.
  venues: () => call<Schemas["VenueRow"][]>("GET", "/api/venues"),
  createEvent: (body: Schemas["CreateEventRequestRequest"], key: string) =>
    call<Schemas["IdResponse"]>("POST", "/api/events", body, key),
  closeEvent: (id: number, key: string) => call<Schemas["IdResponse"]>("POST", `/api/events/${id}/close`, {}, key),
  report: (eventId: number) => call<Schemas["EventReport"]>("GET", `/api/events/${eventId}/report`),
  openingCheck: (eventId: number) => call<Schemas["OpeningCheck"]>("GET", `/api/events/${eventId}/opening-check`),
  deadLetters: () => call<Schemas["DeadLetter"][]>("GET", "/api/ops/dead-letters"),
  replay: (id: number, key: string) => call<Schemas["OkResponse"]>("POST", `/api/ops/dead-letters/${id}/replay`, {}, key),
  carryover: () => call<Schemas["CarryoverRow"][]>("GET", "/api/carryover"),
  config: () => call<Schemas["ConfigResponse"]>("GET", "/api/config"),
  // Every settings save names the version it was based on; a stale one is refused (409 stale_settings).
  saveTimings: (timings: Record<string, number>, version: number, key: string) =>
    call<Schemas["OkResponse"]>("POST", "/api/config/timings", { timings, version }, key),
  saveRetention: (retention_days: Record<string, number>, version: number, key: string) =>
    call<Schemas["OkResponse"]>("POST", "/api/config/retention", { retention_days, version }, key),
  saveTemplates: (overrides: Record<string, Schemas["TemplateCopyRequest"] | null>, version: number, key: string) =>
    call<Schemas["OkResponse"]>("POST", "/api/config/templates", { overrides, version }, key),
  applyRetention: (key: string) => call<Schemas["RetentionResult"]>("POST", "/api/retention/apply", {}, key),
  whatsapp: () => call<Schemas["WhatsAppIntegration"]>("GET", "/api/integrations/whatsapp"),
  // CSV downloads are plain links (the JSON client cannot read text/csv).
  exportUrl: (eventId: number, kind: "tickets" | "guest-phones") => `/api/events/${eventId}/export/${kind}.csv`,
  simOutage: () => call<Schemas["SimOutage"]>("GET", "/api/dev/sim/outage"),
  setSimOutage: (down: boolean) => call<Schemas["SimOutage"]>("POST", "/api/dev/sim/outage", { down }),
  simPhones: () => call<SimPhone[]>("GET", "/api/dev/sim/phones"),
  simMessages: (phone: string) => call<SimMessage[]>("GET", `/api/dev/sim/messages?phone=${encodeURIComponent(phone)}`),
  simSend: (body: Schemas["SimSendRequestRequest"]) => call<Schemas["SimSendResponse"]>("POST", "/api/dev/sim/send", body),
};

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

/** Rank used only to decide which links to show; the server enforces every permission itself. */
export const ROLE_RANK: Record<Role, number> = { VALET: 0, SUPERVISOR: 1, MANAGER: 2, ADMIN: 3, SUPER_ADMIN: 4 };
export const atLeast = (me: Me, role: Role) => ROLE_RANK[me.role] >= ROLE_RANK[role];

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

export const newKey = () => crypto.randomUUID();

export const api = {
  login: (body: Schemas["LoginRequestRequest"]) => call<LoginResult>("POST", "/api/auth/login", body),
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
  issueMfa: (id: number) => call<Schemas["MfaIssueResponse"]>("POST", `/api/staff/${id}/mfa`),
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
  simPhones: () => call<SimPhone[]>("GET", "/api/dev/sim/phones"),
  simMessages: (phone: string) => call<SimMessage[]>("GET", `/api/dev/sim/messages?phone=${encodeURIComponent(phone)}`),
  simSend: (body: Schemas["SimSendRequestRequest"]) => call<Schemas["SimSendResponse"]>("POST", "/api/dev/sim/send", body),
};

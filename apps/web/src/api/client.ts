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
  simPhones: () => call<SimPhone[]>("GET", "/api/dev/sim/phones"),
  simMessages: (phone: string) => call<SimMessage[]>("GET", `/api/dev/sim/messages?phone=${encodeURIComponent(phone)}`),
  simSend: (body: Schemas["SimSendRequestRequest"]) => call<Schemas["SimSendResponse"]>("POST", "/api/dev/sim/send", body),
};

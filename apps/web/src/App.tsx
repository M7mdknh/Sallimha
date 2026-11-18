import { lazy, Suspense, useCallback, useEffect, useState } from "react";

import { ApiError, api, isAdmin, type Me } from "./api/client";
import { LoadFailed, SkeletonRows } from "./components/States";
import { Login } from "./pages/Login";
import { navigate, usePath } from "./router";

// Each role downloads only its own screens (bundle split at the role boundary).
const ValetApp = lazy(() => import("./valet/ValetApp").then((m) => ({ default: m.ValetApp })));
const Console = lazy(() => import("./Console"));

type Session = { status: "loading" } | { status: "anonymous" } | { status: "error" } | { status: "ready"; me: Me };

/** Where each role starts: valets on their work, supervisors on Operations, admins on the Dashboard. */
export const homeFor = (me: Me) => (me.role === "VALET" ? "/work" : isAdmin(me) ? "/dashboard" : "/operations");

export function App() {
  const path = usePath();
  const [session, setSession] = useState<Session>({ status: "loading" });

  const load = useCallback(async () => {
    try {
      setSession({ status: "ready", me: await api.me() });
    } catch (err) {
      setSession(err instanceof ApiError && err.status !== 0 ? { status: "anonymous" } : { status: "error" });
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (session.status === "anonymous" && path !== "/login") navigate("/login", true);
    if (session.status === "ready" && (path === "/login" || path === "/")) navigate(homeFor(session.me), true);
  }, [session, path]);

  if (session.status === "loading") return <main className="page"><SkeletonRows /></main>;
  if (session.status === "error") return <main className="page"><LoadFailed onRetry={load} /></main>;
  if (session.status === "anonymous") return <Login onSignedIn={load} />;

  const me = session.me;
  return (
    <Suspense fallback={<main className="page"><SkeletonRows /></main>}>
      {me.role === "VALET" ? <ValetApp me={me} /> : <Console me={me} path={path} />}
    </Suspense>
  );
}

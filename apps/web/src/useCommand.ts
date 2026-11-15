import { useRef, useState } from "react";

import { ApiError, newKey } from "./api/client";
import { useT } from "./strings";

/** One console command: a stable idempotency key across retries, busy state and a translated problem. */
export function useCommand() {
  const { error } = useT();
  const key = useRef(newKey());
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState("");
  const [done, setDone] = useState(false);

  /** Resolves true on success (after `onSuccess`), false when refused or offline. */
  async function run<T>(fn: (key: string) => Promise<T>, onSuccess?: (value: T) => void): Promise<boolean> {
    setBusy(true);
    setProblem("");
    setDone(false);
    try {
      const result = await fn(key.current);
      key.current = newKey(); // the next submission is a new intended action
      setDone(true);
      onSuccess?.(result);
      return true;
    } catch (err) {
      setProblem(error(err instanceof ApiError ? err.code : "generic"));
      return false;
    } finally {
      setBusy(false);
    }
  }

  return { run, busy, problem, done, setProblem };
}

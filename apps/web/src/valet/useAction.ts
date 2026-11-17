import { useRef, useState } from "react";

import { ApiError, newKey } from "../api/client";
import { useT } from "../strings";

/** One valet action. The idempotency key is kept until the server confirms, so tapping again after a lost reply
 *  repeats nothing; the screen changes only from the server's answer, never optimistically. */
export function useAction(onDone: () => Promise<void> | void) {
  const { verror } = useT();
  const keys = useRef(new Map<string, string>());
  const [busy, setBusy] = useState<string | null>(null);
  const [problem, setProblem] = useState("");

  async function run<T>(name: string, fn: (key: string) => Promise<T>, after?: (value: T) => void): Promise<boolean> {
    if (busy) return false;
    const key = keys.current.get(name) ?? newKey();
    keys.current.set(name, key);
    setBusy(name);
    setProblem("");
    try {
      const value = await fn(key);
      keys.current.delete(name); // the next submission is a new intended action
      after?.(value);
      await onDone();
      return true;
    } catch (err) {
      const code = err instanceof ApiError ? err.code : "generic";
      if (code === "idempotency_mismatch" || (err instanceof ApiError && err.status >= 400 && err.status < 500)) {
        keys.current.delete(name); // refused: a corrected retry is a new action
      }
      setProblem(verror(code));
      if (err instanceof ApiError && err.status === 409) await onDone(); // the situation changed: show it
      return false;
    } finally {
      setBusy(null);
    }
  }
  return { run, busy, problem, setProblem };
}

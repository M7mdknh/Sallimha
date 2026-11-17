import { type FormEvent, useState } from "react";

import { ApiError, api } from "../api/client";
import { setLang } from "../i18n";
import { useT } from "../strings";

/** First sign-in or password reset: the admin-issued one-time code becomes the person's own password. */
function Setup({ onDone, onBack }: { onDone: (name: string) => void; onBack: () => void }) {
  const { t, error } = useT();
  const [username, setUsername] = useState("");
  const [code, setCode] = useState("");
  const [password, setPassword] = useState("");
  const [problem, setProblem] = useState("");
  const [busy, setBusy] = useState(false);
  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setProblem("");
    try {
      await api.setup({ username: username.trim(), code: code.trim(), password });
      onDone(username.trim());
    } catch (err) {
      setProblem(error(err instanceof ApiError ? err.code : "generic"));
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <h1>{t("setupTitle")}</h1>
      <p className="muted">{t("setupHint")}</p>
      <form onSubmit={submit} noValidate>
        <label className="field"><span>{t("identifier")}</span>
          <input type="tel" inputMode="tel" autoComplete="username" dir="ltr" value={username}
            onChange={(e) => setUsername(e.target.value)} /></label>
        <label className="field"><span>{t("setupCode")}</span>
          <input inputMode="numeric" pattern="[0-9]*" autoComplete="one-time-code" dir="ltr" maxLength={12} value={code}
            onChange={(e) => setCode(e.target.value)} /></label>
        <label className="field"><span>{t("newPassword")}</span>
          <input type="password" autoComplete="new-password" dir="ltr" value={password}
            onChange={(e) => setPassword(e.target.value)} aria-describedby="pw-hint" />
          <small id="pw-hint" className="muted">{t("newPasswordHint")}</small></label>
        {problem ? <p className="form-error" role="alert">{problem}</p> : null}
        <button type="submit" className="btn btn-primary btn-block" disabled={busy}>{t("savePassword")}</button>
      </form>
      <button type="button" className="btn btn-quiet" onClick={onBack}>{t("backToSignIn")}</button>
    </>
  );
}

export function Login({ onSignedIn }: { onSignedIn: () => void }) {
  const { t, lang, error } = useT();
  const [mode, setMode] = useState<"signin" | "setup">("signin");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [otp, setOtp] = useState("");
  const [step, setStep] = useState<"password" | "otp">("password");
  const [problem, setProblem] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setProblem("");
    try {
      const result = await api.login({ username: username.trim(), password, ...(step === "password" ? {} : { otp }) });
      if (result.mfa_required) {
        setStep("otp");
      } else if (result.ok) {
        onSignedIn();
      }
    } catch (err) {
      setProblem(error(err instanceof ApiError ? err.code : "generic"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="login">
      <div className="login-card">
        <img className="login-logo" src="/brand/assets/logo-bilingual.svg" alt="سلّمها Sallimha" width={260} height={78} />
        {mode === "setup" ? (
          <Setup onBack={() => setMode("signin")} onDone={(name) => {
            setMode("signin"); setUsername(name); setPassword(""); setNotice(t("setupDone"));
          }} />
        ) : (
          <>
            <h1>{t("signInTitleApp")}</h1>
            <p className="muted">{t("signInHintApp")}</p>
            {notice ? <p className="notice notice-success" role="status">{notice}</p> : null}
            <form onSubmit={submit} noValidate>
              {step === "password" ? (
                <>
                  <label className="field">
                    <span>{t("identifier")}</span>
                    <input autoComplete="username" value={username} onChange={(e) => setUsername(e.target.value)}
                      required dir="ltr" autoCapitalize="none" spellCheck={false} />
                  </label>
                  <label className="field">
                    <span>{t("password")}</span>
                    <input type="password" autoComplete="current-password" value={password}
                      onChange={(e) => setPassword(e.target.value)} required dir="ltr" />
                  </label>
                </>
              ) : (
                <>
                  <p className="muted">{t("otpHint")}</p>
                  <label className="field">
                    <span>{t("otp")}</span>
                    <input inputMode="numeric" autoComplete="one-time-code" pattern="[0-9]*" value={otp}
                      onChange={(e) => setOtp(e.target.value)} required dir="ltr" />
                  </label>
                </>
              )}
              {problem ? <p className="form-error" role="alert">{problem}</p> : null}
              <button type="submit" className="btn btn-primary btn-block" disabled={busy}>
                {busy ? t("signingIn") : t("signIn")}
              </button>
            </form>
            {step === "password" ? (
              <button type="button" className="btn btn-quiet" onClick={() => { setMode("setup"); setNotice(""); setProblem(""); }}>
                {t("firstTime")}
              </button>
            ) : null}
          </>
        )}
        <button type="button" className="btn btn-quiet" onClick={() => setLang(lang === "ar" ? "en" : "ar")}>
          {lang === "ar" ? "English" : "العربية"}
        </button>
      </div>
    </main>
  );
}

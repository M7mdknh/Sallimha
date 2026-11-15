import { type FormEvent, useState } from "react";

import { ApiError, api } from "../api/client";
import { setLang } from "../i18n";
import { useT } from "../strings";

export function Login({ onSignedIn }: { onSignedIn: () => void }) {
  const { t, lang, error } = useT();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [otp, setOtp] = useState("");
  const [step, setStep] = useState<"password" | "otp" | "enrol">("password");
  const [otpUri, setOtpUri] = useState("");
  const [problem, setProblem] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setProblem("");
    try {
      const result = await api.login({ username, password, ...(step === "password" ? {} : { otp }) });
      if (result.mfa_required) {
        setStep(result.mfa_enrolment ? "enrol" : "otp");
        setOtpUri(result.otpauth_uri ?? "");
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
        <h1>{t("signInTitle")}</h1>
        <p className="muted">{t("signInHint")}</p>
        <form onSubmit={submit} noValidate>
          {step === "password" ? (
            <>
              <label className="field">
                <span>{t("username")}</span>
                <input autoComplete="username" value={username} onChange={(e) => setUsername(e.target.value)} required dir="ltr" />
              </label>
              <label className="field">
                <span>{t("password")}</span>
                <input type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required dir="ltr" />
              </label>
            </>
          ) : (
            <>
              <p className="muted">{step === "enrol" ? t("enrolHint") : t("otpHint")}</p>
              {step === "enrol" && otpUri ? (
                <p className="otp-uri">
                  <bdi dir="ltr" className="sl-identifier">{otpUri}</bdi>
                </p>
              ) : null}
              <label className="field">
                <span>{t("otp")}</span>
                <input inputMode="numeric" autoComplete="one-time-code" pattern="[0-9]*" value={otp} onChange={(e) => setOtp(e.target.value)} required dir="ltr" />
              </label>
            </>
          )}
          {problem ? <p className="form-error" role="alert">{problem}</p> : null}
          <button type="submit" className="btn btn-primary btn-block" disabled={busy}>
            {busy ? t("signingIn") : t("signIn")}
          </button>
        </form>
        <button type="button" className="btn btn-quiet" onClick={() => setLang(lang === "ar" ? "en" : "ar")}>
          {lang === "ar" ? "English" : "العربية"}
        </button>
      </div>
    </main>
  );
}

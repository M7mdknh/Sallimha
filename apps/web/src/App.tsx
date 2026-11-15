import { setLang, useLang } from "./i18n";

export function App() {
  const lang = useLang();
  return (
    <>
      <header className="app-header">
        <img
          src={lang === "ar" ? "/brand/assets/logo-ar.svg" : "/brand/assets/logo-en.svg"}
          alt={lang === "ar" ? "سلّمها" : "Sallimha"}
          width={160}
          height={48}
        />
        <button className="lang-switch" type="button" onClick={() => setLang(lang === "ar" ? "en" : "ar")}>
          {lang === "ar" ? "English" : "العربية"}
        </button>
      </header>
      <main className="page">
        <h1>{lang === "ar" ? "لوحة التشغيل" : "Operations console"}</h1>
        <p className="muted">
          {lang === "ar" ? "خدمة صفّ المركبات" : "Valet, handled."} <strong>Sallimha</strong>
        </p>
      </main>
    </>
  );
}

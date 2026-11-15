import { useT } from "../strings";
import { Icon } from "./Icon";

export function StaleBanner({ show }: { show: boolean }) {
  const { t } = useT();
  return (
    <div className="stale" role="status" aria-live="polite" hidden={!show}>
      <Icon name="wifiOff" />
      <span>{t("stale")}</span>
    </div>
  );
}

export function LoadFailed({ onRetry }: { onRetry: () => void }) {
  const { t } = useT();
  return (
    <div className="state-block" role="alert">
      <Icon name="alert" />
      <p>{t("loadFailed")}</p>
      <button type="button" className="btn btn-secondary" onClick={onRetry}>
        <Icon name="refresh" /> {t("retry")}
      </button>
    </div>
  );
}

export function SkeletonRows({ rows = 3 }: { rows?: number }) {
  const { t } = useT();
  return (
    <div className="skeleton" aria-busy="true" aria-label={t("loading")}>
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="skeleton-row" />
      ))}
    </div>
  );
}

export function Empty({ text }: { text: string }) {
  return <p className="empty">{text}</p>;
}

/** Status pill: always icon + label, never colour alone. */
export function StatusPill({ tone, icon, label }: { tone: string; icon: string; label: string }) {
  return (
    <span className={`pill pill-${tone}`}>
      <Icon name={icon} size={16} />
      {label}
    </span>
  );
}

export function Id({ children }: { children: React.ReactNode }) {
  return (
    <bdi dir="ltr" className="sl-identifier">
      {children}
    </bdi>
  );
}

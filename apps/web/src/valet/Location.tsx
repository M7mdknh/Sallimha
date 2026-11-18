import { type FormEvent, lazy, Suspense, useCallback, useEffect, useState } from "react";

import { api, type Schemas, type ValetWork } from "../api/client";
import { Icon } from "../components/Icon";
import { Id } from "../components/States";
import { latinDigits } from "../components/PhoneField";
import { useT } from "../strings";
import type { LatLng } from "./ParkingMap";

const ParkingMap = lazy(() => import("./ParkingMap"));

// Proposed defaults (ADR-0013): a fix older than 30 s is stale; above 50 m it is approximate; above 150 m it is not
// saved unless the valet places the pin.
const STALE_MS = 30_000;
const GOOD_M = 50;
const MAX_M = 150;

type Config = Schemas["MapsConfig"];
let configOnce: Promise<Config> | null = null;
function useMapsConfig(): Config | null {
  const [config, setConfig] = useState<Config | null>(null);
  useEffect(() => {
    configOnce ??= api.mapsConfig().catch(() => ({ configured: false, api_key: "", map_id: "" }));
    let live = true;
    void configOnce.then((c) => { if (live) setConfig(c); });
    return () => { live = false; };
  }, []);
  return config;
}

export type Pin = LatLng & { source: "gps" | "pin"; accuracy: number | null; deviceAt: string | null };
type Fix = { status: "idle" | "locating" | "denied" | "unavailable" | "insecure" }
  | { status: "found"; lat: number; lng: number; accuracy: number; at: number };

/** Browser geolocation only (no Geolocation API). Asked when the valet taps, beside the car; never in the background. */
function useCurrentPosition() {
  const [fix, setFix] = useState<Fix>({ status: "idle" });
  const locate = useCallback(() => {
    if (!window.isSecureContext) return setFix({ status: "insecure" });
    if (!("geolocation" in navigator)) return setFix({ status: "unavailable" });
    setFix({ status: "locating" });
    navigator.geolocation.getCurrentPosition(
      (p) => setFix({ status: "found", lat: p.coords.latitude, lng: p.coords.longitude, accuracy: p.coords.accuracy,
        at: p.timestamp }),
      (err) => setFix({ status: err.code === err.PERMISSION_DENIED ? "denied" : "unavailable" }),
      { enableHighAccuracy: true, timeout: 15_000, maximumAge: 0 });
  }, []);
  return { fix, locate };
}

function fixQuality(fix: Fix): "good" | "approximate" | "too_coarse" | "stale" | null {
  if (fix.status !== "found") return null;
  if (Date.now() - fix.at > STALE_MS) return "stale";
  if (fix.accuracy > MAX_M) return "too_coarse";
  return fix.accuracy > GOOD_M ? "approximate" : "good";
}

export const mapsLink = (p: LatLng) =>
  `https://www.google.com/maps/search/?api=1&query=${p.lat.toFixed(6)}%2C${p.lng.toFixed(6)}`;

/** The map, only when configured and asked for; a failure never blocks anything. */
function MapBlock({ centre, pin, onPin, label }: { centre: LatLng | null; pin: LatLng | null;
  onPin?: (p: LatLng) => void; label: string }) {
  const { t } = useT();
  const config = useMapsConfig();
  const [open, setOpen] = useState(false);
  const [failed, setFailed] = useState(false);
  const fail = useCallback(() => setFailed(true), []);
  const start = pin ?? centre;
  if (config && !config.configured) return <p className="muted small" data-testid="map-state">{t("mapNotConfigured")}</p>;
  if (failed) return <p className="notice notice-warning" data-testid="map-state"><Icon name="alert" /> {t("mapUnavailable")}</p>;
  if (!start) return null;
  if (!open) {
    return (
      <button type="button" className="btn btn-secondary" onClick={() => setOpen(true)} disabled={!config}>
        <Icon name="pin" /> {onPin ? t("mapShowToPlace") : t("mapShow")}
      </button>
    );
  }
  return (
    <div className="map-frame">
      {!pin ? <p className="map-caption"><Icon name="alert" size={16} /> {t("mapVenueCentre")}</p> : null}
      <Suspense fallback={<p className="muted">{t("mapLoading")}</p>}>
        <ParkingMap apiKey={config!.api_key} mapId={config!.map_id} centre={start} pin={pin} onPin={onPin}
          onFailed={fail} label={label} />
      </Suspense>
    </div>
  );
}

export type PlaceBody = Schemas["ParkRequestRequest"];

/** Parking completion: where the car is (zone, floor, spot, a short description, optionally a confirmed pin) and,
 *  kept separate, the key hook. The pin is optional: "Parked" never waits for a position or a map. */
export function LocationPicker({ work, submitLabel, busy, onSubmit }: { work: ValetWork; submitLabel: string;
  busy: boolean; onSubmit: (body: PlaceBody) => void }) {
  const { t, lang, verror } = useT();
  const zones = work.venue?.zones ?? [];
  const [zone, setZone] = useState(zones.length === 1 ? zones[0].code : "");
  const [floor, setFloor] = useState("");
  const [spot, setSpot] = useState("");
  const [note, setNote] = useState("");
  const [hook, setHook] = useState("");
  const [pin, setPin] = useState<Pin | null>(null);
  const [problem, setProblem] = useState("");
  const { fix, locate } = useCurrentPosition();
  const quality = fixQuality(fix);

  useEffect(() => {
    if (fix.status === "found" && (quality === "good" || quality === "approximate")) {
      setPin({ lat: fix.lat, lng: fix.lng, source: "gps", accuracy: Math.round(fix.accuracy * 10) / 10,
        deviceAt: new Date(fix.at).toISOString() });
    }
  }, [fix, quality]);

  function submit(e: FormEvent) {
    e.preventDefault();
    const digits = latinDigits(hook).trim();
    if (!zone) return setProblem(verror("zone_invalid"));
    if (!/^\d+$/.test(digits) || Number(digits) < 1) return setProblem(verror("hook_invalid"));
    setProblem("");
    onSubmit({ zone_code: zone, detail: spot.trim(), floor: floor.trim(), note: note.trim(), hook_number: Number(digits),
      location_source: pin ? pin.source : "",
      ...(pin ? { lat: pin.lat, lng: pin.lng, accuracy_m: pin.source === "gps" ? pin.accuracy : null,
        location_device_at: pin.deviceAt } : {}) });
  }

  const fixText = fix.status === "locating" ? t("locating")
    : fix.status === "denied" ? t("locationDenied")
      : fix.status === "unavailable" ? t("locationUnavailable")
        : fix.status === "insecure" ? t("locationInsecure")
          : quality === "stale" ? t("locationStale")
            : quality === "too_coarse" && fix.status === "found" ? `${t("locationTooCoarse")} ±${Math.round(fix.accuracy)} m`
              : null;

  return (
    <form className="task-form" onSubmit={submit} noValidate data-testid="location-picker">
      <fieldset className="choices">
        <legend>{t("zoneField")}</legend>
        {zones.map((z) => (
          <label key={z.code} className={`choice ${zone === z.code ? "is-on" : ""}`}>
            <input type="radio" name="zone" value={z.code} checked={zone === z.code} onChange={() => setZone(z.code)} />
            <span className="choice-code"><Id>{z.code}</Id></span>
            <span className="choice-label">{lang === "ar" ? z.label_ar : z.label_en}</span>
          </label>
        ))}
      </fieldset>
      <div className="pair">
        <label className="field"><span>{t("floorField")}</span>
          <input dir="auto" value={floor} onChange={(e) => setFloor(e.target.value)} autoComplete="off" maxLength={20}
            placeholder="B1" enterKeyHint="next" /></label>
        <label className="field"><span>{t("spotField")}</span>
          <input dir="ltr" value={spot} onChange={(e) => setSpot(e.target.value)} autoComplete="off" maxLength={80}
            enterKeyHint="next" /></label>
      </div>
      <label className="field"><span>{t("placeNote")}</span>
        <input dir="auto" value={note} onChange={(e) => setNote(e.target.value)} autoComplete="off" maxLength={120}
          placeholder={t("placeNoteExample")} enterKeyHint="next" /></label>

      <div className="pin-block" data-testid="pin-block" data-pin={pin ? pin.source : "none"}>
        {pin ? (
          <p className={`pin-state ${pin.source === "gps" && (pin.accuracy ?? 0) > GOOD_M ? "is-warning" : "is-ok"}`}>
            <Icon name="pin" size={18} />{" "}
            {pin.source === "gps"
              ? <>{(pin.accuracy ?? 0) > GOOD_M ? t("pinApproximate") : t("pinFromDevice")} <Id>±{Math.round(pin.accuracy ?? 0)} m</Id></>
              : t("pinPlaced")}
            <button type="button" className="btn btn-quiet" onClick={() => setPin(null)}
              aria-label={`${t("pinClear")}: ${t("pinPlaced")}`}>{t("pinClear")}</button>
          </p>
        ) : (
          <p className="pin-state muted"><Icon name="pin" size={18} /> {t("pinNone")}</p>
        )}
        {fixText ? <p className="field-hint is-warning" role="status">{fixText}</p> : null}
        <button type="button" className="btn btn-secondary" onClick={locate} disabled={fix.status === "locating"}>
          <Icon name="pin" /> {fix.status === "found" || pin ? t("locateAgain") : t("useMyLocation")}
        </button>
        <MapBlock centre={work.venue?.centre ?? null} pin={pin} label={t("parkTitle")}
          onPin={(p) => setPin({ ...p, source: "pin", accuracy: null, deviceAt: null })} />
      </div>

      <label className="field hook-field"><span>{t("hookField")}</span>
        <input dir="ltr" inputMode="numeric" pattern="[0-9]*" value={hook} onChange={(e) => setHook(e.target.value)}
          autoComplete="off" maxLength={4} enterKeyHint="done" /></label>
      {problem ? <p className="form-error" role="alert">{problem}</p> : null}
      <button type="submit" className="btn btn-primary btn-big" disabled={busy}>
        <Icon name="check" /> {submitLabel}
      </button>
    </form>
  );
}

type Place = Schemas["Place"];

/** On retrieval and moves: the saved place first, in large type; the pin as a map on request and a link out. A pin
 *  never claims a floor or indoor directions: the description does that. */
export function PlaceView({ place, location, hook }: { place: Place | null | undefined; location: string;
  hook: number | null }) {
  const { t } = useT();
  const where = place ? [place.zone, place.floor, place.spot].filter(Boolean).join(" · ") : location;
  return (
    <div className="place" data-testid="place-view">
      <dl className="where">
        <div><dt><Icon name="pin" size={18} /> {t("location")}</dt><dd><Id>{where || "—"}</Id></dd></div>
        <div><dt><Icon name="key" size={18} /> {t("key")}</dt><dd><Id>{hook ?? "—"}</Id></dd></div>
      </dl>
      {place?.note ? <p className="where-note">{place.note}</p> : null}
      {place?.pin ? (
        <div className="where-pin">
          <a className="btn btn-secondary" href={mapsLink(place.pin)} target="_blank" rel="noopener noreferrer">
            <Icon name="pin" /> {t("openInMaps")}
          </a>
          <MapBlock centre={null} pin={place.pin} label={t("location")} />
          <small className="muted">{place.pin.source === "gps" && place.pin.accuracy_m
            ? `${t("pinFromDevice")} ±${Math.round(place.pin.accuracy_m)} m` : t("pinPlaced")} · {t("pinNoFloor")}</small>
        </div>
      ) : null}
    </div>
  );
}

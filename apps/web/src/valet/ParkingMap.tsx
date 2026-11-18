/// <reference types="google.maps" />
// Loaded only when a map is actually shown (React.lazy), so the Maps script never loads on other screens (ADR-0013).
import { AdvancedMarker, APIProvider, Map, Pin, type MapMouseEvent } from "@vis.gl/react-google-maps";
import { useEffect } from "react";

export type LatLng = { lat: number; lng: number };

declare global {
  interface Window { gm_authFailure?: () => void }
}

/** The map itself. The marker carries no customer identifier: nothing about the ticket is sent to Google. `pin` is a
 *  confirmed position; without it the map just opens at the venue centre and shows no marker. */
export default function ParkingMap({ apiKey, mapId, centre, pin, onPin, onFailed, label }: {
  apiKey: string; mapId: string; centre: LatLng; pin: LatLng | null; onPin?: (p: LatLng) => void;
  onFailed: () => void; label: string }) {
  useEffect(() => {
    // A refused key (wrong site, API not enabled, billing) is reported here, not through onError.
    window.gm_authFailure = onFailed;
    return () => { delete window.gm_authFailure; };
  }, [onFailed]);
  const editable = Boolean(onPin);
  return (
    <APIProvider apiKey={apiKey} onError={onFailed}>
      <Map className="parking-map" defaultCenter={pin ?? centre} defaultZoom={pin ? 19 : 17} mapId={mapId || "DEMO_MAP_ID"}
        gestureHandling="greedy" disableDefaultUI clickableIcons={false} aria-label={label}
        onClick={editable ? (e: MapMouseEvent) => { if (e.detail.latLng) onPin?.(e.detail.latLng); } : undefined}>
        {pin ? (
          <AdvancedMarker position={pin} draggable={editable}
            onDragEnd={(e: google.maps.MapMouseEvent) => {
              if (e.latLng) onPin?.({ lat: e.latLng.lat(), lng: e.latLng.lng() });
            }}>
            <Pin background="#62429B" borderColor="#3D2864" glyphColor="#C6A15B" />
          </AdvancedMarker>
        ) : null}
      </Map>
    </APIProvider>
  );
}

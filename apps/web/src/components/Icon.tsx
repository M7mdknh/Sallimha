// One authored icon set: 24-unit grid, 1.75 stroke, round caps. Decorative unless given a label.
const PATHS: Record<string, string> = {
  alert: "M12 3.5 2.8 19.5h18.4L12 3.5Zm0 6v4.5m0 2.7v.1",
  clock: "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18Zm0-13.5V12l3 2",
  car: "M5 16.5h14M6.5 16.5v2m11-2v2M4.5 16.5V12l2-5h11l2 5v4.5M4.5 12h15M8 14.2h.01M16 14.2h.01",
  key: "M14.5 9.5a3.5 3.5 0 1 0-4.6 3.3L4.5 18.2V20h2.2l1-1h1.5v-1.5h1.5L12 16l-.4-.4a3.5 3.5 0 0 0 2.9-6.1Z",
  user: "M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8Zm-7 8.5a7 7 0 0 1 14 0",
  users: "M9 11a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7Zm-6 9a6 6 0 0 1 12 0m1.5-9.2a3.5 3.5 0 1 0 0-6.8M21 20a6 6 0 0 0-3.5-5.5",
  check: "M4.5 12.5 9.5 17.5 19.5 6.5",
  x: "M6 6l12 12M18 6 6 18",
  pin: "M12 21s6.5-5.6 6.5-11a6.5 6.5 0 1 0-13 0c0 5.4 6.5 11 6.5 11Zm0-8.5a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5Z",
  logout: "M14 4.5h4.5v15H14M10 8l-4 4 4 4m-4-4h10",
  wifiOff: "M3 3l18 18M8.5 16.5a5 5 0 0 1 7 0M5 13a9.5 9.5 0 0 1 4-2.2M19 13a9.6 9.6 0 0 0-2.6-1.8M2 9.5a14 14 0 0 1 4.2-2.7M22 9.5A14 14 0 0 0 11 6M12 20h.01",
  message: "M4.5 5.5h15v10h-9l-4.5 3.5v-3.5h-1.5z",
  camera: "M4 8h3l1.5-2h7L17 8h3v11H4zM12 16.5a3 3 0 1 0 0-6 3 3 0 0 0 0 6Z",
  send: "M4 12 20 4l-4.5 16-3.5-6.5L4 12Zm8 1.5L20 4",
  shield: "M12 3 4.5 6v5.5c0 4.4 3.2 8 7.5 9.5 4.3-1.5 7.5-5.1 7.5-9.5V6L12 3Z",
  chevron: "M9 6l6 6-6 6",
  refresh: "M19.5 12a7.5 7.5 0 1 1-2.2-5.3M19.5 4.5v4h-4",
};

export function Icon({ name, label, size = 20 }: { name: keyof typeof PATHS | string; label?: string; size?: number }) {
  return (
    <svg
      className="icon"
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.75}
      strokeLinecap="round"
      strokeLinejoin="round"
      role={label ? "img" : undefined}
      aria-label={label}
      aria-hidden={label ? undefined : true}
    >
      <path d={PATHS[name] ?? PATHS.alert} />
    </svg>
  );
}

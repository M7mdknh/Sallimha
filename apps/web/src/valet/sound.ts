// Optional alert sound for a new offer. Off by default; turning it on is a tap, which also unlocks audio playback.
// The task card is always the way an assignment is discovered; the sound only draws attention to it.
const KEY = "sallimha.sound";
let context: AudioContext | null = null;

export function soundEnabled(): boolean {
  try {
    return window.localStorage.getItem(KEY) === "1";
  } catch {
    return false;
  }
}

export function setSound(on: boolean) {
  try {
    window.localStorage.setItem(KEY, on ? "1" : "0");
  } catch {
    // storage unavailable: the choice lasts until the page closes
  }
  if (on) {
    context ??= new AudioContext();
    void context.resume();
  }
}

export function chime() {
  if (!soundEnabled()) return;
  try {
    context ??= new AudioContext();
    const now = context.currentTime;
    for (const [i, freq] of [880, 1175].entries()) {
      const osc = context.createOscillator();
      const gain = context.createGain();
      osc.frequency.value = freq;
      gain.gain.setValueAtTime(0.0001, now + i * 0.18);
      gain.gain.exponentialRampToValueAtTime(0.25, now + i * 0.18 + 0.02);
      gain.gain.exponentialRampToValueAtTime(0.0001, now + i * 0.18 + 0.16);
      osc.connect(gain).connect(context.destination);
      osc.start(now + i * 0.18);
      osc.stop(now + i * 0.18 + 0.17);
    }
    navigator.vibrate?.([120, 60, 120]);
  } catch {
    // no audio on this device: the card is still shown
  }
}

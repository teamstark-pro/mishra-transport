export type Vehicle = {
  id: string;
  number: string; // vehicle registration number, as entered
  insurer: string; // optional
  expiry: string; // insurance expiry date, yyyy-mm-dd
  addedAt: string; // ISO timestamp
};

const STORAGE_KEY = "fleetline.vehicles.v1";
const DAY = 86_400_000;
const EMPTY: Vehicle[] = [];

/** Days until expiry (0 = today, negative = already expired). */
export function daysLeft(expiry: string, now = new Date()): number {
  const [y, m, d] = expiry.split("-").map(Number);
  if (!y || !m || !d) return NaN;
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const due = new Date(y, m - 1, d);
  return Math.round((due.getTime() - today.getTime()) / DAY);
}

export function normalizeNumber(number: string): string {
  return number.replace(/\s+/g, "").toUpperCase();
}

/* ------------------------------------------------------------------ */
/* localStorage as an external store (useSyncExternalStore-compatible) */
/* ------------------------------------------------------------------ */

let rawCache: string | null = null;
let parsedCache: Vehicle[] = EMPTY;
const listeners = new Set<() => void>();

function read(): Vehicle[] {
  if (typeof window === "undefined") return EMPTY;
  const current = window.localStorage.getItem(STORAGE_KEY);
  if (current !== rawCache) {
    rawCache = current;
    try {
      const parsed = current ? JSON.parse(current) : [];
      parsedCache = Array.isArray(parsed) ? parsed : [];
    } catch {
      parsedCache = EMPTY;
    }
  }
  return parsedCache;
}

export function subscribeVehicles(onChange: () => void): () => void {
  listeners.add(onChange);
  return () => listeners.delete(onChange);
}

export function getVehicles(): Vehicle[] {
  return read();
}

export function getServerVehicles(): Vehicle[] {
  return EMPTY;
}

export function setVehicles(next: Vehicle[]): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
  rawCache = null; // force re-parse on next read
  listeners.forEach((l) => l());
}

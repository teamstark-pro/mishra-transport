"use client";

import { useMemo, useState, useSyncExternalStore } from "react";
import {
  subscribeVehicles,
  getVehicles,
  getServerVehicles,
  setVehicles,
  daysLeft,
  normalizeNumber,
} from "@/lib/vehicles";
import { fetchVehicle, summarize } from "@/lib/api";

type Fetched = ReturnType<typeof summarize> & { number: string };

export default function Home() {
  const vehicles = useSyncExternalStore(
    subscribeVehicles,
    getVehicles,
    getServerVehicles
  );

  const [number, setNumber] = useState("");
  const [insurer, setInsurer] = useState("");
  const [expiry, setExpiry] = useState("");
  const [error, setError] = useState("");
  const [dismissedIds, setDismissedIds] = useState<string[]>([]);

  // API fetch state
  const [fetching, setFetching] = useState(false);
  const [fetched, setFetched] = useState<Fetched | null>(null);
  const [fetchError, setFetchError] = useState("");

  const sorted = useMemo(
    () => vehicles.slice().sort((a, b) => a.expiry.localeCompare(b.expiry)),
    [vehicles]
  );

  // Real alerts: derived only from vehicles the user actually entered
  const urgent = useMemo(
    () =>
      sorted.filter((v) => {
        const d = daysLeft(v.expiry);
        return !isNaN(d) && d <= 30;
      }),
    [sorted]
  );
  const popupVehicle = urgent.find((v) => !dismissedIds.includes(v.id));

  function resetErrors() {
    setError("");
    setFetchError("");
  }

  function resetForm(keepNumber = false) {
    if (!keepNumber) setNumber("");
    setInsurer("");
    setExpiry("");
    setFetched(null);
    resetErrors();
  }

  /** Hit the localhost/Render API with the entered vehicle number. */
  async function handleFetch() {
    const clean = number.trim().toUpperCase();
    if (!clean) {
      setFetchError("Enter the vehicle number first.");
      return;
    }
    setFetching(true);
    setFetchError("");
    try {
      const res = await fetchVehicle(clean);
      if (!res.ok || !res.data) {
        setFetchError(res.error ?? "Lookup failed");
      } else {
        const s = summarize(res.data);
        setFetched({ ...s, number: clean });
        if (s.insuranceExpiry) {
          setExpiry(s.insuranceExpiry.slice(0, 10));
        }
        if (s.insuranceCompany) {
          setInsurer(s.insuranceCompany);
        }
      }
    } catch {
      setFetchError("Could not reach the API. Is the backend running?");
    } finally {
      setFetching(false);
    }
  }

  function handleAdd(e: React.FormEvent) {
    e.preventDefault();
    const clean = number.trim();
    if (!clean) {
      setError("Enter the vehicle number.");
      return;
    }
    if (!expiry) {
      setError("Enter the insurance expiry date.");
      return;
    }
    if (isNaN(daysLeft(expiry))) {
      setError("Expiry date looks invalid.");
      return;
    }
    const dup = vehicles.some(
      (v) => normalizeNumber(v.number) === normalizeNumber(clean)
    );
    if (dup) {
      setError("That vehicle is already added.");
      return;
    }
    setVehicles([
      ...vehicles,
      {
        id: crypto.randomUUID(),
        number: clean,
        insurer: insurer.trim(),
        expiry,
        addedAt: new Date().toISOString(),
      },
    ]);
    resetForm();
  }

  function handleDelete(id: string) {
    setVehicles(vehicles.filter((v) => v.id !== id));
    setDismissedIds((ids) => [...ids, id]);
  }

  return (
    <div className="min-h-screen">
      <header className="border-b border-line bg-bg">
        <div className="mx-auto flex h-16 max-w-3xl items-center px-6">
          <span className="text-sm">
            Mishra <span className="text-ink-soft">Transport Agency</span>
          </span>
        </div>
      </header>

      <main className="mx-auto max-w-3xl px-6 py-12">
        <h1 className="display" style={{ fontSize: "clamp(2.5rem, 7vw, 4.25rem)" }}>
          Track vehicles’ insurance expiry.
        </h1>
        <p className="body mt-4 max-w-md text-ink-soft">
          Enter a vehicle number and press the button. The API fetches the
          insurance company, policy number, owner and expiry — and your site
          reminds you 30 days before anything lapses.
        </p>

        {/* Add form */}
        <form
          onSubmit={handleAdd}
          className="mt-9 border border-line-strong shadow-sm bg-surface"
        >
          <div className="border-b border-line px-4 py-2.5">
            <span className="label">Add vehicle</span>
          </div>

          {/* Step 1: number + fetch from API */}
          <div className="grid gap-4 p-4 sm:grid-cols-[1fr_auto] sm:items-end">
            <label className="block">
              <span className="label block">Vehicle number *</span>
              <input
                value={number}
                onChange={(e) => {
                  setNumber(e.target.value);
                  resetErrors();
                }}
                placeholder="MH 12 AB 4471"
                className="mt-1.5 w-full rounded-md border border-line-strong bg-bg px-3 py-2 text-sm font-semibold uppercase placeholder:font-normal placeholder:normal-case placeholder:text-ink-soft focus:border-ink focus:outline-none"
              />
            </label>
            <button
              type="button"
              onClick={handleFetch}
              disabled={fetching}
              className="rounded-md bg-accent px-5 py-2 text-sm font-semibold text-white hover:bg-[#09407a] disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {fetching ? "Fetching…" : "Fetch from API"}
            </button>
          </div>

          {/* Step 2: fetched details preview */}
          {fetched && (
            <div className="border-y border-line bg-bg px-4 py-3 text-sm">
              <p className="label">Fetched from API · {fetched.number}</p>
              <div className="tabular mt-2 grid gap-x-6 gap-y-1 text-xs sm:grid-cols-2">
                {Object.entries({
                  Maker: [fetched.maker, fetched.model, fetched.variant].filter(Boolean).join(" "),
                  Fuel: fetched.fuel,
                  "Reg. date": fetched.registrationDate,
                  "Insurance company": fetched.insuranceCompany,
                  "Policy no.": fetched.insurancePolicyNo,
                  "Insurance expiry": fetched.insuranceExpiry,
                  "RC expiry": fetched.rcExpiry,
                  Chassis: fetched.chassis,
                  "Linked mobile": fetched.mobile,
                }).flatMap(([k, v]) =>
                  v ? [`${k}: ${v}`] : []
                ).map((line) => (
                  <span key={line}>{line}</span>
                ))}
              </div>
              {fetched.insuranceExpiry ? (
                <p className="mt-2 text-xs font-semibold">
                  Expiry date auto-filled from API ✓
                </p>
              ) : (
                <p className="mt-2 text-xs text-ink-soft">
                  Insurance expiry not found in the API response — please fill it in below.
                </p>
              )}
            </div>
          )}

          {fetchError && (
            <p className="border-y border-line px-4 py-2.5 text-sm font-semibold text-status-danger">
              {fetchError}
            </p>
          )}

          {/* Step 3: expiry + save */}
          <div className="grid gap-4 p-4 sm:grid-cols-[1fr_1fr_150px_auto] sm:items-end">
            <label className="block">
              <span className="label block">Insurer (optional)</span>
              <input
                value={insurer}
                onChange={(e) => {
                  setInsurer(e.target.value);
                  setError("");
                }}
                placeholder="e.g. ICICI Lombard"
                className="mt-1.5 w-full rounded-md border border-line-strong bg-bg px-3 py-2 text-sm placeholder:text-ink-soft focus:border-ink focus:outline-none"
              />
            </label>
            <label className="block sm:col-span-2">
              <span className="label block">Expiry date *</span>
              <input
                type="date"
                value={expiry}
                onChange={(e) => {
                  setExpiry(e.target.value);
                  setError("");
                }}
                className="tabular mt-1.5 w-full rounded-md border border-line-strong bg-bg px-3 py-2 text-sm focus:border-ink focus:outline-none"
              />
            </label>
            <button
              type="submit"
              className="rounded-md bg-accent px-4 py-2 text-sm font-semibold text-white hover:bg-[#1546b8]"
            >
              Add vehicle
            </button>
          </div>
          {error && (
            <p className="border-t border-line px-4 py-2.5 text-sm font-semibold text-status-danger">
              {error}
            </p>
          )}
        </form>

        {/* Saved vehicles */}          <div className="mt-10 border border-line-strong shadow-sm bg-surface">
          <div className="flex items-center justify-between border-b border-line px-4 py-2.5">
            <span className="label">Your vehicles</span>
            {vehicles.length > 0 && (
              <span className="tabular text-xs text-ink-soft">
                {vehicles.length} saved
              </span>
            )
          }
          </div>

          {vehicles.length === 0 ? (
            <p className="px-4 py-12 text-center text-sm text-ink-soft">
              Add a vehicle above to start tracking its insurance.
            </p>
          ) : (
            <ul className="divide-y divide-line">
              {sorted.map((v) => {
                const d = daysLeft(v.expiry);
                const tone =
                  d < 0
                    ? "text-status-danger"
                    : d <= 30
                      ? "text-status-warn"
                      : "text-ink-soft";
                const status =
                  d < 0
                    ? `Expired ${-d}d ago`
                    : d === 0
                      ? "Expires today"
                      : `${d}d left`;
                return (
                  <li key={v.id} className="flex items-center gap-4 px-4 py-3">
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-semibold uppercase">
                        {v.number}
                      </p>
                      <p className="truncate text-xs text-ink-soft">
                        {v.insurer ? `${v.insurer} · ` : ""}
                        <span className="tabular">expires {v.expiry}</span>
                      </p>
                    </div>
                    <span className={`tabular shrink-0 text-xs font-semibold ${tone}`}>
                      {status}
                    </span>
                    <button
                      onClick={() => handleDelete(v.id)}
                      className="shrink-0 rounded-md border border-line-strong px-2 py-1 text-xs font-semibold text-ink-soft hover:border-ink hover:text-ink"
                    >
                      Remove
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      </main>

      {/* Popup alert — appears only for real user-entered vehicles within 30 days */}          {popupVehicle && (
        <div className="fixed bottom-6 right-6 z-20 w-80 max-w-[calc(100vw-3rem)] border border-line-strong bg-surface shadow-[0_8px_24px_rgba(17,24,39,0.12)]">
          <div className="flex items-center justify-between border-b border-line px-4 py-2.5">
            <span className="label">Expiry alert</span>
            <button
              onClick={() =>
                setDismissedIds((ids) => [...ids, popupVehicle.id])
              }
              className="text-xs font-semibold text-ink-soft hover:text-ink"
            >
              Dismiss
            </button>
          </div>
          <div className="px-4 py-4">
            <p className="text-sm font-semibold leading-snug uppercase">
              {popupVehicle.number} —{" "}
              <span className="text-status-danger">
                insurance expires in {daysLeft(popupVehicle.expiry)} days
              </span>
            </p>
            {popupVehicle.insurer && (
              <p className="mt-1 text-xs text-ink-soft">
                Insurer: {popupVehicle.insurer}
              </p>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

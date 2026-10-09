/**
 * URL of the backend API the frontend calls.
 *
 * Local dev: set NEXT_PUBLIC_VEHICLE_API in .env.local.
 * Vercel/Netlify: set NEXT_PUBLIC_VEHICLE_API as a platform environment
 * variable and redeploy — the buildtime value is what gets baked into out/.
 * Fallback is localhost for local-only use.
 */
export const VEHICLE_API =
  process.env.NEXT_PUBLIC_VEHICLE_API || "http://localhost:5001";


export type VehicleLookup = {
  code: number;
  data?: {
    masterData: Record<string, unknown>[];
    result: Record<string, unknown>;
    source: string;
    parivahan_linked_mobile: string;
  };
  error?: string;
};

/** Parse dd/mm/yyyy (Parivahan style) to yyyy-mm-dd; pass through if already ISO. */
function toISODate(v?: string): string | undefined {
  if (!v) return undefined;
  if (/^\d{4}-\d{2}-\d{2}$/.test(v)) return v;
  const m = v.match(/^(\d{2})\/(\d{2})\/(\d{4})$/);
  if (m) return `${m[3]}-${m[2]}-${m[1]}`;
  return undefined;
}

/** Pull the useful fields out of the API's nested result. */
export function summarize(data: NonNullable<VehicleLookup["data"]>) {
  const r = (data.result ?? {}) as Record<string, string | number>;
  const pick = (k: string) =>
    r[k] !== undefined && r[k] !== "" ? String(r[k]) : undefined;
  const firstMaster = data.masterData?.[0] as Record<string, string> | undefined;
  return {
    chassis: pick("chassis"),
    engine: pick("engine"),
    maker: pick("maker_name") ?? firstMaster?.masterMaker,
    model:
      pick("model_name") ??
      firstMaster?.masterModel ??
      firstMaster?.masterMakerModel,
    variant: pick("variant_name") ?? firstMaster?.masterVariant,
    fuel: pick("fuel"),
    registrationDate: toISODate(pick("regDate")),
    insuranceExpiry: toISODate(
      pick("vehicleInsuranceUpto") ?? pick("insurance_upto")
    ),
    insuranceCompany: pick("vehicleInsuranceCompanyName"),
    insurancePolicyNo: pick("vehicleInsurancePolicyNumber"),
    rcExpiry: toISODate(pick("rcExpiryDate")),
    rto: pick("registered_at") ?? pick("rto"),
    mobile: data.parivahan_linked_mobile,
  };
}

/** Unwrap legacy double-nested cache responses ({data:{data:{...}}}). */
function unwrap(d: VehicleLookup): VehicleLookup {
  const inner = d.data as unknown as VehicleLookup | undefined;
  if (inner && typeof inner === "object" && inner.data && (inner.data as { result?: unknown }).result) {
    return inner;
  }
  return d;
}

export async function fetchVehicle(
  vehicleNumber: string
): Promise<{ ok: boolean; data?: VehicleLookup["data"]; error?: string }> {
  const url = `${VEHICLE_API}/fetch?vehicle_number=${encodeURIComponent(
    vehicleNumber
  )}`;
  const res = await fetch(url);
  const json = unwrap((await res.json()) as VehicleLookup);
  if (json.code === 200 && json.data) return { ok: true, data: json.data };
  return { ok: false, error: json.error ?? `API error (${json.code})` };
}

import type { Lang, StringKey } from "./i18n";
import { hasText, translate } from "./i18n";
import type { Ingredient, View, WsError } from "./types";

/** Format a duration in minutes for display. */
export function formatMinutes(lang: Lang, minutes: number | null | undefined): string {
  if (minutes == null || !Number.isFinite(minutes) || minutes <= 0) return "";
  const total = Math.round(minutes);
  const h = Math.floor(total / 60);
  const m = total % 60;
  if (h === 0) return translate(lang, "minutes", { n: m });
  if (m === 0) return translate(lang, "hours", { h });
  return translate(lang, "hours_minutes", { h, m });
}

/** Format an ingredient amount such as 0.5 -> "½" or 1.25 -> "1,25". */
export function formatAmount(lang: Lang, amount: number | null): string {
  if (amount == null) return "";
  const fractions: Record<string, string> = { "0.25": "¼", "0.5": "½", "0.75": "¾" };
  const whole = Math.floor(amount);
  const rest = +(amount - whole).toFixed(2);
  if (fractions[String(rest)]) return `${whole > 0 ? whole : ""}${fractions[String(rest)]}`;
  return amount.toLocaleString(lang === "de" ? "de-DE" : "en-US", { maximumFractionDigits: 2 });
}

export function ingredientQty(lang: Lang, ing: Ingredient): string {
  const qty = [formatAmount(lang, ing.amount), ing.unit ?? ""].filter(Boolean).join(" ");
  if (qty) return qty;
  // Recipes from KitchenOwl carry the amount only in `raw` ("<description> <name>").
  const raw = (ing.raw ?? "").trim();
  const name = (ing.name ?? "").trim();
  if (name && raw.length > name.length && raw.toLowerCase().endsWith(name.toLowerCase()))
    return localQty(lang, raw.slice(0, raw.length - name.length).trim());
  return "";
}

/**
 * A quantity text of the core ("0.75 EL", "1.5 Dose, (400 g)", dot as the
 * decimal mark) in the language of the panel: in German the dot between two
 * digits becomes a comma. Nothing else changes, and notes in brackets stay
 * exactly as they are.
 */
export function localQty(lang: Lang, text: string): string {
  if (lang !== "de" || !text || !text.includes(".")) return text;
  let depth = 0;
  let out = "";
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (c === "(") depth++;
    else if (c === ")" && depth > 0) depth--;
    const digits = /\d/.test(text[i - 1] ?? "") && /\d/.test(text[i + 1] ?? "");
    out += c === "." && depth === 0 && digits ? "," : c;
  }
  return out;
}

/** A plain number of the core ("1.5") in the language of the panel ("1,5"); unreadable text stays as it is. */
export function localNumber(lang: Lang, text: string | number | null | undefined): string {
  if (text == null || text === "") return "";
  const n = typeof text === "number" ? text : Number(String(text).trim());
  if (!Number.isFinite(n)) return String(text);
  return n.toLocaleString(lang === "de" ? "de-DE" : "en-US", { maximumFractionDigits: 2, useGrouping: false });
}

/** Return a short host name for a URL, or the input itself. */
export function hostOf(url: string | null | undefined): string {
  if (!url) return "";
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}

export function isHttpUrl(text: string): boolean {
  try {
    const url = new URL(text.trim());
    return url.protocol === "https:" || url.protocol === "http:";
  } catch {
    return false;
  }
}

/**
 * Text for a Picnic code (a reason of the status, a failed entry or the
 * translation_key `picnic_<code>` of an error), in the language of the panel.
 * Unknown codes fall back to the general Picnic error, never to English.
 */
export function picnicText(lang: Lang, code: string | null | undefined): string {
  const key = `picnic_code_${code ?? ""}`;
  return translate(lang, hasText(key) ? (key as StringKey) : "picnic_code_error");
}

/** Map a WebSocket error to a translated, user friendly message. */
/** `unscheduled_entry` or `plan_entry_lost` from `planner/set_servings` (as code or translation key), else null. */
export function planErrorCode(err: unknown): "unscheduled_entry" | "plan_entry_lost" | null {
  const e = (err ?? {}) as WsError;
  for (const c of [e.code, e.translation_key])
    if (c === "unscheduled_entry" || c === "plan_entry_lost") return c;
  return null;
}

export function errorText(lang: Lang, err: unknown): string {
  const e = (err ?? {}) as WsError;
  // set_servings (0.5.0): the panel has its own words for these two codes.
  const plan = planErrorCode(err);
  if (plan) return translate(lang, plan === "unscheduled_entry" ? "err_unscheduled_entry" : "err_plan_entry_lost");
  switch (e.code) {
    case "source_error":
      return translate(lang, "err_source_error");
    case "source_blocked":
      return translate(lang, "err_source_blocked");
    case "not_found":
      return e.translation_key === "picnic_nothing_to_undo"
        ? picnicText(lang, "nothing_to_undo")
        : translate(lang, "err_not_found");
    case "kitchenowl_error":
      return translate(lang, "err_kitchenowl_error");
    case "kitchenowl_auth":
      return translate(lang, "err_kitchenowl_auth");
    case "picnic_unavailable":
      return e.translation_key?.startsWith("picnic_")
        ? picnicText(lang, e.translation_key.slice(7))
        : translate(lang, "err_picnic_unavailable");
    case "picnic_error":
      return picnicText(lang, e.translation_key?.startsWith("picnic_") ? e.translation_key.slice(7) : "error");
    default:
      return e.message || translate(lang, "err_unknown");
  }
}

/** Parse the panel sub path into a view. */
export function parsePath(path: string): View {
  const parts = path.replace(/^\/+/, "").split("/");
  const decode = (s: string | undefined) => {
    try {
      return decodeURIComponent(s ?? "");
    } catch {
      return "";
    }
  };
  switch (parts[0]) {
    case "collection": {
      const id = Number(parts[1]);
      return parts[1] && Number.isInteger(id) && id > 0 ? { name: "korecipe", id } : { name: "collection" };
    }
    case "planner":
      return { name: "planner" };
    case "shopping":
      return { name: "shopping" };
    case "recipe": {
      const key = decode(parts.slice(1).join("/"));
      return key ? { name: "recipe", key } : { name: "search" };
    }
    case "link": {
      const url = decode(parts.slice(1).join("/"));
      return url ? { name: "recipe", url } : { name: "search" };
    }
    default:
      return { name: "search" };
  }
}

export function viewPath(view: View): string {
  if (view.name === "collection") return "/collection";
  if (view.name === "planner") return "/planner";
  if (view.name === "shopping") return "/shopping";
  if (view.name === "korecipe") return `/collection/${view.id}`;
  if (view.name === "recipe") {
    if (view.key) return `/recipe/${encodeURIComponent(view.key)}`;
    if (view.url) return `/link/${encodeURIComponent(view.url)}`;
  }
  return "/search";
}

// ------------------------------------------------------------------ dates
// Dates are plain "YYYY-MM-DD" strings in local time, like the WebSocket API.

const pad = (n: number) => String(n).padStart(2, "0");

export function isoDate(d: Date): string {
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

export function parseDate(text: string): Date {
  const [y, m, d] = text.split("-").map(Number);
  return new Date(y, (m ?? 1) - 1, d ?? 1);
}

export function addDays(text: string, days: number): string {
  const d = parseDate(text);
  d.setDate(d.getDate() + days);
  return isoDate(d);
}

export function today(): string {
  return isoDate(new Date());
}

/** Monday of the week that holds the given day. */
export function mondayOf(text: string): string {
  const d = parseDate(text);
  return addDays(text, -((d.getDay() + 6) % 7));
}

const locale = (lang: Lang) => (lang === "de" ? "de-DE" : "en-GB");

/** "Mittwoch, 18.11." or "Wednesday 18/11". */
export function formatDay(lang: Lang, text: string, weekday: "long" | "short" = "long"): string {
  return parseDate(text).toLocaleDateString(locale(lang), { weekday, day: "numeric", month: "numeric" });
}

export function weekdayName(lang: Lang, text: string, weekday: "long" | "short" = "long"): string {
  return parseDate(text).toLocaleDateString(locale(lang), { weekday });
}

/** "9.–15. November 2026" style label for a week. */
export function formatWeek(lang: Lang, monday: string): string {
  const a = parseDate(monday);
  const b = parseDate(addDays(monday, 6));
  const fmt = new Intl.DateTimeFormat(locale(lang), { day: "numeric", month: "long", year: "numeric" });
  return fmt.formatRange(a, b);
}

/** Picnic price in cent as text: "1,19 €" in German, "€1.19" in English. */
export function formatPrice(lang: Lang, cents: number | null | undefined): string {
  if (cents == null || !Number.isFinite(cents)) return "";
  return new Intl.NumberFormat(locale(lang), { style: "currency", currency: "EUR" }).format(cents / 100);
}

/** Calendar day ("YYYY-MM-DD") of a moment in the time zone of Home Assistant (browser zone as fallback). */
export function dayIn(when: Date, zone?: string): string {
  if (zone) {
    try {
      // en-CA formats as YYYY-MM-DD.
      return new Intl.DateTimeFormat("en-CA", { timeZone: zone, year: "numeric", month: "2-digit", day: "2-digit" }).format(when);
    } catch {
      /* unknown zone: browser zone */
    }
  }
  return isoDate(when);
}

/**
 * Whole days between an ISO time (UTC) and now, counted in calendar days of
 * Home Assistant: 0 today, 1 yesterday. Null for an unreadable time; never below 0.
 */
export function daysAgo(iso: string | null | undefined, zone?: string, now: Date = new Date()): number | null {
  if (!iso) return null;
  const when = new Date(iso);
  if (Number.isNaN(when.getTime())) return null;
  const a = dayIn(when, zone).split("-").map(Number);
  const b = dayIn(now, zone).split("-").map(Number);
  const diff = Math.round((Date.UTC(b[0], b[1] - 1, b[2]) - Date.UTC(a[0], a[1] - 1, a[2])) / 86400000);
  return Math.max(0, diff);
}

/** "heute", "gestern", "vor 3 Tagen" (or English) for an ISO time; "" if unreadable. */
export function relativeDay(lang: Lang, iso: string | null | undefined, zone?: string, now?: Date): string {
  const n = daysAgo(iso, zone, now);
  if (n == null) return "";
  if (n === 0) return translate(lang, "day_today");
  if (n === 1) return translate(lang, "day_yesterday");
  return translate(lang, "day_ago", { n });
}

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
    return raw.slice(0, raw.length - name.length).trim();
  return "";
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
export function errorText(lang: Lang, err: unknown): string {
  const e = (err ?? {}) as WsError;
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

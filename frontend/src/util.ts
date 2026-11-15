import type { Lang } from "./i18n";
import { translate } from "./i18n";
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
  return [formatAmount(lang, ing.amount), ing.unit ?? ""].filter(Boolean).join(" ");
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

/** Map a WebSocket error to a translated, user friendly message. */
export function errorText(lang: Lang, err: unknown): string {
  const e = (err ?? {}) as WsError;
  switch (e.code) {
    case "source_error":
      return translate(lang, "err_source_error");
    case "source_blocked":
      return translate(lang, "err_source_blocked");
    case "not_found":
      return translate(lang, "err_not_found");
    case "kitchenowl_error":
      return translate(lang, "err_kitchenowl_error");
    case "kitchenowl_auth":
      return translate(lang, "err_kitchenowl_auth");
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
    case "collection":
      return { name: "collection" };
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
  if (view.name === "recipe") {
    if (view.key) return `/recipe/${encodeURIComponent(view.key)}`;
    if (view.url) return `/link/${encodeURIComponent(view.url)}`;
  }
  return "/search";
}

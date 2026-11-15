/**
 * Dashboard cards of EatFresh: `custom:eatfresh-week-card` and
 * `custom:eatfresh-today-card`. Both read `eatfresh/planner` and open the
 * recipe in the EatFresh panel when tapped. They draw their own card frame
 * from the Home Assistant card variables, without `ha-*` elements.
 */
import { mdiAlertCircleOutline, mdiCalendarWeek, mdiSilverwareForkKnife } from "@mdi/js";
import { LitElement, css, html, nothing, svg, type TemplateResult } from "lit";
import { state } from "lit/decorators.js";
import type { HomeAssistant, PlannerEntry, PlannerResponse } from "./types";
import { addDays, formatDay, mondayOf, parseDate, today, weekdayName } from "./util";

type Lang = "de" | "en";

const TEXTS = {
  de: {
    week_title: "Wochenplan",
    today_title: "Heute gibt es",
    nothing: "Nichts geplant",
    nothing_week: "In den nächsten Tagen ist nichts geplant.",
    plan_now: "Wochenplan öffnen",
    loading: "Lädt …",
    error: "Der Wochenplan ließ sich nicht laden.",
    retry: "Noch mal versuchen",
    today: "Heute",
    tomorrow: "Morgen",
    week_name: "EatFresh: Wochenplan",
    week_desc: "Die nächsten Tage aus dem Essensplan von KitchenOwl.",
    today_name: "EatFresh: Heute gibt es",
    today_desc: "Was heute laut Essensplan auf den Tisch kommt.",
    bad_days: "„days“ muss eine ganze Zahl von 1 bis 14 sein.",
  },
  en: {
    week_title: "Week plan",
    today_title: "Today’s menu",
    nothing: "Nothing planned",
    nothing_week: "Nothing is planned for the next days.",
    plan_now: "Open week plan",
    loading: "Loading …",
    error: "The week plan could not be loaded.",
    retry: "Try again",
    today: "Today",
    tomorrow: "Tomorrow",
    week_name: "EatFresh: Week plan",
    week_desc: "The next days from the KitchenOwl meal plan.",
    today_name: "EatFresh: Today’s menu",
    today_desc: "What is on the table today according to the meal plan.",
    bad_days: "“days” must be a whole number from 1 to 14.",
  },
};
type TextKey = keyof (typeof TEXTS)["de"];

const pickLang = (language?: string): Lang => ((language ?? "").toLowerCase().startsWith("de") ? "de" : "en");
const pageLang = (): Lang => pickLang(document.documentElement.lang || navigator.language);

const PANEL = "/eatfresh";
const REFRESH_MS = 10 * 60 * 1000;

const icon = (path: string) =>
  html`<svg class="i" viewBox="0 0 24 24" aria-hidden="true">${svg`<path d=${path}></path>`}</svg>`;

function navigate(path: string): void {
  window.history.pushState(null, "", path);
  window.dispatchEvent(new CustomEvent("location-changed", { detail: { replace: false } }));
}

const cardStyles = css`
  :host {
    display: block;
    --efc-primary: var(--primary-color, #03a9f4);
    --efc-on-primary: var(--text-primary-color, #fff);
    --efc-text: var(--primary-text-color, #212121);
    --efc-text2: var(--secondary-text-color, #727272);
    --efc-divider: var(--divider-color, rgba(0, 0, 0, 0.12));
    --efc-hover: color-mix(in srgb, var(--efc-text) 7%, transparent);
    --efc-tint: color-mix(in srgb, var(--efc-primary) 12%, transparent);
  }
  *, *::before, *::after { box-sizing: border-box; }
  .card {
    height: 100%;
    overflow: hidden;
    display: flex;
    flex-direction: column;
    background: var(--ha-card-background, var(--card-background-color, #fff));
    color: var(--efc-text);
    border-radius: var(--ha-card-border-radius, 12px);
    border-width: var(--ha-card-border-width, 1px);
    border-style: solid;
    border-color: var(--ha-card-border-color, var(--divider-color, #e0e0e0));
    box-shadow: var(--ha-card-box-shadow, none);
    font-family: var(--ha-font-family-body, inherit);
    font-size: var(--ha-font-size-m, 14px);
    line-height: 1.4;
    -webkit-tap-highlight-color: transparent;
  }
  .header {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 12px 8px 8px 16px;
  }
  .header h2 {
    flex: 1;
    min-width: 0;
    margin: 0;
    color: var(--ha-card-header-color, var(--efc-text));
    font-size: var(--ha-card-header-font-size, var(--ha-font-size-2xl, 24px));
    font-weight: var(--ha-font-weight-normal, 400);
    line-height: 1.33;
    letter-spacing: -0.012em;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .header .sub { color: var(--efc-text2); white-space: nowrap; }
  .content { padding: 0 16px 16px; min-width: 0; }
  a { color: inherit; text-decoration: none; }
  .icon-btn {
    flex: none;
    display: inline-grid;
    place-items: center;
    width: 44px;
    height: 44px;
    border-radius: 50%;
    color: var(--efc-text2);
  }
  .icon-btn:hover, a.row:hover, a.hero-link:hover { background: var(--efc-hover); }
  :focus-visible { outline: 2px solid var(--efc-primary); outline-offset: 2px; }
  svg.i { width: 24px; height: 24px; fill: currentColor; flex: none; }
  .photo {
    position: relative;
    flex: none;
    display: grid;
    place-items: center;
    overflow: hidden;
    background: color-mix(in srgb, var(--efc-primary) 10%, var(--ha-card-background, var(--card-background-color, #fff)));
    color: color-mix(in srgb, var(--efc-primary) 55%, var(--ha-card-background, var(--card-background-color, #fff)));
  }
  .photo img { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; }
  .thumb { width: 40px; height: 40px; border-radius: 8px; }
  .thumb svg.i { width: 20px; height: 20px; }
  .name { min-width: 0; overflow-wrap: anywhere; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
  .muted { color: var(--efc-text2); }
  .note { display: flex; flex-direction: column; align-items: center; gap: 8px; padding: 8px 0 4px; text-align: center; color: var(--efc-text2); }
  .note svg.i { width: 32px; height: 32px; opacity: 0.6; }
  .note.error svg.i { color: var(--error-color, #db4437); opacity: 1; }
  .btn {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    min-height: 44px;
    padding: 0 16px;
    border: 1px solid var(--efc-divider);
    border-radius: 22px;
    background: transparent;
    color: var(--efc-primary);
    font: inherit;
    font-weight: 500;
    cursor: pointer;
  }
  .btn:hover { background: var(--efc-tint); }
  .skel { height: 40px; margin: 6px 0; border-radius: 8px; background: var(--efc-hover); animation: pulse 1.4s ease-in-out infinite; }
  .skel.big { height: auto; aspect-ratio: 2 / 1; }
  @keyframes pulse { 50% { opacity: 0.45; } }
  @media (prefers-reduced-motion: reduce) { .skel { animation: none; } }

  /* Week card */
  .days { margin: 0; padding: 0; list-style: none; }
  .day { display: flex; gap: 12px; padding: 6px 0; min-width: 0; }
  .day + .day { border-top: 1px solid var(--efc-divider); }
  .date { flex: none; width: 4.4em; padding-top: 10px; line-height: 1.2; }
  .date .wd { display: block; font-weight: 500; }
  .date .dn { display: block; color: var(--efc-text2); font-size: 0.9em; }
  .day.today .date .wd { color: var(--efc-primary); }
  .meals { flex: 1; min-width: 0; display: flex; flex-direction: column; }
  .meals .muted { min-height: 44px; display: flex; align-items: center; }
  a.row { display: flex; align-items: center; gap: 10px; min-height: 52px; padding: 4px 6px; margin: 0 -6px; border-radius: 10px; min-width: 0; }

  /* Today card */
  .hero-link { display: block; margin: 0 -8px; padding: 0 8px 8px; border-radius: 12px; }
  .hero { width: 100%; aspect-ratio: 2 / 1; border-radius: 10px; }
  .hero svg.i { width: 40px; height: 40px; }
  .hero-name { margin-top: 8px; font-size: 1.15em; font-weight: 500; }
  .more a.row { min-height: 52px; }
`;

abstract class EatFreshCardBase extends LitElement {
  static styles = cardStyles;

  @state() protected _config: { title?: string; days?: number } = {};
  @state() protected _lang: Lang = pageLang();
  @state() protected _weeks = new Map<string, PlannerResponse>();
  @state() protected _state: "loading" | "done" | "error" = "loading";
  /** Today in the time zone of Home Assistant (browser day until the first answer). */
  @state() protected _today = today();

  private _hass?: HomeAssistant;
  private _timer?: number;
  private _day = today();
  private _seq = 0;

  set hass(value: HomeAssistant | undefined) {
    const first = !this._hass && !!value;
    this._hass = value;
    const lang = pickLang(value?.language ?? value?.locale?.language);
    if (lang !== this._lang) this._lang = lang;
    // Reload on the first hass and when the browser's day has changed; the
    // 10-minute refresh catches midnight of Home Assistant if it differs.
    if (first || this._day !== today()) this._load();
  }

  get hass(): HomeAssistant | undefined {
    return this._hass;
  }

  setConfig(config: { title?: string; days?: number }): void {
    if (!config || typeof config !== "object") throw new Error("Invalid configuration");
    if (config.days != null && (!Number.isInteger(config.days) || config.days < 1 || config.days > 14))
      throw new Error(TEXTS[this._lang].bad_days);
    this._config = { ...config };
    if (this._hass) this._load();
  }

  connectedCallback(): void {
    super.connectedCallback();
    this._timer = window.setInterval(() => this._load(), REFRESH_MS);
    document.addEventListener("visibilitychange", this._onVisible);
    if (this._hass) this._load();
  }

  disconnectedCallback(): void {
    super.disconnectedCallback();
    window.clearInterval(this._timer);
    document.removeEventListener("visibilitychange", this._onVisible);
  }

  private _onVisible = (): void => {
    if (document.visibilityState === "visible" && this._hass) this._load();
  };

  protected _t(key: TextKey): string {
    return TEXTS[this._lang][key];
  }

  /** Mondays of all weeks the card needs, counted from `now`. */
  protected abstract _neededWeeks(now: string): string[];

  protected async _load(): Promise<void> {
    if (!this._hass) return;
    const seq = ++this._seq;
    this._day = today();
    if (!this._weeks.size) this._state = "loading";
    try {
      // The current week first: it says which day it is in Home Assistant.
      const current = await this._hass.callWS<PlannerResponse>({ type: "eatfresh/planner" });
      const now = current.today || today();
      const more = await Promise.all(
        this._neededWeeks(now)
          .filter((week_start) => week_start !== current.week_start)
          .map((week_start) => this._hass!.callWS<PlannerResponse>({ type: "eatfresh/planner", week_start })),
      );
      if (seq !== this._seq) return;
      this._today = now;
      this._weeks = new Map([current, ...more].map((w) => [w.week_start, w]));
      this._state = "done";
    } catch {
      if (seq !== this._seq) return;
      this._state = "error";
    }
  }

  protected _entriesOn(date: string): PlannerEntry[] {
    const week = this._weeks.get(mondayOf(date));
    return week?.days.find((d) => d.date === date)?.entries ?? [];
  }

  protected _photo(src: string | null, cls: string): TemplateResult {
    return html`<div class="photo ${cls}">
      ${icon(mdiSilverwareForkKnife)}
      ${src
        ? html`<img src=${src} alt="" loading="lazy" decoding="async" @error=${(e: Event) => ((e.target as HTMLElement).hidden = true)} />`
        : nothing}
    </div>`;
  }

  protected _link(path: string, content: TemplateResult, cls: string): TemplateResult {
    return html`<a
      class=${cls}
      href=${PANEL + path}
      @click=${(e: MouseEvent) => {
        if (e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return;
        e.preventDefault();
        navigate(PANEL + path);
      }}
      >${content}</a
    >`;
  }

  protected _recipeRow(e: PlannerEntry): TemplateResult {
    return this._link(
      `/collection/${e.kitchenowl_id}`,
      html`${this._photo(e.image, "thumb")}<span class="name">${e.name}</span>`,
      "row",
    );
  }

  protected _header(title: string, sub = ""): TemplateResult {
    return html`<div class="header">
      <h2>${title}</h2>
      ${sub ? html`<span class="sub">${sub}</span>` : nothing}
      ${this._link("/planner", icon(mdiCalendarWeek), "icon-btn")}
    </div>`;
  }

  protected _errorNote(): TemplateResult {
    return html`<div class="note error" role="alert">
      ${icon(mdiAlertCircleOutline)}<span>${this._t("error")}</span>
      <button class="btn" @click=${() => this._load()}>${this._t("retry")}</button>
    </div>`;
  }

  protected _emptyNote(text: string): TemplateResult {
    return html`<div class="note">
      ${icon(mdiSilverwareForkKnife)}<span>${text}</span>
      ${this._link("/planner", html`${this._t("plan_now")}`, "btn")}
    </div>`;
  }
}

export class EatFreshWeekCard extends EatFreshCardBase {
  static getStubConfig(): Record<string, unknown> {
    return { days: 7 };
  }

  private _daysFrom(start: string): string[] {
    return Array.from({ length: this._config.days ?? 7 }, (_, i) => addDays(start, i));
  }

  private get _days(): string[] {
    return this._daysFrom(this._today);
  }

  protected _neededWeeks(now: string): string[] {
    return [...new Set(this._daysFrom(now).map(mondayOf))];
  }

  getCardSize(): number {
    return 1 + Math.ceil((this._config.days ?? 7) * 1.1);
  }

  getGridOptions(): Record<string, number> {
    return { columns: 12, min_columns: 6 };
  }

  protected render(): TemplateResult {
    const title = this._config.title ?? this._t("week_title");
    const days = this._days;
    let body: TemplateResult;
    if (this._state === "error" && !this._weeks.size) body = this._errorNote();
    else if (this._state === "loading")
      body = html`<div aria-busy="true" aria-label=${this._t("loading")}>
        ${days.slice(0, 4).map(() => html`<div class="skel"></div>`)}
      </div>`;
    else if (days.every((d) => !this._entriesOn(d).length)) body = this._emptyNote(this._t("nothing_week"));
    else {
      const now = days[0];
      body = html`<ul class="days">
        ${days.map((date) => {
          const entries = this._entriesOn(date);
          const label =
            date === now ? this._t("today") : date === addDays(now, 1) ? this._t("tomorrow") : weekdayName(this._lang, date, "short");
          return html`<li class="day ${date === now ? "today" : ""}">
            <div class="date">
              <span class="wd">${label}</span>
              <span class="dn">${parseDate(date).getDate()}.${parseDate(date).getMonth() + 1}.</span>
            </div>
            <div class="meals">
              ${entries.length
                ? entries.map((e) => this._recipeRow(e))
                : html`<span class="muted">${this._t("nothing")}</span>`}
            </div>
          </li>`;
        })}
      </ul>`;
    }
    return html`<div class="card">${this._header(title)}<div class="content">${body}</div></div>`;
  }
}

export class EatFreshTodayCard extends EatFreshCardBase {
  static getStubConfig(): Record<string, unknown> {
    return {};
  }

  protected _neededWeeks(now: string): string[] {
    return [mondayOf(now)];
  }

  getCardSize(): number {
    return 4;
  }

  getGridOptions(): Record<string, number> {
    return { columns: 6, min_columns: 4 };
  }

  protected render(): TemplateResult {
    const title = this._config.title ?? this._t("today_title");
    const date = this._today;
    const sub = formatDay(this._lang, date, "short");
    let body: TemplateResult;
    if (this._state === "error" && !this._weeks.size) body = this._errorNote();
    else if (this._state === "loading")
      body = html`<div aria-busy="true" aria-label=${this._t("loading")}><div class="skel big"></div><div class="skel"></div></div>`;
    else {
      const [first, ...more] = this._entriesOn(date);
      body = first
        ? html`${this._link(
              `/collection/${first.kitchenowl_id}`,
              html`${this._photo(first.image, "hero")}<div class="hero-name name">${first.name}</div>`,
              "hero-link",
            )}
            ${more.length ? html`<div class="more">${more.map((e) => this._recipeRow(e))}</div>` : nothing}`
        : this._emptyNote(this._t("nothing"));
    }
    return html`<div class="card">${this._header(title, sub)}<div class="content">${body}</div></div>`;
  }
}

if (!customElements.get("eatfresh-week-card")) customElements.define("eatfresh-week-card", EatFreshWeekCard);
if (!customElements.get("eatfresh-today-card")) customElements.define("eatfresh-today-card", EatFreshTodayCard);

interface CustomCardInfo {
  type: string;
  name: string;
  description: string;
  preview?: boolean;
  documentationURL?: string;
}

const w = window as unknown as { customCards?: CustomCardInfo[] };
w.customCards = w.customCards ?? [];
const texts = TEXTS[pageLang()];
for (const card of [
  { type: "eatfresh-week-card", name: texts.week_name, description: texts.week_desc },
  { type: "eatfresh-today-card", name: texts.today_name, description: texts.today_desc },
])
  if (!w.customCards.some((c) => c.type === card.type)) w.customCards.push({ ...card, preview: true });

declare global {
  interface HTMLElementTagNameMap {
    "eatfresh-week-card": EatFreshWeekCard;
    "eatfresh-today-card": EatFreshTodayCard;
  }
}

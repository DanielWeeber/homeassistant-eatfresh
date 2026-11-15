import {
  mdiAlertCircleOutline,
  mdiArrowLeft,
  mdiBookOpenPageVariantOutline,
  mdiCartPlus,
  mdiCheck,
  mdiCheckCircleOutline,
  mdiClockOutline,
  mdiClose,
  mdiHeart,
  mdiHeartOutline,
  mdiLinkVariant,
  mdiMagnify,
  mdiMenu,
  mdiOpenInNew,
  mdiSilverwareForkKnife,
} from "@mdi/js";
import { LitElement, html, nothing, svg, type PropertyValues, type TemplateResult } from "lit";
import { property, state } from "lit/decorators.js";
import { pickLang, translate, type Lang, type StringKey } from "./i18n";
import { panelStyles } from "./styles";
import type {
  CollectionRecipe,
  HomeAssistant,
  PanelRoute,
  RecipeResponse,
  SearchHit,
  SourceErrorInfo,
  SourceInfo,
  View,
  WsError,
} from "./types";
import {
  errorText,
  formatMinutes,
  hostOf,
  ingredientQty,
  isHttpUrl,
  parsePath,
  viewPath,
} from "./util";

type Load = "idle" | "loading" | "done" | "error";

interface Toast {
  text: string;
  kind: "ok" | "error";
  id: number;
}

const WIDE_MIN = 600;
const TOAST_MS = 4500;

const icon = (path: string, cls = "i") =>
  html`<svg class=${cls} viewBox="0 0 24 24" aria-hidden="true">${svg`<path d=${path}></path>`}</svg>`;

export class EatFreshPanel extends LitElement {
  static styles = panelStyles;

  @property({ type: Boolean, reflect: true }) narrow = false;
  @property({ attribute: false }) route?: PanelRoute;
  @property({ attribute: false }) panel?: unknown;

  @state() private _lang: Lang = "en";
  @state() private _wide = false;
  @state() private _view: View = { name: "search" };

  @state() private _sources: SourceInfo[] = [];
  @state() private _sourcesState: Load = "idle";
  @state() private _sourcesError = "";
  @state() private _selectedSources = new Set<string>();

  @state() private _query = "";
  @state() private _hits: SearchHit[] = [];
  @state() private _searchErrors: SourceErrorInfo[] = [];
  @state() private _searchState: Load = "idle";
  @state() private _searchError = "";
  @state() private _linkInvalid = false;

  @state() private _recipe?: RecipeResponse;
  @state() private _recipeFor = "";
  @state() private _recipeState: Load = "idle";
  @state() private _recipeError = "";
  @state() private _recipeMissing = false;

  @state() private _collection: CollectionRecipe[] = [];
  @state() private _collectionState: Load = "idle";
  @state() private _collectionError = "";
  @state() private _selected = new Set<number>();

  /** Favorite state that the user changed in this session, by recipe key. */
  @state() private _favs = new Map<string, boolean>();
  @state() private _favBusy = new Set<string>();
  @state() private _shoppingBusy = false;
  @state() private _toast?: Toast;

  private _hass?: HomeAssistant;
  private _searchSeq = 0;
  private _recipeSeq = 0;
  private _toastTimer?: number;
  private _resize?: ResizeObserver;
  private _navigatedInside = false;
  private _collectionStale = true;

  get hass(): HomeAssistant | undefined {
    return this._hass;
  }

  /** hass changes on every state update; only re-render when the language changes. */
  set hass(value: HomeAssistant | undefined) {
    const first = !this._hass && !!value;
    this._hass = value;
    const lang = pickLang(value?.language ?? value?.locale?.language);
    if (lang !== this._lang) this._lang = lang;
    if (first) this._loadSources();
  }

  connectedCallback(): void {
    super.connectedCallback();
    window.addEventListener("popstate", this._onPopState);
    this._resize = new ResizeObserver((entries) => {
      const width = entries[0]?.contentRect.width ?? 0;
      const wide = width >= WIDE_MIN;
      if (wide !== this._wide) this._wide = wide;
    });
    this._resize.observe(this);
  }

  disconnectedCallback(): void {
    super.disconnectedCallback();
    window.removeEventListener("popstate", this._onPopState);
    this._resize?.disconnect();
    window.clearTimeout(this._toastTimer);
  }

  protected willUpdate(changed: PropertyValues<this>): void {
    if (changed.has("route") && this.route) this._applyView(parsePath(this.route.path ?? ""));
  }

  private _t(key: StringKey, vars?: Record<string, string | number>): string {
    return translate(this._lang, key, vars);
  }

  // ---------------------------------------------------------------- routing

  private get _prefix(): string {
    return this.route?.prefix ?? "/eatfresh";
  }

  private _onPopState = (): void => {
    const { pathname } = window.location;
    if (!pathname.startsWith(this._prefix)) return;
    this._applyView(parsePath(pathname.slice(this._prefix.length)));
  };

  private _navigate(view: View, replace = false): void {
    const url = this._prefix + viewPath(view);
    if (url !== window.location.pathname) {
      if (replace) window.history.replaceState(window.history.state, "", url);
      else window.history.pushState(null, "", url);
      if (!replace) this._navigatedInside = true;
      // Home Assistant listens to this event and updates `route`.
      window.dispatchEvent(new CustomEvent("location-changed", { detail: { replace } }));
    }
    this._applyView(view);
  }

  private _applyView(view: View): void {
    const old = this._view;
    const same =
      old.name === view.name &&
      (view.name !== "recipe" ||
        (old.name === "recipe" && old.key === view.key && old.url === view.url));
    if (!same) {
      this._view = view;
      // A hint belongs to the view it came from; do not carry it along.
      window.clearTimeout(this._toastTimer);
      this._toast = undefined;
      this.renderRoot.querySelector("main")?.scrollTo({ top: 0 });
    }
    if (view.name === "recipe") this._loadRecipe(view);
    if (view.name === "collection" && (this._collectionStale || this._collectionState === "error"))
      this._loadCollection();
  }

  private _back(): void {
    if (this._navigatedInside && window.history.length > 1) window.history.back();
    else this._navigate({ name: "search" }, true);
  }

  private _toggleMenu(): void {
    this.dispatchEvent(new CustomEvent("hass-toggle-menu", { bubbles: true, composed: true }));
  }

  // ------------------------------------------------------------------- data

  private async _ws<T>(msg: Record<string, unknown>): Promise<T> {
    if (!this._hass) throw { code: "not_ready", message: "" };
    return this._hass.callWS<T>(msg);
  }

  private async _loadSources(): Promise<void> {
    this._sourcesState = "loading";
    try {
      const res = await this._ws<{ sources: SourceInfo[] }>({ type: "eatfresh/sources" });
      this._sources = res.sources;
      this._selectedSources = new Set(
        res.sources.filter((s) => s.enabled && s.searchable).map((s) => s.id),
      );
      this._sourcesState = "done";
    } catch (err) {
      this._sourcesError = errorText(this._lang, err);
      this._sourcesState = "error";
    }
  }

  private _sourceName(id: string): string {
    return this._sources.find((s) => s.id === id)?.name ?? id;
  }

  private get _searchable(): SourceInfo[] {
    return this._sources.filter((s) => s.enabled && s.searchable);
  }

  private async _search(): Promise<void> {
    const query = this._query.trim();
    if (!query) return;
    if (isHttpUrl(query)) {
      this._openLink(query);
      return;
    }
    if (this._searchable.length && !this._selectedSources.size) return;
    const seq = ++this._searchSeq;
    this._searchState = "loading";
    this._searchError = "";
    this._searchErrors = [];
    try {
      const msg: Record<string, unknown> = { type: "eatfresh/search", query };
      if (this._searchable.length) msg.sources = [...this._selectedSources];
      const res = await this._ws<{ hits: SearchHit[]; errors: SourceErrorInfo[] }>(msg);
      if (seq !== this._searchSeq) return;
      this._hits = res.hits ?? [];
      this._searchErrors = res.errors ?? [];
      for (const hit of this._hits) this._favs.delete(hit.key);
      this._searchState = "done";
    } catch (err) {
      if (seq !== this._searchSeq) return;
      this._hits = [];
      this._searchError = errorText(this._lang, err);
      this._searchState = "error";
    }
  }

  private _openLink(raw: string): void {
    const url = raw.trim();
    if (!isHttpUrl(url)) {
      this._linkInvalid = true;
      return;
    }
    this._linkInvalid = false;
    this._navigate({ name: "recipe", url });
  }

  private async _loadRecipe(view: View & { name: "recipe" }, force = false): Promise<void> {
    const id = view.key ? `k:${view.key}` : `u:${view.url}`;
    if (!force && id === this._recipeFor && this._recipeState !== "error") return;
    this._recipeFor = id;
    const seq = ++this._recipeSeq;
    this._recipe = undefined;
    this._recipeState = "loading";
    try {
      const msg = view.key
        ? { type: "eatfresh/recipe", key: view.key }
        : { type: "eatfresh/recipe", url: view.url };
      const res = await this._ws<RecipeResponse>(msg);
      if (seq !== this._recipeSeq) return;
      this._recipe = res;
      this._favs.delete(res.recipe.key);
      this._recipeState = "done";
    } catch (err) {
      if (seq !== this._recipeSeq) return;
      this._recipeError = errorText(this._lang, err);
      // "not_found" is no failure: the page simply holds no recipe.
      this._recipeMissing = (err as WsError | undefined)?.code === "not_found";
      this._recipeState = "error";
    }
  }

  private async _loadCollection(): Promise<void> {
    this._collectionState = "loading";
    this._collectionStale = false;
    try {
      const res = await this._ws<{ recipes: CollectionRecipe[] }>({ type: "eatfresh/collection" });
      this._collection = res.recipes ?? [];
      const ids = new Set(this._collection.map((r) => r.kitchenowl_id));
      this._selected = new Set([...this._selected].filter((id) => ids.has(id)));
      this._collectionState = "done";
    } catch (err) {
      this._collectionError = errorText(this._lang, err);
      this._collectionState = "error";
      this._collectionStale = true;
    }
  }

  private _isFav(key: string, fallback: boolean): boolean {
    return this._favs.get(key) ?? fallback;
  }

  /** Toggle a favorite at once and roll back if the server call fails. */
  private async _toggleFav(key: string, current: boolean): Promise<void> {
    if (this._favBusy.has(key)) return;
    const next = !current;
    this._favs = new Map(this._favs).set(key, next);
    this._favBusy = new Set(this._favBusy).add(key);
    try {
      if (next) {
        const res = await this._ws<{ kitchenowl_id: number; created: boolean }>({
          type: "eatfresh/favorite",
          key,
        });
        if (this._recipe?.recipe.key === key) {
          this._recipe = { ...this._recipe, favorite: true, kitchenowl_id: res.kitchenowl_id };
        }
      } else {
        await this._ws({ type: "eatfresh/unfavorite", key });
        if (this._recipe?.recipe.key === key) this._recipe = { ...this._recipe, favorite: false };
      }
      this._collectionStale = true;
    } catch (err) {
      this._favs = new Map(this._favs).set(key, current);
      this._showToast(
        this._t(next ? "favorite_failed" : "unfavorite_failed", { message: errorText(this._lang, err) }),
        "error",
      );
    } finally {
      const busy = new Set(this._favBusy);
      busy.delete(key);
      this._favBusy = busy;
    }
  }

  private async _addToShopping(ids: number[]): Promise<void> {
    if (!ids.length || this._shoppingBusy) return;
    this._shoppingBusy = true;
    try {
      const res = await this._ws<{ added: number }>({
        type: "eatfresh/shopping_list/add",
        kitchenowl_ids: ids,
      });
      const n = res.added ?? 0;
      this._showToast(
        n === 0 ? this._t("added_none") : n === 1 ? this._t("added_items_one") : this._t("added_items", { n }),
        "ok",
      );
      if (this._view.name === "collection") this._selected = new Set();
    } catch (err) {
      const e = (err ?? {}) as WsError;
      const done = Number(e.translation_placeholders?.added_recipes ?? 0);
      if (e.translation_key === "shopping_list_partial" && done > 0) {
        // The first `done` recipes went through (the core keeps the order):
        // deselect them, so a second try does not add them twice.
        if (this._view.name === "collection") {
          const sent = new Set(ids.slice(0, done));
          this._selected = new Set([...this._selected].filter((id) => !sent.has(id)));
        }
        this._showToast(
          this._t("shopping_partial", { done, total: ids.length, message: errorText(this._lang, err) }),
          "error",
        );
      } else {
        this._showToast(this._t("shopping_failed", { message: errorText(this._lang, err) }), "error");
      }
    } finally {
      this._shoppingBusy = false;
    }
  }

  private _showToast(text: string, kind: Toast["kind"]): void {
    window.clearTimeout(this._toastTimer);
    this._toast = { text, kind, id: Date.now() };
    this._toastTimer = window.setTimeout(() => (this._toast = undefined), TOAST_MS);
  }

  // ----------------------------------------------------------------- render

  protected render(): TemplateResult {
    const v = this._view.name;
    const tab = v === "collection" ? "collection" : "search";
    const nav = html`
      <button
        class="nav-btn"
        aria-current=${tab === "search" ? "page" : "false"}
        @click=${() => this._navigate({ name: "search" })}
      >
        ${icon(mdiMagnify)}<span>${this._t("nav_search")}</span>
      </button>
      <button
        class="nav-btn"
        aria-current=${tab === "collection" ? "page" : "false"}
        @click=${() => this._navigate({ name: "collection" })}
      >
        ${icon(mdiBookOpenPageVariantOutline)}<span>${this._t("nav_collection")}</span>
      </button>
    `;
    return html`
      <div class="shell ${this._wide ? "wide" : "narrow"}">
        <header class="top">
          ${this.narrow
            ? html`<button class="icon-btn" aria-label=${this._t("menu")} @click=${this._toggleMenu}>
                ${icon(mdiMenu)}
              </button>`
            : nothing}
          <h1>${this._t("title")}</h1>
          ${this._wide
            ? html`<nav class="top-nav" aria-label=${this._t("nav_label")}>${nav}</nav>`
            : nothing}
        </header>
        <div class="body">
          <main>
            <div class="content ${v === "collection" ? "fill" : ""}">
              ${v === "search"
                ? this._renderSearch()
                : v === "recipe"
                  ? this._renderRecipe()
                  : this._renderCollection()}
            </div>
          </main>
          ${this._renderToast()}
        </div>
        ${this._wide
          ? nothing
          : html`<nav class="bottom-nav" aria-label=${this._t("nav_label")}>${nav}</nav>`}
      </div>
    `;
  }

  private _renderToast(): TemplateResult | typeof nothing {
    const toast = this._toast;
    const raised = this._view.name === "collection" && this._selected.size > 0;
    return html`<div class="sr" role="status" aria-live="polite">${toast?.text ?? ""}</div>
      ${toast
        ? html`<div class="toast ${toast.kind} ${raised ? "raised" : ""}">
            <span class="lead">${icon(toast.kind === "ok" ? mdiCheckCircleOutline : mdiAlertCircleOutline)}</span>
            <span class="msg">${toast.text}</span>
            <button class="icon-btn" aria-label=${this._t("close")} @click=${() => (this._toast = undefined)}>
              ${icon(mdiClose)}
            </button>
          </div>`
        : nothing}`;
  }

  private _photo(src: string | null, cls = ""): TemplateResult {
    return html`<div class="photo ${cls}">
      ${icon(mdiSilverwareForkKnife)}
      ${src
        ? html`<img
            src=${src}
            alt=""
            loading="lazy"
            decoding="async"
            @error=${(e: Event) => ((e.target as HTMLElement).hidden = true)}
          />`
        : nothing}
    </div>`;
  }

  private _heart(key: string, fav: boolean, cls = "heart"): TemplateResult {
    const busy = this._favBusy.has(key);
    return html`<button
      class="${cls} ${busy ? "busy" : ""}"
      aria-pressed=${fav ? "true" : "false"}
      aria-label=${this._t(fav ? "favorite_remove" : "favorite_add")}
      title=${this._t(fav ? "favorite_remove" : "favorite_add")}
      @click=${(e: Event) => {
        e.preventDefault();
        e.stopPropagation();
        this._toggleFav(key, fav);
      }}
    >
      ${icon(fav ? mdiHeart : mdiHeartOutline)}${cls.includes("btn")
        ? html`<span>${this._t(fav ? "favorite_remove" : "favorite_add")}</span>`
        : nothing}
    </button>`;
  }

  private _skeletonCards(n = 6): TemplateResult {
    return html`<div class="grid" aria-busy="true" aria-label=${this._t("loading")}>
      ${Array.from(
        { length: n },
        () => html`<div class="card">
          <div class="photo skel" style="border-radius:0"></div>
          <div class="card-body"><div class="skel line"></div><div class="skel line short"></div></div>
        </div>`,
      )}
    </div>`;
  }

  private _note(text: string, ico = mdiSilverwareForkKnife, retry?: () => void): TemplateResult {
    return html`<div class="note">
      ${icon(ico)}
      <div>${text}</div>
      ${retry ? html`<button class="btn" @click=${retry}>${this._t("retry")}</button>` : nothing}
    </div>`;
  }

  // ---- search view

  private _renderSearch(): TemplateResult {
    const searchable = this._searchable;
    return html`
      <form
        class="search-form"
        role="search"
        @submit=${(e: Event) => {
          e.preventDefault();
          this._search();
        }}
      >
        <label class="field">
          ${icon(mdiMagnify)}
          <span class="sr">${this._t("search_label")}</span>
          <input
            type="search"
            enterkeyhint="search"
            autocomplete="off"
            .value=${this._query}
            placeholder=${this._t("search_placeholder")}
            @input=${(e: Event) => (this._query = (e.target as HTMLInputElement).value)}
          />
        </label>
        <button class="btn primary" type="submit" aria-label=${this._t("search_button")}>
          ${this._wide ? this._t("search_button") : icon(mdiMagnify)}
        </button>
      </form>
      ${this._sourcesState === "error"
        ? html`<div class="banner">
            ${icon(mdiAlertCircleOutline)}<span>${this._sourcesError}</span>
          </div>`
        : nothing}
      ${searchable.length > 1
        ? html`<fieldset class="chips">
            <legend>${this._t("sources_label")}</legend>
            ${searchable.map((s) => {
              const on = this._selectedSources.has(s.id);
              return html`<button
                type="button"
                class="chip"
                aria-pressed=${on ? "true" : "false"}
                @click=${() => {
                  const next = new Set(this._selectedSources);
                  if (on) next.delete(s.id);
                  else next.add(s.id);
                  this._selectedSources = next;
                }}
              >
                ${on ? icon(mdiCheck) : nothing}${s.name}
              </button>`;
            })}
          </fieldset>`
        : nothing}
      ${this._renderResults()}
      <section class="link-box">
        <h2>${icon(mdiLinkVariant, "i s")}${this._t("link_title")}</h2>
        <p>${this._t("link_hint")}</p>
        <form
          class="search-form"
          novalidate
          @submit=${(e: Event) => {
            e.preventDefault();
            const input = (e.target as HTMLFormElement).querySelector("input");
            this._openLink(input?.value ?? "");
          }}
        >
          <label class="field">
            <span class="sr">${this._t("link_title")}</span>
            <input
              type="url"
              inputmode="url"
              autocomplete="off"
              autocapitalize="off"
              spellcheck="false"
              placeholder=${this._t("link_placeholder")}
              aria-invalid=${this._linkInvalid ? "true" : "false"}
              @input=${() => (this._linkInvalid = false)}
            />
          </label>
          <button class="btn" type="submit">${this._t("link_button")}</button>
        </form>
        ${this._linkInvalid ? html`<p class="error-text" role="alert">${this._t("link_invalid")}</p>` : nothing}
      </section>
    `;
  }

  private _renderResults(): TemplateResult {
    const errors = this._searchErrors.map(
      (e) => html`<div class="banner">
        ${icon(mdiAlertCircleOutline)}
        <span>${this._t("source_failed", { source: this._sourceName(e.source), message: e.message })}</span>
      </div>`,
    );
    if (this._searchable.length > 1 && !this._selectedSources.size)
      return html`<div class="banner info">${icon(mdiAlertCircleOutline)}<span>${this._t("search_no_sources")}</span></div>`;
    switch (this._searchState) {
      case "idle":
        return this._note(this._t("search_start"), mdiMagnify);
      case "loading":
        return this._skeletonCards();
      case "error":
        return this._note(this._searchError, mdiAlertCircleOutline, () => this._search());
      default:
        return html`${errors}
          ${this._hits.length
            ? html`<div class="grid">${this._hits.map((hit) => this._renderHit(hit))}</div>`
            : this._note(this._t("search_empty"))}`;
    }
  }

  private _renderHit(hit: SearchHit): TemplateResult {
    const fav = this._isFav(hit.key, hit.favorite);
    const time = formatMinutes(this._lang, hit.total_time);
    const view: View = { name: "recipe", key: hit.key };
    return html`<article class="card">
      <a
        class="card-link"
        href=${this._prefix + viewPath(view)}
        @click=${(e: MouseEvent) => {
          if (e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return;
          e.preventDefault();
          this._navigate(view);
        }}
      >
        ${this._photo(hit.image)}
        <div class="card-body">
          <h3 class="card-title">${hit.title}</h3>
          <div class="meta">
            ${time ? html`<span>${icon(mdiClockOutline)}${time}</span>` : nothing}
            <span class="src">${this._sourceName(hit.source)}</span>
          </div>
        </div>
      </a>
      ${this._heart(hit.key, fav)}
    </article>`;
  }

  // ---- recipe view

  private _renderRecipe(): TemplateResult {
    const back = html`<div class="back-row">
      <button class="nav-btn" @click=${this._back}>${icon(mdiArrowLeft)}<span>${this._t("back")}</span></button>
    </div>`;
    if (this._recipeState === "error") {
      const view = this._view as View & { name: "recipe" };
      if (this._recipeMissing) {
        const page = view.url ?? this._hits.find((h) => h.key === view.key)?.url;
        return html`${back}<div class="note">
            ${icon(mdiSilverwareForkKnife)}
            <div>${this._t("recipe_missing")}</div>
            ${page && isHttpUrl(page)
              ? html`<a class="btn" href=${page} target="_blank" rel="noopener noreferrer">
                  ${icon(mdiOpenInNew)}<span>${this._t("open_source")}</span>
                </a>`
              : nothing}
          </div>`;
      }
      return html`${back}${this._note(
        `${this._t("recipe_failed")} ${this._recipeError}`,
        mdiAlertCircleOutline,
        () => this._loadRecipe(view, true),
      )}`;
    }
    const data = this._recipe;
    if (!data || this._recipeState === "loading") {
      return html`${back}
        <div class="recipe-head" aria-busy="true" aria-label=${this._t("loading")}>
          <div class="photo hero skel"></div>
          <div>
            <div class="skel line" style="height:1.6em"></div>
            <div class="skel line short"></div>
            <div class="skel line"></div>
          </div>
        </div>`;
    }
    const r = data.recipe;
    const fav = this._isFav(r.key, data.favorite);
    const facts: [string, string][] = [];
    const total = formatMinutes(this._lang, r.total_time);
    const prep = formatMinutes(this._lang, r.prep_time);
    const cook = formatMinutes(this._lang, r.cook_time);
    if (total) facts.push([this._t("total_time"), total]);
    if (prep) facts.push([this._t("prep_time"), prep]);
    if (cook) facts.push([this._t("cook_time"), cook]);
    const servings =
      r.servings == null ? "" : r.servings === 1 ? this._t("servings_one") : this._t("servings", { n: r.servings });
    const koId = data.kitchenowl_id;
    return html`${back}
      <div class="recipe-head">
        ${this._photo(r.image, "hero")}
        <div>
          <h2 class="recipe-title">${r.title}</h2>
          <div class="meta" style="margin-top:4px">
            <span class="src">${r.source === "jsonld" ? hostOf(r.url) : this._sourceName(r.source)}</span>
          </div>
          ${r.description ? html`<p class="recipe-desc">${r.description}</p>` : nothing}
          ${facts.length || servings
            ? html`<ul class="facts">
                ${facts.map(([label, value]) => html`<li>${icon(mdiClockOutline)}${label}: ${value}</li>`)}
                ${servings ? html`<li>${icon(mdiSilverwareForkKnife)}${servings}</li>` : nothing}
              </ul>`
            : nothing}
          <div class="actions">
            ${this._heart(r.key, fav, "btn fav")}
            ${isHttpUrl(r.url)
              ? html`<a class="btn" href=${r.url} target="_blank" rel="noopener noreferrer">
                  ${icon(mdiOpenInNew)}<span>${this._t("open_source")}</span>
                </a>`
              : nothing}
            ${koId != null
              ? html`<button
                  class="btn primary"
                  ?disabled=${this._shoppingBusy}
                  @click=${() => this._addToShopping([koId])}
                >
                  ${icon(mdiCartPlus)}<span>${this._t("to_shopping_list")}</span>
                </button>`
              : nothing}
          </div>
          ${koId == null ? html`<p class="hint">${this._t("shopping_hint")}</p>` : nothing}
        </div>
      </div>
      <div class="recipe-body">
        ${r.ingredients.length
          ? html`<section class="panel-box">
              <h2>${this._t("ingredients")}</h2>
              <ul class="ingredients">
                ${r.ingredients.map((ing) => {
                  const qty = ingredientQty(this._lang, ing);
                  return html`<li>
                    <span class="qty">${qty}</span>
                    <span>${ing.name || ing.raw}${ing.note ? html` <span class="note">(${ing.note})</span>` : nothing}</span>
                  </li>`;
                })}
              </ul>
            </section>`
          : nothing}
        ${r.steps.length
          ? html`<section class="panel-box">
              <h2>${this._t("steps")}</h2>
              <ol class="steps">
                ${r.steps.map((step) => html`<li>${step}</li>`)}
              </ol>
            </section>`
          : nothing}
      </div>`;
  }

  // ---- collection view

  private _renderCollection(): TemplateResult {
    if (this._collectionState === "loading" || this._collectionState === "idle")
      return html`<p class="intro">${this._t("collection_intro")}</p>${this._skeletonCards()}`;
    if (this._collectionState === "error")
      return this._note(
        `${this._t("collection_failed")} ${this._collectionError}`,
        mdiAlertCircleOutline,
        () => this._loadCollection(),
      );
    if (!this._collection.length) return this._note(this._t("collection_empty"), mdiHeartOutline);
    const n = this._selected.size;
    return html`<p class="intro">${this._t("collection_intro")}</p>
      <div class="grid">${this._collection.map((r) => this._renderCollectionCard(r))}</div>
      ${n
        ? html`<div class="action-bar">
            <button class="icon-btn" aria-label=${this._t("clear_selection")} @click=${() => (this._selected = new Set())}>
              ${icon(mdiClose)}
            </button>
            <span class="count">${this._t("selected", { n })}</span>
            <button
              class="btn primary"
              ?disabled=${this._shoppingBusy}
              @click=${() => this._addToShopping([...this._selected])}
            >
              ${icon(mdiCartPlus)}<span>${this._t("to_shopping_list")}</span>
            </button>
          </div>`
        : nothing}`;
  }

  private _renderCollectionCard(r: CollectionRecipe): TemplateResult {
    const selected = this._selected.has(r.kitchenowl_id);
    const time = formatMinutes(this._lang, r.time);
    const link = r.source && isHttpUrl(r.source) ? r.source : null;
    const toggle = () => {
      const next = new Set(this._selected);
      if (selected) next.delete(r.kitchenowl_id);
      else next.add(r.kitchenowl_id);
      this._selected = next;
    };
    return html`<article class="card selectable ${selected ? "selected" : ""}">
      <button class="card-link" role="checkbox" aria-checked=${selected ? "true" : "false"} @click=${toggle}>
        ${this._photo(r.image)}
        <div class="card-body">
          <h3 class="card-title">${r.name}</h3>
          <div class="meta">
            ${time ? html`<span>${icon(mdiClockOutline)}${time}</span>` : nothing}
            ${link ? html`<span class="src">${hostOf(link)}</span>` : nothing}
          </div>
        </div>
        <span class="check" aria-hidden="true">${selected ? icon(mdiCheck) : nothing}</span>
      </button>
      ${link
        ? html`<button
            class="icon-btn open-btn"
            aria-label=${`${this._t("open_recipe")}: ${r.name}`}
            title=${this._t("open_recipe")}
            @click=${() => this._navigate({ name: "recipe", url: link })}
          >
            ${icon(mdiOpenInNew)}
          </button>`
        : nothing}
    </article>`;
  }
}

if (!customElements.get("eatfresh-panel")) customElements.define("eatfresh-panel", EatFreshPanel);

declare global {
  interface HTMLElementTagNameMap {
    "eatfresh-panel": EatFreshPanel;
  }
}

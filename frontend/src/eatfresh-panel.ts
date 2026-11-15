import {
  mdiAlertCircleOutline,
  mdiArrowLeft,
  mdiBookOpenPageVariantOutline,
  mdiCalendarPlus,
  mdiCalendarWeek,
  mdiCartPlus,
  mdiCheck,
  mdiCheckCircleOutline,
  mdiChevronLeft,
  mdiChevronRight,
  mdiClockOutline,
  mdiClose,
  mdiEyeOffOutline,
  mdiEyeOutline,
  mdiHeart,
  mdiHeartOutline,
  mdiLinkVariant,
  mdiMagnify,
  mdiMenu,
  mdiOpenInNew,
  mdiPlus,
  mdiSilverwareForkKnife,
  mdiTagMultipleOutline,
} from "@mdi/js";
import { LitElement, html, nothing, svg, type PropertyValues, type TemplateResult } from "lit";
import { property, query, state } from "lit/decorators.js";
import { live } from "lit/directives/live.js";
import { pickLang, translate, type Lang, type StringKey } from "./i18n";
import { panelStyles } from "./styles";
import type {
  CollectionRecipe,
  CollectionRecipeResponse,
  HomeAssistant,
  PanelRoute,
  PlannerEntry,
  PlannerResponse,
  Recipe,
  RecipeResponse,
  SearchHit,
  SourceErrorInfo,
  SourceInfo,
  Tab,
  TagsResponse,
  View,
  WeekShoppingResponse,
  WsError,
} from "./types";
import {
  addDays,
  errorText,
  formatDay,
  formatMinutes,
  formatWeek,
  hostOf,
  ingredientQty,
  isHttpUrl,
  mondayOf,
  parsePath,
  today,
  viewPath,
  weekdayName,
} from "./util";

type Load = "idle" | "loading" | "done" | "error";

interface ToastAction {
  label: string;
  run: () => void;
}

interface Toast {
  text: string;
  kind: "ok" | "error";
  id: number;
  action?: ToastAction;
  /** Runs once when the toast goes away without its action (deferred commits). */
  onExpire?: () => void;
}

type Dialog =
  | { kind: "link" }
  | {
      kind: "categories";
      id: number;
      name: string;
      tags: string[];
      original: string[];
      loading: boolean;
      busy: boolean;
      error: string;
    }
  | { kind: "plan"; id: number; name: string; image: string | null }
  | { kind: "pick"; date: string }
  | { kind: "week_again"; week: string; at: string };

const WIDE_MIN = 600;
const TOAST_MS = 4500;
const UNDO_MS = 7000;

const icon = (path: string, cls = "i") =>
  html`<svg class=${cls} viewBox="0 0 24 24" aria-hidden="true">${svg`<path d=${path}></path>`}</svg>`;

const lower = (s: string) => s.trim().toLocaleLowerCase();

/** Merge tag lists without case duplicates, keeping the first spelling. */
function uniqueTags(...lists: (readonly string[] | undefined)[]): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const list of lists)
    for (const tag of list ?? []) {
      const t = tag.trim();
      if (t && !seen.has(lower(t))) {
        seen.add(lower(t));
        out.push(t);
      }
    }
  return out;
}

export class EatFreshPanel extends LitElement {
  static styles = panelStyles;

  @property({ type: Boolean, reflect: true }) narrow = false;
  @property({ attribute: false }) route?: PanelRoute;
  @property({ attribute: false }) panel?: unknown;

  @state() private _lang: Lang = "en";
  @state() private _wide = false;
  @state() private _view: View = { name: "search" };
  @state() private _tab: Tab = "search";

  @state() private _sources: SourceInfo[] = [];
  @state() private _sourcesState: Load = "idle";
  @state() private _sourcesError = "";
  @state() private _selectedSources = new Set<string>();

  @state() private _query = "";
  @state() private _hits: SearchHit[] = [];
  @state() private _searchErrors: SourceErrorInfo[] = [];
  @state() private _searchState: Load = "idle";
  @state() private _searchError = "";

  @state() private _recipe?: RecipeResponse;
  @state() private _recipeFor = "";
  @state() private _recipeState: Load = "idle";
  @state() private _recipeError = "";
  @state() private _recipeMissing = false;

  @state() private _ko?: CollectionRecipeResponse;
  @state() private _koFor = 0;
  @state() private _koState: Load = "idle";
  @state() private _koError = "";

  @state() private _collection: CollectionRecipe[] = [];
  @state() private _collectionState: Load = "idle";
  @state() private _collectionError = "";
  @state() private _selected = new Set<number>();
  @state() private _filter = new Set<string>();
  @state() private _collectionQuery = "";
  @state() private _showHidden = false;
  @state() private _tags?: TagsResponse;

  // Browser day until the core has sent its own (time zone of Home Assistant).
  @state() private _today = today();
  @state() private _weekStart = mondayOf(today());
  @state() private _planner?: PlannerResponse;
  @state() private _plannerState: Load = "idle";
  @state() private _plannerError = "";
  @state() private _weekBusy = false;

  @state() private _dialog?: Dialog;
  @state() private _linkInvalid = false;
  @state() private _pickQuery = "";
  @state() private _customTag = "";

  /** Favorite state that the user changed in this session, by recipe key. */
  @state() private _favs = new Map<string, boolean>();
  @state() private _favBusy = new Set<string>();
  @state() private _shoppingBusy = false;
  @state() private _busy = new Set<number>();
  @state() private _toast?: Toast;

  @query("dialog") private _dialogEl?: HTMLDialogElement;

  private _hass?: HomeAssistant;
  private _searchSeq = 0;
  private _recipeSeq = 0;
  private _koSeq = 0;
  private _collectionSeq = 0;
  private _plannerSeq = 0;
  private _toastTimer?: number;
  private _resize?: ResizeObserver;
  private _navigatedInside = false;
  private _collectionStale = true;
  private _collectionHidden = false;
  private _plannerStale = true;
  /** True once `_today` comes from Home Assistant. */
  private _todayKnown = false;
  /** True once the person has chosen a week; until then the core picks it. */
  private _weekChosen = false;

  get hass(): HomeAssistant | undefined {
    return this._hass;
  }

  /** hass changes on every state update; only re-render when the language changes. */
  set hass(value: HomeAssistant | undefined) {
    const first = !this._hass && !!value;
    this._hass = value;
    const lang = pickLang(value?.language ?? value?.locale?.language);
    if (lang !== this._lang) this._lang = lang;
    if (first) {
      this._loadSources();
      // The view may have been set before hass arrived.
      this._applyView(this._view);
    }
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
    this._clearToast();
  }

  protected willUpdate(changed: PropertyValues<this>): void {
    if (changed.has("route") && this.route) this._applyView(parsePath(this.route.path ?? ""));
  }

  protected updated(): void {
    const dlg = this._dialogEl;
    if (!dlg) return;
    if (this._dialog && !dlg.open) {
      dlg.showModal();
      // Focus the first text field, so the keyboard comes up at once.
      dlg.querySelector<HTMLInputElement>("input")?.focus();
    } else if (!this._dialog && dlg.open) dlg.close();
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

  private _sameView(a: View, b: View): boolean {
    if (a.name !== b.name) return false;
    if (a.name === "recipe" && b.name === "recipe") return a.key === b.key && a.url === b.url;
    if (a.name === "korecipe" && b.name === "korecipe") return a.id === b.id;
    return true;
  }

  private _applyView(view: View): void {
    if (!this._sameView(this._view, view)) {
      this._view = view;
      // A hint belongs to the view it came from; do not carry it along.
      this._clearToast();
      this._dialog = undefined;
      this.renderRoot.querySelector("main")?.scrollTo({ top: 0 });
    }
    if (view.name === "search" || view.name === "collection" || view.name === "planner") this._tab = view.name;
    else if (view.name === "korecipe" && this._tab === "search") this._tab = "collection";
    if (!this._hass) return;
    if (view.name === "recipe") this._loadRecipe(view);
    if (view.name === "korecipe") this._loadKoRecipe(view.id);
    if (view.name === "collection" && (this._collectionStale || this._collectionState === "error"))
      this._loadCollection();
    if (view.name === "planner" && (this._plannerStale || this._plannerState === "error")) this._loadPlanner();
  }

  private _back(): void {
    if (this._navigatedInside && window.history.length > 1) window.history.back();
    else this._navigate({ name: this._tab }, true);
  }

  private _toggleMenu(): void {
    this.dispatchEvent(new CustomEvent("hass-toggle-menu", { bubbles: true, composed: true }));
  }

  /** Link that opens a view in the panel, but still works as a normal link. */
  private _viewLink(view: View) {
    return {
      href: this._prefix + viewPath(view),
      click: (e: MouseEvent) => {
        if (e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return;
        e.preventDefault();
        this._navigate(view);
      },
    };
  }

  // ------------------------------------------------------------------- data

  private async _ws<T>(msg: Record<string, unknown>): Promise<T> {
    if (!this._hass) throw { code: "not_ready", message: "" };
    return this._hass.callWS<T>(msg);
  }

  private _err(err: unknown): string {
    return errorText(this._lang, err);
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
      this._sourcesError = this._err(err);
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
      this._navigate({ name: "recipe", url: query });
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
      this._searchError = this._err(err);
      this._searchState = "error";
    }
  }

  private _submitLink(raw: string): void {
    const url = raw.trim();
    if (!isHttpUrl(url)) {
      this._linkInvalid = true;
      return;
    }
    this._linkInvalid = false;
    this._dialog = undefined;
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
      this._recipeError = this._err(err);
      // "not_found" is no failure: the page simply holds no recipe.
      this._recipeMissing = (err as WsError | undefined)?.code === "not_found";
      this._recipeState = "error";
    }
  }

  private async _loadKoRecipe(id: number, force = false): Promise<void> {
    if (!force && id === this._koFor && this._koState !== "error") return;
    this._koFor = id;
    const seq = ++this._koSeq;
    this._ko = undefined;
    this._koState = "loading";
    try {
      const res = await this._ws<CollectionRecipeResponse>({
        type: "eatfresh/collection/recipe",
        kitchenowl_id: id,
      });
      if (seq !== this._koSeq) return;
      this._ko = res;
      this._koState = "done";
    } catch (err) {
      if (seq !== this._koSeq) return;
      this._koError = this._err(err);
      this._koState = "error";
    }
  }

  private async _loadCollection(): Promise<void> {
    const seq = ++this._collectionSeq;
    const includeHidden = this._showHidden;
    if (!this._collection.length || this._collectionState === "error") this._collectionState = "loading";
    this._collectionStale = false;
    try {
      const msg: Record<string, unknown> = { type: "eatfresh/collection" };
      if (includeHidden) msg.include_hidden = true;
      const [res] = await Promise.all([
        this._ws<{ recipes: CollectionRecipe[] }>(msg),
        this._ensureTags(),
      ]);
      if (seq !== this._collectionSeq) return;
      this._collection = (res.recipes ?? []).map((r) => ({ ...r, tags: r.tags ?? [], hidden: !!r.hidden }));
      this._collectionHidden = includeHidden;
      const ids = new Set(this._collection.map((r) => r.kitchenowl_id));
      this._selected = new Set([...this._selected].filter((id) => ids.has(id)));
      this._collectionState = "done";
    } catch (err) {
      if (seq !== this._collectionSeq) return;
      this._collectionError = this._err(err);
      this._collectionState = "error";
      this._collectionStale = true;
    }
  }

  /** Load categories and tags once; a failure only means fewer suggestions. */
  private async _ensureTags(force = false): Promise<void> {
    if (this._tags && !force) return;
    try {
      this._tags = await this._ws<TagsResponse>({ type: "eatfresh/tags" });
    } catch {
      /* the chips then come from the recipes alone */
    }
  }

  private async _loadPlanner(): Promise<void> {
    const seq = ++this._plannerSeq;
    const week = this._weekStart;
    if (!this._planner || this._planner.week_start !== week || this._plannerState === "error")
      this._plannerState = "loading";
    this._plannerStale = false;
    // The first load asks for the current week of Home Assistant, not the browser's.
    const auto = !this._todayKnown && !this._weekChosen;
    try {
      const res = await this._ws<PlannerResponse>(
        auto ? { type: "eatfresh/planner" } : { type: "eatfresh/planner", week_start: week },
      );
      this._setToday(res);
      if (seq !== this._plannerSeq) return;
      if (auto) this._weekStart = res.week_start;
      this._planner = res;
      this._plannerState = "done";
    } catch (err) {
      if (seq !== this._plannerSeq) return;
      this._plannerError = this._err(err);
      this._plannerState = "error";
      this._plannerStale = true;
    }
  }

  private _setToday(res: PlannerResponse): void {
    if (!res.today) return;
    this._todayKnown = true;
    if (res.today !== this._today) this._today = res.today;
  }

  /** Fetch today of Home Assistant once, for the day picker outside the week view. */
  private async _ensureToday(): Promise<void> {
    if (this._todayKnown) return;
    try {
      this._setToday(await this._ws<PlannerResponse>({ type: "eatfresh/planner" }));
    } catch {
      /* the picker then uses the browser's day */
    }
  }

  private _goWeek(monday: string): void {
    this._weekChosen = true;
    this._weekStart = monday;
    this._loadPlanner();
  }

  private _isFav(key: string, fallback: boolean): boolean {
    return this._favs.get(key) ?? fallback;
  }

  private _setBusy(id: number, on: boolean): void {
    const next = new Set(this._busy);
    if (on) next.add(id);
    else next.delete(id);
    this._busy = next;
  }

  /** Toggle a favorite at once and roll back if the server call fails. */
  private async _toggleFav(key: string, current: boolean, title: string): Promise<void> {
    if (this._favBusy.has(key)) return;
    const next = !current;
    this._favs = new Map(this._favs).set(key, next);
    this._favBusy = new Set(this._favBusy).add(key);
    try {
      if (next) {
        const res = await this._ws<{ kitchenowl_id: number; created: boolean; tags?: string[] }>({
          type: "eatfresh/favorite",
          key,
        });
        if (this._recipe?.recipe.key === key) {
          this._recipe = { ...this._recipe, favorite: true, kitchenowl_id: res.kitchenowl_id };
        }
        const tags = res.tags ?? [];
        this._showToast(
          tags.length ? this._t("favorite_saved_tags", { tags: tags.join(", ") }) : this._t("favorite_saved"),
          "ok",
          {
            action: {
              label: tags.length ? this._t("change") : this._t("categories"),
              run: () => this._openCategories(res.kitchenowl_id, title, tags),
            },
            ms: UNDO_MS,
          },
        );
      } else {
        await this._ws({ type: "eatfresh/unfavorite", key });
        if (this._recipe?.recipe.key === key) this._recipe = { ...this._recipe, favorite: false };
      }
      this._collectionStale = true;
    } catch (err) {
      this._favs = new Map(this._favs).set(key, current);
      this._showToast(
        this._t(next ? "favorite_failed" : "unfavorite_failed", { message: this._err(err) }),
        "error",
      );
    } finally {
      const busy = new Set(this._favBusy);
      busy.delete(key);
      this._favBusy = busy;
    }
  }

  private _partialDone(err: unknown): number {
    const e = (err ?? {}) as WsError;
    if (e.translation_key !== "shopping_list_partial") return 0;
    return Number(e.translation_placeholders?.added_recipes ?? 0);
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
      const done = this._partialDone(err);
      if (done > 0) {
        // The first `done` recipes went through (the core keeps the order):
        // deselect them, so a second try does not add them twice.
        if (this._view.name === "collection") {
          const sent = new Set(ids.slice(0, done));
          this._selected = new Set([...this._selected].filter((id) => !sent.has(id)));
        }
        this._showToast(
          this._t("shopping_partial", { done, total: ids.length, message: this._err(err) }),
          "error",
        );
      } else {
        this._showToast(this._t("shopping_failed", { message: this._err(err) }), "error");
      }
    } finally {
      this._shoppingBusy = false;
    }
  }

  private async _weekToShopping(confirm = false): Promise<void> {
    if (this._weekBusy) return;
    const week = this._weekStart;
    const before = this._planner?.week_start === week ? this._planner.shopping_list_at : null;
    if (!confirm && before) {
      // Already done (here or on another device): ask first.
      this._dialog = { kind: "week_again", week, at: before };
      return;
    }
    this._weekBusy = true;
    try {
      const res = await this._ws<WeekShoppingResponse>({
        type: "eatfresh/planner/shopping_list",
        week_start: week,
        ...(confirm ? { confirm: true } : {}),
      });
      if (res.already_added_at) {
        // Another window was faster; the core sent nothing.
        this._setWeekListTime(week, res.already_added_at);
        this._dialog = { kind: "week_again", week, at: res.already_added_at };
        return;
      }
      if (res.at) this._setWeekListTime(week, res.at);
      const n = res.added ?? 0;
      const r = res.recipes ?? 0;
      this._showToast(
        r === 0 ? this._t("week_nothing") : n === 0 ? this._t("added_none") : this._t("week_added", { n, r }),
        "ok",
      );
    } catch (err) {
      const done = this._partialDone(err);
      // Part of the week is on the list: a second try asks first.
      if (done > 0) this._setWeekListTime(week, new Date().toISOString());
      const total = Number((err as WsError)?.translation_placeholders?.total ?? 0);
      this._showToast(
        done > 0
          ? this._t("shopping_partial", { done, total, message: this._err(err) })
          : this._t("shopping_failed", { message: this._err(err) }),
        "error",
      );
    } finally {
      this._weekBusy = false;
    }
  }

  private _setWeekListTime(week: string, at: string): void {
    if (this._planner?.week_start === week) this._planner = { ...this._planner, shopping_list_at: at };
  }

  private _formatWhen(iso: string): string {
    const when = new Date(iso);
    if (Number.isNaN(when.getTime())) return iso;
    const options: Intl.DateTimeFormatOptions = {
      weekday: "long",
      day: "numeric",
      month: "long",
      hour: "2-digit",
      minute: "2-digit",
    };
    const zone = this._hass?.config?.time_zone;
    try {
      return when.toLocaleString(this._lang, zone ? { ...options, timeZone: zone } : options);
    } catch {
      return when.toLocaleString(this._lang, options);
    }
  }

  // ---- hide / unhide

  private _patchRecipe(id: number, patch: Partial<CollectionRecipe>): void {
    this._collection = this._collection.map((r) => (r.kitchenowl_id === id ? { ...r, ...patch } : r));
    if (this._ko?.kitchenowl_id === id) {
      const { tags, hidden } = patch;
      this._ko = { ...this._ko, ...(tags ? { tags } : {}), ...(hidden != null ? { hidden } : {}) };
    }
  }

  private async _setHidden(id: number, name: string, hidden: boolean, undoable = true): Promise<void> {
    if (this._busy.has(id)) return;
    this._setBusy(id, true);
    this._patchRecipe(id, { hidden });
    if (hidden) {
      const sel = new Set(this._selected);
      sel.delete(id);
      this._selected = sel;
    }
    try {
      await this._ws({ type: hidden ? "eatfresh/collection/hide" : "eatfresh/collection/unhide", kitchenowl_id: id });
      // A hidden recipe no longer counts as a favorite in the search.
      if (this._recipe?.kitchenowl_id === id) {
        this._recipe = { ...this._recipe, favorite: !hidden && this._recipe.favorite };
        this._favs.delete(this._recipe.recipe.key);
      }
      this._showToast(this._t(hidden ? "hidden_done" : "unhidden_done", { name }), "ok", {
        action: undoable
          ? { label: this._t("undo"), run: () => this._setHidden(id, name, !hidden, false) }
          : undefined,
        ms: undoable ? UNDO_MS : TOAST_MS,
      });
    } catch (err) {
      this._patchRecipe(id, { hidden: !hidden });
      this._showToast(this._t(hidden ? "hide_failed" : "unhide_failed", { message: this._err(err) }), "error");
    } finally {
      this._setBusy(id, false);
    }
  }

  // ---- categories

  private _knownTags(id: number): string[] | undefined {
    if (this._ko?.kitchenowl_id === id) return this._ko.tags;
    return this._collection.find((r) => r.kitchenowl_id === id)?.tags;
  }

  private async _openCategories(id: number, name: string, tags?: string[]): Promise<void> {
    const known = tags ?? this._knownTags(id);
    this._customTag = "";
    this._dialog = {
      kind: "categories",
      id,
      name,
      tags: [...(known ?? [])],
      original: [...(known ?? [])],
      loading: !known,
      busy: false,
      error: "",
    };
    const tagsDone = this._ensureTags();
    if (known) return;
    try {
      const res = await this._ws<CollectionRecipeResponse>({ type: "eatfresh/collection/recipe", kitchenowl_id: id });
      await tagsDone;
      const d = this._dialog;
      if (d?.kind === "categories" && d.id === id)
        this._dialog = { ...d, tags: [...res.tags], original: [...res.tags], loading: false };
    } catch (err) {
      const d = this._dialog;
      if (d?.kind === "categories" && d.id === id)
        this._dialog = { ...d, loading: false, error: this._t("categories_load_failed", { message: this._err(err) }) };
    }
  }

  private _toggleDialogTag(tag: string): void {
    const d = this._dialog;
    if (d?.kind !== "categories") return;
    const has = d.tags.some((t) => lower(t) === lower(tag));
    this._dialog = { ...d, tags: has ? d.tags.filter((t) => lower(t) !== lower(tag)) : [...d.tags, tag] };
  }

  private _addCustomTag(): void {
    const d = this._dialog;
    const tag = this._customTag.trim().replace(/\s+/g, " ");
    if (d?.kind !== "categories" || !tag) return;
    this._dialog = { ...d, tags: uniqueTags(d.tags, [tag]) };
    this._customTag = "";
  }

  private async _saveTags(id: number, name: string, tags: string[], before: string[], undoable = true): Promise<void> {
    const d = this._dialog;
    if (d?.kind === "categories") this._dialog = { ...d, busy: true, error: "" };
    try {
      const res = await this._ws<{ tags: string[] }>({
        type: "eatfresh/collection/set_tags",
        kitchenowl_id: id,
        tags,
      });
      this._patchRecipe(id, { tags: res.tags ?? tags });
      this._tags = this._tags ? { ...this._tags, tags: uniqueTags(this._tags.tags, res.tags ?? tags) } : this._tags;
      if (this._dialog?.kind === "categories") this._dialog = undefined;
      this._showToast(this._t("categories_saved"), "ok", {
        action: undoable ? { label: this._t("undo"), run: () => this._saveTags(id, name, before, tags, false) } : undefined,
        ms: undoable ? UNDO_MS : TOAST_MS,
      });
    } catch (err) {
      const message = this._t("categories_failed", { message: this._err(err) });
      const cur = this._dialog;
      if (cur?.kind === "categories") this._dialog = { ...cur, busy: false, error: message };
      else this._showToast(message, "error");
    }
  }

  // ---- week plan

  private _openPlan(id: number, name: string, image: string | null): void {
    this._dialog = { kind: "plan", id, name, image };
    this._ensureToday();
  }

  private _plannerPatch(fn: (p: PlannerResponse) => PlannerResponse): void {
    if (this._planner) this._planner = fn(this._planner);
  }

  private _insertEntry(date: string, entry: PlannerEntry): void {
    this._plannerPatch((p) => ({
      ...p,
      days: p.days.map((d) =>
        d.date === date && !d.entries.some((e) => e.kitchenowl_id === entry.kitchenowl_id)
          ? { ...d, entries: [...d.entries, entry] }
          : d,
      ),
    }));
  }

  private _dropEntry(date: string | null, id: number): void {
    this._plannerPatch((p) =>
      date
        ? { ...p, days: p.days.map((d) => (d.date === date ? { ...d, entries: d.entries.filter((e) => e.kitchenowl_id !== id) } : d)) }
        : { ...p, unscheduled: p.unscheduled.filter((e) => e.kitchenowl_id !== id) },
    );
  }

  /** Put a recipe on a day. The plan view shows it at once. */
  private async _plan(entry: PlannerEntry, date: string, undoable = true): Promise<void> {
    this._dialog = undefined;
    this._insertEntry(date, entry);
    try {
      await this._ws({ type: "eatfresh/planner/add", kitchenowl_id: entry.kitchenowl_id, date });
      // KitchenOwl replaces an entry without a day when the recipe gets a day.
      this._dropEntry(null, entry.kitchenowl_id);
      this._plannerStale = true;
      if (undoable)
        this._showToast(this._t("planned", { name: entry.name, day: formatDay(this._lang, date) }), "ok", {
          action: { label: this._t("undo"), run: () => this._unplan(entry, date, false) },
          ms: UNDO_MS,
        });
    } catch (err) {
      this._dropEntry(date, entry.kitchenowl_id);
      this._showToast(this._t("plan_failed", { message: this._err(err) }), "error");
    }
  }

  /**
   * Take a recipe off the plan at once, with "Undo". An entry without a day
   * cannot be put back through the API, so its removal waits for the hint
   * to go away and "Undo" simply cancels it.
   */
  private async _unplan(entry: PlannerEntry, date: string | null, undoable = true): Promise<void> {
    this._dropEntry(date, entry.kitchenowl_id);
    const text = this._t("removed", { name: entry.name });
    if (!date) {
      const restore = () =>
        this._plannerPatch((p) => ({ ...p, unscheduled: [...p.unscheduled, entry] }));
      let undone = false;
      this._showToast(text, "ok", {
        action: {
          label: this._t("undo"),
          run: () => {
            undone = true;
            restore();
          },
        },
        ms: UNDO_MS,
        onExpire: () => {
          if (undone) return;
          this._ws({ type: "eatfresh/planner/remove", kitchenowl_id: entry.kitchenowl_id })
            .then(() => (this._plannerStale = true))
            .catch((err) => {
              restore();
              this._showToast(this._t("remove_failed", { message: this._err(err) }), "error");
            });
        },
      });
      return;
    }
    try {
      await this._ws({ type: "eatfresh/planner/remove", kitchenowl_id: entry.kitchenowl_id, date });
      this._plannerStale = true;
      if (undoable)
        this._showToast(text, "ok", {
          action: { label: this._t("undo"), run: () => this._plan(entry, date, false) },
          ms: UNDO_MS,
        });
    } catch (err) {
      this._insertEntry(date, entry);
      this._showToast(this._t("remove_failed", { message: this._err(err) }), "error");
    }
  }

  private _openPick(date: string): void {
    this._pickQuery = "";
    this._dialog = { kind: "pick", date };
    if (this._collectionStale || this._collectionState !== "done") this._loadCollection();
  }

  // ---- toast

  private _showToast(
    text: string,
    kind: Toast["kind"],
    opts: { action?: ToastAction; ms?: number; onExpire?: () => void } = {},
  ): void {
    this._clearToast();
    this._toast = { text, kind, id: Date.now(), action: opts.action, onExpire: opts.onExpire };
    this._toastTimer = window.setTimeout(() => this._clearToast(), opts.ms ?? TOAST_MS);
  }

  private _clearToast(): void {
    window.clearTimeout(this._toastTimer);
    const toast = this._toast;
    this._toast = undefined;
    toast?.onExpire?.();
  }

  private _runToastAction(): void {
    const toast = this._toast;
    if (!toast?.action) return;
    window.clearTimeout(this._toastTimer);
    this._toast = undefined;
    toast.action.run();
  }

  // ----------------------------------------------------------------- render

  protected render(): TemplateResult {
    const v = this._view.name;
    const tabs: [Tab, string, StringKey][] = [
      ["search", mdiMagnify, "nav_search"],
      ["collection", mdiBookOpenPageVariantOutline, "nav_collection"],
      ["planner", mdiCalendarWeek, "nav_planner"],
    ];
    const nav = tabs.map(
      ([tab, ico, label]) => html`<button
        class="nav-btn"
        aria-current=${this._tab === tab ? "page" : "false"}
        @click=${() => this._navigate({ name: tab })}
      >
        ${icon(ico)}<span>${this._t(label)}</span>
      </button>`,
    );
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
          <button
            class="link-btn ${this._wide ? "btn" : "icon-btn"}"
            aria-label=${this._t("link_title")}
            title=${this._t("link_title")}
            aria-haspopup="dialog"
            @click=${() => {
              this._linkInvalid = false;
              this._dialog = { kind: "link" };
            }}
          >
            ${icon(mdiLinkVariant)}${this._wide ? html`<span>${this._t("link_open")}</span>` : nothing}
          </button>
        </header>
        <div class="body">
          <main>
            <div class="content">
              ${v === "search"
                ? this._renderSearch()
                : v === "recipe"
                  ? this._renderRecipe()
                  : v === "korecipe"
                    ? this._renderKoRecipe()
                    : v === "planner"
                      ? this._renderPlanner()
                      : this._renderCollection()}
            </div>
          </main>
          ${this._renderToast()}
        </div>
        ${this._wide
          ? nothing
          : html`<nav class="bottom-nav" aria-label=${this._t("nav_label")}>${nav}</nav>`}
        <dialog
          class="dlg"
          aria-label=${this._dialogTitle()}
          @close=${() => (this._dialog = undefined)}
          @click=${(e: MouseEvent) => {
            // A tap on the dimmed backdrop closes the dialog.
            if (e.target === e.currentTarget) this._dialog = undefined;
          }}
        >
          ${this._dialog ? this._renderDialog() : nothing}
        </dialog>
      </div>
    `;
  }

  private _renderToast(): TemplateResult {
    const toast = this._toast;
    return html`<div class="sr" role="status" aria-live="polite">${toast?.text ?? ""}</div>
      ${toast
        ? html`<div class="toast ${toast.kind}">
            <span class="lead">${icon(toast.kind === "ok" ? mdiCheckCircleOutline : mdiAlertCircleOutline)}</span>
            <span class="msg">${toast.text}</span>
            ${toast.action
              ? html`<button class="toast-action" @click=${this._runToastAction}>${toast.action.label}</button>`
              : nothing}
            <button class="icon-btn" aria-label=${this._t("close")} @click=${() => this._clearToast()}>
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

  private _heart(key: string, fav: boolean, title: string, cls = "heart"): TemplateResult {
    const busy = this._favBusy.has(key);
    return html`<button
      class="${cls} ${busy ? "busy" : ""}"
      aria-pressed=${fav ? "true" : "false"}
      aria-label=${this._t(fav ? "favorite_remove" : "favorite_add")}
      title=${this._t(fav ? "favorite_remove" : "favorite_add")}
      @click=${(e: Event) => {
        e.preventDefault();
        e.stopPropagation();
        this._toggleFav(key, fav, title);
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

  private _searchField(
    value: string,
    label: string,
    placeholder: string,
    onInput: (value: string) => void,
  ): TemplateResult {
    return html`<label class="field">
      ${icon(mdiMagnify)}
      <span class="sr">${label}</span>
      <input
        type="search"
        enterkeyhint="search"
        autocomplete="off"
        .value=${live(value)}
        placeholder=${placeholder}
        @input=${(e: Event) => onInput((e.target as HTMLInputElement).value)}
      />
      ${value
        ? html`<button
            type="button"
            class="icon-btn clear"
            aria-label=${this._t("filter_clear")}
            @click=${() => onInput("")}
          >
            ${icon(mdiClose)}
          </button>`
        : nothing}
    </label>`;
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
        ${this._searchField(this._query, this._t("search_label"), this._t("search_placeholder"), (v) => {
          this._query = v;
        })}
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
    const link = this._viewLink({ name: "recipe", key: hit.key });
    return html`<article class="card">
      <a class="card-link" href=${link.href} @click=${link.click}>
        ${this._photo(hit.image)}
        <div class="card-body">
          <h3 class="card-title">${hit.title}</h3>
          <div class="meta">
            ${time ? html`<span>${icon(mdiClockOutline)}${time}</span>` : nothing}
            <span class="src">${this._sourceName(hit.source)}</span>
          </div>
        </div>
      </a>
      ${this._heart(hit.key, fav, hit.title)}
    </article>`;
  }

  // ---- recipe views

  private _backRow(): TemplateResult {
    return html`<div class="back-row">
      <button class="nav-btn" @click=${this._back}>${icon(mdiArrowLeft)}<span>${this._t("back")}</span></button>
    </div>`;
  }

  private _recipeSkeleton(): TemplateResult {
    return html`${this._backRow()}
      <div class="recipe-head" aria-busy="true" aria-label=${this._t("loading")}>
        <div class="recipe-top">
          <div class="skel line" style="height:1.6em"></div>
          <div class="skel line short"></div>
        </div>
        <div class="photo hero skel"></div>
      </div>`;
  }

  private _sourceLink(url: string): TemplateResult | typeof nothing {
    return isHttpUrl(url)
      ? html`<a class="btn" href=${url} target="_blank" rel="noopener noreferrer">
          ${icon(mdiOpenInNew)}<span>${this._t("open_source")}</span>
        </a>`
      : nothing;
  }

  /**
   * Shared recipe layout. On a phone the title and the actions come first,
   * so the important buttons are on screen without scrolling.
   */
  private _recipeLayout(
    r: Recipe,
    sourceLabel: string,
    actions: TemplateResult,
    extra: TemplateResult | typeof nothing = nothing,
  ): TemplateResult {
    const facts: [string, string][] = [];
    const total = formatMinutes(this._lang, r.total_time);
    const prep = formatMinutes(this._lang, r.prep_time);
    const cook = formatMinutes(this._lang, r.cook_time);
    if (total) facts.push([this._t("total_time"), total]);
    if (prep) facts.push([this._t("prep_time"), prep]);
    if (cook) facts.push([this._t("cook_time"), cook]);
    const servings =
      r.servings == null ? "" : r.servings === 1 ? this._t("servings_one") : this._t("servings", { n: r.servings });
    return html`${this._backRow()}
      <div class="recipe-head">
        <div class="recipe-top">
          <h2 class="recipe-title">${r.title}</h2>
          ${sourceLabel ? html`<div class="meta"><span class="src">${sourceLabel}</span></div>` : nothing}
          <div class="actions">${actions}</div>
          ${extra}
        </div>
        ${this._photo(r.image, "hero")}
        <div class="recipe-rest">
          ${r.description ? html`<p class="recipe-desc">${r.description}</p>` : nothing}
          ${facts.length || servings
            ? html`<ul class="facts">
                ${facts.map(([label, value]) => html`<li>${icon(mdiClockOutline)}${label}: ${value}</li>`)}
                ${servings ? html`<li>${icon(mdiSilverwareForkKnife)}${servings}</li>` : nothing}
              </ul>`
            : nothing}
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

  private _renderRecipe(): TemplateResult {
    const view = this._view as View & { name: "recipe" };
    if (this._recipeState === "error") {
      if (this._recipeMissing) {
        const page = view.url ?? this._hits.find((h) => h.key === view.key)?.url;
        return html`${this._backRow()}
          <div class="note">
            ${icon(mdiSilverwareForkKnife)}
            <div>${this._t("recipe_missing")}</div>
            ${page ? this._sourceLink(page) : nothing}
          </div>`;
      }
      return html`${this._backRow()}${this._note(
        `${this._t("recipe_failed")} ${this._recipeError}`,
        mdiAlertCircleOutline,
        () => this._loadRecipe(view, true),
      )}`;
    }
    const data = this._recipe;
    if (!data || this._recipeState === "loading") return this._recipeSkeleton();
    const r = data.recipe;
    const fav = this._isFav(r.key, data.favorite);
    const koId = data.kitchenowl_id;
    const inKo = koId != null;
    const actions = html`
      ${inKo
        ? html`<button class="btn primary" ?disabled=${this._shoppingBusy} @click=${() => this._addToShopping([koId])}>
            ${icon(mdiCartPlus)}<span>${this._t("to_shopping_list")}</span>
          </button>`
        : nothing}
      ${this._heart(r.key, fav, r.title, "btn fav")}
      ${inKo
        ? html`<button class="btn" @click=${() => this._openPlan(koId, r.title, r.image)}>
              ${icon(mdiCalendarPlus)}<span>${this._t("plan")}</span>
            </button>
            <button class="btn" @click=${() => this._openCategories(koId, r.title)}>
              ${icon(mdiTagMultipleOutline)}<span>${this._t("categories")}</span>
            </button>`
        : nothing}
      ${this._sourceLink(r.url)}
    `;
    const label = r.source === "jsonld" ? hostOf(r.url) : this._sourceName(r.source);
    return this._recipeLayout(
      r,
      label,
      actions,
      inKo ? nothing : html`<p class="hint">${this._t("shopping_hint")}</p>`,
    );
  }

  private _renderKoRecipe(): TemplateResult {
    const view = this._view as View & { name: "korecipe" };
    if (this._koState === "error")
      return html`${this._backRow()}${this._note(
        `${this._t("recipe_failed")} ${this._koError}`,
        mdiAlertCircleOutline,
        () => this._loadKoRecipe(view.id, true),
      )}`;
    const data = this._ko;
    if (!data || this._koState === "loading") return this._recipeSkeleton();
    const r = data.recipe;
    const id = data.kitchenowl_id;
    const busy = this._busy.has(id);
    const actions = html`
      <button class="btn primary" ?disabled=${this._shoppingBusy} @click=${() => this._addToShopping([id])}>
        ${icon(mdiCartPlus)}<span>${this._t("to_shopping_list")}</span>
      </button>
      <button class="btn" @click=${() => this._openPlan(id, r.title, r.image)}>
        ${icon(mdiCalendarPlus)}<span>${this._t("plan")}</span>
      </button>
      <button class="btn" @click=${() => this._openCategories(id, r.title, data.tags)}>
        ${icon(mdiTagMultipleOutline)}<span>${this._t("categories")}</span>
      </button>
      <button class="btn" ?disabled=${busy} @click=${() => this._setHidden(id, r.title, !data.hidden)}>
        ${icon(data.hidden ? mdiEyeOutline : mdiEyeOffOutline)}<span>${this._t(data.hidden ? "unhide" : "hide")}</span>
      </button>
      ${this._sourceLink(r.url)}
    `;
    const extra = html`${data.hidden || data.tags.length
      ? html`<ul class="tag-list">
          ${data.hidden ? html`<li class="badge">${icon(mdiEyeOffOutline)}${this._t("hidden_badge")}</li>` : nothing}
          ${data.tags.map((t) => html`<li>${t}</li>`)}
        </ul>`
      : nothing}`;
    return this._recipeLayout(r, isHttpUrl(r.url) ? hostOf(r.url) : "KitchenOwl", actions, extra);
  }

  // ---- collection view

  /** Chips for the filter: canonical categories first, then the other tags. */
  private get _filterTags(): string[] {
    const used = uniqueTags(...this._collection.filter((r) => this._showHidden || !r.hidden).map((r) => r.tags));
    const usedSet = new Set(used.map(lower));
    const canonical = (this._tags?.categories ?? []).filter((c) => usedSet.has(lower(c)));
    const canonSet = new Set(canonical.map(lower));
    const rest = used.filter((t) => !canonSet.has(lower(t))).sort((a, b) => a.localeCompare(b, this._lang));
    // Keep chips that are switched on, even if no recipe has them any more.
    return uniqueTags(canonical, rest, [...this._filter]);
  }

  private get _visibleCollection(): CollectionRecipe[] {
    const q = lower(this._collectionQuery);
    const want = [...this._filter].map(lower);
    return this._collection.filter((r) => {
      if (r.hidden && !this._showHidden) return false;
      if (q && !lower(r.name).includes(q)) return false;
      const tags = new Set(r.tags.map(lower));
      return want.every((t) => tags.has(t));
    });
  }

  private _toggleFilter(tag: string): void {
    const next = new Set(this._filter);
    const hit = [...next].find((t) => lower(t) === lower(tag));
    if (hit) next.delete(hit);
    else next.add(tag);
    this._filter = next;
  }

  private _toggleShowHidden(): void {
    this._showHidden = !this._showHidden;
    if (this._showHidden && !this._collectionHidden) this._loadCollection();
  }

  private _renderCollection(): TemplateResult {
    if (this._collectionState === "loading" || this._collectionState === "idle")
      return html`<p class="intro">${this._t("collection_intro")}</p>${this._skeletonCards()}`;
    if (this._collectionState === "error")
      return this._note(
        `${this._t("collection_failed")} ${this._collectionError}`,
        mdiAlertCircleOutline,
        () => this._loadCollection(),
      );
    if (!this._collection.length && !this._showHidden)
      return this._note(this._t("collection_empty"), mdiHeartOutline);
    const n = this._selected.size;
    const visible = this._visibleCollection;
    const filterTags = this._filterTags;
    const filtered = this._filter.size > 0 || !!this._collectionQuery.trim();
    return html`
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
        : nothing}
      <div class="search-form" role="search">
        ${this._searchField(
          this._collectionQuery,
          this._t("collection_search_label"),
          this._t("collection_search_placeholder"),
          (v) => (this._collectionQuery = v),
        )}
      </div>
      <fieldset class="chips ${this._wide ? "" : "scroll"}">
        <legend>${this._t("filter_label")}</legend>
        ${filterTags.map((tag) => {
          const on = [...this._filter].some((t) => lower(t) === lower(tag));
          return html`<button type="button" class="chip" aria-pressed=${on ? "true" : "false"} @click=${() => this._toggleFilter(tag)}>
            ${on ? icon(mdiCheck) : nothing}${tag}
          </button>`;
        })}
        <button
          type="button"
          class="chip toggle"
          aria-pressed=${this._showHidden ? "true" : "false"}
          @click=${this._toggleShowHidden}
        >
          ${icon(this._showHidden ? mdiEyeOutline : mdiEyeOffOutline)}${this._t("show_hidden")}
        </button>
      </fieldset>
      <p class="intro">${this._t("collection_intro")}</p>
      ${visible.length
        ? html`<div class="grid">${visible.map((r) => this._renderCollectionCard(r))}</div>`
        : html`<div class="note">
            ${icon(mdiMagnify)}
            <div>${filtered ? this._t("filter_empty") : this._t("collection_empty")}</div>
            ${filtered
              ? html`<button
                  class="btn"
                  @click=${() => {
                    this._filter = new Set();
                    this._collectionQuery = "";
                  }}
                >
                  ${this._t("filter_clear")}
                </button>`
              : nothing}
          </div>`}
    `;
  }

  private _renderCollectionCard(r: CollectionRecipe): TemplateResult {
    const id = r.kitchenowl_id;
    const selected = this._selected.has(id);
    const busy = this._busy.has(id);
    const time = formatMinutes(this._lang, r.time);
    const host = r.source && isHttpUrl(r.source) ? hostOf(r.source) : "";
    const link = this._viewLink({ name: "korecipe", id });
    const toggle = () => {
      const next = new Set(this._selected);
      if (selected) next.delete(id);
      else next.add(id);
      this._selected = next;
    };
    return html`<article class="card ${selected ? "selected" : ""} ${r.hidden ? "is-hidden" : ""}">
      <a class="card-link" href=${link.href} @click=${link.click}>
        ${this._photo(r.image)}
        <div class="card-body">
          <h3 class="card-title">${r.name}</h3>
          <div class="meta">
            ${time ? html`<span>${icon(mdiClockOutline)}${time}</span>` : nothing}
            ${host ? html`<span class="src">${host}</span>` : nothing}
          </div>
          ${r.hidden || r.tags.length
            ? html`<ul class="tag-list small">
                ${r.hidden ? html`<li class="badge">${this._t("hidden_badge")}</li>` : nothing}
                ${r.tags.slice(0, 3).map((t) => html`<li>${t}</li>`)}
                ${r.tags.length > 3 ? html`<li>+${r.tags.length - 3}</li>` : nothing}
              </ul>`
            : nothing}
        </div>
      </a>
      <button
        class="check-btn"
        role="checkbox"
        aria-checked=${selected ? "true" : "false"}
        aria-label=${`${this._t("select_for_list")}: ${r.name}`}
        title=${this._t("select_for_list")}
        @click=${toggle}
      >
        <span class="check" aria-hidden="true">${selected ? icon(mdiCheck) : nothing}</span>
      </button>
      <div class="card-actions">
        <button
          class="icon-btn"
          aria-label=${`${this._t("categories")}: ${r.name}`}
          title=${this._t("categories")}
          @click=${() => this._openCategories(id, r.name, r.tags)}
        >
          ${icon(mdiTagMultipleOutline)}
        </button>
        <button
          class="icon-btn"
          aria-label=${`${this._t("plan")}: ${r.name}`}
          title=${this._t("plan")}
          @click=${() => this._openPlan(id, r.name, r.image)}
        >
          ${icon(mdiCalendarPlus)}
        </button>
        <button
          class="icon-btn ${r.hidden ? "unhide" : ""}"
          aria-label=${`${this._t(r.hidden ? "unhide" : "hide")}: ${r.name}`}
          title=${this._t(r.hidden ? "unhide" : "hide")}
          ?disabled=${busy}
          @click=${() => this._setHidden(id, r.name, !r.hidden)}
        >
          ${icon(r.hidden ? mdiEyeOutline : mdiEyeOffOutline)}
        </button>
      </div>
    </article>`;
  }

  // ---- week plan view

  private _renderPlanner(): TemplateResult {
    const week = this._weekStart;
    const current = mondayOf(this._today);
    const data = this._planner?.week_start === week ? this._planner : undefined;
    const planned = data ? data.days.reduce((n, d) => n + d.entries.length, 0) : 0;
    const head = html`<div class="week-head">
      <div class="week-nav">
        <button class="icon-btn" aria-label=${this._t("planner_prev")} title=${this._t("planner_prev")} @click=${() => this._goWeek(addDays(week, -7))}>
          ${icon(mdiChevronLeft)}
        </button>
        <h2 class="week-label">${formatWeek(this._lang, week)}</h2>
        <button class="icon-btn" aria-label=${this._t("planner_next")} title=${this._t("planner_next")} @click=${() => this._goWeek(addDays(week, 7))}>
          ${icon(mdiChevronRight)}
        </button>
      </div>
      <div class="week-actions">
        ${week !== current
          ? html`<button class="btn" @click=${() => this._goWeek(current)}>${this._t("planner_this")}</button>`
          : nothing}
        <button
          class="btn primary grow"
          ?disabled=${this._weekBusy || !data || planned === 0}
          aria-label=${this._t("week_to_shopping")}
          @click=${() => this._weekToShopping()}
        >
          ${icon(mdiCartPlus)}<span>${this._wide ? this._t("week_to_shopping") : this._t("week_to_shopping_short")}</span>
        </button>
      </div>
    </div>`;
    if (this._plannerState === "error" && !data)
      return html`${head}${this._note(
        `${this._t("planner_failed")} ${this._plannerError}`,
        mdiAlertCircleOutline,
        () => this._loadPlanner(),
      )}`;
    if (!data)
      return html`${head}<div class="days" aria-busy="true" aria-label=${this._t("loading")}>
          ${Array.from(
            { length: 7 },
            () => html`<section class="day"><div class="skel line short"></div><div class="skel line"></div></section>`,
          )}
        </div>`;
    const now = this._today;
    return html`${head}
      <div class="days">
        ${data.days.map((day) => {
          const isToday = day.date === now;
          return html`<section class="day ${isToday ? "today" : ""}" aria-current=${isToday ? "date" : "false"}>
            <header class="day-head">
              <h3>
                <span class="wd">${weekdayName(this._lang, day.date)}</span>
                <span class="dt">${formatDay(this._lang, day.date, "short").replace(/^[^\d]+/, "")}</span>
                ${isToday ? html`<span class="today-badge">${this._t("planner_today")}</span>` : nothing}
                ${day.entries.length ? nothing : html`<span class="empty-inline">${this._t("planner_empty_day")}</span>`}
              </h3>
              <button
                class="icon-btn add"
                aria-label=${this._t("planner_add", { day: formatDay(this._lang, day.date) })}
                title=${this._t("planner_add", { day: formatDay(this._lang, day.date) })}
                @click=${() => this._openPick(day.date)}
              >
                ${icon(mdiPlus)}
              </button>
            </header>
            ${day.entries.length
              ? html`<ul class="entries">${day.entries.map((e) => this._renderEntry(e, day.date))}</ul>`
              : nothing}
          </section>`;
        })}
      </div>
      ${data.unscheduled.length
        ? html`<section class="day unscheduled">
            <header class="day-head"><h3>${this._t("planner_unscheduled")}</h3></header>
            <p class="empty-day">${this._t("planner_unscheduled_hint")}</p>
            <ul class="entries">${data.unscheduled.map((e) => this._renderEntry(e, null))}</ul>
          </section>`
        : nothing}`;
  }

  private _renderEntry(e: PlannerEntry, date: string | null): TemplateResult {
    const link = this._viewLink({ name: "korecipe", id: e.kitchenowl_id });
    return html`<li class="entry">
      <a class="entry-link" href=${link.href} @click=${link.click}>
        ${this._photo(e.image, "thumb")}
        <span class="entry-name">${e.name}</span>
      </a>
      <button
        class="icon-btn"
        aria-label=${this._t("planner_remove", { name: e.name })}
        title=${this._t("planner_remove", { name: e.name })}
        @click=${() => this._unplan(e, date)}
      >
        ${icon(mdiClose)}
      </button>
    </li>`;
  }

  // ---- dialogs

  private _dialogTitle(): string {
    const d = this._dialog;
    if (!d) return "";
    switch (d.kind) {
      case "link":
        return this._t("link_title");
      case "categories":
        return this._t("categories_title", { name: d.name });
      case "plan":
        return this._t("plan_title", { name: d.name });
      case "pick":
        return this._t("pick_title", { day: formatDay(this._lang, d.date) });
      case "week_again":
        return this._t("week_again_title");
    }
  }

  private _dialogFrame(body: TemplateResult, foot: TemplateResult | typeof nothing = nothing): TemplateResult {
    return html`<div class="dlg-head">
        <h2>${this._dialogTitle()}</h2>
        <button class="icon-btn" aria-label=${this._t("close")} @click=${() => (this._dialog = undefined)}>
          ${icon(mdiClose)}
        </button>
      </div>
      <div class="dlg-body">${body}</div>
      ${foot === nothing ? nothing : html`<div class="dlg-foot">${foot}</div>`}`;
  }

  private _renderDialog(): TemplateResult {
    const d = this._dialog!;
    switch (d.kind) {
      case "link":
        return this._renderLinkDialog();
      case "categories":
        return this._renderCategoriesDialog(d);
      case "plan":
        return this._renderPlanDialog(d);
      case "pick":
        return this._renderPickDialog(d);
      case "week_again":
        return this._renderWeekAgainDialog(d);
    }
  }

  private _renderLinkDialog(): TemplateResult {
    return this._dialogFrame(html`
      <p class="dlg-hint">${this._t("link_hint")}</p>
      <form
        class="search-form"
        novalidate
        @submit=${(e: Event) => {
          e.preventDefault();
          const input = (e.target as HTMLFormElement).querySelector("input");
          this._submitLink(input?.value ?? "");
        }}
      >
        <label class="field">
          ${icon(mdiLinkVariant)}
          <span class="sr">${this._t("link_title")}</span>
          <input
            type="url"
            inputmode="url"
            enterkeyhint="go"
            autocomplete="off"
            autocapitalize="off"
            spellcheck="false"
            placeholder=${this._t("link_placeholder")}
            aria-invalid=${this._linkInvalid ? "true" : "false"}
            @input=${() => (this._linkInvalid = false)}
          />
        </label>
        <button class="btn primary" type="submit">${this._t("link_button")}</button>
      </form>
      ${this._linkInvalid ? html`<p class="error-text" role="alert">${this._t("link_invalid")}</p>` : nothing}
    `);
  }

  private _renderCategoriesDialog(d: Dialog & { kind: "categories" }): TemplateResult {
    const options = uniqueTags(this._tags?.categories, d.original, d.tags, this._tags?.tags);
    const body = d.loading
      ? html`<div class="skel line"></div><div class="skel line short"></div>`
      : html`
          <fieldset class="chips">
            <legend>${this._t("categories")}</legend>
            ${options.map((tag) => {
              const on = d.tags.some((t) => lower(t) === lower(tag));
              return html`<button type="button" class="chip" aria-pressed=${on ? "true" : "false"} @click=${() => this._toggleDialogTag(tag)}>
                ${on ? icon(mdiCheck) : nothing}${tag}
              </button>`;
            })}
          </fieldset>
          <form
            class="search-form custom-tag"
            @submit=${(e: Event) => {
              e.preventDefault();
              this._addCustomTag();
            }}
          >
            <label class="field">
              <span class="sr">${this._t("categories_custom")}</span>
              <input
                type="text"
                enterkeyhint="done"
                autocomplete="off"
                maxlength="40"
                .value=${live(this._customTag)}
                placeholder=${`${this._t("categories_custom")}, ${this._t("categories_custom_placeholder")}`}
                @input=${(e: Event) => (this._customTag = (e.target as HTMLInputElement).value)}
              />
            </label>
            <button class="btn" type="submit" ?disabled=${!this._customTag.trim()}>
              ${icon(mdiPlus)}<span>${this._t("categories_add")}</span>
            </button>
          </form>
        `;
    return this._dialogFrame(
      html`${body}${d.error ? html`<p class="error-text" role="alert">${d.error}</p>` : nothing}`,
      html`<button class="btn" @click=${() => (this._dialog = undefined)}>${this._t("cancel")}</button>
        <button
          class="btn primary"
          ?disabled=${d.loading || d.busy}
          @click=${() => this._saveTags(d.id, d.name, d.tags, d.original)}
        >
          ${icon(mdiCheck)}<span>${this._t("save")}</span>
        </button>`,
    );
  }

  private _renderPlanDialog(d: Dialog & { kind: "plan" }): TemplateResult {
    const start = this._today;
    const nextMonday = addDays(mondayOf(start), 7);
    const days = Array.from({ length: 14 }, (_, i) => addDays(start, i)).filter(
      (day) => day < addDays(nextMonday, 7),
    );
    const groups: [string, string[]][] = [
      [this._t("planner_this"), days.filter((day) => day < nextMonday)],
      [this._t("planner_next"), days.filter((day) => day >= nextMonday)],
    ];
    const entry: PlannerEntry = { kitchenowl_id: d.id, name: d.name, image: d.image };
    return this._dialogFrame(html`${groups.map(
      ([label, list]) => html`<h3 class="dlg-sub">${label}</h3>
        <div class="day-picks">
          ${list.map(
            (day) => html`<button class="btn day-pick ${day === start ? "today" : ""}" @click=${() => this._plan(entry, day)}>
              <span class="wd">${day === start ? this._t("planner_today") : weekdayName(this._lang, day)}</span>
              <span class="dt">${formatDay(this._lang, day, "short").replace(/^[^\d]+/, "")}</span>
            </button>`,
          )}
        </div>`,
    )}`);
  }

  private _renderWeekAgainDialog(d: Dialog & { kind: "week_again" }): TemplateResult {
    return this._dialogFrame(
      html`<p class="dlg-hint">${this._t("week_again_text", { when: this._formatWhen(d.at) })}</p>`,
      html`<button class="btn" @click=${() => (this._dialog = undefined)}>${this._t("cancel")}</button>
        <button
          class="btn primary"
          @click=${() => {
            this._dialog = undefined;
            if (this._weekStart === d.week) void this._weekToShopping(true);
          }}
        >
          ${icon(mdiCartPlus)}<span>${this._t("week_again_button")}</span>
        </button>`,
    );
  }

  private _renderPickDialog(d: Dialog & { kind: "pick" }): TemplateResult {
    const q = lower(this._pickQuery);
    const planned = new Set(
      this._planner?.days.find((day) => day.date === d.date)?.entries.map((e) => e.kitchenowl_id) ?? [],
    );
    const list = this._collection.filter((r) => !r.hidden && (!q || lower(r.name).includes(q)));
    let body: TemplateResult;
    if (this._collectionState === "error")
      body = this._note(`${this._t("collection_failed")} ${this._collectionError}`, mdiAlertCircleOutline, () =>
        this._loadCollection(),
      );
    else if (this._collectionState !== "done")
      body = html`<div class="skel line"></div><div class="skel line"></div><div class="skel line short"></div>`;
    else
      body = html`<ul class="pick-list">
        ${list.length
          ? list.map(
              (r) => html`<li>
                <button
                  class="pick"
                  ?disabled=${planned.has(r.kitchenowl_id)}
                  @click=${() => this._plan({ kitchenowl_id: r.kitchenowl_id, name: r.name, image: r.image }, d.date)}
                >
                  ${this._photo(r.image, "thumb")}<span class="entry-name">${r.name}</span>
                  ${planned.has(r.kitchenowl_id) ? icon(mdiCheck) : nothing}
                </button>
              </li>`,
            )
          : html`<li class="empty-day">${this._t("pick_empty")}</li>`}
      </ul>`;
    return this._dialogFrame(html`
      <div class="search-form" role="search">
        ${this._searchField(
          this._pickQuery,
          this._t("collection_search_label"),
          this._t("collection_search_placeholder"),
          (v) => (this._pickQuery = v),
        )}
      </div>
      ${body}
    `);
  }
}

if (!customElements.get("eatfresh-panel")) customElements.define("eatfresh-panel", EatFreshPanel);

declare global {
  interface HTMLElementTagNameMap {
    "eatfresh-panel": EatFreshPanel;
  }
}

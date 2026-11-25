import {
  mdiAlertCircleOutline,
  mdiArrowLeft,
  mdiBookOpenPageVariantOutline,
  mdiCalendarPlus,
  mdiCalendarWeek,
  mdiCancel,
  mdiCartCheck,
  mdiCartOutline,
  mdiCartPlus,
  mdiCheck,
  mdiCheckCircleOutline,
  mdiChevronDown,
  mdiChevronLeft,
  mdiChevronRight,
  mdiClockOutline,
  mdiClose,
  mdiDotsVertical,
  mdiEyeOffOutline,
  mdiEyeOutline,
  mdiHeart,
  mdiHeartOutline,
  mdiInformationOutline,
  mdiLinkVariant,
  mdiLinkVariantOff,
  mdiMagnify,
  mdiMenu,
  mdiMinus,
  mdiOpenInNew,
  mdiPlus,
  mdiRefresh,
  mdiShapeOutline,
  mdiSilverwareForkKnife,
  mdiStorefrontOutline,
  mdiSwapHorizontal,
  mdiTagMultipleOutline,
  mdiUndoVariant,
} from "@mdi/js";
import { LitElement, html, nothing, svg, type PropertyValues, type TemplateResult } from "lit";
import { property, query, state } from "lit/decorators.js";
import { live } from "lit/directives/live.js";
import { repeat } from "lit/directives/repeat.js";
import { pickLang, translate, type Lang, type StringKey } from "./i18n";
import { panelStyles } from "./styles";
import type {
  CollectionForgetResponse,
  CollectionRecipe,
  CollectionRecipeResponse,
  CollectionRestoreResponse,
  HomeAssistant,
  PanelRoute,
  PicnicHit,
  PicnicProduct,
  PicnicSendResponse,
  Portions,
  PlannerEntry,
  PlannerResponse,
  Recipe,
  RecipeResponse,
  SearchHit,
  ShopDepartment,
  ShopDone,
  ShoppingItem,
  ShoppingResponse,
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
  planErrorCode,
  formatDay,
  formatMinutes,
  formatPrice,
  formatWeek,
  hostOf,
  ingredientQty,
  isHttpUrl,
  localNumber,
  localQty,
  mondayOf,
  parsePath,
  picnicText,
  relativeDay,
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
  actions: ToastAction[];
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
  | { kind: "plan"; id: number; name: string; image: string | null; servings?: number }
  | { kind: "pick"; date: string }
  | { kind: "week_again"; week: string; at: string }
  | {
      kind: "product";
      item_id: number;
      name: string;
      query: string;
      state: Load;
      products: PicnicHit[];
      error: string;
      /** Set when the person picks a smaller package for the rest (0.5.0). */
      small?: { rest: string | null; main: string | null };
    }
  | { kind: "item_menu"; item_id: number }
  /** Choose the group of a shopping list entry (0.5.0). */
  | { kind: "department"; item_id: number }
  | { kind: "send"; n: number }
  | { kind: "forget_missing"; id: number };

const WIDE_MIN = 600;
const ROOMY_MIN = 960;
const TOAST_MS = 4500;
const UNDO_MS = 7000;
/** Codes of entries the core leaves out without a call to Picnic (no stop). */
const LIST_CODES = new Set(["twice", "not_on_list", "already_sent"]);
/** Limits of `eatfresh/picnic/send`: at most 60 entries, 1 to 20 pieces each. */
const SEND_MAX = 60;
const AMOUNT_MAX = 20;
const AMOUNT_SAVE_MS = 700;
/** After the last tick or untick call is back, the list is read again once (0.5.0). */
const SHOP_RELOAD_MS = 600;
/** Servings (0.5.0): limits, and the pause before the core is asked after a burst of taps. */
const SERVINGS_MIN = 1;
const SERVINGS_MAX = 99;
const KO_SERVINGS_MS = 250;
const PLAN_SERVINGS_MS = 400;
/** `rest` and `main_unit_quantity` of `eatfresh/picnic/search`: at most 30 characters. */
const REST_MAX = 30;

const clampServings = (n: number) => Math.min(SERVINGS_MAX, Math.max(SERVINGS_MIN, Math.round(n)));

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
  /** Room for text labels on the top bar (four tabs and the link button). */
  @state() private _roomy = false;
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
  /** A restore or forget call for the missing ingredients is running. */
  @state() private _koMissingBusy = false;

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

  @state() private _shop?: ShoppingResponse;
  @state() private _shopState: Load = "idle";
  @state() private _shopError = "";
  @state() private _shopLoading = false;
  /** Entries the user unticked (everything with a product is ticked by default). */
  @state() private _unpicked = new Set<number>();
  /** Entries with `cart_hint` (0.5.0) go only when ticked by hand: part of them is in the cart already. */
  @state() private _hintPicked = new Set<number>();
  @state() private _itemBusy = new Set<number>();
  @state() private _itemErrors = new Map<number, string>();
  @state() private _showSkipped = false;
  @state() private _sending = false;
  @state() private _sendNotice?: { kind: "partial" | "error"; text: string };
  /** The "Done" part of the shopping list is open (0.5.0). */
  @state() private _doneOpen = false;
  /**
   * Entries ticked off in the panel (0.5.0): hidden from the list at once. `seq` is the list load that
   * followed the core's yes; a load started after it shows the truth, then the entry goes from here.
   */
  @state() private _pendingDone = new Map<number, { entry: ShopDone; seq?: number }>();
  /** Ticked-off entries put back on the list in the panel, shown open until the list is read again. */
  @state() private _pendingBack = new Map<number, { entry: ShopDone; seq?: number }>();
  /** Short text for screen readers after ticking off or putting back. */
  @state() private _shopAnnounce = "";
  /** Servings shown in the open recipe of the collection; the core's answer follows (0.5.0). */
  @state() private _koServings?: number;
  /** True while a changed number of servings waits for the core: the ingredients still show the old amounts. */
  @state() private _koServingsBusy = false;
  /** Servings of week plan entries changed a moment ago, by "<id>|<date>", until the core has them. */
  @state() private _planServings = new Map<string, number>();

  @query("dialog") private _dialogEl?: HTMLDialogElement;

  private _hass?: HomeAssistant;
  private _searchSeq = 0;
  private _recipeSeq = 0;
  private _koSeq = 0;
  /** Counts view changes; a late answer is only used while the view is still the one it was asked for. */
  private _viewEpoch = 0;
  /** Close events still to come from our own dialog.close() calls (they must not clear a dialog opened since). */
  private _closeEvents = 0;
  private _collectionSeq = 0;
  private _plannerSeq = 0;
  private _toastTimer?: number;
  /** Tick or untick calls on their way; the list is read again once when all are back. */
  private _shopOps = 0;
  private _shopReloadTimer?: number;
  private _resize?: ResizeObserver;
  private _navigatedInside = false;
  /** Link whose recipe is saved by itself once it has loaded (set only by the link dialog and the search field). */
  private _autoSaveUrl?: string;
  private _collectionStale = true;
  private _collectionHidden = false;
  private _plannerStale = true;
  /** True once `_today` comes from Home Assistant. */
  private _todayKnown = false;
  /** True once the person has chosen a week; until then the core picks it. */
  private _weekChosen = false;
  private _shopSeq = 0;
  private _shopStale = true;
  private _productSeq = 0;
  private _pendingAmounts = new Map<string, number>();
  private _amountTimers = new Map<string, number>();
  /** Pieces of the smaller package changed in the panel, by ingredient name; the core has no call to keep them. */
  private _smallAmounts = new Map<string, number>();
  private _koServingsTimer?: number;
  private _planTimers = new Map<string, number>();
  private _planInflight = new Set<string>();

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
      const roomy = width >= ROOMY_MIN;
      if (roomy !== this._roomy) this._roomy = roomy;
    });
    this._resize.observe(this);
  }

  disconnectedCallback(): void {
    super.disconnectedCallback();
    window.clearTimeout(this._shopReloadTimer);
    window.removeEventListener("popstate", this._onPopState);
    this._resize?.disconnect();
    this._clearToast();
    this._cancelKoServings();
    // Servings of plan entries that still wait are sent now, like the quantities below.
    for (const [key, timer] of this._planTimers) {
      window.clearTimeout(timer);
      const [id, date] = key.split("|");
      void this._savePlanServings(Number(id), date);
    }
    // Save quantities that are still waiting.
    for (const [key, timer] of this._amountTimers) {
      window.clearTimeout(timer);
      const name = this._shop?.items.find((i) => lower(i.name) === key)?.name;
      if (name) void this._saveAmount(name);
    }
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
    } else if (!this._dialog && dlg.open) {
      this._closeEvents++;
      dlg.close();
    }
  }

  /** The native close event: Escape or a late event of our own close(). */
  private _onDialogClose(e: Event): void {
    if (this._closeEvents > 0) {
      this._closeEvents--;
      return;
    }
    if ((e.currentTarget as HTMLDialogElement).open) return;
    this._dialog = undefined;
  }

  /** True while the view still shows recipe `id` of the collection, as it did at `epoch`. */
  private _koStillShown(id: number, epoch: number): boolean {
    const v = this._view;
    return epoch === this._viewEpoch && v.name === "korecipe" && v.id === id;
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

  private _navigate(view: View, replace = false, autoSave = false): void {
    const url = this._prefix + viewPath(view);
    if (url !== window.location.pathname) {
      if (replace) window.history.replaceState(window.history.state, "", url);
      else window.history.pushState(null, "", url);
      if (!replace) this._navigatedInside = true;
      // Home Assistant listens to this event and updates `route`.
      window.dispatchEvent(new CustomEvent("location-changed", { detail: { replace } }));
    }
    this._applyView(view);
    if (autoSave && view.name === "recipe" && view.url) this._armAutoSave(view.url);
  }

  private _sameView(a: View, b: View): boolean {
    if (a.name !== b.name) return false;
    if (a.name === "recipe" && b.name === "recipe") return a.key === b.key && a.url === b.url;
    if (a.name === "korecipe" && b.name === "korecipe") return a.id === b.id;
    return true;
  }

  private _applyView(view: View): void {
    const changed = !this._sameView(this._view, view);
    if (changed) {
      this._view = view;
      this._viewEpoch++;
      // The lock of the missing-ingredient buttons belongs to the recipe that was open.
      this._koMissingBusy = false;
      // A number of servings still waiting belongs to the recipe that was open.
      this._cancelKoServings();
      // A hint belongs to the view it came from; do not carry it along.
      this._clearToast();
      this._autoSaveUrl = undefined;
      this._dialog = undefined;
      this.renderRoot.querySelector("main")?.scrollTo({ top: 0 });
    }
    if (view.name === "search" || view.name === "collection" || view.name === "planner" || view.name === "shopping")
      this._tab = view.name;
    else if (view.name === "korecipe" && this._tab === "search") this._tab = "collection";
    if (!this._hass) return;
    if (view.name === "recipe") this._loadRecipe(view);
    if (view.name === "korecipe") {
      // Nothing is remembered: a recipe opens again with its start value, or with the number of the plan entry.
      const p = this._ko?.kitchenowl_id === view.id ? this._ko.portions : undefined;
      const want = view.servings ?? p?.start ?? undefined;
      const reset = changed && !!p?.scalable && want != null && p.servings !== want;
      if (changed && !reset && this._ko && p) this._koServings = this._shownServings(this._ko);
      this._loadKoRecipe(view.id, reset, view.servings);
    }
    if (view.name === "collection" && (this._collectionStale || this._collectionState === "error"))
      this._loadCollection();
    if (view.name === "planner" && (this._plannerStale || this._plannerState === "error")) this._loadPlanner();
    // Read the list again each time the tab opens (KitchenOwl and the store only, never Picnic).
    if (view.name === "shopping" && !this._shopLoading && (changed || this._shopStale || !this._shop || this._shopState === "error"))
      this._loadShopping(!!this._shop);
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
      this._navigate({ name: "recipe", url: query }, false, true);
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
    this._navigate({ name: "recipe", url }, false, true);
  }

  /** Save the recipe of a link the person opened on purpose: now if it is already shown, else after loading. */
  private _armAutoSave(url: string): void {
    if (this._recipe && this._recipeState === "done" && this._recipeFor === `u:${url}`) {
      this._autoSave(this._recipe);
      return;
    }
    this._autoSaveUrl = url;
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
      // One shot: reload, back/forward and shared links never get here with the flag set.
      if (view.url && this._autoSaveUrl === view.url) {
        this._autoSaveUrl = undefined;
        this._autoSave(res);
      }
    } catch (err) {
      if (seq !== this._recipeSeq) return;
      this._recipeError = this._err(err);
      // "not_found" is no failure: the page simply holds no recipe.
      this._recipeMissing = (err as WsError | undefined)?.code === "not_found";
      this._recipeState = "error";
    }
  }

  private async _loadKoRecipe(id: number, force = false, servings?: number): Promise<void> {
    if (!force && id === this._koFor && this._koState !== "error") return;
    this._koFor = id;
    const seq = ++this._koSeq;
    this._cancelKoServings();
    this._ko = undefined;
    this._koServings = undefined;
    this._koState = "loading";
    try {
      const res = await this._ws<CollectionRecipeResponse>({
        type: "eatfresh/collection/recipe",
        kitchenowl_id: id,
        ...(servings != null ? { servings: clampServings(servings) } : {}),
      });
      if (seq !== this._koSeq) return;
      this._ko = res;
      this._koServings = this._shownServings(res);
      this._koState = "done";
    } catch (err) {
      if (seq !== this._koSeq) return;
      this._koError = this._err(err);
      this._koState = "error";
    }
  }

  /** Restore the missing ingredients in KitchenOwl (adds only), then reload the recipe quietly. */
  private async _restoreMissing(id: number): Promise<void> {
    if (this._koMissingBusy) return;
    this._koMissingBusy = true;
    const epoch = this._viewEpoch;
    try {
      const res = await this._ws<CollectionRestoreResponse>({ type: "eatfresh/collection/restore", kitchenowl_id: id });
      if (!this._koStillShown(id, epoch)) return;
      if (!(await this._reloadAfter(id, epoch))) return;
      const partial = Array.isArray(res?.missing) && res.missing.length > 0;
      this._showToast(this._t(partial ? "miss_restore_partial" : "miss_restored"), partial ? "error" : "ok");
    } catch (err) {
      this._showToast(this._t("miss_restore_failed", { message: this._err(err) }), "error");
    } finally {
      if (epoch === this._viewEpoch) this._koMissingBusy = false;
    }
  }

  /**
   * Reload the recipe after a change that already went through. A failed
   * reload gets its own message, so it is not mistaken for a failed change.
   */
  private async _reloadAfter(id: number, epoch: number): Promise<boolean> {
    try {
      return await this._refreshKo(id, epoch);
    } catch (err) {
      if (this._koStillShown(id, epoch)) {
        this._showToast(this._t("miss_reload_failed", { message: this._err(err) }), "error");
      }
      return false;
    }
  }

  /** EatFresh forgets the missing ingredients. KitchenOwl stays as it is. */
  private async _forgetMissing(id: number): Promise<void> {
    if (this._koMissingBusy) return;
    this._koMissingBusy = true;
    const epoch = this._viewEpoch;
    try {
      await this._ws<CollectionForgetResponse>({ type: "eatfresh/collection/forget", kitchenowl_id: id });
      if (!this._koStillShown(id, epoch)) return;
      if (!(await this._reloadAfter(id, epoch))) return;
      this._showToast(this._t("miss_forgotten"), "ok");
    } catch (err) {
      this._showToast(this._t("miss_forget_failed", { message: this._err(err) }), "error");
    } finally {
      if (epoch === this._viewEpoch) this._koMissingBusy = false;
    }
  }

  /**
   * Reload the open recipe of the collection without the loading skeleton. Returns false when the answer was
   * dropped: the view changed meanwhile, or a regular load started (that one wins). Never invalidates a load.
   */
  private async _refreshKo(id: number, epoch: number): Promise<boolean> {
    const seq = this._koSeq;
    // Keep the servings that are shown.
    const servings = this._ko?.kitchenowl_id === id && this._ko.portions?.scalable ? this._koServings : undefined;
    const res = await this._ws<CollectionRecipeResponse>({
      type: "eatfresh/collection/recipe",
      kitchenowl_id: id,
      ...(servings != null ? { servings } : {}),
    });
    if (seq !== this._koSeq || !this._koStillShown(id, epoch)) return false;
    this._ko = res;
    this._koServings = this._shownServings(res);
    this._koFor = id;
    this._koState = "done";
    const n = res.missing?.length;
    if (n != null) this._patchRecipe(id, { missing: n });
    return true;
  }

  // ---- servings (0.5.0): the core scales, the panel only shows its answer

  /** The number the recipe shows: `portions.servings` when the core can scale it, else none (no counter). */
  private _shownServings(res: CollectionRecipeResponse | undefined): number | undefined {
    const p: Portions | undefined = res?.portions;
    if (!p?.scalable) return undefined;
    return p.servings ?? p.start ?? undefined;
  }

  private _cancelKoServings(): void {
    window.clearTimeout(this._koServingsTimer);
    this._koServingsTimer = undefined;
    this._koServingsBusy = false;
  }

  /** − and + in a recipe of the collection: the number changes at once, the core is asked a moment later. */
  private _stepKoServings(delta: number): void {
    const data = this._ko;
    const now = this._koServings;
    if (!data?.portions?.scalable || now == null || this._koState !== "done") return;
    const next = clampServings(now + delta);
    if (next === now) return;
    this._koServings = next;
    this._koServingsBusy = true;
    // An answer still on its way is for an old number: it is dropped.
    this._koSeq++;
    window.clearTimeout(this._koServingsTimer);
    const id = data.kitchenowl_id;
    const epoch = this._viewEpoch;
    this._koServingsTimer = window.setTimeout(() => void this._fetchKoServings(id, next, epoch), KO_SERVINGS_MS);
  }

  private async _fetchKoServings(id: number, servings: number, epoch: number): Promise<void> {
    this._koServingsTimer = undefined;
    if (!this._koStillShown(id, epoch)) return;
    const seq = ++this._koSeq;
    try {
      const res = await this._ws<CollectionRecipeResponse>({
        type: "eatfresh/collection/recipe",
        kitchenowl_id: id,
        servings,
      });
      if (seq !== this._koSeq || !this._koStillShown(id, epoch)) return;
      this._ko = res;
      this._koServings = this._shownServings(res);
      this._koServingsBusy = false;
      const n = res.missing?.length;
      if (n != null) this._patchRecipe(id, { missing: n });
    } catch (err) {
      if (seq !== this._koSeq || !this._koStillShown(id, epoch)) return;
      // Back to the number whose amounts are shown.
      this._koServings = this._shownServings(this._ko);
      this._koServingsBusy = false;
      this._showToast(this._t("portions_failed", { message: this._err(err) }), "error");
    }
  }

  private _planKey(id: number, date: string): string {
    return `${id}|${date}`;
  }

  /** Servings shown for a plan entry: a number changed a moment ago, else the core's. */
  private _entryServings(e: PlannerEntry, date: string | null): number | null {
    if (!date) return null;
    return this._planServings.get(this._planKey(e.kitchenowl_id, date)) ?? e.servings ?? null;
  }

  private _setPlanPending(key: string, value: number | undefined): void {
    const next = new Map(this._planServings);
    if (value == null) next.delete(key);
    else next.set(key, value);
    this._planServings = next;
  }

  /** − and + at a plan entry: the number changes at once and is saved a moment later. */
  private _stepPlanServings(e: PlannerEntry, date: string, delta: number): void {
    const now = this._entryServings(e, date);
    if (now == null) return;
    const next = clampServings(now + delta);
    if (next === now) return;
    const key = this._planKey(e.kitchenowl_id, date);
    this._setPlanPending(key, next);
    window.clearTimeout(this._planTimers.get(key));
    this._planTimers.set(
      key,
      window.setTimeout(() => void this._savePlanServings(e.kitchenowl_id, date), PLAN_SERVINGS_MS),
    );
  }

  /** One call per burst of taps, never two at once for the same entry: the last number wins. */
  private async _savePlanServings(id: number, date: string): Promise<void> {
    const key = this._planKey(id, date);
    this._planTimers.delete(key);
    // A call is on its way: this number goes once it is answered.
    if (this._planInflight.has(key)) return;
    const want = this._planServings.get(key);
    if (want == null) return;
    this._planInflight.add(key);
    let ok = false;
    try {
      await this._ws({ type: "eatfresh/planner/set_servings", kitchenowl_id: id, date, servings: want });
      ok = true;
      this._plannerPatch((p) => ({
        ...p,
        days: p.days.map((d) =>
          d.date === date
            ? { ...d, entries: d.entries.map((e) => (e.kitchenowl_id === id ? { ...e, servings: want } : e)) }
            : d,
        ),
      }));
      if (this._planServings.get(key) === want) this._setPlanPending(key, undefined);
      const listed = this._planner?.days.some((d) => d.date === date) && !!this._planner.shopping_list_at;
      if (listed) this._showToast(this._t("plan_servings_listed"), "ok", { ms: UNDO_MS });
    } catch (err) {
      // Back to the number the core has.
      window.clearTimeout(this._planTimers.get(key));
      this._planTimers.delete(key);
      this._setPlanPending(key, undefined);
      // The two codes of set_servings (0.5.0) speak for themselves, without the general lead.
      const code = planErrorCode(err);
      this._showToast(code ? this._err(err) : this._t("plan_servings_failed", { message: this._err(err) }), "error");
      // The entry is gone in KitchenOwl: read the week again, so it is not shown any longer.
      if (code === "plan_entry_lost") {
        this._plannerStale = true;
        if (this._view.name === "planner") void this._loadPlanner();
      }
    } finally {
      this._planInflight.delete(key);
    }
    if (this._planServings.has(key)) {
      // Tapped again while the call was on its way, and the pause is over.
      if (!this._planTimers.has(key)) void this._savePlanServings(id, date);
      return;
    }
    if (ok) {
      // Read the week again, quietly (the view stays as it is).
      this._plannerStale = true;
      if (this._view.name === "planner") void this._loadPlanner();
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

  /**
   * Save a recipe that was opened through a link: the person asked for it
   * by pasting the link, so it lands in the collection without a second tap.
   */
  private async _autoSave(data: RecipeResponse): Promise<void> {
    const { key, title } = data.recipe;
    if (this._favBusy.has(key)) return;
    if (this._isFav(key, data.favorite) && data.kitchenowl_id != null) {
      this._showSavedToast(data.kitchenowl_id, title, [], false, undefined);
      return;
    }
    this._favs = new Map(this._favs).set(key, true);
    this._favBusy = new Set(this._favBusy).add(key);
    try {
      const res = await this._ws<{ kitchenowl_id: number; created: boolean; tags?: string[] }>({
        type: "eatfresh/favorite",
        key,
      });
      if (this._recipe?.recipe.key === key) {
        this._recipe = { ...this._recipe, favorite: true, kitchenowl_id: res.kitchenowl_id };
      }
      this._collectionStale = true;
      this._showSavedToast(res.kitchenowl_id, title, res.tags ?? [], res.created, key);
    } catch (err) {
      this._favs = new Map(this._favs).set(key, false);
      this._showToast(this._t("auto_failed", { message: this._err(err) }), "error", {
        actions: [{ label: this._t("again"), run: () => this._autoSave(data) }],
        ms: UNDO_MS,
      });
    } finally {
      const busy = new Set(this._favBusy);
      busy.delete(key);
      this._favBusy = busy;
    }
  }

  private _showSavedToast(id: number, title: string, tags: string[], created: boolean, key: string | undefined): void {
    const actions: ToastAction[] = [
      {
        label: tags.length ? this._t("change") : this._t("categories"),
        run: () => this._openCategories(id, title, tags.length || created ? tags : undefined),
      },
    ];
    // Nothing to take back when the recipe was in the collection before.
    if (created && key) actions.push({ label: this._t("undo"), run: () => this._undoAutoSave(key, id) });
    const text = !created
      ? this._t("auto_existing")
      : tags.length
        ? this._t("auto_saved_tags", { tags: tags.join(", ") })
        : this._t("auto_saved");
    this._showToast(text, "ok", { actions, ms: UNDO_MS + 3000 });
  }

  /** Take back an automatic save: the heart goes off and the new recipe is hidden. */
  private async _undoAutoSave(key: string, id: number): Promise<void> {
    if (this._favBusy.has(key)) return;
    this._favs = new Map(this._favs).set(key, false);
    this._favBusy = new Set(this._favBusy).add(key);
    let heartOff = false;
    try {
      await this._ws({ type: "eatfresh/unfavorite", key });
      heartOff = true;
      await this._ws({ type: "eatfresh/collection/hide", kitchenowl_id: id });
      if (this._recipe?.recipe.key === key) this._recipe = { ...this._recipe, favorite: false };
      this._patchRecipe(id, { hidden: true });
      this._showToast(this._t("auto_undone"), "ok");
    } catch (err) {
      if (!heartOff) this._favs = new Map(this._favs).set(key, true);
      else if (this._recipe?.recipe.key === key) this._recipe = { ...this._recipe, favorite: false };
      this._showToast(this._t("auto_undo_failed", { message: this._err(err) }), "error");
    } finally {
      this._collectionStale = true;
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

  /** `servings`: the number chosen in the open recipe (0.5.0); without it the core takes the start value. */
  private async _addToShopping(ids: number[], servings?: number): Promise<void> {
    if (!ids.length || this._shoppingBusy) return;
    this._shoppingBusy = true;
    try {
      const res = await this._ws<{ added: number }>({
        type: "eatfresh/shopping_list/add",
        kitchenowl_ids: ids,
        ...(servings != null ? { servings: clampServings(servings) } : {}),
      });
      const n = res.added ?? 0;
      this._showToast(
        n === 0 ? this._t("added_none") : n === 1 ? this._t("added_items_one") : this._t("added_items", { n }),
        "ok",
      );
      if (this._view.name === "collection") this._selected = new Set();
      this._shopStale = true;
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
      this._shopStale = true;
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

  private _openPlan(id: number, name: string, image: string | null, servings?: number): void {
    this._dialog = { kind: "plan", id, name, image, ...(servings != null ? { servings } : {}) };
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
      await this._ws({
        type: "eatfresh/planner/add",
        kitchenowl_id: entry.kitchenowl_id,
        date,
        ...(entry.servings != null ? { servings: clampServings(entry.servings) } : {}),
      });
      // KitchenOwl replaces an entry without a day when the recipe gets a day.
      this._dropEntry(null, entry.kitchenowl_id);
      this._plannerStale = true;
      // The core knows the servings of the new entry: read the week quietly when it is shown.
      if (this._view.name === "planner" && entry.servings == null) void this._loadPlanner();
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

  // ---- shopping list to Picnic

  /** Load the list (KitchenOwl and the store only, never Picnic). `quiet` keeps what is shown. */
  private async _loadShopping(quiet = false): Promise<void> {
    const seq = ++this._shopSeq;
    this._shopLoading = true;
    if (!quiet || !this._shop) this._shopState = "loading";
    try {
      const res = await this._ws<ShoppingResponse>({ type: "eatfresh/shopping" });
      if (seq !== this._shopSeq) return;
      // Quantities typed a moment ago win over the stored ones until they are saved.
      const items = res.items.map((i) => {
        const key = lower(i.name);
        const pending = this._pendingAmounts.get(key);
        let item = pending != null && i.product ? { ...i, amount: pending } : i;
        // Pieces of the smaller package set in the panel (0.5.0); a sent entry keeps what is in the cart.
        const small = this._smallAmounts.get(key);
        if (small != null && item.small && !item.sent_at) item = { ...item, small_amount: small };
        // 0 of the main product only with at least one smaller package.
        if (item.product && !item.sent_at && item.amount < 1 && this._smallCount(item) < 1) item = { ...item, amount: 1 };
        return item;
      });
      this._shop = { ...res, items };
      this._prunePending(seq);
      this._shopState = "done";
      this._shopStale = false;
      const open = new Set(items.filter((i) => !i.sent_at && !i.skip).map((i) => i.item_id));
      this._itemErrors = new Map([...this._itemErrors].filter(([id]) => open.has(id)));
    } catch (err) {
      if (seq !== this._shopSeq) return;
      this._shopError = this._err(err);
      if (quiet && this._shop) this._showToast(`${this._t("shop_failed")} ${this._shopError}`, "error");
      else this._shopState = "error";
    } finally {
      if (seq === this._shopSeq) this._shopLoading = false;
    }
  }

  private _isPicked(item: ShoppingItem): boolean {
    return (
      !!item.product &&
      !item.skip &&
      !item.sent_at &&
      !this._unpicked.has(item.item_id) &&
      (!item.cart_hint || this._hintPicked.has(item.item_id)) &&
      !this._pendingDone.has(item.item_id) &&
      item.amount + this._smallCount(item) >= 1
    );
  }

  /** Pieces of the smaller package (0.5.0); 0 without one or on an older integration. */
  private _smallCount(item: ShoppingItem): number {
    return item.small ? Math.max(0, item.small_amount ?? 0) : 0;
  }

  private get _pickedItems(): ShoppingItem[] {
    return (this._shop?.items ?? []).filter((i) => this._isPicked(i));
  }

  private _item(id: number): ShoppingItem | undefined {
    return this._shop?.items.find((i) => i.item_id === id);
  }

  /** The store keys products by ingredient name: entries with the same name change together. */
  private _patchByName(name: string, patch: Partial<ShoppingItem>): void {
    if (!this._shop) return;
    const key = lower(name);
    this._shop = {
      ...this._shop,
      items: this._shop.items.map((i) => {
        if (lower(i.name) !== key) return i;
        // A sent entry keeps the quantity that is in the cart (and that "undo" takes out).
        if (i.sent_at && ("amount" in patch || "small_amount" in patch)) {
          const { amount: _ignored, small_amount: _small, ...rest } = patch;
          return { ...i, ...rest };
        }
        return { ...i, ...patch };
      }),
    };
  }

  private _patchItem(id: number, patch: Partial<ShoppingItem>): void {
    if (!this._shop) return;
    this._shop = { ...this._shop, items: this._shop.items.map((i) => (i.item_id === id ? { ...i, ...patch } : i)) };
  }

  private _setPicked(id: number, on: boolean): void {
    const next = new Set(this._unpicked);
    if (on) next.delete(id);
    else next.add(id);
    this._unpicked = next;
    const hint = new Set(this._hintPicked);
    if (on) hint.add(id);
    else hint.delete(id);
    this._hintPicked = hint;
  }

  private _setItemBusy(id: number, on: boolean): void {
    const next = new Set(this._itemBusy);
    if (on) next.add(id);
    else next.delete(id);
    this._itemBusy = next;
  }

  private _clearItemError(id: number): void {
    if (!this._itemErrors.has(id)) return;
    const next = new Map(this._itemErrors);
    next.delete(id);
    this._itemErrors = next;
  }

  private _openProduct(item: ShoppingItem, small = false): void {
    this._productSeq++;
    this._dialog = {
      kind: "product",
      item_id: item.item_id,
      name: item.name,
      query: item.name.slice(0, 60),
      state: "idle",
      products: [],
      error: "",
      ...(small ? { small: { rest: item.rest ?? null, main: item.product?.unit_quantity ?? null } } : {}),
    };
  }

  /** Searches Picnic. Only ever called from a tap on "Search" or Enter. */
  private async _productSearch(): Promise<void> {
    const d = this._dialog;
    if (d?.kind !== "product" || !this._shop?.picnic.search) return;
    const query = d.query.trim().slice(0, 60);
    if (!query) return;
    const seq = ++this._productSeq;
    this._dialog = { ...d, state: "loading", error: "" };
    // For a smaller package the core marks the hits that cover the rest (0.5.0).
    const rest = d.small?.rest?.trim().slice(0, REST_MAX);
    const main = d.small?.main?.trim().slice(0, REST_MAX);
    try {
      const res = await this._ws<{ products: PicnicHit[] }>({
        type: "eatfresh/picnic/search",
        query,
        ...(d.small && rest ? { rest } : {}),
        ...(d.small && main ? { main_unit_quantity: main } : {}),
      });
      const now = this._dialog;
      if (seq !== this._productSeq || now?.kind !== "product") return;
      let products = res.products ?? [];
      // Hits that cover the rest come first, otherwise in the order of Picnic.
      if (now.small) products = [...products.filter((p) => p.fits_rest), ...products.filter((p) => !p.fits_rest)];
      this._dialog = { ...now, state: "done", products };
    } catch (err) {
      const now = this._dialog;
      if (seq !== this._productSeq || now?.kind !== "product") return;
      this._dialog = { ...now, state: "error", error: this._err(err) };
    }
  }

  /** Remember a product for an ingredient. Without `amount` the core suggests one. */
  private async _mapProduct(item: ShoppingItem, product: PicnicProduct, undoable = true, amount?: number): Promise<void> {
    const before = this._item(item.item_id) ?? item;
    const old = { product: before.product, amount: before.amount };
    if (this._dialog?.kind === "product") this._dialog = undefined;
    this._pendingAmounts.delete(lower(item.name));
    this._patchByName(item.name, { product, amount: amount ?? 1, skip: false });
    this._setPicked(item.item_id, true);
    this._clearItemError(item.item_id);
    try {
      await this._ws({ type: "eatfresh/picnic/map", name: item.name, product, ...(amount != null ? { amount } : {}) });
      // Fetch the suggested quantity (store only, no call to Picnic).
      if (amount == null) void this._loadShopping(true);
      if (undoable)
        this._showToast(this._t("mapped", { name: item.name, product: product.name }), "ok", {
          ms: UNDO_MS,
          action: {
            label: this._t("undo"),
            run: () => {
              const now = { ...item, product };
              if (old.product) void this._mapProduct(now, old.product, false, old.amount);
              else void this._unmap(now, false);
            },
          },
        });
    } catch (err) {
      this._patchByName(item.name, old);
      this._showToast(this._t("map_failed", { message: this._err(err) }), "error");
    }
  }

  private async _unmap(item: ShoppingItem, undoable = true): Promise<void> {
    const before = this._item(item.item_id) ?? item;
    const old = { product: before.product, amount: before.amount };
    if (!old.product) return;
    this._pendingAmounts.delete(lower(item.name));
    this._patchByName(item.name, { product: null, amount: 1 });
    this._clearItemError(item.item_id);
    try {
      await this._ws({ type: "eatfresh/picnic/unmap", name: item.name });
      if (undoable)
        this._showToast(this._t("forgot", { name: item.name }), "ok", {
          ms: UNDO_MS,
          action: { label: this._t("undo"), run: () => void this._mapProduct({ ...item, product: null }, old.product!, false, old.amount) },
        });
    } catch (err) {
      this._patchByName(item.name, old);
      this._showToast(this._t("forget_failed", { message: this._err(err) }), "error");
    }
  }

  private async _setSkip(item: ShoppingItem, skip: boolean, undoable = true): Promise<void> {
    this._patchByName(item.name, { skip });
    this._clearItemError(item.item_id);
    try {
      await this._ws({ type: "eatfresh/picnic/skip", name: item.name, skip });
      if (undoable)
        this._showToast(this._t(skip ? "skipped_done" : "unskipped_done", { name: item.name }), "ok", {
          ms: UNDO_MS,
          action: { label: this._t("undo"), run: () => void this._setSkip({ ...item, skip }, !skip, false) },
        });
    } catch (err) {
      this._patchByName(item.name, { skip: !skip });
      this._showToast(this._t("skip_failed", { message: this._err(err) }), "error");
    }
  }

  /** Quantity changes show at once and are saved a moment later (one call per burst of taps). */
  private _setAmount(item: ShoppingItem, amount: number): void {
    if (!item.product) return;
    // 0 only while at least one smaller package goes along (0.5.0).
    const min = this._smallCount(item) >= 1 ? 0 : 1;
    const value = Math.min(AMOUNT_MAX, Math.max(min, Math.round(amount)));
    const key = lower(item.name);
    this._patchByName(item.name, { amount: value });
    this._pendingAmounts.set(key, value);
    window.clearTimeout(this._amountTimers.get(key));
    this._amountTimers.set(
      key,
      window.setTimeout(() => void this._saveAmount(item.name), AMOUNT_SAVE_MS),
    );
  }

  private async _saveAmount(name: string): Promise<void> {
    const key = lower(name);
    this._amountTimers.delete(key);
    const amount = this._pendingAmounts.get(key);
    const product = this._shop?.items.find((i) => lower(i.name) === key)?.product;
    if (amount == null || !product) return;
    // `eatfresh/picnic/map` keeps 1 to 20; a 0 next to a smaller package stays in the panel until it is sent.
    if (amount < 1) return;
    try {
      await this._ws({ type: "eatfresh/picnic/map", name, product, amount });
    } catch (err) {
      this._showToast(this._t("amount_failed", { message: this._err(err) }), "error");
    } finally {
      if (this._pendingAmounts.get(key) === amount) this._pendingAmounts.delete(key);
    }
  }

  /** Pieces of the smaller package (0.5.0): shown at once and sent with the entry, not saved by themselves. */
  private _setSmallAmount(item: ShoppingItem, amount: number): void {
    if (!item.small || item.sent_at) return;
    const min = item.amount >= 1 ? 0 : 1;
    const value = Math.min(AMOUNT_MAX, Math.max(min, Math.round(amount)));
    this._smallAmounts.set(lower(item.name), value);
    this._patchByName(item.name, { small_amount: value });
  }

  /** Remember (or with null forget) a smaller package for the rest, then read the list again. */
  private async _mapSmall(item: ShoppingItem, product: PicnicProduct | null): Promise<void> {
    if (this._dialog?.kind === "product") this._dialog = undefined;
    const key = lower(item.name);
    const before = this._item(item.item_id) ?? item;
    const old: Partial<ShoppingItem> = { small: before.small ?? null, small_amount: before.small_amount ?? 0, amount: before.amount };
    const oldSmall = this._smallAmounts.get(key);
    this._smallAmounts.delete(key);
    const small = product
      ? { id: product.id, name: product.name, unit_quantity: product.unit_quantity, price: product.price }
      : null;
    // Without a smaller package the main product needs at least one piece again.
    if (!small && before.amount < 1) this._pendingAmounts.delete(key);
    this._patchByName(item.name, {
      small,
      small_amount: small ? before.small_amount ?? 0 : 0,
      ...(!small && before.amount < 1 ? { amount: 1 } : {}),
    });
    this._clearItemError(item.item_id);
    try {
      await this._ws({ type: "eatfresh/picnic/map_small", name: item.name, product: small });
      this._showToast(
        small ? this._t("small_mapped", { name: item.name, product: small.name }) : this._t("small_removed", { name: item.name }),
        "ok",
      );
      // The core splits the amount again (store only, no call to Picnic).
      void this._loadShopping(true);
    } catch (err) {
      this._patchByName(item.name, old);
      if (oldSmall != null) this._smallAmounts.set(key, oldSmall);
      this._showToast(this._t(small ? "small_failed" : "small_remove_failed", { message: this._err(err) }), "error");
    }
  }

  private _askSend(): void {
    const n = this._pickedItems.length;
    if (!n || this._sending) return;
    this._dialog = { kind: "send", n };
  }

  /** Puts the ticked products into the Picnic cart. Never orders. */
  private async _send(): Promise<void> {
    const items = this._pickedItems;
    this._dialog = undefined;
    if (!items.length || this._sending) return;
    this._sending = true;
    this._sendNotice = undefined;
    this._clearToast();
    const sent: PicnicSendResponse["sent"] = [];
    const failed: PicnicSendResponse["failed"] = [];
    let fatal: unknown;
    // The core stops a run at the first error of Picnic; then no further chunk goes.
    let stopped = false;
    for (let i = 0; i < items.length; i += SEND_MAX) {
      const chunk = items.slice(i, i + SEND_MAX);
      if (fatal) {
        failed.push(...chunk.map((c) => ({ item_id: c.item_id, message: this._err(fatal) })));
        continue;
      }
      if (stopped) {
        failed.push(...chunk.map((c) => ({ item_id: c.item_id, code: "not_tried", message: picnicText(this._lang, "not_tried") })));
        continue;
      }
      try {
        const res = await this._ws<PicnicSendResponse>({
          type: "eatfresh/picnic/send",
          items: chunk.map((c) => {
            // The smaller package itself comes from the store; the panel sends only its pieces (0.5.0).
            const small = this._smallCount(c);
            return { item_id: c.item_id, product_id: c.product!.id, amount: c.amount, ...(small ? { small_amount: small } : {}) };
          }),
        });
        sent.push(...(res.sent ?? []));
        failed.push(...(res.failed ?? []));
        if ((res.failed ?? []).some((f) => !f.code || !LIST_CODES.has(f.code))) stopped = true;
      } catch (err) {
        // Stop at once (for example a login error); the rest is not tried.
        fatal = err;
        failed.push(...chunk.map((c) => ({ item_id: c.item_id, message: this._err(err) })));
      }
    }
    const at = new Date().toISOString();
    const sentIds = new Set(sent.map((s) => s.item_id));
    const sentSmall = new Map(sent.map((s) => [s.item_id, s.small_amount]));
    // Picnic did not answer in time: maybe in the cart. The core marked them,
    // so they are never sent again by themselves; show them as "maybe in the cart".
    const maybe = failed.filter((f) => f.code === "maybe_sent");
    const maybeIds = new Set(maybe.map((f) => f.item_id));
    // The main product went in, the smaller package did not (0.5.0): the entry stays marked as sent.
    const smallFailed = failed.filter((f) => sentIds.has(f.item_id) && !maybeIds.has(f.item_id));
    const other = failed.filter((f) => !maybeIds.has(f.item_id) && !sentIds.has(f.item_id));
    for (const f of smallFailed) this._smallAmounts.delete(lower(this._item(f.item_id)?.name ?? ""));
    // Sent: a later `cart_hint` starts unticked again.
    if (sentIds.size || maybeIds.size) this._hintPicked = new Set([...this._hintPicked].filter((id) => !sentIds.has(id) && !maybeIds.has(id)));
    for (const id of [...sentIds, ...maybeIds]) {
      const key = lower(this._item(id)?.name ?? "");
      this._smallAmounts.delete(key);
      // A main amount of 0 next to a smaller package is never saved by itself: after sending, the core's number counts.
      const pend = this._pendingAmounts.get(key);
      if (pend != null && pend < 1) {
        this._pendingAmounts.delete(key);
        window.clearTimeout(this._amountTimers.get(key));
        this._amountTimers.delete(key);
      }
    }
    if (this._shop)
      this._shop = {
        ...this._shop,
        items: this._shop.items.map((i) =>
          sentIds.has(i.item_id)
            ? {
                ...i,
                sent_at: at,
                sent_uncertain: false,
                ...(sentSmall.get(i.item_id) != null ? { small_amount: sentSmall.get(i.item_id) } : {}),
              }
            : maybeIds.has(i.item_id)
              ? { ...i, sent_at: at, sent_uncertain: true }
              : i,
        ),
      };
    // Messages of the core come as codes; the panel says them in its own language.
    this._itemErrors = new Map(
      [...other, ...smallFailed].map((f) => [f.item_id, f.code ? picnicText(this._lang, f.code) : f.message]),
    );
    this._sending = false;
    const total = items.length;
    if (sent.length && !failed.length) {
      const ids = [...sentIds];
      this._showToast(
        sent.length === 1 ? this._t("send_done_one") : this._t("send_done", { n: sent.length }),
        "ok",
        { ms: UNDO_MS, action: { label: this._t("undo"), run: () => void this._undoAll(ids) } },
      );
    } else if (sent.length || maybe.length) {
      // Counted in entries; the first sentence already says that something is missing (0.5.0).
      const parts: string[] = [];
      const whole = sent.length - smallFailed.length;
      parts.push(this._t(other.length || smallFailed.length ? "send_partial_lead" : "send_partial_lead_maybe"));
      if (whole > 0)
        parts.push(whole === 1 ? this._t("send_partial_head_one", { total }) : this._t("send_partial_head", { done: whole, total }));
      if (maybe.length)
        parts.push(maybe.length === 1 ? this._t("send_maybe_one") : this._t("send_maybe", { n: maybe.length }));
      if (other.length)
        parts.push(
          other.length === 1 ? this._t("send_partial_rest_one") : this._t("send_partial_rest", { failed: other.length }),
        );
      if (smallFailed.length)
        parts.push(
          smallFailed.length === 1 ? this._t("send_small_failed_one") : this._t("send_small_failed", { n: smallFailed.length }),
        );
      if (failed.some((f) => f.code === "not_tried")) parts.push(this._t("send_stopped"));
      this._sendNotice = { kind: "partial", text: parts.join(" ") };
    } else {
      const first = other[0];
      const message = fatal
        ? this._err(fatal)
        : first
          ? first.code
            ? picnicText(this._lang, first.code)
            : first.message
          : this._t("err_unknown");
      this._sendNotice = { kind: "error", text: this._t("send_failed", { message }) };
    }
    // The core answered for fewer entries than sent (for example, one left the list): read it again.
    if (!fatal && sent.length + failed.length < total) void this._loadShopping(true);
  }

  /**
   * Takes an entry out of the Picnic cart again. With `remove` false only the
   * mark goes (no call to Picnic): for "maybe in the cart" that was not there.
   */
  private async _undo(item: ShoppingItem, quiet = false, remove = true): Promise<boolean> {
    const id = item.item_id;
    if (this._itemBusy.has(id)) return false;
    this._setItemBusy(id, true);
    try {
      await this._ws(remove ? { type: "eatfresh/picnic/undo", item_id: id } : { type: "eatfresh/picnic/undo", item_id: id, remove: false });
      this._patchItem(id, { sent_at: null, sent_uncertain: false });
      // Back on the list, but not ticked: it only goes again on purpose.
      this._setPicked(id, false);
      if (!quiet)
        this._showToast(this._t(remove ? "undo_done" : "not_in_cart_done", { name: item.name }), "ok");
      return true;
    } catch (err) {
      this._showToast(this._t("auto_undo_failed", { message: this._err(err) }), "error");
      // After an unclear answer the core shows the entry as "maybe in the cart": read it again.
      if (remove) void this._loadShopping(true);
      return false;
    } finally {
      this._setItemBusy(id, false);
    }
  }

  private async _undoAll(ids: number[]): Promise<void> {
    for (const id of ids) {
      const item = this._item(id);
      if (!item?.sent_at) continue;
      if (!(await this._undo(item, true))) return;
    }
    this._showToast(this._t("undo_all_done"), "ok");
  }

  // ---- ticking off and groups (0.5.0)

  /** The core sorts into groups and can tick off (0.5.0). An older core: the list looks like before. */
  private get _shopV5(): boolean {
    return Array.isArray(this._shop?.departments);
  }

  /** Group of an entry; an unknown or missing key goes under the last group, so nothing gets lost. */
  private _deptOf(item: { department?: string }): string {
    const deps = this._shop?.departments ?? [];
    const key = item.department;
    if (key && deps.some((d) => d.key === key)) return key;
    return deps.at(-1)?.key ?? "";
  }

  /** After a list load that started after the core's yes, the list itself shows the truth. */
  private _prunePending(seq: number): void {
    const keep = (m: Map<number, { entry: ShopDone; seq?: number }>) => {
      const next = new Map([...m].filter(([, p]) => p.seq == null || seq <= p.seq));
      return next.size === m.size ? m : next;
    };
    this._pendingDone = keep(this._pendingDone);
    this._pendingBack = keep(this._pendingBack);
  }

  private _shopOpStart(): void {
    this._shopOps++;
    window.clearTimeout(this._shopReloadTimer);
    this._shopReloadTimer = undefined;
  }

  /** When the last call is back, read the list once, quietly. */
  private _shopOpEnd(): void {
    this._shopOps = Math.max(0, this._shopOps - 1);
    if (this._shopOps) return;
    window.clearTimeout(this._shopReloadTimer);
    this._shopReloadTimer = window.setTimeout(() => {
      this._shopReloadTimer = undefined;
      if (!this._shopOps && this.isConnected) void this._loadShopping(true);
    }, SHOP_RELOAD_MS);
  }

  private _withoutKey<T>(m: Map<number, T>, id: number): Map<number, T> {
    const next = new Map(m);
    next.delete(id);
    return next;
  }

  /** Keyboard and screen reader: focus moves to the next round button when an entry leaves the list. */
  private _keepFocus(id: number): () => Promise<void> {
    const root = this.renderRoot as ShadowRoot;
    const buttons = [...root.querySelectorAll<HTMLElement>(".done-btn")];
    const idx = buttons.findIndex((b) => b.closest("[data-item]")?.getAttribute("data-item") === String(id));
    if (idx < 0 || root.activeElement !== buttons[idx]) return async () => {};
    return async () => {
      await this.updateComplete;
      const now = [...root.querySelectorAll<HTMLElement>(".done-btn:not([disabled])")];
      (now[Math.min(idx, now.length - 1)] ?? root.querySelector<HTMLElement>(".done-toggle"))?.focus();
    };
  }

  /** Ticks an entry off: it goes to "Done" at once, the core takes it off the list; on an error it comes back. */
  private async _check(item: ShoppingItem): Promise<void> {
    const id = item.item_id;
    if (this._pendingDone.has(id) || this._itemBusy.has(id)) return;
    const back = this._pendingBack.get(id);
    if (back && back.seq == null) return;
    const entry: ShopDone = {
      item_id: id,
      name: item.name,
      description: item.description,
      department: this._deptOf(item),
      at: new Date().toISOString(),
    };
    const focus = this._keepFocus(id);
    this._pendingDone = new Map(this._pendingDone).set(id, { entry });
    if (back) this._pendingBack = this._withoutKey(this._pendingBack, id);
    this._clearItemError(id);
    this._shopAnnounce = this._t("shop_checked", { name: item.name });
    void focus();
    this._setItemBusy(id, true);
    this._shopOpStart();
    try {
      await this._ws({ type: "eatfresh/shopping/check", item_id: id });
      const p = this._pendingDone.get(id);
      if (p) this._pendingDone = new Map(this._pendingDone).set(id, { ...p, seq: this._shopSeq });
    } catch (err) {
      this._pendingDone = this._withoutKey(this._pendingDone, id);
      // Ticked right after "back on the list": the entry stays where the core has it, on the list.
      if (back) this._pendingBack = new Map(this._pendingBack).set(id, back);
      this._shopAnnounce = "";
      this._showToast(this._t("shop_check_failed", { name: item.name, message: this._err(err) }), "error");
    } finally {
      this._setItemBusy(id, false);
      this._shopOpEnd();
    }
  }

  /** Puts a ticked-off entry back on the list (the core adds it with the remembered quantity). */
  private async _uncheck(entry: ShopDone): Promise<void> {
    const id = entry.item_id;
    if (this._itemBusy.has(id) || this._pendingBack.has(id)) return;
    const done = this._pendingDone.get(id);
    if (done && done.seq == null) return;
    this._pendingBack = new Map(this._pendingBack).set(id, { entry });
    if (done) this._pendingDone = this._withoutKey(this._pendingDone, id);
    this._shopAnnounce = this._t("shop_unchecked", { name: entry.name });
    this._setItemBusy(id, true);
    this._shopOpStart();
    try {
      await this._ws({ type: "eatfresh/shopping/uncheck", item_id: id });
      const p = this._pendingBack.get(id);
      if (p) this._pendingBack = new Map(this._pendingBack).set(id, { ...p, seq: this._shopSeq });
    } catch (err) {
      this._pendingBack = this._withoutKey(this._pendingBack, id);
      if (done) this._pendingDone = new Map(this._pendingDone).set(id, done);
      this._shopAnnounce = "";
      this._showToast(this._t("shop_uncheck_failed", { name: entry.name, message: this._err(err) }), "error");
    } finally {
      this._setItemBusy(id, false);
      this._shopOpEnd();
    }
  }

  /** Moves an entry into another group; the core remembers it per ingredient and writes it to KitchenOwl. */
  private async _setDepartment(item: ShoppingItem, key: string): Promise<void> {
    this._dialog = undefined;
    if (key === this._deptOf(item)) return;
    const old = item.department;
    this._patchByName(item.name, { department: key });
    this._shopOpStart();
    try {
      await this._ws({ type: "eatfresh/shopping/set_department", item_id: item.item_id, name: item.name, department: key });
      const dept = this._shop?.departments?.find((d) => d.key === key)?.name ?? key;
      this._showToast(this._t("dept_changed", { name: item.name, dept }), "ok");
    } catch (err) {
      this._patchByName(item.name, { department: old });
      this._showToast(this._t("dept_failed", { message: this._err(err) }), "error");
    } finally {
      this._shopOpEnd();
    }
  }

  /** Ticked-off entries: the panel's own first, then the core's, newest first, each once. */
  private _doneEntries(): ShopDone[] {
    const own = [...this._pendingDone.values()].map((p) => p.entry);
    const ids = new Set(own.map((e) => e.item_id));
    const all = [...own, ...(this._shop?.done ?? []).filter((e) => !ids.has(e.item_id))];
    const seen = new Set<number>();
    return all
      .filter((e) => !this._pendingBack.has(e.item_id) && !seen.has(e.item_id) && seen.add(e.item_id))
      .sort((a, b) => (Date.parse(b.at) || 0) - (Date.parse(a.at) || 0));
  }

  // ---- toast

  private _showToast(
    text: string,
    kind: Toast["kind"],
    opts: { action?: ToastAction; actions?: ToastAction[]; ms?: number; onExpire?: () => void } = {},
  ): void {
    this._clearToast();
    const actions = opts.actions ?? (opts.action ? [opts.action] : []);
    this._toast = { text, kind, id: Date.now(), actions, onExpire: opts.onExpire };
    this._toastTimer = window.setTimeout(() => this._clearToast(), opts.ms ?? TOAST_MS);
  }

  private _clearToast(): void {
    window.clearTimeout(this._toastTimer);
    const toast = this._toast;
    this._toast = undefined;
    toast?.onExpire?.();
  }

  private _runToastAction(index: number): void {
    const toast = this._toast;
    const action = toast?.actions[index];
    if (!action) return;
    window.clearTimeout(this._toastTimer);
    this._toast = undefined;
    action.run();
  }

  // ----------------------------------------------------------------- render

  protected render(): TemplateResult {
    const v = this._view.name;
    const tabs: [Tab, string, StringKey][] = [
      ["search", mdiMagnify, "nav_search"],
      ["collection", mdiBookOpenPageVariantOutline, "nav_collection"],
      ["planner", mdiCalendarWeek, "nav_planner"],
      ["shopping", mdiCartOutline, "nav_shopping"],
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
      <div class="shell ${this._wide ? "wide" : "narrow"} ${this._wide && !this._roomy ? "mid" : ""}">
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
            class="link-btn ${this._roomy ? "btn" : "icon-btn"}"
            aria-label=${this._t("link_title")}
            title=${this._t("link_title")}
            aria-haspopup="dialog"
            @click=${() => {
              this._linkInvalid = false;
              this._dialog = { kind: "link" };
            }}
          >
            ${icon(mdiLinkVariant)}${this._roomy ? html`<span>${this._t("link_open")}</span>` : nothing}
          </button>
        </header>
        <div class="body">
          <main>
            <div class="content ${this._toast ? "with-toast" : ""}">
              ${v === "search"
                ? this._renderSearch()
                : v === "recipe"
                  ? this._renderRecipe()
                  : v === "korecipe"
                    ? this._renderKoRecipe()
                    : v === "planner"
                      ? this._renderPlanner()
                      : v === "shopping"
                        ? this._renderShopping()
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
          @close=${(e: Event) => this._onDialogClose(e)}
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
        ? html`<div class="toast ${toast.kind} ${toast.actions.length > 1 ? "multi" : ""}">
            <span class="lead">${icon(toast.kind === "ok" ? mdiCheckCircleOutline : mdiAlertCircleOutline)}</span>
            <span class="msg">${toast.text}</span>
            ${toast.actions.length
              ? html`<span class="acts"
                  >${toast.actions.map(
                    (a, i) => html`<button class="toast-action" @click=${() => this._runToastAction(i)}>${a.label}</button>`,
                  )}</span
                >`
              : nothing}
            <button class="icon-btn close" aria-label=${this._t("close")} @click=${() => this._clearToast()}>
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
      aria-busy=${busy ? "true" : "false"}
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

  private _servingsText(n: number): string {
    return n === 1 ? this._t("servings_one") : this._t("servings", { n });
  }

  /**
   * A − n + counter. The limits lock the buttons with aria-disabled, so the
   * keyboard focus stays on them; the number sits in a polite live region.
   */
  private _counter(
    value: number,
    min: number,
    max: number,
    labels: { group: string; less: string; more: string; text: string; sr?: string },
    step: (delta: number) => void,
    compact = false,
  ): TemplateResult {
    const btn = (delta: number, label: string, path: string, locked: boolean) =>
      html`<button
        type="button"
        class="icon-btn"
        aria-label=${label}
        title=${label}
        aria-disabled=${locked ? "true" : "false"}
        @click=${() => {
          if (!locked) step(delta);
        }}
      >
        ${icon(path)}
      </button>`;
    return html`<div class="stepper counter ${compact ? "compact" : ""}" role="group" aria-label=${labels.group}>
      ${btn(-1, labels.less, mdiMinus, value <= min)}
      <output aria-live="polite" aria-atomic="true"
        >${labels.text}${labels.sr ? html`<span class="sr"> ${labels.sr}</span>` : nothing}</output
      >
      ${btn(1, labels.more, mdiPlus, value >= max)}
    </div>`;
  }

  /** Counter of the servings in a recipe of the collection, with the recipe's own number below when it differs. */
  private _koPortions(data: CollectionRecipeResponse): { counter: TemplateResult; busy: boolean } | undefined {
    const p = data.portions;
    const n = this._koServings;
    if (!p?.scalable || n == null) return undefined;
    return {
      busy: this._koServingsBusy,
      counter: html`<div class="portions">
        ${this._counter(
          n,
          SERVINGS_MIN,
          SERVINGS_MAX,
          {
            group: this._t("portions_label"),
            less: this._t("portions_less"),
            more: this._t("portions_more"),
            text: this._servingsText(n),
          },
          (delta) => this._stepKoServings(delta),
        )}
        ${p.base != null && p.base !== n
          ? html`<span class="portions-base">${this._t(p.base === 1 ? "portions_in_recipe_one" : "portions_in_recipe", { n: p.base })}</span>`
          : nothing}
      </div>`,
    };
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
    missing: readonly string[] = [],
    missingNotice: TemplateResult | typeof nothing = nothing,
    /** Counter for the servings (0.5.0): replaces the plain text; `busy` while the new amounts are on their way. */
    portions?: { counter: TemplateResult; busy: boolean },
  ): TemplateResult {
    const missingSet = new Set(missing.map(lower));
    const facts: [string, string][] = [];
    const total = formatMinutes(this._lang, r.total_time);
    const prep = formatMinutes(this._lang, r.prep_time);
    const cook = formatMinutes(this._lang, r.cook_time);
    if (total) facts.push([this._t("total_time"), total]);
    if (prep) facts.push([this._t("prep_time"), prep]);
    if (cook) facts.push([this._t("cook_time"), cook]);
    const servings =
      portions || r.servings == null ? "" : this._servingsText(r.servings);
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
          ${portions?.counter ?? nothing}
        </div>
      </div>
      <div class="recipe-body">
        ${r.ingredients.length
          ? html`<section class="panel-box">
              <h2>${this._t("ingredients")}</h2>
              ${missingNotice}
              <ul class="ingredients ${portions?.busy ? "pending" : ""}" aria-busy=${portions?.busy ? "true" : "false"}>
                ${r.ingredients.map((ing) => {
                  const qty = ingredientQty(this._lang, ing);
                  const gone = missingSet.size > 0 && missingSet.has(lower(ing.name || ing.raw));
                  const from = ing.portion?.rounded_from;
                  return html`<li class=${gone ? "missing" : ""}>
                    <span class="qty"
                      >${qty}${from
                        ? html`<span class="calc">${this._t("portions_calc", { n: localNumber(this._lang, from) })}</span>`
                        : nothing}</span
                    >
                    <span
                      >${ing.name || ing.raw}${ing.note ? html` <span class="note">(${ing.note})</span>` : nothing}${gone
                        ? html`<span class="miss-mark" title=${this._t("miss_item")}>${icon(mdiAlertCircleOutline)}</span
                            ><span class="sr"> – ${this._t("miss_item")}</span>`
                        : nothing}</span
                    >
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
    // The chosen servings go along (0.5.0); unknown base: nothing extra is sent.
    const servings = data.portions?.scalable ? this._koServings : undefined;
    const actions = html`
      <button class="btn primary" ?disabled=${this._shoppingBusy} @click=${() => this._addToShopping([id], servings)}>
        ${icon(mdiCartPlus)}<span>${this._t("to_shopping_list")}</span>
      </button>
      <button class="btn" @click=${() => this._openPlan(id, r.title, r.image, servings)}>
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
    const missing = Array.isArray(data.missing) ? data.missing : [];
    const lock = this._koMissingBusy;
    const notice = missing.length
      ? html`<div class="banner info miss-notice" role="status">
          ${icon(mdiInformationOutline)}
          <div class="miss-body">
            <span>${missing.length === 1 ? this._t("miss_one") : this._t("miss_many", { n: missing.length })}</span>
            <div class="miss-actions">
              <button class="btn small primary" ?disabled=${lock} @click=${() => void this._restoreMissing(id)}>
                ${icon(mdiRefresh)}<span>${this._t("miss_restore")}</span>
              </button>
              <button
                class="btn small"
                ?disabled=${lock}
                @click=${() => (this._dialog = { kind: "forget_missing", id })}
              >
                ${icon(mdiClose)}<span>${this._t("miss_forget")}</span>
              </button>
            </div>
          </div>
        </div>`
      : nothing;
    return this._recipeLayout(
      r,
      isHttpUrl(r.url) ? hostOf(r.url) : "KitchenOwl",
      actions,
      extra,
      missing,
      notice,
      this._koPortions(data),
    );
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
    // Entries without a day and without a number have no counter (0.5.0).
    const servings = this._entryServings(e, date);
    const link = this._viewLink(
      servings != null ? { name: "korecipe", id: e.kitchenowl_id, servings } : { name: "korecipe", id: e.kitchenowl_id },
    );
    const counter =
      servings != null && date
        ? html`<div class="entry-servings">
            ${this._counter(
              servings,
              SERVINGS_MIN,
              SERVINGS_MAX,
              {
                group: this._t("plan_servings_label", { name: e.name }),
                less: this._t("portions_less"),
                more: this._t("portions_more"),
                text: String(servings),
                sr: this._t(servings === 1 ? "portions_word_one" : "portions_word"),
              },
              (delta) => this._stepPlanServings(e, date, delta),
              true,
            )}
            <span class="entry-servings-label" aria-hidden="true">${this._t(servings === 1 ? "portions_word_one" : "portions_word")}</span>
          </div>`
        : nothing;
    return html`<li class="entry ${counter === nothing ? "" : "has-servings"}">
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
      ${counter}
    </li>`;
  }

  // ---- shopping view (Picnic)

  private _formatSent(iso: string): string {
    const when = new Date(iso);
    if (Number.isNaN(when.getTime())) return iso;
    const options: Intl.DateTimeFormatOptions = { weekday: "short", hour: "2-digit", minute: "2-digit" };
    const zone = this._hass?.config?.time_zone;
    try {
      return when.toLocaleString(this._lang, zone ? { ...options, timeZone: zone } : options);
    } catch {
      return when.toLocaleString(this._lang, options);
    }
  }

  private _productMeta(p: PicnicProduct): string {
    const price = p.price == null ? this._t("shop_price_unknown") : formatPrice(this._lang, p.price);
    return [p.unit_quantity, price].filter(Boolean).join(" · ");
  }

  private _shopSkeleton(): TemplateResult {
    return html`<ul class="shop-list" aria-busy="true" aria-label=${this._t("loading")}>
      ${Array.from(
        { length: 5 },
        () => html`<li class="shop-item"><span></span><div class="shop-body"><div class="skel line"></div><div class="skel line short"></div></div></li>`,
      )}
    </ul>`;
  }

  private _renderShopping(): TemplateResult {
    const shop = this._shop;
    if (!shop && this._shopState === "error")
      return this._note(`${this._t("shop_failed")} ${this._shopError}`, mdiAlertCircleOutline, () => this._loadShopping());
    if (!shop) return html`<p class="intro">${this._t("shop_intro")}</p>${this._shopSkeleton()}`;
    const v5 = this._shopV5;
    // An older core without Picnic: the explanation like before. With groups (0.5.0) a plain list to tick off.
    if (!shop.picnic.available && !v5) {
      // Set up but not running is a different message than "not set up".
      const off = shop.picnic.reason_code === "not_loaded";
      return html`<div class="shop"><section class="explain" role="note">
        ${icon(mdiStorefrontOutline)}
        <h2>${this._t(off ? "shop_picnic_off_title" : "shop_no_picnic_title")}</h2>
        <p>${this._t(off ? "shop_picnic_off" : "shop_no_picnic")}</p>
        ${shop.picnic.reason_code && shop.picnic.reason_code !== "not_set_up" && !off
          ? html`<p class="reason">${this._t("shop_reason", { reason: picnicText(this._lang, shop.picnic.reason_code) })}</p>`
          : nothing}
      </section></div>`;
    }
    const picnic = shop.picnic.available;
    const items = shop.items;
    const done = v5 ? this._doneEntries() : [];
    const reload = html`<button
      class="icon-btn"
      aria-label=${this._t("shop_refresh")}
      title=${this._t("shop_refresh")}
      ?disabled=${this._shopLoading || this._sending}
      @click=${() => this._loadShopping(true)}
    >
      ${icon(mdiRefresh)}
    </button>`;
    if (!items.length && !done.length && !this._pendingBack.size)
      return html`<div class="shop">
        <div class="note">
          ${icon(mdiCartOutline)}
          <div>${this._t("shop_empty")}</div>
          <button class="btn" ?disabled=${this._shopLoading} @click=${() => this._loadShopping(true)}>
            ${icon(mdiRefresh)}<span>${this._t("shop_refresh")}</span>
          </button>
        </div>
      </div>`;
    const ticked = this._pendingDone;
    // Without Picnic "never at Picnic" means nothing: every entry is on the list to tick off.
    const open = items.filter((i) => !i.sent_at && (!i.skip || !picnic) && !ticked.has(i.item_id));
    // Entries put back a moment ago, until the list is read again.
    const placeholders = new Set<number>();
    if (v5)
      for (const { entry } of this._pendingBack.values())
        if (!items.some((i) => i.item_id === entry.item_id)) {
          placeholders.add(entry.item_id);
          open.push({ item_id: entry.item_id, name: entry.name, description: entry.description, product: null, amount: 1, skip: false, sent_at: null, department: entry.department });
        }
    const sent = items.filter((i) => !!i.sent_at);
    // 0.5.0: the cart goes under "Done"; "maybe in the cart" needs a look and stays in view.
    const maybe = v5 ? sent.filter((i) => i.sent_uncertain) : [];
    const cart = v5 ? sent.filter((i) => !i.sent_uncertain) : [];
    const skipped = picnic ? items.filter((i) => !i.sent_at && i.skip && !ticked.has(i.item_id)) : [];
    const missing = open.filter((i) => !i.product && !placeholders.has(i.item_id)).length;
    const n = this._pickedItems.length;
    const firstTime = open.length > 0 && missing === open.length && sent.length === 0;
    const notice = this._sendNotice;
    const allDone = html`<div class="note">${icon(mdiCartCheck)}<div>${this._t(picnic ? "shop_all_done" : "shop_all_checked")}</div></div>`;
    return html`<div class="shop ${v5 ? "v5" : ""}">
      ${picnic
        ? html`<div class="action-bar shop-bar">
            <button
              class="btn primary grow send"
              ?disabled=${n === 0 || this._sending}
              aria-label=${`${this._t("shop_send")} (${n})`}
              @click=${() => this._askSend()}
            >
              ${icon(mdiCartPlus)}<span>${this._sending ? this._t("sending") : this._t("shop_send")}</span>
              ${this._sending ? nothing : html`<span class="count-badge" aria-hidden="true">${n}</span>`}
            </button>
            ${reload}
          </div>`
        : html`<div class="action-bar shop-bar plain"><p class="plain-hint">${this._t("shop_plain_hint")}</p>${reload}</div>`}
      ${picnic
        ? html`<p class="shop-status" role="status">
            ${open.length
              ? missing
                ? missing === 1
                  ? this._t(v5 ? "shop_open_one_v5" : "shop_open_one")
                  : this._t(v5 ? "shop_open_v5" : "shop_open", { n: missing })
                : this._t("shop_all_mapped")
              : nothing}
            ${open.length && !n ? html`<span class="sub">${this._t("shop_none_picked")}</span>` : nothing}
          </p>`
        : nothing}
      ${v5 ? html`<p class="sr" role="status">${this._shopAnnounce}</p>` : nothing}
      ${picnic && firstTime ? html`<p class="intro">${this._t("shop_intro")}</p>` : nothing}
      ${!picnic || shop.picnic.search
        ? nothing
        : html`<div class="banner info">
            ${icon(mdiInformationOutline)}<span
              >${this._t("shop_no_search")}${shop.picnic.reason_code
                ? html` ${this._t("shop_reason", { reason: picnicText(this._lang, shop.picnic.reason_code) })}`
                : nothing}</span
            >
          </div>`}
      ${notice
        ? html`<div class="banner ${notice.kind}" role="alert">
            ${icon(mdiAlertCircleOutline)}<span>${notice.text}</span>
            <button class="icon-btn" aria-label=${this._t("close")} @click=${() => (this._sendNotice = undefined)}>
              ${icon(mdiClose)}
            </button>
          </div>`
        : nothing}
      ${v5
        ? open.length
          ? this._renderGroups(open, placeholders)
          : allDone
        : open.length
          ? html`<ul class="shop-list">${open.map((i) => this._renderShopItem(i))}</ul>`
          : allDone}
      ${maybe.length ? html`<ul class="shop-list maybe-list">${maybe.map((i) => this._renderShopItem(i))}</ul>` : nothing}
      ${!v5 && sent.length
        ? html`<h2 class="shop-sub">${icon(mdiCartCheck)}${this._t("shop_in_cart_title")}</h2>
            <ul class="shop-list">${sent.map((i) => this._renderShopItem(i))}</ul>`
        : nothing}
      ${skipped.length
        ? html`<div class="chips">
            <button
              type="button"
              class="chip toggle"
              aria-pressed=${this._showSkipped ? "true" : "false"}
              @click=${() => void this._toggleSkipped()}
            >
              ${icon(this._showSkipped ? mdiEyeOutline : mdiEyeOffOutline)}${this._t("shop_show_skipped")} (${skipped.length})
            </button>
          </div>`
        : nothing}
      ${skipped.length && this._showSkipped
        ? html`<h2 class="shop-sub skipped-head">${icon(mdiCancel)}${this._t("shop_never")}</h2>
            <p class="empty-day">${this._t("shop_skipped_hint")}</p>
            <ul class="shop-list">${skipped.map((i) => this._renderShopItem(i))}</ul>`
        : nothing}
      ${v5 ? this._renderDone(done, cart) : nothing}
    </div>`;
  }

  /** Open entries in groups, in the order of `departments`; groups without entries are left out. */
  private _renderGroups(open: ShoppingItem[], placeholders: Set<number>): TemplateResult {
    const row = (i: ShoppingItem) => this._renderShopItem(i, placeholders.has(i.item_id));
    const deps = this._shop?.departments ?? [];
    if (!deps.length) return html`<ul class="shop-list">${repeat(open, (i) => i.item_id, row)}</ul>`;
    const by = new Map<string, ShoppingItem[]>();
    for (const i of open) {
      const key = this._deptOf(i);
      by.set(key, [...(by.get(key) ?? []), i]);
    }
    return html`${repeat(
      deps.filter((d) => by.get(d.key)?.length),
      (d) => d.key,
      (d) => {
        const list = by.get(d.key)!;
        const count = list.length === 1 ? this._t("dept_count_one") : this._t("dept_count", { n: list.length });
        return html`<section class="dept" data-dept=${d.key}>
          <h2 class="dept-head">
            <span class="dept-name">${d.name}</span><span class="dept-count" aria-hidden="true">${list.length}</span
            ><span class="sr">, ${count}</span>
          </h2>
          <ul class="shop-list" aria-label=${d.name}>${repeat(list, (i) => i.item_id, row)}</ul>
        </section>`;
      },
    )}`;
  }

  /** "Done": ticked-off entries and entries in the Picnic cart, closed until opened. */
  private _renderDone(done: ShopDone[], cart: ShoppingItem[]): TemplateResult | typeof nothing {
    const rows = [
      ...done.map((e) => ({ key: `d${e.item_id}`, at: e.at, tpl: () => this._renderDoneRow(e) })),
      ...cart.map((i) => ({ key: `c${i.item_id}`, at: i.sent_at ?? "", tpl: () => this._renderShopItem(i) })),
    ].sort((a, b) => (Date.parse(b.at) || 0) - (Date.parse(a.at) || 0));
    if (!rows.length) return nothing;
    const days = this._shop?.done_days ?? 3;
    const open = this._doneOpen;
    return html`<section class="done-sec">
      <button class="done-toggle" aria-expanded=${open ? "true" : "false"} aria-controls="shop-done" @click=${() => (this._doneOpen = !open)}>
        ${icon(mdiChevronDown, "i chev")}<span class="done-title">${this._t("shop_done_title", { n: rows.length })}</span>
        <span class="done-hint">${days === 1 ? this._t("shop_done_hint_one") : this._t("shop_done_hint", { n: days })}</span>
      </button>
      <ul id="shop-done" class="shop-list done-list" ?hidden=${!open}>${repeat(rows, (r) => r.key, (r) => r.tpl())}</ul>
    </section>`;
  }

  private _renderDoneRow(e: ShopDone): TemplateResult {
    const id = e.item_id;
    // Still on its way to the core: "back" waits for the answer.
    const waiting = this._itemBusy.has(id) || (this._pendingDone.has(id) && this._pendingDone.get(id)!.seq == null);
    const when = relativeDay(this._lang, e.at, this._hass?.config?.time_zone);
    return html`<li class="shop-item done-item" data-done=${id}>
      <span class="lead-ico">${icon(mdiCheck)}</span>
      <div class="shop-body">
        <div class="shop-name v5">
          <span class="nm">${e.name}</span>${e.description
            ? html`<span class="qty"><span class="desc">${localQty(this._lang, e.description)}</span></span>`
            : nothing}
        </div>
        ${when ? html`<span class="when">${this._t("shop_done_when", { when })}</span>` : nothing}
      </div>
      <button class="btn small back" ?disabled=${waiting} aria-label=${this._t("shop_uncheck_label", { name: e.name })} @click=${() => void this._uncheck(e)}>
        ${icon(mdiUndoVariant, "i s")}<span>${this._wide ? this._t("shop_uncheck") : this._t("shop_uncheck_short")}</span>
      </button>
    </li>`;
  }

  /** The round button that ticks an entry off (0.5.0); not the same as "take" for Picnic. */
  private _doneBtn(item: ShoppingItem, locked = false): TemplateResult {
    const label = this._t("shop_check", { name: item.name });
    return html`<button
      class="done-btn"
      aria-label=${label}
      title=${label}
      ?disabled=${locked || this._itemBusy.has(item.item_id)}
      @click=${() => void this._check(item)}
    >
      <span class="ring" aria-hidden="true">${icon(mdiCheck)}</span>
    </button>`;
  }

  private async _toggleSkipped(): Promise<void> {
    this._showSkipped = !this._showSkipped;
    if (!this._showSkipped) return;
    await this.updateComplete;
    // The excluded entries sit at the end of the list: bring them into view.
    this.renderRoot.querySelector(".skipped-head")?.scrollIntoView({ block: "start", behavior: "smooth" });
  }

  private _renderShopItem(item: ShoppingItem, placeholder = false): TemplateResult {
    const id = item.item_id;
    const p = item.product;
    const busy = this._itemBusy.has(id);
    const v5 = this._shopV5;
    // 0.5.0: name left, quantity right in one line.
    const head = v5
      ? html`<div class="shop-name v5">
          <span class="nm">${item.name}</span>${item.description || item.exact
            ? html`<span class="qty">${item.description
                ? html`<span class="desc">${localQty(this._lang, item.description)}</span>`
                : nothing}${item.exact
                ? html`<span class="calc">${this._t("portions_calc", { n: localNumber(this._lang, item.exact) })}</span>`
                : nothing}</span>`
            : nothing}
        </div>`
      : html`<div class="shop-name">
      <span class="nm">${item.name}</span>${item.description
        ? html`<span class="desc">${localQty(this._lang, item.description)}</span>`
        : nothing}${item.exact
        ? html`<span class="calc">${this._t("portions_calc", { n: localNumber(this._lang, item.exact) })}</span>`
        : nothing}
    </div>`;
    const small = item.small ?? null;
    const smallN = this._smallCount(item);
    // Sent: both products with the pieces that went into the cart (0.5.0).
    const sentProducts = () => html`${p && (item.amount >= 1 || !small) ? product(false) : nothing}${small && smallN >= 1
      ? html`<div class="product static small-product">
          <span class="pname"><span class="small-tag">${this._t("shop_small_label")}:</span> ${small.name}</span
          ><span class="pmeta">${this._productMeta(small)}</span>
        </div>`
      : nothing}`;
    const sentCount = small && smallN >= 1 ? `${item.amount}× + ${smallN}×` : `${item.amount}×`;
    const product = (tappable: boolean) =>
      p
        ? tappable
          ? html`<button class="product" aria-label=${`${this._t("shop_other_product")}: ${p.name}`} @click=${() => this._openProduct(item)}>
              <span class="pname">${p.name}</span><span class="pmeta">${this._productMeta(p)}</span>
            </button>`
          : html`<div class="product static"><span class="pname">${p.name}</span><span class="pmeta">${this._productMeta(p)}</span></div>`
        : nothing;
    if (item.sent_at && item.sent_uncertain)
      return html`<li class="shop-item sent maybe" data-item=${id}>
        <span class="lead-ico">${icon(mdiAlertCircleOutline)}</span>
        <div class="shop-body">
          ${head}${sentProducts()}
          <p class="maybe-text" role="note">${this._t("shop_maybe")} · ${sentCount}</p>
          <div class="maybe-actions">
            <button class="btn small not-in-cart" ?disabled=${busy} @click=${() => this._undo(item, false, false)}>
              ${icon(mdiCartOutline, "i s")}<span>${this._t("shop_not_in_cart")}</span>
            </button>
          </div>
        </div>
      </li>`;
    if (item.sent_at)
      return html`<li class="shop-item sent" data-item=${id}>
        <span class="lead-ico">${icon(mdiCartCheck)}</span>
        <div class="shop-body">
          ${head}${sentProducts()}
          <div class="sent-line">
            <span
              >${v5
                ? this._t("shop_in_cart_when", { when: relativeDay(this._lang, item.sent_at, this._hass?.config?.time_zone) })
                : this._t("shop_in_cart", { when: this._formatSent(item.sent_at) })}
              · ${sentCount}</span
            >
          </div>
          ${this._itemErrors.get(id)
            ? html`<p class="error-text item-error">${this._t("send_item_failed", { message: this._itemErrors.get(id)! })}</p>`
            : nothing}
        </div>
        <button class="btn small undo" ?disabled=${busy} @click=${() => this._undo(item)}>
          ${icon(mdiUndoVariant, "i s")}<span>${this._t("undo")}</span>
        </button>
      </li>`;
    if (item.skip)
      return html`<li class="shop-item skipped" data-item=${id}>
        ${v5 ? this._doneBtn(item) : html`<span class="lead-ico">${icon(mdiCancel)}</span>`}
        <div class="shop-body">${head}</div>
        <button class="btn small take-back" @click=${() => this._setSkip(item, false)}>${this._t("shop_take_back")}</button>
      </li>`;
    const picked = this._isPicked(item);
    const error = this._itemErrors.get(id);
    const mainStepper = html`<div class="stepper" role="group" aria-label=${`${this._t("shop_qty")}: ${item.name}`}>
      <button class="icon-btn" aria-label=${this._t("shop_less")} ?disabled=${item.amount <= (smallN >= 1 ? 0 : 1)} @click=${() => this._setAmount(item, item.amount - 1)}>
        ${icon(mdiMinus)}
      </button>
      <output aria-live="polite">${item.amount}</output>
      <button class="icon-btn" aria-label=${this._t("shop_more")} ?disabled=${item.amount >= AMOUNT_MAX} @click=${() => this._setAmount(item, item.amount + 1)}>
        ${icon(mdiPlus)}
      </button>
    </div>`;
    const menu = html`<button
      class="icon-btn item-menu"
      aria-label=${this._t("shop_menu", { name: item.name })}
      title=${this._t("shop_menu", { name: item.name })}
      aria-haspopup="dialog"
      @click=${() => (this._dialog = { kind: "item_menu", item_id: id })}
    >
      ${icon(mdiDotsVertical)}
    </button>`;
    if (v5) {
      const picnic = !!this._shop?.picnic.available && !placeholder;
      // "take" (for Picnic) sits with the product, apart from the round button that ticks off.
      const take = html`<button
        class="take-btn"
        role="checkbox"
        aria-checked=${picked ? "true" : "false"}
        aria-label=${this._t("shop_take", { name: item.name })}
        title=${this._t("shop_take", { name: item.name })}
        @click=${() => this._setPicked(id, !picked)}
      >
        <span class="box" aria-hidden="true">${picked ? icon(mdiCheck) : nothing}</span><span class="take-text">${this._t("shop_take_short")}</span>
      </button>`;
      // Without a product only a quiet magnifier at the end of the row (0.5.0); the second row only with a product.
      const pick =
        picnic && !p
          ? html`<button
              class="icon-btn pick-product"
              aria-label=${this._t("shop_pick_for", { name: item.name })}
              title=${this._t("shop_pick_for", { name: item.name })}
              aria-haspopup="dialog"
              @click=${() => this._openProduct(item)}
            >
              ${icon(mdiMagnify)}<span class="pick-text" aria-hidden="true">${this._t("shop_pick_short")}</span>
            </button>`
          : nothing;
      // Open again after a later transfer (0.5.0): what already went into the cart.
      const hint = item.cart_hint
        ? html`<p class="cart-hint">${icon(mdiCartOutline, "i s")}<span>${this._t("shop_cart_hint", { qty: localQty(this._lang, item.cart_hint) })}</span></p>`
        : nothing;
      return html`<li class="shop-item v5 ${picked ? "picked" : ""} ${error ? "failed" : ""} ${placeholder ? "pending" : ""}" data-item=${id}>
        ${this._doneBtn(item, placeholder)}
        <div class="shop-body">
          ${head}${hint}
          ${picnic && p
            ? html`<div class="prod-row">${product(true)}<div class="take-row">${take}${mainStepper}</div></div>${this._smallLines(item)}`
            : nothing}
          ${error ? html`<p class="error-text item-error">${this._t("send_item_failed", { message: error })}</p>` : nothing}
        </div>
        <div class="row-end">${pick}${placeholder || (!picnic && !this._shop?.departments?.length) ? html`<span class="menu-gap"></span>` : menu}</div>
      </li>`;
    }
    return html`<li class="shop-item ${picked ? "picked" : ""} ${error ? "failed" : ""}" data-item=${id}>
      <button
        class="check-btn"
        role="checkbox"
        aria-checked=${picked ? "true" : "false"}
        aria-label=${this._t("shop_take", { name: item.name })}
        title=${p ? this._t("shop_take", { name: item.name }) : this._t("shop_pick_product")}
        @click=${() => (p ? this._setPicked(id, !picked) : this._openProduct(item))}
      >
        <span class="check" aria-hidden="true">${picked ? icon(mdiCheck) : nothing}</span>
      </button>
      <div class="shop-body">
        ${head}
        ${p
          ? html`<div class="prod-row">${product(true)}
              ${mainStepper}</div>
              ${this._smallLines(item)}`
          : html`<button class="btn pick-product" @click=${() => this._openProduct(item)}>
              ${icon(mdiMagnify)}<span>${this._t("shop_pick_product")}</span>
            </button>`}
        ${error ? html`<p class="error-text item-error">${this._t("send_item_failed", { message: error })}</p>` : nothing}
      </div>
      ${menu}
    </li>`;
  }

  /** The smaller package of an entry (0.5.0): its own row with pieces, or the hint with a button to pick one. */
  private _smallLines(item: ShoppingItem): TemplateResult | typeof nothing {
    const small = item.small ?? null;
    const smallN = this._smallCount(item);
    return small
                ? html`<div class="prod-row small-row">
                    <button
                      class="product small-product"
                      aria-label=${`${this._t("shop_small_other")}: ${small.name}`}
                      @click=${() => this._openProduct(item, true)}
                    >
                      <span class="pname"><span class="small-tag">${this._t("shop_small_label")}:</span> ${small.name}</span
                      ><span class="pmeta">${this._productMeta(small)}</span>
                    </button>
                    <div class="stepper" role="group" aria-label=${`${this._t("shop_qty")}: ${small.name}`}>
                      <button class="icon-btn" aria-label=${this._t("shop_small_less")} ?disabled=${smallN <= (item.amount >= 1 ? 0 : 1)} @click=${() => this._setSmallAmount(item, smallN - 1)}>
                        ${icon(mdiMinus)}
                      </button>
                      <output aria-live="polite">${smallN}</output>
                      <button class="icon-btn" aria-label=${this._t("shop_small_more")} ?disabled=${smallN >= AMOUNT_MAX} @click=${() => this._setSmallAmount(item, smallN + 1)}>
                        ${icon(mdiPlus)}
                      </button>
                    </div>
                  </div>`
                : item.rest
                  ? html`<div class="rest-line">
                      <span>${this._t("shop_rest", { rest: localQty(this._lang, item.rest) })}</span>
                      <button class="btn small pick-small" @click=${() => this._openProduct(item, true)}>
                        ${icon(mdiMagnify, "i s")}<span>${this._t("shop_pick_small")}</span>
                      </button>
                    </div>`
                  : nothing;
  }

  private _renderItemMenu(d: Dialog & { kind: "item_menu" }): TemplateResult {
    const item = this._item(d.item_id);
    if (!item) return this._dialogFrame(html``);
    const run = (fn: () => void) => () => {
      this._dialog = undefined;
      fn();
    };
    const picnic = !!this._shop?.picnic.available;
    return this._dialogFrame(html`<div class="menu-list">
      ${this._shopV5 && this._shop?.departments?.length
        ? html`<button class="menu-item dept-change" @click=${() => (this._dialog = { kind: "department", item_id: item.item_id })}>
            ${icon(mdiShapeOutline)}<span>${this._t("shop_dept_change")}</span>
          </button>`
        : nothing}
      ${picnic
        ? html`<button class="menu-item" @click=${() => this._openProduct(item)}>
              ${icon(item.product ? mdiSwapHorizontal : mdiMagnify)}<span>${this._t(item.product ? "shop_other_product" : "shop_pick_product")}</span>
            </button>
            ${item.product
              ? html`<button class="menu-item" @click=${run(() => void this._unmap(item))}>
                  ${icon(mdiLinkVariantOff)}<span>${this._t("shop_forget")}</span>
                </button>`
              : nothing}
            ${item.small && !item.sent_at
              ? html`<button class="menu-item" @click=${run(() => void this._mapSmall(item, null))}>
                  ${icon(mdiClose)}<span>${this._t("shop_small_remove")}</span>
                </button>`
              : nothing}
            <button class="menu-item" @click=${run(() => void this._setSkip(item, true))}>
              ${icon(mdiCancel)}<span>${this._t("shop_never")}</span>
            </button>`
        : nothing}
    </div>`);
  }

  /** Groups to choose from (0.5.0); the current one is marked. */
  private _renderDepartmentDialog(d: Dialog & { kind: "department" }): TemplateResult {
    const item = this._item(d.item_id);
    if (!item) return this._dialogFrame(html``);
    const current = this._deptOf(item);
    return this._dialogFrame(html`<ul class="pick-list depts">
      ${(this._shop?.departments ?? []).map(
        (dep: ShopDepartment) => html`<li>
          <button
            class="pick dept-pick"
            aria-pressed=${dep.key === current ? "true" : "false"}
            @click=${() => void this._setDepartment(item, dep.key)}
          >
            <span class="dept-name">${dep.name}</span>
            ${dep.key === current ? html`<span class="chosen">${icon(mdiCheck, "i s")}${this._t("product_current")}</span>` : nothing}
          </button>
        </li>`,
      )}
    </ul>`);
  }

  private _renderProductDialog(d: Dialog & { kind: "product" }): TemplateResult {
    const item = this._item(d.item_id);
    const searchOk = !!this._shop?.picnic.search;
    const forSmall = !!d.small;
    const current = forSmall ? item?.small?.id : item?.product?.id;
    const choose = (p: PicnicHit) => {
      if (!item) return;
      if (forSmall) void this._mapSmall(item, p);
      else void this._mapProduct(item, p);
    };
    let results: TemplateResult | typeof nothing = nothing;
    if (d.state === "loading")
      results = html`<div aria-busy="true" aria-label=${this._t("loading")}>
        <div class="skel line"></div><div class="skel line short"></div><div class="skel line"></div>
      </div>`;
    else if (d.state === "error") results = html`<p class="error-text" role="alert">${this._t("product_failed", { message: d.error })}</p>`;
    else if (d.state === "done")
      results = d.products.length
        ? html`<ul class="pick-list products">
            ${d.products.map(
              (p) => html`<li>
                <button class="pick product-hit" aria-pressed=${p.id === current ? "true" : "false"} @click=${() => choose(p)}>
                  <span class="hit-text"
                    ><span class="pname">${p.name}</span><span class="pmeta">${this._productMeta(p)}</span>${forSmall && p.fits_rest
                      ? html`<span class="fits-mark">${icon(mdiCheck, "i s")}${this._t("shop_fits_rest")}</span>`
                      : nothing}</span
                  >
                  ${p.id === current ? html`<span class="chosen">${icon(mdiCheck, "i s")}${this._t("product_current")}</span>` : nothing}
                </button>
              </li>`,
            )}
          </ul>`
        : html`<p class="empty-day">${this._t("product_none")}</p>`;
    return this._dialogFrame(html`
      ${searchOk
        ? html`<p class="dlg-hint">
            ${forSmall && d.small?.rest
              ? this._t("small_hint", { rest: localQty(this._lang, d.small.rest) })
              : this._t("product_hint")}
          </p>`
        : html`<div class="banner info">${icon(mdiInformationOutline)}<span>${this._t("shop_no_search")}${this._shop?.picnic.reason_code
            ? html` ${this._t("shop_reason", { reason: picnicText(this._lang, this._shop.picnic.reason_code) })}`
            : nothing}</span></div>`}
      <form
        class="search-form product-form"
        role="search"
        @submit=${(e: Event) => {
          e.preventDefault();
          void this._productSearch();
        }}
      >
        <label class="field">
          ${icon(mdiMagnify)}
          <span class="sr">${this._t("product_search_label")}</span>
          <input
            type="search"
            enterkeyhint="search"
            autocomplete="off"
            maxlength="60"
            ?disabled=${!searchOk}
            .value=${live(d.query)}
            @input=${(e: Event) => {
              const now = this._dialog;
              if (now?.kind === "product") this._dialog = { ...now, query: (e.target as HTMLInputElement).value };
            }}
          />
        </label>
        <button class="btn primary" type="submit" ?disabled=${!searchOk || !d.query.trim() || d.state === "loading"}>
          ${this._t("search_button")}
        </button>
      </form>
      ${results}
    `);
  }

  private _renderForgetMissingDialog(d: Dialog & { kind: "forget_missing" }): TemplateResult {
    return this._dialogFrame(
      html`<p class="dlg-hint">${this._t("miss_forget_text")}</p>`,
      html`<button class="btn" @click=${() => (this._dialog = undefined)}>${this._t("cancel")}</button>
        <button
          class="btn primary"
          @click=${() => {
            this._dialog = undefined;
            void this._forgetMissing(d.id);
          }}
        >
          ${icon(mdiClose)}<span>${this._t("miss_forget_confirm")}</span>
        </button>`,
    );
  }

  private _renderSendDialog(d: Dialog & { kind: "send" }): TemplateResult {
    return this._dialogFrame(
      html`<p class="send-count">${d.n === 1 ? this._t("send_text_one") : this._t("send_text", { n: d.n })}</p>
        <p class="send-safe">${icon(mdiInformationOutline)}<span>${this._t("send_no_order")}</span></p>`,
      html`<button class="btn" @click=${() => (this._dialog = undefined)}>${this._t("cancel")}</button>
        <button class="btn primary send-ok" @click=${() => void this._send()}>
          ${icon(mdiCartPlus)}<span>${this._t("send_confirm")}</span>
        </button>`,
    );
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
      case "product":
        return this._t(d.small ? "small_title" : "product_title", { name: d.name });
      case "item_menu":
        return this._item(d.item_id)?.name ?? "";
      case "department":
        return this._t("dept_title", { name: this._item(d.item_id)?.name ?? "" });
      case "send":
        return this._t("send_title");
      case "forget_missing":
        return this._t("miss_forget_title");
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
      case "product":
        return this._renderProductDialog(d);
      case "item_menu":
        return this._renderItemMenu(d);
      case "department":
        return this._renderDepartmentDialog(d);
      case "send":
        return this._renderSendDialog(d);
      case "forget_missing":
        return this._renderForgetMissingDialog(d);
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
    const entry: PlannerEntry = { kitchenowl_id: d.id, name: d.name, image: d.image, servings: d.servings ?? null };
    return this._dialogFrame(html`${d.servings != null
      ? html`<p class="dlg-hint plan-for">${this._t(d.servings === 1 ? "plan_for_one" : "plan_for", { n: d.servings })}</p>`
      : nothing}${groups.map(
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

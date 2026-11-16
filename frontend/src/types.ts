/** Data shapes of the EatFresh WebSocket API (see websocket_api.py). */

export interface HomeAssistant {
  language?: string;
  locale?: { language?: string };
  themes?: { darkMode?: boolean };
  config?: { time_zone?: string };
  callWS<T>(msg: Record<string, unknown>): Promise<T>;
}

export interface PanelRoute {
  prefix: string;
  path: string;
}

export interface SourceInfo {
  id: string;
  name: string;
  enabled: boolean;
  searchable: boolean;
}

export interface SearchHit {
  key: string;
  source: string;
  id: string;
  title: string;
  url: string;
  image: string | null;
  total_time: number | null;
  rating: number | null;
  favorite: boolean;
}

export interface SourceErrorInfo {
  source: string;
  message: string;
}

export interface Ingredient {
  name: string;
  amount: number | null;
  unit: string | null;
  note: string | null;
  raw: string;
}

export interface Recipe {
  key: string;
  source: string;
  id: string;
  url: string;
  title: string;
  description: string | null;
  image: string | null;
  servings: number | null;
  prep_time: number | null;
  cook_time: number | null;
  total_time: number | null;
  ingredients: Ingredient[];
  steps: string[];
  tags: string[];
}

export interface RecipeResponse {
  recipe: Recipe;
  favorite: boolean;
  kitchenowl_id: number | null;
}

export interface CollectionRecipe {
  kitchenowl_id: number;
  name: string;
  image: string | null;
  source: string | null;
  time: number | null;
  yields: number | null;
  tags: string[];
  hidden: boolean;
}

/** Answer of `eatfresh/collection/recipe` (read from KitchenOwl only). */
export interface CollectionRecipeResponse {
  recipe: Recipe;
  kitchenowl_id: number;
  tags: string[];
  hidden: boolean;
}

export interface TagsResponse {
  categories: string[];
  tags: string[];
}

export interface PlannerEntry {
  kitchenowl_id: number;
  name: string;
  image: string | null;
}

export interface PlannerDay {
  date: string;
  entries: PlannerEntry[];
}

export interface PlannerResponse {
  week_start: string;
  /** Today in the time zone of Home Assistant. */
  today: string;
  days: PlannerDay[];
  unscheduled: PlannerEntry[];
  /** When the week went to the shopping list (ISO time), on any device. */
  shopping_list_at?: string | null;
}

export interface WeekShoppingResponse {
  added: number;
  recipes: number;
  /** Time of this transfer. */
  at?: string | null;
  /** Set instead when the week went to the list before; nothing was sent. */
  already_added_at?: string;
}

export interface WsError {
  code?: string;
  message?: string;
  translation_key?: string;
  translation_placeholders?: Record<string, string>;
}

/** A Picnic product as EatFresh shows it (`price` in cent, or null). */
export interface PicnicProduct {
  id: string;
  name: string;
  unit_quantity: string;
  price: number | null;
}

export interface PicnicStatus {
  available: boolean;
  search: boolean;
  /** English reason, only a fallback. */
  reason: string | null;
  /** Stable code of the reason; the panel translates it. */
  reason_code: string | null;
}

/** One open entry of the KitchenOwl shopping list, with what EatFresh remembers. */
export interface ShoppingItem {
  item_id: number;
  name: string;
  description: string;
  product: PicnicProduct | null;
  amount: number;
  skip: boolean;
  /** When the product went to the Picnic cart (ISO time), or null. */
  sent_at: string | null;
  /** Picnic did not answer in time: it may or may not be in the cart. */
  sent_uncertain?: boolean;
}

/** Answer of `eatfresh/shopping` (reads KitchenOwl and the store, never Picnic). */
export interface ShoppingResponse {
  picnic: PicnicStatus;
  items: ShoppingItem[];
}

export interface PicnicSendResponse {
  sent: { item_id: number; product_id: string; amount: number }[];
  /** `code` is translated by the panel; `message` is English, only a fallback. */
  failed: { item_id: number; code?: string; message: string }[];
}

export type Tab = "search" | "collection" | "planner" | "shopping";

export type View =
  | { name: "search" }
  | { name: "collection" }
  | { name: "planner" }
  | { name: "shopping" }
  | { name: "recipe"; key?: string; url?: string }
  | { name: "korecipe"; id: number };

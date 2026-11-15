/** Data shapes of the EatFresh WebSocket API (see websocket_api.py). */

export interface HomeAssistant {
  language?: string;
  locale?: { language?: string };
  themes?: { darkMode?: boolean };
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
}

export interface WsError {
  code?: string;
  message?: string;
  translation_key?: string;
  translation_placeholders?: Record<string, string>;
}

export type View =
  | { name: "search" }
  | { name: "collection" }
  | { name: "recipe"; key?: string; url?: string };

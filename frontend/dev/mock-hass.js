// Fake `hass` for the EatFresh dev pages. All data here is invented.
// URL options: ?theme=dark  ?lang=en  ?delay=600
//   ?fail=favorite,unfavorite,shopping,collection,search,recipe,sources,
//         korecipe,hide,unhide,tags,set_tags,planner,plan,unplan,week_shopping
//   A link to https://rezepte.example.com/emmi/eintopf is already in the collection (id 102).
//   ?failonce=favorite (the named calls fail the first time only, like a short outage)
//   ?empty=collection,planner
//   ?today=YYYY-MM-DD (today of Home Assistant, default: the browser's day)
// Shopping list to Picnic (0.4.0), all products invented:
//   ?picnic=none       Picnic integration not set up
//   ?picnic=nosearch   Picnic set up, but its product search is not available
//   ?picnic=partial    every second entry of a send fails (partial success)
//   ?picnic=used       some entries already have a product, one is in the cart, one is excluded
//   ?picnic=noread     the cart cannot be read at the start of a send: the run does not start
//   ?picnic=cartchanged  "undo" finds fewer pieces in the cart: nothing taken out, "maybe in the cart"
//   ?fail=shopping,picnic_search,picnic_map,picnic_unmap,picnic_skip,picnic_send,picnic_undo
//   ?failonce=picnic_send (fails the first time only)
//   ?empty=shopping    the KitchenOwl shopping list is empty
// The source "Küchengötter" always reports an error in the search, to show the banner.

const pad = (n) => String(n).padStart(2, "0");
const iso = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
const parse = (s) => {
  const [y, m, d] = s.split("-").map(Number);
  return new Date(y, m - 1, d);
};
const plusDays = (s, n) => {
  const d = parse(s);
  d.setDate(d.getDate() + n);
  return iso(d);
};
const mondayOf = (s) => plusDays(s, -((parse(s).getDay() + 6) % 7));

export function createMock(params = new URLSearchParams(location.search)) {
  const fail = new Set((params.get("fail") ?? "").split(",").filter(Boolean));
  const failOnce = new Set((params.get("failonce") ?? "").split(",").filter(Boolean));
  const empty = new Set((params.get("empty") ?? "").split(",").filter(Boolean));
  const delay = Number(params.get("delay") ?? 350);
  const dark = params.get("theme") === "dark";
  const lang = params.get("lang") ?? "de";

  const palette = ["#e9a23b", "#7fb069", "#d1495b", "#5b8e7d", "#8e7dbe", "#f4a259", "#4f9d9a", "#bc4b51"];
  const placeholder = (i) => {
    const c = palette[i % palette.length];
    const c2 = palette[(i + 3) % palette.length];
    const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 300"><defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="${c}"/><stop offset="1" stop-color="${c2}"/></linearGradient></defs><rect width="400" height="300" fill="url(#g)"/><circle cx="200" cy="160" r="88" fill="#fff" opacity=".85"/><circle cx="200" cy="160" r="62" fill="${c}" opacity=".55"/><circle cx="${170 + (i % 3) * 20}" cy="140" r="14" fill="${c2}"/><circle cx="225" cy="${170 + (i % 2) * 12}" r="10" fill="#fff" opacity=".9"/></svg>`;
    return "data:image/svg+xml;charset=utf-8," + encodeURIComponent(svg);
  };

  const sources = [
    { id: "gaumenfreundin", name: "Gaumenfreundin", enabled: true, searchable: true },
    { id: "emmi", name: "Emmikochteinfach", enabled: true, searchable: true },
    { id: "kuechengoetter", name: "Küchengötter", enabled: true, searchable: true },
    { id: "chefkoch", name: "Chefkoch", enabled: false, searchable: true },
    { id: "jsonld", name: "Link", enabled: true, searchable: false },
  ];
  const titles = [
    "Ofengemüse mit Kräuterquark", "Linsensuppe mit Möhren", "Schnelle Tomatenpasta", "Kürbis-Risotto mit Salbei",
    "Gefüllte Paprika aus dem Ofen", "Apfel-Zimt-Pfannkuchen", "Bunter Couscous-Salat", "Spinat-Feta-Quiche",
    "Kartoffelgratin mit Thymian", "Gemüsecurry mit Kokosmilch", "Zucchini-Puffer mit Dip", "Pilzpfanne mit Knödeln",
  ];
  const hits = titles.map((title, i) => {
    const source = ["gaumenfreundin", "emmi", "kuechengoetter"][i % 3];
    const id = `beispiel-${i + 1}`;
    return {
      key: `${source}:${id}`, source, id, title,
      url: `https://rezepte.example.com/${source}/${id}`,
      image: i === 5 ? null : placeholder(i),
      total_time: [25, 45, 15, 50, 70, 30, 20, 85, 95, 35, 40, 120][i],
      rating: null,
    };
  });

  const categories = lang.startsWith("de")
    ? ["Vorspeise", "Hauptspeise", "Nachspeise", "Vegetarisch", "Vegan", "Pasta", "Suppe", "Salat", "Backen", "Frühstück"]
    : ["Starter", "Main course", "Dessert", "Vegetarian", "Vegan", "Pasta", "Soup", "Salad", "Baking", "Breakfast"];

  const favorites = new Map([[hits[1].key, 101]]);
  let nextKo = 200;
  const collection = empty.has("collection") ? [] : [
    { kitchenowl_id: 101, name: hits[1].title, image: placeholder(1), source: hits[1].url, time: 45, yields: 4, tags: ["Suppe", "Vegan"], hidden: false },
    { kitchenowl_id: 102, name: "Omas Gemüseeintopf", image: placeholder(9), source: "https://rezepte.example.com/emmi/eintopf", time: 60, yields: 6, tags: ["Suppe", "Hauptspeise", "Vegetarisch"], hidden: false },
    { kitchenowl_id: 103, name: "Haferflocken-Bananen-Brot", image: placeholder(4), source: null, time: 75, yields: 12, tags: ["Backen", "Frühstück", "Vegetarisch"], hidden: false },
    { kitchenowl_id: 104, name: "Ofenkartoffeln mit Kräuterdip", image: null, source: "https://rezepte.example.com/gaumenfreundin/ofenkartoffeln", time: 50, yields: 2, tags: ["Hauptspeise", "Vegetarisch"], hidden: false },
    { kitchenowl_id: 105, name: "Feierabend-Nudelauflauf mit extra langem Namen zum Testen", image: placeholder(7), source: "https://rezepte.example.com/x/auflauf", time: 40, yields: 4, tags: ["Pasta", "Hauptspeise", "Familienessen", "Schnell"], hidden: false },
    { kitchenowl_id: 106, name: "Alter Kartoffelsalat", image: placeholder(6), source: "https://rezepte.example.com/x/salat", time: 30, yields: 4, tags: ["Salat"], hidden: true },
  ];
  const byId = (id) => collection.find((r) => r.kitchenowl_id === id);

  // Week plan: entries relative to today, plus one without a day.
  // ?today=YYYY-MM-DD plays a Home Assistant in another time zone than the browser.
  const now = params.get("today") ?? iso(new Date());
  const weekLists = new Map();
  const plan = empty.has("planner") ? [] : [
    { id: 102, date: now },
    { id: 101, date: plusDays(now, 1) },
    { id: 103, date: plusDays(now, 1) },
    { id: 105, date: plusDays(now, 3) },
    { id: 104, date: plusDays(now, -2) },
    { id: 104, date: null },
  ];

  const ingredients = [
    { name: "Mehl", amount: 250, unit: "g", note: "Type 405", raw: "250 g Mehl (Type 405)" },
    { name: "Milch", amount: 0.5, unit: "l", note: null, raw: "½ l Milch" },
    { name: "Eier", amount: 2, unit: null, note: null, raw: "2 Eier" },
    { name: "Zwiebel", amount: 1, unit: null, note: "fein gewürfelt", raw: "1 Zwiebel" },
    { name: "Olivenöl", amount: 1.5, unit: "EL", note: null, raw: "1,5 EL Olivenöl" },
    { name: "Salz und Pfeffer", amount: null, unit: null, note: null, raw: "Salz und Pfeffer" },
  ];
  const steps = [
    "Alle Zutaten bereitstellen und den Ofen auf 200 °C vorheizen.",
    "Zwiebel in Öl glasig dünsten, dann die übrigen Zutaten nach und nach dazugeben.",
    "Alles gut verrühren und etwa 20 Minuten garen, bis es duftet.",
    "Mit Salz und Pfeffer abschmecken und warm servieren.",
  ];
  const makeRecipe = (hit) => ({
    key: hit.key, source: hit.source, id: hit.id, url: hit.url, title: hit.title,
    description: "Ein erfundenes Beispielrezept für die Entwicklung. Schmeckt nur in der Fantasie.",
    image: hit.image, servings: 4, prep_time: 15, cook_time: Math.max(5, (hit.total_time ?? 30) - 15), total_time: hit.total_time,
    ingredients, steps, tags: ["Beispiel"],
  });
  const koRecipe = (r) => ({
    key: `kitchenowl:${r.kitchenowl_id}`, source: "kitchenowl", id: String(r.kitchenowl_id), url: r.source ?? "",
    title: r.name, description: "Aus KitchenOwl gelesen, ohne Abruf der Rezeptseite (Beispiel).",
    image: r.image, servings: r.yields, prep_time: null, cook_time: null, total_time: r.time,
    ingredients: ingredients.map((i) => ({ name: i.name, amount: null, unit: null, note: null, raw: `${[i.amount, i.unit].filter((x) => x != null).join(" ")} ${i.name}`.trim() })),
    steps, tags: r.tags,
  });

  const wsError = (code, message, extra = {}) => Object.assign(new Error(message), { code, message, ...extra });
  const wait = () => new Promise((r) => setTimeout(r, delay));
  const extraRecipes = new Map();
  const check = (name) => {
    if (fail.has(name)) throw wsError("kitchenowl_error", `Mock: ${name} failed`);
  };
  const entry = (id) => {
    const r = byId(id);
    return { kitchenowl_id: id, name: r?.name ?? `#${id}`, image: r?.image ?? null };
  };
  const week = (week_start) => {
    const start = week_start ?? mondayOf(now);
    const days = Array.from({ length: 7 }, (_, i) => plusDays(start, i)).map((date) => ({
      date,
      entries: plan.filter((p) => p.date === date).map((p) => entry(p.id)),
    }));
    return { week_start: start, today: now, days, unscheduled: plan.filter((p) => !p.date).map((p) => entry(p.id)) };
  };

  // ---- shopping list to Picnic (invented products, cart in memory)
  const picnicMode = new Set((params.get("picnic") ?? "").split(",").filter(Boolean));
  const catalog = [
    { id: "p-milch-1", name: "Frische Vollmilch 3,5 %", unit_quantity: "1 l", price: 119 },
    { id: "p-milch-2", name: "Haltbare Milch 1,5 %", unit_quantity: "1 l", price: 99 },
    { id: "p-milch-3", name: "Hafer-Drink ohne Milch", unit_quantity: "1 l", price: 189 },
    { id: "p-mehl-1", name: "Weizenmehl Type 405", unit_quantity: "1 kg", price: 89 },
    { id: "p-mehl-2", name: "Dinkelmehl Type 630", unit_quantity: "1 kg", price: 199 },
    { id: "p-eier-1", name: "Eier aus Freilandhaltung", unit_quantity: "10 Stück", price: 329 },
    { id: "p-eier-2", name: "Bio-Eier", unit_quantity: "6 Stück", price: 279 },
    { id: "p-tomaten-1", name: "Gehackte Tomaten", unit_quantity: "400 g", price: 79 },
    { id: "p-tomaten-2", name: "Strauchtomaten", unit_quantity: "500 g", price: 229 },
    { id: "p-zwiebeln-1", name: "Gemüsezwiebeln", unit_quantity: "1 kg", price: 149 },
    { id: "p-zwiebeln-2", name: "Rote Zwiebeln", unit_quantity: "500 g", price: 119 },
    { id: "p-spaghetti-1", name: "Spaghetti Nr. 5", unit_quantity: "500 g", price: 139 },
    { id: "p-spaghetti-2", name: "Vollkorn-Spaghetti", unit_quantity: "500 g", price: 169 },
    { id: "p-basilikum-1", name: "Basilikum im Topf", unit_quantity: "1 Stück", price: null },
    { id: "p-olivenoel-1", name: "Natives Olivenöl extra", unit_quantity: "750 ml", price: 799 },
    { id: "p-parmesan-1", name: "Hartkäse am Stück, gereift, mit sehr langem Produktnamen zum Testen", unit_quantity: "4 x 250 g", price: 1249 },
  ];
  const shopping = empty.has("shopping") ? [] : [
    { item_id: 501, name: "Milch", description: "1 l" },
    { item_id: 502, name: "Mehl", description: "500 g" },
    { item_id: 503, name: "Eier", description: "6" },
    { item_id: 504, name: "Tomaten", description: "800 g" },
    { item_id: 505, name: "Zwiebeln", description: "2" },
    { item_id: 506, name: "Spaghetti", description: "1500g" },
    { item_id: 507, name: "Basilikum", description: "1 Bund" },
    { item_id: 508, name: "Olivenöl", description: "" },
    { item_id: 509, name: "Salz", description: "" },
    { item_id: 510, name: "Parmesan", description: "1kg" },
  ];
  const picnicMap = new Map();
  const picnicSkip = new Set();
  const picnicSent = new Map();
  const cart = new Map();
  if (picnicMode.has("used")) {
    const p = (id) => catalog.find((c) => c.id === id);
    picnicMap.set("milch", { product: p("p-milch-1"), amount: 1 });
    picnicMap.set("mehl", { product: p("p-mehl-1"), amount: 1 });
    picnicMap.set("spaghetti", { product: p("p-spaghetti-1"), amount: 3 });
    picnicMap.set("parmesan", { product: p("p-parmesan-1"), amount: 1 });
    picnicSkip.add("salz");
    picnicSent.set(506, { product_id: "p-spaghetti-1", amount: 3, at: new Date(Date.now() - 40 * 60000).toISOString() });
    cart.set("p-spaghetti-1", 3);
  }
  // Like the core's suggest_amount: "1500g" with "500 g" packs gives 3, otherwise 1.
  const grams = (text) => {
    const t = String(text).toLowerCase().replace(",", ".");
    const m = t.match(/(?:(\d+)\s*x\s*)?(\d+(?:\.\d+)?)\s*(kg|g|ml|l)\b/);
    if (!m) return null;
    const n = Number(m[1] ?? 1) * Number(m[2]);
    return { kg: 1000, l: 1000, g: 1, ml: 1 }[m[3]] * n;
  };
  const suggest = (description, unit) => {
    const need = grams(description);
    const pack = grams(unit);
    if (!need || !pack) return 1;
    return Math.min(20, Math.max(1, Math.ceil(need / pack - 0.01)));
  };
  const picnicCheck = (name) => {
    if (fail.has(name) || failOnce.delete(name))
      throw wsError("picnic_error", `Mock: ${name} failed`);
  };
  const picnicStatus = () =>
    picnicMode.has("none")
      ? { available: false, search: false, reason: "The Picnic integration is not set up in Home Assistant", reason_code: "not_set_up" }
      : picnicMode.has("nosearch")
        ? { available: true, search: false, reason: "The Picnic integration offers no product search", reason_code: "no_search" }
        : { available: true, search: true, reason: null, reason_code: null };
  const needPicnic = () => {
    if (!picnicStatus().available) throw wsError("picnic_unavailable", "Picnic is not set up");
  };
  const stem = (w) => w.slice(0, Math.max(4, w.length - 2));

  const handlers = {
    "eatfresh/sources": () => {
      if (fail.has("sources")) throw wsError("unknown_error", "Mock: sources failed");
      return { sources };
    },
    "eatfresh/search": ({ query, sources: wanted }) => {
      if (fail.has("search")) throw wsError("source_error", "Mock: search failed");
      const q = query.toLowerCase();
      const allowed = new Set(wanted ?? sources.filter((s) => s.enabled && s.searchable).map((s) => s.id));
      const words = q.split(/\s+/).filter(Boolean);
      let found = hits.filter((h) => allowed.has(h.source) && h.source !== "kuechengoetter");
      if (q !== "rezept" && q !== "recipe") found = found.filter((h) => words.some((w) => h.title.toLowerCase().includes(w)));
      const errors = allowed.has("kuechengoetter") ? [{ source: "kuechengoetter", message: "Zeitüberschreitung (Beispiel)" }] : [];
      const hidden = new Set(collection.filter((c) => c.hidden).map((c) => c.kitchenowl_id));
      return { hits: found.map((h) => ({ ...h, favorite: favorites.has(h.key) && !hidden.has(favorites.get(h.key)) })), errors };
    },
    "eatfresh/recipe": ({ key, url }) => {
      if (fail.has("recipe")) throw wsError("source_blocked", "Mock: blocked");
      let hit = key ? hits.find((h) => h.key === key) : hits.find((h) => h.url === url);
      if (!hit && url) {
        if (url.includes("kaputt")) throw wsError("not_found", "No recipe data");
        hit = extraRecipes.get(url) ?? { key: `jsonld:${url}`, source: "jsonld", id: url, url, title: `Rezept von ${new URL(url).hostname}`, image: placeholder(extraRecipes.size + 2), total_time: 35 };
        extraRecipes.set(url, hit);
        hits.push(hit);
      }
      if (!hit) throw wsError("not_found", "Unknown key");
      const koId = favorites.get(hit.key) ?? collection.find((c) => c.source === hit.url)?.kitchenowl_id ?? null;
      return { recipe: makeRecipe(hit), favorite: favorites.has(hit.key) && !byId(koId)?.hidden, kitchenowl_id: koId };
    },
    "eatfresh/favorite": ({ key }) => {
      if (fail.has("favorite")) throw wsError("kitchenowl_error", "Mock: KitchenOwl down");
      if (failOnce.delete("favorite")) throw wsError("kitchenowl_error", "Mock: KitchenOwl down");
      // Like the core: look in the store, then for a recipe with the same source link.
      if (!favorites.has(key)) {
        const known = hits.find((h) => h.key === key);
        const same = known && collection.find((c) => c.source === known.url);
        if (same) favorites.set(key, same.kitchenowl_id);
      }
      if (favorites.has(key)) {
        const r = byId(favorites.get(key));
        if (r) r.hidden = false;
        return { kitchenowl_id: favorites.get(key), created: false, tags: r?.tags ?? [] };
      }
      const hit = hits.find((h) => h.key === key);
      const id = nextKo++;
      const tags = [categories[1]];
      favorites.set(key, id);
      if (hit) collection.unshift({ kitchenowl_id: id, name: hit.title, image: hit.image, source: hit.url, time: hit.total_time, yields: 4, tags, hidden: false });
      return { kitchenowl_id: id, created: true, tags };
    },
    "eatfresh/unfavorite": ({ key }) => {
      if (fail.has("unfavorite")) throw wsError("unknown_error", "Mock: store failed");
      favorites.delete(key);
      return {};
    },
    "eatfresh/favorites": () => ({ favorites: [...favorites].map(([key, kitchenowl_id]) => ({ key, kitchenowl_id })) }),
    "eatfresh/collection": ({ include_hidden }) => {
      if (fail.has("collection")) throw wsError("kitchenowl_auth", "Mock: 401");
      return { recipes: collection.filter((r) => include_hidden || !r.hidden) };
    },
    "eatfresh/collection/recipe": ({ kitchenowl_id }) => {
      check("korecipe");
      const r = byId(kitchenowl_id);
      if (!r) throw wsError("not_found", "Unknown recipe");
      return { recipe: koRecipe(r), kitchenowl_id, tags: r.tags, hidden: r.hidden };
    },
    "eatfresh/collection/hide": ({ kitchenowl_id }) => {
      check("hide");
      byId(kitchenowl_id).hidden = true;
      return {};
    },
    "eatfresh/collection/unhide": ({ kitchenowl_id }) => {
      check("unhide");
      byId(kitchenowl_id).hidden = false;
      return {};
    },
    "eatfresh/collection/set_tags": ({ kitchenowl_id, tags }) => {
      check("set_tags");
      byId(kitchenowl_id).tags = [...tags];
      return { tags };
    },
    "eatfresh/tags": () => {
      check("tags");
      return { categories, tags: [...new Set(collection.flatMap((r) => r.tags))] };
    },
    "eatfresh/planner": ({ week_start }) => {
      check("planner");
      const w = week(week_start);
      return { ...w, shopping_list_at: weekLists.get(w.week_start) ?? null };
    },
    "eatfresh/planner/add": ({ kitchenowl_id, date }) => {
      check("plan");
      // Like KitchenOwl: a recipe that gets a day loses its entry without a day.
      const undated = plan.findIndex((p) => p.id === kitchenowl_id && !p.date);
      if (undated >= 0) plan.splice(undated, 1);
      if (!plan.some((p) => p.id === kitchenowl_id && p.date === date)) plan.push({ id: kitchenowl_id, date });
      return {};
    },
    "eatfresh/planner/remove": ({ kitchenowl_id, date }) => {
      check("unplan");
      const i = plan.findIndex((p) => p.id === kitchenowl_id && p.date === (date ?? null));
      if (i >= 0) plan.splice(i, 1);
      return {};
    },
    "eatfresh/planner/shopping_list": ({ week_start, confirm }) => {
      const w = week(week_start);
      // Like the core: a second transfer of a week needs confirm.
      const before = weekLists.get(w.week_start);
      if (before && !confirm) return { added: 0, recipes: 0, already_added_at: before };
      // A recipe planned on two days counts twice.
      const ids = w.days.flatMap((d) => [...new Set(d.entries.map((e) => e.kitchenowl_id))]);
      if (fail.has("week_shopping"))
        throw wsError("kitchenowl_error", "Mock: shopping failed", {
          translation_key: "shopping_list_partial",
          translation_placeholders: { added_recipes: "1", total: String(ids.length), added: "6", message: "Mock" },
        });
      const at = new Date().toISOString();
      if (ids.length) weekLists.set(w.week_start, at);
      return { added: ids.length * 6, recipes: ids.length, at: ids.length ? at : before ?? null };
    },
    "eatfresh/shopping": () => {
      check("shopping");
      return {
        picnic: picnicStatus(),
        items: shopping.map((i) => {
          const m = picnicMap.get(i.name.toLowerCase());
          return {
            ...i,
            product: m?.product ?? null,
            amount: m?.amount ?? 1,
            skip: picnicSkip.has(i.name.toLowerCase()),
            sent_at: picnicSent.get(i.item_id)?.at ?? null,
            sent_uncertain: !!picnicSent.get(i.item_id)?.uncertain,
          };
        }),
      };
    },
    "eatfresh/picnic/search": ({ query }) => {
      needPicnic();
      if (!picnicStatus().search) throw wsError("picnic_unavailable", "Search not available");
      picnicCheck("picnic_search");
      if (typeof query !== "string" || !query.trim() || query.length > 60) throw wsError("invalid_format", "Bad query");
      const words = query.toLowerCase().split(/\s+/).filter(Boolean).map(stem);
      return { products: catalog.filter((c) => words.some((w) => c.name.toLowerCase().includes(w))).slice(0, 8) };
    },
    "eatfresh/picnic/map": ({ name, product, amount }) => {
      picnicCheck("picnic_map");
      const key = name.toLowerCase();
      const item = shopping.find((i) => i.name.toLowerCase() === key);
      const value = amount ?? suggest(item?.description ?? "", product.unit_quantity);
      if (value < 1 || value > 20) throw wsError("invalid_format", "Bad amount");
      picnicMap.set(key, { product, amount: value });
      picnicSkip.delete(key);
      return {};
    },
    "eatfresh/picnic/unmap": ({ name }) => {
      picnicCheck("picnic_unmap");
      picnicMap.delete(name.toLowerCase());
      return {};
    },
    "eatfresh/picnic/skip": ({ name, skip }) => {
      picnicCheck("picnic_skip");
      if (skip) picnicSkip.add(name.toLowerCase());
      else picnicSkip.delete(name.toLowerCase());
      return {};
    },
    "eatfresh/picnic/send": ({ items }) => {
      needPicnic();
      picnicCheck("picnic_send");
      if (!Array.isArray(items) || items.length > 60) throw wsError("invalid_format", "Too many items");
      // Like the core: the cart is read once at the start; without it the run does not start.
      if (picnicMode.has("noread"))
        throw wsError("picnic_error", "EatFresh could not read the Picnic cart and changed nothing; try again later", { translation_key: "picnic_cart_unreadable" });
      const sent = [];
      const failed = [];
      // Like the core: the run stops at the first error of Picnic, the rest is not tried.
      let stopped = false;
      items.forEach((it, index) => {
        if (stopped) return failed.push({ item_id: it.item_id, code: "not_tried", message: "Not sent: the transfer stopped at an error before" });
        const onList = shopping.some((i) => i.item_id === it.item_id);
        if (!onList || picnicSent.has(it.item_id)) return failed.push({ item_id: it.item_id, code: "not_on_list", message: "The entry is no longer on the shopping list" });
        if (it.amount < 1 || it.amount > 20) throw wsError("invalid_format", "Bad amount");
        if (picnicMode.has("partial") && index === 1) {
          stopped = true;
          return failed.push({ item_id: it.item_id, code: "not_added", message: "Picnic did not put the product into the cart" });
        }
        if (picnicMode.has("maybe") && index === 1) {
          stopped = true;
          picnicSent.set(it.item_id, { product_id: it.product_id, amount: it.amount, at: new Date().toISOString(), uncertain: true });
          return failed.push({ item_id: it.item_id, code: "maybe_sent", message: "Picnic's answer does not show whether the product is in the cart" });
        }
        cart.set(it.product_id, (cart.get(it.product_id) ?? 0) + it.amount);
        picnicSent.set(it.item_id, { product_id: it.product_id, amount: it.amount, at: new Date().toISOString() });
        sent.push({ item_id: it.item_id, product_id: it.product_id, amount: it.amount });
      });
      return { sent, failed };
    },
    "eatfresh/picnic/undo": ({ item_id, remove }) => {
      needPicnic();
      picnicCheck("picnic_undo");
      const s = picnicSent.get(item_id);
      if (!s) throw wsError("not_found", "Not sent");
      if (remove === false) {
        picnicSent.delete(item_id);
        return {};
      }
      // Like the core: "maybe in the cart" is never taken out.
      if (s.uncertain) throw wsError("picnic_error", "EatFresh takes nothing out for an entry that is maybe in the cart", { translation_key: "picnic_maybe_no_undo" });
      // Like the core: fewer pieces in the cart than put in, nothing is taken out, the entry becomes "maybe".
      if (picnicMode.has("cartchanged")) {
        picnicSent.set(item_id, { ...s, uncertain: true });
        throw wsError("picnic_error", "The Picnic cart has fewer pieces than EatFresh put in", { translation_key: "picnic_cart_changed" });
      }
      const left = (cart.get(s.product_id) ?? 0) - s.amount;
      if (left > 0) cart.set(s.product_id, left);
      else cart.delete(s.product_id);
      picnicSent.delete(item_id);
      return {};
    },
    "eatfresh/shopping_list/add": ({ kitchenowl_ids }) => {
      if (fail.has("shopping")) throw wsError("kitchenowl_error", "Mock: shopping failed");
      return { added: kitchenowl_ids.length * 6 };
    },
  };

  window.mockCalls = [];
  window.mockCart = cart;
  const hass = {
    language: lang,
    locale: { language: lang },
    themes: { darkMode: dark },
    async callWS(msg) {
      window.mockCalls.push(msg);
      await wait();
      const handler = handlers[msg.type];
      if (!handler) throw wsError("unknown_command", `Unknown command ${msg.type}`);
      return structuredClone(handler(msg));
    },
  };
  return { hass, dark, lang };
}

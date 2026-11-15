// Fake `hass` for the EatFresh dev pages. All data here is invented.
// URL options: ?theme=dark  ?lang=en  ?delay=600
//   ?fail=favorite,unfavorite,shopping,collection,search,recipe,sources,
//         korecipe,hide,unhide,tags,set_tags,planner,plan,unplan,week_shopping
//   ?empty=collection,planner
//   ?today=YYYY-MM-DD (today of Home Assistant, default: the browser's day)
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
    "eatfresh/shopping_list/add": ({ kitchenowl_ids }) => {
      if (fail.has("shopping")) throw wsError("kitchenowl_error", "Mock: shopping failed");
      return { added: kitchenowl_ids.length * 6 };
    },
  };

  window.mockCalls = [];
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

# EatFresh

[Deutsch](#deutsch) · [English](#english)

## Deutsch

EatFresh ist eine Integration für Home Assistant. Sie sucht Rezepte auf ausgewählten Webseiten, zeigt sie in einer eigenen Seite in der Seitenleiste und speichert sie mit einem Herz in [KitchenOwl](https://kitchenowl.org). Zutaten eines Rezepts kommen mit einem Tipp auf die Einkaufsliste in KitchenOwl.

### Installation über HACS

1. HACS öffnen, oben rechts das Menü wählen, dann **Benutzerdefinierte Repositories**.
2. Adresse `https://github.com/DanielWeeber/homeassistant-eatfresh` eintragen, Typ **Integration**.
3. EatFresh herunterladen und Home Assistant neu starten.

Mindestversion: Home Assistant 2026.11. Getestet mit KitchenOwl 0.8.1. KitchenOwl lädt das Foto eines Rezepts selbst von der Rezeptseite herunter.

### Einrichtung

1. **Einstellungen > Geräte & Dienste > Integration hinzufügen > EatFresh**.
2. Adresse von KitchenOwl (zum Beispiel `https://kitchenowl.example.com`) und einen langlebigen Zugangsschlüssel aus KitchenOwl eingeben.
3. Haushalt und Einkaufsliste wählen.

Danach erscheint „EatFresh“ in der Seitenleiste. Unter **Konfigurieren** wählst du die Rezeptquellen.

### Quellen

- Gaumenfreundin, Emmi kocht einfach, Küchengötter: standardmäßig an.
- Knopf „Rezept-Link“ oben rechts: öffnet das Fenster „Rezept-Link einfügen“. Geht immer, für jede Seite mit Rezeptdaten (schema.org/Recipe).
- Chefkoch: standardmäßig **aus**. Die AGB von Chefkoch (Ziffer 5.1) schränken automatische Abrufe ein. Einschalten geht nur mit einem eigenen Häkchen. Die Nutzung liegt in deiner eigenen Verantwortung. Ist Chefkoch aus, sperrt EatFresh die Quelle über ihre bekannten Hostnamen.

Das Suchlimit gilt **je Quelle**: Eine Suche liefert von jeder Quelle höchstens 20 Treffer (im WebSocket-Befehl `eatfresh/search` über `limit` bis 50 einstellbar). Bei drei Quellen kommen also bis zu 60 Treffer zurück, gemischt.

### Sparsame Abrufe

EatFresh ruft Rezeptseiten nur ab, wenn du suchst oder ein Rezept öffnest, nie im Hintergrund. Je Webseite läuft höchstens ein Abruf gleichzeitig, mit Pause dazwischen. Suchergebnisse bleiben eine Stunde, Rezepte 24 Stunden im Zwischenspeicher. Lehnt eine Seite ab (403, 429, Captcha), versucht EatFresh es nicht noch einmal.

### Sammlung, Kategorien und Ausblenden

- Die Sammlung zeigt die Rezepte aus KitchenOwl. Antippen öffnet ein Rezept so, wie es in KitchenOwl gespeichert ist. Die Rezeptseite wird dafür nicht abgerufen.
- Kategorien: Vorspeise, Hauptspeise, Nachspeise, Vegetarisch, Vegan, Pasta, Suppe, Salat, Backen, Frühstück. Beim Herz schlägt EatFresh passende Kategorien aus den Angaben der Rezeptseite (Tags, Stichwörter) und dem Titel vor. Nur diese Kategorien kommen als Tags nach KitchenOwl. Vegetarisch und Vegan schlägt EatFresh nur vor, wenn ein ganzer Tag der Rezeptseite genau das sagt (`Vegetarisch`, `vegane Rezepte`) oder die Rezeptdaten es als Ernährungsform angeben. Nie aus den Zutaten, nie aus dem Titel und nie aus Teilen längerer Tags (`Vegane Alternativen`, `vegetarisch möglich`). Es bleibt ein Vorschlag: Bitte prüfen, bevor sich jemand darauf verlässt.
- In der Sammlung lassen sich die Kategorien eines Rezepts ändern und eigene ergänzen. Chips filtern die Sammlung. Mehrere gewählte Chips heißt: Das Rezept hat alle. Kategorien in der anderen Sprache (`Soup` und `Suppe`) sind derselbe Chip.
- Ein Rezept-Link wird nur einmal gespeichert, egal wie er geschrieben ist (mit oder ohne `www.`, mit Anhängseln wie `utm_…` oder `fbclid`, als AMP-Seite). Bei eingefügten Links übernimmt EatFresh die kanonische Adresse der Seite.
- **Ausblenden:** Das Rezept verschwindet nur aus der Sammlung in EatFresh. In KitchenOwl bleibt es. „Ausgeblendete anzeigen“ und „Wieder einblenden“ machen es rückgängig, ein neues Herz ebenso. Ausgeblendete Rezepte zählen in Suche und Rezeptansicht nicht als Favorit. Gelöscht wird nichts.

### Wochenplan

Der Reiter „Wochenplan“ zeigt Montag bis Sonntag (Zeitzone von Home Assistant). Mit „Einplanen“ (in der Sammlung) oder „+“ (am Tag) kommt ein Rezept aus der Sammlung auf einen Tag, das Kreuz nimmt es wieder heraus. „Zutaten der Woche auf die Einkaufsliste“ überträgt die Zutaten aller Rezepte der Woche. Ein Rezept, das an zwei Tagen geplant ist, kommt zweimal auf die Liste. Rezepte „Ohne Tag“ bleiben dabei außen vor. Wurde die Woche schon übertragen (auf irgendeinem Gerät), fragt EatFresh vorher nach und nennt den Zeitpunkt, denn sonst zählen die Mengen doppelt. Grundlage ist der Essensplan von KitchenOwl.

### Kalender und Sensor

Das Gerät „EatFresh“ hat zwei Entitäten:

- Kalender **Wochenplan**: ein ganztägiger Termin je geplantem Rezept.
- Sensor **Heute**: die Namen der heutigen Gerichte mit Komma, sonst unbekannt. Das Attribut `recipes` enthält je Gericht `kitchenowl_id`, `name` und `image`.

EatFresh holt den Essensplan alle 15 Minuten und nach jeder Änderung in EatFresh. Ist KitchenOwl nicht erreichbar, sind beide Entitäten nicht verfügbar. Lehnt KitchenOwl den Zugangsschlüssel ab, fragt Home Assistant nach einem neuen.

### Karten fürs Dashboard

EatFresh lädt zwei Karten automatisch auf allen Dashboards. Antippen öffnet das Rezept in EatFresh.

```yaml
type: custom:eatfresh-week-card
title: Wochenplan
days: 7
```

```yaml
type: custom:eatfresh-today-card
title: Heute gibt es
```

`title` und `days` sind freiwillig.

### Aktionen

- `eatfresh.import_recipe` mit `url`: Rezept in KitchenOwl speichern. Antwort: `kitchenowl_id`, `title`, `created`.
- `eatfresh.add_recipe_to_shopping_list` mit `recipe_id`: Zutaten auf die Einkaufsliste. Antwort: `added`.

### Lizenz

EatFresh steht unter der MIT-Lizenz, siehe [`LICENSE`](LICENSE). Die Panel-Datei enthält gebündelte Pakete Dritter (Lit, Material Design Icons). Deren Lizenzhinweise stehen in [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md).

## English

EatFresh is a Home Assistant integration. It searches selected recipe websites, shows the results in its own sidebar panel and saves recipes with a heart in [KitchenOwl](https://kitchenowl.org). One tap puts the ingredients on your KitchenOwl shopping list.

### Installation with HACS

1. Open HACS, choose the menu in the top right corner, then **Custom repositories**.
2. Add `https://github.com/DanielWeeber/homeassistant-eatfresh` with type **Integration**.
3. Download EatFresh and restart Home Assistant.

Minimum version: Home Assistant 2026.11. Tested with KitchenOwl 0.8.1. KitchenOwl downloads the photo of a recipe itself from the recipe page.

### Setup

1. **Settings > Devices & services > Add integration > EatFresh**.
2. Enter the KitchenOwl address (for example `https://kitchenowl.example.com`) and a long-lived access token from KitchenOwl.
3. Choose the household and the shopping list.

"EatFresh" then appears in the sidebar. Use **Configure** to choose the recipe sources.

### Sources

- Gaumenfreundin, Emmi kocht einfach, Küchengötter: on by default.
- "Recipe link" button in the top right corner: opens the "Paste a recipe link" window. Always available, for any page with recipe data (schema.org/Recipe).
- Chefkoch: **off** by default. The Chefkoch terms of use (section 5.1) restrict automated access. You can only turn it on with an extra checkbox. You use it at your own responsibility. While Chefkoch is off, EatFresh blocks the source by its known host names.

The search limit applies **per source**: a search returns at most 20 hits from each source (up to 50 with `limit` in the WebSocket command `eatfresh/search`). With three sources you get up to 60 hits, mixed.

### Gentle on websites

EatFresh only loads recipe pages when you search or open a recipe, never in the background. Only one request per website runs at a time, with a pause between requests. Search results are cached for one hour, recipes for 24 hours. When a site refuses (403, 429, captcha), EatFresh does not retry.

### Collection, categories and hiding

- The collection shows the recipes stored in KitchenOwl. Tap a recipe to open it as stored in KitchenOwl. The recipe page is not loaded for this.
- Categories: Starter, Main course, Dessert, Vegetarian, Vegan, Pasta, Soup, Salad, Baking, Breakfast. When you set a heart, EatFresh suggests categories from what the recipe page says (tags, keywords) and from the title. Only these categories become tags in KitchenOwl. Vegetarian and Vegan are only suggested when a whole tag of the recipe page says exactly that (`Vegetarian`, `vegan recipes`) or the recipe data names it as the diet. Never from the ingredients, never from the title and never from parts of longer tags (`vegan alternatives`, `can be made vegetarian`). It stays a suggestion: please check before anyone relies on it.
- In the collection you can change the categories of a recipe and add your own. Chips filter the collection. Several selected chips mean: the recipe has all of them. Categories in the other language (`Suppe` and `Soup`) are the same chip.
- A recipe link is saved only once, however it is written (with or without `www.`, with additions such as `utm_…` or `fbclid`, as an AMP page). For pasted links EatFresh uses the canonical address of the page.
- **Hide:** the recipe disappears from the EatFresh collection only. It stays in KitchenOwl. "Show hidden" and "Show again" undo it, and so does a new heart. Hidden recipes do not count as favourites in search and recipe view. Nothing is deleted.

### Week plan

The "Week plan" tab shows Monday to Sunday (time zone of Home Assistant). "Plan" (in the collection) or "+" (on a day) puts a recipe from the collection on a day, the cross takes it off again. "Add the week’s ingredients to the shopping list" sends the ingredients of all recipes of the week. A recipe planned on two days goes on the list twice. Recipes under "No day" are left out. If the week was already sent (on any device), EatFresh asks first and says when, because the amounts would count twice. The data is the meal plan of KitchenOwl.

### Calendar and sensor

The device "EatFresh" has two entities:

- Calendar **Week plan**: one all-day event per planned recipe.
- Sensor **Today**: the names of today's meals separated by commas, otherwise unknown. The attribute `recipes` holds `kitchenowl_id`, `name` and `image` of each meal.

EatFresh fetches the meal plan every 15 minutes and after every change made in EatFresh. If KitchenOwl cannot be reached, both entities are unavailable. If KitchenOwl rejects the access token, Home Assistant asks for a new one.

### Dashboard cards

EatFresh loads two cards on all dashboards automatically. Tapping a recipe opens it in EatFresh.

```yaml
type: custom:eatfresh-week-card
title: Week plan
days: 7
```

```yaml
type: custom:eatfresh-today-card
title: Today’s menu
```

`title` and `days` are optional.

### Actions

- `eatfresh.import_recipe` with `url`: save a recipe in KitchenOwl. Response: `kitchenowl_id`, `title`, `created`.
- `eatfresh.add_recipe_to_shopping_list` with `recipe_id`: put the ingredients on the shopping list. Response: `added`.

### License

EatFresh is licensed under the MIT License, see [`LICENSE`](LICENSE). The panel file bundles third-party packages (Lit, Material Design Icons). Their license notices are in [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md).

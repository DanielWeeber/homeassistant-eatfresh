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

Danach erscheint „EatFresh“ in der Seitenleiste. Unter **Konfigurieren** wählst du die Rezeptquellen und wie oft EatFresh den Essensplan abgleicht (1 bis 60 Minuten, Standard: jede Minute).

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
- **Per Link geöffnet, von selbst gespeichert:** Ein Rezept, das du über den Knopf „Rezept-Link“ (oder mit einem Link im Suchfeld) öffnest, landet ohne weiteres Antippen in deiner Sammlung. Der Hinweis „In der Sammlung gespeichert.“ nennt die vorgeschlagenen Kategorien und bietet „Ändern“ für die Kategorien und „Rückgängig“ an. „Rückgängig“ nimmt das Herz zurück und blendet das Rezept aus; in KitchenOwl bleibt es. Lag das Rezept schon in der Sammlung, steht im Hinweis „Lag schon in der Sammlung.“ (ein ausgeblendetes Rezept erscheint dann wieder), und es gibt nichts rückgängig zu machen. Klappt das Speichern nicht, bleibt das Rezept sichtbar, mit Fehlermeldung und „Nochmal“. Neuladen und „Zurück“ speichern nichts noch einmal. Rezepte aus Suchtreffern speicherst du weiterhin nur mit dem Herz.
- **Ausblenden:** Das Rezept verschwindet nur aus der Sammlung in EatFresh. In KitchenOwl bleibt es. „Ausgeblendete anzeigen“ und „Wieder einblenden“ machen es rückgängig, ein neues Herz ebenso. Ausgeblendete Rezepte zählen in Suche und Rezeptansicht nicht als Favorit. Gelöscht wird nichts.

### Wochenplan

Der Reiter „Wochenplan“ zeigt Montag bis Sonntag (Zeitzone von Home Assistant). Mit „Einplanen“ (in der Sammlung) oder „+“ (am Tag) kommt ein Rezept aus der Sammlung auf einen Tag, das Kreuz nimmt es wieder heraus. „Zutaten der Woche auf die Einkaufsliste“ überträgt die Zutaten aller Rezepte der Woche. Ein Rezept, das an zwei Tagen geplant ist, kommt zweimal auf die Liste. Rezepte „Ohne Tag“ bleiben dabei außen vor. Wurde die Woche schon übertragen (auf irgendeinem Gerät), fragt EatFresh vorher nach und nennt den Zeitpunkt, denn sonst zählen die Mengen doppelt. Grundlage ist der Essensplan von KitchenOwl.

### Kalender und Sensor

Das Gerät „EatFresh“ hat zwei Entitäten:

- Kalender **Wochenplan**: ein ganztägiger Termin je geplantem Rezept.
- Sensor **Heute**: die Namen der heutigen Gerichte mit Komma, sonst unbekannt. Das Attribut `recipes` enthält je Gericht `kitchenowl_id`, `name` und `image`. Das Attribut `week` listet die Gerichte von heute bis in sechs Tagen nach Datum, je Gericht `date`, `recipe_id` und `name`.

EatFresh holt den Essensplan jede Minute (einstellbar unter **Konfigurieren**) und sofort nach jeder Änderung in EatFresh. Eine Änderung in der KitchenOwl-App ist so nach etwa einer Minute in Kalender, Sensor und Karten zu sehen. Jeder Abgleich ist eine einzige Anfrage an KitchenOwl. Ist KitchenOwl nicht erreichbar, sind beide Entitäten nicht verfügbar. Lehnt KitchenOwl den Zugangsschlüssel ab, fragt Home Assistant nach einem neuen.

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
- `eatfresh.search_collection` mit `query` und `limit` (beide freiwillig): Sammlung nach Name oder Zutat durchsuchen, Groß- und Kleinschreibung egal. Ohne `query` kommt die ganze Sammlung, ausgeblendete Rezepte fehlen. `limit` begrenzt die Zahl der Rezepte in der Antwort (1 bis 200, Standard 50). Antwort: `recipes` mit `recipe_id`, `name`, `time`, `yields`, `tags` und `planned_dates` (Tage als `YYYY-MM-DD`), dazu `total` (Zahl aller Treffer). Ist nur der Essensplan nicht ladbar, bleibt `planned_dates` leer.
- `eatfresh.get_planner` mit `start_date` (freiwillig, Standard heute) und `days` (1 bis 31, Standard 7): Essensplan lesen. Antwort: `start_date`, `days`, `entries` mit `date`, `recipe_id`, `name` sowie `unscheduled` (Rezepte ohne Tag) mit `recipe_id`, `name`.
- `eatfresh.plan_recipe` mit `recipe_id` und `date`: Rezept an einem Tag einplanen. Antwort: `recipe_id`, `date`.
- `eatfresh.unplan_recipe` mit `recipe_id` und `date` (freiwillig): Rezept von einem Tag nehmen, ohne `date` den Eintrag ohne Tag. Das Rezept selbst bleibt. Antwort: `recipe_id`, `date`.

`recipe_id` ist die ID in KitchenOwl. Es gehen nur Rezepte der eigenen Sammlung. Kalender und Sensor zeigen eine Änderung sofort. `search_collection` und `get_planner` brauchen eine Antwortvariable (`response_variable`).

Beispiel: ein Skript, das ein Nudelgericht für morgen einplant und die nächsten drei Tage meldet.

```yaml
alias: Nudeln für morgen
sequence:
  - action: eatfresh.search_collection
    data:
      query: nudeln
    response_variable: found
  - if: '{{ found.recipes | count > 0 }}'
    then:
      - action: eatfresh.plan_recipe
        data:
          recipe_id: '{{ found.recipes[0].recipe_id }}'
          date: '{{ (now() + timedelta(days=1)).date().isoformat() }}'
      - action: eatfresh.get_planner
        data:
          days: 3
        response_variable: plan
      - action: persistent_notification.create
        data:
          message: |-
            {% for item in plan.entries %}{{ item.date }}: {{ item.name }}
            {% endfor %}
```

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

"EatFresh" then appears in the sidebar. Use **Configure** to choose the recipe sources and how often EatFresh fetches the meal plan (1 to 60 minutes, default: every minute).

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
- **Opened by link, saved by itself:** A recipe you open with the "Recipe link" button (or with a link in the search field) is saved to your collection without another tap. The notice "Saved to your collection." shows the suggested categories, with "Change" for the categories and "Undo". "Undo" takes the heart off and hides the recipe; it stays in KitchenOwl. If the recipe was in the collection already, the notice says "Was already in your collection." (and shows a hidden recipe again); then there is nothing to undo. If saving fails, the recipe stays on screen with a message and "Try again". Reloading the page and going back do not save again. Recipes from search results are still saved only with the heart.
- **Hide:** the recipe disappears from the EatFresh collection only. It stays in KitchenOwl. "Show hidden" and "Show again" undo it, and so does a new heart. Hidden recipes do not count as favourites in search and recipe view. Nothing is deleted.

### Week plan

The "Week plan" tab shows Monday to Sunday (time zone of Home Assistant). "Plan" (in the collection) or "+" (on a day) puts a recipe from the collection on a day, the cross takes it off again. "Add the week’s ingredients to the shopping list" sends the ingredients of all recipes of the week. A recipe planned on two days goes on the list twice. Recipes under "No day" are left out. If the week was already sent (on any device), EatFresh asks first and says when, because the amounts would count twice. The data is the meal plan of KitchenOwl.

### Calendar and sensor

The device "EatFresh" has two entities:

- Calendar **Week plan**: one all-day event per planned recipe.
- Sensor **Today**: the names of today's meals separated by commas, otherwise unknown. The attribute `recipes` holds `kitchenowl_id`, `name` and `image` of each meal. The attribute `week` lists the meals from today to six days ahead by date, each with `date`, `recipe_id` and `name`.

EatFresh fetches the meal plan every minute (adjustable under **Configure**) and right after every change made in EatFresh. A change made in the KitchenOwl app shows up in the calendar, the sensor and the cards after about a minute. Each fetch is a single request to KitchenOwl. If KitchenOwl cannot be reached, both entities are unavailable. If KitchenOwl rejects the access token, Home Assistant asks for a new one.

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
- `eatfresh.search_collection` with `query` and `limit` (both optional): search the collection by name or ingredient, ignoring case. Without `query` the whole collection comes back; hidden recipes are left out. `limit` caps the number of recipes in the response (1 to 200, default 50). Response: `recipes` with `recipe_id`, `name`, `time`, `yields`, `tags` and `planned_dates` (days as `YYYY-MM-DD`), plus `total` (number of all matches). If only the meal plan cannot be loaded, `planned_dates` stays empty.
- `eatfresh.get_planner` with `start_date` (optional, default today) and `days` (1 to 31, default 7): read the meal plan. Response: `start_date`, `days`, `entries` with `date`, `recipe_id`, `name`, and `unscheduled` (recipes without a day) with `recipe_id`, `name`.
- `eatfresh.plan_recipe` with `recipe_id` and `date`: plan a recipe on a day. Response: `recipe_id`, `date`.
- `eatfresh.unplan_recipe` with `recipe_id` and `date` (optional): take a recipe off a day; without `date` the entry without a day. The recipe itself stays. Response: `recipe_id`, `date`.

`recipe_id` is the id in KitchenOwl. Only recipes of the own collection are accepted. The calendar and the sensor show a change at once. `search_collection` and `get_planner` need a response variable (`response_variable`).

Example: a script that plans a pasta dish for tomorrow and reports the next three days.

```yaml
alias: Pasta for tomorrow
sequence:
  - action: eatfresh.search_collection
    data:
      query: pasta
    response_variable: found
  - if: '{{ found.recipes | count > 0 }}'
    then:
      - action: eatfresh.plan_recipe
        data:
          recipe_id: '{{ found.recipes[0].recipe_id }}'
          date: '{{ (now() + timedelta(days=1)).date().isoformat() }}'
      - action: eatfresh.get_planner
        data:
          days: 3
        response_variable: plan
      - action: persistent_notification.create
        data:
          message: |-
            {% for item in plan.entries %}{{ item.date }}: {{ item.name }}
            {% endfor %}
```

### License

EatFresh is licensed under the MIT License, see [`LICENSE`](LICENSE). The panel file bundles third-party packages (Lit, Material Design Icons). Their license notices are in [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md).

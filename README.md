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
- „Rezept-Link einfügen“: geht immer, für jede Seite mit Rezeptdaten (schema.org/Recipe).
- Chefkoch: standardmäßig **aus**. Die AGB von Chefkoch (Ziffer 5.1) schränken automatische Abrufe ein. Einschalten geht nur mit einem eigenen Häkchen. Die Nutzung liegt in deiner eigenen Verantwortung. Ist Chefkoch aus, sperrt EatFresh die Quelle über ihre bekannten Hostnamen.

### Sparsame Abrufe

EatFresh ruft Rezeptseiten nur ab, wenn du suchst oder ein Rezept öffnest, nie im Hintergrund. Je Webseite läuft höchstens ein Abruf gleichzeitig, mit Pause dazwischen. Suchergebnisse bleiben eine Stunde, Rezepte 24 Stunden im Zwischenspeicher. Lehnt eine Seite ab (403, 429, Captcha), versucht EatFresh es nicht noch einmal.

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
- "Paste recipe link": always available, for any page with recipe data (schema.org/Recipe).
- Chefkoch: **off** by default. The Chefkoch terms of use (section 5.1) restrict automated access. You can only turn it on with an extra checkbox. You use it at your own responsibility. While Chefkoch is off, EatFresh blocks the source by its known host names.

### Gentle on websites

EatFresh only loads recipe pages when you search or open a recipe, never in the background. Only one request per website runs at a time, with a pause between requests. Search results are cached for one hour, recipes for 24 hours. When a site refuses (403, 429, captcha), EatFresh does not retry.

### Actions

- `eatfresh.import_recipe` with `url`: save a recipe in KitchenOwl. Response: `kitchenowl_id`, `title`, `created`.
- `eatfresh.add_recipe_to_shopping_list` with `recipe_id`: put the ingredients on the shopping list. Response: `added`.

### License

EatFresh is licensed under the MIT License, see [`LICENSE`](LICENSE). The panel file bundles third-party packages (Lit, Material Design Icons). Their license notices are in [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md).

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

Danach erscheint „EatFresh“ in der Seitenleiste. Unter **Konfigurieren** wählst du die Rezeptquellen, wie oft EatFresh den Essensplan abgleicht (1 bis 60 Minuten, Standard: jede Minute), die „Standard-Portionen“ (1 bis 12, Standard: 3) und ob EatFresh „Kategorien in KitchenOwl eintragen“ darf (Standard: an).

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
- **Zutaten gehen nicht verloren:** EatFresh merkt sich die Zutaten jedes Rezepts selbst. Löscht jemand in KitchenOwl einen Artikel, nimmt KitchenOwl ihn aus allen Rezepten. In EatFresh bleibt die Zutat sichtbar, die Suche findet sie, und sie kommt weiter auf die Einkaufsliste (EatFresh trägt sie davor wieder in KitchenOwl ein). Im Rezept steht dann ein Hinweis mit „Wiederherstellen“ (trägt die Zutaten wieder in KitchenOwl ein) und „Aus Rezept entfernen“ (EatFresh vergisst sie; in KitchenOwl ändert sich nichts). Das gilt auch, wenn jemand in KitchenOwl eine Zutat absichtlich aus einem Rezept nimmt: EatFresh kann das nicht von einem gelöschten Artikel unterscheiden, zeigt sie weiter und trägt sie beim nächsten Übertrag auf die Einkaufsliste wieder ein (auch aus dem Wochenplan und über die Aktion `eatfresh.add_recipe_to_shopping_list`). Dauerhaft weg ist sie erst mit „Aus Rezept entfernen“. Das gilt auch, wenn im Rezept in KitchenOwl eine Zutat gegen eine andere getauscht wird: Die alte gilt dann als fehlend. Ein Rezept, das 30 Tage nicht mehr in KitchenOwl steht, vergisst EatFresh. Etwas auf der Einkaufsliste abzuhaken, ändert kein Rezept.

### Portionen

- Im Rezept der Sammlung steht ein Zähler mit den „Portionen“. Mit **−** und **+** wählst du 1 bis 99. Die Mengen der Zutaten rechnen sich um.
- Ein Rezept öffnet mit den „Standard-Portionen“ (Option, Standard: 3), wenn es in KitchenOwl für 2 bis 8 Portionen gedacht ist. Steht dort 1 oder mehr als 8, öffnet es mit dieser Zahl, denn gemeint ist oft ein ganzer Kuchen oder eine Menge Stück. Hat das Rezept in KitchenOwl keine Portionsangabe oder mehr als 99, gibt es keinen Zähler, und die Mengen bleiben unverändert. EatFresh merkt sich deine Wahl nicht: Jedes Rezept öffnet wieder mit dem Startwert. Weicht die Zahl vom Rezept ab, steht darunter klein die Zahl aus dem Rezept.
- Mengen werden auf glatte Werte gerundet: g und ml in Schritten (1 unter 20, 5 unter 250, 10 unter 1000, 50 ab 1000), kg und l in Schritten von 0,05 (unter 1 wird daraus g oder ml), EL, TL, Tasse und andere Maße in halben Schritten, Prisen ganz. Unteilbares (Dose, Packung, Becher, Glas, Bund, Zehe, Stück, Ei) wird auf ganze Stück **aufgerundet**, denn 1,5 Dosen kann man nicht kaufen. Liegt die Zahl bis 0,1 über einer ganzen Zahl, rundet EatFresh ab (2,08 wird 2). Weicht die ganze Zahl um mehr als 0,01 von der genauen ab, steht hinter der Menge dezent „gerechnet“ mit der genauen Zahl.
- Als Menge liest EatFresh auch Bereiche und Brüche (`2-3`, `1/2`), ein Dezimalkomma (`1,5 kg`), einen Tausenderpunkt (`1.000 g`) und eine Einheit ohne Zahl (`Bund` zählt als 1 und wird zu `3 Bund`, nur `Prise` bleibt `Prise`). Ein einzelnes Wort nach der Zahl zählt als Stück (`3 Eier`). Weitere Wörter nach einer bekannten Einheit bleiben stehen, nur die Zahl ändert sich (`2 EL gehäuft`).
- **Das Rezept in KitchenOwl bleibt unverändert.** EatFresh schreibt wegen der Portionen weder die Portionsangabe noch Zutaten eines Rezepts.
- Auf die Einkaufsliste kommen die umgerechneten Mengen. Was EatFresh nicht als Menge lesen kann, bleibt wie es ist.

### Wochenplan

Der Reiter „Wochenplan“ zeigt Montag bis Sonntag (Zeitzone von Home Assistant). Mit „Einplanen“ (in der Sammlung) oder „+“ (am Tag) kommt ein Rezept aus der Sammlung auf einen Tag, das Kreuz nimmt es wieder heraus. „Zutaten der Woche auf die Einkaufsliste“ überträgt die Zutaten aller Rezepte der Woche. Ein Rezept, das an zwei Tagen geplant ist, kommt zweimal auf die Liste. Rezepte „Ohne Tag“ bleiben dabei außen vor. Wurde die Woche schon übertragen (auf irgendeinem Gerät), fragt EatFresh vorher nach und nennt den Zeitpunkt, denn sonst zählen die Mengen doppelt. Grundlage ist der Essensplan von KitchenOwl.

Jeder Eintrag mit Tag hat eigene Portionen und einen kleinen Zähler mit **−** und **+**. „Einplanen“ nimmt die Zahl aus dem geöffneten Rezept mit. KitchenOwl speichert die Portionen je Eintrag. Beim Übertrag auf die Einkaufsliste gilt je Eintrag seine Zahl. Ein Eintrag ohne Zahl nimmt den Startwert des Rezepts, und ohne Portionsangabe im Rezept gibt es keinen Zähler. Steht die Woche schon auf der Liste, meldet EatFresh nach einer Änderung: „Die Woche steht schon auf der Einkaufsliste. Die Liste ändert sich dadurch nicht.“ Ein Rezept, das du aus dem Wochenplan öffnest, öffnet mit der Zahl des Eintrags.

KitchenOwl ändert die Zahl eines vorhandenen Eintrags nicht direkt. Deshalb nimmt EatFresh ihn heraus und legt ihn mit der neuen Zahl wieder an. Klappt das Anlegen nicht, kommt er mit der alten Zahl zurück. Scheitert auch das, meldet EatFresh, dass der Eintrag fehlt, und du planst das Rezept neu ein. Steht dasselbe Rezept zusätzlich „Ohne Tag“ im Plan, lassen sich die Portionen nicht ändern, denn KitchenOwl würde den Eintrag ohne Tag dabei entfernen. Plane ihn zuerst an einem Tag ein oder nimm ihn heraus.

### Einkauf

Der Reiter „Einkauf“ zeigt die Einkaufsliste aus KitchenOwl, in Kategorien sortiert und zum Abhaken. Wer bei Picnic einkauft, kann von dort außerdem Produkte in den Picnic-Warenkorb legen.

- **Kategorien:** Die Zutaten stehen in Gruppen wie Obst und Gemüse, Milchprodukte oder Gewürze, in der Reihenfolge eines Supermarkts, Unbekanntes unter Sonstiges. Zuerst gilt die Kategorie, die der Artikel in KitchenOwl schon hat. Hat er keine, sortiert EatFresh nach dem Namen. Mit „Kategorie ändern“ im Menü eines Eintrags schiebst du ihn in eine andere Gruppe. Diese Wahl gilt für die Zutat, bis du sie wieder änderst.
- **Abhaken:** Der runde Knopf links hakt einen Eintrag ab. EatFresh liest dafür die Liste und nimmt den Eintrag sofort von der Einkaufsliste in KitchenOwl, wenn er dort steht. Unter „Erledigt“ steht er noch 3 Tage (mit dem Hinweis „verschwindet nach“ und der Zahl der Tage), dort bringt „Zurück auf die Liste“ ihn zurück. Die Mengen zählen dabei zusammen, wenn der Artikel inzwischen wieder auf der Liste steht. Ohne Picnic ist der Reiter einfach eine Liste zum Abhaken.
- **Was EatFresh in KitchenOwl schreibt:** Kategorien, solange „Kategorien in KitchenOwl eintragen“ an ist. Das passiert, wenn du „Kategorie ändern“ nutzt, und nach einem Übertrag auf die Liste für die übertragenen Artikel, die noch keine Kategorie haben (höchstens 40, im Hintergrund, ein Fehler hält den Übertrag nicht auf). Fehlt die Kategorie, legt EatFresh sie an. Eine Kategorie, die ein Artikel schon hat, ändert EatFresh nie von selbst. Schiebst du einen Eintrag nach Sonstiges, leert EatFresh seine Kategorie in KitchenOwl. Ist die Option aus, ändert EatFresh dort keine Kategorie.
- **Was EatFresh von der Liste nimmt:** abgehakte Einträge sofort, Einträge im Picnic-Warenkorb 3 Tage nach dem Senden, aber nur, wenn ihr Mengentext noch derselbe ist wie beim Senden. Einträge, die aus Version 0.4 stammen (dort wurde kein Mengentext gemerkt), nimmt EatFresh nie von der Liste, ihre Markierung fällt nach 3 Tagen weg. Das passiert beim Öffnen des Reiters und vor einem Übertrag auf die Liste, nie nach der Uhr im Hintergrund. **EatFresh löscht nie einen Artikel und nie ein Rezept.** Ein Artikel, der von der Liste geht, bleibt in KitchenOwl und in seinen Rezepten.
- **Voraussetzung für Picnic:** In Home Assistant ist die Picnic-Integration eingerichtet und angemeldet. EatFresh bekommt keine eigenen Picnic-Zugangsdaten, es nutzt die Picnic-Integration. Ohne sie läuft der Reiter ohne die Picnic-Teile.
- **Wer es benutzen kann:** Jeder angemeldete Nutzer von Home Assistant kann den Reiter „Einkauf“ benutzen und damit Produkte suchen, in den Picnic-Warenkorb legen und wieder herausnehmen, auch Kinder oder Gäste mit eigenem Zugang. EatFresh prüft dabei keine Rechte, und Home Assistant kann den Reiter nicht für einzelne Nutzer sperren. Wer das nicht möchte, richtet die Picnic-Integration nicht ein.
- **Produkt wählen:** Für jede Zutat suchst du einmal mit der Lupe beim Eintrag ein Picnic-Produkt aus (Name, Packungsgröße, Preis). Auf breiten Bildschirmen steht „Produkt wählen“ neben der Lupe. EatFresh merkt sich die Wahl. Die Stückzahl ist ein Vorschlag aus Menge und Packungsgröße und lässt sich ändern. Steht auf der Liste eine Zahl mit Packungs-Einheit (`2 Dose`), heißt sie Packungen des Produkts, auch wenn dieses in Stück angegeben ist. Eine Stückzahl, die du selbst änderst, merkt sich EatFresh fest für die Zutat. „Nie bei Picnic“ nimmt eine Zutat dauerhaft aus. „Ausgenommene anzeigen“ zeigt sie wieder, „Wieder aufnehmen“ holt sie zurück.
- **Warenkorb füllen:** „In den Picnic-Warenkorb“ legt die angehakten Produkte nacheinander in den Warenkorb, mit kurzer Pause dazwischen. Vorher fragt EatFresh noch einmal nach. Vor dem ersten Produkt liest EatFresh den Picnic-Warenkorb einmal, damit es weiß, wie viele Stücke schon darin liegen. Klappt das nicht, legt EatFresh nichts hinein und sagt das. Nach jedem Produkt liest EatFresh den Warenkorb aus der Antwort von Picnic. Nur wenn das Produkt dort in der erwarteten Stückzahl liegt (Stücke, die schon vorher darin lagen, mitgezählt), zeigt der Eintrag „Im Warenkorb“. Zeilen im Warenkorb ohne erkennbare Stückzahl stören die anderen Produkte nicht. Steht das gewählte Produkt selbst in so einer Zeile, legt EatFresh es nicht hinein. Die Einträge bleiben 3 Tage auf der KitchenOwl-Liste, danach nimmt EatFresh sie herunter, aber nur, wenn ihr Mengentext noch derselbe ist wie beim Senden. Hat ein späterer Übertrag dazugezählt, gilt der Eintrag sofort wieder als offen, mit dem Hinweis „Schon im Warenkorb“ und der Menge, die hineinging. Er ist dann nicht zum Senden vorgewählt, damit nichts doppelt im Warenkorb landet. Dann lässt er sich noch einmal senden.
- **Kleinere Packung:** Braucht die letzte Packung nur einen kleinen Rest (höchstens 60 % ihres Inhalts), steht beim Eintrag, dass für den Rest eine kleinere Packung reicht. „Kleinere Packung wählen“ öffnet die Produktsuche, Treffer mit „reicht für den Rest“ stehen oben. EatFresh merkt sich die Wahl wie das Hauptprodukt, der Eintrag bekommt eine zweite Zeile mit eigener Stückzahl, und „Kleinere Packung entfernen“ nimmt sie wieder weg. Beim Senden gehen beide Produkte nacheinander in den Warenkorb. Klappt das zweite nicht, bleibt das erste im Warenkorb, und EatFresh meldet den Fehler. „Rückgängig“ nimmt beide heraus. Der Vorschlag kommt aus den Mengen, die EatFresh selbst auf die Liste gesetzt hat. Hat jemand die Liste von Hand geändert, gibt es keinen Vorschlag, und mit einer festen, gemerkten Stückzahl auch nicht. Neben der Menge steht „gerechnet“ mit der genauen Zahl, wenn die Zahl auf der Liste von der genauen abweicht (zum Beispiel weil bei den Portionen aufgerundet wurde).
- **Beim ersten Fehler hört EatFresh auf:** Antwortet Picnic nicht, nicht rechtzeitig oder nicht lesbar, lehnt es die Anmeldung ab oder legt es ein Produkt nicht in den Warenkorb (zum Beispiel, weil es nicht lieferbar ist), schickt EatFresh nichts mehr an Picnic. Die übrigen Produkte werden nicht versucht und bleiben angehakt. Auch eine fehlgeschlagene Suche wiederholt EatFresh nicht von selbst.
- **Vielleicht im Warenkorb:** Antwortet Picnic nicht rechtzeitig oder nicht eindeutig, kann das Produkt trotzdem im Warenkorb liegen. Der Eintrag zeigt dann „Vielleicht im Warenkorb: Picnic hat nicht eindeutig geantwortet. Sieh in der Picnic-App nach und nimm es bei Bedarf dort heraus.“ EatFresh legt ihn nicht von selbst noch einmal hinein und nimmt ihn auch nicht heraus. Nach 3 Tagen fällt die Markierung weg, der Eintrag bleibt auf der Liste. Liegt er nicht im Warenkorb, tippe auf „Ist nicht im Warenkorb“, dann kannst du ihn noch einmal senden. Das passiert auch, wenn sich der Warenkorb verändert hat, das Produkt aber nicht in der erwarteten Stückzahl darin steht, zum Beispiel weil Picnic es im Warenkorb unter einer anderen Nummer führt als in der Suche. Dass ein Produkt sicher nicht hineingelegt wurde, meldet EatFresh nur, wenn Picnic ausdrücklich abgelehnt hat oder der Warenkorb ganz unverändert geblieben ist.
- **Rückgängig:** „Rückgängig“ gibt es nur bei „Im Warenkorb“, und die Markierung gilt 3 Tage. Es nimmt die Stückzahl heraus, die EatFresh hineingelegt hat, nie mehr. Picnic zieht diese Zahl einfach ab: Hast du das Produkt inzwischen in der Picnic-App geändert, nimm es lieber dort heraus, sonst können auch Stücke wegfallen, die du selbst hineingelegt hast. Vorher liest EatFresh den Warenkorb einmal. Liegen dort weniger Stücke, als EatFresh hineingelegt hat, nimmt es nichts heraus, und der Eintrag zeigt „Vielleicht im Warenkorb“. Ist die Antwort auf „Rückgängig“ unklar oder ist die Stückzahl darin nicht um die gesendete Zahl gesunken, zeigt der Eintrag ebenfalls „Vielleicht im Warenkorb“, und EatFresh nimmt nichts mehr heraus.
- **Es wird nie bestellt.** EatFresh bucht kein Lieferfenster und bezahlt nichts. Bestellen machst du selbst in der Picnic-App. Prüfe den Warenkorb vor jeder Bestellung in der Picnic-App. Ändere während des Sendens nichts in der Picnic-App, sonst kann EatFresh den Stand des Warenkorbs falsch einschätzen.
- **Sparsam:** EatFresh ruft Picnic nur auf, wenn du suchst, den Warenkorb füllst oder etwas rückgängig machst, nie im Hintergrund. Ein Lauf liest den Warenkorb einmal und legt dann jedes Produkt mit einem eigenen Aufruf hinein. „Rückgängig“ liest den Warenkorb einmal und nimmt dann heraus. Es läuft immer nur ein Aufruf: Hängt einer, wartet EatFresh, bis er zu Ende ist, bevor der nächste an Picnic geht. Bleibt Picnic in EatFresh deshalb lange beschäftigt, hilft ein Neustart von Home Assistant. Lehnt Picnic die Anmeldung ab, in Home Assistant die Picnic-Integration neu anmelden.
- **Eigene Verantwortung:** Die Picnic-Integration nutzt eine nicht öffentliche Schnittstelle der Picnic-App. Picnic kann sie jederzeit ändern, dann gehen Suche oder Warenkorb nicht mehr, bis die Integration angepasst ist. Automatische Zugriffe können gegen die AGB von Picnic verstoßen. Bitte lies die AGB von Picnic und entscheide selbst, ob und mit welchem Konto du das nutzt.

### Kalender und Sensor

Das Gerät „EatFresh“ hat zwei Entitäten:

- Kalender **Wochenplan**: ein ganztägiger Termin je geplantem Rezept.
- Sensor **Heute**: die Namen der heutigen Gerichte mit Komma, sonst unbekannt. Das Attribut `recipes` enthält je Gericht `kitchenowl_id`, `name`, `image` und `servings` (die Portionen des Eintrags, sonst der Startwert des Rezepts, sonst unbekannt). Das Attribut `week` listet die Gerichte von heute bis in sechs Tagen nach Datum, je Gericht `date`, `recipe_id`, `name` und `servings`.

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
- `eatfresh.add_recipe_to_shopping_list` mit `recipe_id` und `servings` (freiwillig, 1 bis 99): Zutaten auf die Einkaufsliste, auf `servings` umgerechnet. Antwort: `added`.
- `eatfresh.search_collection` mit `query`, `limit` und `name_only` (alle freiwillig): Sammlung nach Name oder Zutat durchsuchen, Groß- und Kleinschreibung egal. Mit `name_only: true` trifft `query` nur den Namen, nicht die Zutaten (Standard `false`). Ohne `query` kommt die ganze Sammlung, ausgeblendete Rezepte fehlen. `limit` begrenzt die Zahl der Rezepte in der Antwort (1 bis 200, Standard 50). Antwort: `recipes` mit `recipe_id`, `name`, `time`, `yields`, `tags` und `planned_dates` (Tage als `YYYY-MM-DD`), dazu `total` (Zahl aller Treffer). Ist nur der Essensplan nicht ladbar, bleibt `planned_dates` leer.
- `eatfresh.get_planner` mit `start_date` (freiwillig, Standard heute) und `days` (1 bis 31, Standard 7): Essensplan lesen. Antwort: `start_date`, `days`, `entries` mit `date`, `recipe_id`, `name`, `servings` sowie `unscheduled` (Rezepte ohne Tag) mit `recipe_id`, `name`, `servings`.
- `eatfresh.plan_recipe` mit `recipe_id`, `date` und `servings` (freiwillig, 1 bis 99): Rezept an einem Tag einplanen, für `servings` Portionen. Antwort: `recipe_id`, `date`.
- `eatfresh.unplan_recipe` mit `recipe_id` und `date` (freiwillig): Rezept von einem Tag nehmen, ohne `date` den Eintrag ohne Tag. Das Rezept selbst bleibt. Antwort: `recipe_id`, `date`.

`recipe_id` ist die ID in KitchenOwl. Ohne `servings` gilt der Startwert des Rezepts (siehe „Portionen“): Die Mengen auf der Liste sind dann auf diese Zahl umgerechnet und nicht mehr die Mengen des Rezepts unverändert. Hat das Rezept in KitchenOwl keine Portionsangabe (oder mehr als 99), werden `servings` ignoriert, und die Mengen bleiben unverändert. `servings` ist eine ganze Zahl von 1 bis 99. Die Aktionen nehmen auch `3.0`, aber nicht `2.5`. Es gehen nur Rezepte der eigenen Sammlung. Kalender und Sensor zeigen eine Änderung sofort. `search_collection` und `get_planner` brauchen eine Antwortvariable (`response_variable`).

Beispiel: ein Skript, das ein Nudelgericht für morgen für vier Portionen einplant und die nächsten drei Tage meldet.

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
          servings: 4
      - action: eatfresh.get_planner
        data:
          days: 3
        response_variable: plan
      - action: persistent_notification.create
        data:
          message: |-
            {% for item in plan.entries %}{{ item.date }}: {{ item.name }} ({{ item.servings }})
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

"EatFresh" then appears in the sidebar. Use **Configure** to choose the recipe sources, how often EatFresh fetches the meal plan (1 to 60 minutes, default: every minute), the "Default servings" (1 to 12, default: 3) and whether EatFresh may "Write categories to KitchenOwl" (default: on).

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
- **Ingredients do not get lost:** EatFresh keeps its own copy of the ingredients of every recipe. When somebody deletes an article in KitchenOwl, KitchenOwl takes it out of all recipes. In EatFresh the ingredient stays visible, the search finds it, and it still goes to the shopping list (EatFresh puts it back into KitchenOwl first). The recipe then shows a notice with "Restore" (puts the ingredients back into KitchenOwl) and "Remove from recipe" (EatFresh forgets them; nothing changes in KitchenOwl). The same holds when somebody takes an ingredient out of a recipe in KitchenOwl on purpose: EatFresh cannot tell that from a deleted article, keeps showing it and puts it back with the next transfer to the shopping list (also from the week plan and through the action `eatfresh.add_recipe_to_shopping_list`). It is only gone for good after "Remove from recipe". This also applies when an ingredient is swapped for another one in the recipe in KitchenOwl: the old one then counts as missing. EatFresh forgets a recipe that has not been in KitchenOwl for 30 days. Ticking something off the shopping list changes no recipe.

### Servings

- The recipe of the collection has a counter with the "Servings". Use **−** and **+** to choose 1 to 99. The amounts of the ingredients are recalculated.
- A recipe opens with the "Default servings" (option, default: 3) if it is made for 2 to 8 servings in KitchenOwl. If it says 1 or more than 8, it opens with that number, because it often means a whole cake or a number of pieces. If the recipe has no servings in KitchenOwl or more than 99, there is no counter and the amounts stay as they are. EatFresh does not remember your choice: every recipe opens with the start value again. If the number differs from the recipe, the number from the recipe is shown below in small type.
- Amounts are rounded to round values: g and ml in steps (1 below 20, 5 below 250, 10 below 1000, 50 from 1000), kg and l in steps of 0.05 (below 1 they become g or ml), tbsp, tsp, cups and other measures in halves, pinches whole. Things you cannot split (can, pack, tub, jar, bunch, clove, piece, egg) are **rounded up** to whole pieces, because you cannot buy 1.5 cans. If the number is up to 0.1 above a whole number, EatFresh rounds down (2.08 becomes 2). If the whole number differs from the exact one by more than 0.01, "calculated" with the exact number is shown quietly behind the amount.
- EatFresh also reads ranges and fractions (`2-3`, `1/2`), a decimal comma (`1,5 kg`), a dot for thousands (`1.000 g`) and a unit without a number (`Bund` counts as 1 and becomes `3 Bund`; only `Prise` stays `Prise`). A single word after the number counts as pieces (`3 Eier`). More words after a known unit stay as they are, only the number changes (`2 EL gehäuft`).
- **The recipe in KitchenOwl stays unchanged.** EatFresh does not write the servings or the ingredients of a recipe because of the servings.
- The shopping list gets the recalculated amounts. What EatFresh cannot read as an amount stays as it is.

### Week plan

The "Week plan" tab shows Monday to Sunday (time zone of Home Assistant). "Plan" (in the collection) or "+" (on a day) puts a recipe from the collection on a day, the cross takes it off again. "Add the week’s ingredients to the shopping list" sends the ingredients of all recipes of the week. A recipe planned on two days goes on the list twice. Recipes under "No day" are left out. If the week was already sent (on any device), EatFresh asks first and says when, because the amounts would count twice. The data is the meal plan of KitchenOwl.

Every entry with a day has its own servings and a small counter with **−** and **+**. "Plan" takes the number from the open recipe along. KitchenOwl stores the servings per entry. When the week goes to the shopping list, each entry counts with its own number. An entry without a number takes the start value of its recipe, and without servings in the recipe there is no counter. If the week is already on the list, EatFresh says after a change: "The week is already on the shopping list. The list does not change." A recipe you open from the week plan opens with the number of the entry.

KitchenOwl does not change the number of an existing entry directly. So EatFresh takes the entry out and creates it again with the new number. If creating fails, the entry comes back with the old number. If that fails too, EatFresh says the entry is missing, and you plan the recipe again. If the same recipe is in the plan under "No day" as well, the servings cannot be changed, because KitchenOwl would remove the entry without a day. Plan it on a day first or take it out.

### Shopping

The tab "Shopping" shows the shopping list from KitchenOwl, sorted into categories and ready to tick off. If you shop at Picnic, you can also put products into the Picnic cart from there.

- **Categories:** the ingredients are in groups like fruit and vegetables, dairy or spices, in the order of a supermarket, unknown ones under Other. The category the article already has in KitchenOwl comes first. If it has none, EatFresh sorts by the name. "Change category" in the menu of an entry moves it to another group. This choice holds for the ingredient until you change it again.
- **Ticking off:** the round button on the left ticks an entry off. EatFresh reads the list for this and takes the entry off the shopping list in KitchenOwl at once, if it is there. It stays under "Done" for 3 more days (with the note "goes away after" and the number of days), where "Back on the list" brings it back. The amounts add up if the article is on the list again by then. Without Picnic the tab is simply a list to tick off.
- **What EatFresh writes to KitchenOwl:** categories, as long as "Write categories to KitchenOwl" is on. This happens when you use "Change category", and after a transfer to the list for the transferred articles that have no category yet (at most 40, in the background; an error does not stop the transfer). If the category is missing, EatFresh creates it. EatFresh never changes a category an article already has by itself. If you move an entry to Other, EatFresh clears its category in KitchenOwl. If the option is off, EatFresh changes no category there.
- **What EatFresh takes off the list:** ticked entries at once, entries in the Picnic cart 3 days after sending, but only if their amount text is still the one sent. Entries from version 0.4 (no amount text was remembered then) are never taken off the list; their mark goes away after 3 days. This happens when you open the tab and before a transfer to the list, never by the clock in the background. **EatFresh never deletes an article and never deletes a recipe.** An article that leaves the list stays in KitchenOwl and in its recipes.
- **Requirement for Picnic:** the Picnic integration is set up and signed in in Home Assistant. EatFresh gets no Picnic credentials of its own; it uses the Picnic integration. Without it the tab works without the Picnic parts.
- **Who can use it:** every signed-in user of Home Assistant can use the tab "Shopping" to search products, put them into the Picnic cart and take them out again, children or guests with their own login too. EatFresh checks no permissions, and Home Assistant cannot lock the tab for single users. If you do not want that, do not set up the Picnic integration.
- **Choose a product:** for each ingredient you pick a Picnic product once with the magnifier at the entry (name, pack size, price). On wide screens "Choose product" stands next to the magnifier. EatFresh remembers the choice. The quantity is a suggestion from the amount and the pack size and can be changed. A number with a pack unit on the list (`2 Dose`) means packs of the product, even if the product is given in pieces. A quantity you change yourself is remembered for the ingredient as a fixed one. "Never at Picnic" leaves an ingredient out for good. "Show excluded" shows it again, "Include again" brings it back.
- **Fill the cart:** "Add to Picnic cart" puts the ticked products into the cart one after the other, with a short pause in between. EatFresh asks once more before adding. Before the first product EatFresh reads the Picnic cart once, so it knows how many pieces are in it already. If that fails, EatFresh puts nothing in and says so. After each product EatFresh reads the cart from Picnic's answer. Only if the product is there with the expected quantity (pieces that were there before counted in), the entry shows "In the cart". Lines in the cart without a readable quantity do not disturb the other products. If the chosen product itself is in such a line, EatFresh does not put it in. The entries stay on the KitchenOwl list for 3 days; after that EatFresh takes them off, but only if their amount text is still the one sent. If a later transfer added to it, the entry is open again at once, with the note "Already in the cart" and the amount that went in. It is then not preselected for sending, so nothing ends up in the cart twice. Then you can send it again.
- **Smaller package:** if the last package is needed only for a small rest (at most 60 % of its content), the entry says that a smaller package is enough for the rest. "Choose smaller package" opens the product search; hits marked "enough for the rest" come first. EatFresh remembers the choice like the main product, the entry gets a second line with a quantity of its own, and "Remove smaller package" takes it away. When sending, both products go into the cart one after the other. If the second fails, the first stays in the cart and EatFresh reports the error. "Undo" takes out both. The suggestion comes from the amounts EatFresh itself put on the list. If somebody changed the list by hand, there is no suggestion, and with a fixed, remembered quantity there is none either. Next to the amount, "calculated" with the exact number is shown if the number on the list differs from the exact one (for example because it was rounded up for the servings).
- **EatFresh stops at the first error:** if Picnic does not answer, answers too late or unreadably, rejects the login or does not put a product into the cart (for example because it is not available), EatFresh sends nothing more to Picnic. The other products are not tried and stay ticked. A failed search is not repeated by itself either.
- **Maybe in the cart:** if Picnic does not answer in time or not clearly, the product may be in the cart anyway. The entry then shows "Maybe in the cart: Picnic's answer was not clear. Check the Picnic app and take it out there if needed." EatFresh does not add it again by itself and does not take it out either. After 3 days the mark goes away and the entry stays on the list. If it is not in the cart, tap "Not in the cart"; then you can send it again. This also happens when the cart changed but does not show the product with the expected quantity, for example because Picnic keeps it under another number in the cart than in the search. EatFresh only reports a product as surely not added when Picnic refused it explicitly or the cart stayed unchanged in every number.
- **Undo:** "Undo" is only offered for "In the cart", and the mark lasts 3 days. It takes out the quantity EatFresh put in, never more. Picnic simply subtracts that number: if you changed the product in the Picnic app in the meantime, better take it out there, or pieces you added yourself may go too. Before that EatFresh reads the cart once. If it holds fewer pieces than EatFresh put in, EatFresh takes nothing out and the entry shows "Maybe in the cart". If the answer to "Undo" is not clear or the quantity in it did not drop by the number sent, the entry shows "Maybe in the cart" as well, and EatFresh takes nothing more out.
- **Nothing is ever ordered.** EatFresh books no delivery slot and pays nothing. You order yourself in the Picnic app. Check the cart in the Picnic app before every order. Do not change anything in the Picnic app while EatFresh is sending, otherwise EatFresh may misjudge what is in the cart.
- **Gentle:** EatFresh only calls Picnic when you search, fill the cart or undo, never in the background. A run reads the cart once and then puts in each product with a call of its own. "Undo" reads the cart once and then takes out. Only one call runs at a time: if one hangs, EatFresh waits until it has ended before the next one goes to Picnic. If Picnic stays busy in EatFresh for long because of that, restarting Home Assistant helps. If Picnic rejects the login, sign in again in the Picnic integration of Home Assistant.
- **Your own responsibility:** the Picnic integration uses a non-public interface of the Picnic app. Picnic can change it at any time; search or cart then stop working until the integration is updated. Automated access may break the terms of Picnic. Please read the terms of Picnic and decide yourself whether and with which account you use this.

### Calendar and sensor

The device "EatFresh" has two entities:

- Calendar **Week plan**: one all-day event per planned recipe.
- Sensor **Today**: the names of today's meals separated by commas, otherwise unknown. The attribute `recipes` holds `kitchenowl_id`, `name`, `image` and `servings` (the servings of the entry, else the start value of the recipe, else unknown) of each meal. The attribute `week` lists the meals from today to six days ahead by date, each with `date`, `recipe_id`, `name` and `servings`.

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
- `eatfresh.add_recipe_to_shopping_list` with `recipe_id` and `servings` (optional, 1 to 99): put the ingredients on the shopping list, recalculated to `servings`. Response: `added`.
- `eatfresh.search_collection` with `query`, `limit` and `name_only` (all optional): search the collection by name or ingredient, ignoring case. With `name_only: true`, `query` only matches the name, not the ingredients (default `false`). Without `query` the whole collection comes back; hidden recipes are left out. `limit` caps the number of recipes in the response (1 to 200, default 50). Response: `recipes` with `recipe_id`, `name`, `time`, `yields`, `tags` and `planned_dates` (days as `YYYY-MM-DD`), plus `total` (number of all matches). If only the meal plan cannot be loaded, `planned_dates` stays empty.
- `eatfresh.get_planner` with `start_date` (optional, default today) and `days` (1 to 31, default 7): read the meal plan. Response: `start_date`, `days`, `entries` with `date`, `recipe_id`, `name`, `servings`, and `unscheduled` (recipes without a day) with `recipe_id`, `name`, `servings`.
- `eatfresh.plan_recipe` with `recipe_id`, `date` and `servings` (optional, 1 to 99): plan a recipe on a day, for `servings` servings. Response: `recipe_id`, `date`.
- `eatfresh.unplan_recipe` with `recipe_id` and `date` (optional): take a recipe off a day; without `date` the entry without a day. The recipe itself stays. Response: `recipe_id`, `date`.

`recipe_id` is the id in KitchenOwl. Without `servings` the start value of the recipe applies (see "Servings"): the amounts on the list are then recalculated to that number and are no longer the amounts of the recipe unchanged. If the recipe has no servings in KitchenOwl (or more than 99), `servings` is ignored and they stay unchanged. `servings` is a whole number from 1 to 99. The actions also take `3.0`, but not `2.5`. Only recipes of the own collection are accepted. The calendar and the sensor show a change at once. `search_collection` and `get_planner` need a response variable (`response_variable`).

Example: a script that plans a pasta dish for tomorrow for four servings and reports the next three days.

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
          servings: 4
      - action: eatfresh.get_planner
        data:
          days: 3
        response_variable: plan
      - action: persistent_notification.create
        data:
          message: |-
            {% for item in plan.entries %}{{ item.date }}: {{ item.name }} ({{ item.servings }})
            {% endfor %}
```

### License

EatFresh is licensed under the MIT License, see [`LICENSE`](LICENSE). The panel file bundles third-party packages (Lit, Material Design Icons). Their license notices are in [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md).

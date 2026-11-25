"""Sort ingredient names into supermarket departments.

Pure module without Home Assistant. ``classify`` maps the name of an
ingredient, as recipe sites write it, to the key of a department. German
comes first, English second. Unknown names go to ``other``: a wrong
department is worse than no department.

Matching works on normalised words (lower case, no accents, ``ß`` as
``ss``, umlauts without dots, simple plural and adjective endings removed).
Longer matches beat shorter ones, so "Kokosmilch" is canned and not dairy.
Compound words are recognised by their end ("Bergkäse" ends in "käse").
"""

from __future__ import annotations

import re
import unicodedata

OTHER = "other"

DEPARTMENTS: tuple[str, ...] = (
    "fruits_vegetables",
    "bread",
    "dairy",
    "refrigerated",
    "meat_fish",
    "grain",
    "canned",
    "spices",
    "baking",
    "freezer",
    "drinks",
    "snacks",
    "hygiene",
    OTHER,
)

_NAMES: dict[str, tuple[str, str, str]] = {
    # key: (emoji, German, English)
    "fruits_vegetables": ("🥬", "Obst und Gemüse", "Fruits and vegetables"),
    "bread": ("🍞", "Brot und Backwaren", "Bread and bakery"),
    "dairy": ("🥛", "Milchprodukte und Eier", "Dairy and eggs"),
    "refrigerated": ("🧊", "Kühlregal", "Refrigerated"),
    "meat_fish": ("🥩", "Fleisch, Wurst und Fisch", "Meat, sausage and fish"),
    "grain": ("🌾", "Nudeln, Reis und Getreide", "Pasta, rice and grains"),
    "canned": ("🥫", "Konserven", "Canned goods"),
    "spices": ("🧂", "Gewürze, Öl und Soßen", "Spices, oil and sauces"),
    "baking": ("🧁", "Backzutaten", "Baking"),
    "freezer": ("❄️", "Tiefkühl", "Frozen"),
    "drinks": ("🍹", "Getränke", "Drinks"),
    "snacks": ("🥜", "Snacks und Süßes", "Snacks and sweets"),
    "hygiene": ("🧻", "Haushalt", "Household"),
    OTHER: ("🛒", "Sonstiges", "Other"),
}

# The ten default categories of KitchenOwl use the same keys.
KITCHENOWL_DEFAULT_KEYS: dict[str, str] = {
    key: key
    for key in (
        "bread",
        "canned",
        "dairy",
        "drinks",
        "freezer",
        "fruits_vegetables",
        "grain",
        "hygiene",
        "refrigerated",
        "snacks",
    )
}

# ---------------------------------------------------------------------------
# Word tables, one per department. Entries are separated by commas and may
# contain spaces ("passierte Tomaten"). Write them as recipes do; plural
# forms are found on their own.
# ---------------------------------------------------------------------------

_WORDS: dict[str, str] = {
    "fruits_vegetables": """
        Obst, Gemüse, Apfel, Äpfel, Birne, Banane, Orange, Mandarine,
        Clementine, Zitrone, Limette, Grapefruit, Traube, Weintrauben,
        Erdbeere, Himbeere, Heidelbeere, Blaubeere, Brombeere, Johannisbeere,
        Beeren, Kirsche, Pfirsich, Nektarine, Aprikose, Pflaume, Zwetschge,
        Mango, Ananas, Kiwi, Melone, Wassermelone, Avocado, Granatapfel,
        Feige, Rhabarber, Kokosnuss, Zitronensaft, Limettensaft,
        Zitronenschale, Zitronenabrieb, Orangenschale, Limettenschale,
        Fruchtfleisch, Kürbisfleisch, Kartoffel, Süßkartoffel,
        Frühkartoffel, Zwiebel, rote Zwiebel, Schalotte, Frühlingszwiebel,
        Lauchzwiebel, Knoblauch, Knoblauchzehe, Ingwer, Karotte, Möhre,
        Pastinake, Petersilienwurzel, Wurzel, Sellerie, Knollensellerie,
        Staudensellerie, Stangensellerie, Lauch, Porree, Tomate,
        Cocktailtomate, Kirschtomate, Cherrytomate, Rispentomate,
        Strauchtomate, Gurke, Salatgurke, Paprika, Paprikaschote, Spitzpaprika,
        Zucchini, Aubergine, Kürbis, Hokkaido, Butternut, Brokkoli, Broccoli,
        Blumenkohl, Rosenkohl, Weißkohl, Rotkohl, Spitzkohl, Wirsing,
        Grünkohl, Kohlrabi, Chinakohl, Kohl, Kraut, Pak Choi, Spinat,
        Blattspinat, Babyspinat, Salat, Eisbergsalat, Kopfsalat, Feldsalat,
        Rucola, Rauke, Römersalat, Radicchio, Chicorée, Radieschen, Rettich,
        Rote Bete, Rüben, Champignon, Pilze, Pfifferlinge, Steinpilze,
        Austernpilze, Kräuterseitlinge, Shiitake, Maiskolben, Karfiol, grüne
        Bohnen, Buschbohnen,
        Stangenbohnen, Bohnen, Zuckerschoten, Spargel, Fenchel, Artischocke,
        Mangold, Chili, Chilischote, Peperoni, Jalapeño, Okra, Sprossen,
        Kresse, Kräuter, frische Kräuter, Petersilie, Schnittlauch, Basilikum,
        Koriander, Dill, Minze, Thymian, Rosmarin, Salbei, Estragon, Kerbel,
        Liebstöckel, Zitronengras, Bärlauch, Kaffirlimettenblätter,
        fruit, vegetables, apple, pear, banana, lemon, lime, berries,
        strawberry, raspberry, blueberry, cherry, peach, plum, grapes,
        pineapple, melon, potato, sweet potato, onion, red onion, shallot,
        spring onion, scallion, garlic, garlic clove, ginger, carrot,
        parsnip, celery, celeriac, leek, tomato, cherry tomato, cucumber,
        bell pepper, zucchini, courgette, eggplant, pumpkin, squash,
        cauliflower, cabbage, spinach, lettuce, mushroom, green beans, snow
        peas, asparagus, fennel, herbs, fresh herbs, parsley, chives, basil,
        cilantro, mint, thyme, rosemary, sage, dill, lemon juice, lime juice
    """,
    "bread": """
        Brot, Toast, Toastbrot, Brötchen, Semmel, Baguette, Ciabatta,
        Fladenbrot, Vollkornbrot, Bauernbrot, Mischbrot, Laugenbrezel, Brezel,
        Laugenstange, Croissant, Brioche, Burger Buns, Burgerbrötchen,
        Hot Dog Brötchen, Tortilla, Tortillas, Wraps, Wrap, Pita, Naan,
        Knäckebrot, Zwieback, Toastbrötchen, Weizentortillas,
        bread, toast, bun, buns, roll, rolls, baguette, croissant, tortilla,
        pita, flatbread
    """,
    "dairy": """
        Milch, Vollmilch, H-Milch, fettarme Milch, Butter, Margarine,
        Butterschmalz, Sahne, Schlagsahne, Kochsahne, saure Sahne, Schmand,
        Crème fraîche, Crème double, Quark, Magerquark, Speisequark, Joghurt,
        Jogurt, Naturjoghurt, griechischer Joghurt, Skyr, Kefir, Buttermilch,
        Kondensmilch, Hafermilch, Mandelmilch, Sojamilch, Käse, Gouda,
        Emmentaler, Parmesan, Grana Padano, Pecorino, Mozzarella, Burrata,
        Feta, Schafskäse, Hirtenkäse, Ziegenkäse, Frischkäse, Mascarpone,
        Ricotta, Hüttenkäse, Cheddar, Bergkäse, Gruyère, Raclettekäse,
        Camembert, Brie, Gorgonzola, Halloumi, Reibekäse, geriebener Käse,
        Pizzakäse, Schmelzkäse, Kräuterbutter, Ei, Eier, Eigelb, Eiweiß,
        Eiklar, Wachteleier,
        milk, butter, cream, heavy cream, whipping cream, sour cream,
        cheese, cream cheese, yogurt, yoghurt, buttermilk, egg, eggs,
        egg yolk, egg white, parmesan, mozzarella, feta
    """,
    "refrigerated": """
        Blätterteig, Pizzateig, Quicheteig, Filoteig, Yufka, Yufkateig,
        Strudelteig, Croissantteig, Teig, Gnocchi, Schupfnudeln, Tofu,
        Räuchertofu, Seidentofu, Tempeh, Tortellini, frische Tortellini,
        Ravioli, frische Pasta, frische Nudeln, Maultaschen, Spätzle,
        frische Spätzle, Hummus, Kloßteig, Knödel, Kartoffelknödel,
        Semmelknödel, Pudding, Kräuterquark, Kartoffelsalat, Nudelsalat,
        Fleischsalat, Tzatziki, Gyros fertig,
        puff pastry, pizza dough, gnocchi, tofu, tempeh, fresh pasta, hummus
    """,
    "meat_fish": """
        Fleisch, Hackfleisch, Hack, gemischtes Hackfleisch,
        Rinderhack, Hähnchen, Hähnchenbrust, Hähnchenbrustfilet,
        Hähnchenschenkel, Hähnchenkeule, Hühnchen, Huhn, Hühnerbrust,
        Geflügel, Pute, Putenbrust, Putenfleisch, Ente, Entenbrust, Gans,
        Schwein, Schweinefleisch, Schweinefilet, Schweinebauch, Rind,
        Rindfleisch, Rinderfilet, Rinderbraten, Rinderhüfte, Kalb,
        Kalbfleisch, Lamm, Lammfleisch, Wild, Hirsch, Reh, Steak,
        Rumpsteak, Schnitzel, Kotelett, Gulasch, Geschnetzeltes, Filet,
        Medaillons, Braten, Schweinebraten, Kassler, Mett, Leber, Speck,
        Bauchspeck, Frühstücksspeck,
        Schinkenspeck, Speckwürfel, Bacon, Pancetta, Guanciale, Schinken,
        Kochschinken, Rohschinken, Serranoschinken, Parmaschinken,
        Schinkenwürfel, Salami, Chorizo, Wurst, Würstchen, Wiener Würstchen,
        Bratwurst, Leberkäse, Frikadelle, Hackbällchen, Mortadella,
        Fisch, Lachs, Räucherlachs, Lachsfilet, Kabeljau, Seelachs, Forelle,
        Dorade, Zander, Pangasius, Scholle, Hering, Matjes, Garnelen,
        Shrimps, Krabben, Scampi, Muscheln, Miesmuscheln, Tintenfisch,
        Calamari, Meeresfrüchte,
        meat, ground beef, minced meat, beef, pork, chicken, chicken breast,
        turkey, duck, lamb, veal, steak, bacon, ham, sausage, sausages,
        salami, fish, salmon, cod, trout, shrimp, prawns, mussels, squid
    """,
    "grain": """
        Nudeln, Pasta, Spaghetti, Spaghettini, Penne, Rigatoni, Fusilli,
        Farfalle, Tagliatelle, Pappardelle, Linguine, Makkaroni, Maccaroni,
        Conchiglie, Orecchiette, Lasagneplatten, Lasagneblätter, Cannelloni,
        Bandnudeln, Eiernudeln, Suppennudeln, Spiralnudeln, Hörnchennudeln,
        Glasnudeln, Reisnudeln, Mie Nudeln, Udon, Soba, Orzo, Risoni,
        Reis, Basmatireis, Jasminreis, Risottoreis, Arborio, Vollkornreis,
        Wildreis, Milchreis, Sushireis, Parboiled Reis, Couscous, Bulgur,
        Quinoa, Linsen, rote Linsen, Berglinsen, Belugalinsen, Hirse,
        Polenta, Haferflocken, Müsli, Cornflakes, Grieß, Hartweizengrieß,
        Graupen, Buchweizen, Dinkel, Amaranth, Getreide,
        pasta, noodles, spaghetti, penne, macaroni, lasagna sheets, rice,
        basmati rice, couscous, bulgur, quinoa, lentils, red lentils, oats,
        rolled oats, oatmeal, polenta, semolina
    """,
    "canned": """
        Konserve, Dose, Kokosmilch, Kokoscreme, Tomatenmark,
        passierte Tomaten, gehackte Tomaten, Tomaten gehackt,
        stückige Tomaten, Tomaten stückig, geschälte Tomaten,
        Tomaten aus der Dose, Dosentomaten, Pizzatomaten, Polpa,
        Passata, Tomatensauce, Tomatensoße, Tomatensugo, getrocknete Tomaten,
        Tomaten getrocknet,
        Kidneybohnen, weiße Bohnen, schwarze Bohnen, Cannellinibohnen,
        Baked Beans, Mais, Zuckermais, Kichererbsen, Thunfisch, Sardellen,
        Sardinen, Oliven, schwarze Oliven, grüne Oliven, Kapern,
        Gewürzgurken, Essiggurken, Cornichons, Sauerkraut, Rotkraut im Glas,
        Artischockenherzen, Pfirsiche aus der Dose, Ananas aus der Dose,
        Apfelmus, Currypaste, rote Currypaste, grüne Currypaste,
        Antipasti, Jackfruit,
        coconut milk, coconut cream, tomato paste, canned tomatoes,
        chopped tomatoes, crushed tomatoes, passata, tomato sauce,
        kidney beans, black beans, white beans, baked beans, chickpeas, corn,
        sweet corn, tuna, anchovies, olives, capers, pickles, sauerkraut
    """,
    "spices": """
        Gewürz, Gewürze, Salz, Meersalz, Kräutersalz, Jodsalz, Pfeffer,
        schwarzer Pfeffer, weißer Pfeffer, Pfefferkörner, Cayennepfeffer,
        Salz und Pfeffer, Paprikapulver, Paprika edelsüß,
        Paprika rosenscharf, Paprika geräuchert, Rauchpaprika, Curry,
        Currypulver, Kurkuma, Kreuzkümmel, Kümmel, Zimt, Muskat, Muskatnuss,
        Zimtstange, Nelken, Gewürznelken, edelsüß, rosenscharf, Lorbeer,
        Lorbeerblatt, Lorbeerblätter,
        Chiliflocken, Chilipulver, Chilifäden, Piment, Kardamom, Sternanis,
        Fenchelsamen, Senfsaat, Oregano, Majoran, getrocknete Kräuter,
        Kräuter der Provence, italienische Kräuter, Ingwerpulver,
        Knoblauchpulver, Zwiebelpulver, Garam Masala, Ras el Hanout,
        Za'atar, Pulver, Gemüsebrühe, Brühe, Rinderbrühe, Hühnerbrühe,
        Geflügelbrühe, Fond, Kalbsfond, Bouillon, Brühwürfel,
        Gemüsebrühwürfel, Brühpulver, Öl, Olivenöl, Rapsöl,
        Sonnenblumenöl, Sesamöl, Kokosöl, Erdnussöl, Walnussöl, Leinöl,
        Kürbiskernöl, Trüffelöl, Salatöl, Speiseöl, Pflanzenöl, Bratöl, Essig,
        Balsamico, Balsamicoessig, Aceto Balsamico, Weißweinessig,
        Rotweinessig, Apfelessig, Reisessig, Senf, Dijonsenf, mittelscharfer
        Senf, Sojasauce, Sojasoße, Sojasoße hell, Teriyakisauce,
        Worcestersauce, Worcestershiresauce, Fischsauce, Austernsauce,
        Hoisinsauce, Sriracha, Tabasco, Sambal Oelek, Harissa, Ketchup,
        Tomatenketchup, Mayonnaise, Mayo, Remoulade, Grillsauce, BBQ Sauce,
        Sauce, Soße, Pesto, Tahini, Sesampaste, Miso, Mirin, Würzmischung,
        Gyrosgewürz, Liquid Smoke,
        spice, salt, pepper, black pepper, salt and pepper, smoked paprika,
        paprika powder, cumin, cinnamon, nutmeg, turmeric, cloves, bay leaf,
        bay leaves, chili flakes, chili powder, curry powder, oregano,
        dried herbs, broth, stock, bouillon cube, oil, olive oil,
        vegetable oil, sesame oil, vinegar, balsamic vinegar, mustard,
        soy sauce, ketchup, mayonnaise, fish sauce, sauce
    """,
    "baking": """
        Mehl, Weizenmehl, Dinkelmehl, Roggenmehl, Vollkornmehl, Kokosmehl,
        Mandelmehl, Zucker, Puderzucker, brauner Zucker, Rohrzucker,
        Kokosblütenzucker, Gelierzucker, Hagelzucker, Vanillezucker,
        Vanillinzucker, Hefe, Trockenhefe, frische Hefe, Backpulver, Natron,
        Speisestärke, Maisstärke, Kartoffelstärke, Stärke, Kakao,
        Kakaopulver, Backkakao, Kuvertüre, Schokotropfen, Schokodrops,
        Zartbitterschokolade, Blockschokolade, Gelatine, Agar-Agar,
        Puddingpulver, Vanillepuddingpulver, Vanilleschote, Vanilleextrakt,
        Vanillepaste, Vanillearoma, Backaroma, Zitronenaroma, Rumaroma,
        Mandeln, gemahlene Mandeln, Mandelblättchen, Mandelstifte,
        Haselnüsse, gemahlene Haselnüsse, Walnüsse, Pekannüsse, Cashewkerne,
        Pistazien, Nüsse, Rosinen, Sultaninen, Cranberries getrocknet,
        Kokosraspel, Kokosflocken, Paniermehl, Semmelbrösel, Mohn, Sesam,
        Leinsamen, Chiasamen, Sonnenblumenkerne, Kürbiskerne, Pinienkerne,
        Kerne, Saaten, Streusel, Marzipan, Fondant, Lebensmittelfarbe,
        Agavendicksaft, Rosenwasser, Kakaobutter, Kokosfleisch,
        flour, sugar, brown sugar, powdered sugar, icing sugar, yeast,
        baking powder, baking soda, cornstarch, cocoa, cocoa powder,
        vanilla, vanilla extract, gelatin, almonds, ground almonds,
        hazelnuts, walnuts, nuts, raisins, breadcrumbs, sesame seeds
    """,
    "freezer": """
        Tiefkühlkost, Erbsen, Tiefkühlerbsen, Erbsen und Möhren, Rahmspinat,
        Fischstäbchen, Pommes, Pommes frites, Kroketten, Rösti,
        Tiefkühlpizza, Eis, Eiscreme, Speiseeis, Vanilleeis, Eiswürfel,
        Kaisergemüse, Buttergemüse, Suppengrün TK,
        peas, frozen peas, frozen vegetables, fries, french fries,
        ice cream, ice cubes, fish sticks
    """,
    "drinks": """
        Wasser, Mineralwasser, Sprudelwasser, stilles Wasser, Kokoswasser,
        Saft, Orangensaft, Apfelsaft, Traubensaft, Kirschsaft, Multivitaminsaft,
        Wein, Weißwein, Rotwein, Roséwein, Sekt, Prosecco, Champagner,
        Portwein, Sherry, Marsala, Bier, Cola, Limonade, Limo, Tonic Water,
        Ginger Ale, Kaffee, Espresso, Instantkaffee, Kaffeebohnen, Tee,
        Schwarztee, Grüner Tee, Kräutertee, Pfefferminztee, Früchtetee,
        Rum, Wodka, Gin, Whisky, Brandy, Cognac, Likör, Amaretto,
        Schnaps, Grappa, Kakaogetränk,
        water, sparkling water, juice, orange juice, apple juice, wine,
        white wine, red wine, coffee, tea, soda
    """,
    "snacks": """
        Snacks, Chips, Kartoffelchips, Tortillachips, Nachos, Salzstangen,
        Cracker, Popcorn, Erdnüsse, Studentenfutter, Schokolade,
        Vollmilchschokolade, Nutella, Nuss-Nougat-Creme, Kekse, Butterkekse,
        Löffelbiskuits, Gummibärchen, Bonbons, Müsliriegel, Riegel,
        Marmelade, Konfitüre, Gelee, Honig, Ahornsirup, Sirup, Erdnussbutter,
        Mandelmus, Trockenobst, Datteln, getrocknete Aprikosen, Pralinen,
        chips, crisps, crackers, popcorn, peanuts, chocolate, cookies,
        biscuits, candy, sweets, jam, honey, maple syrup, peanut butter
    """,
    "hygiene": """
        Haushalt, Toilettenpapier, Klopapier, Küchenrolle, Küchenpapier,
        Taschentücher, Servietten, Spülmittel, Spülmaschinentabs,
        Waschmittel, Weichspüler, Allzweckreiniger, Schwamm, Schwämme,
        Müllbeutel, Mülltüten, Alufolie, Frischhaltefolie, Backpapier,
        Gefrierbeutel, Zahnpasta, Zahnbürste, Shampoo, Duschgel, Seife,
        Deo, Windeln,
        toilet paper, paper towels, kitchen roll, tissues, napkins,
        dish soap, detergent, sponge, trash bags, aluminium foil, foil,
        cling film, baking paper, parchment paper, toothpaste, shampoo, soap
    """,
}

# Herbs and roots that are fresh by default but a spice when dried or ground.
_DRYABLE = """
    Kräuter, Petersilie, Schnittlauch, Basilikum, Koriander, Dill, Minze,
    Thymian, Rosmarin, Salbei, Estragon, Kerbel, Liebstöckel, Bärlauch,
    Zitronengras, Ingwer, Knoblauch, Chili, Zwiebel, herbs, parsley, basil,
    cilantro, mint, thyme, rosemary, sage, dill, ginger, garlic, onion
"""

# Words that show a frozen product, a dried or ground spice, a can or jar.
_FROZEN_WORDS = frozenset(
    {"tk", "tiefgekuhlt", "tiefgefroren", "gefroren", "frozen", "tiefkuhl"}
)
_FROZEN_PREFIXES = ("tiefkuhl", "tiefgekuhlt", "tiefgefroren")
_DRIED_WORDS = frozenset(
    {"getrocknet", "getr", "gerebelt", "gemahlen", "dried", "ground", "pulver"}
)
_CANNED_WORDS = frozenset({"dose", "konserve", "canned", "tinned"})

# Words that start a purpose ("zum Kochen", "nach Geschmack"): the rest of
# the name says nothing about the department.
_CUT_WORDS = frozenset({"zum", "zur", "fur", "nach", "for", "to"})

# Compound heads that only count after a word of the same department, so
# "Kürbisfleisch" is not meat: if the part before "fleisch" is a fruit or a
# vegetable, the whole word is a fruit or a vegetable.
_FLESH_HEADS = frozenset({"fleisch"})

_MIN_SUFFIX = 4
_MAX_NAME = 200
_ENDINGS = ("en", "em", "er", "es", "e", "n", "s")
_NON_WORD = re.compile(r"[^a-z0-9]+")
_PARENS = re.compile(r"\([^)]*\)|\[[^\]]*\]")


def _fold(text: str) -> str:
    """Lower case, ``ß`` as ``ss``, accents and umlaut dots removed."""
    text = text.casefold().replace("ß", "ss")
    text = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in text if not unicodedata.combining(ch))


def _stem(word: str) -> str:
    """Remove up to two plural or adjective endings, keep four letters."""
    for _ in range(2):
        for ending in _ENDINGS:
            if word.endswith(ending) and len(word) - len(ending) >= _MIN_SUFFIX:
                word = word[: -len(ending)]
                break
        else:
            break
    return word


def _words(text: str) -> list[str]:
    return [word for word in _NON_WORD.split(_fold(text)) if word]


def _key(text: str) -> tuple[str, ...]:
    return tuple(_stem(word) for word in _words(text))


def _entries(block: str) -> list[str]:
    return [entry.strip() for entry in block.split(",") if entry.strip()]


def _build() -> tuple[dict[tuple[str, ...], tuple[str, int]], int]:
    table: dict[tuple[str, ...], tuple[str, int]] = {}
    longest = 1
    for department, block in _WORDS.items():
        for entry in _entries(block):
            key = _key(entry)
            if not key:
                continue
            score = len("".join(_words(entry))) + len(key) - 1
            current = table.get(key)
            if current is not None and current[0] != department:
                # A word listed twice keeps its first, more careful place.
                continue
            table[key] = (department, score)
            longest = max(longest, len(key))
    return table, longest


_TABLE, _LONGEST = _build()
_SINGLE: dict[str, str] = {
    key[0]: department for key, (department, _) in _TABLE.items() if len(key) == 1
}
_DRYABLE_KEYS = frozenset(_key(entry) for entry in _entries(_DRYABLE))


def _lookup_compound(word: str) -> tuple[str, int, tuple[str, ...]] | None:
    """Find the longest known end of a compound word ("Bergkäse")."""
    for start in range(1, len(word) - _MIN_SUFFIX + 1):
        head = _stem(word[start:])
        department = _SINGLE.get(head)
        if department is None:
            continue
        if head in _FLESH_HEADS:
            prefix = _stem(word[:start])
            alt = _stem(prefix[:-1]) if prefix.endswith("s") else prefix
            if _SINGLE.get(prefix) == "fruits_vegetables" or (
                _SINGLE.get(alt) == "fruits_vegetables"
            ):
                department = "fruits_vegetables"
        return department, len(word) - start, (head,)
    return None


def _best(words: list[str]) -> tuple[str, tuple[str, ...]] | None:
    stems = [_stem(word) for word in words]
    best: tuple[str, int, tuple[str, ...]] | None = None
    count = len(stems)
    for start in range(count):
        found = False
        for size in range(min(_LONGEST, count - start), 0, -1):
            key = tuple(stems[start : start + size])
            hit = _TABLE.get(key)
            if hit is not None:
                found = True
                if best is None or hit[1] > best[1]:
                    best = (hit[0], hit[1], key)
                break
        if not found:
            compound = _lookup_compound(words[start])
            if compound is not None and (best is None or compound[1] > best[1]):
                best = compound
    if best is None:
        return None
    return best[0], best[2]


def classify(name: str) -> str:
    """Return the department key for an ingredient name, ``OTHER`` if unknown."""
    if not isinstance(name, str) or not name.strip():
        return OTHER
    text = name[:_MAX_NAME]
    all_words = _words(text)
    folded = set(all_words)
    frozen = bool(folded & _FROZEN_WORDS) or any(
        word.startswith(_FROZEN_PREFIXES) for word in all_words
    )
    dried = any(_stem(word) in _DRIED_WORDS or word in _DRIED_WORDS for word in folded)
    canned = bool({_stem(word) for word in folded} & _CANNED_WORDS)

    words: list[str] = []
    for word in _words(_PARENS.sub(" ", text)):
        if word in _CUT_WORDS and words:
            break
        if not word.isdigit():
            words.append(word)
    if not words:
        words = [word for word in all_words if not word.isdigit()]

    found = _best(words)
    if found is None:
        return "freezer" if frozen else OTHER
    department, key = found
    if frozen and department not in ("drinks", "hygiene", "spices"):
        department = "freezer"
    elif department == "fruits_vegetables" and dried and key in _DRYABLE_KEYS:
        department = "spices"
    elif department in ("fruits_vegetables", "freezer") and canned:
        department = "canned"
    return department


def department_name(key: str, language: str) -> str:
    """Return the name of a department with emoji, German or English."""
    emoji, german, english = _NAMES.get(key, _NAMES[OTHER])
    text = german if isinstance(language, str) and language[:2] == "de" else english
    return f"{emoji} {text}"


# Names of KitchenOwl categories, ours and KitchenOwl's own, without emoji.
_CATEGORY_SYNONYMS: dict[str, str] = {
    "fruits_vegetables": """
        Obst und Gemüse, Obst & Gemüse, Gemüse und Obst, Obst, Gemüse,
        Fruits and Vegetables, Fruits & Vegetables, Fruit and Vegetables,
        Produce, fruits_vegetables
    """,
    "bread": """
        Brot und Backwaren, Brot & Backwaren, Brot, Backwaren, Bäckerei,
        Bread, Bread and Bakery, Bread & Bakery, Bakery, Baked Goods,
        Bread and Baked Goods
    """,
    "dairy": """
        Milchprodukte und Eier, Milchprodukte, Milch und Eier, Molkerei,
        Dairy, Dairy and Eggs, Dairy & Eggs, Dairy Products
    """,
    "refrigerated": """
        Kühlregal, Gekühlt, Gekühltes, Kühlware, Kühlprodukte, Refrigerated,
        Chilled, Fridge
    """,
    "meat_fish": """
        Fleisch, Wurst und Fisch, Fleisch und Fisch, Fleisch & Fisch,
        Fleisch, Wurst, Fisch, Metzgerei, Meat, Meat and Fish, Meat & Fish,
        Meat, sausage and fish, Fish, Meat_fish
    """,
    "grain": """
        Nudeln, Reis und Getreide, Getreide, Getreideprodukte, Nudeln und Reis,
        Teigwaren, Grain, Grains, Grain Products, Pasta, rice and grains,
        Pasta and Rice
    """,
    "canned": """
        Konserven, Konserve, Dosen, Canned, Canned goods, Canned food, Cans
    """,
    "spices": """
        Gewürze, Öl und Soßen, Gewürze, Gewürze und Öl, Gewürze & Saucen,
        Soßen, Saucen, Spices, Spices, oil and sauces, Spices and Sauces,
        Condiments, Seasoning
    """,
    "baking": """
        Backzutaten, Backen, Backbedarf, Baking, Baking supplies
    """,
    "freezer": """
        Tiefkühl, Tiefkühlprodukte, Tiefkühlkost, Tiefgekühlt, Tiefgekühltes,
        TK, Gefroren, Freezer, Frozen, Frozen food, Frozen Goods
    """,
    "drinks": """
        Getränke, Drinks, Beverages
    """,
    "snacks": """
        Snacks und Süßes, Snacks, Süßes, Süßigkeiten, Snacks & Süßes,
        Snacks and sweets, Sweets, Candy
    """,
    "hygiene": """
        Haushalt, Hygiene, Drogerie, Haushalt und Hygiene, Household,
        Household and hygiene, Toiletries
    """,
    OTHER: """
        Sonstiges, Andere, Anderes, Other, Others, Misc, Miscellaneous
    """,
}


def _category_key(text: str) -> str:
    return " ".join(_words(text.replace("&", " und ").replace("_", " ")))


def _build_categories() -> dict[str, str]:
    table: dict[str, str] = {}
    for key, block in _CATEGORY_SYNONYMS.items():
        # Commas inside our own names ("Fleisch, Wurst und Fisch") would
        # split them, so the names from department_name are added whole.
        for entry in [*_entries(block), *_NAMES[key][1:], key]:
            normal = _category_key(entry)
            if normal:
                table.setdefault(normal, key)
        for language in ("de", "en"):
            table.setdefault(_category_key(department_name(key, language)), key)
    # "und" and "and" are interchangeable.
    for normal, key in list(table.items()):
        table.setdefault(normal.replace(" und ", " and "), key)
        table.setdefault(normal.replace(" and ", " und "), key)
    return table


_CATEGORIES = _build_categories()


def match_category_name(name: str) -> str | None:
    """Return the department key for a KitchenOwl category name, or ``None``."""
    if not isinstance(name, str) or not name.strip():
        return None
    return _CATEGORIES.get(_category_key(name[:_MAX_NAME]))

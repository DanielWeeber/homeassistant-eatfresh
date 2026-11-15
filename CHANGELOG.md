# Changelog

## 0.1.0 (2026-11-15)

First release.

- Sidebar panel "EatFresh": search recipes, open a recipe, mark favourites and browse the collection.
- Recipe sources: Gaumenfreundin, Emmi kocht einfach, Küchengötter and any page with schema.org recipe data ("paste a recipe link"). Chefkoch is an opt-in source and is off by default.
- Favourites are saved as recipes in KitchenOwl with ingredients, steps, times, servings, source link and photo. A recipe is never created twice and nothing is ever deleted in KitchenOwl.
- Add the ingredients of saved recipes to a KitchenOwl shopping list.
- Actions `eatfresh.import_recipe` and `eatfresh.add_recipe_to_shopping_list`.
- Setup through the user interface, texts in German and English.
- Polite fetching: only on user action, one request per host at a time with a pause, cached results.
- Requests to addresses supplied by users only reach public hosts.

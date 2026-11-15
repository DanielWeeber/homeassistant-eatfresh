# Changelog

## 0.3.0 (2026-11-15)

- New actions with a response, for scripts and voice assistants: `eatfresh.search_collection` (search the collection by name or ingredient, with the planned days), `eatfresh.get_planner` (meal plan from a day on 1 to 31 days, plus recipes without a day), `eatfresh.plan_recipe` and `eatfresh.unplan_recipe`. Only recipes of the own collection are accepted (`not_in_collection`); KitchenOwl errors and a rejected token behave as in the other actions. The calendar and the sensor are updated right after planning or removing.
- The meal plan is fetched every minute instead of every 15 minutes, so a change made in the KitchenOwl app shows up after about a minute. The interval can be set in the options (1 to 60 minutes); existing setups get one minute. Each fetch is one request to KitchenOwl, and a plan loaded for the cards counts as the fetch of that minute.
- Sensor "Today" has a new attribute `week`: the meals from today to six days ahead (`date`, `recipe_id`, `name`), sorted by date. It moves on shortly after midnight.
- The recipe list from KitchenOwl now also keeps the names of the ingredients (used by the search of the collection).
- Sensor "Today" no longer writes a new state every minute when a recipe with a photo is planned for today. A signed image address is reused until less than 12 of its 24 hours are left, so the state only changes with the plan (and at most twice a day for a new address). The sensor signs for Home Assistant's content user. The panel and the cards get the same address for the same photo as well, so the browser cache works.
- Calls that need the meal plan at the same time (for example many `eatfresh.get_planner` with an old plan) share one request to KitchenOwl.
- `eatfresh.search_collection` takes `limit` (1 to 200, default 50) and answers `total`, the number of all matches. If only the meal plan cannot be loaded, it still answers, with empty `planned_dates`; a rejected token still fails.
- An unknown `recipe_id` loads the recipe list from KitchenOwl at most every 5 seconds, not on every try.
- A recipe opened with the "Recipe link" button (or a link in the search field) is saved to the collection by itself: the panel calls `eatfresh/favorite` once after loading. The notice "Saved to your collection." shows the suggested categories, with "Change" and "Undo"; "Undo" takes the heart off and hides the recipe (it stays in KitchenOwl). A recipe that was in the collection already gives "Was already in your collection." (a hidden one is shown again) and nothing to undo. If saving fails, the recipe stays visible with a message and "Try again". Reloading the page and going back save nothing again. Recipes from search results are still saved only with the heart.

## 0.2.0 (2026-11-15)

- "Recipe link" button in the top right corner of the panel; the field at the bottom is gone.
- Open recipes from the collection. They are shown as stored in KitchenOwl, without loading the recipe page.
- Categories (Starter, Main course, Dessert, Vegetarian, Vegan, Pasta, Soup, Salad, Baking, Breakfast) with a filter in the collection. A heart suggests categories from the tags, keywords and title of the recipe page; only these become tags in KitchenOwl (before: all keywords of the source). Categories can be changed in the collection.
- Hide recipes in the collection. They stay in KitchenOwl; "Show hidden" and a new heart bring them back. Existing favourites are kept when upgrading.
- New tab "Week plan" based on the KitchenOwl meal plan: plan recipes on a day, remove them, put the ingredients of the week on the shopping list.
- Calendar "Week plan" and sensor "Today" on the new service device "EatFresh". The meal plan is fetched every 15 minutes and after each change.
- Dashboard cards `custom:eatfresh-week-card` and `custom:eatfresh-today-card`, loaded on all dashboards.
- New WebSocket commands `eatfresh/collection/recipe`, `eatfresh/collection/hide`, `eatfresh/collection/unhide`, `eatfresh/collection/set_tags`, `eatfresh/tags`, `eatfresh/planner`, `eatfresh/planner/add`, `eatfresh/planner/remove`, `eatfresh/planner/shopping_list`. `eatfresh/collection` takes `include_hidden` and returns `tags` and `hidden`; `eatfresh/favorite` also returns `tags`.
- `eatfresh/planner` also returns `today` (time zone of Home Assistant). The panel and the cards use it for "today" and the current week instead of the browser's time zone.
- Planning a recipe that is in the plan without a day replaces that entry, as KitchenOwl does; the week plan shows this at once.
- Documented that the search limit applies per source.
- One recipe per page: links with or without `www.`, with tracking parameters (`utm_*`, `fbclid`, `gclid` and the like), `ref` or `share`, as AMP page, with an anchor, another scheme or percent encoding in the path count as the same address. Pasted links are saved under the canonical address of the page, but only if it names the same page (same host, path and recipe parameters); a canonical start or overview page is ignored. Favourites of 0.1.0 are still found.
- "Vegetarian" and "Vegan" are only suggested from a whole tag or the diet in the recipe data, never from the title, part of a tag or a tag with punctuation ("vegan?", "#vegan"). Pancakes and sandwiches are no longer "Baking". Canonical categories of both languages are one filter chip.
- Recipe ids outside the own collection are refused (`not_found`) before anything is sent to KitchenOwl and no longer start a reauthentication. Hiding accepts only recipes of the own collection.
- "Add the week's ingredients" remembers when a week was sent (for all devices) and asks before a second time (`confirm`, `already_added_at`, `shopping_list_at`). A recipe planned on two days counts twice. Two transfers of the same week at the same time send it only once; the second one is asked. After a partial transfer, a confirmed second try sends only the recipes that did not go through.
- Days are accepted from 2000 to 2100 only. A store with a broken part starts anyway, with a warning.
- `eatfresh/planner` answers the current week from the plan of the last 60 seconds, so many cards do not each ask KitchenOwl.

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

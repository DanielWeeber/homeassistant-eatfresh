"""Constants of EatFresh."""

from __future__ import annotations

from datetime import timedelta
from typing import Final

DOMAIN: Final = "eatfresh"
NAME: Final = "EatFresh"
VERSION: Final = "0.4.0"

REPOSITORY_URL: Final = "https://github.com/DanielWeeber/homeassistant-eatfresh"
USER_AGENT: Final = f"EatFresh/{VERSION} (+{REPOSITORY_URL})"

# Config entry data
CONF_URL: Final = "url"
CONF_TOKEN: Final = "token"
CONF_HOUSEHOLD_ID: Final = "household_id"
CONF_SHOPPINGLIST_ID: Final = "shoppinglist_id"

# Options
CONF_SOURCES: Final = "sources"
CONF_ACCEPT_CHEFKOCH: Final = "accept_chefkoch_terms"
# Minutes between two fetches of the meal plan. Entries of 0.2.0 have no
# such option and use the default.
CONF_PLANNER_INTERVAL: Final = "planner_interval"

CHEFKOCH: Final = "chefkoch"
JSONLD: Final = "jsonld"

# Persistent storage
STORAGE_VERSION: Final = 1
# 1.1: EatFresh 0.1.0 (favorites). 1.2: EatFresh 0.2.0 adds hidden recipes.
# 1.3: EatFresh 0.4.0 adds picnic_map, picnic_skip and picnic_sent.
STORAGE_MINOR_VERSION: Final = 3
STORAGE_KEY: Final = "eatfresh.favorites"
STORAGE_SAVE_DELAY: Final = 2

# In-memory cache
SEARCH_CACHE_TTL: Final = timedelta(hours=1)
RECIPE_CACHE_TTL: Final = timedelta(hours=24)
CACHE_MAX_ENTRIES: Final = 256

# Search
DEFAULT_SEARCH_LIMIT: Final = 20
MAX_SEARCH_LIMIT: Final = 50

# Meal plan
DEFAULT_PLANNER_INTERVAL: Final = 1
MIN_PLANNER_INTERVAL: Final = 1
MAX_PLANNER_INTERVAL: Final = 60
# ``eatfresh/planner`` for the current week reuses the plan of the
# coordinator while it is younger than this (cards on many screens).
PLANNER_MAX_AGE: Final = timedelta(seconds=60)
# Days outside these years are refused (KitchenOwl stores "no day" as 0001).
MIN_PLANNER_YEAR: Final = 2000
MAX_PLANNER_YEAR: Final = 2100
# Days the sensor "Today" lists in its attribute ``week`` (today included).
WEEK_DAYS: Final = 7
# Days the action ``get_planner`` returns at most / by default.
MAX_PLANNER_DAYS: Final = 31
DEFAULT_PLANNER_DAYS: Final = 7
# How many weeks remember when they went to the shopping list.
MAX_WEEK_LISTS: Final = 26

# Tags of a recipe
MAX_TAGS: Final = 30
MAX_TAG_LENGTH: Final = 64

# Panel
PANEL_URL_PATH: Final = "eatfresh"
PANEL_TITLE: Final = "EatFresh"
PANEL_ICON: Final = "mdi:silverware-fork-knife"
PANEL_ELEMENT: Final = "eatfresh-panel"
PANEL_FILENAME: Final = "eatfresh-panel.js"
CARDS_FILENAME: Final = "eatfresh-cards.js"
STATIC_URL_PATH: Final = "/eatfresh_static"

# Image proxy
IMAGE_PROXY_PATH: Final = "/api/eatfresh/image"
IMAGE_SIGN_EXPIRATION: Final = timedelta(hours=24)
# A signed image path is reused until less than this is left of it.
IMAGE_SIGN_RENEW_BEFORE: Final = timedelta(hours=12)
IMAGE_MAX_BYTES: Final = 10 * 1024 * 1024
IMAGE_FETCH_TIMEOUT: Final = 15

# Actions
SERVICE_IMPORT_RECIPE: Final = "import_recipe"
SERVICE_ADD_TO_SHOPPING_LIST: Final = "add_recipe_to_shopping_list"
SERVICE_SEARCH_COLLECTION: Final = "search_collection"
SERVICE_GET_PLANNER: Final = "get_planner"
SERVICE_PLAN_RECIPE: Final = "plan_recipe"
SERVICE_UNPLAN_RECIPE: Final = "unplan_recipe"
ATTR_URL: Final = "url"
ATTR_RECIPE_ID: Final = "recipe_id"
ATTR_QUERY: Final = "query"
ATTR_START_DATE: Final = "start_date"
ATTR_DAYS: Final = "days"
ATTR_DATE: Final = "date"
MAX_QUERY_LENGTH: Final = 100
ATTR_LIMIT: Final = "limit"
ATTR_NAME_ONLY: Final = "name_only"
DEFAULT_COLLECTION_LIMIT: Final = 50
MAX_COLLECTION_LIMIT: Final = 200

# WebSocket error codes
ERR_SOURCE_ERROR: Final = "source_error"
ERR_SOURCE_BLOCKED: Final = "source_blocked"
ERR_NOT_FOUND: Final = "not_found"
ERR_KITCHENOWL_ERROR: Final = "kitchenowl_error"
ERR_KITCHENOWL_AUTH: Final = "kitchenowl_auth"
ERR_NOT_LOADED: Final = "not_loaded"
ERR_PICNIC_UNAVAILABLE: Final = "picnic_unavailable"
ERR_PICNIC_ERROR: Final = "picnic_error"

# Picnic
# Ingredients with a remembered product, excluded ingredients and marks of
# entries put into the cart kept at most.
MAX_PICNIC_MAP: Final = 500
MAX_PICNIC_SKIP: Final = 500
MAX_PICNIC_SENT: Final = 300
# Marks of entries put into the cart are dropped after this.
PICNIC_SENT_MAX_AGE: Final = timedelta(days=14)
MAX_PICNIC_NAME_LENGTH: Final = 100
MAX_PICNIC_QUERY_LENGTH: Final = 60
MAX_PICNIC_SEND_ITEMS: Final = 60
MAX_PICNIC_AMOUNT: Final = 20
PICNIC_SEARCH_LIMIT: Final = 8

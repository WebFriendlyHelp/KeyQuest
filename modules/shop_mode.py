import pygame
from typing import List, Optional

from modules import currency_manager
from modules import shop_manager


def show_shop(app, categories: Optional[List[str]] = None, title: str = "Shop") -> None:
    """Show shop interface for purchasing items."""
    app.state.mode = "SHOP"
    app.shop_category_index = 0
    app.shop_item_index = 0
    app.shop_view = "categories"  # "categories" or "items"
    app.shop_title = title
    if categories:
        app.shop_categories = [cat for cat in categories if cat in shop_manager.SHOP_CATEGORIES]
    else:
        app.shop_categories = list(shop_manager.SHOP_CATEGORIES.keys())

    balance = currency_manager.get_balance(app.state.settings)
    balance_text = currency_manager.format_balance(balance)
    if len(app.shop_categories) == 1:
        cat_id = app.shop_categories[0]
        cat_info = shop_manager.SHOP_CATEGORIES[cat_id]
        app.shop_view = "items"
        announcement = (
            f"{title}. {cat_info['name']}. You have {balance_text}. "
            "Use Up and Down arrows to browse items. Press Enter to purchase. "
            "Press Escape to return to main menu."
        )
    else:
        announcement = (
            f"{title}. You have {balance_text}. Use Up and Down arrows to browse. "
            f"Press Enter to select a category. Press Escape to return to main menu."
        )
    app.speech.say(announcement, priority=True, protect_seconds=3.0)

    if app.shop_categories:
        first_cat = app.shop_categories[0]
        if app.shop_view == "items":
            items = shop_manager.get_category_items(first_cat)
            if items:
                announce_shop_item(app, items[0])
            else:
                app.speech.say("No items in this category.", priority=True)
        else:
            cat_info = shop_manager.SHOP_CATEGORIES[first_cat]
            app.speech.say(f"{cat_info['name']}. {cat_info['description']}")


def handle_shop_input(app, event, mods: int) -> None:
    """Handle shop navigation and purchases."""
    if event.key == pygame.K_ESCAPE:
        if app.shop_view == "items":
            app.shop_view = "categories"
            app.shop_item_index = 0
            if app.shop_categories:
                cat_id = app.shop_categories[app.shop_category_index]
                cat_info = shop_manager.SHOP_CATEGORIES[cat_id]
                app.speech.say(f"{cat_info['name']}. {cat_info['description']}")
        else:
            app.save_progress()
            app._return_to_main_menu()
        return

    if event.key == pygame.K_UP:
        if app.shop_view == "categories":
            app.shop_category_index = (app.shop_category_index - 1) % len(app.shop_categories)
            cat_id = app.shop_categories[app.shop_category_index]
            cat_info = shop_manager.SHOP_CATEGORIES[cat_id]
            app.speech.say(f"{cat_info['name']}. {cat_info['description']}")
        else:
            cat_id = app.shop_categories[app.shop_category_index]
            items = shop_manager.get_category_items(cat_id)
            app.shop_item_index = (app.shop_item_index - 1) % len(items)
            announce_shop_item(app, items[app.shop_item_index])
        return

    if event.key == pygame.K_DOWN:
        if app.shop_view == "categories":
            app.shop_category_index = (app.shop_category_index + 1) % len(app.shop_categories)
            cat_id = app.shop_categories[app.shop_category_index]
            cat_info = shop_manager.SHOP_CATEGORIES[cat_id]
            app.speech.say(f"{cat_info['name']}. {cat_info['description']}")
        else:
            cat_id = app.shop_categories[app.shop_category_index]
            items = shop_manager.get_category_items(cat_id)
            app.shop_item_index = (app.shop_item_index + 1) % len(items)
            announce_shop_item(app, items[app.shop_item_index])
        return

    if event.key in (pygame.K_RETURN, pygame.K_SPACE):
        if app.shop_view == "categories":
            app.shop_view = "items"
            app.shop_item_index = 0
            cat_id = app.shop_categories[app.shop_category_index]
            items = shop_manager.get_category_items(cat_id)
            if items:
                cat_info = shop_manager.SHOP_CATEGORIES[cat_id]
                app.speech.say(
                    f"{cat_info['name']}. Use Up and Down to browse items. "
                    f"Press Enter to purchase. Press Escape to go back."
                )
                # Queued: an interrupting first item cancelled the instructions.
                announce_shop_item(app, items[0], queued=True)
            else:
                app.speech.say("No items in this category.")
        else:
            cat_id = app.shop_categories[app.shop_category_index]
            items = shop_manager.get_category_items(cat_id)
            item_id = items[app.shop_item_index]
            purchase_shop_item(app, item_id)


def announce_shop_item(app, item_id: str, queued: bool = False) -> None:
    """Announce a shop item with details."""
    item = shop_manager.get_item_info(item_id)
    if not item:
        return

    owned = shop_manager.is_owned(app.state.settings, item_id)
    quantity = shop_manager.get_inventory_count(app.state.settings, item_id)

    name = item["name"]
    cost = item["cost"]
    description = item["description"]

    status = ""
    if shop_manager.is_consumable(item_id):
        if quantity > 0:
            status = f"Owned: {quantity}. "
    else:
        if owned:
            status = "Already owned. "
    balance = currency_manager.get_balance(app.state.settings)
    affordability = "You can afford this." if balance >= cost else f"You need {cost - balance} more coins."

    announcement = f"{name}. {cost} coins. {status}{description} {affordability}"
    if queued:
        app.speech.say(announcement, priority=True, interrupt=False)
    else:
        app.speech.say(announcement)


def purchase_shop_item(app, item_id: str) -> None:
    """Attempt to purchase a shop item."""
    can_buy, reason = shop_manager.can_purchase(app.state.settings, item_id)
    if not can_buy:
        app.audio.beep_bad()
        app.speech.say(reason, priority=True)
        return

    success, message = shop_manager.purchase_item(app.state.settings, item_id)
    if success:
        app.audio.play_success()
        extra_hint = ""
        if item_id.startswith("pet_"):
            extra_hint = " Open Pets from the main menu to use or view pet items."
        app.speech.say(f"{message}{extra_hint}", priority=True)
        app.save_progress()

        balance = currency_manager.get_balance(app.state.settings)
        balance_text = currency_manager.format_balance(balance)
        app.speech.say(f"Remaining balance: {balance_text}", priority=True, interrupt=False)
    else:
        app.audio.beep_bad()
        app.speech.say(message, priority=True)

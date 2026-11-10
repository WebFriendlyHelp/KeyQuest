import pygame

from modules import dialog_manager
from modules import pet_manager
from modules import pet_ui_data
from modules import shop_manager


def ensure_pet_ui_state(app) -> None:
    """Populate pet UI attributes when older or partial app objects are missing them."""
    if not hasattr(app, "pet_options"):
        app.pet_options = list(pet_ui_data.PET_MENU_OPTIONS)
    if not hasattr(app, "pet_types"):
        app.pet_types = []
    if not hasattr(app, "pet_view"):
        app.pet_view = "status"
    if not hasattr(app, "pet_menu_index"):
        app.pet_menu_index = 0
    if not hasattr(app, "pet_choose_index"):
        app.pet_choose_index = 0
    if not hasattr(app, "pet_choose_mode"):
        app.pet_choose_mode = "new"


def _build_pet_visual_items_text(settings) -> str:
    owned = getattr(settings, "owned_items", set())
    labels = []
    if "pet_accessory_hat" in owned:
        labels.append("hat")
    if "pet_accessory_bowtie" in owned:
        labels.append("bowtie")
    if "pet_accessory_wings" in owned:
        labels.append("wings")
    if "pet_toy_ball" in owned:
        labels.append("ball")
    if "pet_toy_laser" in owned:
        labels.append("laser")

    food_total = (
        shop_manager.get_inventory_count(settings, "pet_food_basic")
        + shop_manager.get_inventory_count(settings, "pet_food_premium")
    )
    if food_total > 0:
        labels.append(f"food x {food_total}")

    if not labels:
        return "No visual items equipped."
    return f"Visual items: {', '.join(labels)}."


def show_pet(app) -> None:
    """Show pet interface."""
    ensure_pet_ui_state(app)
    app.state.mode = "PET"
    app.pet_menu_index = 0

    pet_status = pet_manager.get_pet_status(app.state.settings)
    if not pet_status["has_pet"]:
        app.pet_view = "choose"
        app.pet_choose_mode = "new"
        app.pet_types = list(pet_manager.PET_TYPES.keys())
        app.pet_choose_index = 0

        announcement = (
            "Pets. You don't have a pet yet! Choose your companion. "
            "Use Up and Down arrows to browse. Press Enter to select."
        )
        app.speech.say(announcement, priority=True, protect_seconds=3.0)
        if app.pet_types:
            # Queued: an interrupting first item cancelled the invitation.
            announce_pet_type(app, app.pet_types[0], queued=True)
        return

    app.pet_view = "status"
    app.pet_options = list(pet_ui_data.PET_MENU_OPTIONS)

    pet_name = pet_status["pet_name"]
    stage_name = pet_status["stage_name"]
    happiness = pet_status["happiness"]
    announcement = (
        f"Your Pet: {pet_name}. {stage_name}. Happiness: {happiness}%. "
        "Use Up and Down arrows to choose an action. Press Enter to select. "
        "Press Escape to return to main menu."
    )
    # One line: three interrupting lines in a row left only the first option.
    app.speech.say(
        f"{announcement} {_build_pet_visual_items_text(app.state.settings)} {app.pet_options[0]}",
        priority=True,
        protect_seconds=3.0,
    )


def handle_pet_input(app, event, mods: int) -> None:
    """Handle pet navigation and interactions."""
    ensure_pet_ui_state(app)
    if event.key == pygame.K_ESCAPE:
        if app.pet_view == "choose" and getattr(app, "pet_choose_mode", "new") == "change":
            app.pet_view = "status"
            app.pet_options = list(pet_ui_data.PET_MENU_OPTIONS)
            app.pet_menu_index = 0
            pet_status = pet_manager.get_pet_status(app.state.settings)
            app.speech.say(
                f"Kept your current pet. {pet_status['pet_name']}. Use Up and Down arrows to choose an action.",
                priority=True,
            )
            return
        app.save_progress()
        app._return_to_main_menu()
        return

    if app.pet_view == "choose":
        if event.key == pygame.K_UP:
            app.pet_choose_index = (app.pet_choose_index - 1) % len(app.pet_types)
            announce_pet_type(app, app.pet_types[app.pet_choose_index])
        elif event.key == pygame.K_DOWN:
            app.pet_choose_index = (app.pet_choose_index + 1) % len(app.pet_types)
            announce_pet_type(app, app.pet_types[app.pet_choose_index])
        elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
            pet_type = app.pet_types[app.pet_choose_index]
            if getattr(app, "pet_choose_mode", "new") == "change":
                confirm = dialog_manager.show_yes_no_dialog(
                    "Change Pet",
                    "Changing pets will reset your current pet's progress. Do you want to continue?",
                    yes_label="Change Pet",
                    no_label="Keep Current",
                )
                if not confirm:
                    current_status = pet_manager.get_pet_status(app.state.settings)
                    app.speech.say(
                        f"Keeping your current pet. {current_status['pet_name']}.",
                        priority=True,
                    )
                    return
            result = pet_manager.choose_pet(app.state.settings, pet_type)
            if result["success"]:
                app.audio.play_success()
                app.speech.say(result["message"], priority=True, protect_seconds=2.0)
                app.save_progress()
                app.pet_view = "status"
                app.pet_options = list(pet_ui_data.PET_MENU_OPTIONS)
                app.pet_menu_index = 0
                app.speech.say(
                    "Use Up and Down to choose an action. Press Enter to select.",
                    priority=True,
                    interrupt=False,
                )
            else:
                app.audio.beep_bad()
                app.speech.say(result["message"], priority=True)
        return

    if app.pet_view == "status":
        if event.key == pygame.K_UP:
            app.pet_menu_index = (app.pet_menu_index - 1) % len(app.pet_options)
            app.speech.say(app.pet_options[app.pet_menu_index])
        elif event.key == pygame.K_DOWN:
            app.pet_menu_index = (app.pet_menu_index + 1) % len(app.pet_options)
            app.speech.say(app.pet_options[app.pet_menu_index])
        elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
            handle_pet_action(app, app.pet_options[app.pet_menu_index])


def announce_pet_type(app, pet_type: str, queued: bool = False) -> None:
    """Announce a pet type with description.

    ``queued`` speaks it after the line before instead of cutting that off;
    priority keeps it from being dropped by that line's protection window.
    """
    ensure_pet_ui_state(app)
    pet_info = pet_manager.get_pet_info(pet_type)
    if pet_info:
        if queued:
            app.speech.say(f"{pet_info['name']}. {pet_info['description']}", priority=True, interrupt=False)
        else:
            app.speech.say(f"{pet_info['name']}. {pet_info['description']}")


def handle_pet_action(app, action: str) -> None:
    """Handle pet actions."""
    ensure_pet_ui_state(app)
    if action == "View Status":
        pet_status = pet_manager.get_pet_status(app.state.settings)
        status_text = (
            "Pet Status.\n\n"
            f"Name: {pet_status['pet_name']}\n"
            f"Type: {pet_status['pet_type'].title()}\n"
            f"Stage: {pet_status['stage_name']}\n"
            f"XP: {pet_status['xp']}\n"
            f"XP to next stage: {pet_status['xp_to_next']}\n"
            f"Happiness: {pet_status['happiness']}%\n"
            f"Mood: {pet_status['mood'].title()}\n"
            f"{_build_pet_visual_items_text(app.state.settings)}"
        )
        app.show_info_dialog("Pet Status", status_text)
        return

    if action == "Feed Pet":
        basic_food_count = shop_manager.get_inventory_count(app.state.settings, "pet_food_basic")
        premium_food_count = shop_manager.get_inventory_count(app.state.settings, "pet_food_premium")

        if basic_food_count > 0:
            food_result = pet_manager.feed_pet(app.state.settings, "basic")
            shop_manager.use_consumable(app.state.settings, "pet_food_basic")
            app.audio.play_success()
            pet_status = pet_manager.get_pet_status(app.state.settings)
            app.speech.say(
                f"{food_result['message']} {pet_status['pet_name']} now has {pet_status['happiness']} percent happiness.",
                priority=True,
            )
            app.save_progress()
        elif premium_food_count > 0:
            food_result = pet_manager.feed_pet(app.state.settings, "premium")
            shop_manager.use_consumable(app.state.settings, "pet_food_premium")
            app.audio.play_success()
            pet_status = pet_manager.get_pet_status(app.state.settings)
            app.speech.say(
                f"{food_result['message']} {pet_status['pet_name']} now has {pet_status['happiness']} percent happiness.",
                priority=True,
            )
            app.save_progress()
        else:
            app.audio.beep_bad()
            app.speech.say("You don't have any pet food. Visit the shop to purchase some!", priority=True)
        return

    if action == "Play with Pet":
        app.state.settings.pet_happiness = min(100, app.state.settings.pet_happiness + 5)
        app.audio.play_success()
        pet_status = pet_manager.get_pet_status(app.state.settings)
        app.speech.say(
            f"You played with your pet. {pet_status['pet_name']} now has {pet_status['happiness']} percent happiness.",
            priority=True,
        )
        app.save_progress()
        return

    if action == "Change Pet":
        app.pet_view = "choose"
        app.pet_choose_mode = "change"
        app.pet_types = list(pet_manager.PET_TYPES.keys())
        app.pet_choose_index = 0
        app.speech.say(
            "Choose a new pet. Warning: This will reset your pet's progress. "
            "Use Up and Down arrows to browse. Press Enter to select. Press Escape to keep your current pet."
        )
        if app.pet_types:
            announce_pet_type(app, app.pet_types[0], queued=True)

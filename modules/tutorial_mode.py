#!python3.11
"""Tutorial mode input handling for KeyQuest."""

import random

import pygame

from modules import input_utils
from modules import tutorial_data


def handle_tutorial_input(app, event, mods) -> None:
    if event.key == pygame.K_ESCAPE:
        app.state.mode = "MENU"
        app.say_menu()
        return

    t = app.state.tutorial
    if event.key == pygame.K_SPACE and input_utils.mod_ctrl(mods):
        if t.in_intro and t.intro_items:
            name, desc = t.intro_items[t.intro_index]
            key_friendly = tutorial_data.FRIENDLY.get(name, name)
            app.speech.say(
                f"{key_friendly}. {desc}. Press Enter or Space when you are ready to start practice.",
                priority=True,
                protect_seconds=3.0,
            )
        else:
            app.speech.say(
                f"Press {tutorial_data.FRIENDLY[app.state.tutorial.required_name]}",
                priority=True,
                protect_seconds=2.0,
            )
        return

    if t.in_intro:
        if event.key == pygame.K_UP and t.intro_items:
            t.intro_index = (t.intro_index - 1) % len(t.intro_items)
            name, desc = t.intro_items[t.intro_index]
            key_friendly = tutorial_data.FRIENDLY.get(name, name)
            app.speech.say(f"{key_friendly}. {desc}")
            return
        if event.key == pygame.K_DOWN and t.intro_items:
            t.intro_index = (t.intro_index + 1) % len(t.intro_items)
            name, desc = t.intro_items[t.intro_index]
            key_friendly = tutorial_data.FRIENDLY.get(name, name)
            app.speech.say(f"{key_friendly}. {desc}")
            return
        if event.key in (pygame.K_RETURN, pygame.K_SPACE):
            app._start_tutorial_phase(t.phase)
            app.load_tutorial_prompt()
            return
        return

    if event.key in (pygame.K_LSHIFT, pygame.K_RSHIFT):
        if t.phase in (4, 5):
            app.speech.say("That's Shift. Control is below Shift in the bottom left corner.", priority=True)
        else:
            app.speech.say("That's Shift. Not needed for this tutorial.", priority=True)
        return

    if event.key in (pygame.K_LALT, pygame.K_RALT):
        if t.phase in (4, 5):
            app.speech.say("That's Alt. Control is to the left of Alt in the bottom left corner.", priority=True)
        else:
            app.speech.say("That's Alt. Not needed for this tutorial.", priority=True)
        return

    if event.key in (pygame.K_LMETA, pygame.K_RMETA, pygame.K_LSUPER, pygame.K_RSUPER):
        if t.phase in (4, 5):
            app.speech.say("That's the Windows key. Control is to the left of the Windows key in the bottom left corner.", priority=True)
        else:
            app.speech.say("That's the Windows key. Not needed for this tutorial.", priority=True)
        return

    keyset = tutorial_data.input_keyset_for_phase(t.phase)

    pressed_name = None
    for name, key in keyset:
        if name == "control" and (event.key == pygame.K_LCTRL or event.key == pygame.K_RCTRL):
            pressed_name = name
            break
        elif event.key == key:
            pressed_name = name
            break

    if pressed_name is None:
        if t.phase == 1:
            app.speech.say("Use Space bar")
        elif t.phase == 2:
            app.speech.say("Use the arrow keys")
        elif t.phase == 3:
            app.speech.say("Use Enter")
        elif t.phase == 4:
            app.speech.say("Use Control")
        else:
            app.speech.say("Use arrows, space, Enter, or Control")
        return

    t.total_attempts += 1
    t.phase_attempts += 1

    correct_key = False
    if t.required_name == "control" and (event.key == pygame.K_LCTRL or event.key == pygame.K_RCTRL):
        correct_key = True
    elif event.key == t.required_key:
        correct_key = True

    if correct_key:
        app.audio.beep_ok()
        app.trigger_flash((0, 80, 0), 0.12)
        t.total_correct += 1
        t.phase_correct += 1
        t.counts_done[t.required_name] += 1
        t.index += 1
        t.guidance_message = ""
        t.hint_message = ""
        app.speech.say(random.choice(tutorial_data.ENCOURAGEMENT["correct"]))
        app.load_tutorial_prompt()
    else:
        app.audio.beep_bad()
        app.trigger_flash((100, 0, 0), 0.12)
        target = t.required_name
        pressed = pressed_name
        t.phase_mistakes += 1
        t.key_errors[target] += 1
        guidance = tutorial_data.RELATION.get((pressed, target), f"Try {tutorial_data.FRIENDLY[target]}")
        hint = tutorial_data.HINTS[target]
        t.guidance_message = f"{tutorial_data.FRIENDLY[pressed]} {guidance}"
        t.hint_message = hint
        app.speech.say(f"{tutorial_data.FRIENDLY[pressed]} {guidance} {hint}")

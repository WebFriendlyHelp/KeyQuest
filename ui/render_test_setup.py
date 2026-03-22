from modules import sentences_manager
from ui.a11y import draw_action_emphasis, draw_active_panel, draw_focus_frame, get_visible_window
from ui.text_wrap import wrap_text


def draw_test_setup_screen(
    *,
    screen,
    title_font,
    text_font,
    small_font,
    screen_w: int,
    screen_h: int,
    fg,
    accent,
    hilite,
    duration_input: str,
    view: str,
    topic_options,
    topic_index: int,
    focus_assist: bool = False,
):
    title_surf, _ = title_font.render("Speed Test Setup", hilite)
    screen.blit(title_surf, (screen_w // 2 - title_surf.get_width() // 2, 100))

    if view == "topic":
        question_surf, _ = text_font.render("Choose language", fg)
        screen.blit(question_surf, (screen_w // 2 - question_surf.get_width() // 2, 180))

        y = 250
        for idx, topic in enumerate(topic_options):
            selected = idx == topic_index
            color = hilite if selected else fg
            display_topic = sentences_manager.get_practice_topic_display_name(topic)
            label = f"> {display_topic}" if selected else f"  {display_topic}"
            line_surf, _ = text_font.render(label, color)
            line_rect = line_surf.get_rect(topleft=(screen_w // 2 - line_surf.get_width() // 2, y))
            if selected:
                draw_active_panel(screen, line_rect, accent, fg, strong=focus_assist)
                draw_focus_frame(screen, line_rect, hilite, accent)
                draw_action_emphasis(screen, line_rect, hilite, strong=focus_assist)
            screen.blit(line_surf, line_rect)
            y += 55

        instructions = [
            "",
            "Up/Down: Choose language",
            "Enter/Space: Continue",
            "Escape: Return to menu",
        ]
    else:
        question_surf, _ = text_font.render("How many minutes for the test?", fg)
        screen.blit(question_surf, (screen_w // 2 - question_surf.get_width() // 2, 200))

        input_label_surf, _ = text_font.render("Type minutes:", accent)
        screen.blit(input_label_surf, (screen_w // 2 - input_label_surf.get_width() // 2, 245))

        input_text = duration_input if duration_input else "_"
        input_surf, _ = title_font.render(input_text, hilite)
        input_rect = input_surf.get_rect(topleft=(screen_w // 2 - input_surf.get_width() // 2, 280))
        draw_active_panel(screen, input_rect, accent, fg, strong=focus_assist)
        screen.blit(input_surf, input_rect)
        draw_focus_frame(screen, input_rect, hilite, accent)
        draw_action_emphasis(screen, input_rect, hilite, strong=focus_assist)

        instructions = [
            "",
            "Type a number (1-60 minutes)",
            "Press Enter to start",
            "Press Backspace to correct",
            "Press Escape to go back",
        ]

    y = 380
    for line in instructions:
        if line:
            text_surf, _ = small_font.render(line, accent)
            screen.blit(text_surf, (screen_w // 2 - text_surf.get_width() // 2, y))
        y += 35


def draw_practice_setup_screen(
    *,
    screen,
    title_font,
    text_font,
    small_font,
    screen_w: int,
    screen_h: int,
    fg,
    accent,
    hilite,
    focus_assist: bool = False,
    view: str,
    menu_options,
    menu_index: int,
    topic_options,
    topic_index: int,
):
    title_surf, _ = title_font.render("Sentence Practice Setup", hilite)
    screen.blit(title_surf, (screen_w // 2 - title_surf.get_width() // 2, 80))

    if view == "menu":
        subtitle_surf, _ = text_font.render("Choose how to start", fg)
        screen.blit(subtitle_surf, (screen_w // 2 - subtitle_surf.get_width() // 2, 165))

        visible_count = max(3, min(4, (screen_h - 340) // 55))
        start, end = get_visible_window(len(menu_options), menu_index, visible_count)
        y = 250
        if start > 0:
            more_above_surf, _ = small_font.render("^  more above  ^", accent)
            screen.blit(more_above_surf, (screen_w // 2 - more_above_surf.get_width() // 2, 220))

        for idx in range(start, end):
            option = menu_options[idx]
            selected = idx == menu_index
            color = hilite if selected else fg
            line_text = f"> {option}" if selected else f"  {option}"
            line_surf, _ = text_font.render(line_text, color)
            line_rect = line_surf.get_rect(topleft=(screen_w // 2 - line_surf.get_width() // 2, y))
            if selected:
                draw_active_panel(screen, line_rect, accent, fg, strong=focus_assist)
            screen.blit(line_surf, line_rect)
            if selected:
                draw_focus_frame(screen, line_rect, hilite, accent)
                draw_action_emphasis(screen, line_rect, hilite, strong=focus_assist)
            y += 55

        if end < len(menu_options):
            more_below_surf, _ = small_font.render("v  more below  v", accent)
            screen.blit(more_below_surf, (screen_w // 2 - more_below_surf.get_width() // 2, min(screen_h - 130, y - 8)))

        instructions = [
            "Sentences must match capitals and punctuation exactly",
            "Up/Down: Change option",
            "Enter/Space: Select",
            "Escape: Return to menu",
        ]
    else:
        subtitle_surf, _ = text_font.render("Select a sentence file", fg)
        screen.blit(subtitle_surf, (screen_w // 2 - subtitle_surf.get_width() // 2, 165))

        visible_count = max(5, min(7, (screen_h - 330) // 38))
        start, end = get_visible_window(len(topic_options), topic_index, visible_count)
        visible = list(topic_options[start:end])

        y = 235
        if start > 0:
            more_above_surf, _ = small_font.render("^  more above  ^", accent)
            screen.blit(more_above_surf, (screen_w // 2 - more_above_surf.get_width() // 2, 205))

        for i, topic in enumerate(visible):
            absolute_idx = start + i
            selected = absolute_idx == topic_index
            color = hilite if selected else fg
            display_topic = sentences_manager.get_practice_topic_display_name(topic)
            line_text = f"> {display_topic}" if selected else f"  {display_topic}"
            line_surf, _ = small_font.render(line_text, color)
            line_rect = line_surf.get_rect(topleft=(screen_w // 2 - line_surf.get_width() // 2, y))
            if selected:
                draw_active_panel(screen, line_rect, accent, fg, strong=focus_assist)
            screen.blit(line_surf, line_rect)
            if selected:
                draw_focus_frame(screen, line_rect, hilite, accent)
                draw_action_emphasis(screen, line_rect, hilite, strong=focus_assist)
            y += 38

        if end < len(topic_options):
            more_below_surf, _ = small_font.render("v  more below  v", accent)
            screen.blit(more_below_surf, (screen_w // 2 - more_below_surf.get_width() // 2, min(screen_h - 130, y - 8)))

        instructions = [
            "Sentences must match capitals and punctuation exactly",
            "Up/Down: Browse files",
            "Enter/Space: Start with selected file",
            "Escape: Back to previous menu",
        ]

    y = 490
    for line in instructions:
        for wrapped in wrap_text(small_font, line, screen_w - 100, accent):
            text_surf, _ = small_font.render(wrapped, accent)
            screen.blit(text_surf, (screen_w // 2 - text_surf.get_width() // 2, y))
            y += 24
        y += 6

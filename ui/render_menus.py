from ui.a11y import (
    draw_action_emphasis,
    draw_active_panel,
    draw_controls_hint,
    draw_focus_frame,
    get_visible_window,
)
from ui.layout import center_x, draw_centered_wrapped_text, get_footer_y


def draw_main_menu(
    *,
    screen,
    title_font,
    small_font,
    menu_items,
    current_index: int,
    screen_w: int,
    screen_h: int,
    fg,
    accent,
    hilite,
    unlocked_count: int,
    total_count: int,
    streak_text: str = "",
):
    title_surf, _ = title_font.render("KeyQuest", hilite)
    screen.blit(title_surf, (center_x(screen_w, title_surf.get_width()), 30))

    visible_count = max(6, min(9, (screen_h - 240) // 50))
    start, end = get_visible_window(len(menu_items), current_index, visible_count)

    y = 110
    if start > 0:
        more_above_surf, _ = small_font.render("^  more above  ^", accent)
        screen.blit(more_above_surf, (center_x(screen_w, more_above_surf.get_width()), 90))

    for idx in range(start, end):
        item = menu_items[idx]
        selected = idx == current_index
        color = hilite if selected else fg
        item_text = f"> {item}" if selected else f"  {item}"
        text_surf, _ = title_font.render(item_text, color)
        x = center_x(screen_w, text_surf.get_width())
        item_rect = text_surf.get_rect(topleft=(x, y))
        if selected:
            draw_active_panel(screen, item_rect, accent, fg)
        screen.blit(text_surf, item_rect)
        if selected:
            draw_focus_frame(screen, item_rect, hilite, accent)
            draw_action_emphasis(screen, item_rect, hilite)
        y += 50

    if end < len(menu_items):
        more_below_surf, _ = small_font.render("v  more below  v", accent)
        screen.blit(more_below_surf, (center_x(screen_w, more_below_surf.get_width()), y - 8))

    info = f"Unlocked Lessons: {unlocked_count} / {total_count}"
    info_surf, _ = small_font.render(info, accent)
    info_y = min(screen_h - 110, y + 20)
    screen.blit(info_surf, (center_x(screen_w, info_surf.get_width()), info_y))

    if streak_text:
        streak_surf, _ = small_font.render(streak_text, hilite)
        streak_y = min(screen_h - 80, info_y + 30)
        screen.blit(streak_surf, (center_x(screen_w, streak_surf.get_width()), streak_y))

    draw_controls_hint(
        screen=screen,
        small_font=small_font,
        text="Up/Down choose; Enter/Space select; Ctrl+Space repeat; Esc quit",
        screen_w=screen_w,
        y=get_footer_y(screen_h, padding=50),
        accent=accent,
    )


def draw_lesson_menu(
    *,
    screen,
    title_font,
    text_font,
    small_font,
    unlocked_lessons,
    lesson_names,
    current_index: int,
    screen_w: int,
    screen_h: int,
    fg,
    accent,
    hilite,
):
    title = "Select a Lesson"
    title_surf, _ = title_font.render(title, hilite)
    screen.blit(title_surf, (center_x(screen_w, title_surf.get_width()), 50))

    visible_count = max(6, min(9, (screen_h - 240) // 40))
    start, end = get_visible_window(len(unlocked_lessons), current_index, visible_count)

    y = 120
    if start > 0:
        more_above_surf, _ = small_font.render("^  more above  ^", accent)
        screen.blit(more_above_surf, (center_x(screen_w, more_above_surf.get_width()), 90))

    for idx in range(start, end):
        lesson_num = unlocked_lessons[idx]
        if lesson_num < len(lesson_names):
            lesson_name = lesson_names[lesson_num]
        else:
            lesson_name = f"Lesson {lesson_num}"
        text = f"Lesson {lesson_num}: {lesson_name}"

        selected = idx == current_index
        color = hilite if selected else fg
        item_text = f"> {text}" if selected else f"  {text}"
        text_surf, _ = text_font.render(item_text, color)
        x = center_x(screen_w, text_surf.get_width())
        item_rect = text_surf.get_rect(topleft=(x, y))
        if selected:
            draw_active_panel(screen, item_rect, accent, fg)
        screen.blit(text_surf, item_rect)
        if selected:
            draw_focus_frame(screen, item_rect, hilite, accent)
            draw_action_emphasis(screen, item_rect, hilite)
        y += 40

    if end < len(unlocked_lessons):
        more_surf, _ = small_font.render("v  more below  v", accent)
        screen.blit(more_surf, (center_x(screen_w, more_surf.get_width()), min(screen_h - 95, y - 8)))

    draw_controls_hint(
        screen=screen,
        small_font=small_font,
        text="Up/Down choose; Enter select; Esc menu",
        screen_w=screen_w,
        y=get_footer_y(screen_h, padding=50),
        accent=accent,
    )


def draw_games_menu(
    *,
    screen,
    title_font,
    text_font,
    small_font,
    games,
    current_index: int,
    screen_w: int,
    screen_h: int,
    fg,
    accent,
    hilite,
):
    title = "Select a Game"
    title_surf, _ = title_font.render(title, hilite)
    screen.blit(title_surf, (center_x(screen_w, title_surf.get_width()), 50))

    visible_count = max(4, min(6, (screen_h - 260) // 70))
    start, end = get_visible_window(len(games), current_index, visible_count)

    y = 120
    if start > 0:
        more_above_surf, _ = small_font.render("^  more above  ^", accent)
        screen.blit(more_above_surf, (center_x(screen_w, more_above_surf.get_width()), 90))

    for idx in range(start, end):
        game = games[idx]
        text = f"{game.NAME}"

        selected = idx == current_index
        color = hilite if selected else fg
        item_text = f"> {text}" if selected else f"  {text}"
        text_surf, _ = text_font.render(item_text, color)
        x = center_x(screen_w, text_surf.get_width())
        item_rect = text_surf.get_rect(topleft=(x, y))
        if selected:
            draw_active_panel(screen, item_rect, accent, fg)
        screen.blit(text_surf, item_rect)
        if selected:
            draw_focus_frame(screen, item_rect, hilite, accent)
            draw_action_emphasis(screen, item_rect, hilite)
        y += 40

        if selected:
            description_rect = draw_centered_wrapped_text(
                screen=screen,
                font=small_font,
                text=game.DESCRIPTION,
                color=accent,
                screen_w=screen_w,
                y=y,
                max_width=min(720, screen_w - 120),
                side_margin=60,
                line_gap=4,
            )
            y = description_rect.bottom + 8

    if end < len(games):
        more_surf, _ = small_font.render("v  more below  v", accent)
        screen.blit(more_surf, (center_x(screen_w, more_surf.get_width()), min(screen_h - 95, y - 8)))

    draw_controls_hint(
        screen=screen,
        small_font=small_font,
        text="Up/Down choose; Enter select; H hotkeys; Esc menu",
        screen_w=screen_w,
        y=get_footer_y(screen_h, padding=50),
        accent=accent,
    )


def draw_simple_menu(
    *,
    screen,
    title_font,
    text_font,
    small_font,
    title: str,
    items: list,
    current_index: int,
    screen_w: int,
    screen_h: int,
    fg,
    accent,
    hilite,
):
    """Render a plain list-of-strings menu.

    Extracted so a small submenu does not need a bespoke screen. Keeps the same
    focus frame, active panel and controls hint as the other menus, so the
    visual affordances stay consistent for sighted and low-vision users; the
    screen reader path is handled by the Menu class speaking each item.
    """
    title_surf, _ = title_font.render(title, hilite)
    screen.blit(title_surf, (center_x(screen_w, title_surf.get_width()), 50))

    visible_count = max(6, min(9, (screen_h - 240) // 40))
    start, end = get_visible_window(len(items), current_index, visible_count)

    y = 120
    if start > 0:
        more_above_surf, _ = small_font.render("^  more above  ^", accent)
        screen.blit(more_above_surf, (center_x(screen_w, more_above_surf.get_width()), 90))

    for idx in range(start, end):
        selected = idx == current_index
        color = hilite if selected else fg
        item_text = f"> {items[idx]}" if selected else f"  {items[idx]}"
        text_surf, _ = text_font.render(item_text, color)
        x = center_x(screen_w, text_surf.get_width())
        item_rect = text_surf.get_rect(topleft=(x, y))
        if selected:
            draw_active_panel(screen, item_rect, accent, fg)
        screen.blit(text_surf, item_rect)
        if selected:
            draw_focus_frame(screen, item_rect, hilite, accent)
            draw_action_emphasis(screen, item_rect, hilite)
        y += 40

    if end < len(items):
        more_surf, _ = small_font.render("v  more below  v", accent)
        screen.blit(more_surf, (center_x(screen_w, more_surf.get_width()), min(screen_h - 95, y - 8)))

    draw_controls_hint(
        screen=screen,
        small_font=small_font,
        text="Up/Down choose; Enter select; Esc menu",
        screen_w=screen_w,
        y=get_footer_y(screen_h, padding=50),
        accent=accent,
    )

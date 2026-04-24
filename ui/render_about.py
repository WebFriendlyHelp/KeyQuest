from ui.a11y import draw_action_emphasis, draw_active_panel, draw_controls_hint, draw_focus_frame
from ui.layout import center_x, get_footer_y


def draw_about_screen(
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
    version: str,
    about_items,
    current_index: int,
):
    """Draw the About screen."""
    title_surf, _ = title_font.render("About", hilite)
    screen.blit(title_surf, (center_x(screen_w, title_surf.get_width()), 40))

    version_surf, _ = small_font.render(f"KeyQuest {version}", accent)
    screen.blit(version_surf, (center_x(screen_w, version_surf.get_width()), 84))

    subtitle_surf, _ = text_font.render("Web Friendly Help LLC", fg)
    screen.blit(subtitle_surf, (center_x(screen_w, subtitle_surf.get_width()), 116))

    y = 180
    for idx, item in enumerate(about_items):
        selected = idx == current_index
        prefix = "> " if selected else "  "
        text = f"{prefix}{item['display']}"
        color = hilite if selected else fg
        surf, _ = text_font.render(text, color)
        rect = surf.get_rect(topleft=(80, y))
        if selected:
            draw_active_panel(screen, rect, accent, fg)
            draw_focus_frame(screen, rect, hilite, accent)
            draw_action_emphasis(screen, rect, hilite)
        screen.blit(surf, rect)
        y += 52

    draw_controls_hint(
        screen=screen,
        small_font=small_font,
        text="Enter select; Esc back",
        screen_w=screen_w,
        y=get_footer_y(screen_h, padding=50),
        accent=accent,
    )

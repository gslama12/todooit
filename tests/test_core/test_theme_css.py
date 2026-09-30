from todooit.api.theme import TokyoNight


def test_every_palette_color_is_a_css_variable():
    css = TokyoNight.to_css()

    for color in ("red", "orange", "yellow", "green", "blue", "purple", "magenta", "cyan"):
        assert f"${color}: {getattr(TokyoNight, color)};" in css

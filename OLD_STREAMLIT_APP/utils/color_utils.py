# utils/color_utils.py

# utils/color_utils.py
# utils/color_utils.py

def generate_random_color():
    """Generate a random HEX color."""
    import random
    r = random.randint(0, 255)
    g = random.randint(0, 255)
    b = random.randint(0, 255)
    return f"#{r:02X}{g:02X}{b:02X}"

def hex_to_rgba(hex_code, alpha=1.0):
    """Convert hex color to rgba format."""
    if hex_code.startswith("rgba"):
        return hex_code  # Already in correct format
    hex_code = hex_code.lstrip('#')
    r, g, b = tuple(int(hex_code[i:i+2], 16) for i in (0, 2, 4))
    return f"rgba({r}, {g}, {b}, {alpha})"

def rgba_to_hex(color_string):
    """Convert rgba color to hex format."""
    import re
    # If already hex, return as-is
    if isinstance(color_string, str) and color_string.startswith('#') and len(color_string) == 7:
        return color_string
    # If rgba, convert to hex
    match = re.match(r'rgba\((\d+),\s*(\d+),\s*(\d+),?.*\)', color_string)
    if match:
        r, g, b = match.groups()
        return '#{:02X}{:02X}{:02X}'.format(int(r), int(g), int(b))
    # fallback
    return '#000000'
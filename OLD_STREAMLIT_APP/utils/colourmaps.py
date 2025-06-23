# utils/colourmaps.py 

def palette_color_to_hex(color_tuple):
    """Convert a RGB tuple to a hex color string"""
    if color_tuple is None:
        return "#888888"  # Medium gray that won't stand out too much
    
    r, g, b = color_tuple
    return f"#{r:02X}{g:02X}{b:02X}"


def get_color_from_palette(index, alpha=1.0):
    """Return a color from a nature-inspired palette based on index"""
    palette = [
        (0, 128, 0),       # Green
        (34, 139, 34),     # Forest Green
        (85, 107, 47),     # Dark Olive Green
        (255, 99, 71),     # Tomato
        (255, 215, 0),     # Gold
        (70, 130, 180),    # Steel Blue
        (255, 99, 71),     # Coral
        (153, 50, 204),    # Dark Orchid
        (240, 128, 128),   # Light Coral
        (255, 222, 173),   # Navajo White
        (95, 158, 160),    # Cadet Blue
        (169, 169, 169)    # Dark Gray
    ]
    
    # Get the color from the palette
    idx = index % len(palette)
    color = palette[idx]
    
    # For alpha=1.0, return RGB tuple for consistent behavior with other palette functions
    if alpha == 1.0:
        return color
    
    # Convert the RGB tuple to rgba string
    r, g, b = color
    return f"rgba({r}, {g}, {b}, {alpha})"

def get_color_by_retention_time(rt, window=0.2, palette_func=None):
    """
    Get a color based on retention time, ensuring similar RTs get the same color.
    
    Parameters:
    -----------
    rt : float
        Retention time (midpoint) of the peak
    window : float
        Time window for grouping (default: 0.2)
    palette_func : function
        Function to get colors from a palette (default: None, uses current theme)
        
    Returns:
    --------
    tuple
        RGB color tuple
    """
    # Calculate a discrete "bin" for this retention time using the window size
    # This ensures peaks within the same window get the same color
    rt_bin = int(rt / window)
    
    # If no palette function is provided, use the default
    if palette_func is None:
        # Try to get current theme from session state
        current_theme = "get_color_from_palette"
        if 'plot_settings' in st.session_state and 'color_palette_function' in st.session_state.plot_settings:
            current_theme = st.session_state.plot_settings['color_palette_function']
        
        # Get the palette function
        import importlib
        colourmaps = importlib.import_module("utils.colourmaps")
        palette_func = getattr(colourmaps, current_theme)
    
    # Get color from the palette based on the RT bin
    # Add a prime number offset to avoid collisions with chromatogram indices
    color = palette_func(rt_bin * 7 + 3)  # Multiply by 7 and add 3 to create distinct spacing
    
    return color

def get_color_by_group_id(group_id, palette_func=None):
    """
    Get a color based on a peak group ID.
    
    Parameters:
    -----------
    group_id : int or str
        Group identifier for peaks with similar retention times
    palette_func : function
        Function to get colors from a palette (default: None, uses current theme)
        
    Returns:
    --------
    tuple
        RGB color tuple
    """
    # Convert group_id to a numeric hash if it's a string
    if isinstance(group_id, str):
        # Simple hash function
        hash_value = sum(ord(c) for c in group_id)
        numeric_id = hash_value
    else:
        numeric_id = int(group_id)
    
    # If no palette function is provided, use the default
    if palette_func is None:
        # Try to get current theme from session state
        current_theme = "get_color_from_palette"
        if 'plot_settings' in st.session_state and 'color_palette_function' in st.session_state.plot_settings:
            current_theme = st.session_state.plot_settings['color_palette_function']
        
        # Get the palette function
        import importlib
        colourmaps = importlib.import_module("utils.colourmaps")
        palette_func = getattr(colourmaps, current_theme)
    
    # Get color from the palette based on the group ID
    # Use a prime number multiplier to create good distribution
    color = palette_func(numeric_id * 11 + 7)  # Multiply by 11 and add 7 for better distribution
    
    return color

#=============================================================================
# Color Palettes for Scientific and Artistic Visualization
#=============================================================================


# ==== SCIENTIFIC QUALITATIVE (DISTINCT COLORS) ====

# ColorBrewer Set1 - Bold distinct colors
def get_set1_palette(index, alpha=1.0):
    """ColorBrewer Set1 - Bold distinct colors for categorical data"""
    palette = [
        (228, 26, 28),    # Red
        (55, 126, 184),   # Blue
        (77, 175, 74),    # Green
        (152, 78, 163),   # Purple
        (255, 127, 0),    # Orange
        (255, 255, 51),   # Yellow
        (166, 86, 40),    # Brown
        (247, 129, 191),  # Pink
        (153, 153, 153)   # Gray
    ]
    # Extend to ensure enough colors
    extended = palette * 2
    return extended[index % len(extended)]

# ColorBrewer Paired - Adjacent distinct hues
def get_paired_palette(index, alpha=1.0):
    """ColorBrewer Paired - Light/dark pairs of colors"""
    palette = [
        (166, 206, 227),  # Light Blue
        (31, 120, 180),   # Dark Blue
        (178, 223, 138),  # Light Green
        (51, 160, 44),    # Dark Green
        (251, 154, 153),  # Light Red
        (227, 26, 28),    # Dark Red
        (253, 191, 111),  # Light Orange
        (255, 127, 0),    # Dark Orange
        (202, 178, 214),  # Light Purple
        (106, 61, 154),   # Dark Purple
        (255, 255, 153),  # Light Yellow
        (177, 89, 40)     # Brown
    ]
    return palette[index % len(palette)]

# Tableau 10 - Modern categorical palette
def get_tableau10_palette(index, alpha=1.0):
    """Tableau 10 - Modern, vibrant categorical colors"""
    palette = [
        (31, 119, 180),   # Blue
        (255, 127, 14),   # Orange
        (44, 160, 44),    # Green
        (214, 39, 40),    # Red
        (148, 103, 189),  # Purple
        (140, 86, 75),    # Brown
        (227, 119, 194),  # Pink
        (127, 127, 127),  # Gray
        (188, 189, 34),   # Olive
        (23, 190, 207)    # Teal
    ]
    # Extend to ensure enough colors
    extended = palette * 2
    return extended[index % len(extended)]

# ==== SCIENTIFIC SEQUENTIAL (ORDERED PROGRESSION) ====

# Crameri Batlow - Perceptually uniform rainbow
def get_batlow_palette(index, alpha=1.0):
    """Batlow - Perceptually uniform rainbow (Crameri)"""
    palette = [
        (0, 20, 44),      # Dark blue
        (10, 64, 80),     # Blue-teal
        (41, 93, 93),     # Teal
        (83, 108, 95),    # Gray-teal
        (125, 117, 87),   # Olive
        (162, 117, 76),   # Tan
        (188, 112, 69),   # Burnt orange
        (206, 102, 66),   # Orange
        (214, 86, 68),    # Salmon
        (213, 58, 74),    # Pink-red
        (191, 17, 72)     # Red
    ]
    extended_palette = palette + palette[:5]
    return extended_palette[index % len(extended_palette)]

# Viridis - Perceptually uniform blue-green-yellow
def get_viridis_palette(index, alpha=1.0):
    """Viridis - Perceptually uniform blue-green-yellow"""
    palette = [
        (68, 1, 84),      # Dark purple
        (72, 40, 120),    # Purple
        (62, 73, 137),    # Blue-purple
        (49, 104, 142),   # Blue
        (38, 130, 142),   # Blue-green
        (31, 158, 137),   # Teal
        (53, 183, 121),   # Green
        (109, 205, 89),   # Lime green
        (180, 222, 44),   # Yellow-green
        (253, 231, 37)    # Yellow
    ]
    extended_palette = palette + palette[:5]
    return extended_palette[index % len(extended_palette)]

# Crameri Lajolla - Peach/Terracotta palette
def get_lajolla_palette(index, alpha=1.0):
    """Lajolla - Beautiful earth tone progression (Crameri)"""
    palette = [
        (19, 15, 35),     # Dark purple
        (42, 26, 44),     # Purple
        (70, 36, 44),     # Burgundy
        (100, 45, 40),    # Brown
        (130, 58, 37),    # Rust
        (158, 73, 41),    # Terracotta 
        (188, 97, 53),    # Orange-brown
        (213, 125, 69),   # Light orange
        (231, 163, 99),   # Peach
        (239, 202, 151),  # Light peach
        (245, 236, 211)   # Cream
    ]
    extended_palette = palette + palette[:5]
    return extended_palette[index % len(extended_palette)]

# ==== SCIENTIFIC DIVERGING (CENTERED) ====

# Crameri Turku - Blue-white-red
def get_turku_palette(index, alpha=1.0):
    """Turku - Diverging blue-white-red (Crameri)"""
    palette = [
        (21, 40, 106),    # Dark blue
        (66, 81, 139),    # Blue
        (108, 126, 170),  # Light blue
        (155, 176, 200),  # Pale blue
        (207, 218, 225),  # White-blue
        (245, 245, 245),  # White
        (242, 218, 205),  # White-red
        (229, 179, 170),  # Pale red
        (209, 129, 132),  # Light red
        (177, 71, 94),    # Red
        (138, 25, 60)     # Dark red
    ]
    extended_palette = palette + palette[:5]
    return extended_palette[index % len(extended_palette)]

# ColorBrewer RdYlBu - Classic red-yellow-blue
def get_rdylbu_palette(index, alpha=1.0):
    """RdYlBu - ColorBrewer's Red-Yellow-Blue diverging palette"""
    palette = [
        (165, 0, 38),     # Dark red
        (215, 48, 39),    # Red
        (244, 109, 67),   # Light red
        (253, 174, 97),   # Orange
        (254, 224, 144),  # Yellow
        (255, 255, 191),  # Pale yellow
        (224, 243, 248),  # Pale blue
        (171, 217, 233),  # Light blue
        (116, 173, 209),  # Blue
        (69, 117, 180),   # Medium blue
        (49, 54, 149)     # Dark blue
    ]
    extended_palette = palette + palette[:5]
    return extended_palette[index % len(extended_palette)]

# ==== ARTISTIC PALETTES ====

# Wes Anderson Palette
def get_wes_anderson_palette(index, alpha=1.0):
    """Wes Anderson film-inspired palette - cinematic and nostalgic"""
    palette = [
        (120, 192, 186),  # Mendl's Blue (Grand Budapest Hotel)
        (225, 85, 84),    # Red (The Royal Tenenbaums)
        (232, 182, 71),   # Mustard (Fantastic Mr. Fox)
        (86, 125, 70),    # Green (Moonrise Kingdom)
        (197, 222, 221),  # Pale Blue (The Life Aquatic)
        (192, 146, 151),  # Dusty Rose (Grand Budapest Hotel)
        (210, 202, 171),  # Beige (Fantastic Mr. Fox)
        (236, 202, 223),  # Pale Pink (Grand Budapest Hotel)
        (249, 163, 27),   # Orange (Darjeeling Limited)
        (135, 162, 177),  # Steel Blue (The Life Aquatic)
        (78, 73, 95),     # Deep Purple (Grand Budapest Hotel)
        (120, 116, 48)    # Olive (Fantastic Mr. Fox)
    ]
    return palette[index % len(palette)]

# Retro 80s Palette
def get_retro80s_palette(index, alpha=1.0):
    """1980s retro-wave inspired neon colors"""
    palette = [
        (255, 89, 253),   # Hot Pink
        (74, 246, 242),   # Cyan
        (255, 254, 141),  # Bright Yellow 
        (147, 79, 249),   # Purple
        (0, 227, 147),    # Bright Green
        (255, 128, 56),   # Orange
        (0, 142, 255),    # Electric Blue
        (90, 17, 179),    # Deep Purple
        (255, 46, 100),   # Flamingo Pink
        (49, 230, 227),   # Turquoise
        (252, 238, 33),   # Yellow
        (240, 138, 255)   # Lavender
    ]
    return palette[index % len(palette)]

# Vintage Print Palette
def get_vintage_print_palette(index, alpha=1.0):
    """Vintage print/poster colors - muted but distinct"""
    palette = [
        (217, 80, 64),    # Brick Red
        (42, 113, 125),   # Teal
        (231, 173, 94),   # Mustard
        (107, 123, 137),  # Slate Blue
        (203, 126, 115),  # Dusty Rose
        (81, 149, 141),   # Sage Green
        (245, 223, 187),  # Cream
        (169, 120, 108),  # Taupe
        (186, 190, 180),  # Light Gray
        (91, 76, 73),     # Dark Brown
        (226, 137, 94),   # Terracotta
        (115, 123, 76)    # Olive
    ]
    return palette[index % len(palette)]

# ==== FUN EASTER EGG PALETTES ====

# Candy Palette
def get_candy_palette(index, alpha=1.0):
    """Sweet candy colors - bright and playful"""
    palette = [
        (255, 105, 180),  # Hot Pink
        (127, 255, 212),  # Aquamarine
        (255, 218, 185),  # Peach
        (152, 251, 152),  # Pale Green
        (255, 182, 193),  # Light Pink
        (135, 206, 250),  # Light Sky Blue
        (255, 160, 122),  # Light Salmon
        (221, 160, 221),  # Plum
        (240, 230, 140),  # Khaki
        (255, 192, 203),  # Pink
        (173, 216, 230),  # Light Blue
        (255, 255, 224)   # Light Yellow
    ]
    return palette[index % len(palette)]

# Fruits Palette
def get_fruits_palette(index, alpha=1.0):
    """Fruit-inspired colors - juicy and natural"""
    palette = [
        (255, 50, 20),    # Strawberry
        (255, 140, 0),    # Orange
        (255, 230, 0),    # Lemon
        (173, 255, 47),   # Lime
        (75, 130, 0),     # Green Apple
        (0, 0, 139),      # Blueberry
        (160, 32, 240),   # Grape
        (255, 0, 255),    # Dragon Fruit
        (255, 192, 203),  # Watermelon
        (210, 105, 30),   # Coconut
        (139, 69, 19),    # Kiwi
        (255, 218, 185)   # Peach
    ]
    return palette[index % len(palette)]

# Midnight Synthwave
def get_midnight_synthwave_palette(index, alpha=1.0):
    """Midnight synthwave - dark with neon accents"""
    palette = [
        (5, 5, 25),       # Deep Night
        (25, 10, 40),     # Midnight Purple
        (40, 15, 60),     # Twilight
        (80, 20, 100),    # Deep Purple
        (130, 25, 105),   # Magenta
        (160, 40, 120),   # Bright Magenta
        (200, 60, 130),   # Hot Pink
        (215, 90, 140),   # Neon Pink
        (95, 30, 180),    # Electric Purple
        (60, 100, 190),   # Deep Blue
        (80, 180, 220),   # Neon Blue
        (100, 220, 255)   # Cyan
    ]
    return palette[index % len(palette)]

# Hidden Crayon Box (Easter Egg)
def get_crayon_box_palette(index, alpha=1.0):
    """Crayon box colors - childlike and nostalgic"""
    palette = [
        (237, 10, 63),    # Red (Apple)
        (255, 127, 30),   # Orange
        (253, 218, 13),   # Yellow
        (35, 132, 67),    # Green
        (0, 149, 183),    # Blue
        (107, 63, 160),   # Purple
        (215, 0, 96),     # Pink
        (232, 122, 144),  # Salmon
        (118, 93, 97),    # Brown
        (168, 228, 160),  # Mint Green
        (180, 103, 77),   # Burnt Sienna
        (255, 195, 11)    # Goldenrod
    ]
    return palette[index % len(palette)]

# Gameboy Palette (Easter Egg)
def get_gameboy_palette(index, alpha=1.0):
    """Original 4-color Gameboy palette - retro gaming nostalgia"""
    palette = [
        (15, 56, 15),     # Darkest Green
        (48, 98, 48),     # Dark Green
        (139, 172, 15),   # Light Green
        (155, 188, 15),   # Lightest Green
        # Repeat to ensure enough colors
        (15, 56, 15),     # Darkest Green
        (48, 98, 48),     # Dark Green
        (139, 172, 15),   # Light Green
        (155, 188, 15),   # Lightest Green
        (15, 56, 15),     # Darkest Green
        (48, 98, 48),     # Dark Green
        (139, 172, 15),   # Light Green
        (155, 188, 15),   # Lightest Green
    ]
    return palette[index % len(palette)]
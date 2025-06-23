import streamlit as st


def load_css(css_path: str) -> None:
    """
    Read a CSS file and inject into the Streamlit app.

    Parameters:
    - css_path: path to a .css file
    """
    try:
        with open(css_path, 'r') as f:
            css = f.read()
        st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)
    except FileNotFoundError:
        st.warning(f"CSS file not found: {css_path}")


def inject_css(css_string: str) -> None:
    """
    Directly inject a CSS string into the Streamlit app.

    Parameters:
    - css_string: raw CSS rules
    """
    st.markdown(f"<style>{css_string}</style>", unsafe_allow_html=True)


def set_page_style(title: str = None, favicon: str = None, layout: str = 'wide', initial_sidebar_state: str = 'auto') -> None:
    """
    Convenience wrapper for Streamlit's set_page_config.

    Parameters:
    - title: page title
    - favicon: path or emoji for favicon
    - layout: 'centered' or 'wide'
    - initial_sidebar_state: 'auto', 'expanded', or 'collapsed'
    """
    st.set_page_config(page_title=title, page_icon=favicon, layout=layout, initial_sidebar_state=initial_sidebar_state)


def inject_google_font(font_family: str = 'Roboto') -> None:
    """
    Inject Google Fonts into the app for custom typography.

    Parameters:
    - font_family: font family name as on Google Fonts
    """
    link = f"<link href='https://fonts.googleapis.com/css2?family={font_family.replace(' ', '+')}&display=swap' rel='stylesheet'>"
    st.markdown(link, unsafe_allow_html=True)


def apply_custom_theme(theme: dict) -> None:
    """
    Apply a custom Streamlit theme by injecting CSS variables.

    Parameters:
    - theme: dict of CSS variable names to values, e.g. {'--primary-color': '#ff0000'}
    """
    css_lines = [f"{var}: {val};" for var, val in theme.items()]
    css = ":root {" + "".join(css_lines) + "}"
    st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)
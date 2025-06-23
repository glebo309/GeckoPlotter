import streamlit as st
from lcms.cdf_reader import load_cdf, get_mass_spectrum
from lcms.ms_plotter import plot_tic, plot_mass_spectrum

def render_lcms_view():
    st.title("🧬 LC–MS Viewer")

    uploaded_file = st.file_uploader("Upload LC–MS CDF File", type=["cdf"])
    if uploaded_file:
        rt, tic, tmp_path = load_cdf(uploaded_file)

        st.plotly_chart(plot_tic(rt, tic), use_container_width=True)

        scan = st.slider("Select Scan Index", 0, len(rt)-1, 0)

        mz, intensity = get_mass_spectrum(tmp_path, scan)

        st.plotly_chart(plot_mass_spectrum(mz, intensity), use_container_width=True)

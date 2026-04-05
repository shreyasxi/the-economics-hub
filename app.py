import streamlit as st
import os
import glob
from datetime import datetime

# 1. Page Configuration
st.set_page_config(
    page_title="The Economics Hub | Global Dashboard",
    page_icon="🌍",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 2. Inject Custom CSS for Premium UI styling
st.markdown("""
    <style>
    .block-container {
        padding-top: 2rem;
        padding-bottom: 2rem;
    }
    h1 {
        font-weight: 700;
        letter-spacing: -0.02em;
        margin-bottom: 0.5rem;
    }
    .stImage > img {
        border-radius: 8px;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);
        transition: transform 0.2s ease, box-shadow 0.2s ease;
    }
    .stImage > img:hover {
        transform: translateY(-2px);
        box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.1), 0 4px 6px -2px rgba(0, 0, 0, 0.05);
    }
    [data-testid="stSidebar"] {
        background-color: #f8f9fa;
        border-right: 1px solid #e5e7eb;
    }
    </style>
""", unsafe_allow_html=True)

# 3. Helper Functions
def render_image_grid(image_paths, cols=2):
    """Renders a list of images in a clean, responsive grid."""
    if not image_paths:
        st.warning("No charts available for this category.")
        return
    
    columns = st.columns(cols)
    for i, img_path in enumerate(image_paths):
        # Extract a clean title from the filename (e.g., '01_macro_inflation.png' -> 'Macro Inflation')
        filename = os.path.basename(img_path)
        clean_title = filename.split('.')[0].split('_', 1)[-1].replace('_', ' ').title()
        
        with columns[i % cols]:
            st.image(img_path, caption=clean_title, use_container_width=True)
            st.markdown("<br>", unsafe_allow_html=True)

# 4. Fetch All Active Charts
# We now ONLY look inside the ephemeral hosted_charts folder
all_images = []
if os.path.exists("hosted_charts"):
    all_images = sorted(glob.glob("hosted_charts/*.png"))

# 5. Sidebar Layout
with st.sidebar:
    st.title("📊 Economics Hub")
    st.markdown("Automated macroeconomic & financial tracking.")
    st.markdown("---")
    
    view_mode = st.radio("Select View", ["Global Macro", "Weekly Markets", "India Setup (WIP)"])
    
    st.markdown("---")
    st.caption(f"App Last Refreshed: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
    st.caption("Data sources: FRED, Yahoo Finance")

# 6. Main Dashboard Routing
if not all_images:
    st.warning("The dashboard is currently updating or awaiting its first data run. Please check back shortly.")
else:
    if view_mode == "Global Macro":
        st.title("Global Macroeconomic Environment")
        # Filter for filenames containing 'macro'
        macro_images = [img for img in all_images if "macro" in os.path.basename(img).lower()]
        render_image_grid(macro_images, cols=2)

    elif view_mode == "Weekly Markets":
        st.title("Weekly Cross-Asset Performance")
        # Filter out macro and india to get the general weekly charts
        weekly_images = [img for img in all_images if "macro" not in os.path.basename(img).lower() and "india" not in os.path.basename(img).lower()]
        
        # Pull out the summary table specifically to feature it at the top
        summary_img = next((img for img in weekly_images if "summary" in os.path.basename(img).lower()), None)
        
        if summary_img:
            st.subheader("Market Summary")
            st.image(summary_img, use_container_width=True)
            st.markdown("<br>", unsafe_allow_html=True)
            weekly_images.remove(summary_img) # Remove so it doesn't render twice
            
        st.subheader("Asset Class Deep Dives")
        render_image_grid(weekly_images, cols=2)

    elif view_mode == "India Setup (WIP)":
        st.title("India Domestic Indicators")
        st.info("India data pipeline relies on manual CSV uploads. Automated parsing framework is under construction.")
        # Filter for filenames containing 'india'
        india_images = [img for img in all_images if "india" in os.path.basename(img).lower()]
        render_image_grid(india_images, cols=2)
import streamlit as st
import os
import glob
from datetime import datetime

# 1. Page Configuration (Must be the first Streamlit command)
st.set_page_config(
    page_title="The Economics Hub | Global Dashboard",
    page_icon="🌍",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 2. Inject Custom CSS for Premium UI styling
st.markdown("""
    <style>
    /* Clean up the main UI */
    .block-container {
        padding-top: 2rem;
        padding-bottom: 2rem;
    }
    /* Style headers */
    h1 {
        font-weight: 700;
        letter-spacing: -0.02em;
        margin-bottom: 0.5rem;
    }
    /* Chart container hover effects */
    .stImage > img {
        border-radius: 8px;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);
        transition: transform 0.2s ease, box-shadow 0.2s ease;
    }
    .stImage > img:hover {
        transform: translateY(-2px);
        box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.1), 0 4px 6px -2px rgba(0, 0, 0, 0.05);
    }
    /* Style the sidebar */
    [data-testid="stSidebar"] {
        background-color: #f8f9fa;
        border-right: 1px solid #e5e7eb;
    }
    </style>
""", unsafe_allow_html=True)

# 3. Helper Functions
def get_latest_folder(base_path):
    """Finds the most recent date-stamped folder in a directory."""
    if not os.path.exists(base_path):
        return None
    folders = [f for f in os.listdir(base_path) if os.path.isdir(os.path.join(base_path, f))]
    if not folders:
        return None
    # Sort descending to get the newest folder first
    folders.sort(reverse=True) 
    return folders[0]

def render_image_grid(image_paths, cols=2):
    """Renders a list of images in a clean, responsive grid."""
    if not image_paths:
        st.warning("No charts available for this period.")
        return
    
    # Create columns dynamically
    columns = st.columns(cols)
    for i, img_path in enumerate(image_paths):
        # Extract a clean title from the filename (e.g., '01_macro_inflation.png' -> 'Macro Inflation')
        filename = os.path.basename(img_path)
        clean_title = filename.split('.')[0].split('_', 1)[-1].replace('_', ' ').title()
        
        with columns[i % cols]:
            st.image(img_path, caption=clean_title, use_container_width=True)
            st.markdown("<br>", unsafe_allow_html=True) # Spacing between rows

# 4. Sidebar Layout
with st.sidebar:
    st.title("📊 Economics Hub")
    st.markdown("Automated macroeconomic & financial tracking.")
    st.markdown("---")
    
    view_mode = st.radio("Select View", ["Global Macro", "Weekly Markets", "India Setup (WIP)"])
    
    st.markdown("---")
    st.caption(f"App Last Refreshed: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
    st.caption("Data sources: FRED, Yahoo Finance")

# 5. Main Dashboard Routing
if view_mode == "Global Macro":
    st.title("Global Macroeconomic Environment")
    latest_macro = get_latest_folder("assets/macro")
    
    if latest_macro:
        st.markdown(f"**Latest Data Cut:** `{latest_macro}`")
        images = sorted(glob.glob(f"assets/macro/{latest_macro}/*.png"))
        render_image_grid(images, cols=2)
    else:
        st.info("Macro data directory is empty or currently updating.")

elif view_mode == "Weekly Markets":
    st.title("Weekly Cross-Asset Performance")
    latest_weekly = get_latest_folder("assets/weekly")
    
    if latest_weekly:
        st.markdown(f"**Latest Data Cut:** `{latest_weekly}`")
        
        # Pull out the summary table specifically to feature it at the top
        summary_img = f"assets/weekly/{latest_weekly}/00_summary_table.png"
        if os.path.exists(summary_img):
            st.subheader("Market Summary")
            st.image(summary_img, use_container_width=True)
            st.markdown("<br>", unsafe_allow_html=True)
        
        st.subheader("Asset Class Deep Dives")
        # Get all other images except the summary
        other_images = sorted([img for img in glob.glob(f"assets/weekly/{latest_weekly}/*.png") if "00_summary_table" not in img])
        render_image_grid(other_images, cols=2)
    else:
        st.info("Weekly data directory is empty or currently updating.")

elif view_mode == "India Setup (WIP)":
    st.title("India Domestic Indicators")
    st.info("India data pipeline relies on manual CSV uploads. Automated parsing framework is under construction.")
    # Placeholder for when you bring generate_india.py online
    latest_india = get_latest_folder("assets/india")
    if latest_india:
        images = sorted(glob.glob(f"assets/india/{latest_india}/*.png"))
        render_image_grid(images, cols=2)

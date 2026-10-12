"""Shared responsive chart placement for every Portfolio Lab view."""
import streamlit as st


def centered_chart(chart, width=900, stretch=True):
    # Fixed maximum width shrinks to the available space on narrow screens
    # and inside side-by-side panels; the outer row keeps it centered.
    with st.container(horizontal=True, horizontal_alignment="center"):
        if stretch:
            with st.container(width=width):
                st.altair_chart(chart, use_container_width=True, theme=None)
        else:
            with st.container(width=int(chart.width)):
                st.altair_chart(chart, use_container_width=False, theme=None)


def centered_note(text):
    from html import escape
    st.markdown('<p class="pl-centered-note">'+escape(text)+'</p>',unsafe_allow_html=True)


def research_navigation(key):
    with st.container(key='pl-research-navigation'):
        return st.radio('Research view',['Overview','Performance Attribution','Risk','Macro Regimes','Stress Testing'],horizontal=True,key=key)


def centered_dataframe(frame):
    with st.container(horizontal=True,horizontal_alignment='center'):
        with st.container(width=760):
            st.dataframe(frame,use_container_width=True)

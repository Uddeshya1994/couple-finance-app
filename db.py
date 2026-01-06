import streamlit as st
import psycopg

def get_connection():
    return psycopg.connect(st.secrets["DATABASE_URL"])

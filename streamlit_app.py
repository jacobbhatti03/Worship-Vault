import streamlit as st
from pathlib import Path
from datetime import datetime
from supabase import create_client
import os

# -------------------------------
# CONFIG
# -------------------------------
SUPABASE_URL = st.secrets.get("SUPABASE_URL") or os.getenv("SUPABASE_URL")
SUPABASE_KEY = st.secrets.get("SUPABASE_KEY") or os.getenv("SUPABASE_KEY")
MASTER_ADMIN_KEY = st.secrets.get("MASTER_ADMIN_KEY") or os.getenv("MASTER_ADMIN_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    st.error("❌ Missing Supabase credentials.")
    st.stop()

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# -------------------------------
# BUCKET HELPER
# -------------------------------
def create_bucket_if_needed(bucket_name: str):
    """Ensure bucket exists before upload."""
    try:
        res = supabase.storage.get_buckets()
        buckets = res.get("data", []) if isinstance(res, dict) else []
        if any((b.get("name") == bucket_name) for b in buckets if isinstance(b, dict)):
            return
        supabase.storage.create_bucket(bucket_name, public=False)
    except Exception as e:
        st.error(f"Bucket check failed: {e}")

def upload_to_bucket(bucket_name: str, file_obj, filename: str):
    """Upload file to Supabase bucket (auto-create if missing)."""
    try:
        create_bucket_if_needed(bucket_name)
        data = file_obj.getbuffer().tobytes() if hasattr(file_obj, "getbuffer") else file_obj.read()
        supabase.storage.from_(bucket_name).upload(filename, data)
        return True
    except Exception as e:
        st.error(f"Upload failed: {e}")
        return False

# -------------------------------
# GALLERY PAGE
# -------------------------------
def gallery_page(vault_name: str):
    st.title(f"📁 {vault_name} Gallery")

    try:
        res = supabase.storage.from_(vault_name).list()
        if not res or not isinstance(res, list):
            st.info("No files found.")
            return

        for file in res:
            name = file.get("name", "unknown")
            url = f"{SUPABASE_URL}/storage/v1/object/public/{vault_name}/{name}"
            st.markdown(f"📄 [{name}]({url})")
    except Exception as e:
        st.error(f"Failed to load gallery: {e}")

    if st.button("⬅️ Back to Vault", use_container_width=True):
        st.session_state["page"] = "vault"
        st.rerun()

# -------------------------------
# VAULT PAGE
# -------------------------------
def vault_page(vault_name: str):
    st.subheader(f"🔒 Vault: {vault_name}")

    col1, col2 = st.columns([1, 3])

    with col1:
        if st.button("📁 Gallery", use_container_width=True):
            st.session_state["page"] = "gallery"
            st.session_state["vault_name"] = vault_name
            st.rerun()

    with col2:
        file = st.file_uploader("Upload File", type=["png", "jpg", "jpeg", "pdf", "txt"])
        if file:
            if upload_to_bucket(vault_name, file, file.name):
                st.success("✅ Upload complete!")

# -------------------------------
# MAIN APP
# -------------------------------
st.title("📚 Worship Vault")

# Initialize navigation state
if "page" not in st.session_state:
    st.session_state["page"] = "home"

# HOME PAGE
if st.session_state["page"] == "home":
    vault_name = st.text_input("Enter Vault Name")
    if vault_name:
        if st.button("Enter Vault", use_container_width=True):
            st.session_state["vault_name"] = vault_name
            st.session_state["page"] = "vault"
            st.rerun()

# VAULT PAGE
elif st.session_state["page"] == "vault":
    vault_page(st.session_state.get("vault_name", ""))

# GALLERY PAGE
elif st.session_state["page"] == "gallery":
    gallery_page(st.session_state.get("vault_name", ""))

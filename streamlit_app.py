# app.py
import streamlit as st
from pathlib import Path
from dotenv import load_dotenv
import os, math
from uuid import uuid4

# ---------------------------
# Config
# ---------------------------
load_dotenv()

VAULTS_FOLDER = Path("vaults")
VAULTS_FOLDER.mkdir(exist_ok=True)

MASTER_ADMIN_KEY = os.getenv("MASTER_ADMIN_KEY", "YOUR_MASTER_KEY")

# ---------------------------
# Session state defaults
# ---------------------------
defaults = {
    "vault_name": None,
    "is_admin_internal": False,
    "member_key": None,
    "page": "home",
    "action": None
}
for k, v in defaults.items():
    st.session_state.setdefault(k, v)

# ---------------------------
# Helpers
# ---------------------------
def go_home():
    for k in ["vault_name", "is_admin_internal", "member_key", "page", "action"]:
        st.session_state[k] = None if k != "page" else "home"

def vault_path(name: str):
    path = VAULTS_FOLDER / name
    path.mkdir(exist_ok=True)
    return path

def list_files(vault_name):
    path = vault_path(vault_name)
    return sorted(
        [f.name for f in path.iterdir() if f.is_file() and not f.name.startswith(".")],
        key=lambda s: s.lower(),
    )

def save_file(vault_name, uploaded_file):
    path = vault_path(vault_name) / uploaded_file.name
    with open(path, "wb") as f:
        f.write(uploaded_file.getbuffer())

def rename_file(vault_name, old_name, new_name):
    """Safely rename a file by copying then deleting the old one."""
    old_path = vault_path(vault_name) / old_name
    new_path = vault_path(vault_name) / new_name

    # Don’t allow overwriting existing files
    if not old_path.exists():
        return False
    if new_path.exists():
        return False

    try:
        # Copy content safely
        with open(old_path, "rb") as src, open(new_path, "wb") as dst:
            dst.write(src.read())
        old_path.unlink()  # Delete old only if copy succeeded
        return True
    except Exception as e:
        print(f"Rename failed: {e}")
        return False


def delete_file(vault_name, filename):
    path = vault_path(vault_name) / filename
    if path.exists():
        path.unlink()
        return True
    return False

# ---------------------------
# Pages
# ---------------------------
def vault_page():
    vault_name = st.session_state.vault_name
    st.header(f"📂 Vault — {vault_name}")

    c1, c2 = st.columns([1, 1])
    if c1.button("⬅ Back to home"):
        go_home()
        st.session_state.action = "home"
    if c2.button("📸 Open Gallery"):
        st.session_state.page = "gallery"
        st.session_state.action = "gallery"

    uploaded_files = st.file_uploader("Upload images (lyrics, posters, etc.)", accept_multiple_files=True, type=["png", "jpg", "jpeg", "webp"])
    if uploaded_files:
        for f in uploaded_files:
            save_file(vault_name, f)
        st.success("✅ Uploaded successfully!")

def gallery_page():
    vault_name = st.session_state.vault_name
    st.header(f"🖼️ Gallery — {vault_name}")

    if st.button("⬅ Back to Vault"):
        st.session_state.page = "vault"
        st.session_state.action = "vault"

    # --- Search bar ---
    search_query = st.text_input("🔍 Search lyrics or image name", placeholder="Type to search...").strip().lower()

    files = list_files(vault_name)
    # Only show image types
    files = [f for f in files if f.split(".")[-1].lower() in ("jpg", "jpeg", "png", "gif", "webp")]

    # Filter files by search term (ignore extension)
    if search_query:
        files = [f for f in files if search_query in f.lower().replace(".jpg", "").replace(".jpeg", "").replace(".png", "").replace(".webp", "").replace(".gif", "")]

    if not files:
        st.info("No matching images found.")
        return

    per_row = 3
    rows = math.ceil(len(files) / per_row)
    idx = 0

    for _ in range(rows):
        cols = st.columns(per_row, gap="large")
        for c in range(per_row):
            if idx >= len(files):
                break
            fname = files[idx]
            with cols[c]:
                st.image(str(vault_path(vault_name) / fname))
                st.markdown(f"**{fname}**")

                # Admin-only options
                if st.session_state.is_admin_internal:
                    new_name = st.text_input("Rename to", value=fname, key=f"rename_{fname}")
                    if st.button("Rename", key=f"btn_rn_{fname}"):
                        rename_file(vault_name, fname, new_name)
                        st.session_state.action = "refresh"
                    if st.button("Delete", key=f"btn_del_{fname}"):
                        delete_file(vault_name, fname)
                        st.session_state.action = "refresh"
            idx += 1

def home_page():
    st.title("🙏 Worship Vault")
    st.divider()

    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Enter existing vault")
        vault_name = st.text_input("Vault name", key="login_vault_name")
        member_pass = st.text_input("Vault password (member)", type="password", key="login_vault_pass")
        admin_pass = st.text_input("Vault admin passkey", type="password", key="login_vault_admin_pass")

        if st.button("Open vault"):
            path = vault_path(vault_name)
            vault_pass_file = path / ".vault_pass"
            admin_pass_file = path / ".admin_pass"

            if not path.exists() or not vault_pass_file.exists():
                st.error("Vault not found.")
            else:
                vault_member_pass = vault_pass_file.read_text()
                vault_admin_pass = admin_pass_file.read_text() if admin_pass_file.exists() else vault_member_pass

                # LOGIN LOGIC
                if member_pass == MASTER_ADMIN_KEY:
                    st.session_state.vault_name = vault_name
                    st.session_state.is_admin_internal = True
                    st.session_state.member_key = "MASTER_ADMIN"
                elif admin_pass:
                    if admin_pass == vault_admin_pass:
                        st.session_state.vault_name = vault_name
                        st.session_state.is_admin_internal = True
                        st.session_state.member_key = "VAULT_ADMIN"
                    else:
                        st.error("Incorrect admin passkey.")
                        st.stop()
                elif member_pass == vault_member_pass:
                    st.session_state.vault_name = vault_name
                    st.session_state.is_admin_internal = False
                    st.session_state.member_key = "MEMBER"
                else:
                    st.error("Incorrect password.")
                    st.stop()

                st.session_state.page = "vault"
                st.session_state.action = "vault"

    with c2:
        st.subheader("Create new vault")
        new_name = st.text_input("Vault name", key="new_vault_name")
        vault_pass_new = st.text_input("Vault passkey (member)", type="password", key="new_vault_pass")
        admin_pass_new = st.text_input("Vault admin passkey", type="password", key="new_vault_admin_pass")

        if st.button("Create vault"):
            if not new_name or not vault_pass_new or not admin_pass_new:
                st.warning("Fill all fields")
            else:
                path = vault_path(new_name)
                (path / ".vault_pass").write_text(vault_pass_new)
                (path / ".admin_pass").write_text(admin_pass_new)

                st.session_state.vault_name = new_name
                st.session_state.is_admin_internal = True
                st.session_state.member_key = "VAULT_ADMIN"
                st.session_state.page = "vault"
                st.session_state.action = "vault"

# ---------------------------
# Routing
# ---------------------------
if st.session_state.page == "home":
    home_page()
elif st.session_state.page == "vault":
    vault_page()
elif st.session_state.page == "gallery":
    gallery_page()

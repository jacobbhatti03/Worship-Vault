# app.py
import streamlit as st
from pathlib import Path
from dotenv import load_dotenv
import os, math, json
from uuid import uuid4

# ---------------------------
# Config
# ---------------------------
load_dotenv()

VAULTS_FOLDER = Path("vaults")
VAULTS_FOLDER.mkdir(exist_ok=True)

# Persistent device ID
DEVICE_FILE = Path("device.id")
if not DEVICE_FILE.exists():
    DEVICE_FILE.write_text(str(uuid4()))
DEVICE_ID = DEVICE_FILE.read_text().strip()

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
    old_path = vault_path(vault_name) / old_name
    new_path = vault_path(vault_name) / new_name
    if old_path.exists():
        old_path.rename(new_path)
        return True
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

    uploaded_files = st.file_uploader("Upload images/PDFs", accept_multiple_files=True)
    if uploaded_files:
        for f in uploaded_files:
            save_file(vault_name, f)
        st.success("Uploaded successfully!")

def gallery_page():
    vault_name = st.session_state.vault_name
    st.header(f"🖼️ Gallery — {vault_name}")

    if st.button("⬅ Back to Vault"):
        st.session_state.page = "vault"
        st.session_state.action = "vault"

    files = list_files(vault_name)
    if not files:
        st.info("No files yet.")
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
            ext = fname.split(".")[-1].lower()
            with cols[c]:
                if ext in ("jpg", "jpeg", "png", "gif", "webp"):
                    st.image(str(vault_path(vault_name) / fname))
                else:
                    st.write("📄 File")

                st.markdown(f"**{fname}**")

                # Admin-only actions
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

    # Auto-login if this device owns any vault
    auto_vault = None
    for v in VAULTS_FOLDER.iterdir():
        if v.is_dir() and (v / ".creator_device").exists():
            creator = (v / ".creator_device").read_text().strip()
            if creator == DEVICE_ID:
                auto_vault = v.name
                break

    if auto_vault:
        st.info(f"💾 This device owns vault: **{auto_vault}**")
        if st.button("Login as Admin"):
            st.session_state.vault_name = auto_vault
            st.session_state.is_admin_internal = True
            st.session_state.member_key = "VAULT_ADMIN"
            st.session_state.page = "vault"
            st.session_state.action = "vault"

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
            creator_file = path / ".creator_device"

            if not path.exists() or not vault_pass_file.exists():
                st.error("Vault not found.")
            else:
                vault_member_pass = vault_pass_file.read_text()
                vault_admin_pass = admin_pass_file.read_text() if admin_pass_file.exists() else vault_member_pass
                creator_device = creator_file.read_text().strip() if creator_file.exists() else ""

                if member_pass == MASTER_ADMIN_KEY:
                    # Global override
                    st.session_state.vault_name = vault_name
                    st.session_state.is_admin_internal = True
                    st.session_state.member_key = "MASTER_ADMIN"
                elif admin_pass == vault_admin_pass or DEVICE_ID == creator_device:
                    # Vault admin
                    st.session_state.vault_name = vault_name
                    st.session_state.is_admin_internal = True
                    st.session_state.member_key = "VAULT_ADMIN"
                elif member_pass == vault_member_pass:
                    # Regular member
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
        vault_pass = st.text_input("Vault passkey (member)", type="password", key="new_vault_pass")
        admin_pass_new = st.text_input("Vault admin passkey", type="password", key="new_vault_admin_pass")

        if st.button("Create vault"):
            if not new_name or not vault_pass or not admin_pass_new:
                st.warning("Fill all fields")
            else:
                path = vault_path(new_name)
                (path / ".vault_pass").write_text(vault_pass)
                (path / ".admin_pass").write_text(admin_pass_new)
                (path / ".creator_device").write_text(DEVICE_ID)

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

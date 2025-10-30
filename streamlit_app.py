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

SERVER_ID_FILE = Path("server.id")
if not SERVER_ID_FILE.exists():
    SERVER_ID_FILE.write_text(str(uuid4()))
SERVER_ID = SERVER_ID_FILE.read_text().strip()

MASTER_ADMIN_KEY = os.getenv("MASTER_ADMIN_KEY", "YOUR_MASTER_KEY")

# ---------------------------
# Session State
# ---------------------------
defaults = {
    "vault_name": None,
    "is_admin_internal": False,
    "member_key": None,
    "page": "home",
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v


def go_home():
    for k in ["vault_name", "is_admin_internal", "member_key", "page"]:
        st.session_state[k] = None if k != "page" else "home"


# ---------------------------
# Vault Helpers
# ---------------------------
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
# Auto-admin Vault Check
# ---------------------------
def check_auto_admin_vault():
    for v in VAULTS_FOLDER.iterdir():
        if v.is_dir() and (v / ".creator_id").exists():
            creator_id = (v / ".creator_id").read_text().strip()
            if creator_id == SERVER_ID:
                return v.name
    return None


# ---------------------------
# Home Page
# ---------------------------
def home_page():
    st.title("🙏 Worship Vault")
    st.divider()

    auto_vault = check_auto_admin_vault()
    if auto_vault:
        with st.form("server_admin_form"):
            st.info(f"💾 This server is linked to vault: **{auto_vault}**")
            st.write(
                "⚠️ For security, only the server owner (who knows the MASTER ADMIN key) can log in here."
            )
            entered_master_for_auto = st.text_input(
                "Master admin key (server owner only)", type="password", key="auto_master_input"
            )
            submit_admin = st.form_submit_button("Login as Server (MASTER) Admin")

            if submit_admin:
                if entered_master_for_auto == MASTER_ADMIN_KEY:
                    st.session_state.vault_name = auto_vault
                    st.session_state.is_admin_internal = True
                    st.session_state.member_key = "MASTER_ADMIN"
                    st.session_state.page = "vault"
                else:
                    st.error("Incorrect master admin key.")

    c1, c2 = st.columns(2)

    # ----------- LOGIN EXISTING VAULT -----------
    with c1:
        with st.form("vault_login_form"):
            st.subheader("Enter existing vault")
            vault_name = st.text_input("Vault name", key="login_vault_name")
            entered_pass = st.text_input("Vault password", type="password", key="login_vault_pass")
            submit_login = st.form_submit_button("Open vault")

            if submit_login:
                path = vault_path(vault_name)
                vault_pass_file = path / ".vault_pass"
                admin_pass_file = path / ".admin_pass"
                creator_id_file = path / ".creator_id"

                if not path.exists() or not vault_pass_file.exists():
                    st.error("Vault not found.")
                else:
                    vault_pass = vault_pass_file.read_text()
                    admin_pass = admin_pass_file.read_text() if admin_pass_file.exists() else vault_pass
                    creator_id = creator_id_file.read_text().strip() if creator_id_file.exists() else ""

                    # --- Authentication hierarchy ---
                    if entered_pass == MASTER_ADMIN_KEY:
                        st.session_state.vault_name = vault_name
                        st.session_state.is_admin_internal = True
                        st.session_state.member_key = "MASTER_ADMIN"
                        st.session_state.page = "vault"
                    elif entered_pass == admin_pass or SERVER_ID == creator_id:
                        st.session_state.vault_name = vault_name
                        st.session_state.is_admin_internal = True
                        st.session_state.member_key = "VAULT_ADMIN"
                        st.session_state.page = "vault"
                    elif entered_pass == vault_pass:
                        st.session_state.vault_name = vault_name
                        st.session_state.is_admin_internal = False
                        st.session_state.member_key = "MEMBER"
                        st.session_state.page = "vault"
                    else:
                        st.error("Incorrect password.")

    # ----------- CREATE NEW VAULT -----------
    with c2:
        with st.form("create_vault_form"):
            st.subheader("Create a new vault")
            new_name = st.text_input("Vault name", key="new_vault_name")
            vault_pass = st.text_input("Vault passkey", type="password", key="new_vault_pass")
            submit_create = st.form_submit_button("Create vault")

            if submit_create:
                if not new_name or not vault_pass:
                    st.warning("Fill all fields")
                else:
                    path = vault_path(new_name)
                    (path / ".vault_pass").write_text(vault_pass)
                    (path / ".admin_pass").write_text(vault_pass)
                    (path / ".creator_id").write_text(SERVER_ID)

                    st.session_state.vault_name = new_name
                    st.session_state.is_admin_internal = True
                    st.session_state.member_key = "VAULT_ADMIN"
                    st.session_state.page = "vault"


# ---------------------------
# Vault Page
# ---------------------------
def vault_page():
    vault_name = st.session_state.vault_name
    st.header(f"📂 Vault — {vault_name}")

    c1, c2 = st.columns([1, 1])
    with c1:
        with st.form("back_home_form"):
            back_home = st.form_submit_button("⬅ Back to Home")
            if back_home:
                go_home()

    with c2:
        with st.form("open_gallery_form"):
            open_gallery = st.form_submit_button("📸 Open Gallery")
            if open_gallery:
                st.session_state.page = "gallery"

    uploaded_files = st.file_uploader("Upload images/PDFs", accept_multiple_files=True)
    if uploaded_files:
        for f in uploaded_files:
            save_file(vault_name, f)
        st.success("Uploaded successfully!")


# ---------------------------
# Gallery Page
# ---------------------------
def gallery_page():
    vault_name = st.session_state.vault_name
    st.header(f"🖼️ Gallery — {vault_name}")

    with st.form("back_vault_form"):
        back_vault = st.form_submit_button("⬅ Back to Vault")
        if back_vault:
            st.session_state.page = "vault"

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

                # Only admins can rename/delete
                if st.session_state.is_admin_internal:
                    with st.form(f"edit_{fname}"):
                        new_name = st.text_input("Rename to", value=fname, key=f"rn_{fname}")
                        colr1, colr2 = st.columns(2)
                        with colr1:
                            rename = st.form_submit_button("Rename")
                        with colr2:
                            delete = st.form_submit_button("Delete")

                        if rename:
                            if rename_file(vault_name, fname, new_name):
                                st.success(f"{fname} → {new_name}")
                        if delete:
                            if delete_file(vault_name, fname):
                                st.success(f"{fname} deleted")

            idx += 1


# ---------------------------
# Routing
# ---------------------------
if st.session_state.page == "home":
    home_page()
elif st.session_state.page == "vault":
    vault_page()
elif st.session_state.page == "gallery":
    gallery_page()

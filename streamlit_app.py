# streamlit_app.py
import streamlit as st
from supabase import create_client, Client
import os
import math
import requests
from datetime import datetime, timedelta
import uuid
from pathlib import Path
import socket

# ----------------- Config -----------------
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
MASTER_ADMIN_KEY = os.getenv("MASTER_ADMIN_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    st.error("SUPABASE_URL and SUPABASE_KEY must be set.")
    st.stop()

if not MASTER_ADMIN_KEY:
    st.warning("MASTER_ADMIN_KEY not set; master admin won't work until set in env/secrets.")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
st.set_page_config(page_title="Worship Vault", layout="wide")

# ----------------- Host identity -----------------
HOST_ID_FILE = Path("host.id")
if not HOST_ID_FILE.exists():
    HOST_ID_FILE.write_text(f"{socket.gethostname()}-{uuid.uuid4()}")
HOST_ID = HOST_ID_FILE.read_text().strip()

# ----------------- Helpers -----------------
def _data_from_res(res):
    if res is None:
        return None
    if hasattr(res, "data"):
        return res.data
    if isinstance(res, dict) and "data" in res:
        return res["data"]
    return res

def safe_signed_url(bucket: str, path: str, expires=60):
    try:
        res = supabase.storage.from_(bucket).create_signed_url(path, expires)
        if isinstance(res, dict):
            return res.get("signedURL") or res.get("signed_url") or res.get("signedUrl")
    except Exception:
        pass
    return f"{SUPABASE_URL}/storage/v1/object/public/{bucket}/{path}"

def create_bucket_if_needed(bucket_name: str):
    try:
        res = supabase.storage.get_buckets()
        buckets = _data_from_res(res) or []
        if any((b.get("name") == bucket_name) for b in buckets if isinstance(b, dict)):
            return
        supabase.storage.create_bucket(bucket_name, public=False)
    except Exception:
        pass

def list_bucket_files(bucket_name: str):
    try:
        res = supabase.storage.from_(bucket_name).list()
        data = _data_from_res(res) or []
        files = [item["name"] for item in data if isinstance(item, dict) and "name" in item]
        return sorted(files, key=lambda s: s.lower())
    except Exception:
        return []

def upload_to_bucket(bucket_name: str, file_obj, filename: str):
    try:
        # ✅ FIX: Convert memoryview safely to bytes before upload
        data = file_obj.getbuffer() if hasattr(file_obj, "getbuffer") else file_obj.read()
        if isinstance(data, memoryview):
            data = data.tobytes()
        elif not isinstance(data, (bytes, bytearray)):
            data = bytes(data)

        supabase.storage.from_(bucket_name).upload(filename, data)
        public_url = f"{SUPABASE_URL}/storage/v1/object/public/{bucket_name}/{filename}"

        supabase.table("uploads").insert({
            "filename": filename,
            "url": public_url,
            "vault_name": bucket_name,
            "created_at": datetime.utcnow().isoformat()
        }).execute()
        return True
    except Exception as e:
        st.error(f"Upload failed: {e}")
        return False

def download_file_bytes(bucket_name: str, filename: str):
    try:
        res = supabase.storage.from_(bucket_name).download(filename)
        if isinstance(res, (bytes, bytearray)):
            return bytes(res)
        if hasattr(res, "content"):
            return res.content
        data = _data_from_res(res)
        if data:
            return data
    except Exception:
        pass
    try:
        url = safe_signed_url(bucket_name, filename, expires=60)
        r = requests.get(url)
        if r.status_code == 200:
            return r.content
    except Exception:
        pass
    return None

def remove_file(bucket_name: str, filename: str):
    try:
        supabase.storage.from_(bucket_name).remove([filename])
        supabase.table("uploads").delete().eq("filename", filename).eq("vault_name", bucket_name).execute()
        return True
    except Exception as e:
        st.error(f"Delete failed: {e}")
        return False

def log_activity(vault_name: str, actor: str, action: str, filename: str, details: str = None):
    try:
        supabase.table("vault_logs").insert({
            "vault_name": vault_name,
            "actor": actor,
            "action": action,
            "filename": filename,
            "details": details,
            "created_at": datetime.utcnow().isoformat()
        }).execute()
    except Exception:
        pass

# ----------------- Sessions -----------------
def create_session(vault_name: str, is_admin_internal: bool, is_ui_admin: bool):
    token = str(uuid.uuid4())
    try:
        supabase.table("vault_sessions").insert({
            "token": token,
            "vault_name": vault_name,
            "is_admin_internal": is_admin_internal,
            "is_ui_admin": is_ui_admin,
            "created_at": datetime.utcnow().isoformat(),
            "host_id": HOST_ID
        }).execute()
    except Exception as e:
        st.error(f"Failed to create session record: {e}")
        return False
    st.session_state.token = token
    st.session_state.vault_name = vault_name
    st.session_state.is_admin_internal = is_admin_internal
    st.session_state.is_ui_admin = is_ui_admin
    st.session_state.login_time = datetime.utcnow()
    st.session_state.page = "vault"
    return True

def validate_session():
    token = st.session_state.get("token")
    if not token:
        return False
    try:
        res = supabase.table("vault_sessions").select("*").eq("token", token).execute()
        data = _data_from_res(res) or []
        if not data:
            return False
        s = data[0]
        created_at = datetime.fromisoformat(s["created_at"])
        if datetime.utcnow() - created_at < timedelta(hours=24):
            st.session_state.vault_name = s["vault_name"]
            st.session_state.is_admin_internal = s.get("is_admin_internal", False)
            st.session_state.is_ui_admin = s.get("is_ui_admin", False)
            st.session_state.login_time = created_at
            st.session_state.page = "vault"
            return True
    except Exception:
        pass
    return False

def end_session():
    token = st.session_state.get("token")
    if token:
        try:
            supabase.table("vault_sessions").delete().eq("token", token).execute()
        except Exception:
            pass
    for k in ("token", "vault_name", "is_admin_internal", "is_ui_admin", "login_time", "page"):
        if k in st.session_state:
            del st.session_state[k]
    st.session_state.page = "home"

# ----------------- Defaults -----------------
st.session_state.setdefault("page", "home")
st.session_state.setdefault("token", None)
st.session_state.setdefault("vault_name", None)
st.session_state.setdefault("is_admin_internal", False)
st.session_state.setdefault("is_ui_admin", False)
st.session_state.setdefault("login_time", None)
if st.session_state.token:
    validate_session()

# ----------------- UI -----------------
ACCENT = "#FF4B5C"
CARD_BG = "rgba(255,255,255,0.18)"
TEXT_COLOR = "#0b1220"

def home_page():
    st.markdown(f"<h1 style='color:{ACCENT};'>🙏 Worship Vault</h1>", unsafe_allow_html=True)
    st.divider()
    c1, c2 = st.columns(2)

    with c1:
        st.subheader("Enter Existing Vault")
        vault_input = st.text_input("Vault name", key="login_vault_name")
        passkey_input = st.text_input("Passkey", type="password", key="login_passkey")
        if st.button("Enter Vault", key="enter_vault_btn"):
            if not vault_input or not passkey_input:
                st.warning("Please fill both Vault name and Passkey.")
            else:
                try:
                    res = supabase.table("vaults").select("*").execute()
                    rows = _data_from_res(res) or []
                except Exception as e:
                    st.error(f"Failed to query vaults: {e}")
                    rows = []

                vault_row = next((r for r in rows if r.get("vault_name", "").strip().lower() == vault_input.strip().lower()), None)
                if not vault_row:
                    st.error("Vault not found.")
                else:
                    if passkey_input == MASTER_ADMIN_KEY:
                        create_session(vault_row["vault_name"], True, False)
                    elif passkey_input == vault_row.get("admin_passkey"):
                        create_session(vault_row["vault_name"], True, True)
                    elif passkey_input == vault_row.get("vault_passkey"):
                        create_session(vault_row["vault_name"], False, False)
                    else:
                        st.error("Incorrect passkey.")

    with c2:
        st.subheader("Create New Vault")
        new_name = st.text_input("New Vault Name", key="new_vault_name")
        vault_pass = st.text_input("Vault Passkey (Members)", type="password", key="new_vault_pass")
        admin_pass = st.text_input("Admin Passkey (Vault Admin)", type="password", key="new_admin_pass")
        if st.button("Create Vault", key="create_vault_btn"):
            if not new_name or not vault_pass or not admin_pass:
                st.warning("Fill all fields.")
            else:
                normalized = new_name.strip()
                try:
                    res = supabase.table("vaults").select("vault_name").execute()
                    rows = _data_from_res(res) or []
                    existing = [r.get("vault_name", "").strip().lower() for r in rows]
                except Exception:
                    existing = []

                if normalized.lower() in existing:
                    st.error(f"A vault named '{normalized}' already exists.")
                else:
                    bucket_name = normalized.lower().replace(" ", "-")
                    create_bucket_if_needed(bucket_name)
                    try:
                        supabase.table("vaults").insert({
                            "vault_name": normalized,
                            "vault_passkey": vault_pass,
                            "admin_passkey": admin_pass,
                            "creator_host_id": HOST_ID,
                            "created_at": datetime.utcnow().isoformat()
                        }).execute()
                        create_session(normalized, True, True)
                        st.success(f"Vault '{normalized}' created.")
                    except Exception as e:
                        st.error(f"Vault creation failed: {e}")

def vault_page():
    vault = st.session_state.vault_name
    is_internal = st.session_state.is_admin_internal
    is_ui_admin = st.session_state.is_ui_admin

    st.markdown(f"<h2 style='color:{TEXT_COLOR};'>📂 Vault — {vault}</h2>", unsafe_allow_html=True)
    if st.button("⬅ Back to Home"):
        end_session()
    if is_ui_admin and st.button("View Activity Log"):
        st.session_state.page = "activity_log"

    with st.expander("Upload files"):
        files = st.file_uploader("Upload Images/PDFs", accept_multiple_files=True)
        if files:
            for f in files:
                ok = upload_to_bucket(vault, f, f.name)
                actor = "VAULT_ADMIN" if is_internal and is_ui_admin else ("MASTER_ADMIN" if is_internal and not is_ui_admin else "MEMBER")
                if ok:
                    log_activity(vault, actor, "upload", f.name)
            st.success("Uploaded successfully.")

    if st.button("View Gallery"):
        st.session_state.page = "gallery"

def gallery_page():
    vault = st.session_state.vault_name
    is_internal = st.session_state.is_admin_internal
    is_ui_admin = st.session_state.is_ui_admin

    st.markdown(f"<h2 style='color:{ACCENT};'>🖼️ Gallery — {vault}</h2>", unsafe_allow_html=True)
    if st.button("⬅ Back to Vault"):
        st.session_state.page = "vault"

    files = list_bucket_files(vault)
    if not files:
        st.info("No files yet.")
        return

    per_row = 3
    idx = 0
    for _ in range(math.ceil(len(files)/per_row)):
        cols = st.columns(per_row)
        for c in cols:
            if idx >= len(files):
                break
            fname = files[idx]
            with c:
                ext = fname.split(".")[-1].lower()
                if ext in ("jpg", "jpeg", "png", "gif", "webp"):
                    st.image(safe_signed_url(vault, fname))
                else:
                    st.write("📄 File")
                st.markdown(f"**{fname}**")
                new_name = st.text_input("Rename to", value=fname, key=f"rename_{vault}_{fname}")
                if st.button("Rename", key=f"rn_{vault}_{fname}"):
                    b = download_file_bytes(vault, fname)
                    if b:
                        supabase.storage.from_(vault).upload(new_name, b)
                        supabase.storage.from_(vault).remove([fname])
                        st.success(f"{fname} → {new_name}")
                if is_internal and st.button("Delete", key=f"del_{vault}_{fname}"):
                    remove_file(vault, fname)
                    st.success(f"{fname} deleted")
            idx += 1

def activity_log_page():
    vault = st.session_state.vault_name
    if st.button("⬅ Back to Vault"):
        st.session_state.page = "vault"
        return
    try:
        res = supabase.table("vault_logs").select("*").eq("vault_name", vault).order("created_at", desc=True).execute()
        logs = _data_from_res(res) or []
    except Exception as e:
        st.error(f"Failed to fetch logs: {e}")
        logs = []
    for row in logs:
        st.markdown(f"*{row.get('created_at')}* — **{row.get('actor')}** — {row.get('action')} `{row.get('filename')}`")

# ----------------- Routing -----------------
if st.session_state.page == "home":
    home_page()
elif st.session_state.page == "vault":
    vault_page()
elif st.session_state.page == "gallery":
    gallery_page()
elif st.session_state.page == "activity_log":
    activity_log_page()

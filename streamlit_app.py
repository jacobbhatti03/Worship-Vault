# streamlit_app.py
import streamlit as st
from supabase import create_client, Client
import os
import math
import requests
from datetime import datetime, timedelta
import uuid

# ----------------- Config (set these in Streamlit secrets or .env) ----------
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
MASTER_ADMIN_KEY = os.getenv("MASTER_ADMIN_KEY")  # your invisible master key

if not SUPABASE_URL or not SUPABASE_KEY:
    st.error("SUPABASE_URL and SUPABASE_KEY must be set in environment variables.")
    st.stop()

if not MASTER_ADMIN_KEY:
    st.warning("MASTER_ADMIN_KEY not set; master admin won't work (set it in env).")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
st.set_page_config(page_title="Worship Vault", layout="wide")

# ----------------- Utility helpers -----------------
def _data_from_res(res):
    """Normalize supabase response to list/dict safely."""
    if res is None:
        return None
    if hasattr(res, "data"):
        return res.data
    if isinstance(res, dict) and "data" in res:
        return res["data"]
    return res

def safe_signed_url(bucket: str, path: str, expires=60):
    """Return a signed URL if possible; fall back to public URL."""
    try:
        res = supabase.storage.from_(bucket).create_signed_url(path, expires)
        if isinstance(res, dict):
            for k in ("signedURL", "signed_url", "signedUrl"):
                if res.get(k):
                    return res.get(k)
        if hasattr(res, "get"):
            return res.get("signedURL") or res.get("signed_url") or res.get("signedUrl")
    except Exception:
        pass
    return f"{SUPABASE_URL}/storage/v1/object/public/{bucket}/{path}"

def create_bucket_if_needed(bucket_name: str):
    """Create storage bucket if not exists (best-effort)."""
    try:
        existing = supabase.storage.get_buckets()
        buckets = _data_from_res(existing) or []
        if any((b.get("name") == bucket_name if isinstance(b, dict) else getattr(b, "name", None) == bucket_name) for b in buckets):
            return
        supabase.storage.create_bucket(bucket_name, public=False)
    except Exception:
        # best-effort; ignore errors (may already exist or permission)
        pass

def list_bucket_files(bucket_name: str):
    try:
        res = supabase.storage.from_(bucket_name).list()
        data = _data_from_res(res) or []
        files = []
        for item in data:
            if isinstance(item, dict) and item.get("name"):
                files.append(item["name"])
            elif hasattr(item, "name"):
                files.append(getattr(item, "name"))
        return sorted(files, key=lambda s: s.lower())
    except Exception:
        return []

def upload_to_bucket(bucket_name: str, file_obj, filename: str):
    """Upload file and create an uploads record. Returns True on success."""
    try:
        data = file_obj.getbuffer() if hasattr(file_obj, "getbuffer") else file_obj.read()
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
    # fallback signed url
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
        pass  # don't break UX if logging fails

# ----------------- Session creation & validation -----------------
def create_session(vault_name: str, is_admin_internal: bool, is_ui_admin: bool):
    token = str(uuid.uuid4())
    try:
        supabase.table("vault_sessions").insert({
            "token": token,
            "vault_name": vault_name,
            "is_admin_internal": is_admin_internal,
            "is_ui_admin": is_ui_admin,
            "created_at": datetime.utcnow().isoformat()
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
        session_row = data[0]
        created_at = datetime.fromisoformat(session_row["created_at"])
        if datetime.utcnow() - created_at < timedelta(hours=24):
            st.session_state.vault_name = session_row["vault_name"]
            st.session_state.is_admin_internal = session_row.get("is_admin_internal", False)
            st.session_state.is_ui_admin = session_row.get("is_ui_admin", False)
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

# ----------------- Session defaults -----------------
if "page" not in st.session_state:
    st.session_state.page = "home"
if "token" not in st.session_state:
    st.session_state.token = None
if "vault_name" not in st.session_state:
    st.session_state.vault_name = None
if "is_admin_internal" not in st.session_state:
    st.session_state.is_admin_internal = False
if "is_ui_admin" not in st.session_state:
    st.session_state.is_ui_admin = False
if "login_time" not in st.session_state:
    st.session_state.login_time = None

# validate persistent session if token present
if st.session_state.token:
    validate_session()

# ----------------- UI helpers & constants -----------------
ACCENT = "#FF4B5C"
CARD_BG = "rgba(255,255,255,0.18)"
TEXT_COLOR = "#0b1220"

# ----------------- Pages -----------------
def home_page():
    st.markdown(f"<h1 style='color:{ACCENT};'>🙏 Worship Vault</h1>", unsafe_allow_html=True)
    st.divider()
    c1, c2 = st.columns(2)

    # ---------- Existing Vault (single-click)
    with c1:
        st.subheader("Enter Existing Vault")
        vault_input = st.text_input("Vault name", key="login_vault_name")
        passkey_input = st.text_input("Passkey", type="password", key="login_passkey")
        if st.button("Enter Vault", key="enter_vault_btn"):
            if not vault_input or not passkey_input:
                st.warning("Please fill both Vault name and Passkey.")
            else:
                # lookup vault (case-insensitive)
                try:
                    res = supabase.table("vaults").select("*").execute()
                    rows = _data_from_res(res) or []
                except Exception as e:
                    st.error(f"Failed to query vaults: {e}")
                    rows = []

                vault_row = None
                for r in rows:
                    if r.get("vault_name", "").strip().lower() == vault_input.strip().lower():
                        vault_row = r
                        break

                if not vault_row:
                    st.error("Vault not found. Check spelling or create it.")
                else:
                    # master admin (invisible)
                    if passkey_input == MASTER_ADMIN_KEY:
                        create_session(vault_row["vault_name"], True, False)
                    # vault admin (shows admin UI)
                    elif passkey_input == vault_row.get("admin_passkey"):
                        create_session(vault_row["vault_name"], True, True)
                    # normal member
                    elif passkey_input == vault_row.get("vault_passkey"):
                        create_session(vault_row["vault_name"], False, False)
                    else:
                        st.error("Incorrect passkey.")

    # ---------- Create Vault (with duplicate check)
    with c2:
        st.subheader("Create New Vault")
        new_name = st.text_input("New Vault Name", key="new_vault_name")
        vault_pass = st.text_input("Vault Passkey (Members)", type="password", key="new_vault_pass")
        admin_pass = st.text_input("Admin Passkey (Vault Admin)", type="password", key="new_admin_pass")
        if st.button("Create Vault", key="create_vault_btn"):
            if not new_name or not vault_pass or not admin_pass:
                st.warning("Fill all fields to create the vault.")
            else:
                normalized = new_name.strip()
                # check for existing vault (case-insensitive)
                try:
                    res = supabase.table("vaults").select("vault_name").execute()
                    rows = _data_from_res(res) or []
                    exists = any(r.get("vault_name","").strip().lower() == normalized.lower() for r in rows)
                except Exception as e:
                    st.error(f"Error checking existing vaults: {e}")
                    exists = False

                if exists:
                    st.error(f"A vault named '{normalized}' already exists. Choose another name.")
                else:
                    bucket_name = normalized.lower().replace(" ", "-")
                    create_bucket_if_needed(bucket_name)
                    try:
                        supabase.table("vaults").insert({
                            "vault_name": normalized,
                            "vault_passkey": vault_pass,
                            "admin_passkey": admin_pass,
                            "created_at": datetime.utcnow().isoformat()
                        }).execute()
                        create_session(normalized, True, True)
                        st.success(f"Vault '{normalized}' created and logged in as admin.")
                    except Exception as e:
                        st.error(f"Vault creation failed: {e}")

def vault_page():
    vault = st.session_state.vault_name
    is_internal = st.session_state.is_admin_internal
    is_ui_admin = st.session_state.is_ui_admin

    st.markdown(f"<h2 style='color:{TEXT_COLOR};'>📂 Vault — {vault}</h2>", unsafe_allow_html=True)

    # menu
    left_col, right_col = st.columns([0.92, 0.08])
    with right_col:
        if st.button("⋮ Menu"):
            # simple menu using session_state to toggle a small menu area
            st.session_state.show_menu = not st.session_state.get("show_menu", False)

        if st.session_state.get("show_menu", False):
            if st.button("Back to Home"):
                end_session()
            if is_ui_admin:
                if st.button("View Activity Log"):
                    st.session_state.page = "activity_log"

    # upload
    with st.expander("Upload files"):
        files = st.file_uploader("Images (jpg, png, webp, gif) or PDFs", accept_multiple_files=True)
        if files:
            for f in files:
                ok = upload_to_bucket(vault, f, f.name)
                actor = "VAULT_ADMIN" if is_internal and is_ui_admin else ("MASTER_ADMIN" if is_internal and not is_ui_admin else "MEMBER")
                if ok:
                    log_activity(vault, actor, "upload", f.name)
            st.success("Uploaded files (if any).")

    # quick controls
    c1, c2 = st.columns([0.6, 0.4])
    with c1:
        if st.button("View Gallery"):
            st.session_state.page = "gallery"

def gallery_page():
    vault = st.session_state.vault_name
    is_internal = st.session_state.is_admin_internal
    is_ui_admin = st.session_state.is_ui_admin

    st.markdown(f"<h2 style='color:{ACCENT};'>🖼️ Gallery — {vault}</h2>", unsafe_allow_html=True)
    st.divider()
    if st.button("⬅ Back to Vault"):
        st.session_state.page = "vault"

    files = list_bucket_files(vault)
    if not files:
        st.info("No files yet.")
        return

    per_row = 3
    total = len(files)
    rows = math.ceil(total / per_row)
    idx = 0
    for r in range(rows):
        cols = st.columns(per_row, gap="large")
        for c in range(per_row):
            if idx >= total:
                cols[c].empty()
            else:
                fname = files[idx]
                with cols[c]:
                    st.markdown(f"""
                        <div style="
                            border-radius:12px;
                            padding:8px;
                            box-shadow: 0 6px 18px rgba(11,17,32,0.06);
                            background: {CARD_BG};
                            text-align:center;
                        ">
                    """, unsafe_allow_html=True)

                    ext = fname.split(".")[-1].lower()
                    if ext in ("jpg", "jpeg", "png", "gif", "webp"):
                        url = safe_signed_url(vault, fname)
                        try:
                            st.image(url)
                        except Exception:
                            st.write("🖼️ Preview not available")
                    else:
                        st.write("📄 File")

                    st.markdown(f"**{fname}**")

                    # rename input + button
                    new_key = f"rename_{vault}_{fname}"
                    new_name = st.text_input("Rename to", value=fname, key=new_key)
                    if st.button("Rename", key=f"rn_btn_{vault}_{fname}"):
                        b = download_file_bytes(vault, fname)
                        if b:
                            try:
                                supabase.storage.from_(vault).upload(new_name, b)
                                supabase.table("uploads").update({
                                    "filename": new_name,
                                    "url": f"{SUPABASE_URL}/storage/v1/object/public/{vault}/{new_name}"
                                }).eq("filename", fname).eq("vault_name", vault).execute()
                                supabase.storage.from_(vault).remove([fname])
                                actor = "VAULT_ADMIN" if is_internal and is_ui_admin else ("MASTER_ADMIN" if is_internal and not is_ui_admin else "MEMBER")
                                log_activity(vault, actor, "rename", fname, details=new_name)
                                st.success(f"Renamed {fname} → {new_name}")
                            except Exception as e:
                                st.error(f"Rename failed: {e}")
                        else:
                            st.error("Could not download file to rename.")

                    # delete button (internal admin only)
                    if is_internal:
                        if st.button("Delete", key=f"del_{vault}_{fname}"):
                            ok = remove_file(vault, fname)
                            if ok:
                                actor = "VAULT_ADMIN" if is_ui_admin else ("MASTER_ADMIN")
                                log_activity(vault, actor, "delete", fname)
                                st.success(f"{fname} deleted")

                    st.markdown("</div>", unsafe_allow_html=True)
                idx += 1

def activity_log_page():
    vault = st.session_state.vault_name
    st.markdown(f"<h2 style='color:{TEXT_COLOR};'>📝 Activity Log — {vault}</h2>", unsafe_allow_html=True)
    if st.button("⬅ Back to Vault"):
        st.session_state.page = "vault"
        return

    try:
        res = supabase.table("vault_logs").select("*").eq("vault_name", vault).order("created_at", desc=True).execute()
        logs = _data_from_res(res) or []
    except Exception as e:
        st.error(f"Failed to fetch logs: {e}")
        logs = []

    if not logs:
        st.info("No activity yet.")
        return

    for row in logs:
        ts = row.get("created_at", "")
        actor = row.get("actor", "")
        action = row.get("action", "")
        filename = row.get("filename", "")
        details = row.get("details", "")
        st.markdown(f"*[{ts}]* **{actor}** — {action} — `{filename}` {('- ' + details) if details else ''}")

# ----------------- Routing ---------------
if st.session_state.page == "home":
    home_page()
elif st.session_state.page == "vault":
    vault_page()
elif st.session_state.page == "gallery":
    gallery_page()
elif st.session_state.page == "activity_log":
    if st.session_state.is_ui_admin:
        activity_log_page()
    else:
        st.error("Not authorized to view activity logs.")
        st.session_state.page = "vault"

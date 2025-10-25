import os
import streamlit as st

# -------------------------------
# Folder for storing images locally
# -------------------------------
UPLOAD_FOLDER = "worship_vault_images"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

st.set_page_config(page_title="Worship Vault", page_icon="📸", layout="centered")
st.title("📸 Worship Vault")
st.caption("Upload and view your stored images safely within the app")

# -------------------------------
# Session state for files
# -------------------------------
if "files" not in st.session_state:
    st.session_state.files = sorted(os.listdir(UPLOAD_FOLDER))

def refresh_file_list():
    st.session_state.files = sorted(os.listdir(UPLOAD_FOLDER))

# -------------------------------
# File Upload Section
# -------------------------------
uploaded_file = st.file_uploader("📤 Choose an image", type=["jpg", "jpeg", "png"])

if uploaded_file:
    st.image(uploaded_file, caption="Preview", use_container_width=True)
    if st.button("Upload"):
        file_path = os.path.join(UPLOAD_FOLDER, uploaded_file.name)
        if os.path.exists(file_path):
            st.warning("⚠️ File already exists in Worship Vault!")
        else:
            with open(file_path, "wb") as f:
                f.write(uploaded_file.getbuffer())
            st.success(f"✅ Uploaded '{uploaded_file.name}' successfully!")
            refresh_file_list()

# -------------------------------
# Image Gallery with Delete Only
# -------------------------------
st.write("---")
st.subheader("🖼️ Gallery")

if not st.session_state.files:
    st.info("No images found yet.")
else:
    for i, img_file in enumerate(st.session_state.files):
        col1, col2 = st.columns([3, 1])

        # Show image
        with col1:
            st.image(os.path.join(UPLOAD_FOLDER, img_file), caption=img_file, use_container_width=True)

        # Delete button
        with col2:
            if st.button("Delete", key=f"btn_delete_{img_file}"):
                os.remove(os.path.join(UPLOAD_FOLDER, img_file))
                st.success(f"Deleted '{img_file}'")
                refresh_file_list()

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

SCOPES = ["https://www.googleapis.com/auth/drive"]
SERVICE_ACCOUNT_FILE = "credenciales.json"

creds = service_account.Credentials.from_service_account_file(
    SERVICE_ACCOUNT_FILE, scopes=SCOPES
)
service = build("drive", "v3", credentials=creds)

# ID de la carpeta controlada
FOLDER_ID = "1xHUXnymGCFHr58ptJTNhIHH8NhL3A9cr"

# Subir archivo dentro de ella
file_metadata = {"name": "informe.txt", "parents": [FOLDER_ID]}
media = MediaFileUpload("informe.txt", mimetype="text/plain")

file = service.files().create(body=file_metadata, media_body=media, fields="id").execute()
print("Subido con ID:", file["id"])
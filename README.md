# Descripción

## Crear ejecutable

```python
python -m PyInstaller --onefile --noconfirm --windowed --add-data "client_secrets.json;." --add-data "credentials.json;." --add-data "drive_config.json;." --add-data "user_credentials.json;." --add-data "drive;drive" --add-data "pdf;pdf" --add-data "ui;ui" --add-data "utils;utils" main.py
```

## Credenciales 

Poner credenciales en la ubicación del archivo `main.py`.
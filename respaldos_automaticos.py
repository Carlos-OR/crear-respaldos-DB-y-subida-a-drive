import os
import time
import subprocess
import zipfile
from datetime import datetime, date
import mysql.connector
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

# Función para leer la configuración de la base de datos desde un archivo externo
def read_db_config(config_file='db_config.txt'):
    config = {}
    try:
        with open(config_file, 'r') as file:
            for line in file:
                if '=' in line:
                    key, value = line.strip().split('=', 1)
                    config[key] = value
    except Exception as e:
        print(f"Error al leer el archivo de configuración: {e}")
    return config

# Función para realizar el respaldo de las bases de datos MySQL
def backup_databases(host, user, password):
    try:
        db_connection = mysql.connector.connect(
            host=host,
            user=user,
            password=password
        )
        cursor = db_connection.cursor()

        cursor.execute("SHOW DATABASES")
        databases = cursor.fetchall()

        backup_folder = "respaldos_mysql"
        if not os.path.exists(backup_folder):
            os.makedirs(backup_folder)

        for database in databases:
            database_name = database[0]
            if database_name not in ['information_schema', 'mysql', 'performance_schema', 'phpmyadmin', 'sys']:
                backup_filename = f"{backup_folder}/{database_name}_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.sql"
                backup_command = [
                    "mysqldump",
                    f"--host={host}",
                    f"--user={user}",
                    f"--password={password}" if password else "--password=",
                    database_name,
                    f"--result-file={backup_filename}",
                    "--default-character-set=utf8mb4",
                    "--collation=utf8mb4_general_ci",
                    "--skip-set-charset"  # Evitar agregar SET NAMES con un collation incompatible
                ]
                result = subprocess.run(backup_command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                if result.returncode == 0:
                    file_size = os.path.getsize(backup_filename) / (1024 * 1024)  # Convertir a MB
                    print(f"Se ha creado el respaldo de la base de datos {database_name} en {backup_filename} (Tamaño: {file_size:.2f} MB)")
                else:
                    print(f"Error al crear el respaldo de la base de datos {database_name}: {result.stderr.decode()}")
                    return False

        return True

    except mysql.connector.Error as err:
        print(f"Error al conectar con MySQL: {err}")
        return False
    finally:
        if db_connection.is_connected():
            cursor.close()
            db_connection.close()

# Función para comprimir los archivos SQL en un archivo ZIP
def zip_backups():
    try:
        backup_folder = "respaldos_mysql"
        for backup_file in os.listdir(backup_folder):
            if backup_file.endswith(".sql"):
                file_path = os.path.join(backup_folder, backup_file)
                zip_filename = f"{file_path}.zip"
                with zipfile.ZipFile(zip_filename, 'w') as zipf:
                    zipf.write(file_path, os.path.basename(file_path))
                file_size = os.path.getsize(zip_filename) / (1024 * 1024)  # Convertir a MB
                print(f"Archivo comprimido: {zip_filename} (Tamaño: {file_size:.2f} MB)")
                os.remove(file_path)  # Eliminar el archivo SQL después de comprimirlo
        return True

    except Exception as e:
        print(f"Error al comprimir los archivos: {e}")
        return False

# Función para subir los respaldos a Google Drive
def upload_to_google_drive():
    try:
        SCOPES = ['https://www.googleapis.com/auth/drive']
        SERVICE_ACCOUNT_FILE = 'respaldos-automaticos-nat-0c250f488388.json'

        credentials = service_account.Credentials.from_service_account_file(
            SERVICE_ACCOUNT_FILE, scopes=SCOPES)
        service = build('drive', 'v3', credentials=credentials)

        backup_folder = "respaldos_mysql"
        for backup_file in os.listdir(backup_folder):
            if backup_file.endswith(".zip"):
                file_path = os.path.join(backup_folder, backup_file)

                file_metadata = {'name': backup_file, 'parents': ['1RT1rRpG8lTF-R1QszwvEe6cUDIB-urM_']}
                with open(file_path, 'rb') as f:
                    media = MediaIoBaseUpload(f, mimetype='application/zip', chunksize=1024*1024, resumable=True)
                    request = service.files().create(body=file_metadata, media_body=media, fields='id')
                    response = None
                    # Eliminar la barra de progreso y solo notificar cuando se complete
                    while response is None:
                        status, response = request.next_chunk()
                        if status:
                            print(f"\rSubiendo archivo {backup_file}: {int(status.progress() * 100)}% completado.", end="")
                    print(f"\nSe ha subido el archivo {backup_file} a Google Drive")

                # Borrar el archivo local después de subirlo a Google Drive
                try:
                    os.remove(file_path)
                    print(f"Archivo {backup_file} eliminado localmente")
                except PermissionError:
                    print(f"Error al borrar el archivo {backup_file}: El archivo está en uso")
                except Exception as e:
                    print(f"Error al borrar el archivo {backup_file}: {e}")

        return True

    except Exception as e:
        print(f"Error al subir a Google Drive: {e}")
        return False

# Función para limpiar la carpeta de respaldos en caso de error
def clean_backup_folder():
    try:
        backup_folder = "respaldos_mysql"
        for backup_file in os.listdir(backup_folder):
            file_path = os.path.join(backup_folder, backup_file)
            os.remove(file_path)
        print("Carpeta de respaldos limpia.")
    except Exception as e:
        print(f"Error al limpiar la carpeta de respaldos: {e}")

# Función para verificar si el respaldo ya se realizó hoy
def backup_done_today():
    backup_log_file = "backup_log.txt"
    today_date = date.today().isoformat()
    
    # Verificar y leer el archivo de log
    try:
        if os.path.exists(backup_log_file):
            with open(backup_log_file, 'r') as log_file:
                last_backup_date = log_file.read().strip()
                if last_backup_date == today_date:
                    print("El respaldo ya se ha realizado hoy.")
                    return True
    except Exception as e:
        print(f"Error al leer el archivo de log: {e}")

    # Escribir la fecha actual en el archivo de log
    try:
        with open(backup_log_file, 'w') as log_file:
            log_file.write(today_date)
    except Exception as e:
        print(f"Error al escribir en el archivo de log: {e}")

    print("Realizando el respaldo para hoy.")
    return False

# Leer la configuración de la base de datos desde un archivo externo
db_config = read_db_config()

# Ejecutar la creación de respaldos, compresión y subida a Google Drive al inicio
if not backup_done_today():
    if backup_databases(db_config.get('host'), db_config.get('user'), db_config.get('password')):
        print("Respaldos creados")
        if zip_backups():
            print("Archivos comprimidos")
            # Esperar unos segundos para asegurar que la conexión a Internet esté disponible
            time.sleep(5)
            if upload_to_google_drive():
                print("Respaldos subidos a Google Drive")
            else:
                print("Error al subir los respaldos a Google Drive")
                clean_backup_folder()
        else:
            print("Error al comprimir los archivos")
            clean_backup_folder()
    else:
        print("Error al crear los respaldos")
        clean_backup_folder()
else:
    print("El respaldo ya se ha realizado hoy. Esperando hasta el próximo domingo.")

# Subir los respaldos a Google Drive cada fin de semana
while True:
    today = datetime.now()
    if today.weekday() == 6 and not backup_done_today():  # Domingo y no se ha hecho respaldo hoy
        if backup_databases(db_config.get('host'), db_config.get('user'), db_config.get('password')):
            print("Respaldos creados")
            if zip_backups():
                print("Archivos comprimidos")
                if upload_to_google_drive():
                    print("Respaldos subidos a Google Drive")
                else:
                    print("Error al subir los respaldos a Google Drive")
                    clean_backup_folder()
            else:
                print("Error al comprimir los archivos")
                clean_backup_folder()
        else:
            print("Error al crear los respaldos")
            clean_backup_folder()

    # Esperar un día (86400 segundos)
    time.sleep(86400)

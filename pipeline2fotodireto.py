import os
import re
import subprocess
from PIL import Image, ImageFile

ImageFile.LOAD_TRUNCATED_IMAGES = True

MODELO_FILE = "modelo.jpg"
FRAMES_DIR = "frames"
OUT_DIR = "frames_processados"
EXIFTOOL = "exiftool.exe"

os.makedirs(OUT_DIR, exist_ok=True)

if not os.path.exists(MODELO_FILE):
    print("ERRO: modelo.jpg não encontrado.")
    exit()

if not os.path.exists(FRAMES_DIR):
    print("ERRO: pasta frames não encontrada.")
    exit()

frames = sorted([
    f for f in os.listdir(FRAMES_DIR)
    if f.lower().endswith((".jpg", ".jpeg"))
])

print(f"Imagens encontradas: {len(frames)} arquivos")

if len(frames) == 0:
    print("ERRO: pasta frames sem imagens.")
    exit()

# Descobre o maior índice já existente em frames_processados
last_number = 0

pattern = re.compile(r"^MULTICAPTURA_0000_(\d{6})\.jpg$", re.IGNORECASE)

for file in os.listdir(OUT_DIR):
    match = pattern.match(file)
    if match:
        number = int(match.group(1))
        if number > last_number:
            last_number = number

print(f"Último índice existente: {last_number}")
print(f"Próxima imagem será: MULTICAPTURA_0000_{last_number + 1:06d}.jpg")

processadas = 0
falhas = []

for i, frame in enumerate(frames):
    old_path = os.path.join(FRAMES_DIR, frame)

    new_index = last_number + i + 1
    new_name = f"MULTICAPTURA_0000_{new_index:06d}.jpg"
    new_path = os.path.join(OUT_DIR, new_name)

    try:
        img = Image.open(old_path)

        # Mantém EXIF existente da imagem de origem, inclusive GPS
        exif_bytes = img.info.get("exif", b"")

        img.save(
            new_path,
            "jpeg",
            exif=exif_bytes,
            quality=95
        )

        img.close()

        # Copia SOMENTE metadados panorâmicos do modelo.
        # NÃO copia GPS do modelo.
        # NÃO limpa GPS da imagem, para manter a coordenada original.
        cmd = [
            EXIFTOOL,
            "-overwrite_original",

            "-TagsFromFile", MODELO_FILE,
            "-XMP-GPano:ProjectionType",
            "-XMP-GPano:UsePanoramaViewer",
            "-XMP-GPano:CroppedAreaImageHeightPixels",
            "-XMP-GPano:CroppedAreaImageWidthPixels",
            "-XMP-GPano:CroppedAreaLeftPixels",
            "-XMP-GPano:CroppedAreaTopPixels",
            "-XMP-GPano:FullPanoHeightPixels",
            "-XMP-GPano:FullPanoWidthPixels",
            "-XMP-GPano:SourcePhotosCount",

            "-XMP-GPano:StitchingSoftware=Insta360 Studio",

            "-Make=Insta360",
            "-Model=Insta360 X4",
            "-Software=Insta360 Studio",

            new_path
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.stderr:
            print(f"AVISO EXIFTOOL em {new_name}: {result.stderr}")

        processadas += 1
        print(f"OK: {new_name}")

    except Exception as e:
        falhas.append((frame, str(e)))
        print(f"ERRO: {frame} -> {e}")

print("")
print("==============")
print(f"Processadas: {processadas}")
print(f"Falhas: {len(falhas)}")
print(f"Saída: {OUT_DIR}")

if falhas:
    with open("falhas.txt", "w", encoding="utf-8") as f:
        for nome, erro in falhas:
            f.write(f"{nome} -> {erro}\n")

    print("Relatório salvo em falhas.txt")

print("OK - Finalizado!")
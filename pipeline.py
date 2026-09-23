import gpxpy
import os
import glob
import subprocess
from PIL import Image, ImageFile
import piexif
from datetime import timedelta

ImageFile.LOAD_TRUNCATED_IMAGES = True

MODELO_FILE = "modelo.jpg"
FRAMES_DIR = "frames"
OUT_DIR = "frames_processados"
EXIFTOOL = "exiftool.exe"

# AJUSTE CONFORME O FFMPEG:
# fps=1      -> 1 segundo
# fps=0.5    -> 2 segundos
# fps=0.3333 -> 3 segundos
FRAME_INTERVAL_SECONDS = 3

os.makedirs(OUT_DIR, exist_ok=True)

# Detecta automaticamente o único GPX na raiz
gpx_files = glob.glob("*.gpx")

if len(gpx_files) == 0:
    print("AVISO: nenhum arquivo .gpx encontrado. Coordenadas serão zeradas.")
    GPX_FILE = None
elif len(gpx_files) > 1:
    print("ERRO: mais de um arquivo .gpx encontrado na raiz.")
    print("Deixe apenas 1 GPX na pasta.")
    print(gpx_files)
    exit()
else:
    GPX_FILE = gpx_files[0]
    print(f"GPX usado: {GPX_FILE}")

def dms(coord):
    deg = int(abs(coord))
    min_float = (abs(coord) - deg) * 60
    minute = int(min_float)
    sec = (min_float - minute) * 60
    return ((deg, 1), (minute, 1), (int(sec * 100), 100))

def interpolate(p1, p2, target_time):
    total = (p2.time - p1.time).total_seconds()

    if total <= 0:
        return p1.latitude, p1.longitude, p1.elevation

    part = (target_time - p1.time).total_seconds()
    ratio = max(0, min(1, part / total))

    lat = p1.latitude + (p2.latitude - p1.latitude) * ratio
    lon = p1.longitude + (p2.longitude - p1.longitude) * ratio

    if p1.elevation is not None and p2.elevation is not None:
        ele = p1.elevation + (p2.elevation - p1.elevation) * ratio
    else:
        ele = p1.elevation

    return lat, lon, ele

def find_position(points, target_time):
    if not points or len(points) < 2:
        return 0, 0, 0, False

    if target_time <= points[0].time:
        return points[0].latitude, points[0].longitude, points[0].elevation, True

    if target_time >= points[-1].time:
        return points[-1].latitude, points[-1].longitude, points[-1].elevation, True

    for i in range(len(points) - 1):
        if points[i].time <= target_time <= points[i + 1].time:
            lat, lon, ele = interpolate(points[i], points[i + 1], target_time)
            return lat, lon, ele, True

    return 0, 0, 0, False

if not os.path.exists(MODELO_FILE):
    print("ERRO: modelo.jpg não encontrado.")
    exit()

if not os.path.exists(FRAMES_DIR):
    print("ERRO: pasta frames não encontrada.")
    exit()

points = []

if GPX_FILE:
    with open(GPX_FILE, "r", encoding="utf-8") as f:
        gpx = gpxpy.parse(f)

    for track in gpx.tracks:
        for seg in track.segments:
            for p in seg.points:
                if p.time and p.latitude is not None and p.longitude is not None:
                    points.append(p)

    points = sorted(points, key=lambda p: p.time)

frames = sorted([
    f for f in os.listdir(FRAMES_DIR)
    if f.lower().endswith((".jpg", ".jpeg"))
])

print(f"GPX encontrados com tempo/coordenada: {len(points)} pontos")
print(f"Imagens encontradas: {len(frames)} arquivos")

if len(frames) == 0:
    print("ERRO: pasta frames sem imagens.")
    exit()

if len(points) >= 2:
    start_time = points[0].time
else:
    print("AVISO: GPX ausente ou insuficiente. Coordenadas serão zeradas.")
    start_time = None

# Descobre último índice já existente para não sobrescrever
existing = sorted([
    f for f in os.listdir(OUT_DIR)
    if f.startswith("MULTICAPTURA_0000_")
    and f.lower().endswith(".jpg")
])

if existing:
    last_file = existing[-1]
    try:
        last_number = int(
            last_file
            .replace("MULTICAPTURA_0000_", "")
            .replace(".jpg", "")
            .replace(".JPG", "")
        )
    except:
        last_number = 0
else:
    last_number = 0

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
        if start_time:
            frame_time = start_time + timedelta(seconds=i * FRAME_INTERVAL_SECONDS)
            lat, lon, ele, has_gps = find_position(points, frame_time)
        else:
            frame_time = None
            lat, lon, ele, has_gps = 0, 0, 0, False

        img = Image.open(old_path)

        exif_dict = {
            "0th": {},
            "Exif": {},
            "GPS": {}
        }

        exif_dict["0th"][piexif.ImageIFD.Make] = "Insta360"
        exif_dict["0th"][piexif.ImageIFD.Model] = "Insta360 X4"
        exif_dict["0th"][piexif.ImageIFD.Software] = "Insta360 Studio"

        if frame_time:
            dt = frame_time.strftime("%Y:%m:%d %H:%M:%S")
            gps_date = frame_time.strftime("%Y:%m:%d")
            gps_time = (
                (frame_time.hour, 1),
                (frame_time.minute, 1),
                (frame_time.second, 1)
            )

            exif_dict["0th"][piexif.ImageIFD.DateTime] = dt
            exif_dict["Exif"][piexif.ExifIFD.DateTimeOriginal] = dt
            exif_dict["Exif"][piexif.ExifIFD.DateTimeDigitized] = dt
        else:
            gps_date = None
            gps_time = None

        # GPS somente do GPX. Nunca copia GPS do modelo.
        if has_gps:
            exif_dict["GPS"][piexif.GPSIFD.GPSVersionID] = (2, 3, 0, 0)

            exif_dict["GPS"][piexif.GPSIFD.GPSLatitudeRef] = (
                "N" if lat >= 0 else "S"
            )
            exif_dict["GPS"][piexif.GPSIFD.GPSLatitude] = dms(lat)

            exif_dict["GPS"][piexif.GPSIFD.GPSLongitudeRef] = (
                "E" if lon >= 0 else "W"
            )
            exif_dict["GPS"][piexif.GPSIFD.GPSLongitude] = dms(lon)

            if ele is not None:
                exif_dict["GPS"][piexif.GPSIFD.GPSAltitudeRef] = 0
                exif_dict["GPS"][piexif.GPSIFD.GPSAltitude] = (
                    int(ele * 100), 100
                )

            if gps_date and gps_time:
                exif_dict["GPS"][piexif.GPSIFD.GPSDateStamp] = gps_date
                exif_dict["GPS"][piexif.GPSIFD.GPSTimeStamp] = gps_time

        exif_bytes = piexif.dump(exif_dict)

        img.save(
            new_path,
            "jpeg",
            exif=exif_bytes,
            quality=95
        )

        img.close()

        cmd = [
            EXIFTOOL,
            "-overwrite_original",

            "-GPS:All=",

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

        # Regrava GPS original do GPX depois da limpeza/cópia do ExifTool
        if has_gps:
            gps_cmd = [
                EXIFTOOL,
                "-overwrite_original",
                f"-GPSLatitude={abs(lat)}",
                f"-GPSLatitudeRef={'N' if lat >= 0 else 'S'}",
                f"-GPSLongitude={abs(lon)}",
                f"-GPSLongitudeRef={'E' if lon >= 0 else 'W'}",
                "-GPSAltitudeRef=0",
                f"-GPSAltitude={ele if ele is not None else 0}",
                new_path
            ]

            gps_result = subprocess.run(gps_cmd, capture_output=True, text=True)

            if gps_result.stderr:
                print(f"AVISO GPS EXIFTOOL em {new_name}: {gps_result.stderr}")

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
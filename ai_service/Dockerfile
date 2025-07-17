# ai_service/Dockerfile
# Bauanleitung für den Docker-Container des KI-Dienstes.

# Verwende ein offizielles NVIDIA CUDA-Image als Basis, um GPU-Unterstützung zu gewährleisten.
# Dies ist die Voraussetzung für eine performante Ausführung des Modells.
FROM nvidia/cuda:12.1.1-cudnn8-runtime-ubuntu22.04

# Setze Umgebungsvariablen, um Interaktionen zu vermeiden
ENV DEBIAN_FRONTEND=noninteractive

# Installiere Python und den Paketmanager pip
RUN apt-get update && \
    apt-get install -y python3.11 python3-pip && \
    rm -rf /var/lib/apt/lists/*

# Setze das Arbeitsverzeichnis im Container
WORKDIR /app

# Kopiere zuerst die Anforderungsdatei und installiere die Abhängigkeiten.
# Dies nutzt den Docker-Cache, sodass die Pakete nicht bei jeder Code-Änderung neu installiert werden.
COPY ./ai_service/requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

# Kopiere den gesamten Projektinhalt in das Arbeitsverzeichnis.
# Wir benötigen 'class_folder' und 'templates' für die Inferenz.
COPY . .

# Gib an, auf welchem Port der Dienst im Container lauscht.
# Google Cloud Run erwartet standardmäßig Port 8080.
EXPOSE 8080

# Der Befehl, der beim Starten des Containers ausgeführt wird.
# Startet den Uvicorn-Server, der unsere FastAPI-App ausführt.
# --host 0.0.0.0 macht den Server von außerhalb des Containers erreichbar.
# --port 8080 entspricht dem EXPOSE-Befehl.
CMD ["uvicorn", "ai_service.main:app", "--host", "0.0.0.0", "--port", "8080"]


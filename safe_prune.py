import subprocess
import datetime
import os

IMAGE = "last-strawberry-ai-service"
CONTAINER = "keep-last-strawberry"
BACKUP = True  # True = Backup wird erstellt

def docker(cmd):
    return subprocess.run(["docker"] + cmd, capture_output=True, text=True)

def image_exists(image):
    result = docker(["images", "-q", image])
    return bool(result.stdout.strip())

def container_exists(container):
    result = docker(["ps", "-a", "--format", "{{.Names}}"])
    return container in result.stdout.splitlines()

def run_dummy_container():
    print(f"Starte Dummy-Container für '{IMAGE}' ...")
    return docker(["run", "-d", "--name", CONTAINER, IMAGE, "tail", "-f", "/dev/null"])

def save_backup():
    now = datetime.datetime.now().strftime("%Y-%m-%d")
    filename = f"{IMAGE}_{now}.tar.gz"
    print(f"Backup des Images wird als '{filename}' erstellt...")
    with open(filename, "wb") as f:
        p1 = subprocess.Popen(["docker", "save", IMAGE], stdout=subprocess.PIPE)
        p2 = subprocess.Popen(["gzip"], stdin=p1.stdout, stdout=f)
        p1.stdout.close()
        p2.communicate()
    print("Backup abgeschlossen!")

def prune():
    print("Docker wird bereinigt...")
    docker(["system", "prune", "-a", "-f"])
    docker(["volume", "prune", "-f"])
    docker(["builder", "prune", "-f"])
    print("Bereinigung abgeschlossen.")

def main():
    if not image_exists(IMAGE):
        print(f"Image '{IMAGE}' nicht gefunden! Vorgang abgebrochen.")
        return

    if not container_exists(CONTAINER):
        run_dummy_container()
    else:
        print(f"Dummy-Container '{CONTAINER}' existiert bereits.")

    if BACKUP:
        save_backup()

    prune()
    print(f"Fertig! Dein Image und der Container '{CONTAINER}' sind weiterhin vorhanden.")
    print(f"Du kannst den Container später mit:\n  docker rm -f {CONTAINER}\nlöschen, falls nicht mehr benötigt.")

if __name__ == "__main__":
    main()

"""
Pobiera pliki z mordora (https://mordor.ksi.ii.uj.edu.pl/file/) do data/mordor/,
zachowujac strukture katalogow. Wymaga ciasteczka sesji w MORDOR_COOKIE (.env).

Uzycie (z katalogu glownego repo):
    python pipeline/scrapers/mordor/files_downloader.py
"""

import os
import time
from urllib.parse import unquote, urljoin

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

START_PAGE = "https://mordor.ksi.ii.uj.edu.pl/file/"
BASE_SAVE_DIR = os.path.join("data", "mordor")
REQUEST_TIMEOUT = 60
DOWNLOAD_DELAY = 0.5
FILE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".pdf", ".doc", ".docx", ".txt")
BLOCKED_FOLDERS = {"książki", "ksiazki"}


def save_file(session: requests.Session, file_url: str, out_folder: str, file_name: str) -> None:
    os.makedirs(out_folder, exist_ok=True)
    path = os.path.join(out_folder, file_name)

    if os.path.exists(path):
        print(f"Already exists: {file_name}")
        return

    try:
        response = session.get(file_url, stream=True, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        with open(path, "wb") as file:
            for chunk in response.iter_content(1024):
                file.write(chunk)
    except (requests.RequestException, OSError) as e:
        print(f"Error downloading {file_url}: {e}")
        # Niepelny plik zablokowalby ponowna probe ("Already exists").
        if os.path.exists(path):
            os.remove(path)
        return

    print(f"Downloaded: {file_name}")
    time.sleep(DOWNLOAD_DELAY)


def scrape_folder(session: requests.Session, url: str, cur_folder: str) -> None:
    print(f"Entering: {cur_folder}")

    try:
        response = session.get(url, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
    except requests.RequestException as e:
        print(f"Error loading page {url}: {e}")
        return

    soup = BeautifulSoup(response.text, "html.parser")
    title = soup.title.get_text(strip=True) if soup.title else "(brak tytulu)"
    print(f"On page: {response.url} ({title})")

    for link in soup.find_all("a"):
        href = link.get("href")
        if not href or not href.startswith("/file/") or href == "/file/":
            continue

        full_url = urljoin(url, href)
        name = unquote(href).strip("/").split("/")[-1]

        if name.lower() in BLOCKED_FOLDERS:
            print(f"Blocked '{name}'")
            continue

        if href.endswith("/"):
            scrape_folder(session, full_url, os.path.join(cur_folder, name))
        elif href.lower().endswith(FILE_EXTENSIONS):
            save_file(session, full_url.replace("/file/", "/download/"), cur_folder, name)


def main() -> None:
    load_dotenv()
    cookie = os.getenv("MORDOR_COOKIE")

    session = requests.Session()
    if cookie:
        session.headers.update({"cookie": cookie})
    else:
        print("Brak MORDOR_COOKIE w .env - pobieranie bez sesji.")

    print("Downloading started")
    scrape_folder(session, START_PAGE, BASE_SAVE_DIR)
    print("\nFinished")


if __name__ == "__main__":
    main()

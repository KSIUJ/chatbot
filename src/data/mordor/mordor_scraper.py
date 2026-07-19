import os
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, unquote
import time
from dotenv import load_dotenv

load_dotenv()
M_COOKIE = os.getenv("MORDOR_COOKIE")

session = requests.Session()

if M_COOKIE:
    session.headers.update({'cookie': M_COOKIE})
else:
    print("Cannot find cookie")

BASE_SAVE_DIR = os.path.join("data", "mordor")

def save_img(img_url, out_folder, file_name):
    os.makedirs(out_folder, exist_ok=True)
    path = os.path.join(out_folder, file_name)
    
    if os.path.exists(path):
        print(f"Already exists: {file_name}")
        return

    try:
        response = session.get(img_url, stream=True)
        response.raise_for_status()
        print(f"On page: {response.url}")
        
        #soup = BeautifulSoup(response.text, 'html.parser')

        with open(path, 'wb') as file:
            for chunk in response.iter_content(1024):
                file.write(chunk)

        print(f"Downloaded: {file_name}")
        time.sleep(0.5) 

    except Exception as e:
        print(f"Error downloading {img_url}: {e}")

def scrape_cat(url, cur_folder):
    print(f"Entering: {cur_folder}")
    
    try:
        response = session.get(url)
        response.raise_for_status()
        
        print(f"On page: {response.url}")
        print(f"Page title: {BeautifulSoup(response.text, 'html.parser').title.text}")
       
        soup = BeautifulSoup(response.text, 'html.parser')
    
        print("Found links:")
        for link in soup.find_all('a'):
            print(f" -> {link.get('href')}")
        print("======================================")

    except Exception as e:
        print(f"Error loading page {url}: {e}")
        return

    for link in soup.find_all('a'):
        href = link.get('href')
        
        if not href or not href.startswith('/file/') or href == '/file/':
            continue
            
        full_url = urljoin(url, href)
        name = unquote(href).strip('/').split('/')[-1]

        if name.lower() in ['książki', 'ksiazki']:
            print(f"Blocked '{name}'")
            continue
        
        if href.endswith('/'):
            new_folder = os.path.join(cur_folder, name)
            scrape_cat(full_url, new_folder)
            
        elif href.lower().endswith(('.jpg', '.jpeg', '.png', '.pdf', '.doc')):
            direct_download_url = full_url.replace('/file/', '/download/')
            save_img(direct_download_url, cur_folder, name)

if __name__ == "__main__":
    PAGE = "https://mordor.ksi.ii.uj.edu.pl/file/"
    
    print("Downloading started")
    scrape_cat(PAGE, BASE_SAVE_DIR)
    print("\nFinished")
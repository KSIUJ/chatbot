import os
import pymupdf4llm
from langchain_text_splitters import RecursiveCharacterTextSplitter

BASE_DIR = os.path.join("data", "mordor")

def scrape_mordor(directory=BASE_DIR):
    if not os.path.exists(directory):
        return

    files = []
    for root, _, filenames in os.walk(directory):
        for filename in filenames:
            if not filename.startswith('.'):
                files.append(os.path.join(root, filename))

    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=200,
        length_function=len,
    )

    all_chunks = []

    # Test with small sample of files 
    for file_path in files[:5]:
        file_name = os.path.basename(file_path)
        parent_dir = os.path.dirname(file_path)
        _, file_extension = os.path.splitext(file_name)
        
        print(f"Processing file: {file_name})")

        try:
            clean_text = pymupdf4llm.to_markdown(file_path)
            
            if not clean_text:
                continue

            chunks = text_splitter.create_documents(
                texts=[clean_text],
                metadatas=[{
                    "source_file": file_name,
                    "file_type": file_extension,
                    "directory": parent_dir
                }]
            )
            
            all_chunks.extend(chunks)

        except Exception:
            print (f"Error processing file: {file_name}")
            continue
    

    # TODO : Save chunks to a database or file for later use 

if __name__ == "__main__":
    scrape_mordor()
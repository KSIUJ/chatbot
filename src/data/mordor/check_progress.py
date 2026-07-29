import os
from collections import Counter

BASE_DIR = os.path.join("data", "mordor")

def check_progress(directory=BASE_DIR):
    if not os.path.exists(directory):
        print(f"Directory {directory} does not exist.")
        return

    files = []
    for root, _, filenames in os.walk(directory):
        for filename in filenames:
            files.append(os.path.join(root, filename))

    file_count = len(files)
    print(f"Total files: {file_count}")
    if file_count > 0:
        extensions = [os.path.splitext(file)[1] for file in files]
        counts = Counter(extensions)
        for ext, count in counts.items():
            print(f"Extension {ext}: {count} files")

if __name__ == "__main__":
    check_progress()
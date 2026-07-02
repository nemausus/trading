import os
import sys

def strip_trailing_spaces(file_path):
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        modified = False
        new_lines = []
        for line in lines:
            content = line
            ending = ''
            if content.endswith('\n'):
                content = content[:-1]
                ending = '\n'
            if content.endswith('\r'):
                content = content[:-1]
                ending = '\r' + ending

            stripped = content.rstrip(' \t')
            new_line = stripped + ending
            if new_line != line:
                modified = True
            new_lines.append(new_line)

        if modified:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.writelines(new_lines)
            print(f"Stripped trailing spaces from: {file_path}")
    except Exception:
        # Ignore binary or non-UTF-8 files
        pass

def process_directory(root_dir):
    exclude_dirs = {'.git', '.venv', '__pycache__', '.idea', '.gemini', 'venv'}
    exclude_extensions = {'.png', '.jpg', '.jpeg', '.webp', '.ico', '.pyc', '.zip', '.tar', '.gz', '.db'}

    for dirpath, dirnames, filenames in os.walk(root_dir):
        # Exclude directories in-place
        dirnames[:] = [d for d in dirnames if d not in exclude_dirs]

        for name in filenames:
            ext = os.path.splitext(name)[1].lower()
            if ext in exclude_extensions:
                continue

            file_path = os.path.join(dirpath, name)
            strip_trailing_spaces(file_path)

if __name__ == '__main__':
    target_dir = sys.argv[1] if len(sys.argv) > 1 else '.'
    # Resolve absolute path to be robust
    abs_target_dir = os.path.abspath(target_dir)
    process_directory(abs_target_dir)

import os
import subprocess
import sys
import shutil

def run_command(command):
    print(f"Running: {command}")
    process = subprocess.run(command, shell=True, check=False) # Changed check to False to avoid immediate exit on error
    if process.returncode != 0:
        print(f"Command failed with exit code {process.returncode}")
        print(f"Output: {process.stdout.decode()}")
        print(f"Error: {process.stderr.decode()}")
        sys.exit(1)

def main():
    # Nettoyer les anciens fichiers de build
    print("Cleaning up previous build...")
    for folder in ["build", "dist"]:
        if os.path.exists(folder):
            try:
                shutil.rmtree(folder)
                print(f"  Removed {folder}/")
            except OSError as e:
                print(f"  Error removing {folder}/: {e}")
                print("  Please close any programs that might be using these files and try again.")
                sys.exit(1) # Exit if cleanup fails
    if os.path.exists("CaptionLab.spec"):
        try:
            os.remove("CaptionLab.spec")
            print("  Removed CaptionLab.spec")
        except OSError as e:
            print(f"  Error removing CaptionLab.spec: {e}")
            print("  Please close any programs that might be using this file and try again.")
            sys.exit(1)

    # Créer l'icône
    print("Creating icon...")
    run_command("python create_icon.py")
    
    # Installer les dépendances
    print("Installing requirements...")
    run_command("pip install -r requirements.txt")
    
    # Construire l'exécutable avec --noupx
    print("Building executable (without UPX compression)...")
    run_command("pyinstaller --onefile --windowed --icon=icon.ico --name CaptionLab --noupx main.py")
    
    print("Done!")

if __name__ == "__main__":
    main() 
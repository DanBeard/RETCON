import os
import importlib

# Get the current directory of the package
package_dir = os.path.dirname(__file__)

# Loop through all files in the directory
for filename in os.listdir(package_dir):
    # Check if the file is a Python file and not __init__.py
    if filename.endswith(".py") and filename != "__init__.py":
        module_name = filename[:-3]  # Remove the .py extension
        importlib.import_module(f".{module_name}", package=__name__)
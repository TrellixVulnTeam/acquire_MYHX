
import sys
import os

# # Added path for Acquire source in tests
# sys.path.insert(0, os.path.abspath("../"))

# # Added for import of services modules in tests
# sys.path.insert(0, os.path.abspath("../services"))

# Added for import of services modules in tests
sys.path.insert(0, os.path.abspath("services"))

# Added for import of openghg from testing directory
sys.path.insert(0, os.path.abspath("."))

# load all of the common fixtures used by the mocked tests
pytest_plugins = ["services.fixtures.mocked_services"]

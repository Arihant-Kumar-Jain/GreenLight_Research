import os
import tempfile

os.environ["GLR_DB_PATH"] = os.path.join(tempfile.mkdtemp(), "test.db")

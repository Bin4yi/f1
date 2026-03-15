import pytest
import sys

try:
    pytest.main(["tests/phase8_server_test.py", "--collect-only"])
except Exception as e:
    print(f"Caught exception: {e}")
    import traceback
    traceback.print_exc()

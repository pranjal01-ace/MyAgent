import sys
import unittest
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from backend.agent.tools import (
    get_current_time, get_system_info, read_clipboard,
    take_screenshot, list_files, create_file, read_file,
    open_application, resolve_workspace_path
)
from backend.agent.permissions import permission_manager, PermissionLevel

class TestAgentTools(unittest.TestCase):
    def test_get_current_time(self):
        time_str = get_current_time()
        self.assertIn("Current time is", time_str)

    def test_get_system_info(self):
        info_str = get_system_info()
        self.assertIn("CPU:", info_str)
        self.assertIn("RAM:", info_str)

    def test_file_operations(self):
        test_file = "data/test_companion_file.txt"
        create_res = create_file(test_file, "Hello from Desktop AI Mate!")
        self.assertIn("Successfully created", create_res)

        read_res = read_file(test_file)
        self.assertIn("Hello from Desktop AI Mate!", read_res)

        list_res = list_files("data")
        self.assertIn("test_companion_file.txt", list_res)

        # Cleanup
        fpath = BASE_DIR / test_file
        if fpath.exists():
            fpath.unlink()

    def test_permissions(self):
        # Safe tool
        allowed, level, _ = permission_manager.check_permission("get_time", {})
        self.assertTrue(allowed)
        self.assertEqual(level, PermissionLevel.SAFE)

        # Dangerous tool
        allowed, level, _ = permission_manager.check_permission("delete_file", {"filepath": "important.txt"})
        self.assertFalse(allowed)
        self.assertEqual(level, PermissionLevel.DANGEROUS)

    def test_command_injection_rejection(self):
        payloads = [
            "notepad.exe && whoami",
            "notepad.exe & whoami",
            "notepad.exe | whoami",
            "notepad.exe; whoami",
            "notepad.exe $(whoami)",
            "notepad.exe `whoami`",
            "notepad.exe > output.txt",
            "notepad.exe\nwhoami",
            "cmd.exe /c calc",
        ]
        for payload in payloads:
            res = open_application(payload)
            self.assertTrue(
                "Access denied" in res or "not in the approved application allowlist" in res,
                f"Payload {payload} should be rejected, got: {res}"
            )

    def test_path_traversal_rejection(self):
        traversals = [
            "../../../Windows/win.ini",
            "..\\..\\Windows\\System32\\drivers\\etc\\hosts",
            "C:\\Windows\\win.ini",
            "%2e%2e%2fWindows/win.ini",
            "data/test.txt\x00.exe",
            "/etc/passwd",
        ]
        for path in traversals:
            with self.assertRaises((PermissionError, ValueError)):
                resolve_workspace_path(path)
            res = read_file(path)
            self.assertTrue("access restricted" in res.lower() or "access denied" in res.lower(), f"read_file should deny access to: {path}")

if __name__ == "__main__":
    unittest.main()

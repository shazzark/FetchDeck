import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fetchdeck.engine import available_output_name, parse_session_entries
from fetchdeck.filesystem import RecycleBinError, move_to_recycle_bin


class DownloadControlTests(unittest.TestCase):
    def test_restart_destination_avoids_existing_names(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            self.assertEqual(available_output_name(folder, "archive.zip"), "archive.zip")
            (folder / "archive.zip").touch()
            self.assertEqual(available_output_name(folder, "archive.zip"), "archive.1.zip")
            (folder / "archive.1.zip").touch()
            self.assertEqual(available_output_name(folder, "archive.zip"), "archive.2.zip")

    def test_session_metadata_restores_source_and_custom_output_folder(self):
        entries = parse_session_entries(
            "https://downloads.example.test/file.zip\t\n"
            " gid=0123456789abcdef\n"
            " dir=C:\\Users\\Test\\Desktop\\chosen\n"
            " out=custom-name.zip\n\n"
        )
        uri, folder, output = entries["0123456789abcdef"]
        self.assertEqual(uri, "https://downloads.example.test/file.zip")
        self.assertEqual(str(folder), r"C:\Users\Test\Desktop\chosen")
        self.assertEqual(output, "custom-name.zip")

    @unittest.skipUnless(os.name == "nt", "Windows Recycle Bin operation is Windows-only")
    def test_recycle_bin_uses_undo_flag_and_reports_shell_errors(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "download.bin"
            target.write_bytes(b"temporary")
            with patch("fetchdeck.filesystem.ctypes.windll.shell32.SHFileOperationW", return_value=0) as operation:
                move_to_recycle_bin([target])
                request = operation.call_args.args[0]._obj
                self.assertEqual(request.wFunc, 3)
                self.assertEqual(request.fFlags, 0x0040)
                self.assertEqual(request.pFrom.split("\0")[:1], [str(target)])

            with patch("fetchdeck.filesystem.ctypes.windll.shell32.SHFileOperationW", return_value=5):
                with self.assertRaises(RecycleBinError):
                    move_to_recycle_bin([target])


if __name__ == "__main__":
    unittest.main()

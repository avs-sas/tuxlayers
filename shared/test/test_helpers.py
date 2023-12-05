"""Unit tests for helpers"""

__copyright__ = "Copyright (c) 2023, Avnet EMG GmbH"
__license__ = "MIT"
__version__ = "0.1.0"
__status__ = "Development"

import os

import tempfile

#import pytest

from shared.helpers import remove_empty_folders

def test_remove_empty_folders():
    """Unit test to check basic behaviour of folder cleanup function"""
    with tempfile.TemporaryDirectory() as tmpdirname:

        folders = [
            os.path.join(tmpdirname, "folder_a"),
            os.path.join(tmpdirname, "folder_d"),
            os.path.join(tmpdirname, "folder_c"),
            os.path.join(tmpdirname, "folder_c", "subfolder_c_a"),
            os.path.join(tmpdirname, "folder_d", "subfolder_d_a")
        ]

        empty_folders = [
            os.path.join(tmpdirname, "folder_empty_b"),
            os.path.join(tmpdirname, "folder_c", "subfolder_empty_c_b"),
        ]
        for folder in folders:
            os.mkdir(folder)

        for folder in empty_folders:
            os.mkdir(folder)

        files = [
            os.path.join(tmpdirname, "folder_a", "file_a.txt"),
            os.path.join(tmpdirname, "folder_a", "file_b.txt"),
            os.path.join(tmpdirname, "folder_d", "file_a.txt"),
            os.path.join(tmpdirname, "folder_c", "subfolder_c_a", "file_a.txt"),
            os.path.join(tmpdirname, "folder_d", "subfolder_d_a", "file_a.txt")
        ]

        for file in files:
            with open(file, encoding="utf-8", mode="a"):
                pass

        remove_empty_folders(tmpdirname, False)

        for file in files:
            assert os.path.isfile(file) is True

        for folder in empty_folders:
            assert os.path.isdir(folder) is False

        for folder in folders:
            assert os.path.isdir(folder) is True


def test_remove_empty_folders_with_root():
    """Unit test to check basic behaviour of folder cleanup function"""
    with tempfile.TemporaryDirectory() as tmpdirname:
        empty_root = os.path.join(tmpdirname, "base_a")
        non_empty_root = os.path.join(tmpdirname, "base_b")

        os.mkdir(empty_root)

        folders = [
            os.path.join(empty_root, "folder_a"),
            os.path.join(empty_root, "folder_d"),
            os.path.join(empty_root, "folder_c"),
            os.path.join(empty_root, "folder_c", "subfolder_c_a"),
            os.path.join(empty_root, "folder_d", "subfolder_d_a")
        ]

        empty_folders = [
            os.path.join(empty_root, "folder_empty_b"),
            os.path.join(empty_root, "folder_c", "subfolder_empty_c_b"),
        ]
        for folder in folders:
            os.mkdir(folder)

        for folder in empty_folders:
            os.mkdir(folder)


        remove_empty_folders(empty_root, True)

        for folder in empty_folders:
            assert os.path.isdir(folder) is False

        for folder in folders:
            assert os.path.isdir(folder) is False

        assert os.path.isdir(empty_root) is False

        os.mkdir(non_empty_root)

        folders = [
            os.path.join(non_empty_root, "folder_a"),
            os.path.join(non_empty_root, "folder_d"),
            os.path.join(non_empty_root, "folder_c"),
            os.path.join(non_empty_root, "folder_c", "subfolder_c_a"),
            os.path.join(non_empty_root, "folder_d", "subfolder_d_a")
        ]

        empty_folders = [
            os.path.join(non_empty_root, "folder_empty_b"),
            os.path.join(non_empty_root, "folder_c", "subfolder_empty_c_b"),
        ]

        for folder in folders:
            os.mkdir(folder)

        for folder in empty_folders:
            os.mkdir(folder)

        files = [
            os.path.join(non_empty_root, "folder_a", "file_a.txt"),
            os.path.join(non_empty_root, "folder_a", "file_b.txt"),
            os.path.join(non_empty_root, "folder_d", "file_a.txt"),
            os.path.join(non_empty_root, "folder_c", "subfolder_c_a", "file_a.txt"),
            os.path.join(non_empty_root, "folder_d", "subfolder_d_a", "file_a.txt")
        ]

        for file in files:
            with open(file, encoding="utf-8", mode="a"):
                pass

        remove_empty_folders(non_empty_root, True)

        for file in files:
            assert os.path.isfile(file) is True

        for folder in empty_folders:
            assert os.path.isdir(folder) is False

        for folder in folders:
            assert os.path.isdir(folder) is True

        assert os.path.isdir(non_empty_root) is True

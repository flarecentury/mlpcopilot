"""Tests for filesystem utility functions."""

import pytest
import os
import tempfile
from pathlib import Path

from fs_explorer.fs import (
    describe_dir_content,
    read_file,
    grep_file_content,
    glob_paths,
    parse_file,
    preview_file,
    scan_folder,
    clear_document_cache,
    SUPPORTED_EXTENSIONS,
)


class TestDescribeDirContent:
    """Tests for describe_dir_content function."""
    
    def test_valid_directory(self) -> None:
        """Test describing a valid directory with files and subfolders."""
        description = describe_dir_content("tests/testfiles")
        assert "Content of tests/testfiles" in description
        assert "tests/testfiles/file1.txt" in description
        assert "tests/testfiles/file2.md" in description
        assert "tests/testfiles/last" in description

    def test_nonexistent_directory(self) -> None:
        """Test describing a directory that doesn't exist."""
        description = describe_dir_content("tests/testfile")
        assert description == "No such directory: tests/testfile"

    def test_directory_without_subfolders(self) -> None:
        """Test describing a directory that has no subdirectories."""
        description = describe_dir_content("tests/testfiles/last")
        assert "Content of tests/testfiles/last" in description
        assert "tests/testfiles/last/lastfile.txt" in description
        assert "This folder does not have any sub-folders" in description


class TestReadFile:
    """Tests for read_file function."""
    
    def test_valid_file(self) -> None:
        """Test reading a valid text file."""
        content = read_file("tests/testfiles/file1.txt")
        assert content.strip() == "this is a test"

    def test_nonexistent_file(self) -> None:
        """Test reading a file that doesn't exist."""
        content = read_file("tests/testfiles/file2.txt")
        assert content == "No such file: tests/testfiles/file2.txt"


class TestGrepFileContent:
    """Tests for grep_file_content function."""
    
    def test_pattern_match(self) -> None:
        """Test searching for a pattern that exists."""
        result = grep_file_content("tests/testfiles/file2.md", r"(are|is) a test")
        assert "MATCHES for (are|is) a test" in result
        assert "is" in result

    def test_no_match(self) -> None:
        """Test searching for a pattern that doesn't exist."""
        result = grep_file_content("tests/testfiles/last/lastfile.txt", r"test")
        assert result == "No matches found"

    def test_nonexistent_file(self) -> None:
        """Test searching in a file that doesn't exist."""
        result = grep_file_content("tests/testfiles/file2.txt", r"test")
        assert result == "No such file: tests/testfiles/file2.txt"


class TestGlobPaths:
    """Tests for glob_paths function."""
    
    def test_pattern_match(self) -> None:
        """Test finding files that match a glob pattern."""
        result = glob_paths("tests/testfiles", "file?.*")
        assert "MATCHES for file?.* in tests/testfiles" in result
        assert "file1.txt" in result
        assert "file2.md" in result

    def test_no_match(self) -> None:
        """Test a pattern that matches nothing."""
        result = glob_paths("tests/testfiles", "nonexistent*")
        assert result == "No matches found"

    def test_nonexistent_directory(self) -> None:
        """Test glob in a directory that doesn't exist."""
        result = glob_paths("tests/nonexistent", "*.txt")
        assert result == "No such directory: tests/nonexistent"


class TestDocumentParsing:
    """Tests for document parsing functions (parse_file, preview_file)."""
    
    def setup_method(self) -> None:
        """Clear cache before each test."""
        clear_document_cache()

    def test_parse_file_nonexistent(self) -> None:
        """Test parsing a file that doesn't exist."""
        content = parse_file("data/nonexistent.pdf")
        assert content == "No such file: data/nonexistent.pdf"

    def test_parse_file_unsupported_extension(self) -> None:
        """Test parsing a file with unsupported extension."""
        content = parse_file("tests/testfiles/file1.txt")
        assert "Unsupported file extension: .txt" in content

    def test_preview_file_nonexistent(self) -> None:
        """Test previewing a file that doesn't exist."""
        content = preview_file("data/nonexistent.pdf")
        assert content == "No such file: data/nonexistent.pdf"

    def test_preview_file_unsupported_extension(self) -> None:
        """Test previewing a file with unsupported extension."""
        content = preview_file("tests/testfiles/file1.txt")
        assert "Unsupported file extension: .txt" in content

    @pytest.mark.skipif(
        not os.path.exists("data/large_acquisition"),
        reason="Test documents not generated"
    )
    def test_parse_file_pdf(self) -> None:
        """Test parsing an actual PDF file."""
        # Use one of the generated test PDFs
        pdf_files = list(Path("data/large_acquisition").glob("*.pdf"))
        if pdf_files:
            content = parse_file(str(pdf_files[0]))
            assert len(content) > 0
            assert "Error" not in content

    @pytest.mark.skipif(
        not os.path.exists("data/large_acquisition"),
        reason="Test documents not generated"
    )
    def test_preview_file_pdf(self) -> None:
        """Test previewing an actual PDF file."""
        pdf_files = list(Path("data/large_acquisition").glob("*.pdf"))
        if pdf_files:
            content = preview_file(str(pdf_files[0]), max_chars=500)
            assert "=== PREVIEW of" in content
            # Preview should be limited
            assert len(content) < 2000  # Preview + header + truncation message


class TestScanFolder:
    """Tests for scan_folder function."""
    
    def setup_method(self) -> None:
        """Clear cache before each test."""
        clear_document_cache()

    def test_nonexistent_directory(self) -> None:
        """Test scanning a directory that doesn't exist."""
        result = scan_folder("nonexistent/path")
        assert result == "No such directory: nonexistent/path"

    def test_empty_directory(self) -> None:
        """Test scanning a directory with no supported documents."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a non-document file
            Path(tmpdir, "test.txt").write_text("hello")
            result = scan_folder(tmpdir)
            assert "No supported documents found" in result

    @pytest.mark.skipif(
        not os.path.exists("data/large_acquisition"),
        reason="Test documents not generated"
    )
    def test_scan_folder_with_documents(self) -> None:
        """Test scanning a folder with actual documents."""
        result = scan_folder("data/large_acquisition", max_workers=2)
        assert "PARALLEL DOCUMENT SCAN" in result
        assert "Found" in result
        assert "documents" in result


class TestSupportedExtensions:
    """Tests for supported extensions configuration."""
    
    def test_supported_extensions_is_frozenset(self) -> None:
        """Verify SUPPORTED_EXTENSIONS is immutable."""
        assert isinstance(SUPPORTED_EXTENSIONS, frozenset)
    
    def test_common_extensions_supported(self) -> None:
        """Verify common document extensions are supported."""
        assert ".pdf" in SUPPORTED_EXTENSIONS
        assert ".docx" in SUPPORTED_EXTENSIONS
        assert ".md" in SUPPORTED_EXTENSIONS

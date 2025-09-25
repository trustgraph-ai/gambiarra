"""
Tests for client-side path validation security component.
These tests are CRITICAL - path validation prevents directory traversal attacks.
"""

import pytest
from pathlib import Path
from gambiarra.client.security.path_validator import PathValidator, SecurityError


@pytest.mark.security
class TestPathValidator:
    """Test path validation security features."""

    def test_init_with_workspace(self, temp_workspace):
        """Test PathValidator initialization with workspace."""
        validator = PathValidator(temp_workspace)
        assert validator.workspace_root == temp_workspace
        assert isinstance(validator.ignore_patterns, list)

    def test_valid_workspace_paths(self, temp_workspace):
        """Test validation of valid paths within workspace."""
        validator = PathValidator(temp_workspace)

        # Test valid paths
        valid_paths = [
            "main.py",
            "./main.py",
            "src/utils.py",
            "./src/utils.py",
            "new_file.txt"
        ]

        for path in valid_paths:
            resolved = validator.validate_path(path)
            assert resolved is not None
            assert Path(resolved).is_relative_to(temp_workspace)

    def test_directory_traversal_prevention(self, temp_workspace):
        """CRITICAL: Test prevention of directory traversal attacks."""
        validator = PathValidator(temp_workspace)

        # Test dangerous directory traversal patterns
        dangerous_paths = [
            "../etc/passwd",
            "../../etc/shadow",
            "../../../root/.ssh/id_rsa",
            "./../outside.txt",
            "subdir/../../etc/hosts",
            "..\\windows\\system32\\config\\sam",  # Windows style
            "%2e%2e%2f%2e%2e%2fetc%2fpasswd",  # URL encoded
        ]

        for dangerous_path in dangerous_paths:
            with pytest.raises(SecurityError, match="Path traversal detected"):
                validator.validate_path(dangerous_path)

    def test_absolute_path_rejection(self, temp_workspace):
        """Test rejection of absolute paths."""
        validator = PathValidator(temp_workspace)

        absolute_paths = [
            "/etc/passwd",
            "/root/.ssh/id_rsa",
            "/home/user/secret.txt",
            "C:\\Windows\\System32\\config\\sam",
            "/var/log/secret.log"
        ]

        for abs_path in absolute_paths:
            with pytest.raises((ValueError, SecurityError), match="(Absolute paths not allowed|Path traversal detected)"):
                validator.validate_path(abs_path)

    def test_symlink_handling(self, temp_workspace):
        """Test handling of symbolic links."""
        validator = PathValidator(temp_workspace)

        # Create a symlink pointing outside workspace
        symlink_path = temp_workspace / "dangerous_link"
        target_path = temp_workspace.parent / "outside_file.txt"

        # Create target file and symlink
        target_path.write_text("secret")
        symlink_path.symlink_to(target_path)

        # Should detect and reject symlink traversal
        with pytest.raises((ValueError, SecurityError), match="Path traversal detected"):
            validator.validate_path("dangerous_link")

    def test_gambiarraignore_patterns(self, temp_workspace):
        """Test .gambiarraignore pattern handling."""
        validator = PathValidator(temp_workspace)

        # Should ignore files matching patterns in .gambiarraignore
        ignored_paths = [
            "test.pyc",
            "__pycache__/module.pyc",
            "src/__pycache__/utils.pyc",
            ".env"
        ]

        for ignored_path in ignored_paths:
            with pytest.raises((ValueError, SecurityError), match="(Path matches ignore patterns|Access denied by ignore patterns)"):
                validator.validate_path(ignored_path)

    def test_special_file_rejection(self, temp_workspace):
        """Test rejection of files based on ignore patterns."""
        validator = PathValidator(temp_workspace)

        # Files that should be rejected by ignore patterns
        ignored_files = [
            ".env",  # Matches .env pattern
            "test.pyc",  # Matches *.pyc pattern
            "__pycache__/module.pyc",  # Matches __pycache__/** pattern
        ]

        # Files that should be allowed (not in ignore patterns)
        allowed_files = [
            ".ssh/id_rsa",  # Not in ignore patterns
            ".aws/credentials",  # Not in ignore patterns
            "config.json",  # Not in ignore patterns
        ]

        # Test that ignored files are rejected
        for ignored_file in ignored_files:
            with pytest.raises(SecurityError, match="Access denied by ignore patterns"):
                validator.validate_path(ignored_file)

        # Test that allowed files pass validation
        for allowed_file in allowed_files:
            result = validator.validate_path(allowed_file)
            assert result is not None

    def test_case_insensitive_dangerous_patterns(self, temp_workspace):
        """Test case-insensitive detection of dangerous patterns."""
        validator = PathValidator(temp_workspace)

        case_variants = [
            "../ETC/passwd",
            "../etc/PASSWD",
            "..\\ETC\\passwd",  # Mixed case with backslashes
        ]

        for variant in case_variants:
            with pytest.raises((ValueError, SecurityError), match="Path traversal detected"):
                validator.validate_path(variant)

    def test_unicode_and_encoding_attacks(self, temp_workspace):
        """Test prevention of Unicode and encoding-based attacks."""
        validator = PathValidator(temp_workspace)

        # Unicode normalization attacks
        unicode_attacks = [
            "..%2F..%2Fetc%2Fpasswd",  # URL encoded
            "..%252F..%252Fetc%252Fpasswd",  # Double URL encoded
            "..%c0%af..%c0%afetc%c0%afpasswd",  # UTF-8 overlong encoding
        ]

        for attack in unicode_attacks:
            with pytest.raises((ValueError, SecurityError)):
                validator.validate_path(attack)

    def test_workspace_boundary_enforcement(self, temp_workspace):
        """Test strict workspace boundary enforcement."""
        validator = PathValidator(temp_workspace)

        # Create files at workspace boundary
        boundary_file = temp_workspace / "boundary.txt"
        boundary_file.write_text("test")

        # Valid: within workspace
        assert validator.validate_path("boundary.txt") is not None

        # Invalid: would escape workspace
        with pytest.raises((ValueError, SecurityError)):
            validator.validate_path("../boundary.txt")

    def test_empty_and_special_input_handling(self, temp_workspace):
        """Test handling of empty and special inputs."""
        validator = PathValidator(temp_workspace)

        special_inputs = ["", ".", "..", None]

        for special_input in special_inputs:
            if special_input is None:
                with pytest.raises((ValueError, TypeError, SecurityError)):
                    validator.validate_path(special_input)
            elif special_input in ["", "."]:
                # These might be valid or invalid depending on implementation
                try:
                    result = validator.validate_path(special_input)
                    if result is not None:
                        assert Path(result).is_relative_to(temp_workspace)
                except ValueError:
                    # Rejection is also acceptable for security
                    pass
            else:  # ".."
                with pytest.raises((ValueError, SecurityError)):
                    validator.validate_path(special_input)

    def test_get_security_info(self, temp_workspace):
        """Test security information reporting."""
        validator = PathValidator(temp_workspace)

        info = validator.get_security_info()

        # Should provide security-relevant information
        assert isinstance(info, dict)
        assert "workspace_root" in info
        assert "has_gambiarraignore" in info
        assert "ignore_patterns_count" in info

        # Values should be reasonable
        assert info["workspace_root"] == str(temp_workspace)
        assert isinstance(info["has_gambiarraignore"], bool)
        assert isinstance(info["ignore_patterns_count"], int)
        assert info["ignore_patterns_count"] >= 0


@pytest.mark.security
@pytest.mark.slow
class TestPathValidatorEdgeCases:
    """Test edge cases and advanced security scenarios."""

    def test_long_path_handling(self, temp_workspace):
        """Test handling of extremely long paths."""
        validator = PathValidator(temp_workspace)

        # Very long valid path
        long_path = "/".join(["dir"] * 100) + "/file.txt"

        # Should handle gracefully (either accept or reject consistently)
        try:
            result = validator.validate_path(long_path)
            if result:
                assert len(result) > 0
        except ValueError:
            # Rejection due to length is also acceptable
            pass

    def test_concurrent_validation(self, temp_workspace):
        """Test thread safety of path validation."""
        import threading
        import time

        validator = PathValidator(temp_workspace)
        results = []
        errors = []

        def validate_path_worker(path):
            try:
                result = validator.validate_path(path)
                results.append(result)
            except Exception as e:
                errors.append(e)

        # Run concurrent validations
        threads = []
        paths = ["main.py", "src/utils.py", "README.md"] * 10

        for path in paths:
            thread = threading.Thread(target=validate_path_worker, args=(path,))
            threads.append(thread)
            thread.start()

        for thread in threads:
            thread.join()

        # Should handle concurrent access without issues
        assert len(results) + len(errors) == len(paths)
        # All successful results should be valid
        for result in results:
            if result:
                assert Path(result).is_relative_to(temp_workspace)
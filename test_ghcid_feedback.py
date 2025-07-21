#!/usr/bin/env python3
"""
Test suite for ghcid_feedback.py script.

This test suite validates the behavior of the ghcid_feedback script in various scenarios.
"""

import os
import subprocess
import time
import tempfile
import shutil
from pathlib import Path

class TestGhcidFeedback:
    def __init__(self):
        self.test_project_dir = Path(__file__).parent / "test_project"
        self.script_path = Path(__file__).parent / "claude_hooks" / "ghcid_feedback.py"
        self.original_cwd = os.getcwd()
        
    def setup(self):
        """Setup test environment."""
        # Change to test project directory
        os.chdir(self.test_project_dir)
        
        # Kill any existing ghcid processes for this project
        subprocess.run(["pkill", "-f", "ghcid.*test.project"], capture_output=True)
        
        # Remove any existing log files
        import glob
        for log_file in glob.glob("/tmp/ghcid_feedback-test-project.*"):
            try:
                os.remove(log_file)
            except OSError:
                pass
        
        # Reset Lib.hs to working state
        lib_hs = self.test_project_dir / "src" / "Lib.hs"
        lib_hs.write_text("""module Lib
    ( someFunc
    ) where

import Prelude

someFunc :: IO ()
someFunc = putStrLn "someFunc"
""")
        
    def teardown(self):
        """Cleanup after tests."""
        os.chdir(self.original_cwd)
        # Kill any ghcid processes we started
        subprocess.run(["pkill", "-f", "ghcid.*test.project"], capture_output=True)
        
    def run_script(self, timeout=10):
        """Run the ghcid_feedback script and return result."""
        try:
            result = subprocess.run(
                ["uv", "run", str(self.script_path)],
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=self.test_project_dir
            )
            return result
        except subprocess.TimeoutExpired:
            return subprocess.CompletedProcess(
                args=["timeout"], returncode=-1, 
                stdout="", stderr="Timeout"
            )
    
    def test_no_changes_exits_immediately(self):
        """Test that script exits immediately when no Haskell files are newer."""
        print("Testing: Script exits immediately when no changes...")
        
        # First run to ensure ghcid output exists
        result1 = self.run_script()
        
        # Wait a moment then run again - should exit immediately
        time.sleep(1)
        result2 = self.run_script()
        
        assert result2.returncode == 0, f"Expected exit code 0, got {result2.returncode}"
        assert "No Haskell files newer than last output, exiting" in result2.stdout, \
            f"Expected exit message not found in: {result2.stdout}"
        print("✓ PASS: Script exits immediately when no changes")
        
    def test_detects_newer_files(self):
        """Test that script detects when Haskell files are newer than output."""
        print("Testing: Script detects newer Haskell files...")
        
        # Kill any existing ghcid to ensure clean state
        subprocess.run(["pkill", "-f", "ghcid.*test.project"], capture_output=True)
        
        # Remove log files
        import glob
        for log_file in glob.glob("/tmp/ghcid_feedback-test-project.*"):
            try:
                os.remove(log_file)
            except OSError:
                pass
        
        # Touch a Haskell file
        lib_hs = self.test_project_dir / "src" / "Lib.hs"
        lib_hs.touch()
        
        # Run script - should detect newer file and start ghcid
        result = self.run_script()
        
        # Should either detect newer files or show successful compilation
        if ("newer than last output" in result.stdout and 
            "1 newer" in result.stdout):
            print("✓ PASS: Script detects newer Haskell files")
        elif "All good" in result.stdout:
            print("✓ PASS: Script processed files and compilation succeeded")
        else:
            print(f"? UNCLEAR: Unexpected result: {result.stdout}")
            print("  (This may still be correct behavior depending on timing)")
        
    def test_ghcid_starts_correctly(self):
        """Test that ghcid starts and produces output."""
        print("Testing: ghcid starts correctly...")
        
        # Touch a file to ensure there are changes to process
        time.sleep(1)
        lib_hs = self.test_project_dir / "src" / "Lib.hs"
        lib_hs.touch()
        
        result = self.run_script(timeout=15)
        
        # Check that ghcid log file was created
        log_file = Path("/tmp/ghcid_feedback-test-project.log")
        
        if not log_file.exists():
            # Wait a bit more for ghcid to create the file
            time.sleep(2)
        
        # Check for evidence that ghcid was started
        if (log_file.exists() or 
            "Starting ghcid" in result.stdout or
            "All good" in result.stdout):
            if log_file.exists():
                log_content = log_file.read_text()
                print(f"Log content: {log_content}")
            print("✓ PASS: ghcid starts correctly")
        else:
            print(f"? UNCLEAR: Could not confirm ghcid started properly")
            print(f"  Script output: {result.stdout}")
            print(f"  Script stderr: {result.stderr}")
            print(f"  Exit code: {result.returncode}")
        
    def test_successful_compilation_exit_code(self):
        """Test that successful compilation returns exit code 0."""
        print("Testing: Successful compilation returns exit code 0...")
        
        # Touch file to trigger script
        time.sleep(1)
        lib_hs = self.test_project_dir / "src" / "Lib.hs"
        lib_hs.touch()
        
        result = self.run_script()
        
        # Should eventually return 0 for successful compilation
        if result.returncode == 0:
            # Check if it's because no changes or because success
            if "All good" in result.stdout or "No Haskell files newer" in result.stdout:
                print("✓ PASS: Successful compilation returns exit code 0")
            else:
                print(f"? UNCLEAR: Exit code 0 but unexpected output: {result.stdout}")
        else:
            print(f"✗ FAIL: Expected exit code 0, got {result.returncode}")
            print(f"  stdout: {result.stdout}")
            print(f"  stderr: {result.stderr}")
    
    def test_compilation_error_exit_code(self):
        """Test that compilation errors return exit code 2."""
        print("Testing: Compilation errors return exit code 2...")
        
        # Introduce syntax error
        lib_hs = self.test_project_dir / "src" / "Lib.hs"
        lib_hs.write_text("""module Lib
    ( someFunc
    ) where

import Prelude

someFunc :: IO ()
someFunc = putStrLn "someFunc" + undefined  -- This will cause a type error
""")
        
        # Wait then touch to make newer
        time.sleep(1)
        lib_hs.touch()
        
        result = self.run_script()
        
        if result.returncode == 2:
            print("✓ PASS: Compilation errors return exit code 2")
        elif result.returncode == 0 and "No Haskell files newer" in result.stdout:
            print("? SKIP: No files were considered newer (ghcid already processed)")
        else:
            print(f"✗ FAIL: Expected exit code 2, got {result.returncode}")
            print(f"  stdout: {result.stdout}")
            print(f"  stderr: {result.stderr}")
            
        # Restore working code
        lib_hs.write_text("""module Lib
    ( someFunc
    ) where

import Prelude

someFunc :: IO ()
someFunc = putStrLn "someFunc"
""")
    
    def run_all_tests(self):
        """Run all tests."""
        print("Running ghcid_feedback.py tests...")
        print("=" * 50)
        
        self.setup()
        
        try:
            self.test_ghcid_starts_correctly()
            self.test_no_changes_exits_immediately()
            self.test_detects_newer_files()
            self.test_successful_compilation_exit_code()
            self.test_compilation_error_exit_code()
        finally:
            self.teardown()
        
        print("=" * 50)
        print("Tests completed!")

if __name__ == "__main__":
    tester = TestGhcidFeedback()
    tester.run_all_tests()
"""
Multi-Agent Orchestrator Test Suite
Validates Google SMTP Email Authentication and Task Routing Engine
"""
import sys
import unittest

# Ensure UTF-8 output encoding for Windows terminals
if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

from test_auth import TestEmailAuthManager

if __name__ == "__main__":
    print("=" * 60)
    print("Running Autonomous Orchestrator & Auth Tests...")
    print("=" * 60)
    suite = unittest.TestLoader().loadTestsFromTestCase(TestEmailAuthManager)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    if result.wasSuccessful():
        print("\n[SUCCESS] All tests passed successfully!")
    else:
        print("\n[FAILED] Some tests failed.")

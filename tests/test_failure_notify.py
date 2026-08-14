import os
import unittest
from unittest.mock import patch

from failure_notify import build_message


class FailureNotifyTest(unittest.TestCase):
    @patch.dict(
        os.environ,
        {
            "MAIL_USERNAME": "sender@example.com",
            "MAIL_RECEIVER": "receiver@example.com",
            "WORKFLOW_NAME": "Dashboard Build",
            "RUN_URL": "https://github.com/example/actions/runs/1",
            "GITHUB_SHA": "1234567890abcdef",
        },
        clear=False,
    )
    def test_message_contains_actionable_run_link(self):
        message = build_message()

        self.assertIn("Dashboard Build", message["Subject"])
        self.assertIn("https://github.com/example/actions/runs/1", message.get_content())
        self.assertIn("1234567890ab", message.get_content())


if __name__ == "__main__":
    unittest.main()

import io
from unittest.mock import Mock
from test_regressions import IsolatedTest, bot


class PublicPagesTests(IsolatedTest):
    def test_about_and_privacy_are_public_static_html(self):
        for path in ("/about", "/privacy"):
            handler = object.__new__(bot.HealthCheckHandler)
            handler.path = path
            handler.send_response = Mock()
            handler.send_header = Mock()
            handler.end_headers = Mock()
            handler.wfile = io.BytesIO()
            handler.do_GET()
            handler.send_response.assert_called_once_with(200)
            page = handler.wfile.getvalue().decode()
            self.assertIn("YoBot", page)
            self.assertIn("<!doctype html>", page)
            self.assertNotIn("refresh_token", page)

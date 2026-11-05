import time
from unittest.mock import Mock, patch

from test_regressions import IsolatedTest, config, OTHER, ai_agent, bot
import linkedin_service as linkedin


class LinkedInTests(IsolatedTest):
    def setUp(self):
        super().setUp()
        self.stack.enter_context(patch.object(config, "LINKEDIN_ACCESS_TOKEN", "fake-linkedin-token"))
        self.stack.enter_context(patch.object(config, "LINKEDIN_PERSON_URN", "urn:li:person:fake"))
        self.stack.enter_context(patch.object(linkedin, "_drafts", {}))

    def test_post_is_previewed_then_published_once_after_exact_confirmation(self):
        response = Mock(status_code=201, headers={"X-RestLi-Id": "urn:li:share:test"})
        with patch.object(linkedin.requests, "post", return_value=response) as post:
            self.assertIn("Visibility: Public", linkedin.post_to_linkedin("My exact post — ₹"))
            post.assert_not_called()
            self.assertIsNone(linkedin.handle_post_reply("send"))
            self.assertIsNone(linkedin.handle_post_reply("yes"))
            self.assertIn("successfully published", ai_agent.query_agent("publish linkedin"))
            self.assertIn("No LinkedIn post", ai_agent.query_agent("publish linkedin"))
            post.assert_called_once()
            self.assertEqual(post.call_args.kwargs["json"]["specificContent"]["com.linkedin.ugc.ShareContent"]["shareCommentary"]["text"], "My exact post — ₹")

    def test_cancel_expiry_and_account_change_never_publish(self):
        with patch.object(linkedin.requests, "post") as post:
            linkedin.post_to_linkedin("Cancelled")
            self.assertIn("cancelled", linkedin.handle_post_reply("cancel linkedin"))
            linkedin.post_to_linkedin("Old")
            linkedin._drafts[config.ADMIN_USER_ID]["expires"] = time.monotonic() - 1
            self.assertIn("expired", linkedin.handle_post_reply("publish linkedin"))
            linkedin.post_to_linkedin("Different account")
            config.LINKEDIN_ACCESS_TOKEN = "different-fake-token"
            self.assertIn("account changed", linkedin.handle_post_reply("publish linkedin"))
            post.assert_not_called()

    def test_guest_cannot_consume_owner_preview(self):
        linkedin.post_to_linkedin("Owner post")
        config.set_current_user(OTHER)
        self.assertIn("restricted", linkedin.handle_post_reply("publish linkedin"))
        self.assertIn(config.ADMIN_USER_ID, linkedin._drafts)
        with self.assertRaises(PermissionError):
            linkedin.post_to_linkedin("Guest post")

    def test_rejected_or_uncertain_write_does_not_retry_or_leak_details(self):
        for response in (Mock(status_code=403, text="private server response"), Mock(status_code=500)):
            linkedin.post_to_linkedin("Test")
            with patch.object(linkedin.requests, "post", return_value=response) as post:
                result = linkedin.handle_post_reply("publish linkedin")
                self.assertNotIn("private server response", result)
                post.assert_called_once()
        linkedin.post_to_linkedin("Timeout")
        with patch.object(linkedin.requests, "post", side_effect=TimeoutError("sensitive diagnostic")) as post:
            self.assertIn("uncertain", linkedin.handle_post_reply("publish linkedin"))
            self.assertIn("No LinkedIn post", linkedin.handle_post_reply("publish linkedin"))
            post.assert_called_once()

    def test_blank_long_and_unconnected_posts_never_create_preview(self):
        for text in (" ", "a" * 3001):
            self.assertIn("Nothing was published", linkedin.post_to_linkedin(text))
        config.LINKEDIN_ACCESS_TOKEN = ""
        self.assertIn("not connected", linkedin.post_to_linkedin("Hello"))
        self.assertEqual(linkedin._drafts, {})

    def test_author_cache_is_invalidated_after_token_change(self):
        config.LINKEDIN_PERSON_URN = ""
        with patch.object(linkedin, "_CACHED_PERSON_URN", None), patch.object(linkedin, "_CACHED_TOKEN_HASH", None), patch.object(linkedin.requests, "get") as get:
            get.side_effect = [Mock(status_code=200, json=lambda: {"sub": "first"}), Mock(status_code=200, json=lambda: {"sub": "second"})]
            self.assertEqual(linkedin.get_author_urn("token-one"), "urn:li:person:first")
            self.assertEqual(linkedin.get_author_urn("token-two"), "urn:li:person:second")

    def test_model_response_cannot_skip_or_replace_actual_preview(self):
        session = Mock()
        def model(_):
            linkedin.post_to_linkedin("Actual requested post")
            return Mock(text="Already published a different post")
        session.send_message.side_effect = model
        with patch.object(ai_agent, "get_or_create_chat_session", return_value=session):
            result = ai_agent.query_gemini_agent("Prepare a LinkedIn post")
        self.assertIn("Actual requested post", result)
        self.assertNotIn("Already published", result)

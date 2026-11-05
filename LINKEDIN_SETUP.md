# Connect the owner's LinkedIn account

The posting code is prepared, but no LinkedIn access token is configured yet.
WhatsApp is excluded. This integration is owner-only; it does not connect guest
accounts or provide LinkedIn inbox access, connection requests, or feed scraping.

## LinkedIn account setup

1. Open https://www.linkedin.com/developers/apps and create an app named
   **YoBot Executive Assistant**. The current account has no developer apps.
2. Select the LinkedIn Page you are authorized to associate with this app and
   upload an app logo. Follow LinkedIn's individual-developer instructions if
   using a supported default Page. The Page association cannot be changed after
   creation; do not select an unrelated organization.
3. Review and accept LinkedIn's API terms yourself, then create the app.
4. In Products, request **Share on LinkedIn** and **Sign In with LinkedIn using
   OpenID Connect**. Product approval must finish before token generation.
5. Use LinkedIn's official token generator under Developer tools. Authorize your
   own account for `openid`, `profile`, and `w_member_social`. Email permission
   is optional and not needed for posting.
6. Enter the generated token directly into the existing Render service's
   `LINKEDIN_ACCESS_TOKEN` environment variable. Never send it through Telegram
   or commit it to GitHub. `LINKEDIN_PERSON_URN` can be omitted when profile
   access succeeds; remove any stale value for a different account.
7. Save and deploy, then send `/linkedin` in your private Telegram chat to check
   the connected identity. Real profile/post permission verification remains
   pending until the token exists. Token renewal depends on LinkedIn access;
   the bot does not promise permanent authorization.

## Posting workflow

- `/linkedin YOUR EXACT TEXT` creates a preview with **Public** visibility.
- Reply `publish linkedin` or `/linkedin publish` to publish that exact preview.
- Reply `cancel linkedin` or `/linkedin cancel` to discard it.
- Natural-language requests use the same service and confirmation boundary.
- Previews expire after 30 minutes or restart, and changing the token requires
  another preview. A publish confirmation is consumed once before network I/O.
- Publication uses one UGC API request. Rejections and timeouts never fall back
  to a second posting API or silently retry. Check your LinkedIn profile if
  delivery is uncertain before creating another post.

No real post is published as part of tests or connection setup.

References: [Share on LinkedIn](https://learn.microsoft.com/en-us/linkedin/consumer/integrations/self-serve/share-on-linkedin),
[LinkedIn authorization](https://learn.microsoft.com/en-us/linkedin/shared/authentication/authorization-code-flow).

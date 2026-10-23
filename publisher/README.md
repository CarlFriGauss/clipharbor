# Local Google desktop registration

The optional ignored `google-oauth-client.json` identifies a publisher's native
desktop app. It contains only the client ID and native-client secret. Google treats installed
applications as public clients: this registration is not a user's password or
an account authorization. OAuth uses PKCE, a random state, and a loopback callback.

A source build needs publisher configuration before Google sign-in is available.
The official installer includes its registration. Each user authorizes their own account in
Google's browser screen. Access and refresh tokens are stored separately in the
operating-system credential store. Neither local registration files nor user
authorization tokens should be added to Git.

Fork publishers can supply their own registration through the overrides described
in the main README and complete Google's consent and verification requirements.

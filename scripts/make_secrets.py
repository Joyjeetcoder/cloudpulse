"""Run on your own computer. These values are secrets; do not commit the output."""
import secrets

print("GITHUB_WEBHOOK_SECRET=" + secrets.token_urlsafe(40))
print("DASHBOARD_TOKEN=" + secrets.token_urlsafe(40))

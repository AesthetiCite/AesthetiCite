import os
import httpx
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail


def _get_sendgrid_credentials() -> tuple[str, str]:
    """
    Fetch SendGrid credentials from environment variable or Replit connector system.
    Returns (api_key, from_email) tuple.
    """
    api_key = os.getenv("SENDGRID_API_KEY", "")
    from_email = "support@aestheticite.com"
    
    if api_key:
        return api_key, from_email
    
    hostname = os.getenv("REPLIT_CONNECTORS_HOSTNAME", "")
    repl_identity = os.getenv("REPL_IDENTITY", "")
    web_repl_renewal = os.getenv("WEB_REPL_RENEWAL", "")
    
    if repl_identity:
        x_replit_token = f"repl {repl_identity}"
    elif web_repl_renewal:
        x_replit_token = f"depl {web_repl_renewal}"
    else:
        raise RuntimeError("No Replit token available for connector auth")
    
    if not hostname:
        raise RuntimeError("REPLIT_CONNECTORS_HOSTNAME not set")
    
    url = f"https://{hostname}/api/v2/connection?include_secrets=true&connector_names=sendgrid"
    
    with httpx.Client() as client:
        resp = client.get(
            url,
            headers={
                "Accept": "application/json",
                "X_REPLIT_TOKEN": x_replit_token
            }
        )
        resp.raise_for_status()
        data = resp.json()
    
    items = data.get("items", [])
    if not items:
        raise RuntimeError("SendGrid connector not configured")
    
    settings = items[0].get("settings", {})
    api_key = settings.get("api_key", "")
    from_email = settings.get("from_email", "") or "support@aestheticite.com"
    
    if not api_key:
        raise RuntimeError("SendGrid API key not found")
    
    return api_key, from_email


def send_email(to_email: str, subject: str, body: str):
    """
    Send email via SendGrid API using Replit connector credentials.
    """
    api_key, from_email = _get_sendgrid_credentials()
    
    message = Mail(
        from_email=from_email,
        to_emails=to_email,
        subject=subject,
        plain_text_content=body
    )
    
    try:
        sg = SendGridAPIClient(api_key)
        response = sg.send(message)
        if response.status_code not in (200, 201, 202):
            raise RuntimeError(f"SendGrid returned status {response.status_code}")
    except Exception as e:
        raise RuntimeError(f"SendGrid email failed: {e}")

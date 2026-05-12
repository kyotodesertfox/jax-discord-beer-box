import requests

def notify(message, category="INFO"):
#    """
#    Centralized notification system for JaxBot.
#    Categories: INFO, ALERT, CRITICAL, SUCCESS
#    """
    url = "https://ntfy.sh/jax-discord-bot-904"

    settings = {
        "INFO":     {"priority": 3, "tags": "speech_balloon", "title": "JaxBot: Info"},
        "ALERT":    {"priority": 4, "tags": "warning",        "title": "JaxBot: Alert"},
        "CRITICAL": {"priority": 5, "tags": "fire",           "title": "JaxBot: CRITICAL"},
        "SUCCESS":  {"priority": 3, "tags": "white_check_mark","title": "JaxBot: Success"}
    }

    s = settings.get(category, settings["INFO"])

    try:
        requests.post(
            url,
            data=message.encode('utf-8'),
            headers={
                "Title": s["title"],
                "Priority": str(s["priority"]),
                "Tags": s["tags"]
            },
            timeout=5
        )
    except Exception as e:
        print(f"Internal Notification Error: {e}")

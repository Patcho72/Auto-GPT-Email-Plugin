import os
import json
import smtplib
import email
import imaplib
import mimetypes
import time
from email.header import decode_header
from email.message import EmailMessage


def bothEmailAndPwdSet() -> bool:
    return True if os.getenv("EMAIL_ADDRESS") and os.getenv("EMAIL_PASSWORD") else False


def getSender():
    email_sender = os.getenv("EMAIL_ADDRESS")
    if not email_sender:
        return "Error: email not sent. EMAIL_ADDRESS not set in environment."
    return email_sender


def getPwd():
    email_password = os.getenv("EMAIL_PASSWORD")
    if not email_password:
        return "Error: email not sent. EMAIL_PASSWORD not set in environment."
    return email_password


def send_email(to: str, subject: str, body: str) -> str:
    return send_email_with_attachment_internal(to, subject, body, None, None)


def send_email_with_attachment(
    to: str, subject: str, body: str, attachment: str
) -> str:
    from autogpt.workspace import path_in_workspace

    attachment_path = path_in_workspace(attachment)
    return send_email_with_attachment_internal(
        to, subject, body, attachment_path, attachment
    )


def send_email_with_attachment_internal(
    to: str, title: str, message: str, attachment_path: str, attachment: str
) -> str:
    """Send an email

    Args:
        to (str): The email of the tos
        title (str): The title of the email
        message (str): The message content of the email

    Returns:
        str: Any error messages
    """
    email_sender = getSender()
    email_password = getPwd()

    msg = EmailMessage()
    msg["Subject"] = title
    msg["From"] = email_sender
    msg["To"] = to

    signature = os.getenv("EMAIL_SIGNATURE")
    if signature:
        message += f"\n{signature}"

    # Ajoutez la partie texte simple de votre message
    msg.set_content(message)

    # Ajoutez la partie HTML de votre message
    html_message = '<html><body>{}</body></html>'.format(message.replace("\n", "<br>"))

    msg.add_alternative(html_message, subtype="html")

    if attachment_path:
        ctype, encoding = mimetypes.guess_type(attachment_path)
        if ctype is None or encoding is not None:
            # No guess could be made, or the file is encoded (compressed)
            ctype = "application/octet-stream"
        maintype, subtype = ctype.split("/", 1)
        with open(attachment_path, "rb") as fp:
            msg.add_attachment(
                fp.read(), maintype=maintype, subtype=subtype, filename=attachment
            )

    draft_folder = os.getenv("EMAIL_DRAFT_MODE_WITH_FOLDER")

    if not draft_folder:
        smtp_host = os.getenv("EMAIL_SMTP_HOST")
        smtp_port = os.getenv("EMAIL_SMTP_PORT")
        # send email
        with smtplib.SMTP(smtp_host, smtp_port) as smtp:
            smtp.ehlo()
            smtp.starttls()
            smtp.login(email_sender, email_password)
            smtp.send_message(msg)
            smtp.quit()
        return f"Email was sent to {to}!"
    else:
        conn = imap_open(draft_folder, email_sender, email_password)
        conn.append(
            draft_folder,
            "",
            imaplib.Time2Internaldate(time.time()),
            str(msg).encode("UTF-8"),
        )
        return f"Email went to {draft_folder}!"


def read_emails(imap_folder: str = "inbox", imap_search_command: str = "UNSEEN") -> str:
    """Read emails from an IMAP mailbox.

    This function reads emails from a specified IMAP folder, using a given IMAP search command.
    It returns a list of emails with their details, including the sender, recipient, date, CC, subject, and message body.

    Args:
        imap_folder (str, optional): The name of the IMAP folder to read emails from. Defaults to "inbox".
        imap_search_command (str, optional): The IMAP search command to filter emails. Defaults to "UNSEEN".

    Returns:
        str: A list of dictionaries containing email details if there are any matching emails. Otherwise, returns
             a string indicating that no matching emails were found.
    """
    email_sender = getSender()
    email_password = getPwd()

    mark_as_seen = os.getenv("EMAIL_MARK_AS_SEEN")
    if isinstance(mark_as_seen, str):
        mark_as_seen = json.loads(mark_as_seen.lower())

    conn = imap_open(imap_folder, email_sender, email_password)
    _, search_data = conn.search(None, imap_search_command)

    messages = []
    for num in search_data[0].split():
        if mark_as_seen:
            message_parts = "(RFC822)"
        else:
            message_parts = "(BODY.PEEK[])"
        _, msg_data = conn.fetch(num, message_parts)
        for response_part in msg_data:
            if isinstance(response_part, tuple):
                msg = email.message_from_bytes(response_part[1])

                subject, encoding = decode_header(msg["Subject"])[0]
                if isinstance(subject, bytes):
                    subject = subject.decode(encoding)

                body = get_email_body(msg)
                from_address = msg["From"]
                to_address = msg["To"]
                date = msg["Date"]
                cc = msg["CC"] if msg["CC"] else ""

                messages.append(
                    {
                        "From": from_address,
                        "To": to_address,
                        "Date": date,
                        "CC": cc,
                        "Subject": subject,
                        "Message Body": body,
                    }
                )

    conn.logout()
    if not messages:
        return (
            f"There are no Emails in your folder `{imap_folder}` "
            f"when searching with imap command `{imap_search_command}`"
        )
    return messages


def imap_open(
    imap_folder: str, email_sender: str, email_password: str
) -> imaplib.IMAP4_SSL:
    imap_server = os.getenv("EMAIL_IMAP_SERVER")
    conn = imaplib.IMAP4_SSL(imap_server)
    conn.login(email_sender, email_password)
    conn.select(imap_folder)
    return conn


def get_email_body(msg: email.message.Message) -> str:
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            content_disposition = str(part.get("Content-Disposition"))
            if content_type == "text/plain" and "attachment" not in content_disposition:
                return part.get_payload(decode=True).decode(errors="replace")
            if content_type == "text/html" and "attachment" not in content_disposition:
                return part.get_payload(decode=True).decode(errors="replace")
    else:
        return msg.get_payload(decode=True).decode(errors="replace")

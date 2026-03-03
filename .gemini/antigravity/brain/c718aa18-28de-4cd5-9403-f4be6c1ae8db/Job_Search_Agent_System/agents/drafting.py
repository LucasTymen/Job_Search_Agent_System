"""
Agent Gmail : brouillons (IMAP) et envoi d'emails (SMTP).
Même compte : GMAIL_USER + GMAIL_APP_PASSWORD.
"""
import imaplib
import smtplib
import time
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from dotenv import load_dotenv

load_dotenv()

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587

class GmailDraftingAgent:
    def __init__(self):
        self.user = os.getenv("GMAIL_USER")
        self.password = os.getenv("GMAIL_APP_PASSWORD")
        self.host = "imap.gmail.com"

    def create_draft(self, to_email: str, subject: str, body: str, attachment_paths: list = None, cc_emails: list = None) -> bool:
        """
        Crée un brouillon avec des pièces jointes optionnelles.
        to_email = destinataire principal ; cc_emails = liste d'adresses en Cc (toutes les autres contacts).
        """
        if not to_email or not str(to_email).strip():
            print("Erreur: Destinataire (to_email) vide. Brouillon non créé.")
            return False
        if not self.user or not self.password:
            print("Erreur: GMAIL_USER ou GMAIL_APP_PASSWORD non configuré dans .env")
            return False

        cc_list = [e.strip() for e in (cc_emails or []) if e and str(e).strip() and "@" in str(e)]

        try:
            msg = MIMEMultipart()
            msg['Subject'] = subject
            msg['From'] = self.user
            msg['To'] = to_email
            if cc_list:
                msg['Cc'] = ", ".join(cc_list)

            msg.attach(MIMEText(body, 'plain'))

            # Pièces jointes
            if attachment_paths:
                for path in attachment_paths:
                    if os.path.exists(path):
                        with open(path, "rb") as f:
                            part = MIMEApplication(f.read(), Name=os.path.basename(path))
                            part['Content-Disposition'] = f'attachment; filename="{os.path.basename(path)}"'
                            msg.attach(part)
                    else:
                        print(f"Attention: Le fichier {path} n'existe pas.")

            # Connexion IMAP
            mail = imaplib.IMAP4_SSL(self.host)
            mail.login(self.user, self.password)

            # Recherche du dossier Brouillons
            draft_folder = None
            typ, folders = mail.list()
            if typ == 'OK':
                for f in folders:
                    fd = f.decode()
                    if r'\Drafts' in fd:
                        parts = fd.split(' "/" ')
                        if len(parts) > 1:
                            draft_folder = parts[1].strip('"')
                            break

            if not draft_folder:
                draft_folder = "[Gmail]/Drafts"

            mail.append(draft_folder, '', imaplib.Time2Internaldate(time.time()), msg.as_bytes())
            mail.logout()
            return True

        except Exception as e:
            print(f"Erreur lors de la création du brouillon avec attachment: {e}")
            return False

    def send_email(self, to_email: str, subject: str, body: str, attachment_paths: list = None, cc_emails: list = None) -> bool:
        """
        Envoie un email via SMTP. to_email = destinataire principal ; cc_emails = adresses en Cc.
        """
        if not to_email or not str(to_email).strip():
            print("Erreur: Destinataire (to_email) vide. Email non envoyé.")
            return False
        if not self.user or not self.password:
            print("Erreur: GMAIL_USER ou GMAIL_APP_PASSWORD non configuré dans .env")
            return False

        cc_list = [e.strip() for e in (cc_emails or []) if e and str(e).strip() and "@" in str(e)]
        recipients = [to_email] + cc_list

        try:
            msg = MIMEMultipart()
            msg["Subject"] = subject
            msg["From"] = self.user
            msg["To"] = to_email
            if cc_list:
                msg["Cc"] = ", ".join(cc_list)
            msg.attach(MIMEText(body, "plain"))

            if attachment_paths:
                for path in attachment_paths:
                    if os.path.exists(path):
                        with open(path, "rb") as f:
                            part = MIMEApplication(f.read(), Name=os.path.basename(path))
                            part["Content-Disposition"] = f'attachment; filename="{os.path.basename(path)}"'
                            msg.attach(part)

            with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
                server.starttls()
                server.login(self.user, self.password)
                server.sendmail(self.user, recipients, msg.as_string())
            return True
        except Exception as e:
            print(f"Erreur envoi email: {e}")
            return False

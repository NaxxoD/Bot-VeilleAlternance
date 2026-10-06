"""Test de connexion à Proton Mail Bridge (IMAP local), en lecture seule.

Se connecte avec les identifiants BRIDGE_* du .env, liste les dossiers,
puis se déconnecte. N'envoie rien, n'affiche pas le mot de passe.

Avec --brouillon : dépose en plus un brouillon factice adressé à
soi-même dans le dossier Brouillons (à supprimer ensuite à la main).

Lancement (Bridge doit tourner) :
    python scripts/test_bridge.py
    python scripts/test_bridge.py --brouillon
"""

import imaplib
import os
import re
import ssl
import sys
import time
from email.message import EmailMessage
from pathlib import Path

from dotenv import load_dotenv

RACINE = Path(__file__).resolve().parent.parent


def trouver_brouillons(dossiers: list[bytes]) -> str | None:
    """Nom du dossier portant l'attribut \\Drafts, quelle que soit sa langue."""
    for ligne in dossiers:
        texte = ligne.decode("utf-8", errors="replace")
        if "\\Drafts" in texte:
            nom = re.search(r'"([^"]*)"$', texte)
            if nom:
                return nom.group(1)
    return None


def deposer_brouillon(imap: imaplib.IMAP4, dossier: str, adresse: str) -> None:
    message = EmailMessage()
    message["From"] = adresse
    message["To"] = adresse
    message["Subject"] = "[TEST] Brouillon Bot Veille Alternance"
    message.set_content(
        "Brouillon de test déposé par scripts/test_bridge.py.\n"
        "Il peut être supprimé."
    )
    statut, _ = imap.append(
        f'"{dossier}"',
        "(\\Draft)",
        imaplib.Time2Internaldate(time.time()),
        message.as_bytes(),
    )
    if statut != "OK":
        raise imaplib.IMAP4.error(f"dépôt refusé : {statut}")


def main() -> int:
    avec_brouillon = "--brouillon" in sys.argv[1:]
    load_dotenv(RACINE / ".env")
    hote = os.environ.get("BRIDGE_IMAP_HOST", "127.0.0.1").strip()
    port = int(os.environ.get("BRIDGE_IMAP_PORT", "1143").strip())
    utilisateur = os.environ.get("BRIDGE_USER", "").strip()
    mot_de_passe = os.environ.get("BRIDGE_PASSWORD", "").strip()

    if not utilisateur or not mot_de_passe:
        print("BRIDGE_USER ou BRIDGE_PASSWORD manquant dans .env")
        return 1

    # Bridge présente un certificat auto-signé : la vérification est
    # désactivée, acceptable uniquement parce que la connexion reste locale.
    if hote not in ("127.0.0.1", "localhost"):
        print(f"Refus : hôte non local ({hote}), vérification TLS désactivée")
        return 1
    contexte = ssl.create_default_context()
    contexte.check_hostname = False
    contexte.verify_mode = ssl.CERT_NONE

    try:
        imap = imaplib.IMAP4(hote, port)
    except ConnectionRefusedError:
        print(f"Connexion refusée sur {hote}:{port} — Bridge est-il lancé ?")
        return 1

    try:
        imap.starttls(ssl_context=contexte)
        imap.login(utilisateur, mot_de_passe)
        print(f"Connecté à Bridge ({hote}:{port}) en tant que {utilisateur}")
        statut, dossiers = imap.list()
        if statut != "OK":
            print(f"Impossible de lister les dossiers : {statut}")
            return 1
        print(f"{len(dossiers)} dossiers :")
        for ligne in dossiers:
            print("  " + ligne.decode("utf-8", errors="replace"))
        if avec_brouillon:
            dossier = trouver_brouillons(dossiers)
            if dossier is None:
                print("Dossier Brouillons introuvable (aucun attribut \\Drafts)")
                return 1
            deposer_brouillon(imap, dossier, utilisateur)
            print(f"Brouillon de test déposé dans « {dossier} »")
    except imaplib.IMAP4.error as erreur:
        print(f"Échec IMAP : {erreur}")
        return 1
    finally:
        try:
            imap.logout()
        except (imaplib.IMAP4.error, OSError):
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())

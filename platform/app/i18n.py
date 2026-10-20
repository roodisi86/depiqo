"""Message catalog for the tenant app: Dutch (source), French and English.

Covers what the server writes itself for the app: error messages (by stable error code), notification
titles and bodies (by notification type, with parameters), the fixed push line and a few e-mails.
Labels in API responses stay Dutch, always next to a stable key the app translates itself.

A missing translation falls back to Dutch; tests list missing keys. Parameters are formatted per
language by name: *_cents as money, *_bps as a percentage, *_date as a date, *_at as a date and time,
and a value starting with '@' is itself a catalog key (translated in the same language).
"""
import re

from .util import LOCAL_TZ, parse_date, parse_dt

LANGS = ("nl", "fr", "en")
DEFAULT = "nl"

MONTHS = {
    "nl": ["januari", "februari", "maart", "april", "mei", "juni", "juli", "augustus", "september", "oktober", "november", "december"],
    "fr": ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre"],
    "en": ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"],
}

M = {
    # ------------------------------------------------------------ errors (key: error.<code>)
    "error.bad_request": ("Dit verzoek klopt niet.", "Cette requête n'est pas valide.", "This request is not valid."),
    "error.unauthorized": ("Log in om verder te gaan.", "Connectez-vous pour continuer.", "Log in to continue."),
    "error.forbidden": ("Je hebt hier geen toegang toe.", "Vous n'avez pas accès à ceci.", "You do not have access to this."),
    "error.not_found": ("Niet gevonden.", "Introuvable.", "Not found."),
    "error.method_not_allowed": ("Deze methode kan hier niet.", "Cette méthode n'est pas autorisée ici.", "This method is not allowed here."),
    "error.file_too_large": ("Het bestand is groter dan 10 MB.", "Le fichier dépasse 10 Mo.", "The file is larger than 10 MB."),
    "error.unsupported_media_type": ("Stuur JSON met Content-Type application/json.", "Envoyez du JSON avec Content-Type application/json.",
                                     "Send JSON with Content-Type application/json."),
    "error.rate_limited": ("Te veel pogingen. Probeer het later opnieuw.", "Trop de tentatives. Réessayez plus tard.",
                           "Too many attempts. Please try again later."),
    "error.server_error": ("Er ging iets mis bij Depiqo. Probeer het later opnieuw.", "Une erreur s'est produite chez Depiqo. Réessayez plus tard.",
                           "Something went wrong at Depiqo. Please try again later."),
    "error.cookie_auth_not_allowed": ("De app werkt niet met de inlog van de website. Stuur je toegangstoken mee.",
                                      "L'application n'utilise pas la connexion du site web. Envoyez votre jeton d'accès.",
                                      "The app does not use the website login. Send your access token."),
    "error.app_update_required": ("Deze versie van de app wordt niet meer ondersteund. Werk de app bij.",
                                  "Cette version de l'application n'est plus prise en charge. Mettez l'application à jour.",
                                  "This version of the app is no longer supported. Please update the app."),
    "error.staff_not_allowed": ("Medewerkers van Depiqo gebruiken de beheeromgeving op de website, niet de app.",
                                "Les collaborateurs de Depiqo utilisent l'espace de gestion sur le site web, pas l'application.",
                                "Depiqo staff use the back office on the website, not the app."),
    "error.not_a_tenant": ("Deze app is voor huurders. Gebruik Depiqo Business op de website.",
                           "Cette application est destinée aux locataires. Utilisez Depiqo Business sur le site web.",
                           "This app is for tenants. Use Depiqo Business on the website."),
    "error.token_missing": ("Log in om verder te gaan.", "Connectez-vous pour continuer.", "Log in to continue."),
    "error.token_invalid": ("Je sessie is niet geldig. Log opnieuw in.", "Votre session n'est pas valide. Reconnectez-vous.",
                            "Your session is not valid. Please log in again."),
    "error.token_expired": ("Je sessie is verlopen.", "Votre session a expiré.", "Your session has expired."),
    "error.device_revoked": ("Dit apparaat is afgemeld. Log opnieuw in.", "Cet appareil a été déconnecté. Reconnectez-vous.",
                             "This device has been signed out. Please log in again."),
    "error.refresh_token_reused": ("Deze sessie is om veiligheidsredenen beëindigd. Log opnieuw in.",
                                   "Cette session a été fermée pour des raisons de sécurité. Reconnectez-vous.",
                                   "This session was ended for security reasons. Please log in again."),
    "error.mfa_token_invalid": ("Deze inlogpoging is verlopen. Log opnieuw in met je wachtwoord.",
                                "Cette tentative de connexion a expiré. Reconnectez-vous avec votre mot de passe.",
                                "This login attempt has expired. Log in again with your password."),
    "error.invalid_json": ("De body is geen geldig JSON-object.", "Le corps n'est pas un objet JSON valide.", "The body is not a valid JSON object."),
    "error.validation_failed": ("Controleer de ingevulde gegevens.", "Vérifiez les données saisies.", "Please check the data you entered."),
    "error.unknown_field": ("Dit veld kun je hier niet wijzigen.", "Vous ne pouvez pas modifier ce champ ici.", "You cannot change this field here."),
    "error.invalid_limit": ("limit moet een getal zijn.", "limit doit être un nombre.", "limit must be a number."),
    "error.invalid_cursor": ("Deze cursor is niet geldig.", "Ce curseur n'est pas valide.", "This cursor is not valid."),
    "error.idempotency_key_required": ("Stuur een Idempotency-Key mee, zodat een herhaald verzoek niet dubbel wordt uitgevoerd.",
                                       "Envoyez une Idempotency-Key pour qu'une requête répétée ne soit pas exécutée deux fois.",
                                       "Send an Idempotency-Key so a repeated request is not carried out twice."),
    "error.invalid_idempotency_key": ("De Idempotency-Key moet 8 tot 100 tekens zijn.", "L'Idempotency-Key doit compter de 8 à 100 caractères.",
                                      "The Idempotency-Key must be 8 to 100 characters."),
    "error.idempotency_key_reused": ("Deze Idempotency-Key is al gebruikt voor een ander verzoek.",
                                     "Cette Idempotency-Key a déjà été utilisée pour une autre requête.",
                                     "This Idempotency-Key was already used for a different request."),
    "error.idempotency_in_progress": ("Dit verzoek wordt al verwerkt. Probeer het zo opnieuw.", "Cette requête est déjà en cours. Réessayez dans un instant.",
                                      "This request is already being processed. Try again in a moment."),
    "error.too_many_attempts": ("Te veel mislukte pogingen. Wacht 15 minuten en probeer het opnieuw.",
                                "Trop de tentatives échouées. Attendez 15 minutes et réessayez.",
                                "Too many failed attempts. Wait 15 minutes and try again."),
    "error.invalid_credentials": ("Dat e-mailadres en wachtwoord passen niet bij elkaar.", "Cette adresse e-mail et ce mot de passe ne correspondent pas.",
                                  "That email address and password do not match."),
    "error.invalid_code": ("Deze code klopt niet of is al gebruikt.", "Ce code est incorrect ou a déjà été utilisé.",
                           "This code is incorrect or has already been used."),
    "error.invalid_password": ("Dit wachtwoord klopt niet.", "Ce mot de passe est incorrect.", "This password is incorrect."),
    "error.weak_password": ("Kies een sterker wachtwoord van minstens 12 tekens.", "Choisissez un mot de passe plus fort d'au moins 12 caractères.",
                            "Choose a stronger password of at least 12 characters."),
    "error.invite_expired": ("Deze link is verlopen of al gebruikt. Vraag je verhuurder om een nieuwe uitnodiging.",
                             "Ce lien a expiré ou a déjà été utilisé. Demandez une nouvelle invitation à votre bailleur.",
                             "This link has expired or was already used. Ask your landlord for a new invitation."),
    "error.use_web": ("Je hebt al een Depiqo-account. Open de uitnodiging op de website en log daar in.",
                      "Vous avez déjà un compte Depiqo. Ouvrez l'invitation sur le site web et connectez-vous.",
                      "You already have a Depiqo account. Open the invitation on the website and log in there."),
    "error.login_required": ("Er bestaat al een account met dit e-mailadres. Log eerst in.", "Un compte existe déjà avec cette adresse e-mail. Connectez-vous d'abord.",
                             "An account with this email address already exists. Log in first."),
    "error.invite_for_other_account": ("Deze uitnodiging is voor een ander e-mailadres.", "Cette invitation est destinée à une autre adresse e-mail.",
                                       "This invitation is for a different email address."),
    "error.invite_not_accepted": ("De uitnodiging kon niet worden geaccepteerd.", "L'invitation n'a pas pu être acceptée.", "The invitation could not be accepted."),
    "error.confirm_details_required": ("Bevestig dat de naam van je verhuurder, het adres, het bedrag en het kenmerk kloppen.",
                                       "Confirmez que le nom du bailleur, l'adresse, le montant et la référence sont corrects.",
                                       "Confirm that your landlord's name, the address, the amount and the reference are correct."),
    "error.confirm_required": ("Bevestig deze stap.", "Confirmez cette étape.", "Please confirm this step."),
    "error.risk_acknowledged_required": ("Bevestig dat je de kosten en het risico hebt gelezen.", "Confirmez que vous avez lu les coûts et les risques.",
                                         "Confirm that you have read the costs and the risk."),
    "error.accept_partner_required": ("Ga akkoord met de voorwaarden van de partner.", "Acceptez les conditions du partenaire.",
                                      "Accept the partner's terms."),
    "error.accept_depiqo_required": ("Ga akkoord met de voorwaarden van Depiqo Invest.", "Acceptez les conditions de Depiqo Invest.",
                                     "Accept the Depiqo Invest terms."),
    "error.accept_required": ("Vink aan dat je akkoord gaat.", "Cochez pour donner votre accord.", "Tick the box to agree."),
    "error.deletion_blocked": ("Je account kan nog niet worden verwijderd.", "Votre compte ne peut pas encore être supprimé.",
                               "Your account cannot be deleted yet."),
    "error.identity_not_possible": ("Identificatie is nu niet mogelijk.", "L'identification n'est pas possible pour le moment.",
                                    "Identity verification is not possible right now."),
    "error.deposit_closed": ("Dit dossier is gesloten.", "Ce dossier est clôturé.", "This file is closed."),
    "error.upload_rejected": ("Dit bestand kan niet worden toegevoegd. Alleen PDF, JPG en PNG tot 10 MB.",
                              "Ce fichier ne peut pas être ajouté. Uniquement PDF, JPG et PNG jusqu'à 10 Mo.",
                              "This file cannot be added. Only PDF, JPG and PNG up to 10 MB."),
    "error.settlement_not_open": ("Er staat geen afrekening open om op te reageren.", "Aucun décompte n'attend votre réponse.",
                                  "There is no settlement waiting for your response."),
    "error.reason_required": ("Leg in een paar zinnen uit waarmee je het oneens bent.", "Expliquez en quelques phrases ce que vous contestez.",
                              "Explain in a few sentences what you disagree with."),
    "error.not_available": ("Dit is nu niet beschikbaar.", "Ceci n'est pas disponible pour le moment.", "This is not available right now."),
    "error.payout_choice_closed": ("Dit kan niet meer: de uitbetaling is al gestart.", "Ce n'est plus possible : le paiement a déjà commencé.",
                                   "This is no longer possible: the payout has already started."),
    "error.partner_unavailable": ("Dit kan nu niet: er is geen financiële partner gekoppeld. Er wordt geen geld verplaatst.",
                                  "Impossible pour le moment : aucun partenaire financier n'est connecté. Aucun argent n'est déplacé.",
                                  "Not possible right now: no financial partner is connected. No money is moved."),
    "error.invest_not_offered": ("Beleggen is niet beschikbaar voor jou.", "L'investissement n'est pas disponible pour vous.",
                                 "Investing is not available to you."),
    "error.invest_rejected": ("Deze actie kan nu niet bij je beleggingsrekening.", "Cette action n'est pas possible sur votre compte d'investissement.",
                              "This action is not possible on your investment account right now."),
    "error.account_not_active": ("Je beleggingsrekening is nog niet actief.", "Votre compte d'investissement n'est pas encore actif.",
                                 "Your investment account is not active yet."),
    "error.account_exists": ("Je hebt al een beleggingsrekening.", "Vous avez déjà un compte d'investissement.", "You already have an investment account."),
    "error.terms_outdated": ("De voorwaarden zijn gewijzigd. Lees de nieuwe versie en ga opnieuw akkoord.",
                             "Les conditions ont changé. Lisez la nouvelle version et acceptez-la à nouveau.",
                             "The terms have changed. Read the new version and accept again."),
    "error.terms_not_accepted": ("Ga eerst akkoord met de huidige voorwaarden.", "Acceptez d'abord les conditions actuelles.",
                                 "Accept the current terms first."),
    "error.quote_not_found": ("Deze offerte bestaat niet. Vraag eerst een offerte op.", "Ce devis n'existe pas. Demandez d'abord un devis.",
                              "This quote does not exist. Request a quote first."),
    "error.quote_used": ("Deze offerte is al gebruikt. Vraag een nieuwe offerte op.", "Ce devis a déjà été utilisé. Demandez un nouveau devis.",
                         "This quote has already been used. Request a new quote."),
    "error.quote_expired": ("Deze offerte is verlopen (na 10 minuten). Vraag een nieuwe offerte op.",
                            "Ce devis a expiré (après 10 minutes). Demandez un nouveau devis.",
                            "This quote has expired (after 10 minutes). Request a new quote."),
    "error.amount_below_minimum": ("Het minimum is € 25.", "Le minimum est de 25 €.", "The minimum is €25."),
    "error.push_token_in_use": ("Deze pushtoken hoort bij een ander account dat nog is ingelogd op dit toestel.",
                                "Ce jeton push appartient à un autre compte encore connecté sur cet appareil.",
                                "This push token belongs to another account that is still logged in on this device."),
    "error.support_rate_limited": ("Je hebt net al een paar vragen gestuurd. Probeer het later opnieuw.",
                                   "Vous venez d'envoyer plusieurs questions. Réessayez plus tard.",
                                   "You have just sent several questions. Please try again later."),

    # ------------------------------------------------------------ field messages
    "field.required": ("Vul dit veld in.", "Remplissez ce champ.", "Fill in this field."),
    "field.answer": ("Beantwoord deze vraag.", "Répondez à cette question.", "Answer this question."),
    "field.unknown": ("Onbekend veld.", "Champ inconnu.", "Unknown field."),

    # ------------------------------------------------------------ notifications
    "notif.invite.title": ("Nieuwe uitnodiging voor je borg", "Nouvelle invitation pour votre garantie locative", "New invitation for your deposit"),
    "notif.invite.body": ("{landlord} heeft je uitgenodigd voor de borg van {address}, {city}.",
                          "{landlord} vous a invité pour la garantie locative de {address}, {city}.",
                          "{landlord} invited you for the deposit of {address}, {city}."),
    "notif.payment_received.title": ("Je storting is ontvangen", "Votre versement a été reçu", "Your payment has been received"),
    "notif.payment_received.body": ("De bank heeft je storting van {amount_cents} ontvangen. Totaal ontvangen: {total_cents} van {required_cents}.",
                                    "La banque a reçu votre versement de {amount_cents}. Total reçu : {total_cents} sur {required_cents}.",
                                    "The bank received your payment of {amount_cents}. Total received: {total_cents} of {required_cents}."),
    "notif.deposit_secured.title": ("Je borg staat veilig", "Votre garantie est en sécurité", "Your deposit is secured"),
    "notif.deposit_secured.body": ("De bank bevestigt dat je borg geblokkeerd staat op de borgrekening op jouw naam.",
                                   "La banque confirme que votre garantie est bloquée sur le compte de garantie à votre nom.",
                                   "The bank confirms that your deposit is blocked on the deposit account in your name."),
    "notif.settlement_proposed.title": ("Je eindafrekening staat klaar", "Votre décompte final est prêt", "Your final settlement is ready"),
    "notif.settlement_proposed.body": ("Je verhuurder stelt {deductions_cents} aan inhoudingen voor. Bekijk de afrekening en ga akkoord of maak bezwaar.",
                                       "Votre bailleur propose {deductions_cents} de retenues. Consultez le décompte et acceptez-le ou contestez-le.",
                                       "Your landlord proposes {deductions_cents} in deductions. Review the settlement and agree or object."),
    "notif.dispute_resolved.title": ("Je geschil is afgerond", "Votre litige est clôturé", "Your dispute has been resolved"),
    "notif.dispute_resolved.body": ("Het geschil is afgesloten op basis van {basis}: {landlord_cents} voor de verhuurder.",
                                    "Le litige est clôturé sur la base {basis} : {landlord_cents} pour le bailleur.",
                                    "The dispute was closed on the basis of {basis}: {landlord_cents} for the landlord."),
    "basis.agreement": ("een akkoord tussen huurder en verhuurder", "d'un accord entre locataire et bailleur", "an agreement between tenant and landlord"),
    "basis.court_decision": ("een beslissing van de rechter", "d'une décision du juge", "a court decision"),
    "notif.payout_completed.title": ("Je borg is uitbetaald", "Votre garantie a été remboursée", "Your deposit has been paid out"),
    "notif.payout_completed.body": ("De bank heeft {tenant_cents} aan jou uitbetaald {destination}.", "La banque vous a versé {tenant_cents} {destination}.",
                                    "The bank paid {tenant_cents} to you {destination}."),
    "dest.own": ("op je eigen rekening", "sur votre propre compte", "to your own account"),
    "dest.invest": ("op je beleggingsrekening", "sur votre compte d'investissement", "to your investment account"),
    "notif.release_confirmed.title": ("Je borg is vrijgegeven", "Votre garantie a été libérée", "Your deposit has been released"),
    "notif.release_confirmed.body": ("Je verhuurder bevestigt dat je borg is vrijgegeven: {tenant_cents} voor jou.",
                                     "Votre bailleur confirme que votre garantie a été libérée : {tenant_cents} pour vous.",
                                     "Your landlord confirms that your deposit has been released: {tenant_cents} for you."),
    "notif.invest_order_executed.title": ("Je order is uitgevoerd", "Votre ordre a été exécuté", "Your order has been executed"),
    "notif.invest_order_executed.body": ("{side} voor {amount_cents} in je portefeuille {portfolio}, tegen de koers van {day_date}.",
                                         "{side} pour {amount_cents} dans votre portefeuille {portfolio}, au cours du {day_date}.",
                                         "{side} for {amount_cents} in your {portfolio} portfolio, at the price of {day_date}."),
    "side.buy": ("Gekocht", "Achat", "Bought"),
    "side.sell": ("Verkocht", "Vente", "Sold"),
    "portfolio.defensief": ("Defensief", "Défensif", "Defensive"),
    "portfolio.neutraal": ("Neutraal", "Neutre", "Balanced"),
    "portfolio.offensief": ("Offensief", "Offensif", "Growth"),
    "notif.invest_order_failed.title": ("Je order is niet uitgevoerd", "Votre ordre n'a pas été exécuté", "Your order was not executed"),
    "notif.invest_order_failed.body": ("Je order ({side}, {amount_cents}) is niet uitgevoerd. {reason}",
                                       "Votre ordre ({side}, {amount_cents}) n'a pas été exécuté. {reason}",
                                       "Your order ({side}, {amount_cents}) was not executed. {reason}"),
    "notif.invest_withdrawal_completed.title": ("Je opname is uitgevoerd", "Votre retrait a été effectué", "Your withdrawal is complete"),
    "notif.invest_withdrawal_completed.body": ("{amount_cents} is overgemaakt naar je rekening {iban_tail}.",
                                               "{amount_cents} a été viré sur votre compte {iban_tail}.",
                                               "{amount_cents} has been transferred to your account {iban_tail}."),
    "notif.invest_withdrawal_failed.title": ("Je opname is niet gelukt", "Votre retrait a échoué", "Your withdrawal failed"),
    "notif.invest_withdrawal_failed.body": ("Je opname van {amount_cents} is niet gelukt. {reason}", "Votre retrait de {amount_cents} a échoué. {reason}",
                                            "Your withdrawal of {amount_cents} failed. {reason}"),
    "notif.invest_fee_change.title": ("Voorstel: nieuwe servicevergoeding", "Proposition : nouveaux frais de service", "Proposal: new service fee"),
    "notif.invest_fee_change.body": ("Depiqo stelt een nieuwe servicevergoeding voor: {new_bps} per jaar in plaats van {old_bps}. Die geldt pas na je akkoord.",
                                     "Depiqo propose de nouveaux frais de service : {new_bps} par an au lieu de {old_bps}. Ils ne s'appliquent qu'après votre accord.",
                                     "Depiqo proposes a new service fee: {new_bps} per year instead of {old_bps}. It only applies once you agree."),
    "notif.new_device_login.title": ("Nieuwe inlog op je account", "Nouvelle connexion à votre compte", "New login to your account"),
    "notif.new_device_login.body": ("Er is ingelogd op {device} ({platform}) op {login_at}. Was jij dit niet? Meld het apparaat af onder Beveiliging en wijzig je wachtwoord.",
                                    "Une connexion a eu lieu sur {device} ({platform}) le {login_at}. Ce n'était pas vous ? Déconnectez l'appareil sous Sécurité et changez votre mot de passe.",
                                    "Someone logged in on {device} ({platform}) on {login_at}. Was this not you? Sign the device out under Security and change your password."),
    "platform.ios": ("iPhone of iPad", "iPhone ou iPad", "iPhone or iPad"),
    "platform.android": ("Android", "Android", "Android"),
    "notif.support_reply.title": ("Antwoord op je vraag", "Réponse à votre question", "Reply to your question"),
    "notif.support_reply.body": ("Depiqo heeft je vraag #{ticket} beantwoord. Open Hulp om het antwoord te lezen.",
                                 "Depiqo a répondu à votre question n° {ticket}. Ouvrez Aide pour lire la réponse.",
                                 "Depiqo has answered your question #{ticket}. Open Help to read the reply."),
    "push.body": ("Open Depiqo voor de details.", "Ouvrez Depiqo pour les détails.", "Open Depiqo for the details."),

    # ------------------------------------------------------------ e-mails to a user with a language preference
    "mail.iban_changed.subject": ("Je rekeningnummer voor opnames is gewijzigd", "Votre numéro de compte pour les retraits a été modifié",
                                  "Your account number for withdrawals has changed"),
    "mail.iban_changed.body": ("Hallo {name},\n\nVoor opnames van je beleggingsrekening staat nu dit rekeningnummer: {iban_short}.\n{when}\n\n"
                               "Was jij dit niet? Wijzig je wachtwoord en neem contact op met Depiqo.\n",
                               "Bonjour {name},\n\nPour les retraits de votre compte d'investissement, ce numéro de compte est désormais enregistré : {iban_short}.\n{when}\n\n"
                               "Ce n'était pas vous ? Changez votre mot de passe et contactez Depiqo.\n",
                               "Hello {name},\n\nThis account number is now registered for withdrawals from your investment account: {iban_short}.\n{when}\n\n"
                               "Was this not you? Change your password and contact Depiqo.\n"),
    "mail.iban_now": ("Je kunt het direct gebruiken.", "Vous pouvez l'utiliser immédiatement.", "You can use it right away."),
    "mail.iban_from": ("Je kunt het gebruiken vanaf {usable_at}.", "Vous pourrez l'utiliser à partir du {usable_at}.", "You can use it from {usable_at}."),
    "mail.fee_change.subject": ("Voorstel: nieuwe servicevergoeding voor je beleggingsrekening", "Proposition : nouveaux frais de service pour votre compte d'investissement",
                                "Proposal: new service fee for your investment account"),
    "mail.fee_change.body": ("Hallo {name},\n\nDepiqo stelt een nieuwe servicevergoeding voor: {new_bps} per jaar in plaats van {old_bps}.\n\n"
                             "De nieuwe vergoeding geldt alleen als je ermee akkoord gaat in Depiqo Wallet, en dan pas vanaf die dag. "
                             "Tot dan blijft je huidige vergoeding gelden.\n",
                             "Bonjour {name},\n\nDepiqo propose de nouveaux frais de service : {new_bps} par an au lieu de {old_bps}.\n\n"
                             "Les nouveaux frais ne s'appliquent que si vous les acceptez dans Depiqo Wallet, et seulement à partir de ce jour. "
                             "D'ici là, vos frais actuels restent d'application.\n",
                             "Hello {name},\n\nDepiqo proposes a new service fee: {new_bps} per year instead of {old_bps}.\n\n"
                             "The new fee only applies if you accept it in Depiqo Wallet, and only from that day. Until then your current fee applies.\n"),
}

# Field messages written in Dutch by the API and the services, mapped to a catalog key for translation.
FIELD_KEYS = {"Vul dit veld in.": "field.required", "Beantwoord deze vraag.": "field.answer", "Onbekend veld.": "field.unknown"}


def norm(lang):
    return lang if lang in LANGS else DEFAULT


def pick(header):
    """The best of nl/fr/en from an Accept-Language header, honouring q values. None when nothing matches."""
    best, best_q = None, -1.0
    for part in (header or "").split(","):
        bits = part.strip().split(";")
        tag = bits[0].strip().lower()[:2]
        q = 1.0
        for b in bits[1:]:
            if b.strip().startswith("q="):
                try:
                    q = float(b.strip()[2:])
                except ValueError:
                    q = 0.0
        if not 0 < q <= 1:  # also nan and inf
            continue
        if tag in LANGS and q > best_q:
            best, best_q = tag, q
    return best


def has(key):
    return key in M


def raw(key, lang):
    entry = M.get(key)
    if not entry:
        return None
    text = entry[LANGS.index(norm(lang))]
    return text or entry[0]


def money(cents, lang):
    neg = cents < 0
    c = abs(int(cents))
    whole, frac = c // 100, c % 100
    if lang == "en":
        text = f"€{whole:,}.{frac:02d}"
    elif lang == "fr":
        text = f"{whole:,}".replace(",", " ") + f",{frac:02d} €"
    else:
        text = f"€ {whole:,}".replace(",", ".") + f",{frac:02d}"
    return ("−" if neg else "") + text


def percent(bps, lang):
    v = f"{bps / 100:.2f}"
    return (v if lang == "en" else v.replace(".", ",")) + (" %" if lang == "fr" else "%")


def date_text(value, lang):
    d = parse_date(value)
    if not d:
        return "—"
    if lang == "en":
        return f"{d.day} {MONTHS['en'][d.month - 1]} {d.year}"
    return f"{d.day} {MONTHS[norm(lang)][d.month - 1]} {d.year}"


def datetime_text(value, lang):
    dt = parse_dt(value) if isinstance(value, str) else value
    if not dt:
        return "—"
    local = dt.astimezone(LOCAL_TZ)  # 0.6.1: Europe/Amsterdam (summer and winter time), not a fixed offset
    return f"{date_text(local.date(), lang)}, {local:%H:%M}"


def _fmt(name, value, lang):
    if isinstance(value, str) and value.startswith("@"):
        return raw(value[1:], lang) or value[1:]
    if value is None:
        return ""
    if name.endswith("_cents"):
        return money(value, lang)
    if name.endswith("_bps"):
        return percent(value, lang)
    if name.endswith("_date"):
        return date_text(value, lang)
    if name.endswith("_at"):
        return datetime_text(value, lang)
    return str(value)


def t(key, lang=DEFAULT, **params):
    text = raw(key, lang)
    if text is None:
        return key
    if params:
        values = {k: _fmt(k, v, norm(lang)) for k, v in params.items()}
        text = re.sub(r"\{(\w+)\}", lambda m: values.get(m.group(1), m.group(0)), text)
    return text.strip()


def missing():
    """(key, language) pairs without a translation."""
    return [(k, lang) for k, entry in M.items() for i, lang in enumerate(LANGS) if len(entry) <= i or not entry[i]]


def user_lang(user):
    try:
        return norm(user["language"])
    except (KeyError, IndexError, TypeError):
        return DEFAULT

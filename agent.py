"""
Catawiki Watch Agent
Monitora aste di orologi e notifica via Telegram quando le condizioni sono soddisfatte.
"""

import json
import re
import time
import logging
from datetime import datetime, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

CONFIG_PATH = Path(__file__).parent / "config.json"
SEEN_PATH = Path(__file__).parent / "seen_auctions.json"

CATAWIKI_SEARCH_URL = "https://www.catawiki.com/en/c/89-watches?order=closing_soon"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "it-IT,it;q=0.9,en;q=0.8",
}


# ---------------------------------------------------------------------------
# Config & stato
# ---------------------------------------------------------------------------

def load_config() -> dict:
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


def load_seen() -> set:
    if SEEN_PATH.exists():
        with open(SEEN_PATH, encoding="utf-8") as f:
            return set(json.load(f))
    return set()


def save_seen(seen: set):
    with open(SEEN_PATH, "w", encoding="utf-8") as f:
        json.dump(list(seen), f)


# ---------------------------------------------------------------------------
# Scraping Catawiki
# ---------------------------------------------------------------------------

def fetch_auctions() -> list[dict]:
    """Recupera le aste dalla pagina orologi di Catawiki."""
    auctions = []
    try:
        resp = requests.get(CATAWIKI_SEARCH_URL, headers=HEADERS, timeout=20)
        resp.raise_for_status()
    except requests.RequestException as e:
        log.error(f"Errore fetch Catawiki: {e}")
        return auctions

    soup = BeautifulSoup(resp.text, "html.parser")

    # Catawiki carica i dati anche in tag <script type="application/ld+json">
    # Proviamo prima il JSON strutturato, poi il fallback HTML
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
            items = data if isinstance(data, list) else [data]
            for item in items:
                if item.get("@type") not in ("Product", "Offer"):
                    continue
                auction = _parse_ld_json(item)
                if auction:
                    auctions.append(auction)
        except (json.JSONDecodeError, AttributeError):
            continue

    # Fallback: parsing HTML classico
    if not auctions:
        auctions = _parse_html(soup)

    log.info(f"Trovate {len(auctions)} aste")
    return auctions


def _parse_ld_json(item: dict) -> dict | None:
    try:
        return {
            "id": str(item.get("sku") or item.get("url", "").split("/")[-1]),
            "title": item.get("name", ""),
            "url": item.get("url", ""),
            "price": float(item.get("offers", {}).get("price", 0) or 0),
            "currency": item.get("offers", {}).get("priceCurrency", "EUR"),
            "ends_at": item.get("offers", {}).get("availabilityEnds") or
                       item.get("offers", {}).get("priceValidUntil"),
        }
    except Exception:
        return None


def _parse_html(soup: BeautifulSoup) -> list[dict]:
    """Parsing HTML di fallback — adatta i selettori se Catawiki cambia layout."""
    auctions = []
    for card in soup.select("article[data-lot-id], li[data-lot-id]"):
        try:
            lot_id = card.get("data-lot-id", "")
            title_el = card.select_one("[class*='lot-title'], h2, h3")
            price_el = card.select_one("[class*='current-bid'], [class*='price']")
            time_el = card.select_one("time[datetime], [data-ends-at]")

            title = title_el.get_text(strip=True) if title_el else ""
            price_text = price_el.get_text(strip=True) if price_el else "0"
            price = _parse_price(price_text)
            ends_at = (time_el.get("datetime") or time_el.get("data-ends-at")) if time_el else None
            url = card.select_one("a[href]")
            href = url["href"] if url else ""
            if href and not href.startswith("http"):
                href = "https://www.catawiki.com" + href

            if lot_id and title:
                auctions.append({
                    "id": lot_id,
                    "title": title,
                    "url": href,
                    "price": price,
                    "currency": "EUR",
                    "ends_at": ends_at,
                })
        except Exception:
            continue
    return auctions


def _parse_price(text: str) -> float:
    digits = re.sub(r"[^\d.,]", "", text).replace(",", ".")
    try:
        return float(digits)
    except ValueError:
        return 0.0


def hours_until_end(ends_at: str | None) -> float | None:
    """Restituisce le ore mancanti alla scadenza, o None se non disponibile."""
    if not ends_at:
        return None
    try:
        # Supporta ISO 8601 con e senza timezone
        dt = datetime.fromisoformat(ends_at.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        delta = (dt - now).total_seconds() / 3600
        return max(delta, 0)
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Motore di regole
# ---------------------------------------------------------------------------

def matches_rule(auction: dict, rule: dict) -> bool:
    """
    Valuta se un'asta soddisfa una regola.

    Logica parole chiave:
      mode=AND  → TUTTE le include devono essere nel titolo
      mode=OR   → ALMENO UNA include deve essere nel titolo
    Le exclude sono sempre in AND: basta una per escludere l'asta.
    """
    title_lower = auction["title"].lower()

    kw = rule.get("keywords", {})
    includes = [k.lower() for k in kw.get("include", [])]
    excludes = [k.lower() for k in kw.get("exclude", [])]
    mode = kw.get("mode", "OR").upper()

    # Controllo esclusioni
    for exc in excludes:
        if exc in title_lower:
            log.debug(f"Escluso '{auction['title']}' per termine '{exc}'")
            return False

    # Controllo inclusioni
    if includes:
        if mode == "AND":
            if not all(inc in title_lower for inc in includes):
                return False
        else:  # OR
            if not any(inc in title_lower for inc in includes):
                return False

    # Controllo prezzo
    max_price = rule.get("max_price_eur")
    if max_price and auction["price"] > 0 and auction["price"] > max_price:
        return False

    # Controllo scadenza
    max_hours = rule.get("expiry_within_hours")
    if max_hours:
        hours_left = hours_until_end(auction.get("ends_at"))
        if hours_left is None or hours_left > max_hours:
            return False

    return True


# ---------------------------------------------------------------------------
# Notifiche Telegram
# ---------------------------------------------------------------------------

def send_telegram(bot_token: str, chat_id: str, text: str):
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": False,
    }
    try:
        resp = requests.post(url, json=payload, timeout=10)
        resp.raise_for_status()
        log.info("Notifica Telegram inviata")
    except requests.RequestException as e:
        log.error(f"Errore invio Telegram: {e}")


def build_message(auction: dict, rule: dict) -> str:
    hours_left = hours_until_end(auction.get("ends_at"))
    time_str = f"{hours_left:.1f}h" if hours_left is not None else "N/D"
    price_str = f"€ {auction['price']:,.0f}" if auction["price"] > 0 else "N/D"

    return (
        f"🔔 <b>Asta trovata!</b> — {rule['name']}\n\n"
        f"<b>{auction['title']}</b>\n\n"
        f"💰 Offerta attuale: <b>{price_str}</b>\n"
        f"⏱ Scade tra: <b>{time_str}</b>\n\n"
        f"🔗 <a href=\"{auction['url']}\">Apri su Catawiki</a>"
    )


# ---------------------------------------------------------------------------
# Loop principale
# ---------------------------------------------------------------------------

def run_once():
    config = load_config()
    seen = load_seen()
    tg = config["telegram"]

    auctions = fetch_auctions()
    if not auctions:
        log.warning("Nessuna asta recuperata — possibile blocco o cambio struttura HTML")
        return

    active_rules = [r for r in config["rules"] if r.get("enabled", True)]
    notified = 0

    for auction in auctions:
        for rule in active_rules:
            alert_key = f"{auction['id']}:{rule['name']}"
            if alert_key in seen:
                continue
            if matches_rule(auction, rule):
                log.info(f"Match! '{auction['title']}' → regola '{rule['name']}'")
                msg = build_message(auction, rule)
                send_telegram(tg["bot_token"], tg["chat_id"], msg)
                seen.add(alert_key)
                notified += 1
                time.sleep(1)  # evita rate limit Telegram

    save_seen(seen)
    log.info(f"Scansione completata. Notifiche inviate: {notified}")


if __name__ == "__main__":
    log.info("Avvio Catawiki Watch Agent")
    run_once()

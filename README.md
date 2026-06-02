# Catawiki Watch Agent 🔔

Agente Python che monitora le aste di orologi su Catawiki e ti notifica su Telegram quando un'asta soddisfa le tue regole. Gira automaticamente ogni 15 minuti su GitHub Actions — nessun PC da tenere acceso.

---

## Setup (10 minuti)

### 1. Crea il tuo bot Telegram

1. Apri Telegram e cerca `@BotFather`
2. Scrivi `/newbot` e segui le istruzioni
3. Copia il **token** che ti fornisce (es. `123456:ABCdef...`)
4. Avvia una chat col tuo bot, poi vai su:
   `https://api.telegram.org/bot<TOKEN>/getUpdates`
5. Scrivi un messaggio al bot e ricarica la pagina — copia il valore `"id"` dentro `"chat"` — è il tuo **Chat ID**

### 2. Crea il repository GitHub

```bash
git init catawiki-agent
cd catawiki-agent
# Copia i file del progetto qui dentro
git add .
git commit -m "primo commit"
gh repo create catawiki-agent --public --push
# oppure crea il repo manualmente su github.com e fai push
```

### 3. Aggiungi i secret su GitHub

Vai su **Settings → Secrets and variables → Actions → New repository secret** e crea:

| Nome secret | Valore |
|---|---|
| `TG_BOT_TOKEN` | Il token del tuo bot Telegram |
| `TG_CHAT_ID` | Il tuo Chat ID |

### 4. Configura le regole in `config.json`

```json
{
  "rules": [
    {
      "name": "Nome descrittivo della regola",
      "enabled": true,
      "keywords": {
        "mode": "AND",
        "include": ["Rolex", "Submariner"],
        "exclude": ["replica", "rotto"]
      },
      "max_price_eur": 8000,
      "expiry_within_hours": 3
    }
  ]
}
```

**mode AND** → tutte le parole chiave devono essere nel titolo  
**mode OR** → basta una parola chiave

### 5. Aggiorna `agent.py` per leggere i secret

Nel file `agent.py`, sostituisci la funzione `load_config` con questa versione che legge i valori da variabili d'ambiente quando gira su GitHub Actions:

```python
import os

def load_config() -> dict:
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    # Sovrascrive con i secret di GitHub Actions se presenti
    token = os.getenv("TG_BOT_TOKEN")
    chat_id = os.getenv("TG_CHAT_ID")
    if token:
        config["telegram"]["bot_token"] = token
    if chat_id:
        config["telegram"]["chat_id"] = chat_id
    return config
```

### 6. Attiva il workflow

Vai su **Actions** nel tuo repository GitHub, seleziona **Catawiki Watch Agent** e clicca **Run workflow** per testarlo subito. Poi partirà automaticamente ogni 15 minuti.

---

## Struttura del progetto

```
catawiki-agent/
├── agent.py              # logica principale
├── config.json           # regole di monitoraggio
├── seen_auctions.json    # generato automaticamente (non toccare)
└── .github/
    └── workflows/
        └── watch.yml     # scheduler GitHub Actions
```

---

## Aggiungere una nuova regola

Apri `config.json` e aggiungi un oggetto nell'array `rules`:

```json
{
  "name": "Rolex Daytona vintage",
  "enabled": true,
  "keywords": {
    "mode": "AND",
    "include": ["Rolex", "Daytona"],
    "exclude": ["replica", "rotto", "cassa solo"]
  },
  "max_price_eur": 15000,
  "expiry_within_hours": 6
}
```

Salva e fai `git push` — la modifica è attiva al prossimo ciclo.

---

## Note

- GitHub Actions gratuito include 2.000 minuti/mese — più che sufficienti
- Il file `seen_auctions.json` viene cachato tra un run e l'altro per evitare notifiche duplicate
- Se Catawiki cambia struttura HTML, aggiorna i selettori in `_parse_html()` in `agent.py`

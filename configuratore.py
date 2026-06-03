"""
Configuratore Catawiki Agent
GUI locale per aggiornare i parametri e fare push su GitHub.
Esegui con: python configuratore.py
"""

import json
import subprocess
import sys
import os
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
from pathlib import Path

# ---------------------------------------------------------------------------
# Percorso del repo — modifica se necessario
# ---------------------------------------------------------------------------
REPO_PATH = Path(__file__).parent


# ---------------------------------------------------------------------------
# Logica
# ---------------------------------------------------------------------------

def load_config():
    path = REPO_PATH / "config.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"telegram": {"bot_token": "", "chat_id": ""}, "rules": []}


def save_config(config):
    path = REPO_PATH / "config.json"
    path.write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")


def patch_agent_py(bot_token, chat_id):
    """Inserisce la load_config aggiornata in agent.py."""
    agent_path = REPO_PATH / "agent.py"
    if not agent_path.exists():
        return False, "agent.py non trovato"

    content = agent_path.read_text(encoding="utf-8")

    new_func = '''import os

def load_config() -> dict:
    with open(CONFIG_PATH, encoding="utf-8") as f:
        config = json.load(f)
    token = os.getenv("TG_BOT_TOKEN")
    chat_id = os.getenv("TG_CHAT_ID")
    if token:
        config["telegram"]["bot_token"] = token
    if chat_id:
        config["telegram"]["chat_id"] = chat_id
    return config
'''

    # Sostituisce la funzione load_config esistente
    import re
    pattern = r'def load_config\(\).*?(?=\ndef |\Z)'
    if re.search(pattern, content, re.DOTALL):
        content = re.sub(pattern, new_func.strip() + "\n", content, flags=re.DOTALL)
    else:
        content = new_func + "\n" + content

    # Rimuove eventuale doppio "import os"
    content = re.sub(r'(import os\n)+', 'import os\n', content)

    agent_path.write_text(content, encoding="utf-8")
    return True, "agent.py aggiornato"


def git_push(log_callback):
    cmds = [
        ["git", "-C", str(REPO_PATH), "add", "."],
        ["git", "-C", str(REPO_PATH), "commit", "-m", "aggiornamento config da GUI"],
        ["git", "-C", str(REPO_PATH), "push"],
    ]
    for cmd in cmds:
        log_callback(f"$ {' '.join(cmd[2:])}")
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.stdout:
            log_callback(result.stdout.strip())
        if result.stderr:
            log_callback(result.stderr.strip())
        if result.returncode != 0 and "nothing to commit" not in result.stderr:
            return False
    return True


# ---------------------------------------------------------------------------
# GUI
# ---------------------------------------------------------------------------

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Configuratore Catawiki Agent")
        self.resizable(False, False)
        self.configure(bg="#1e1e2e")

        self.config_data = load_config()
        self.rule_frames = []

        self._build_ui()

    # ---- costruzione UI ----

    def _build_ui(self):
        pad = {"padx": 16, "pady": 8}

        # Header
        tk.Label(self, text="🔔 Catawiki Watch Agent", font=("Segoe UI", 16, "bold"),
                 bg="#1e1e2e", fg="#cdd6f4").pack(pady=(20, 4))
        tk.Label(self, text="Configura i parametri e pubblica su GitHub con un click",
                 font=("Segoe UI", 10), bg="#1e1e2e", fg="#a6adc8").pack(pady=(0, 16))

        # Notebook
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TNotebook", background="#1e1e2e", borderwidth=0)
        style.configure("TNotebook.Tab", background="#313244", foreground="#cdd6f4",
                        padding=[12, 6], font=("Segoe UI", 10))
        style.map("TNotebook.Tab", background=[("selected", "#89b4fa")],
                  foreground=[("selected", "#1e1e2e")])
        style.configure("TFrame", background="#1e1e2e")

        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=16, pady=0)

        tab_telegram = ttk.Frame(nb)
        tab_rules = ttk.Frame(nb)
        tab_log = ttk.Frame(nb)

        nb.add(tab_telegram, text="  Telegram  ")
        nb.add(tab_rules, text="  Regole  ")
        nb.add(tab_log, text="  Log push  ")

        self._build_telegram_tab(tab_telegram)
        self._build_rules_tab(tab_rules)
        self._build_log_tab(tab_log)

        # Bottone salva e push
        btn = tk.Button(self, text="💾  Salva e pubblica su GitHub",
                        font=("Segoe UI", 11, "bold"),
                        bg="#89b4fa", fg="#1e1e2e", relief="flat",
                        activebackground="#74c7ec", cursor="hand2",
                        command=self._save_and_push, pady=10)
        btn.pack(fill="x", padx=16, pady=16)

    def _label(self, parent, text):
        tk.Label(parent, text=text, font=("Segoe UI", 10),
                 bg="#1e1e2e", fg="#a6adc8", anchor="w").pack(fill="x", padx=16, pady=(10, 2))

    def _entry(self, parent, value="", show=None):
        e = tk.Entry(parent, font=("Segoe UI", 11), bg="#313244", fg="#cdd6f4",
                     insertbackground="#cdd6f4", relief="flat", show=show or "")
        e.insert(0, value)
        e.pack(fill="x", padx=16, ipady=6)
        return e

    # ---- tab Telegram ----

    def _build_telegram_tab(self, parent):
        tg = self.config_data.get("telegram", {})

        self._label(parent, "Bot Token (da @BotFather)")
        self.entry_token = self._entry(parent, tg.get("bot_token", ""), show="*")
        btn_show = tk.Button(parent, text="Mostra/Nascondi", font=("Segoe UI", 9),
                             bg="#45475a", fg="#cdd6f4", relief="flat",
                             command=lambda: self._toggle_show(self.entry_token))
        btn_show.pack(anchor="e", padx=16, pady=2)

        self._label(parent, "Chat ID (il tuo ID numerico)")
        self.entry_chatid = self._entry(parent, tg.get("chat_id", ""))

        tk.Label(parent, text="Non sai come trovarli? Segui il README.",
                 font=("Segoe UI", 9, "italic"), bg="#1e1e2e", fg="#6c7086").pack(
            anchor="w", padx=16, pady=(12, 0))

        self._label(parent, "Frequenza controllo (minuti)")
        self.entry_interval = self._entry(parent,
                                          str(self.config_data.get("check_interval_minutes", 15)))

    def _toggle_show(self, entry):
        entry.config(show="" if entry.cget("show") == "*" else "*")

    # ---- tab Regole ----

    def _build_rules_tab(self, parent):
        canvas = tk.Canvas(parent, bg="#1e1e2e", highlightthickness=0)
        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        self.rules_frame = tk.Frame(canvas, bg="#1e1e2e")

        self.rules_frame.bind("<Configure>",
                              lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=self.rules_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        for rule in self.config_data.get("rules", []):
            self._add_rule_frame(rule)

        tk.Button(self.rules_frame, text="+ Aggiungi regola",
                  font=("Segoe UI", 10), bg="#a6e3a1", fg="#1e1e2e",
                  relief="flat", cursor="hand2",
                  command=lambda: self._add_rule_frame()).pack(
            padx=16, pady=12, anchor="w")

    def _add_rule_frame(self, rule=None):
        rule = rule or {
            "name": "Nuova regola",
            "enabled": True,
            "keywords": {"mode": "AND", "include": [], "exclude": []},
            "max_price_eur": 5000,
            "expiry_within_hours": 3
        }

        box = tk.LabelFrame(self.rules_frame, text=f"  {rule.get('name', '')}  ",
                            font=("Segoe UI", 10, "bold"),
                            bg="#313244", fg="#89b4fa", relief="flat",
                            labelanchor="nw", bd=1)
        box.pack(fill="x", padx=16, pady=8)

        fields = {}

        def row(label, key, value):
            tk.Label(box, text=label, font=("Segoe UI", 9), bg="#313244",
                     fg="#a6adc8", anchor="w").grid(row=len(fields), column=0,
                     sticky="w", padx=10, pady=3)
            e = tk.Entry(box, font=("Segoe UI", 10), bg="#45475a", fg="#cdd6f4",
                         insertbackground="#cdd6f4", relief="flat", width=36)
            e.insert(0, str(value))
            e.grid(row=len(fields), column=1, padx=10, pady=3, sticky="ew")
            fields[key] = e

        row("Nome regola", "name", rule.get("name", ""))
        row("Include (separate da virgola)", "include",
            ", ".join(rule.get("keywords", {}).get("include", [])))
        row("Escludi (separate da virgola)", "exclude",
            ", ".join(rule.get("keywords", {}).get("exclude", [])))

        # Mode AND/OR
        tk.Label(box, text="Modalità", font=("Segoe UI", 9),
                 bg="#313244", fg="#a6adc8").grid(row=len(fields), column=0,
                 sticky="w", padx=10, pady=3)
        mode_var = tk.StringVar(value=rule.get("keywords", {}).get("mode", "AND"))
        mode_frame = tk.Frame(box, bg="#313244")
        mode_frame.grid(row=len(fields), column=1, sticky="w", padx=10)
        tk.Radiobutton(mode_frame, text="AND (tutte le parole)", variable=mode_var,
                       value="AND", bg="#313244", fg="#cdd6f4",
                       selectcolor="#45475a", font=("Segoe UI", 9)).pack(side="left")
        tk.Radiobutton(mode_frame, text="OR (almeno una)", variable=mode_var,
                       value="OR", bg="#313244", fg="#cdd6f4",
                       selectcolor="#45475a", font=("Segoe UI", 9)).pack(side="left", padx=8)
        fields["mode"] = mode_var

        row("Prezzo massimo (€)", "max_price", rule.get("max_price_eur", 5000))
        row("Scade entro (ore)", "expiry_hours", rule.get("expiry_within_hours", 3))

        # Attiva/disattiva
        enabled_var = tk.BooleanVar(value=rule.get("enabled", True))
        tk.Checkbutton(box, text="Regola attiva", variable=enabled_var,
                       bg="#313244", fg="#a6e3a1", selectcolor="#45475a",
                       font=("Segoe UI", 9)).grid(row=len(fields)+1, column=0,
                       columnspan=2, sticky="w", padx=10, pady=6)
        fields["enabled"] = enabled_var

        box.columnconfigure(1, weight=1)
        self.rule_frames.append(fields)

    # ---- tab Log ----

    def _build_log_tab(self, parent):
        self.log_area = scrolledtext.ScrolledText(
            parent, font=("Consolas", 10), bg="#181825", fg="#a6e3a1",
            insertbackground="#cdd6f4", relief="flat", state="disabled"
        )
        self.log_area.pack(fill="both", expand=True, padx=8, pady=8)

    def _log(self, text):
        self.log_area.configure(state="normal")
        self.log_area.insert("end", text + "\n")
        self.log_area.see("end")
        self.log_area.configure(state="disabled")
        self.update()

    # ---- salva e push ----

    def _save_and_push(self):
        # Raccoglie dati Telegram
        token = self.entry_token.get().strip()
        chat_id = self.entry_chatid.get().strip()
        interval = int(self.entry_interval.get().strip() or 15)

        if not token or not chat_id:
            messagebox.showwarning("Dati mancanti",
                                   "Inserisci Bot Token e Chat ID prima di salvare.")
            return

        # Raccoglie regole
        rules = []
        for fields in self.rule_frames:
            try:
                include_raw = fields["include"].get()
                exclude_raw = fields["exclude"].get()
                rules.append({
                    "name": fields["name"].get().strip(),
                    "enabled": fields["enabled"].get(),
                    "keywords": {
                        "mode": fields["mode"].get(),
                        "include": [k.strip() for k in include_raw.split(",") if k.strip()],
                        "exclude": [k.strip() for k in exclude_raw.split(",") if k.strip()],
                    },
                    "max_price_eur": float(fields["max_price"].get() or 0),
                    "expiry_within_hours": float(fields["expiry_hours"].get() or 3),
                })
            except Exception as e:
                self._log(f"Errore nella regola: {e}")

        # Aggiorna config.json
        self.config_data["telegram"] = {"bot_token": token, "chat_id": chat_id}
        self.config_data["check_interval_minutes"] = interval
        self.config_data["rules"] = rules
        save_config(self.config_data)
        self._log("✓ config.json salvato")

        # Patcha agent.py
        ok, msg = patch_agent_py(token, chat_id)
        self._log(f"{'✓' if ok else '✗'} {msg}")

        # Push
        self._log("\n--- Git push ---")
        ok = git_push(self._log)
        if ok:
            self._log("\n✅ Tutto pubblicato su GitHub!")
            messagebox.showinfo("Fatto!", "Configurazione salvata e pubblicata su GitHub.")
        else:
            self._log("\n⚠️  Push non riuscito — controlla il log sopra.")
            messagebox.showerror("Errore push",
                                 "Il push su GitHub non è riuscito.\nControlla il log nella tab 'Log push'.")


if __name__ == "__main__":
    app = App()
    app.mainloop()

# 🐱 Katzen-Wächter Linz (Willhaben + Landwirt.com + Tieranzeigen.at)

Automatischer Hintergrund-Wächter, der **alle 5 Minuten** rund um die Uhr nach jungen **weiblichen Bauernhofkatzen** (oder frischen Bauernhof-Würfen) im Umkreis von **50 km um Linz** sucht – **ohne Tierheime/Tierschutzvereine** – und **dir und deiner Frau gleichzeitig** sofort eine Push-Benachrichtigung inkl. Foto und Direktlink aufs Handy schickt.

## Was geprüft & gefiltert wird
* **Plattformen:**
  * **Willhaben.at** (Hauskatzen in OÖ + angrenzendes NÖ wie St. Valentin/Haag + Mischlinge mit Bauernhof-/Hauskatzen-Bezug)
  * **Landwirt.com** (Kleinanzeigen Katzen – ideal für echte Bauernhöfe!)
  * **Tieranzeigen.at** (Oberösterreich & Niederösterreich)
* **Standard-Filter (jederzeit anpassbar):**
  * **Umkreis:** max. **50 km** um Linz (exakte GPS-/PLZ-Entfernung, nur Österreich)
  * **Preis:** max. **€ 300** (inkl. „zu verschenken“ / „Preis a. A.“)
  * **Kein Tierheim / Tierschutz:** Filtert Tierheime, Tierschutzvereine, Pflegestellen, Schutzverträge & Vereins-Rassezuchten automatisch aus (erlaubt aber österreichische Bauernhof-Inserate mit *„behördlich genehmigte Zucht“* nach § 8a TSchG!)
  * **Geschlecht:** Weiblich **oder** gemischter Wurf / Geschlecht nicht angegeben (damit kein schneller Treffer durchrutscht – nur eindeutig reine Kater-Inserate werden aussortiert)
  * **Alter:** Jung / Kitten (bis ca. 7 Monate; ältere/ausgewachsene Katzen und „reserviert“ / „gesucht“-Inserate werden aussortiert)
* **Selbstüberwachung:** Falls eine Plattform 30 Min. lang Fehler/Blocks meldet, bekommt ihr automatisch eine kurze Warnung aufs Handy.

---

## Einrichtung in 5 Minuten (für dich & deine Frau!)

### Schritt 1: `ntfy` App auf beiden Handys installieren (1 Minute)
1. Installiert die kostenlose **ntfy** App auf **deinem Handy** und auf dem **Handy deiner Frau**:
   * **iPhone (App Store):** nach `ntfy` suchen
   * **Android (Google Play):** nach `ntfy` suchen
2. Denkt euch **einen gemeinsamen, geheimen Kanalnamen (Topic)** aus – wie ein Passwort, z. B.:
   `bauernhofkatze-linz-k8m2p9x4` *(bitte einen eigenen zufälligen Namen wählen!)*
3. In der **ntfy App auf beiden Handys**:
   * Auf **`+`** (Abonnieren / Subscribe) tippen
   * Genau diesen gemeinsamen Kanalnamen eingeben → **Abonnieren**
   * Mitteilungen erlauben!
   * *Fertig!* Jede Benachrichtigung klingelt ab sofort **gleichzeitig auf beiden Handys** – kostenlos und ohne Account.

### Schritt 2: Auf GitHub hochladen (24/7 kostenlos in der Cloud)
> **Wichtig für 5-Minuten-Takt über Wochen:** Lege das GitHub-Repository als **Public** an!
> Bei einem *Public*-Repo sind GitHub Actions **unbegrenzt kostenlos** (bei einem *Private*-Repo wären die 2.000 Gratis-Minuten/Monat nach ~7 Tagen aufgebraucht).
> Dein geheimes `NTFY_TOPIC` landet **nicht** im Code, sondern geschützt in den **GitHub Secrets** – niemand anderes kann es sehen.

1. Neues **Public** Repository auf [github.com/new](https://github.com/new) erstellen (z. B. `katzen-watcher-linz`, ohne README/Gitignore).
2. Diesen Ordner einmalig hochladen (im Terminal):
   ```bash
   cd /Users/mhohen/.gemini/antigravity/scratch/katzen-watcher
   git init -b main
   git add .
   git commit -m "Initial commit: Katzen-Wächter Linz"
   git remote add origin https://github.com/<DEIN-GITHUB-USER>/katzen-watcher-linz.git
   git push -u origin main
   ```
3. **Geheimes Topic in GitHub hinterlegen:**
   * Im GitHub-Repo auf **Settings → Secrets and variables → Actions → New repository secret**
   * Name: `NTFY_TOPIC`
   * Secret: euer geheimer Kanalname (z. B. `bauernhofkatze-linz-k8m2p9x4`)
   * Speichern!
4. **Permissions prüfen (einmalig):**
   * Unter **Settings → Actions → General → Workflow permissions** sicherstellen, dass **Read and write permissions** aktiviert ist (damit `state/seen.json` gespeichert werden kann).

### Schritt 3: Sofort testen, ob beide Handys klingeln!
* Im GitHub-Repo auf **Actions → Katzen-Wächter Linz (alle 5 Min.) → Run workflow**:
  * Haken bei **„Nur eine Test-Benachrichtigung ans Handy schicken?“** setzen → **Run workflow**
  * Nach ca. 15 Sekunden sollte auf **deinem und dem Handy deiner Frau** die Test-Push erscheinen!
* Danach noch einmal **Run workflow** (ohne Haken) starten – dann läuft der erste echte Check und du siehst im Log sofort, dass alle 3 Plattformen aus der GitHub-Cloud sauber erreichbar sind. Danach läuft es alle 5 Min. vollautomatisch!

---

## Filter später jederzeit anpassen (ohne Code zu ändern)
Unter **Settings → Secrets and variables → Actions → Variables** kannst du optional eigene Werte setzen:
* `MAX_DISTANCE_KM` (Standard: `50`)
* `MAX_PRICE_EUR` (Standard: `300`)
* `MAX_AGE_MONTHS` (Standard: `7`)

---

## Lokal testen & optionales Mac-Backup (`launchd`)
Falls du das Tool lokal am Mac testen möchtest:
```bash
# Trockenlauf ohne Push (zeigt aktuelle Treffer & Aussortierungen):
python3 -m src.main --dry-run --verbose

# Test-Push an euer ntfy-Topic schicken:
NTFY_TOPIC="dein-geheimes-topic" python3 -m src.main --test-notify
```

**Falls Willhaben irgendwann Cloud-IPs von GitHub blockieren sollte:**
Das Tool meldet dir das automatisch nach 30 Min. aufs Handy. In dem Fall kannst du mit einem Befehl das lokale Mac-Backup (mit deiner echten Heim-IP) aktivieren:
```bash
# Nur Willhaben lokal am Mac (während Landwirt + Tieranzeigen weiter 24/7 in der Cloud laufen):
./scripts/install_mac_launchd.sh "dein-geheimes-topic" willhaben

# Oder alle 3 Plattformen lokal am Mac:
./scripts/install_mac_launchd.sh "dein-geheimes-topic"

# Wieder stoppen:
./scripts/uninstall_mac_launchd.sh
```

**Zusatz-Tipp:** Aktiviere parallel in der normalen **Willhaben-App** (bei dir & deiner Frau) einen kostenlosen Suchagenten auf *Marktplatz → Katzen → Hauskatzen → Oberösterreich* als doppeltes Sicherheitsnetz!

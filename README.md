# psn-sync

Denní sync PSN knihovny (hry + celkový playtime) a trofejí (s přesným datem
získání) do BigQuery. Běží jako GitHub Actions job na cronu `0 4 * * *` (UTC).

Postaveno na [`psnawp`](https://github.com/isFakeAccount/psnawp) (neoficiální
PSN API wrapper). Nevystavuje se přes to per-day playtime historie — Sony
API dává jen kumulativní `playtime_hours`/`play_count`; proto DB uchovává jen
aktuální stav (viz [sql/schema.sql](sql/schema.sql)), žádné denní diffy.

## Architektura

- `src/psn_sync/psn_client.py` — veškerá komunikace s PSN (`psnawp`).
- `src/psn_sync/bigquery_client.py` — schema (`CREATE TABLE IF NOT EXISTS`) +
  stage-then-MERGE loading (BigQuery nemá UPSERT ani unique constraints).
- `src/psn_sync/secrets.py` — NPSSO token z GCP Secret Manager (lokálně lze
  přebít proměnnou `$PSN_NPSSO`).
- `src/psn_sync/sync.py` — orchestrace: fetch → diff proti uloženým hrám →
  trofeje jen pro změněné tituly → load do BigQuery → řádek do `sync_runs`.

## Tabulky (dataset `psn` v BigQuery)

| Tabulka | Obsah |
|---|---|
| `games` | jedna řádka na titul (`title_id`), aktuální `playtime_hours`/`play_count`/`last_played` |
| `trophy_definitions` | statická metadata trofejí (název, typ, popis) |
| `trophy_progress` | stav trofeje per hra: `earned`, přesné `earned_at` od Sony |
| `sync_runs` | audit log každého běhu (počty, chyby) |

## Jednorázové nastavení GCP (přes Cloud Shell, žádný lokální install)

Otevři [Cloud Shell](https://console.cloud.google.com/?cloudshell=true) (ikona
terminálu vpravo nahoře v GCP Console) — je to prohlížečový terminál, kde jsi
už přihlášený, takže odpadá řešení `gcloud auth login` lokálně.

1. **Service account** s rolemi na projektu `playstationgamesdatabase`:

   ```bash
   gcloud iam service-accounts create psn-sync \
     --project=playstationgamesdatabase \
     --display-name="PSN sync (GitHub Actions)"

   gcloud projects add-iam-policy-binding playstationgamesdatabase \
     --member="serviceAccount:psn-sync@playstationgamesdatabase.iam.gserviceaccount.com" \
     --role="roles/bigquery.dataEditor"

   gcloud projects add-iam-policy-binding playstationgamesdatabase \
     --member="serviceAccount:psn-sync@playstationgamesdatabase.iam.gserviceaccount.com" \
     --role="roles/bigquery.jobUser"
   ```

2. **JSON klíč pro GitHub Actions**:

   ```bash
   gcloud iam service-accounts keys create sa-key.json \
     --iam-account=psn-sync@playstationgamesdatabase.iam.gserviceaccount.com
   cat sa-key.json   # zkopíruj celý výstup, vlož jako repo secret GCP_SA_KEY (viz níž)
   rm sa-key.json
   ```

3. **Repo secrets** (Settings → Secrets and variables → Actions → *Secrets*):

   | Name | Hodnota |
   |---|---|
   | `GCP_SA_KEY` | celý obsah `sa-key.json` |
   | `PSN_NPSSO` | tvůj 64znakový NPSSO token |

   `PSN_NPSSO` jako přímý secret je zkratka pro test/první běh — kód nejdřív
   zkusí `$PSN_NPSSO`, a teprve když není nastavený, sáhne do GCP Secret
   Manager (`NPSSO_SECRET_NAME`). Secret Manager (bod 4 níže) je volitelný,
   vhodný až později kvůli auditu/rotaci.

4. **Repo variables** (stejné místo → *Variables*):

   | Name | Hodnota |
   |---|---|
   | `GCP_PROJECT` | `playstationgamesdatabase` |
   | `BQ_DATASET` | `psn` |
   | `BQ_LOCATION` | `EU` |

Dataset a tabulky v BigQuery se vytvoří samy při prvním běhu (`ensure_schema`).

### Volitelně: NPSSO v Secret Manager (místo přímého secretu)

```bash
gcloud secrets create psn-npsso --project=playstationgamesdatabase \
  --replication-policy=automatic
echo -n "<tvůj npsso token>" | \
  gcloud secrets versions add psn-npsso --project=playstationgamesdatabase --data-file=-
gcloud secrets add-iam-policy-binding psn-npsso \
  --project=playstationgamesdatabase \
  --member="serviceAccount:psn-sync@playstationgamesdatabase.iam.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"
```
Pak smaž repo secret `PSN_NPSSO` a nastav variable `NPSSO_SECRET_NAME=psn-npsso`.

## Test přes GitHub Actions

Po nastavení výše: záložka **Actions → PSN sync to BigQuery → Run workflow**,
do pole `limit` napiš např. `5` (test na pár titulech) a spusť. Log běhu
uvidíš přímo v Actions; výsledek ověříš v BigQuery (`bq query` nebo konzole).

## Lokální test bez GCP (dry-run)

Ověří jen PSN část (fetch her + trofejí), nic nezapisuje a nepotřebuje GCP
přihlášení:

```bash
export PSN_NPSSO="$(cat ~/.config/psnstats/npsso)"
export GCP_PROJECT=playstationgamesdatabase   # vyžadováno i pro dry-run (Config.from_env)
pip install -e .
python -m psn_sync.sync --dry-run
```

## Lokální plný běh (s GCP)

```bash
gcloud auth application-default login
export PSN_NPSSO="$(cat ~/.config/psnstats/npsso)"
export GCP_PROJECT=playstationgamesdatabase
python -m psn_sync.sync
```

-- Ukázkové dotazy nad datasetem `playstationgamesdatabase.psn` (viz schema.sql).
-- Zkopíruj jednotlivé dotazy do BigQuery konzole (console.cloud.google.com/bigquery)
-- nebo spusť přes `bq query --use_legacy_sql=false "$(cat ...)"`.

-- 1) Seznam všech her podle odehraného času (sestupně).
SELECT
  title,
  system,
  ROUND(playtime_hours, 1) AS hours,
  play_count,
  last_played
FROM `playstationgamesdatabase.psn.games`
ORDER BY playtime_hours DESC;


-- 2) Souhrn trofejí po hrách: kolik celkem, kolik získaných, % dokončení
--    a rozpad podle typu (platina/zlato/stříbro/bronz).
SELECT
  g.title,
  g.system,
  COUNT(*) AS total_trophies,
  COUNTIF(tp.earned) AS earned_trophies,
  ROUND(100 * COUNTIF(tp.earned) / COUNT(*), 1) AS pct_complete,
  COUNTIF(tp.earned AND td.trophy_type = 'platinum') AS platinum,
  COUNTIF(tp.earned AND td.trophy_type = 'gold') AS gold,
  COUNTIF(tp.earned AND td.trophy_type = 'silver') AS silver,
  COUNTIF(tp.earned AND td.trophy_type = 'bronze') AS bronze
FROM `playstationgamesdatabase.psn.trophy_progress` tp
JOIN `playstationgamesdatabase.psn.trophy_definitions` td
  ON tp.np_communication_id = td.np_communication_id AND tp.trophy_id = td.trophy_id
JOIN `playstationgamesdatabase.psn.games` g
  ON g.title_id = tp.title_id
GROUP BY g.title, g.system
ORDER BY pct_complete DESC;


-- 3) Kompletní seznam trofejí ke konkrétní hře, seřazený podle data získání.
--    Uprav podmínku ve WHERE podle názvu hry, kterou chceš zobrazit.
SELECT
  td.trophy_name,
  td.trophy_type,
  td.trophy_detail,
  tp.earned,
  tp.earned_at,
  tp.rarity
FROM `playstationgamesdatabase.psn.trophy_progress` tp
JOIN `playstationgamesdatabase.psn.trophy_definitions` td
  ON tp.np_communication_id = td.np_communication_id AND tp.trophy_id = td.trophy_id
JOIN `playstationgamesdatabase.psn.games` g
  ON g.title_id = tp.title_id
WHERE g.title LIKE '%METAL GEAR SOLID V%'
ORDER BY tp.earned_at;


-- 4) Posledních 20 získaných trofejí napříč celou knihovnou (nejnovější nahoře).
SELECT
  g.title,
  td.trophy_name,
  td.trophy_type,
  tp.earned_at
FROM `playstationgamesdatabase.psn.trophy_progress` tp
JOIN `playstationgamesdatabase.psn.trophy_definitions` td
  ON tp.np_communication_id = td.np_communication_id AND tp.trophy_id = td.trophy_id
JOIN `playstationgamesdatabase.psn.games` g
  ON g.title_id = tp.title_id
WHERE tp.earned = TRUE
ORDER BY tp.earned_at DESC
LIMIT 20;


-- 5) Historie sync běhů (audit log) — kdy proběhl sync, kolik her/trofejí
--    se zpracovalo a jestli bez chyby.
SELECT started_at, finished_at, games_synced, trophies_synced, status, error_message
FROM `playstationgamesdatabase.psn.sync_runs`
ORDER BY started_at DESC;


-- 6) Hry, které zatím nemají žádný řádek v trophy_progress (nikdy se pro ně
--    nepodařilo stáhnout trofeje — buď čekají na další sync, nebo pro ně Sony
--    žádný trophy title nevrací, viz sql/schema.sql a poznámka v repo paměti).
SELECT title, system, playtime_hours
FROM `playstationgamesdatabase.psn.games` g
WHERE NOT EXISTS (
  SELECT 1 FROM `playstationgamesdatabase.psn.trophy_progress` tp
  WHERE tp.title_id = g.title_id
)
ORDER BY playtime_hours DESC;


-- 7) Hry, pro které Sony API nevrací žádný trophy title (np_communication_id
--    je NULL). Jde o known limitation, ne o chybu — viz poznámka v repo paměti
--    (/memories/repo/psn-sync-bigquery.md) a komentář v src/psn_sync/psn_client.py.
SELECT title, system, playtime_hours
FROM `playstationgamesdatabase.psn.games`
WHERE np_communication_id IS NULL
ORDER BY playtime_hours DESC;


-- 8) Kolik her celkem má vs. nemá stažené trofeje — rychlý přehled pokrytí.
SELECT
  COUNT(*) AS total_games,
  COUNTIF(np_communication_id IS NOT NULL) AS games_with_trophies,
  COUNTIF(np_communication_id IS NULL) AS games_without_trophies
FROM `playstationgamesdatabase.psn.games`;

# Ground truth from the game (calibration data for decoders)

Source: karl's own screenshots, in-game date 4/12/2037, build 26.3.2.
These are FACTS the save-file decoders must reproduce. Decoders exist so the
write-up does not depend on screenshots; these pin down field meanings.

## Manager profile
- Karl Hudgell, born 17/3/1986 (51 at Dec 2037), English, Continental B Licence,
  studying Continental A. Contract £8.5k p/w until 30/6/2040 (St. Albans).
- Personality: Fairly Determined. Tactical style: Control Possession.
  Preferred formations: 4-4-2, 4-4-2 2DM. Tendencies include Plays Attacking
  Football, possession-based style, signs high-reputation/domestic players.
- Top attributes: Motivating/Authority/People Management Elite-level.

## Manager career (Job History screen, "data only valid from 26/12/2024")
Joined St. Albans 18/7/2023; never left; 1 club job.

| season | league | position | awards | trophies |
|---|---|---|---|---|
| 2023/24 | Vanarama South | 3rd | 1 | 0 |
| 2024/25 | Vanarama South | 1st | 2 | 2 |
| 2025/26 | Vanarama National | 1st | 2 | 1 |
| 2026/27 | Sky Bet League Two | 3rd | 2 | 0 |
| 2027/28 | Sky Bet League One | 7th | 1 | 0 |
| 2028/29 | Sky Bet League One | 1st | 2 | 1 |
| 2029/30 | Sky Bet Championship | (5th?) | 1 | 0 |
| 2030/31 | Sky Bet Championship | ? | ? | 0 |
| 2031/32 | Sky Bet Championship | 7th | 1 | 0 |
| 2032/33 | Sky Bet Championship | 5th | 1 | 0 |
| 2033/34 | Sky Bet Championship | 2nd | 2 | 0 |
| 2034/35 | Premier Division | 12th | 0 | 0 |
| 2035/36 | Premier Division | 12th | 0 | 0 |
| 2036/37 | Premier Division | 11th | 0 | 0 |
| 2037/38 | Premier Division | ongoing | 0 | 0 |

- Career totals: 741 games, 391W 131D 219L (52% win), GF 1589, GA 1059, 1 cup,
  league titles = 3 visible in screenshot (cut; 3 by honours list below).
- Awards: 19 total. Named in biography: Vanarama NLS Manager of the Season
  runner-up; Vanarama National League Manager of the Year; Sky Bet League Two
  Manager of the Season; Sky Bet League One Manager of the Season; Sky Bet
  Championship Manager of the Season (twice).
- Highest fee spent £23M (Corentin Dumas, 10/8/2036); highest received £32.5M
  (Ben Young-Thomas, 9/8/2036?); 127 players bought (£101M), 39 sold, 50 released.

## Club (St. Albans City, db unique_id 717, save uid 716)
- Founded 1908, professional, The Saints, St. Albans Stadium. Rivals: Boreham
  Wood, Hemel Hempstead Town.
- Honours (8 shown in list; counts seen): Sky Bet League One x1; Vanarama
  National x1; FA Trophy x1; Vanarama South x1; Isthmian D1 x1; Isthmian
  Premier x3 (pre-career history).
- Club history narrative: runners-up in English 2nd tier in 2034; won English
  3rd tier 2029; won English 5th tier 2026; FA Trophy 2025; best spell "the 2030s";
  eight-year trophy drought after 2029 as of Dec 2037.
- League history chart: 18/19 onward, climb VNS → VNL → L2 → L1 → CH → PRM.
- Highest League Position: 11th Premier Division (2036/37).
- Landmarks: youth facilities upgraded 4/4/2037.
- 2024/25: Vanarama National League South champions, 111 points (source: season
  summary news item 6 May 2025; Worthing 2nd with 96). GF/game 2.80, xG/game 2.37,
  87% pass completion — league-best in all shown categories.
- Premier Division table 2037/38 after 13 games (from save, matches game): 10th,
  19 pts (W5 D4 L4).

## Known data-corpus facts (from the saves)
- Save 1 (26.0.6 launch build): finances monthly 2032-12 → 2037-11 for St Albans:
  balance -£1.2M → £131M; transfer budgets allocated ~0.5M/yr net recently.
- tc_manager_history_dt has exactly ONE u32 literal 716 (the spell record,
  ~0x36c4): one spell, club 716, day word 182 (≈ July 1), year word 2023 nearby.
- tc_cup_history_dt: 20 rows referencing club 716 in 16-byte records with season
  year-pairs (0x7e8/0x7e9 = 2024/2025 etc.) — cup campaigns per season.
- award_year_hist_dt: 29 rows referencing 716 (awards won incl. club awards,
  not only the manager's 19).
- comp_history_dt: 37 rows referencing 716; 55-byte stride blocks, season rows
  2018→2021 visible in the probed block (pre-career club history), two u32
  payloads per row (263…9,490 range) — meaning unresolved.
- hall_of_fame: 4 rows referencing 716.
- FM24-import artefacts: duplicated player records (2 uids duplicated);
  manager-history screens say data only valid from 26/12/2024.
- FM24 origin: career began in FM24 (screenshots from Jan 2025 FM24/DB 24.3),
  imported into FM26 and continued; started unemployed, took St. Albans July 2023.
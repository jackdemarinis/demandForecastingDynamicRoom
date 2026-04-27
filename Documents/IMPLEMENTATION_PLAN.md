# CSC 561 Project Implementation Plan

## 1. Project goal

The goal of this project is to build an academic MVP for hotel demand forecasting and pricing support for **D. Hotel Suites & Spa**. The final system should do two things:

1. Forecast future hotel demand as accurately as possible.
2. Turn that demand forecast into a bounded room pricing recommendation.

The important adjustment is that the repository still does **not** contain a forecasting or pricing pipeline yet, but it now contains cleaned operational datasets and preprocessing scripts in addition to the raw report exports. That means the next part of the project is still not model training first. The next part is building a canonical modeling table from the cleaned files we now have.

## 2. What is currently in the repository

As of this repository inspection, the project contains:

- `Documents/CSC_561_Individual_Project_Proposal.pdf`
- `Data/` with guest-list exports, ReservationForecast daily reports, Block RoomSales daily reports, and STR STAR report exports
- `cleaned_data/` with cleaned guest-list outputs plus cleaned ReservationForecast and Block RoomSales outputs
- `scripts/clean_new_operational_reports.py`
- no README yet
- no notebooks yet
- no forecasting or training pipeline yet

So the repo is still a **data-first starting point**, but it is no longer only raw reports. We now have cleaned operational datasets that can support the next modeling stage.

## 3. Exact data we have right now

### 3.1 Proposal document

We have **1 PDF**:

- `Documents/CSC_561_Individual_Project_Proposal.pdf`

This file is not training data. It is the scope document that explains the intended project direction:

- compare baseline models and deep learning models
- forecast hotel demand
- generate pricing recommendations
- evaluate with error metrics and business metrics

We will use this PDF as the requirements reference, not as model input.

### 3.2 Guest list data

We have **11 legacy Excel `.XLS` guest-list files**. Each file has:

- one sheet named `GuestNameList`
- `31` columns in report layout
- multi-row records instead of a clean one-row-per-stay table
- data for one property: `D. Hotel Suites & Spa`
- report scope marked as `All Guest Records`

#### Guest-list file inventory

| File | Coverage period | Total sheet rows | Approx. stay rows |
| --- | --- | ---: | ---: |
| `GuestNameList Jan Feb 2025.XLS` | 1/1/2025 - 2/28/2025 | 12,826 | 3,862 |
| `GuestNameList mar 2025.XLS` | 3/1/2025 - 3/31/2025 | 10,608 | 3,148 |
| `GuestNameList apr2025.XLS` | 4/1/2025 - 4/30/2025 | 10,527 | 3,136 |
| `GuestNameList MAY2025.XLS` | 5/1/2025 - 5/31/2025 | 11,546 | 3,340 |
| `GuestNameList JUNE2025.XLS` | 6/1/2025 - 6/30/2025 | 10,431 | 3,068 |
| `GuestNameList JULY2025.XLS` | 7/1/2025 - 7/31/2025 | 11,165 | 3,320 |
| `GuestNameList AUGUST2025.XLS` | 8/1/2025 - 8/31/2025 | 13,439 | 3,986 |
| `GuestNameList SEPT2025.XLS` | 9/1/2025 - 9/30/2025 | 10,923 | 3,188 |
| `GuestNameList OCTOBER2025.XLS` | 10/1/2025 - 10/31/2025 | 13,269 | 3,892 |
| `GuestNameList NOVEMBER2025.XLS` | 11/1/2025 - 11/30/2025 | 10,109 | 3,064 |
| `GuestNameList DECEMBER2025.XLS` | 12/1/2025 - 12/31/2025 | 8,924 | 2,726 |

Approximate total stay rows detected from arrival-date lines: **36,730**

Important note: that `36,730` figure is an inference from the report body, not a final cleaned reservation count. These guest-list files are report-style exports where one logical stay spans multiple lines.

#### Guest-list fields visible in the raw reports

From the multi-row headers and sample body rows, the guest-list exports contain fields such as:

- arrival date
- departure date
- guest name
- address
- phone number
- email
- folio number
- confirmation number
- room number
- room type
- nights
- adults
- market segment
- rate code
- rate
- hold type
- status
- balance
- group
- corporate profile
- loyalty program number
- VIP code
- ETA
- comments / booking notes
- other names / share names
- ID number

#### What the guest-list files are good for

These files are the reservation-level operational source in the repo. After cleaning, they let us build:

- stay-level reservation records
- daily arrival and departure counts
- daily rooms sold proxies
- ADR-related features
- market-segment mix features
- room-type usage features
- length-of-stay features

#### Important limitations in the guest-list files

- The files are not already normalized.
- Each stay appears to span several report rows.
- These files contain **PII** such as guest names, email addresses, addresses, and ID numbers.
- PII should be removed or hashed during preprocessing and must not be used as predictive features.
- Some comments include long free-text booking and payment notes, which may be useful for cleaning or source inference but should not be part of the initial MVP model.

### 3.3 Daily operational forecast and RoomSales data

We now also have **14 legacy Excel `.xls` daily operational report files** across two report families that materially change the confirmed data available to the project.

#### ReservationForecast family

The `ReservationForecast*.xls` files are property-level daily reports.

Confirmed cleaned coverage:

- `2023-01-01` through `2024-12-31`
- `731` cleaned daily rows
- no missing dates inside that span

Confirmed fields in the cleaned output:

- business date
- arrivals
- departures
- stayovers
- projected walk-ins
- projected cancellation / no-show rate
- rooms sold
- total comp rooms
- out of order rooms
- occupancy percentage
- room revenue (net)
- ADR
- RevPAR
- transient rooms
- group rooms picked up
- group rooms not picked up
- group room revenue (net)
- group ADR
- group non-GTD arrivals
- group GTD arrivals
- group comp rooms
- total group guests in house

Important note:

- the projected walk-in and projected cancellation / no-show columns exist, but every observed value in the current 2023-2024 files is zero

#### Block RoomSales family

The `Block*.xls` files are RoomSales reports that provide daily totals plus room-class and room-type detail.

Confirmed cleaned coverage:

- `2023-01-01` through `2025-12-31`
- `1,096` cleaned property-level daily total rows
- `2,192` cleaned room-class rows
- `10,960` cleaned leaf room-type rows
- `10` cleaned special adjustment rows after deduplicating repeated raw pairs
- no missing dates inside that span

Confirmed fields in the cleaned outputs:

- business date
- property total rooms
- on-market rooms
- out of order rooms
- rooms sold
- transient rooms
- group rooms
- day-use rooms
- comp rooms
- gross and net room revenue
- gross and net ADR
- gross and net RevPAR
- room-class daily rollups for `Standard` and `Suite`
- daily leaf room-type metrics for `10` room-type codes

Important structural note:

- `Standard` and `Suite` are room-class rollups, not leaf room types
- the raw `***` rows are special revenue-adjustment rows, not valid room-type rows
- the cleaned outputs keep those row types separate so the report can be used without double-counting

#### What these operational report families are good for

These files materially strengthen the project because they give us:

- direct daily rooms sold instead of only guest-list-derived proxies
- direct daily room revenue, ADR, and RevPAR
- explicit daily on-market inventory and out-of-order counts
- multi-year daily operational history covering `2023`, `2024`, and `2025`
- room-class-level and room-type-level daily operational metrics
- a direct daily target table for forecasting work

#### Important limitations in these operational report families

- they still do **not** provide booking creation date / time
- the two report families use different occupancy denominators:
  - Block RoomSales occupancy is based on total property inventory
  - ReservationForecast occupancy appears to align with on-market rooms on overlapping dates
- some segment-specific counts differ slightly between the two families on overlapping dates
- the special `***` adjustment rows need to stay isolated from room-type modeling tables

### 3.4 STR STAR data

We have **32 `.xlsx` STR STAR report files** for the same property (`STR ID 42439`), but these are not 32 unique months.

After reading the embedded report month inside each workbook:

- there are **11 actual report months**
- there are **21 unique binary file variants**
- several files are exact copies
- some months have multiple slightly different file variants
- one file named like a July file actually contains a **June 2025** report

#### STAR report month inventory

| Embedded report month | Files present | Unique variants | Notes |
| --- | ---: | ---: | --- |
| March 2025 | 2 | 1 | exact copy pair |
| April 2025 | 1 | 1 | single file |
| May 2025 | 2 | 1 | exact copy pair |
| June 2025 | 6 | 4 | includes the file named `july2025`, but its embedded month is still June 2025 |
| August 2025 | 3 | 2 | duplicate plus variant |
| September 2025 | 3 | 2 | duplicate plus variant |
| October 2025 | 3 | 2 | duplicate plus variant |
| November 2025 | 3 | 2 | duplicate plus variant |
| December 2025 | 3 | 2 | duplicate plus variant |
| January 2026 | 3 | 2 | duplicate plus variant |
| February 2026 | 3 | 2 | duplicate plus variant |

Important gap: there is **no confirmed July 2025 STAR workbook** in the current repo contents.

#### What is inside each STAR workbook

Each STAR workbook contains **23 sheets**, including:

- `Table of Contents`
- `Glance`
- `Summary`
- `Comp`
- `Industry`
- `Day of Week`
- `Day of Week Industry`
- `Daily by Month`
- `Daily by Month Industry`
- `Segmentation Glance`
- `Segmentation Occ`
- `Segmentation ADR`
- `Segmentation RevPAR`
- `Segmentation Indexes`
- `Segmentation Ranking`
- `Segmentation DOW Month`
- `Segmentation DOW YTD`
- `Segmentation DOW Run 3`
- `Segmentation DOW Run 12`
- `Add Rev ADR`
- `Add Rev RevPAR`
- `Response`
- `Help`

#### Metrics visible in the STAR reports

The STAR reports give us benchmark and market-context metrics such as:

- occupancy percentage
- ADR
- RevPAR
- MPI
- ARI
- RGI
- supply
- percent change for current month, year to date, running 3 months, and running 12 months
- competitive-set comparisons
- industry comparisons
- day-of-week patterns
- segmentation metrics for transient, group, contract, and total
- additional revenue views such as TrevPOR and TrevPAR

#### What the STAR files are good for

These files are useful for:

- market benchmarking
- competitive context
- external validation context
- comparing hotel performance to comp set and industry
- creating monthly performance features
- evaluating whether model-assisted pricing would outperform historical patterns

#### Important limitations in the STAR files

- These are **aggregated reports**, not raw reservation transactions.
- They do not give us a clean daily competitor price table.
- They are much more useful for benchmarking and evaluation than for direct row-level model training.
- They must be deduplicated and canonicalized before use.

## 4. What data we do not currently have in a clean usable form

The proposal expected inputs such as reservations, stay dates, booking dates, room types, rates, occupancy, and possibly competitor pricing and market signals. Based on the current repository contents, much more of that is now confirmed directly, but some key fields are still missing.

What is still not currently confirmed as a clean modeling input:

- explicit booking creation date for each reservation
- clean booking-pace history
- clean competitor daily pricing table
- explicit local-event features
- holiday flags beyond what we engineer ourselves
- a final merged modeling table that combines guest-list, daily operational reports, and STAR benchmarks into one training-ready dataset

This matters because the original proposal is stronger than the current raw data state. We can still complete the project, but the first milestone must be **data engineering and dataset construction**.

## 5. What we are going to do with the data

### 5.1 Guest-list data

We will use the guest-list files as the reservation-level enrichment dataset, not as the only operational source.

We will do the following with them:

1. Parse the legacy `.XLS` reports into structured records.
2. Flatten the multi-row report layout into one row per stay or one row per reservation.
3. Standardize types for dates, rates, statuses, room types, and market segments.
4. Remove or hash PII fields.
5. Derive daily aggregates by stay date.
6. Build model features such as:
   - rooms sold by day
   - length of stay
   - average rate
   - segment mix
   - room-type mix
   - weekend and seasonality indicators
7. Use those features to enrich the primary daily operational tables with reservation-level and segment-level detail.

### 5.2 Daily operational report data

We will use the cleaned ReservationForecast and Block RoomSales outputs as the primary daily forecasting source.

We will do the following with them:

1. Build one canonical property-level daily operational table anchored on the cleaned Block daily totals.
2. Join in ReservationForecast fields that are not available in Block, especially arrivals, departures, stayovers, and group-arrival fields.
3. Keep occupancy-denominator differences explicit instead of blending the two occupancy measures blindly.
4. Use the room-class and room-type daily outputs for room-mix and inventory features.
5. Treat the cleaned adjustment rows as explicit revenue adjustments rather than room-type rows.
6. Use the resulting daily operational table as the main direct target source for forecasting.

Expected output:

- one canonical cleaned daily operational target table
- one supporting room-class daily table
- one supporting room-type daily table

### 5.3 STAR data

We will use the STAR files as a benchmark and market-context dataset, not as the core transactional dataset.

We will do the following with them:

1. Deduplicate exact copies.
2. Resolve multiple variants for the same report month.
3. Extract monthly hotel, comp-set, and industry metrics.
4. Build a clean monthly benchmark table.
5. Use that benchmark table to:
   - compare hotel performance against the market
   - add context features where appropriate
   - evaluate pricing strategy quality
   - support final report visualizations

### 5.4 Proposal PDF

We will use the proposal document to keep the work aligned with the original course objective:

- compare baseline and deep learning models
- produce a forecasting system
- produce a pricing recommendation layer
- report both predictive and business outcomes

## 6. Recommended project scope based on the data we actually have

The most realistic MVP with the current repository is:

1. Use the cleaned daily operational reports as the primary direct target dataset.
2. Enrich that daily table with guest-list-derived reservation and segment detail where it adds value.
3. Forecast daily rooms sold and related daily demand metrics.
4. Use STAR monthly data for market benchmarking and pricing context.
5. Generate bounded pricing recommendations from the forecast.

That is a strong CSC 561 project and is still aligned with the proposal.

The project becomes much stronger if we later obtain:

- booking creation dates
- cleaner PMS reservation exports
- real competitor pricing series
- event and holiday signals

## 7. How we are going to build the codebase

We should build the code in phases. The correct order is important because model quality depends on data quality.

### Phase 1: Repository structure

We will first create a simple project structure for reproducible work:

- `src/ingest/`
- `src/clean/`
- `src/features/`
- `src/models/`
- `src/pricing/`
- `src/evaluation/`
- `data/raw/`
- `data/interim/`
- `data/processed/`
- `notebooks/`
- `reports/figures/`

### Phase 2: Daily operational report integration

This is now the most important engineering step for the forecasting target.

We will build integration logic that:

- reads the cleaned ReservationForecast and Block RoomSales outputs
- resolves metric-definition differences between the two report families
- keeps the Block daily totals as the canonical daily target spine
- adds ReservationForecast-only fields where they improve forecasting features
- preserves audit fields so every daily row can be traced back to source workbooks

Expected output:

- one canonical cleaned daily operational target table
- one cleaned room-class daily table
- one cleaned room-type daily table

### Phase 3: Guest-list ingestion and parsing

We will continue to use the guest-list files for reservation-level enrichment.

This step will:

- read legacy `.XLS` files
- identify the repeating multi-row reservation pattern
- convert each logical reservation into one structured record
- keep only fields useful for modeling and audit
- remove PII from downstream model tables

Expected output:

- one cleaned reservation table
- one guest-list-derived daily enrichment table

### Phase 4: STAR extraction

We will build a separate extractor for the STAR workbooks.

This step will:

- read each workbook
- choose one canonical file per report month
- pull key metrics from `Glance`, `Summary`, segmentation sheets, and day-of-week sheets
- store those metrics in a clean monthly benchmark table

Expected output:

- one deduplicated monthly STAR benchmark table

### Phase 5: Data quality checks

Before modeling, we will validate:

- duplicate stays
- missing dates
- impossible stays
- bad rates
- inconsistent room-type labels
- missing months
- occupancy-denominator differences between ReservationForecast and Block daily reports
- special Block adjustment rows
- mismatch between guest data coverage and STAR coverage

This phase also includes confirming the July 2025 STAR gap and deciding whether we can obtain that missing report.

### Phase 6: Feature engineering

Once the cleaned tables exist, we will create forecasting features such as:

- stay date
- day of week
- month
- quarter
- weekend flag
- holiday flag
- rolling averages
- lagged demand values
- lagged rate values
- room-type counts
- segment mix
- recent occupancy behavior
- recent ADR behavior
- STAR benchmark context by month

### Phase 7: Baseline models

Before deep learning, we need strong baselines.

We should start with:

- moving average baseline
- seasonal baseline
- linear regression
- tree-based model such as XGBoost or Random Forest

These models tell us whether the data pipeline is useful before we invest in more complex models.

### Phase 8: Deep learning comparison

After the baseline models are working, we will compare:

- MLP
- LSTM
- GRU
- a small Transformer-based time-series model

These models will use chronological splits, not random splits.

### Phase 9: Pricing recommendation layer

The pricing layer should come after demand prediction, not before it.

The first version should be a bounded rule-based layer that:

- starts from current or recent ADR
- increases price when forecast demand is strong
- decreases price when forecast demand is weak
- keeps recommendations inside realistic business limits
- optionally uses STAR benchmark context to avoid unrealistic recommendations

This is the safest academic MVP and is easier to explain in the final report than a full optimization engine.

### Phase 10: Evaluation

We will evaluate the forecasting model with:

- MAE
- RMSE
- MAPE
- R-squared

We will evaluate the pricing recommendation layer with business-facing comparisons such as:

- simulated revenue
- ADR difference
- occupancy difference
- RevPAR difference

### Phase 11: Final deliverables

The final project should include:

- cleaned datasets
- reproducible preprocessing pipeline
- baseline model results
- deep learning comparison results
- pricing recommendation logic
- plots of predicted vs actual demand
- plots of recommended vs historical price
- benchmark comparisons using STAR data
- final CSC 561 report and presentation material

## 8. Primary target variable recommendation

Based on the data currently in the repo, the best primary target is likely:

- **daily rooms sold**

or

- **daily occupancy-related demand**

Why this is the best choice:

- it aligns with the proposal
- it is now observed directly in the cleaned daily operational report files
- it can be cross-validated across multiple operational report families
- it is easier to validate than a fully direct pricing target
- it lets pricing be handled as a second-stage decision layer

ADR and daily net room revenue can be secondary targets or supporting features.

## 9. What should not be used as model features

These fields should not be used directly as predictive features:

- guest name
- address
- phone number
- email
- ID number
- confirmation number
- folio number
- raw comments text in the initial MVP

These fields are either private, unstable, overly specific, or likely to leak information.

## 10. Main risks and how we handle them

### Risk 1: The guest-list files are messy report exports

Response:

- build the parser first
- validate record reconstruction carefully
- test on one month before scaling to all months

### Risk 2: STAR files contain duplicates and variants

Response:

- canonicalize one version per report month
- document exactly which file becomes the monthly source of truth

### Risk 3: Missing booking-date information may weaken booking-pace features

Response:

- use demand-by-stay-date forecasting as the MVP
- add booking-pace features only if a clean reservation creation field is found or obtained

### Risk 4: PII in the raw files

Response:

- anonymize early
- keep raw PII out of modeling tables and shared outputs

### Risk 5: The operational report families define occupancy differently

Response:

- keep Block and ReservationForecast occupancy metrics separate until their denominators are handled explicitly
- prefer direct rooms sold and revenue targets for the first forecasting MVP
- document any denominator conversions instead of silently merging occupancy fields

## 11. Final summary

This project is absolutely buildable, but the correct first step is not "train a deep learning model." The correct first step is:

1. turn the daily operational report families into one canonical daily forecasting table
2. use the guest-list exports as reservation-level enrichment
3. turn the STAR workbooks into a clean monthly benchmark dataset
4. build baseline forecasting models
5. compare deep learning models against those baselines
6. add a bounded pricing recommendation layer

In short:

- the **ReservationForecast and Block RoomSales files** will become the main daily operational forecasting source
- the **guest-list files** will become the reservation-level enrichment source
- the **STAR files** will become the benchmark and market-context dataset
- the **proposal PDF** will stay the scope and evaluation reference

That is the cleanest path to completing the CSC 561 project with the data that is actually present in this repository.

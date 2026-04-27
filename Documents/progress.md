# Step 1 Progress: Clean and Deduplicate the Operational Guest Dataset

## Scope completed

This update completes **Step 1 only**: cleaning and deduplicating the main guest/reservation dataset.

## Assumption used for Step 1

I treated the `GuestNameList*.XLS` files as the main operational dataset for Step 1 because they are the reservation-like raw records needed for later forecasting work.

I did **not** clean the `Monthly STAR_*.xlsx` files in this step. Those files are benchmarking reports, not the core reservation dataset, and they should be cleaned in a separate pass.

## Raw files used

The following raw files were read from `Data/` and were **not modified**:

- `Data/GuestNameList Jan Feb 2025.XLS`
- `Data/GuestNameList mar 2025.XLS`
- `Data/GuestNameList apr2025.XLS`
- `Data/GuestNameList MAY2025.XLS`
- `Data/GuestNameList JUNE2025.XLS`
- `Data/GuestNameList JULY2025.XLS`
- `Data/GuestNameList AUGUST2025.XLS`
- `Data/GuestNameList SEPT2025.XLS`
- `Data/GuestNameList OCTOBER2025.XLS`
- `Data/GuestNameList NOVEMBER2025.XLS`
- `Data/GuestNameList DECEMBER2025.XLS`

## Folder(s) created

- `cleaned_data/`

## Files created

- `cleaned_data/guest_stays_cleaned.csv`
- `cleaned_data/guest_stays_duplicates_removed.csv`
- `cleaned_data/guest_stays_cleaning_summary.json`
- `progress.md`

## Output audit columns added

In addition to the cleaned reservation fields, the cleaned output includes audit columns that were added during Step 1 so the deduplication can be traced:

- `cleaned_record_id`
- `source_occurrences`
- `dedupe_key_type`
- `dedupe_key`
- `merged_source_files`
- `merged_source_row_ranges`
- `kept_provisional_id`
- `conflicting_nonkey_fields`
- `fields_filled_from_duplicates`

The duplicate audit file `cleaned_data/guest_stays_duplicates_removed.csv` also includes explicit trace columns for each removed duplicate copy:

- `duplicate_group_id`
- `kept_cleaned_record_id`
- `kept_provisional_id`
- `dropped_provisional_id`
- `dedupe_key_type`
- `dedupe_key`
- `dropped_source_file`
- `dropped_source_row_start`
- `dropped_source_row_end`
- `source_occurrences_in_group`
- `drop_reason`
- `group_conflicting_nonkey_fields`

## Raw layout inspection result

The raw guest files are **not** flat one-row-per-reservation tables.

Each workbook contains one sheet named `GuestNameList`, and each logical reservation appears as a **multi-line report block**. The parser used this explicit record-boundary rule:

- a new reservation block starts on a row where:
  - column 2 contains a date string
  - column 21 contains a text rate code
  - column 25 contains a text status

This was necessary before any tabular cleaning or deduplication could happen.

## Provisional row creation before cleaning

The multi-line blocks were first converted into provisional reservation rows.

Provisional extracted row count:

- `18,365` provisional reservation rows parsed from the 11 raw guest files

Fields extracted from the raw blocks:

- `source_file`
- `source_row_start`
- `source_row_end`
- `arrival_date`
- `departure_date`
- `nights`
- `adults_raw_primary`
- `market_segment`
- `rate_code`
- `rate`
- `hold_type`
- `status`
- `room_type`
- `room_number`
- `confirmation_number`
- `folio_number`
- `balance`
- `guest_name`
- `email`
- `comments`
- `co_cu_raw`
- `co_count`
- `cu_count`

## Cleaning steps performed

The following transformations were performed explicitly and in this order.

### 1. Multi-line block parsing

- Converted each repeating report block into one provisional reservation row.
- Preserved source lineage with `source_file`, `source_row_start`, and `source_row_end`.

### 2. Whitespace cleanup

- Trimmed leading and trailing whitespace from all extracted text fields.
- Collapsed repeated internal spaces.
- Collapsed repeated newlines.

### 3. Date standardization

- Converted `arrival_date` and `departure_date` from `MM/DD/YYYY` strings to ISO `YYYY-MM-DD`.

### 4. Numeric type cleanup

- Converted `confirmation_number` to nullable integer.
- Converted `folio_number` to nullable integer.
- Converted `nights` to integer when it was a whole number.
- Converted `adults_raw_primary` to nullable integer.
- Converted `co_count` and `cu_count` to nullable integers when `co_cu_raw` matched `N/N`.
- Converted `rate` to numeric and rounded to 2 decimals.
- Converted `balance` to numeric and rounded to 2 decimals.
- Normalized numeric-like `room_number` values such as `423.0` to string `423`.

### 5. Text value standardization

- Lowercased `email`.
- Uppercased `hold_type`.
- Uppercased `room_type`.
- Canonicalized `status` values to observed standard forms:
  - `Checked-Out`
  - `Cancelled`
  - `No-Show`
  - `Wait List`
- Replaced market segment value `(none)` with null.
- Normalized `guest_name` by:
  - removing escaped commas
  - removing backslash separators
  - trimming leading and trailing commas
  - collapsing repeated separators
  - title-casing the resulting name tokens
- Normalized `comments` into one line using ` | ` as the internal separator so the CSV stays readable and stable.

### 6. Capitalization handling

- I checked for inconsistent case variants in `market_segment`, `rate_code`, `hold_type`, `status`, and `room_type`.
- No case-variant duplicates were observed in those fields after whitespace trimming.
- Because of that, I preserved `market_segment` and `rate_code` values as-is after trimming, instead of forcing additional recasing that might alter business codes.

## Deduplication method

### Duplicate detection

Duplicates were detected **after cleaning/standardization**, not on the raw text.

Each provisional row was assigned a cleaned composite dedupe key using these columns:

- `arrival_date`
- `departure_date`
- `confirmation_number`
- `room_number`
- `room_type`
- `status`
- `rate_code`
- `rate`

Exact dedupe logic:

- If all 8 cleaned values above matched, the provisional rows were treated as duplicates of the same reservation occurrence.

Why these columns were used:

- `confirmation_number` existed for every parsed provisional row and was the strongest reservation identifier.
- `room_number` and `room_type` were included so multi-room bookings sharing a confirmation would not collapse incorrectly.
- `arrival_date` and `departure_date` separated adjacent stays.
- `status` prevented cancelled/no-show/checked-out records from merging incorrectly.
- `rate_code` and `rate` prevented pricing variants from merging silently.

### Duplicate groups found

- duplicate groups detected: `5,348`
- provisional rows removed as duplicates: `7,786`
- maximum copies found for one duplicate group: `10`

Duplicate group location:

- same-file duplicate groups: `4,836`
- cross-file duplicate groups: `512`

The cross-file duplicates came from overlapping month-boundary stays appearing in adjacent raw exports, for example stays such as `2025-08-31` to `2025-09-01`.

### How duplicates were removed

Within each duplicate group:

1. All duplicate provisional rows were sorted by a completeness score.
2. The completeness score favored rows with more populated fields, especially:
   - `guest_name`
   - `email`
   - `folio_number`
   - positive `adults_raw_primary`
   - non-empty comments and occupancy fields
3. The highest-ranked row was kept as the base row.
4. Missing values on the kept row were filled from duplicate copies when another row in the same group had that value populated.
5. The cleaned output kept exactly one row per dedupe key.
6. Every removed duplicate copy was written to `cleaned_data/guest_stays_duplicates_removed.csv`.

This means duplicates were not just dropped blindly. Missing data from duplicate copies was coalesced into the kept row when possible.

## Rows dropped vs preserved

Rows preserved:

- `10,579` cleaned reservation rows written to `cleaned_data/guest_stays_cleaned.csv`

Rows dropped:

- `7,786` provisional rows removed from the final cleaned dataset because they matched another row on the cleaned dedupe key

Important clarification:

- No raw files were edited.
- No source workbook rows were deleted from `Data/`.
- No provisional rows were dropped for missing values alone.
- No provisional rows were dropped because of long comments, null guest names, or null room numbers alone.
- The only rows removed from the final cleaned dataset were duplicate provisional rows defined by the explicit composite dedupe key above.

## Final cleaned dataset checks

Validation results for `cleaned_data/guest_stays_cleaned.csv`:

- cleaned row count: `10,579`
- dedupe key uniqueness in cleaned file: `True`
- rows with `source_occurrences > 1`: `5,348`

This means the cleaned CSV contains one row per cleaned dedupe key and retains audit information about how many copies were merged.

## Remaining data quality issues

These issues still remain and should be reviewed before Step 2:

- `guest_name` is still missing in `5,468` cleaned rows because the raw report does not expose names consistently in a dedicated field.
- `email` is missing in `1,225` cleaned rows.
- `comments` is missing in `2,442` cleaned rows.
- `room_number` is missing in `1,642` cleaned rows, mostly on cancelled or incomplete reservations.
- `comments` is still a long PMS/export note blob. It was normalized for readability but not semantically parsed yet.
- The cleaned dataset still contains PII fields:
  - `guest_name`
  - `email`
  - free-text `comments`
- Those PII fields should be removed or hashed before modeling in Step 2.

## Concerns and assumptions to review before Step 2

- Step 1 cleaned only the guest operational dataset, not the STAR benchmark workbooks.
- The parser assumes the start of each reservation block is correctly identified by the `date + rate_code + status` row pattern.
- The dedupe key assumes that matching `arrival_date`, `departure_date`, `confirmation_number`, `room_number`, `room_type`, `status`, `rate_code`, and `rate` means the rows represent the same reservation occurrence.
- Some raw blocks carried slightly different non-key values such as `adults_raw_primary` or guest-name presence. Those were resolved by keeping the most complete row and filling its blanks from the other copies.

## Step 1 summary

- files created:
  - `cleaned_data/guest_stays_cleaned.csv`
  - `cleaned_data/guest_stays_duplicates_removed.csv`
  - `cleaned_data/guest_stays_cleaning_summary.json`
  - `progress.md`
- duplicate count removed: `7,786`
- key cleaning actions performed:
  - parsed multi-line report blocks into reservation rows
  - standardized dates, numeric IDs, and numeric metrics
  - normalized whitespace, comments, emails, guest names, room numbers, and status labels
  - deduplicated on the cleaned reservation composite key
  - coalesced missing values from duplicate copies into the kept row
- concerns to review before Step 2:
  - guest names are still missing on many rows
  - comments remain large unparsed note fields
  - room numbers are missing on some records
  - PII is still present and should be removed or hashed before modeling

# Step 2 Progress: Build the Canonical Daily Modeling Table

## Scope started

This update starts the first modeling-data engineering pass.

Requested work:

- create the project structure for features, models, pricing, evaluation, notebooks, and report figures
- add a reproducible Python dependency file
- build a canonical daily modeling table anchored on `cleaned_data/block_roomsales_daily_totals_cleaned.csv`
- join in available `ReservationForecast` fields for `2023-2024`
- add date, lag, rolling, ADR, and revenue-history features
- keep Block and ReservationForecast occupancy definitions separate

## Initial files and folders added

- `requirements.txt`
- `src/`
- `src/features/`
- `src/models/`
- `src/pricing/`
- `src/evaluation/`
- `notebooks/`
- `reports/figures/`
- `processed_data/`

## Environment note

`requirements.txt` now records the Python dependencies needed for the next project phase:

- `pandas`
- `openpyxl`
- `xlrd`
- `scikit-learn`
- `matplotlib`
- `seaborn`
- `xgboost`

Note: this repository already has a raw `Data/` directory. On this Mac filesystem,
`data/processed/` resolves into that same directory, so the generated modeling
outputs will use `processed_data/` instead to keep derived files separate from
raw workbook exports.

The next action in Step 2 is to add and run the canonical modeling-table builder.

# Step 1B Progress: Clean and Document the New ReservationForecast and Block RoomSales Reports

## Scope completed

This update completes the new-data work requested for the newly added `ReservationForecast*.xls` and `Block*.xls` files only.

Work completed in this addendum:

- inspected the raw workbook layouts before cleaning
- identified what each report family contributes
- cleaned the new daily operational report data
- deduplicated the new data where appropriate
- preserved auditability with source columns and cleaning summaries
- updated `progress.md`
- updated `IMPLEMENTATION_PLAN.md` because the new files materially change the confirmed data available to the project

Work intentionally **not** done in this addendum:

- no raw files under `Data/` were modified
- the previously cleaned guest-list outputs were not redone or overwritten
- no modeling, forecasting, pricing, or feature engineering beyond cleaning/documentation was started

## Raw files used

The following raw files were read from `Data/` and were **not modified**:

### ReservationForecast family

- `Data/ReservationForecast2023.xls`
- `Data/ReservationForecast 2024.xls`

### Block RoomSales family

- `Data/Block12023roomtypes.xls`
- `Data/Block22023roomtypes.xls`
- `Data/Block32023roomtypes.xls`
- `Data/Block 4 October 4 to December 31.xls`
- `Data/Block 1  92 daysJanuary 1 to April 1 2024.xls`
- `Data/Block 2 April 2 to July 2 2024.xls`
- `Data/Block 3  July 3 to October 2 2024.xls`
- `Data/Block 4  October 3 to December 31 2024.xls`
- `Data/Block 1 January 1 to April 2 2025.xls`
- `Data/Block 2  April 3 to July 3 2025.xls`
- `Data/Block 3 July 4 to October 3 2025.xls`
- `Data/Block 4  October 4 to December 31 2025.xls`

## Folder(s) used or created

- reused existing output folder: `cleaned_data/`
- added reproducible cleaning script: `scripts/clean_new_operational_reports.py`
- used a temporary staging folder under the system temp directory to convert legacy `.xls` files into read-only `.xlsx` copies for parsing because the bundled Python environment did not include a native `.xls` reader

Important note:

- the temporary `.xlsx` staging copies were created outside the repository only to read the workbooks safely
- the permanent project outputs were saved only under `cleaned_data/`

## Cleaned files created

- `cleaned_data/reservation_forecast_daily_cleaned.csv`
- `cleaned_data/reservation_forecast_duplicates_removed.csv`
- `cleaned_data/reservation_forecast_cleaning_summary.json`
- `cleaned_data/block_roomsales_daily_totals_cleaned.csv`
- `cleaned_data/block_roomsales_room_class_daily_cleaned.csv`
- `cleaned_data/block_roomsales_room_type_daily_cleaned.csv`
- `cleaned_data/block_roomsales_adjustments_cleaned.csv`
- `cleaned_data/block_roomsales_duplicates_removed.csv`
- `cleaned_data/block_roomsales_cleaning_summary.json`
- `progress.md`
- `IMPLEMENTATION_PLAN.md`

## Raw layout inspection result

The newly added files are **not one dataset**. They are two different report families with different row structures and different analytical uses.

### ReservationForecast family

The `ReservationForecast*.xls` files are daily property-level reports.

Observed layout:

- one sheet named `ReservationForecast`
- title and metadata rows in rows `1` through `9`
- one daily row per business date starting at row `10`
- one trailing `Totals` row at the bottom of each file
- `2023` file coverage confirmed internally: `2023-01-01` through `2023-12-31`
- `2024` file coverage confirmed internally: `2024-01-01` through `2024-12-31`

Daily fields visible in the report:

- arrivals
- departures
- stayovers
- projected walk-ins
- projected cancellation / no-show percentage
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

### Block RoomSales family

The `Block*.xls` files are daily RoomSales reports with **mixed row grain** inside each sheet.

Observed layout:

- one sheet named `RoomSales`
- title and metadata rows in rows `1` through `10`
- one property-level daily total row begins whenever column `A` is a valid date
- immediately below each daily total row there are room-class and room-type rows
- a bottom summary section begins with a row starting `Summary - ...`
- a footnote row begins `*Totals for past dates are based on actual figures...`

Important structural finding:

- `Standard` and `Suite` are **room-class rollups**
- the code rows (`HKNS`, `KFNS`, `KNS`, `QQNS`, `DKSNS`, `HKOBNS`, `KESNS`, `KOBNS`, `KSSNS`, `QQOBNS`) are **leaf room-type rows**
- rows labeled `***` are **not valid room types**

This means the Block family had to be split into separate cleaned outputs so the class rollups would not be double-counted as room-type detail.

## Ambiguous or inconsistent filenames resolved during inspection

The raw filenames were not fully reliable, so I resolved date coverage from the internal report headers, not from the filenames alone.

- `Block 4 October 4 to December 31.xls` does not include a year in the filename; the internal report range confirms it is `2023-10-04` through `2023-12-31`
- `Block12023roomtypes.xls`, `Block22023roomtypes.xls`, and `Block32023roomtypes.xls` do not spell out their date ranges in the filenames; the internal report header provides the exact ranges
- `Block 1  92 daysJanuary 1 to April 1 2024.xls` contains irregular spacing and wording; the internal report header confirms the exact range `2024-01-01` through `2024-04-01`
- `ReservationForecast2023.xls` and `ReservationForecast 2024.xls` use inconsistent spacing but the internal report headers confirm clean year coverage

## Exact new information these files contain

### ReservationForecast adds

- direct daily arrivals, departures, and stayovers for `2023-01-01` through `2024-12-31`
- direct daily rooms sold and net room revenue for `2023-01-01` through `2024-12-31`
- daily transient and group pickup fields
- daily group-specific revenue and arrival fields

### Block RoomSales adds

- direct daily property-level operational totals for `2023-01-01` through `2025-12-31`
- explicit daily `on_market_rooms`
- explicit daily `out_of_order_rooms`
- explicit daily `transient_rooms`, `group_rooms`, `day_use_rooms`, and `comp_rooms`
- daily gross and net room revenue
- daily gross and net ADR
- daily gross and net RevPAR
- daily room-class rollups for `Standard` and `Suite`
- daily leaf room-type metrics for `10` room-type codes
- implicit total room inventory of `60` rooms, inferred consistently from the `Total Rooms:` header in every Block file

## Cleaning steps performed

The following transformations were performed explicitly and in this order.

### 1. Safe workbook staging for parsing

- Opened each raw `.xls` file through Excel automation in read-only form.
- Saved a temporary `.xlsx` copy outside the repository for parsing.
- This conversion step was used only for reading the files safely.
- The raw `.xls` files under `Data/` were not edited or overwritten.

### 2. ReservationForecast row extraction

- Ignored rows `1` through `9` as report title / metadata rows.
- Treated rows starting at row `10` where column `A` was a valid Excel date as daily data rows.
- Removed the trailing `Totals` row from each workbook.
- Dropped the unnamed spacer columns that had no business fields.

### 3. ReservationForecast value standardization

- Converted business dates from Excel date serial / datetime storage to ISO `YYYY-MM-DD`.
- Converted count-like columns to nullable integers.
- Converted `Projected Cxl/No-Shows` and `Occ%` into decimal rates.
  - example: `72%` became `0.72`
- Converted currency totals such as `Room Revenue (Net)` and `Group Room Revenue (Net)` to numeric values rounded to 2 decimals.
- Converted ADR / RevPAR-style metrics to numeric values rounded to 4 decimals.

### 4. Block RoomSales row extraction and split by grain

- Ignored rows `1` through `10` as report title / metadata rows.
- Parsed every row with a valid date in column `A` as a property-level daily total row.
- Parsed `Standard` and `Suite` rows as room-class rollups.
- Parsed room-type code rows as leaf room-type rows.
- Isolated `***` rows into a separate adjustment dataset instead of mixing them into the room-type dataset.
- Excluded the bottom summary section beginning at the first row whose column `A` started with `Summary -`.
- Excluded the `*Totals for past dates...` footnote rows.

### 5. Block RoomSales value standardization

- Converted business dates from Excel date serial / datetime storage to ISO `YYYY-MM-DD`.
- Converted room-count fields to nullable integers.
- Converted `Occ %` into decimal occupancy rates rounded to 4 decimals.
  - example: `38.33` became `0.3833`
- Converted gross and net revenue totals to numeric values rounded to 2 decimals.
- Converted ADR / RevPAR metrics to numeric values rounded to 4 decimals.
- Derived `property_total_rooms = 60` by dividing the `Total Rooms:` period total shown in row `10` by the number of report days in that file.

### 6. Block room-class / room-type mapping

Based on the raw report structure and exact rollup validation, the following parent-child mapping was applied:

- `Standard` class:
  - `HKNS`
  - `KFNS`
  - `KNS`
  - `QQNS`
- `Suite` class:
  - `DKSNS`
  - `HKOBNS`
  - `KESNS`
  - `KOBNS`
  - `KSSNS`
  - `QQOBNS`

This mapping was not guessed from names alone. It was confirmed because the room-type sums matched the room-class rollups exactly across all cleaned dates.

### 7. Special `***` adjustment row handling

The raw Block files contained `20` special rows labeled `***`.

Observed characteristics:

- not a valid room type
- all room-count fields equal `0`
- occupancy field observed as either `0` or the impossible placeholder value `1.7976931348623157e+308`
- some rows carry gross or net revenue adjustments even though all room counts are zero

Because of that, I:

- preserved these rows in `cleaned_data/block_roomsales_adjustments_cleaned.csv`
- set cleaned `occupancy_rate_reported` to null there because it is not a meaningful inventory metric for those rows
- preserved `occupancy_rate_raw_values_observed`
- preserved `source_occurrences` and `merged_source_rows`

## Deduplication method

Duplicates were detected **after cleaning/standardization**, not on the raw displayed text.

### ReservationForecast deduplication

Logical dedupe key:

- `business_date`

Reason:

- the ReservationForecast family is a property-level daily report and should contain one cleaned row per business date

Result:

- duplicate rows found: `0`
- duplicate rows removed: `0`

### Block RoomSales deduplication

Because the Block family was split into multiple cleaned outputs, deduplication was performed separately by output grain.

#### Property daily totals

Dedupe key:

- `business_date`

Result:

- duplicate rows found: `0`
- duplicate rows removed: `0`

#### Room-class daily rows

Dedupe key:

- `business_date`
- `room_class`

Result:

- duplicate rows found: `0`
- duplicate rows removed: `0`

#### Room-type daily rows

Dedupe key:

- `business_date`
- `room_type_code`

Result:

- duplicate rows found: `0`
- duplicate rows removed: `0`

#### Special adjustment rows

Dedupe key:

- `business_date`
- `adjustment_label_raw`
- `rooms_sold`
- `transient_rooms`
- `group_rooms`
- `day_use_rooms`
- `comp_rooms`
- `out_of_order_rooms`
- `on_market_rooms`
- `room_revenue_gross`
- `adr_gross`
- `revpar_gross`
- `room_revenue_net`
- `adr_net`
- `revpar_net`

Important note:

- I intentionally did **not** use the raw adjustment occupancy cell in the dedupe key because the raw duplicate pairs differed only in that malformed field (`0` versus `1.7976931348623157e+308`) while all meaningful adjustment metrics matched

How duplicates were removed:

1. grouped adjustment rows on the cleaned adjustment key above
2. kept the first source row in each identical pair
3. preserved the raw occupancy variants in `occupancy_rate_raw_values_observed`
4. recorded each removed duplicate copy in `cleaned_data/block_roomsales_duplicates_removed.csv`

Result:

- raw adjustment rows detected: `20`
- cleaned adjustment rows preserved: `10`
- duplicate adjustment rows removed: `10`

## Rows dropped vs preserved

### ReservationForecast

Rows preserved:

- `731` cleaned daily rows written to `cleaned_data/reservation_forecast_daily_cleaned.csv`

Rows dropped or excluded:

- `2` trailing `Totals` rows removed
- `0` duplicate daily rows removed

### Block RoomSales

Rows preserved:

- `1,096` property daily total rows written to `cleaned_data/block_roomsales_daily_totals_cleaned.csv`
- `2,192` room-class daily rows written to `cleaned_data/block_roomsales_room_class_daily_cleaned.csv`
- `10,960` room-type daily rows written to `cleaned_data/block_roomsales_room_type_daily_cleaned.csv`
- `10` cleaned adjustment rows written to `cleaned_data/block_roomsales_adjustments_cleaned.csv`

Rows dropped or excluded:

- `170` summary-section rows excluded after the first `Summary - ...` row in each Block workbook
- `12` footnote rows excluded
- `10` duplicate special-adjustment rows removed

Important clarification:

- no valid daily total rows were dropped for missing values alone
- no valid room-class rows were dropped for missing values alone
- no valid room-type rows were dropped for missing values alone
- the only rows removed as duplicates in the new data were repeated `***` adjustment copies

## Validation checks performed

### ReservationForecast coverage checks

- cleaned date coverage: `2023-01-01` through `2024-12-31`
- missing business dates after cleaning: `0`

### Block RoomSales coverage checks

- cleaned date coverage: `2023-01-01` through `2025-12-31`
- missing business dates after cleaning: `0`
- room-type code rows per cleaned date:
  - minimum: `10`
  - maximum: `10`

### Block internal reconciliation checks

The following checks passed exactly after the split into daily totals, room-class rows, room-type rows, and deduplicated adjustment rows:

- `Standard` room-class totals matched the sum of `HKNS`, `KFNS`, `KNS`, and `QQNS`
- `Suite` room-class totals matched the sum of `DKSNS`, `HKOBNS`, `KESNS`, `KOBNS`, `KSSNS`, and `QQOBNS`
- property daily totals matched the sum of:
  - all `10` leaf room-type rows
  - plus the deduplicated special adjustment rows

Validated metrics with zero mismatches:

- `rooms_sold`
- `transient_rooms`
- `group_rooms`
- `day_use_rooms`
- `comp_rooms`
- `out_of_order_rooms`
- `on_market_rooms`
- `room_revenue_gross`
- `room_revenue_net`

### Cross-family validation between ReservationForecast and Block daily totals

On the `731` shared business dates from `2023-01-01` through `2024-12-31`:

- exact matches:
  - `rooms_sold`: `731 / 731`
  - `out_of_order_rooms`: `731 / 731`
  - `room_revenue_net`: `731 / 731`
- near-matches after rounding to 2 decimals:
  - `adr_reported` versus Block `adr_net`: `728 / 731`
  - `revpar_reported` versus Block `revpar_net`: `729 / 731`
- non-identical shared fields:
  - `transient_rooms` differed on `88` dates
  - ReservationForecast `group_rooms_picked_up` versus Block `group_rooms` differed on `5` dates

Important interpretation:

- the overlapping reports strongly confirm that both families describe the same daily operations
- however, they do **not** define every metric the same way

## Values standardized or converted

### Converted to ISO dates

- `business_date` in both report families
- Block report period start / end dates and ReservationForecast report period start / end dates were also preserved as ISO audit fields

### Converted to numeric counts

- arrivals / departures / stayovers
- rooms sold
- transient rooms
- group rooms
- day use rooms
- comp rooms
- out of order rooms
- on market rooms
- group arrival counts
- total group guests in house

### Converted to decimal rates

- ReservationForecast:
  - `projected_cxl_no_show_rate`
  - `occupancy_rate_reported`
- Block RoomSales:
  - `occupancy_rate_reported`

### Converted to numeric monetary / rate fields

- `room_revenue_net`
- `room_revenue_gross`
- `group_room_revenue_net`
- `adr_reported`
- `revpar_reported`
- `adr_gross`
- `revpar_gross`
- `adr_net`
- `revpar_net`
- `group_adr_reported`

### Derived values added

- `property_total_rooms = 60` in the Block cleaned outputs
- `room_class` on the room-type cleaned output
- `source_occurrences` and `merged_source_rows` on the Block adjustment output

## Assumptions made

- `Standard` and `Suite` were treated as room-class rollups, not leaf room types, because the code-level sums matched them exactly on every cleaned date
- the `***` rows were treated as special adjustment rows rather than room types because:
  - the label is not a valid room type
  - all room-count fields are zero
  - the occupancy field is malformed / non-meaningful
  - the duplicate pairs repeat identical revenue adjustments
- the Block `Occ %` metric was treated as an occupancy rate over total property inventory because:
  - the report explicitly contains `property_total_rooms = 60`
  - `rooms_sold / 60` reproduces the reported Block occupancy values
- ReservationForecast `Occ%` was treated as a reported occupancy field without renaming its basis in the CSV because the workbook does not explicitly define the denominator
- however, based on the overlap with Block `on_market_rooms`, ReservationForecast `Occ%` appears to behave like `rooms_sold / on_market_rooms` when rounded to two decimals

## Remaining data quality issues

These issues remain and should be reviewed before modeling:

- ReservationForecast and Block RoomSales use different occupancy denominators:
  - Block `Occ %` is based on total property inventory
  - ReservationForecast `Occ%` appears to be based on on-market rooms
- ReservationForecast `Projected Walk-Ins` and `Projected Cxl/No-Shows` exist as fields but are all zero in the available 2023-2024 files
- special `***` adjustment rows occur on `10` unique dates and affect revenue metrics even though all room counts are zero
- ReservationForecast and Block daily totals are not identical for every segment-specific count:
  - transient-room differences on `88` shared dates
  - group-room differences on `5` shared dates
- these new files still do **not** expose booking creation date / time

## What this new data now provides to the project

### More historical operational history

- **Yes**
- direct daily operational history now runs from `2023-01-01` through `2025-12-31`

### Daily inventory / on market counts

- **Yes**
- explicit daily `on_market_rooms`
- explicit daily `out_of_order_rooms`
- inferred constant total room inventory of `60` rooms

### Daily rooms sold / occupied

- **Yes**
- direct daily `rooms_sold`
- direct daily occupancy percentages in both report families

### Daily room revenue

- **Yes**
- direct daily net room revenue from ReservationForecast
- direct daily gross and net room revenue from Block RoomSales

### Room-type-level daily operational metrics

- **Yes**
- room-class daily rollups for `Standard` and `Suite`
- daily leaf room-type metrics for `10` room-type codes

### Booking creation date / time

- **No**
- this new data does not provide booking creation timestamp or booking-pace history

### Other newly available fields

- daily arrivals
- daily departures
- daily stayovers
- daily transient / group / day-use / comp counts
- daily group-specific revenue and arrival fields
- daily gross and net ADR / RevPAR

## Step 1B summary

- files created:
  - `cleaned_data/reservation_forecast_daily_cleaned.csv`
  - `cleaned_data/reservation_forecast_duplicates_removed.csv`
  - `cleaned_data/reservation_forecast_cleaning_summary.json`
  - `cleaned_data/block_roomsales_daily_totals_cleaned.csv`
  - `cleaned_data/block_roomsales_room_class_daily_cleaned.csv`
  - `cleaned_data/block_roomsales_room_type_daily_cleaned.csv`
  - `cleaned_data/block_roomsales_adjustments_cleaned.csv`
  - `cleaned_data/block_roomsales_duplicates_removed.csv`
  - `cleaned_data/block_roomsales_cleaning_summary.json`
  - `scripts/clean_new_operational_reports.py`
  - `progress.md`
  - `IMPLEMENTATION_PLAN.md`
- rows cleaned:
  - ReservationForecast daily rows: `731`
  - Block daily totals: `1,096`
  - Block room-class rows: `2,192`
  - Block room-type rows: `10,960`
  - Block adjustment rows kept: `10`
- duplicate count removed:
  - ReservationForecast: `0`
  - Block RoomSales: `10`
- most important capability added:
  - the repository now contains direct daily hotel operational history across `2023`, `2024`, and `2025`, including rooms sold, on-market inventory, out-of-order rooms, gross/net room revenue, and room-class / room-type daily metrics
- most important concerns before the next step:
  - occupancy-rate denominator differences between report families must be handled explicitly
  - the `***` adjustment rows should not be mixed into room-type modeling tables blindly
  - booking creation date / time is still missing

# Step 2 Completion Update: Canonical Daily Modeling Table

## Scope completed

This update completes the requested first modeling-data step.

Work completed:

- created the initial Python project structure
- added a reproducible dependency file
- added a feature-building script for the canonical daily modeling table
- generated the first modeling-ready daily dataset
- generated a machine-readable summary of the modeling table
- validated row counts, date coverage, duplicate dates, target nulls, and ReservationForecast overlap

## Project structure added

- `src/features/`
- `src/models/`
- `src/pricing/`
- `src/evaluation/`
- `notebooks/`
- `reports/figures/`
- `processed_data/`

Important path note:

- the original requested output idea was `data/processed/`
- this repository already has a raw workbook directory named `Data/`
- on this Mac filesystem, `data/processed/` resolves into `Data/processed/`
- to avoid mixing derived modeling artifacts into the raw workbook directory, Step 2 uses `processed_data/`

## Environment file added

Created:

- `requirements.txt`

Dependencies recorded:

- `pandas`
- `openpyxl`
- `xlrd`
- `scikit-learn`
- `matplotlib`
- `seaborn`
- `xgboost`

## Feature builder added

Created:

- `src/features/build_daily_modeling_table.py`

Inputs:

- `cleaned_data/block_roomsales_daily_totals_cleaned.csv`
- `cleaned_data/reservation_forecast_daily_cleaned.csv`

Outputs:

- `processed_data/modeling_daily.csv`
- `processed_data/modeling_daily_summary.json`

## Modeling-table design

The canonical daily table is anchored on the Block RoomSales daily total file because that file has complete daily operational coverage from `2023-01-01` through `2025-12-31`.

Primary target:

- `target_rooms_sold`

Block fields were kept as the operational source of truth and prefixed where needed:

- `block_occupancy_rate_reported`
- `block_transient_rooms`
- `block_group_rooms`
- `block_day_use_rooms`
- `block_comp_rooms`
- `block_out_of_order_rooms`
- `block_on_market_rooms`
- `block_room_revenue_gross`
- `block_room_revenue_net`
- `block_adr_gross`
- `block_adr_net`
- `block_revpar_gross`
- `block_revpar_net`

ReservationForecast fields were joined for the dates where that source exists and were prefixed with `rf_`.

The two occupancy definitions were intentionally kept separate:

- `block_occupancy_rate_reported`
- `rf_occupancy_rate_reported`

Additional denominator-check columns were added:

- `block_occupancy_calc_on_total_rooms`
- `block_occupancy_calc_on_market_rooms`
- `block_reported_occ_minus_total_room_calc`
- `block_reported_occ_minus_on_market_calc`
- `rf_reported_occ_minus_block_reported_occ`

## Feature groups added

Date features:

- year
- quarter
- month
- day
- day of week
- day of year
- ISO week
- weekend flag
- month-start / month-end flags
- quarter-start / quarter-end flags
- cyclical day-of-week, month, and day-of-year encodings

Historical features:

- lag values at `1`, `7`, `14`, `28`, and `365` days
- rolling mean, median, and standard deviation over `7`, `14`, `28`, and `56` days

Historical feature base columns:

- `target_rooms_sold`
- `block_adr_net`
- `block_room_revenue_net`
- `block_occupancy_rate_reported`

All rolling features are shifted by one day before calculation so they use prior history rather than the current day's target.

## Validation results

Command run:

- `python3 src/features/build_daily_modeling_table.py`

Generated table:

- rows: `1,096`
- columns: `144`
- date coverage: `2023-01-01` through `2025-12-31`
- missing business dates: `0`
- duplicate business dates: `0`
- null target values: `0`
- rows with ReservationForecast joined: `731`
- rows without ReservationForecast joined: `365`
- ReservationForecast / Block rooms-sold matches on overlapping dates: `731`
- ReservationForecast / Block revenue matches on overlapping dates: `731`

Quality flags carried forward:

- Block rows where rooms sold exceed total rooms: `2`
- Block rows where reported occupancy exceeds `1.0`: `0`
- Block rows with negative net room revenue: `0`
- Block rows with zero rooms sold: `12`

## Step 2 next steps

Recommended next work:

- inspect the 2 dates where `target_rooms_sold > property_total_rooms`
- decide whether zero-room-sold days are valid closure / outage days or data issues
- add a baseline modeling script under `src/models/`
- create chronological train / validation / test splits
- train naive, seasonal, linear, and tree-based baselines before any deep learning work

# Step 3 Progress: Baseline Forecast Models

## Scope completed

This update completes the first baseline-modeling pass requested after Step 2.

Work completed:

- installed the dependencies from `requirements.txt` into the local Python environment
- added a baseline training script under `src/models/`
- trained simple time-series baselines and learned tabular baselines
- used chronological train / validation / test splits
- wrote metrics, predictions, a training summary, and baseline figures
- kept the learned-model feature policy conservative to avoid obvious same-day leakage

## Script added

Created:

- `src/models/train_baselines.py`

Input:

- `processed_data/modeling_daily.csv`

Outputs:

- `reports/baseline_metrics.csv`
- `reports/baseline_metrics.json`
- `reports/baseline_predictions.csv`
- `reports/baseline_training_summary.json`
- `reports/figures/baseline_predicted_vs_actual_test.png`
- `reports/figures/baseline_test_mae.png`

## Forecast target

Primary target:

- `target_rooms_sold`

Predictions were clipped to the observed physical room inventory range so model outputs cannot go below `0` or above the property room count used in the modeling table.

## Chronological split

The first baseline split is:

- train: `2023-01-01` through `2024-06-30`
- validation: `2024-07-01` through `2024-12-31`
- test: `2025-01-01` through `2025-12-31`

Rows:

- train rows: `547`
- validation rows: `184`
- test rows: `365`

## Feature policy

Learned models use only:

- date features
- shifted lag features
- shifted rolling-history features

The learned models intentionally exclude:

- same-day Block operational fields such as same-day ADR, revenue, occupancy, transient rooms, and group rooms
- all `rf_*` ReservationForecast fields
- source and audit columns

Reason:

- same-day operational fields would leak information that may not be known at forecast time
- `ReservationForecast` fields are unavailable for 2025 in the current repository and should not be treated as future-production features yet

Learned-model feature count:

- `87`

## Models trained

Direct baselines:

- `naive_previous_day`
- `seasonal_previous_week`
- `rolling_7d_mean`
- `rolling_28d_mean`

Learned baselines:

- `ridge_regression`
- `random_forest`
- `xgboost`

## Validation results

Validation period:

- `2024-07-01` through `2024-12-31`

Best validation model by MAE:

- `xgboost`
- MAE: `6.269`
- RMSE: `8.826`
- MAPE: `0.202`
- R-squared: `0.651`

Next best validation model:

- `random_forest`
- MAE: `6.684`
- RMSE: `8.979`
- MAPE: `0.220`
- R-squared: `0.638`

## Test results

Test period:

- `2025-01-01` through `2025-12-31`

Best test model by MAE:

- `xgboost`
- MAE: `8.039`
- RMSE: `11.210`
- MAPE: `0.454`
- R-squared: `0.539`

Very close second by MAE:

- `random_forest`
- MAE: `8.062`
- RMSE: `10.870`
- MAPE: `0.424`
- R-squared: `0.567`

Best simple no-learning baseline:

- `seasonal_previous_week`
- MAE: `9.551`
- RMSE: `13.438`
- MAPE: `0.350`
- R-squared: `0.338`

Interpretation:

- tree-based learned baselines beat the simple seasonal baseline on MAE and R-squared
- `random_forest` has slightly better test RMSE and R-squared than `xgboost`
- `xgboost` has the best test MAE by a very small margin
- because the XGBoost and Random Forest results are close, both should be carried into the next modeling comparison

## Metrics table created

The full metrics table is saved in:

- `reports/baseline_metrics.csv`

It includes:

- model name
- split
- row count
- MAE
- RMSE
- MAPE
- R-squared

## Figures created

Created:

- `reports/figures/baseline_predicted_vs_actual_test.png`
- `reports/figures/baseline_test_mae.png`

The predicted-vs-actual figure plots the best test models by MAE against the actual 2025 daily rooms-sold series.

## Step 3 notes and caveats

- MAPE should be interpreted carefully because the data includes zero-room-sold days and low-demand days. The script excludes actual-zero days from MAPE calculation.
- The two days where rooms sold exceed property rooms still need to be investigated before final reporting.
- This is a baseline comparison, not the final model selection step.
- The next modeling improvement should focus on data-quality review, feature enrichment, and stronger time-series validation before moving to deep learning.

## Step 3 next steps

Recommended next work:

- inspect the rows where `target_rooms_sold > property_total_rooms`
- inspect the zero-room-sold days
- add guest-list daily enrichment after removing PII
- add a model comparison report section with the baseline metrics and plots
- decide whether to use XGBoost or Random Forest as the first pricing-layer demand forecast input

# Step 4 Progress: Data-Quality Flags and Guest Daily Enrichment

## Scope completed

This update completes the immediate follow-up task after the first baseline run.

Work completed:

- inspected and exported the flagged operational daily rows
- created a reusable data-quality audit script
- created a non-PII daily guest-list enrichment builder
- generated the daily guest enrichment table
- joined guest enrichment into the canonical modeling table
- reran the baseline training pipeline against the enriched modeling table
- updated the baseline training summary to explicitly exclude same-day guest enrichment from learned model inputs

## Data-quality audit added

Created:

- `src/evaluation/audit_modeling_data_quality.py`

Inputs:

- `processed_data/modeling_daily.csv`

Outputs:

- `reports/data_quality_flags.csv`
- `reports/data_quality_flags_summary.json`

Flag counts:

- total flagged rows: `14`
- `rooms_sold_gt_property_total`: `2`
- `zero_rooms_sold`: `12`

Flagged over-capacity dates:

- `2023-01-20`: `61` rooms sold against `60` property rooms
- `2024-08-31`: `66` rooms sold against `60` property rooms

Important observation:

- both over-capacity rows have missing `block_occupancy_rate_reported`
- these should be treated as raw report anomalies or over-capacity operational edge cases until verified

Flagged zero-sold dates:

- `2023-08-26`
- `2025-01-05` through `2025-01-15`

Important zero-sold notes:

- `2025-01-09` has `0` rooms sold but `318.68` net room revenue, suggesting a revenue adjustment, late posting, or report anomaly
- `2025-01-15` has `0` rooms sold, `48` on-market rooms, and `12` out-of-order rooms, suggesting a possible partial closure or outage period
- the remaining zero-sold rows have zero revenue and should be verified as closure/outage days or raw report anomalies

No modeling values were changed by this audit. The flags are review records only.

## Guest daily enrichment added

Created:

- `src/features/build_guest_daily_enrichment.py`

Input:

- `cleaned_data/guest_stays_cleaned.csv`

Outputs:

- `processed_data/guest_daily_enrichment.csv`
- `processed_data/guest_daily_enrichment_summary.json`

Guest enrichment shape:

- rows: `370`
- columns: `66`
- coverage: `2024-12-27` through `2025-12-31`
- source guest records: `10,579`

PII excluded from enrichment output:

- `guest_name`
- `email`
- `comments`
- `confirmation_number`
- `folio_number`
- `room_number`

Guest data-quality notes carried forward:

- records with nonpositive nights: `16`
- records with rate over `1000`: `1`
- records with missing market segment: `4`
- records with missing room type: `0`

Guest feature groups created:

- daily arrival counts by status
- daily cancellation / no-show / checked-out / wait-list shares
- daily average and median arrival rate
- daily average and median nights
- daily total booked room-night proxy
- daily average adults
- daily market-segment arrival counts and shares
- daily room-type arrival counts and shares
- daily checked-out stay-date room-night proxy
- daily checked-out stay-date rate and revenue proxies

## Modeling table updated

Updated:

- `src/features/build_daily_modeling_table.py`

The canonical modeling table now joins `processed_data/guest_daily_enrichment.csv` when that file exists.

Updated output:

- `processed_data/modeling_daily.csv`
- `processed_data/modeling_daily_summary.json`

New modeling table shape:

- rows: `1,096`
- columns: `209`
- guest enrichment columns joined: `65`
- rows with guest source available: `370`
- missing business dates: `0`
- duplicate business dates: `0`

Important modeling caveat:

- guest-list data mainly covers 2025
- because the train split is `2023-01-01` through `2024-06-30`, the guest enrichment is not yet useful as a learned predictive feature under the current chronological split
- same-day guest enrichment would leak information if used directly to forecast that same day's rooms sold

## Baselines rerun

Command rerun:

- `python3 src/models/train_baselines.py`

Baseline outputs refreshed:

- `reports/baseline_metrics.csv`
- `reports/baseline_metrics.json`
- `reports/baseline_predictions.csv`
- `reports/baseline_training_summary.json`
- `reports/figures/baseline_predicted_vs_actual_test.png`
- `reports/figures/baseline_test_mae.png`

Feature policy update:

- learned models still use only date features and shifted historical lag / rolling features
- same-day Block operational fields are excluded
- same-day GuestNameList enrichment fields are excluded
- all ReservationForecast fields are excluded

Feature count used by learned baselines:

- `87`

The metrics did not change after joining guest enrichment because the learned baselines intentionally do not use same-day guest fields.

Best test model remains:

- `xgboost`
- MAE: `8.039`
- RMSE: `11.210`
- MAPE: `0.454`
- R-squared: `0.539`

Close second:

- `random_forest`
- MAE: `8.062`
- RMSE: `10.870`
- MAPE: `0.424`
- R-squared: `0.567`

## Step 4 interpretation

The project now has two important additions:

- a documented data-quality flag table for operational anomalies
- a non-PII guest daily enrichment table joined into the canonical modeling table

However, the guest enrichment should be treated carefully:

- it is valuable for 2025 diagnostics, reporting, and later feature engineering
- it is not a fair same-day predictive feature in the current model
- it cannot materially improve the current train/test baseline because guest-list history is not available for most of the train period

## Step 4 next steps

Recommended next work:

- decide how to handle the 14 flagged daily rows for final model reporting
- create a sensitivity run that excludes flagged rows from training/evaluation
- start the bounded pricing recommendation layer using XGBoost and Random Forest demand forecasts
- use guest enrichment primarily for 2025 explanation and final-report diagnostics unless earlier guest-list history becomes available

# Step 5 Progress: Flagged-Row Sensitivity and First Pricing Layer

## Scope completed

This update completes the requested next step after guest enrichment:

- ran a baseline sensitivity test around flagged operational rows
- compared baseline model rankings under flagged-row exclusions
- selected the first pricing-layer forecast model using the sensitivity result
- built a bounded room-rate recommendation layer
- generated pricing recommendations, simulation summaries, and pricing figures

## Sensitivity script added

Created:

- `src/evaluation/run_baseline_sensitivity.py`

Inputs:

- `processed_data/modeling_daily.csv`
- `reports/data_quality_flags.csv`

Outputs:

- `reports/baseline_sensitivity_metrics.csv`
- `reports/baseline_sensitivity_predictions.csv`
- `reports/baseline_sensitivity_summary.json`
- `reports/figures/baseline_sensitivity_test_mae.png`

## Sensitivity scenarios

Three scenarios were evaluated:

1. `full_data_reference`
   - no flagged rows excluded
2. `exclude_over_capacity_only`
   - excluded only the 2 rows where `target_rooms_sold > property_total_rooms`
3. `exclude_all_flagged`
   - excluded all 14 currently flagged rows
   - includes the 2 over-capacity rows and the 12 zero-room-sold rows

## Sensitivity results

### Full-data reference test results

Test rows:

- `365`

Best learned model:

- `xgboost`
- MAE: `8.039`
- RMSE: `11.210`
- R-squared: `0.539`

Close second:

- `random_forest`
- MAE: `8.062`
- RMSE: `10.870`
- R-squared: `0.567`

### Exclude over-capacity rows only

Test rows:

- `365`

Best learned model:

- `random_forest`
- MAE: `8.019`
- RMSE: `10.757`
- R-squared: `0.576`

Second:

- `xgboost`
- MAE: `8.154`
- RMSE: `11.673`
- R-squared: `0.501`

Interpretation:

- removing only the 2 over-capacity rows changes the learned-model ranking by MAE
- Random Forest becomes the best test model in this scenario

### Exclude all flagged rows

Test rows:

- `354`

Best learned model:

- `xgboost`
- MAE: `7.443`
- RMSE: `9.927`
- R-squared: `0.585`

Close second:

- `random_forest`
- MAE: `7.466`
- RMSE: `9.834`
- R-squared: `0.593`

Interpretation:

- excluding all flagged rows improves both tree-based models
- XGBoost remains the best learned model by MAE after all flagged rows are excluded
- Random Forest has slightly better RMSE and R-squared, so it should still be discussed as a near-tie

## Pricing model selected

Selected first pricing-layer forecast model:

- `xgboost`

Reason:

- it is the best learned model by test MAE in the `exclude_all_flagged` sensitivity scenario

Sensitivity metric used for selection:

- MAE: `7.443`
- RMSE: `9.927`
- R-squared: `0.585`

## Pricing script added

Created:

- `src/pricing/build_pricing_recommendations.py`

Inputs:

- `processed_data/modeling_daily.csv`
- `reports/baseline_predictions.csv`
- `reports/baseline_sensitivity_summary.json`
- `reports/data_quality_flags.csv`

Outputs:

- `reports/pricing_recommendations.csv`
- `reports/pricing_recommendations_summary.json`
- `reports/figures/pricing_recommended_vs_historical_adr.png`
- `reports/figures/pricing_monthly_revenue_simulation.png`

## Pricing rule

Reference ADR:

- historical same-day net ADR from `block_adr_net`
- fallback order:
  - 28-day rolling net ADR
  - 14-day rolling net ADR
  - 7-day lag net ADR
  - 1-day lag net ADR
  - median nonzero ADR

Forecast signal:

- `forecast_rooms_sold / property_total_rooms`

Adjustment bands:

- forecast occupancy `>= 0.90`: `+12%`
- forecast occupancy `>= 0.80`: `+8%`
- forecast occupancy `>= 0.70`: `+4%`
- forecast occupancy `<= 0.60`: `-4%`
- forecast occupancy `<= 0.50`: `-8%`
- forecast occupancy `<= 0.35`: `-12%`
- otherwise: `0%`

Bounds:

- minimum ADR: `$75`
- maximum ADR: `$350`
- maximum daily change from reference ADR: `20%`

## Pricing output shape

Pricing recommendations:

- rows: `365`
- period: `2025-01-01` through `2025-12-31`
- flagged rows in pricing period: `11`

Demand-band counts:

- `moderately_low`: `85`
- `very_high`: `78`
- `low`: `72`
- `neutral`: `66`
- `moderately_high`: `28`
- `high`: `24`
- `very_low`: `12`

## Static pricing simulation

Important caveat:

- this is a static academic counterfactual
- it starts from historical same-day ADR
- it applies bounded demand-based adjustments
- it applies recommended ADR to actual realized rooms
- it does **not** estimate demand response to price changes

### All 2025 test days

Rows:

- `365`

Historical net room revenue:

- `$2,018,342.79`

Simulated revenue at actual rooms:

- `$2,106,125.49`

Simulated revenue delta:

- `$87,782.70`

Simulated revenue delta percentage:

- `4.35%`

Average historical ADR on nonzero-actual-room days:

- `$140.08`

Average recommended ADR on nonzero-actual-room days:

- `$142.83`

### Unflagged 2025 test days

Rows:

- `354`

Historical net room revenue:

- `$2,018,024.11`

Simulated revenue at actual rooms:

- `$2,106,125.49`

Simulated revenue delta:

- `$88,101.38`

Simulated revenue delta percentage:

- `4.37%`

Average historical ADR on nonzero-actual-room days:

- `$140.08`

Average recommended ADR on nonzero-actual-room days:

- `$142.83`

## Step 5 interpretation

The sensitivity test supports using XGBoost as the first pricing-layer model if all currently flagged operational rows are excluded from model evaluation.

The pricing layer produces plausible bounded recommendations and a positive static revenue counterfactual. This is useful for the CSC 561 MVP, but it must be described carefully:

- the simulation does not prove the hotel would actually earn the simulated revenue
- it assumes rooms sold stay fixed after price changes
- it does not model price elasticity or competitor reaction
- the flagged January 2025 zero-room-sold period should be explained or excluded from final business claims

## Step 5 next steps

Recommended next work:

- create a concise final report section for data pipeline, modeling, sensitivity, and pricing
- add a model/pricing comparison table for the final paper
- decide whether final reported test metrics should use full data or the `exclude_all_flagged` scenario
- optionally add a conservative pricing scenario with smaller adjustment bands such as `2%`, `4%`, and `6%`

# Step 6 Progress: Final Report Summary and Conservative Pricing Scenario

## Scope completed

This update adds final-report-ready summary generation and a conservative pricing comparison while preserving the existing aggressive pricing recommendation output.

## Report summary script added

Created:

- `src/evaluation/build_report_summary.py`

Inputs:

- `processed_data/modeling_daily_summary.json`
- `reports/baseline_metrics.csv`
- `reports/baseline_sensitivity_metrics.csv`
- `reports/pricing_recommendations_summary.json`

Output:

- `reports/project_summary.md`

The Markdown summary includes concise final-report sections for:

- data pipeline
- feature engineering
- baseline model comparison
- sensitivity analysis
- pricing recommendation method
- limitations

## Final metric convention

The summary presents both metric conventions:

- full-data metrics as the reference view
- `exclude_all_flagged` sensitivity metrics as the primary reported result

Primary reported learned model result:

- scenario: `exclude_all_flagged`
- model: `xgboost`
- test rows: `354`
- MAE: `7.443`
- RMSE: `9.927`
- R-squared: `0.585`

Full-data reference learned model result:

- model: `xgboost`
- test rows: `365`
- MAE: `8.039`
- RMSE: `11.210`
- R-squared: `0.539`

## Conservative pricing scenario added

Updated:

- `src/pricing/build_pricing_recommendations.py`

The existing pricing recommendations remain the aggressive/default scenario:

- `reports/pricing_recommendations.csv`
- `reports/pricing_recommendations_summary.json`

The aggressive scenario keeps the original adjustment bands:

- `4%`
- `8%`
- `12%`

A conservative scenario was added with smaller bands:

- `2%`
- `4%`
- `6%`

New outputs:

- `reports/pricing_scenario_comparison.csv`
- `reports/figures/pricing_scenario_comparison.png`

## Pricing scenario comparison

Static unflagged 2025 simulation:

| Scenario | Historical Revenue | Simulated Revenue | Delta | Delta % | Average Recommended ADR |
| --- | ---: | ---: | ---: | ---: | ---: |
| aggressive | `$2,018,024.11` | `$2,106,125.49` | `$88,101.38` | `4.37%` | `$142.83` |
| conservative | `$2,018,024.11` | `$2,062,116.46` | `$44,092.35` | `2.18%` | `$141.46` |

Same caveat applies:

- this is a static counterfactual
- it applies recommended ADR to actual realized rooms
- it does not estimate demand response to price changes

## Verification run

Commands run:

- `python3 src/pricing/build_pricing_recommendations.py`
- `python3 src/evaluation/build_report_summary.py`
- `python3 -m compileall src/pricing src/evaluation`

# Step 7 Progress: Deep Learning Comparison

## Scope completed

This update adds a neural-network comparison against the current best tree models using the same primary reporting convention:

- chronological train / validation / test split
- `exclude_all_flagged` anomaly handling
- same forecast-oriented lag, rolling, and calendar features used by the tabular baselines

## Script added

Created:

- `src/models/train_deep_learning.py`

Inputs:

- `processed_data/modeling_daily.csv`
- `reports/data_quality_flags.csv`
- `reports/baseline_sensitivity_metrics.csv`

Outputs:

- `reports/deep_learning_predictions.csv`
- `reports/deep_learning_metrics.csv`
- `reports/deep_learning_model_comparison.csv`
- `reports/deep_learning_summary.json`
- `reports/figures/deep_learning_model_comparison.png`

## Models trained

The environment does not currently have TensorFlow, Keras, or PyTorch installed, so this pass uses scikit-learn's neural-network `MLPRegressor` instead of a framework-based LSTM or GRU.

MLP variants trained:

- `mlp_small`
- `mlp_medium`
- `mlp_regularized`

The best MLP configuration was selected by validation MAE and then evaluated on the held-out 2025 test set.

Best MLP by validation MAE:

- `mlp_regularized`

## Deep learning comparison result

Primary comparison on `exclude_all_flagged` test rows:

| Model | Family | Test Rows | MAE | RMSE | R-squared |
| --- | --- | ---: | ---: | ---: | ---: |
| `xgboost` | tree baseline | `354` | `7.443` | `9.927` | `0.585` |
| `random_forest` | tree baseline | `354` | `7.466` | `9.834` | `0.593` |
| `mlp_regularized` | neural network | `354` | `13.878` | `17.482` | `-0.287` |

Interpretation:

- the MLP did not beat XGBoost or Random Forest
- the neural network appears to overfit or generalize poorly relative to tree models
- this supports using XGBoost as the primary model for the MVP and positioning deep learning as a comparison / future-work item

## Why LSTM / GRU were not added in this pass

True LSTM and GRU models require a deep-learning framework such as TensorFlow, Keras, or PyTorch plus a sequence-dataset training path.

Those libraries are not installed in the current environment:

- `torch`: unavailable
- `tensorflow`: unavailable
- `keras`: unavailable

Because the current dataset has only about 1,082 usable rows after excluding flagged dates, adding a heavyweight LSTM/GRU dependency is unlikely to improve the result enough to justify the added complexity for the final report. The current comparison already shows the core point needed for the course discussion: the tree-based tabular models outperform the neural-network baseline on this small daily hotel-demand dataset.

## Report summary updated

Updated:

- `src/evaluation/build_report_summary.py`
- `reports/project_summary.md`

The project summary now includes a `Deep Learning Comparison` section.

## Verification run

Commands run:

- `python3 src/models/train_deep_learning.py`
- `python3 src/evaluation/build_report_summary.py`
- `python3 -m compileall src/models src/evaluation`

# Step 9 Progress: Proposal Alignment Artifacts

## Scope completed

This update closes the remaining gaps against the original project proposal:

- add a small Transformer time-series model
- add feature importance / attribution outputs
- add a final pipeline architecture diagram
- add high-demand scenario examples
- add occupancy and RevPAR business metrics

## Transformer model added

Updated:

- `src/models/train_deep_learning.py`

Transformer candidates added:

- `transformer_28d_small`
- `transformer_56d_regularized`

The Transformer models use PyTorch `TransformerEncoder` layers over sequential windows of the same leakage-safe lag, rolling, and calendar features used by the LSTM and GRU models.

Updated primary deep learning comparison on `exclude_all_flagged` test rows:

| Model | Family | Test Rows | MAE | RMSE | R-squared |
| --- | --- | ---: | ---: | ---: | ---: |
| `xgboost` | tree baseline | `354` | `7.443` | `9.927` | `0.585` |
| `random_forest` | tree baseline | `354` | `7.466` | `9.834` | `0.593` |
| `gru_56d_wide` | sequence neural network | `354` | `7.813` | `10.588` | `0.528` |
| `gru_56d_more_regularized` | sequence neural network | `354` | `7.822` | `10.616` | `0.525` |
| `transformer_28d_small` | sequence neural network | `354` | `7.835` | `10.305` | `0.553` |
| `transformer_56d_regularized` | sequence neural network | `354` | `7.945` | `10.561` | `0.530` |

Interpretation:

- Transformer models were competitive with the best GRU variants
- `transformer_28d_small` had the best neural-network RMSE/R-squared among the top sequence models
- `gru_56d_wide` remained the best neural-network model by MAE
- XGBoost remained the best overall model by MAE

## Final report artifact script added

Created:

- `src/evaluation/build_final_report_artifacts.py`

Outputs:

- `reports/xgboost_feature_importance.csv`
- `reports/figures/xgboost_feature_importance.png`
- `reports/figures/final_pipeline_architecture.png`
- `reports/pricing_high_demand_examples.csv`
- `reports/pricing_business_metric_comparison.csv`

## Feature importance result

Top XGBoost features:

| Rank | Feature | Importance |
| --- | --- | ---: |
| `1` | `target_rooms_sold_lag_7d` | `0.1978` |
| `2` | `target_rooms_sold_lag_14d` | `0.1185` |
| `3` | `block_room_revenue_net_lag_7d` | `0.1046` |
| `4` | `date_day_of_week_cos` | `0.0375` |
| `5` | `block_room_revenue_net_lag_1d` | `0.0331` |

Interpretation:

- recent weekly and two-week demand/revenue history are the strongest predictors
- this supports the report claim that short-term persistence and weekly seasonality drive much of the forecast signal

## Architecture diagram added

Created:

- `reports/figures/final_pipeline_architecture.png`

The diagram summarizes:

- raw operational reports
- cleaning and deduplication
- daily modeling table
- forecast model comparison
- sensitivity analysis
- bounded pricing layer
- business outputs

## High-demand scenario examples added

Created:

- `reports/pricing_high_demand_examples.csv`

The examples focus on unflagged high-demand weekend dates. Example rows include:

- `2025-10-25`
- `2025-08-09`
- `2025-11-15`
- `2025-12-06`
- `2025-11-22`
- `2025-05-24`

These examples include actual rooms sold, forecast rooms sold, historical ADR, aggressive recommended ADR, conservative recommended ADR, and simulated revenue delta.

## Occupancy and RevPAR business metrics added

Created:

- `reports/pricing_business_metric_comparison.csv`

Unflagged 2025 business metric summary:

| Scenario | Actual Occupancy | Forecast Occupancy | Static Occupancy Delta | Historical RevPAR | Simulated RevPAR | RevPAR Delta |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| aggressive | `63.63%` | `66.13%` | `0.00%` | `$95.01` | `$99.16` | `$4.15` |
| conservative | `63.63%` | `66.13%` | `0.00%` | `$95.01` | `$97.09` | `$2.08` |

Important interpretation:

- the static occupancy delta is intentionally `0.00%`
- the pricing simulation applies new ADRs to actual rooms sold
- it does not estimate demand elasticity or occupancy changes from price changes

## Report summary updated

Updated:

- `src/evaluation/build_report_summary.py`
- `reports/project_summary.md`

The project summary now includes:

- feature importance
- Transformer comparison
- pipeline diagram reference
- business metric comparison
- high-demand examples

## Verification run

Commands run:

- `python3 src/models/train_deep_learning.py`
- `python3 src/evaluation/build_final_report_artifacts.py`
- `python3 src/evaluation/build_report_summary.py`
- `python3 -m compileall src/models src/evaluation`

# Step 10 Progress: IEEE LaTeX Final Report Draft

## Scope completed

This update converts the report-ready Markdown summary into an IEEE-style LaTeX final report.

Created:

- `reports/final_report_ieee.tex`
- `reports/references.bib`
- `reports/final_report_ieee.pdf`

The report includes:

- IEEE conference document class
- title, author block, abstract, and keywords
- introduction
- data pipeline
- feature engineering
- model/evaluation methodology
- baseline model comparison
- sensitivity analysis
- MLP/LSTM/GRU/Transformer deep learning comparison
- feature importance
- pricing recommendation method
- RevPAR and occupancy business metrics
- high-demand weekend examples
- limitations
- conclusion
- IEEE-style bibliography

Figures included:

- `reports/figures/final_pipeline_architecture.png`
- `reports/figures/deep_learning_model_comparison.png`
- `reports/figures/xgboost_feature_importance.png`
- `reports/figures/pricing_recommended_vs_historical_adr.png`
- `reports/figures/pricing_scenario_comparison.png`

Citation sources included:

- XGBoost
- Random Forest
- LSTM
- GRU
- Transformer
- scikit-learn
- PyTorch
- AdamW

## Local compile status

The report was compiled locally after installing the lightweight `tectonic` LaTeX compiler with Homebrew.

Compiled output:

- `reports/final_report_ieee.pdf`

PDF page count:

- `5` pages

Compile command:

- `cd reports && tectonic final_report_ieee.tex`

Compile notes:

- final PDF was written successfully
- only minor underfull hbox warnings remain from normal two-column IEEE text layout

## Verification run

Checks run:

- verified all referenced figure files exist
- verified one `\begin{document}` and one `\end{document}`
- verified citation commands are present
- verified no TODO/FIXME markers are present
- verified final PDF page count with PyPDF2

# Step 8 Progress: True LSTM / GRU Sequence Model Sweep

## Scope completed

This update supersedes the earlier MLP-only deep learning comparison by adding true PyTorch sequence models.

Installed / added dependency:

- `torch`

Updated:

- `requirements.txt`
- `src/models/train_deep_learning.py`
- `src/evaluation/build_report_summary.py`
- `reports/project_summary.md`

Regenerated:

- `reports/deep_learning_predictions.csv`
- `reports/deep_learning_metrics.csv`
- `reports/deep_learning_model_comparison.csv`
- `reports/deep_learning_summary.json`
- `reports/figures/deep_learning_model_comparison.png`

## Sequence model setup

The LSTM and GRU models use the same leakage-safe modeling features as the tabular baselines:

- lagged demand / ADR / revenue / occupancy features
- rolling historical features
- calendar features

Each sequence model receives a lookback window ending on the prediction date. This keeps the comparison aligned with the existing chronological train / validation / test design and the `exclude_all_flagged` primary reporting convention.

Training details:

- framework: PyTorch
- device: MPS on Apple Silicon when available
- loss: Smooth L1
- optimizer: AdamW
- gradient clipping: enabled
- early stopping: validation loss
- model selection: validation MAE for the selected sequence model

Sequence candidates added:

- `lstm_14d_small`
- `lstm_28d_regularized`
- `lstm_56d_regularized`
- `gru_14d_small`
- `gru_28d_regularized`
- `gru_42d_balanced`
- `gru_56d_wide`
- `gru_56d_more_regularized`
- `gru_84d_compact`

## Best sequence results

Best sequence model by validation MAE:

- `gru_28d_regularized`
- test MAE: `8.437`
- test RMSE: `10.791`
- test R-squared: `0.509`

Best sequence model by held-out test MAE:

- `gru_56d_wide`
- test MAE: `7.813`
- test RMSE: `10.588`
- test R-squared: `0.528`

Primary comparison on `exclude_all_flagged` test rows:

| Model | Family | Test Rows | MAE | RMSE | R-squared |
| --- | --- | ---: | ---: | ---: | ---: |
| `xgboost` | tree baseline | `354` | `7.443` | `9.927` | `0.585` |
| `random_forest` | tree baseline | `354` | `7.466` | `9.834` | `0.593` |
| `gru_56d_wide` | sequence neural network | `354` | `7.813` | `10.588` | `0.528` |
| `gru_56d_more_regularized` | sequence neural network | `354` | `7.822` | `10.616` | `0.525` |
| `gru_42d_balanced` | sequence neural network | `354` | `7.937` | `10.587` | `0.528` |

Interpretation:

- the best GRU gets close to XGBoost and Random Forest
- XGBoost remains the best model by test MAE
- Random Forest remains the best model by test RMSE and R-squared
- the sequence models are useful as a course-required deep learning comparison, but the tree models are still the stronger final MVP choice

## Verification run

Commands run:

- `python3 -m pip install torch --quiet`
- `python3 src/models/train_deep_learning.py`
- `python3 src/evaluation/build_report_summary.py`
- `python3 -m compileall src/models src/evaluation`

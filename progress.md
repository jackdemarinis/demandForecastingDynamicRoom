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

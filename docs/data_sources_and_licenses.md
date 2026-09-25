# Data Sources And Reuse Notices

The operational archive contains transformed and aggregated data from several
public sources. It does not contain API keys, raw DWD GRIB downloads, private
Energy Arena responses, or the original MaStR XML export.

This page records the upstream reuse notices used for this release. It is not a
replacement for checking the current source terms before publishing a new data
snapshot.

## DWD ICON-D2

- Source: Deutscher Wetterdienst (DWD) Open Data, ICON-D2 numerical weather
  forecasts.
- Terms: DWD permits reuse of freely accessible geodata with a source notice.
- Project transformation: spatial aggregation to model clusters, conversion of
  accumulated/average fields, and derivation of renewable weather features.
- Notice: `Source: Deutscher Wetterdienst (DWD); modified and aggregated.`
- Terms: <https://www.dwd.de/EN/ourservices/opendata/opendata.html>

## Open-Meteo

- Source: Open-Meteo Single Runs API and its listed numerical weather providers.
- Terms: API data are supplied under CC BY 4.0; attribution to Open-Meteo and
  applicable upstream weather providers is required. Free API access is limited
  to non-commercial use and published rate limits.
- Project transformation: capacity-weighted point aggregation and regional
  renewable/load feature generation.
- Notice: `Weather data by Open-Meteo.com; modified and aggregated. Underlying
  model providers are identified by the provider names in the archive/configs.`
- Terms: <https://open-meteo.com/en/terms>

## ENTSO-E Transparency Platform

- Source: ENTSO-E Transparency Platform, including DE-LU day-ahead prices,
  load, load forecasts, and renewable generation/forecast series.
- Terms: data categories on ENTSO-E's current free-reuse list are available
  under CC BY 4.0. Users must name the ENTSO-E Transparency Platform as the
  publication source and must not imply endorsement.
- Project transformation: timezone normalization, quarter-hour alignment,
  cache repair, and feature construction.
- Notice: `Source: ENTSO-E Transparency Platform; modified.`
- Terms: <https://transparency.entsoe.eu/content/static_content/Static%20content/terms%20and%20conditions/181108_ENTSOE_Transparency_Terms_Conditions_MC_APPROVED.pdf>
- Free-reuse list: <https://m-transparency.entsoe.eu/content/static_content/Static%20content/terms%20and%20conditions/220218_List_of_Data_available_for_reuse.pdf>

Before publishing a snapshot, confirm that every included ENTSO-E category is
still present on the current free-reuse list.

## Marktstammdatenregister

- Source: Bundesnetzagentur Marktstammdatenregister (MaStR) public full export.
- Terms: Datenlizenz Deutschland - Namensnennung - Version 2.0.
- Project transformation: filtering to active German wind/solar units,
  coordinate/capacity processing, and cluster/region aggregation.
- Notice: `Source: Bundesnetzagentur, Marktstammdatenregister (MaStR); modified.`
- Download and licence: <https://www.marktstammdatenregister.de/MaStR/Datendownload>

## Eurostat

- Source: Eurostat population-grid data used to derive load-weather weights.
- Terms: statistical data may generally be reused when Eurostat is acknowledged
  and modifications are indicated; dataset-specific notices and listed
  exceptions still apply.
- Project transformation: mapping and normalization to weather clusters.
- Notice: `Source: Eurostat; modified.`
- Reuse notice: <https://ec.europa.eu/eurostat/help/copyright-notice>

## Natural Earth

- Source: Natural Earth country boundaries used for the Germany weather mask.
- Terms: Natural Earth raster and vector map data are in the public domain.
- Terms: <https://www.naturalearthdata.com/about/terms-of-use/>

## Snapshot Checklist

Before committing an operational archive or publishing an immutable data pack:

1. Run `pixi run operational-archive verify`.
2. Confirm the current upstream terms and ENTSO-E free-reuse list.
3. Keep this file and the manifest with the distributed data.
4. State that archived values were transformed/aggregated by this project.
5. Record the archive coverage date and Git revision in the release notes.

The data notices above are separate from the software licence. The repository
must still receive an explicit code licence before it is described as an
open-source release.

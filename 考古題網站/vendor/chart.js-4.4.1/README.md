# Chart.js 4.4.1 (vendored)

`chart.umd.js` is the unmodified `package/dist/chart.umd.js` file from the
`chart.js@4.4.1` npm package.

- npm tarball integrity: `sha512-C74QN1bxwV1v2PEujhmKjOZ7iUM4w6BWs23Md/6aOZZSlwMzeCIDGuZay++rBgChYru7/+QFeoQW0fQoP534Dg==`
- vendored file SHA-256: `74401d738dd3e03ee5dfb3b6841210fe2c4ead8a960c4011ca4ba0b78a9fd8f3`
- license: MIT — see `LICENSE.md`

It is vendored and precached so that the Analytics page — itself a core
offline asset — keeps working on a first offline visit, before the runtime
CDN cache could ever have seen the old jsDelivr copy.

When upgrading Chart.js, update this versioned directory, the script URL in
`analytics.html`, `CACHE_VERSION` and `CORE_ASSETS` in `sw.js` together, and
keep the provenance above accurate.

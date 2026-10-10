# Third-party files

These files are served by Kilo itself instead of from a CDN, so a visit to the dashboard sends
nothing (IP address, browser, time) to a third party, and the chart keeps working when a CDN is
slow, down or blocked.

## Chart.js 4.4.4

- `chartjs-4.4.4/chart.umd.js`: `dist/chart.umd.js` from the npm package
  <https://registry.npmjs.org/chart.js/-/chart.js-4.4.4.tgz> (npm integrity
  `sha512-emICKGBABnxhMjUjlYRR12PmOXhJ2eJjEHL2/dZlWjxRAZT1D8xplLFq5M0tMQK8ja+wBS/tuVEJB5C6r7VxJA==`),
  already minified. The only change is the last line, `//# sourceMappingURL=chart.umd.js.map`,
  removed so that opening the browser's developer tools does not request a map file that is not
  here.
- `chartjs-4.4.4/LICENSE.md`: the package's MIT licence.

To update: download the new version's tarball from the npm registry, check its `integrity`
(`npm view chart.js@X.Y.Z dist.integrity`), copy `dist/chart.umd.js` (without the
`sourceMappingURL` line) and `LICENSE.md` into a new `chartjs-X.Y.Z/` folder, change the path in
`app/templates/index.html`, delete the old folder and check the chart. The version in the folder
name also makes browsers fetch the new file instead of a cached old one.

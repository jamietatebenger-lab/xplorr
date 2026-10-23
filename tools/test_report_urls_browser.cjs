// Offline browser-contract test for the real reportHref() function in app.js.
// Does not run application startup code, call a live endpoint, or modify data.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const app = fs.readFileSync(path.join(__dirname, "..", "app.js"), "utf8");
const start = app.indexOf("  function safeHttpUrl(");
const end = app.indexOf("  function holderTokens(", start);
assert.ok(start >= 0 && end > start, "expected reportHref implementation in app.js");

const context = {
  isDemoString: () => false,
  PORTAL_HOMES: {
    wa: ["https://wamex.dmp.wa.gov.au/Wamex"],
    nsw: ["https://search.geoscience.nsw.gov.au"],
    qld: ["https://geoscience.data.qld.gov.au"]
  }
};
vm.runInNewContext(app.slice(start, end) + "\nthis.reportHref = reportHref;", context);
const href = context.reportHref;
const qldBase = "https://geoscience.data.qld.gov.au/data/";

assert.equal(href({st: "qld", id: "EL23186"}), "", "arbitrary id is not a QLD document");
assert.equal(href({st: "qld", id: "cr119257garbage"}), "", "malformed CR is not a document");
assert.equal(href({st: "qld", id: "cr119257"}), qldBase + "report/cr119257");
const uuid = "000acf17-3bcd-4262-9e49-3b8f6f00346e";
assert.equal(href({st: "qld", id: uuid}), qldBase + "dataset/" + uuid);
const source = "https://example.com/original-contract.pdf";
assert.equal(href({st: "qld", id: "123", u: source}), source, "preserve original harvested URL");
assert.equal(href({st: "wa", a: "0x123"}), "", "hex string is not a WA A-number");
assert.equal(
  href({st: "wa", a: "00120783"}),
  "https://wamex.dmp.wa.gov.au/Wamex/Search/ReportDetails?ANumber=120783"
);
assert.equal(href({st: "wa", a: "A120783"}), "");
assert.doesNotThrow(() => href({st: "nsw", u: "https://search.geoscience.nsw.gov.au/report/%Q"}));
assert.doesNotThrow(() => href({st: "qld", u: "https://geoscience.data.qld.gov.au/data/report/%Q"}));
const ntSource = "https://geoscience.nt.gov.au/gemis/ntgsjspui/bitstream/1/83875/1/EL23186_2004_A.pdf";
assert.equal(href({st: "nt", u: ntSource}), ntSource);
console.log("Browser report URL contract checks passed (11 assertions).");

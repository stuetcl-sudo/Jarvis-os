// These checks exercise the actual pure formatting functions in family.js.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const test = require("node:test");

const source = fs.readFileSync("app/static/js/family.js", "utf8");
function section(start, end) {
  const from = source.indexOf(start);
  const to = source.indexOf(end, from);
  assert.ok(from >= 0 && to > from, `Missing function section: ${start}`);
  return source.slice(from, to);
}
const context = vm.createContext({});
vm.runInContext(
  section("function percentage(", "function greetingFor(") +
  section("function rainProbability(", "function childRainText("),
  context,
);

test("missing measurements remain unknown, never display zero", () => {
  for (const value of [null, undefined, "", Number.NaN, Infinity]) {
    assert.equal(context.percentage(value), "–");
    assert.equal(context.measurement(value, "°C"), "–");
  }
  assert.equal(context.measurement(0, "°C"), "0 °C");
  assert.equal(context.percentage(0), "0 %");
  assert.equal(context.measurement("12.5", "°C"), "12.5 °C");
});

test("missing rain forecast never becomes a false zero-percent forecast", () => {
  for (const entry of [undefined, {}, { precipitation_probability: null },
    { precipitation_probability: "" }, { precipitation_probability: "invalid" },
    { precipitation_probability: -1 }, { precipitation_probability: 101 }]) {
    assert.equal(context.rainProbability(entry === undefined ? [] : [entry]), null);
  }
  assert.equal(context.rainProbability([{ precipitation_probability: 0 }]), 0);
  assert.equal(context.rainProbability([{ precipitation_probability: 55 }]), 55);
});

# 61 — Server settings hooks, fields and labels

Step 9 (Server settings) · Depends on: 60, 18 · Size: M

## Goal

One field component per setting kind, labelled from translations.

## Changes

- Regenerate the API types. Hooks with key `['server settings']`: list, update,
  reset.
- `src/locales/en/serverSettings.json`, nested by key path (`mqtt.host` →
  `{mqtt: {host: {label, help}}}`), plus `groups.<prefix>` titles and
  `choices.<key path>.<choice>` labels for enum values.
- `SettingField` picks a control from `kind`:
  - integer → `NumberInput` with min and max
  - boolean → `Switch`
  - enum → `Select`
  - string → `TextInput`, or `Textarea` when `max_length` exceeds 1024
    (`mqtt.tls_ca`)
  - secret → shows "set" / "not set" with a Replace action opening a
    `PasswordInput`
- Read-only when not `editable`.
- Test against `server-setting-keys.json` (task 17): every key has a `label` in
  English.

## Tests

Each kind renders and emits typed values; read-only state; the label coverage
test.

## Review focus

Setting keys contain dots, so they're nested in the JSON. That relies on
i18next's default `.` key separator.

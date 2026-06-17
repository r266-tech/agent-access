# Source Contract Strategy

Read this before creating a new companion CLI, adding a new route, or moving a
browser/CDP discovery into a durable interface.

## Strategy Classes

| Strategy | Contract | Use When |
| --- | --- | --- |
| `PUBLIC_API` | `stable` | A public or documented endpoint returns target data without a user session. |
| `COOKIE_API` | `stable` | A stable web endpoint works with the user's local session. |
| `DOM_STATE` | `visible-ui` | SSR, hydration JSON, JSON-LD, or embedded state exposes the data. |
| `UI_SELECTOR` | `visible-ui` | The action or data is naturally represented by visible UI or semantic DOM. |
| `PAGE_FETCH` | `internal-unstable` | Page-context fetch must reuse same-origin/runtime state. |
| `INTERCEPT` | `internal-unstable` | The page must naturally trigger a signed or runtime-generated request. |
| `LOCAL_APP_DB` | `local-data` | A local app database/cache/file format is the durable source. |
| `LOCAL_APP_SCRIPT` | `local-control` | A local app exposes a script, plugin, export, or automation API. |
| `DEVICE_API` | `local-control` | A local device or service API is the intended control surface. |
| `EXTERNAL_CLI` | `stable` | An existing CLI is the durable surface. |

## Required Strategy Note

Record strategy, contract, observed source, auth/session source, replay/probe
result, expected drift, failure signal, and fallback/recovery command before
promoting a route.

## Registry Fields

Registry entries should include `source_strategy`, `source_contract`,
`source_note`, and a `verify` object with required flow and fixture policy.

## Promotion Gate

A route can be hot only after source strategy, install/update/doctor, JSON
output, error shape, verification flow, write gates, and private-data exclusion
are all declared.

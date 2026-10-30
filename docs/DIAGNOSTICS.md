# Diagnostic reports

Open **About → Diagnostic reports** to download the local report or enable sharing with the configured PostHog project. Sharing starts off. Without a configured project the switch is disabled and reports stay local.

Reports record control IDs and action names, operation outcomes and durations, application revision, OS/architecture, browser family/version, and imported filenames (basenames only). Python exceptions include their type and code locations. Error messages, local variables, control values, scientific arrays, file contents, full paths, and screenshots are excluded. There is no session replay or third-party browser autocapture.

A random installation ID groups reports; a session ID groups one browser workspace. The local report uses `GECKO_SETTINGS_DIR` when set, otherwise `~/Documents/GeckoPlotter`. Logs rotate at approximately 1 MB, retaining the current and previous file. Download exports the current file. Local reports are recorded even with sharing off, as stated in the About window.

## Connect the project

Create a free PostHog project and put its public **Project API key** (`phc_…`) in the repository's `diagnostics.json`, with the matching ingestion host (`https://eu.i.posthog.com` or `https://us.i.posthog.com`). Do not use a personal API key. `GECKO_POSTHOG_KEY` and `GECKO_POSTHOG_HOST` can override those values for testing. The default configuration has no key and sends nothing.

The standard launcher downloads this configuration with the app. Each installation must enable sharing in About. The background sender posts bounded batches to `/batch/` every three seconds; a three-second network timeout cannot block a user operation. Turning sharing off clears unsent queued events. A request already in flight may finish. Offline batches remain in the local log, but are not automatically replayed to PostHog later.

In PostHog, filter `ui_action`, `callback_finished`, `client_error`, and `$exception` by installation/session ID. `callback_finished` distinguishes a save download being prepared from the file actually reaching disk; the browser does not expose confirmation of a completed disk write.

## Validation

Python and JavaScript tests cover the metadata allowlist, filename path removal, disabled/unconfigured delivery, network failure, sanitized exceptions, pattern-matched channel callback outcomes, and browser events that exclude values and error messages. Cloud ingestion requires a real project key and must be verified separately after connecting the project.
